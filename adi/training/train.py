"""Train a "target / not target" image classifier and export it for the C++ camera app.

Dataset layout (one folder per class, any image size, jpg/png):

    <data>/target/       images that contain the target
    <data>/not_target/   images that do not

--data, --val-data and --test-data each accept several folders (for example SARD and NOMAD).
Training mixes them at random; test scores are reported for each folder and combined.

Outputs in --out (default: adi/model):
    model.keras        Keras model (for retraining / inspection)
    model.onnx         model used by adi/camera/target_camera.cpp
    model_info.json    input size and default threshold, read by the C++ app

See adi/README.md for full instructions.
"""
import argparse
import json
import os
import sys

import numpy as np
import tensorflow as tf
from tensorflow import keras

CLASS_NAMES = ["not_target", "target"]  # index 1 = target, so the model outputs P(target)


def parse_args():
    here = os.path.dirname(os.path.abspath(__file__))
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", required=True, nargs="+", help="dataset folder(s) containing target/ and not_target/")
    p.add_argument("--out", default=os.path.join(here, "..", "model"), help="output folder")
    p.add_argument("--img-size", type=int, default=224, help="square input size in pixels")
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--epochs", type=int, default=10, help="epochs with the pretrained base frozen")
    p.add_argument("--fine-tune-epochs", type=int, default=5, help="extra epochs with the top of the base unfrozen (0 to skip)")
    p.add_argument("--val-data", nargs="+", help="separate validation folder(s); if omitted, --val-split of each --data folder is used")
    p.add_argument("--test-data", nargs="+", help="optional test folder(s), evaluated once at the end")
    p.add_argument("--val-split", type=float, default=0.2, help="fraction of --data held out for validation when --val-data is not given")
    p.add_argument("--threshold", type=float, default=0.5, help="default decision threshold written to model_info.json")
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args()


def image_folder(path, args, **kwargs):
    for name in CLASS_NAMES:
        folder = os.path.join(path, name)
        if not os.path.isdir(folder):
            sys.exit(f"Missing folder: {folder}\nThe dataset needs subfolders {CLASS_NAMES}.")
    return keras.utils.image_dataset_from_directory(
        path,
        class_names=CLASS_NAMES,
        label_mode="binary",
        seed=args.seed,
        image_size=(args.img_size, args.img_size),
        batch_size=args.batch_size,
        crop_to_aspect_ratio=True,  # center crop, same as the C++ app does
        **kwargs,
    )


def count_labels(datasets):
    counts = np.zeros(2, dtype=np.int64)
    for ds in datasets:
        for path in ds.file_paths:
            counts[CLASS_NAMES.index(os.path.basename(os.path.dirname(path)))] += 1
    return counts


def combine(datasets, batch_size, shuffle):
    """Merge per-folder datasets into one. When shuffling, draw images from each at random."""
    if len(datasets) == 1:
        return datasets[0]
    singles = [ds.unbatch() for ds in datasets]
    if shuffle:
        sizes = np.array([len(ds.file_paths) for ds in datasets], dtype=np.float64)
        merged = tf.data.Dataset.sample_from_datasets(singles, weights=list(sizes / sizes.sum()), stop_on_empty_dataset=False)
    else:
        merged = singles[0]
        for ds in singles[1:]:
            merged = merged.concatenate(ds)
    return merged.batch(batch_size)


def load_datasets(args):
    """Returns train and validation datasets, the per-folder training datasets, and a list of (name, test dataset)."""
    if args.val_data:
        train_parts = [image_folder(d, args) for d in args.data]
        val_parts = [image_folder(d, args, shuffle=False) for d in args.val_data]
    else:
        pairs = [image_folder(d, args, validation_split=args.val_split, subset="both") for d in args.data]
        train_parts, val_parts = [t for t, _ in pairs], [v for _, v in pairs]
    tests = [(d, image_folder(d, args, shuffle=False)) for d in (args.test_data or [])]
    return (combine(train_parts, args.batch_size, True), combine(val_parts, args.batch_size, False), train_parts, tests)


def build_model(img_size):
    # Input: RGB float pixels in [0, 255]. Scaling to MobileNetV2's [-1, 1] range
    # happens inside the model, so the C++ side only has to resize the frame.
    inputs = keras.Input(shape=(img_size, img_size, 3), name="input")
    x = keras.layers.Rescaling(1.0 / 127.5, offset=-1.0)(inputs)
    base = keras.applications.MobileNetV2(
        input_shape=(img_size, img_size, 3), include_top=False, weights="imagenet", pooling="avg"
    )
    base.trainable = False
    x = base(x, training=False)  # keep BatchNorm in inference mode, also while fine-tuning
    x = keras.layers.Dropout(0.2)(x)
    outputs = keras.layers.Dense(1, activation="sigmoid", name="p_target")(x)
    return keras.Model(inputs, outputs), base


def compile_model(model, learning_rate):
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate),
        loss="binary_crossentropy",
        metrics=[
            keras.metrics.BinaryAccuracy(name="accuracy"),
            keras.metrics.Precision(name="precision"),
            keras.metrics.Recall(name="recall"),
            keras.metrics.AUC(name="auc"),
        ],
    )


def export_onnx(model, img_size, path):
    import tf2onnx

    spec = (tf.TensorSpec((None, img_size, img_size, 3), tf.float32, name="input"),)

    @tf.function(input_signature=spec)
    def predict(x):
        return model(x, training=False)

    # inputs_as_nchw makes the ONNX input [N, 3, H, W], which is what cv::dnn::blobFromImage produces.
    tf2onnx.convert.from_function(predict, input_signature=spec, opset=13, inputs_as_nchw=["input"], output_path=path)


def check_onnx(model, onnx_path, val_ds):
    """Compare ONNX output with Keras on one validation batch."""
    try:
        import onnxruntime as ort
    except ImportError:
        print("onnxruntime not installed; skipping ONNX check.")
        return
    images, _ = next(iter(val_ds))
    expected = model(images, training=False).numpy()
    session = ort.InferenceSession(onnx_path)
    nchw = np.transpose(images.numpy(), (0, 3, 1, 2)).astype(np.float32)
    got = session.run(None, {session.get_inputs()[0].name: nchw})[0]
    diff = float(np.max(np.abs(expected - got)))
    print(f"ONNX check: max difference vs Keras = {diff:.6f}")
    if diff > 1e-3:
        sys.exit("ONNX output does not match Keras; do not use this model.onnx.")


def main():
    args = parse_args()
    keras.utils.set_random_seed(args.seed)
    os.makedirs(args.out, exist_ok=True)

    train_ds, val_ds, train_parts, tests = load_datasets(args)
    counts = count_labels(train_parts)
    print(f"Training images: not_target={counts[0]}, target={counts[1]}")
    if counts.min() == 0:
        sys.exit("Both classes need at least one training image.")
    # Weight classes so an unbalanced dataset doesn't just learn "never the target".
    class_weight = {i: counts.sum() / (2.0 * counts[i]) for i in range(2)}

    augment = keras.Sequential([
        keras.layers.RandomFlip("horizontal"),
        keras.layers.RandomRotation(0.08),
        keras.layers.RandomZoom(0.15),
        keras.layers.RandomBrightness(0.2, value_range=(0, 255)),
        keras.layers.RandomContrast(0.2),
    ])
    autotune = tf.data.AUTOTUNE
    train_ds = train_ds.map(lambda x, y: (augment(x, training=True), y), num_parallel_calls=autotune).prefetch(autotune)
    val_ds = val_ds.cache().prefetch(autotune)

    model, base = build_model(args.img_size)
    early_stop = keras.callbacks.EarlyStopping(monitor="val_loss", patience=3, restore_best_weights=True)

    print("\n== Stage 1: train the classifier head ==")
    compile_model(model, 1e-3)
    model.fit(train_ds, validation_data=val_ds, epochs=args.epochs, class_weight=class_weight, callbacks=[early_stop])

    if args.fine_tune_epochs > 0:
        print("\n== Stage 2: fine-tune the top of MobileNetV2 ==")
        stage1_weights = model.get_weights()
        stage1_loss = model.evaluate(val_ds, verbose=0, return_dict=True)["loss"]
        base.trainable = True
        for i, layer in enumerate(base.layers):
            # Only the top 30 layers train, and BatchNorm stays frozen: updating its statistics
            # on a small dataset wrecks the pretrained features.
            layer.trainable = i >= len(base.layers) - 30 and not isinstance(layer, keras.layers.BatchNormalization)
        compile_model(model, 1e-5)
        early_stop = keras.callbacks.EarlyStopping(monitor="val_loss", patience=3, restore_best_weights=True)
        model.fit(train_ds, validation_data=val_ds, epochs=args.fine_tune_epochs, class_weight=class_weight, callbacks=[early_stop])
        stage2_loss = model.evaluate(val_ds, verbose=0, return_dict=True)["loss"]
        if stage2_loss > stage1_loss:
            print(f"Fine-tuning did not help (val_loss {stage2_loss:.4f} vs {stage1_loss:.4f}); keeping the stage 1 model.")
            model.set_weights(stage1_weights)

    print("\n== Validation ==")
    results = model.evaluate(val_ds, return_dict=True)
    for name, value in results.items():
        print(f"  {name}: {value:.4f}")
    test_results = {}
    for folder, test_ds in tests:
        print(f"\n== Test: {folder} ==")
        test_results[folder] = model.evaluate(test_ds, return_dict=True)
        for name, value in test_results[folder].items():
            print(f"  {name}: {value:.4f}")

    keras_path = os.path.join(args.out, "model.keras")
    onnx_path = os.path.join(args.out, "model.onnx")
    model.save(keras_path)
    export_onnx(model, args.img_size, onnx_path)
    check_onnx(model, onnx_path, val_ds)

    info = {
        "img_size": args.img_size,
        "threshold": args.threshold,
        "input": "RGB, float 0-255, NCHW, center-cropped to square",
        "output": "probability that the image contains the target",
        "val_metrics": {k: round(float(v), 4) for k, v in results.items()},
    }
    if test_results:
        info["test_metrics"] = {
            folder: {k: round(float(v), 4) for k, v in metrics.items()} for folder, metrics in test_results.items()
        }
    with open(os.path.join(args.out, "model_info.json"), "w") as f:
        json.dump(info, f, indent=2)
    print(f"\nSaved {keras_path}, {onnx_path} and model_info.json")


if __name__ == "__main__":
    main()

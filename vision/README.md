# adi: target detection

Two parts:

- `training/train.py` trains a TensorFlow image classifier that answers one question:
  "is the target in this picture?" It exports `model/model.onnx`.
- `camera/target_camera.cpp` reads frames from a USB camera (Logitech webcam), runs the
  model on each frame, and prints `TARGET_FOUND` / `TARGET_LOST`.

The model is trained on two aerial search and rescue datasets, SARD and NOMAD (section 1).
Section 4 compares it with OpenCV's built-in HOG people detector, and section 5 covers whether
it can run on the robot's ESP32.

Everything runs offline once installed. The only download during training is the
pretrained MobileNetV2 weights (about 9 MB, first run only, cached in `~/.keras`).

## 1. Prepare the dataset

### Dataset used: SARD (search and rescue)

The model is trained on **SARD** (Search and Rescue Dataset), found on **Kaggle**. The
download is a Roboflow export (`sard-8xjhy`, version 17, "TILES_3x3"):
https://universe.roboflow.com/datasets-pdabr/sard-8xjhy

- 5755 aerial images, 640×640, with people labeled as `human` in YOLOv8 format.
- It's 821 MB, so it is **not committed**. `vision/search-and-rescue/` is in `.gitignore`.
  Download it from Kaggle and unzip it so you have `vision/search-and-rescue/train/`,
  `valid/`, `test/`, and `data.yaml`.

SARD labels boxes around people, but the classifier only needs "person in the image or not".
`prepare_yolo.py` sorts each split by its label files: an image with at least one box goes in
`target/`, an image with none goes in `not_target/`. It symlinks the images, so no extra
disk space is used.

```sh
cd vision
python training/prepare_yolo.py --yolo search-and-rescue --out search-and-rescue/classification
```

| Split | target (person) | not_target |
|---|---|---|
| train | 3470 | 571 |
| valid | 967 | 177 |
| test | 486 | 84 |

The classes are unbalanced (about 6 to 1), so the training script weights `not_target` higher.

### Dataset used: NOMAD

**NOMAD** (Natural, Occluded, Multi-scale Aerial Dataset) is from https://github.com/ArtRuss/NOMAD,
licensed CC BY 4.0. It has 100 actors filmed by drone at 10, 30, 50, 70, and 90 m while
walking, lying down, and hiding. It includes 42,825 annotated frames at 5472×3078, each with a
person box and a visibility level (10–100% of the body visible), plus 500 "true negative"
scenes with nobody in them.

If you use it, cite the authors (BibTeX is in `vision/NOMAD/README.md`): Russell Bernal,
Scheirer, Cleland-Huang, "NOMAD: A Natural, Occluded, Multi-Scale Aerial Dataset, for
Emergency Response Scenarios", WACV 2024.

**Where it lives.** The repo is cloned into `vision/NOMAD/` and the downloaded data goes in
`vision/NOMAD/data/`. The whole folder is in `.gitignore`.

**Downloading.** The images are only on Google Drive, as 10 zip files totaling about 290 GB.
Drive blocked every one of those zips with "quota exceeded", and it began blocking single
frames after about 300. `download_nomad.py` downloads `annotations.json`, `TN.zip` (3.2 GB,
the empty scenes), and a sample of frames, by default 12 per actor and distance for the
10, 30, and 50 m distances:

```sh
cd vision
git clone https://github.com/ArtRuss/NOMAD.git NOMAD
python training/download_nomad.py --out NOMAD/data
```

Re-run it later to fetch more. It skips files it already has. **The current model uses only
278 frames, from actors 1–10**, because Drive stopped serving files after that. Re-running the
download when the quota resets (usually within 24 hours) and retraining should improve the
NOMAD results.

**Preparing.** A whole 5472×3078 frame shrunk to 224×224 makes the person a few pixels tall,
so `prepare_nomad.py` cuts square crops instead. The crop size depends on the distance
(1026 px at 10 m down to 216 px at 50 m), so the person fills about 20% of every crop,
similar to SARD. It reads images straight from `frames/` and `TN.zip` without extracting.

```sh
python training/prepare_nomad.py --nomad NOMAD/data --out NOMAD/classification \
  --valid-actors 7 --test-actors 6 --pos-per-frame 5 --neg-per-frame 1 --neg-per-tn 3
```

- `target/`: 5 crops per frame containing the person, at different positions in the crop.
  Frames where the person is less than 30% visible are skipped (`--min-visibility`).
- `not_target/`: 1 person-free crop per frame, and 3 crops per empty scene from `TN.zip`.
- Splits are **by actor**, so near-identical frames of one person never appear in both
  training and test. With only actors 1–10 downloaded, actor 7 is validation and actor 6 is
  test. With the full dataset, drop `--valid-actors`/`--test-actors`, and actors ending in 7
  and 9 are used instead.
- The 70 and 90 m distances are left out by default (`--distances`). A person there is about
  25 px tall in the original frame, too blurry to learn from once enlarged.

| Split | target (person) | not_target |
|---|---|---|
| train | 735 | 1029 |
| valid | 160 | 41 |
| test | 150 | 39 |

### Using your own images

The training script needs two folders of images:

```
dataset/
  target/        images where the target IS visible
  not_target/    images where it is NOT (empty rooms, rubble, floor, other objects)
```

- Any size and aspect ratio, `.jpg` or `.png`. Images are center-cropped to a square and
  resized, so keep the target near the middle of the photo.
- Aim for at least 200 images per folder. More variety (lighting, distance, angle,
  background) matters more than more copies of the same shot.
- Put images taken **with the robot's own Logitech camera** in both folders if you can.
  A model trained only on internet or aerial photos often does worse on a different camera.
- If the search and rescue dataset comes with bounding boxes (for example YOLO or COCO
  labels), crop or sort it into these two folders first. Images with at least one labeled
  target go in `target/`, images with none go in `not_target/`.

The class order is fixed: `not_target` = 0, `target` = 1. The model outputs the
probability of `target`.

## 2. Train

Requires Python 3.9–3.12 (TensorFlow doesn't support 3.13+ yet).

```sh
cd vision/training
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python train.py --data /path/to/dataset
```

For SARD, use its own validation and test splits (run from `vision/`):

```sh
python training/train.py \
  --data search-and-rescue/classification/train \
  --val-data search-and-rescue/classification/valid \
  --test-data search-and-rescue/classification/test
```

To train on **both SARD and NOMAD** (this is how the current model was made), list a folder
from each dataset. Training draws images from both at random, and the test scores are reported
for each dataset separately:

```sh
python training/train.py \
  --data search-and-rescue/classification/train NOMAD/classification/train \
  --val-data search-and-rescue/classification/valid NOMAD/classification/valid \
  --test-data search-and-rescue/classification/test NOMAD/classification/test
```

Either command takes a few minutes on a laptop CPU (about 10 s per epoch on an M-series Mac).

Output goes to `vision/model/`:

| File | Used by |
|---|---|
| `model.onnx` | the C++ camera app |
| `model_info.json` | the C++ camera app (input size, threshold) and you (validation scores) |
| `model.keras` | retraining or inspecting in Python (not committed, too large) |

### What the script does

1. Loads the images. Validation uses `--val-data` if given, otherwise 20% of `--data` (`--val-split`).
2. Weights the classes so an unbalanced dataset doesn't just learn "never the target".
3. Augments training images: random flip, rotation, zoom, brightness, contrast.
4. **Stage 1:** a MobileNetV2 pretrained on ImageNet, frozen, with a new 1-output head.
   Trains the head for `--epochs` (default 10) at learning rate 1e-3.
5. **Stage 2:** unfreezes the top 30 layers of MobileNetV2, except BatchNorm layers, and
   fine-tunes for `--fine-tune-epochs` (default 5) at learning rate 1e-5. Use `0` to skip.
   If this makes validation loss worse, the stage 1 model is kept.
6. Both stages stop early if validation loss doesn't improve for 3 epochs, keeping the best weights.
7. Prints validation accuracy, precision, recall, and AUC.
8. Exports to ONNX and checks that the ONNX output matches the Keras model.

### Options

| Option | Default | Notes |
|---|---|---|
| `--data` | (required) | one or more dataset folders |
| `--out` | `vision/model` | output folder |
| `--img-size` | 224 | MobileNetV2 accepts 96, 128, 160, 192, 224. Smaller is faster on the laptop, less accurate. |
| `--batch-size` | 32 | lower it if you run out of memory |
| `--epochs` | 10 | stage 1 |
| `--fine-tune-epochs` | 5 | stage 2 |
| `--val-data` | | one or more validation folders. If omitted, `--val-split` of each `--data` folder is used. |
| `--test-data` | | one or more test folders, evaluated once at the end and saved in `model_info.json` |
| `--val-split` | 0.2 | only used without `--val-data` |
| `--threshold` | 0.5 | default threshold saved for the camera app |
| `--seed` | 42 | same seed = same train/validation split |

### Current model (trained on SARD + NOMAD)

Trained with the SARD + NOMAD command above, default settings, 224×224. The threshold in
`model_info.json` is set to **0.7**, chosen on the validation sets. At 0.5 the model flagged
53% of empty SARD validation images.

Results on the **test** splits, which the model never saw during training:

| Model | SARD: people found | SARD: false alarms | NOMAD: people found | NOMAD: false alarms |
|---|---|---|---|---|
| SARD + NOMAD, threshold 0.7 (current) | 90% | 23% | 72% | 0% |
| SARD only, threshold 0.5 (previous) | 86% | 23% | 88% | 13% |

"False alarms" is the share of images without a person that the model flagged.

Adding NOMAD improved SARD recall and removed NOMAD false alarms. NOMAD recall dropped,
though. The test set is a single actor (actor 6) with 150 crops, and the training data has only
8 NOMAD actors, so these NOMAD numbers are noisy. More NOMAD frames are the next step (see
"Downloading" above). Lower the threshold to find more people at the cost of more false
alarms. On validation, threshold 0.5 found 96% of SARD people and 62% of NOMAD people.

### Reading the results

- **Recall**: of the images with the target, how many it caught. For search and rescue this
  matters most. A missed person is worse than a false alarm.
- **Precision**: of the images it flagged, how many really had the target.
- If recall is too low, lower the threshold (`--threshold 0.3` here, or at run time in the
  camera app). That catches more targets at the cost of more false alarms.
- Validation scores near 100% on a small dataset usually mean the validation images are too
  similar to the training ones. Test on new photos from the robot's camera before trusting it.

## 3. Build and run the camera app

Requires OpenCV 4.x or 5.x with the `dnn` module, and CMake.

```sh
brew install opencv cmake            # macOS
# sudo apt install libopencv-dev cmake   # Ubuntu

cd vision/camera
cmake -S . -B build
cmake --build build
```

Run from the repo root (the default model path is `vision/model/model.onnx`):

```sh
vision/camera/build/target_camera --list        # find the Logitech camera's index
vision/camera/build/target_camera --camera 1    # usually 1 on a laptop; 0 is the built-in camera
```

A window shows the camera with a green border when the target is found and red when it isn't.
Press `q` or `Esc` to quit. Stdout prints only state changes, so other programs can read it:

```
TARGET_FOUND p=0.93
TARGET_LOST p=0.21
```

| Option | Default | Notes |
|---|---|---|
| `--camera N` | 0 | camera index |
| `--source PATH` | | image, video, or image sequence (`frames/f_%03d.jpg`) instead of a camera |
| `--model PATH` | `vision/model/model.onnx` | |
| `--info PATH` | `model_info.json` next to the model | |
| `--threshold T` | from `model_info.json` | |
| `--smooth N` | 5 | averages the last N frames so one bad frame doesn't trigger it |
| `--width W --height H` | 1280×720 | requested camera resolution |
| `--no-window` | | no preview window (headless) |

"Lost" needs the average to fall 0.1 below the threshold, so the output doesn't flicker
when the probability hovers right at the threshold.

On a single image (`--source photo.jpg`) it prints one line, `TARGET_FOUND` or
`TARGET_NOT_FOUND`, and exits. This is useful for checking the model on new photos.

**macOS:** the first run asks for camera permission for your terminal app. If you denied it,
re-enable it in System Settings → Privacy & Security → Camera.

## 4. Comparison with OpenCV's HOG people detector

`camera/compare_detectors.cpp` runs the trained model and OpenCV's built-in person detector
(`HOGDescriptor::getDefaultPeopleDetector()`, the classic Dalal–Triggs pedestrian detector)
on the same labeled images. The model uses exactly the camera app's preprocessing. For HOG,
"found" means `detectMultiScale` returned at least one person.

```sh
cmake --build vision/camera/build
vision/camera/build/compare_detectors --model vision/model/model.onnx --threshold 0.7 \
  vision/search-and-rescue/classification/test vision/NOMAD/classification/test
# add --hog-upscale 2 to enlarge images before HOG
```

Results on the test splits. Timings are for a single image on one Apple M-series laptop:

| Detector | SARD: people found | SARD: false alarms | NOMAD: people found | NOMAD: false alarms | Time per image |
|---|---|---|---|---|---|
| Trained model (threshold 0.7) | **90%** | 23% | **72%** | 0% | 2–4 ms |
| OpenCV HOG | 4% | 2% | 3% | 0% | 1.5–7 ms |
| OpenCV HOG, images enlarged 2× | 24% | 14% | 11% | 0% | 8–34 ms |

On full 1280×720 frames, the camera's resolution, the model took 4.2 ms per frame and HOG
17.6 ms. The model only ever sees a 224×224 image, so its time barely depends on camera
resolution.

**How to read this.** HOG misses almost everyone here because it was built for upright
pedestrians seen from the side at least 64×128 px tall. These test images are taken from a
drone looking down, and the people are small, lying down, or partly hidden. That matches the
datasets but **not a ground robot's camera**. From the robot's height, people appear upright
and larger, which is the case HOG was designed for, and the trained model has never seen that
view. Neither result predicts how the robot will do. Collect a few hundred labeled frames from
the robot's own camera and run `compare_detectors` on that folder to compare them fairly.

## 5. Can it run on the ESP32?

**No, not this model on the robot's ESP32 (`esp32dev`).** It's far too big, and the board
also has no way to connect the Logitech camera.

| | This model | ESP32 (esp32dev) |
|---|---|---|
| Parameters | 2.26 million | |
| Compute per image | 299 million multiply-adds | |
| Model file | 8.9 MB (ONNX, float32), **2.7 MB** (TFLite, int8) | 4 MB flash total, shared with the firmware |
| Working memory | largest single layer output alone is **1.2 MB** at int8 | **520 KB** SRAM total, no PSRAM |
| Camera | USB webcam | the classic ESP32 has no USB host port, so it can't read a USB webcam |

For scale, Espressif's TensorFlow Lite Micro person-detection example is a much smaller model
(96×96 grayscale, about 250 KB). It takes **380 ms** per image on an ESP32 and **54 ms** on an
ESP32-S3, with Espressif's optimized ESP-NN kernels
([esp-tflite-micro](https://github.com/espressif/esp-tflite-micro)). This model needs about
40× more compute. Even if memory allowed it, that is roughly 15 s per image on the ESP32
and 2 s on an S3. That's an estimate by scaling, not a measurement.

**LoRa doesn't change the verdict much, but it rules out a workaround.** The LoRa radio chip
does the modulation itself, and the ESP32 only moves bytes over SPI and handles an interrupt,
so the radio adds little CPU load. Short messages like `TARGET_FOUND p=0.93` fit easily. LoRa
is too slow to stream camera images to the laptop for detection, though. Typical rates are
about 0.3–20 kbit/s, so one small 10 KB JPEG takes seconds to tens of seconds to send. If the
camera is on the robot, detection has to run on the robot.

**Options:**

1. **Run the camera and model on a laptop or other computer**, as `target_camera` does now.
   This works today, but only where a USB cable reaches the camera, so it fits a base station
   better than a moving robot.
2. **Put a camera board on the robot and run a much smaller model there.** For example, an
   ESP32-S3 board with a built-in camera and 8 MB PSRAM, such as the ESP32-S3-EYE or XIAO
   ESP32S3 Sense. You'd retrain with a tiny network, for example MobileNetV2 at width 0.35
   with 96×96 input, quantized to int8 (a few hundred KB). Run inference as a FreeRTOS task on
   one core and LoRa on the other, and send only the yes/no result over LoRa. Expect lower
   accuracy than the current model, so it would need its own test.
3. **Put a small Linux computer on the robot**, such as a Raspberry Pi 4/5, with the Logitech
   camera. It can run this exact model and app (the laptop needs about 4 ms per frame; a Pi
   will be slower but usable). It then tells the ESP32 over serial, and the ESP32 keeps handling
   motors and LoRa. This costs more power and weight.

For a hackathon, option 3 reuses everything already built here. Option 2 is the only one
where the ESP32 does the detecting itself.


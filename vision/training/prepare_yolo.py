"""Sort a YOLO-format dataset into the target/ and not_target/ folders train.py expects.

An image goes in target/ if its label file has at least one box, otherwise in not_target/.
Images are symlinked, not copied.

    python prepare_yolo.py --yolo ../search-and-rescue --out ../search-and-rescue/classification

Input:  <yolo>/<split>/images/*.jpg and <yolo>/<split>/labels/*.txt for split in train, valid, test
Output: <out>/<split>/target/ and <out>/<split>/not_target/
"""
import argparse
import os
import sys

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--yolo", required=True, help="YOLO dataset folder (contains train/, valid/, test/)")
    p.add_argument("--out", required=True, help="output folder")
    p.add_argument("--splits", nargs="+", default=["train", "valid", "test"])
    args = p.parse_args()

    found_any = False
    for split in args.splits:
        image_dir = os.path.join(args.yolo, split, "images")
        label_dir = os.path.join(args.yolo, split, "labels")
        if not os.path.isdir(image_dir):
            print(f"Skipping {split}: no {image_dir}")
            continue
        found_any = True
        counts = {"target": 0, "not_target": 0}
        for cls in counts:
            os.makedirs(os.path.join(args.out, split, cls), exist_ok=True)

        for name in sorted(os.listdir(image_dir)):
            stem, ext = os.path.splitext(name)
            if ext.lower() not in IMAGE_EXTS:
                continue
            label_path = os.path.join(label_dir, stem + ".txt")
            has_box = False
            if os.path.exists(label_path):
                with open(label_path) as f:
                    has_box = any(line.strip() for line in f)
            cls = "target" if has_box else "not_target"

            link = os.path.join(args.out, split, cls, name)
            if os.path.lexists(link):
                os.remove(link)
            src = os.path.abspath(os.path.join(image_dir, name))
            os.symlink(os.path.relpath(src, os.path.dirname(os.path.abspath(link))), link)
            counts[cls] += 1

        print(f"{split}: target={counts['target']}, not_target={counts['not_target']}")

    if not found_any:
        sys.exit(f"No splits found in {args.yolo}")


if __name__ == "__main__":
    main()

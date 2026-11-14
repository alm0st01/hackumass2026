"""Cut NOMAD aerial frames into target / not_target crops for train.py.

NOMAD frames are 5472x3078 with one small person per frame, so the whole frame can't be fed
to a 224x224 classifier. For each frame this script saves:
  - one crop that contains the person          -> target/
  - --neg-per-frame crops that contain nobody  -> not_target/
and from each true-negative (TN) scene, --neg-per-tn crops -> not_target/.

The crop size depends on the filming distance so the person ends up roughly the same size
in every crop (see CROP_SIZE). Crops are saved at --out-size pixels.

Images are read from <nomad>/frames/*.jpg (written by download_nomad.py) and straight from
any NOMAD zip files in <nomad> (for example TN.zip); nothing needs extracting.

Splits are by actor so near-identical frames of one person never end up in both train and
test. By default actor numbers ending in 7 go to valid and ending in 9 to test; choose
specific actors with --valid-actors / --test-actors.

    python prepare_nomad.py --nomad ../NOMAD/data --out ../NOMAD/classification
"""
import argparse
import glob
import io
import json
import os
import random
import re
import sys
import zipfile
from multiprocessing import Pool

from PIL import Image

# Crop side in original pixels per distance. Median person height is 193 px at 10 m and
# 71 / 43 / 31 / 25 px at 30 / 50 / 70 / 90 m, so these keep the person around 20% of the crop.
CROP_SIZE = {"a10": 1026, "a30": 360, "a50": 216, "a70": 156, "a90": 128}
NAME_RE = re.compile(r"Actor(\d{3})_(a\d{2})")


def split_for_actor(actor, args):
    if args.valid_actors or args.test_actors:
        if actor in args.valid_actors:
            return "valid"
        if actor in args.test_actors:
            return "test"
        return "train"
    if actor % 10 == 7:
        return "valid"
    if actor % 10 == 9:
        return "test"
    return "train"


def overlaps(crop, box, margin):
    x, y, s = crop
    bx, by, bw, bh = box
    return not (bx + bw + margin <= x or bx - margin >= x + s or by + bh + margin <= y or by - margin >= y + s)


def random_negative(rng, width, height, size, boxes, margin=20, tries=50):
    for _ in range(tries):
        x = rng.randint(0, width - size)
        y = rng.randint(0, height - size)
        if not any(overlaps((x, y, size), b, margin) for b in boxes):
            return x, y
    return None


def positive_crop(rng, width, height, size, box):
    """A square crop that fully contains the box, with the box at a random position inside it."""
    bx, by, bw, bh = box
    if bw > size or bh > size:  # person bigger than the crop: grow the crop
        size = int(max(bw, bh) * 1.25)
    x_min, x_max = max(0, int(bx + bw) - size), min(width - size, int(bx))
    y_min, y_max = max(0, int(by + bh) - size), min(height - size, int(by))
    if x_min > x_max or y_min > y_max:
        return None
    return rng.randint(x_min, x_max), rng.randint(y_min, y_max), size


def save_crop(image, x, y, size, out_size, path):
    image.crop((x, y, x + size, y + size)).resize((out_size, out_size), Image.BICUBIC).save(path, quality=92)


FRAMES = {}
ARGS = None


def init_worker(frames, args):
    global FRAMES, ARGS
    FRAMES, ARGS = frames, args


def wanted(name, frames, args):
    """Return True if this zip member should be processed."""
    if not name.lower().endswith(".jpg"):
        return False
    m = NAME_RE.search(name)
    if not m or m.group(2) not in args.distances:
        return False
    if "_TN" in name:
        return True
    if name not in frames:
        return False
    return args.frame_step <= 1 or int(re.search(r"_f(\d+)", name).group(1)) % args.frame_step == 0


def process_chunk(job):
    zip_path, members = job
    frames, args, out = FRAMES, ARGS, ARGS.out
    counts = {"target": 0, "not_target": 0}
    zf = zipfile.ZipFile(zip_path) if zip_path else None
    try:
        for member in members:
            name = os.path.basename(member)
            rng = random.Random(f"{args.seed}:{name}")  # same crops every run
            m = NAME_RE.search(name)
            actor, dist = int(m.group(1)), m.group(2)
            is_tn = "_TN" in name
            if not is_tn:
                record = frames[name]
                boxes = [a["bbox"] for a in record["annotations"]]
                visible = [a["bbox"] for a in record["annotations"] if int(a["visibility"]) >= args.min_visibility]
                if not visible:
                    continue  # person too hidden to count as a target, but present, so not a negative either

            try:
                data = zf.read(member) if zf else open(member, "rb").read()
                image = Image.open(io.BytesIO(data)).convert("RGB")
            except Exception as error:
                print(f"Skipping unreadable {name}: {error}", flush=True)
                continue
            width, height = image.size
            size = CROP_SIZE[dist]
            split = split_for_actor(actor, args)
            stem = os.path.splitext(name)[0]

            if is_tn:
                for i in range(args.neg_per_tn):
                    pos = random_negative(rng, width, height, size, [])
                    save_crop(image, *pos, size, args.out_size, os.path.join(out, split, "not_target", f"nomad_{stem}_{i}.jpg"))
                    counts["not_target"] += 1
                continue

            for i in range(args.pos_per_frame):  # same person, different position inside the crop
                crop = positive_crop(rng, width, height, size, rng.choice(visible))
                if crop:
                    save_crop(image, crop[0], crop[1], crop[2], args.out_size, os.path.join(out, split, "target", f"nomad_{stem}_{i}.jpg"))
                    counts["target"] += 1
            for i in range(args.neg_per_frame):
                pos = random_negative(rng, width, height, size, boxes)
                if pos:
                    save_crop(image, *pos, size, args.out_size, os.path.join(out, split, "not_target", f"nomad_{stem}_neg{i}.jpg"))
                    counts["not_target"] += 1
    finally:
        if zf:
            zf.close()
    return counts


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--nomad", required=True, help="folder with annotations/annotations.json and the downloaded zips")
    p.add_argument("--out", required=True, help="output folder")
    p.add_argument("--distances", nargs="+", default=["a10", "a30", "a50"], choices=sorted(CROP_SIZE),
                   help="filming distances to use (default: 10, 30, 50 m)")
    p.add_argument("--min-visibility", type=int, default=30, help="skip frames where the person is less than this %% visible")
    p.add_argument("--frame-step", type=int, default=1, help="use every Nth annotated frame (frames are close to duplicates)")
    p.add_argument("--pos-per-frame", type=int, default=1, help="crops containing the person per annotated frame")
    p.add_argument("--neg-per-frame", type=int, default=1, help="person-free crops per annotated frame")
    p.add_argument("--neg-per-tn", type=int, default=30, help="crops per true-negative scene")
    p.add_argument("--out-size", type=int, default=320, help="saved crop size in pixels")
    p.add_argument("--workers", type=int, default=os.cpu_count())
    p.add_argument("--valid-actors", type=int, nargs="*", default=[], help="actor numbers for validation")
    p.add_argument("--test-actors", type=int, nargs="*", default=[], help="actor numbers for test")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    ann_path = os.path.join(args.nomad, "annotations", "annotations.json")
    if not os.path.exists(ann_path):
        sys.exit(f"Missing {ann_path}. See adi/README.md for the download steps.")
    with open(ann_path) as f:
        frames = {r["file_name"]: r for r in json.load(f)}

    zips = sorted(glob.glob(os.path.join(args.nomad, "*.zip")))
    loose = sorted(glob.glob(os.path.join(args.nomad, "frames", "*.jpg")))
    if not zips and not loose:
        sys.exit(f"No images in {args.nomad}/frames or zip files in {args.nomad}")
    for split in ("train", "valid", "test"):
        for cls in ("target", "not_target"):
            os.makedirs(os.path.join(args.out, split, cls), exist_ok=True)

    jobs = []
    members = [path for path in loose if wanted(os.path.basename(path), frames, args)]
    print(f"frames/: {len(members)} images to process")
    jobs += [(None, members[i:i + 50]) for i in range(0, len(members), 50)]
    for z in zips:
        with zipfile.ZipFile(z) as zf:
            members = [n for n in zf.namelist() if wanted(os.path.basename(n), frames, args)]
        print(f"{os.path.basename(z)}: {len(members)} images to process")
        jobs += [(z, members[i:i + 50]) for i in range(0, len(members), 50)]
    done = 0
    with Pool(args.workers, initializer=init_worker, initargs=(frames, args)) as pool:
        for _ in pool.imap_unordered(process_chunk, jobs):
            done += 1
            if done % 10 == 0 or done == len(jobs):
                print(f"  {done}/{len(jobs)} chunks", flush=True)
    for split in ("train", "valid", "test"):
        n = {c: len(os.listdir(os.path.join(args.out, split, c))) for c in ("target", "not_target")}
        print(f"{split}: target={n['target']}, not_target={n['not_target']}")


if __name__ == "__main__":
    main()

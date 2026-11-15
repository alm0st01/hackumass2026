"""Download a sample of NOMAD frames from its public Google Drive folder.

The full image set is about 290 GB in 10 zip files, and Drive often blocks those zips with
"quota exceeded". Single frames still download, so this script lists the per-actor image
folders and fetches --per-folder evenly spaced annotated frames from each actor and distance.

It also downloads annotations.json. The true-negative zip (TN.zip, 3.2 GB, scenes with no
person) is downloaded too unless --skip-tn is given.

    python download_nomad.py --out ../NOMAD/data

Re-running skips files that are already there.
"""
import argparse
import html
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

ROOT_FOLDER = "1zRiOzedR-PzO1bps5I1vb6jtVoQHFWzg"  # from https://github.com/ArtRuss/NOMAD
ENTRY_RE = re.compile(r'href="(https://drive\.google\.com/[^"]+)"[^>]*>.*?<div class="flip-entry-title">([^<]+)</div>', re.S)

session = requests.Session()


def list_folder(folder_id):
    """Return {name: id} for a public Drive folder."""
    for attempt in range(5):
        r = session.get(f"https://drive.google.com/embeddedfolderview?id={folder_id}", timeout=60)
        if r.ok:
            break
        time.sleep(2 ** attempt)
    r.raise_for_status()
    entries = {}
    for url, name in ENTRY_RE.findall(r.text):
        m = re.search(r"/folders/([\w-]+)", url) or re.search(r"/d/([\w-]+)", url)
        entries[html.unescape(name)] = m.group(1)
    return entries


def download(file_id, path, big=False):
    if os.path.exists(path):
        return "exists"
    tmp = path + ".part"
    url = f"https://drive.usercontent.google.com/download?id={file_id}&export=download"
    for attempt in range(5):
        try:
            params = {}
            if big:  # large files go through a confirm form first
                page = html.unescape(session.get(url, timeout=60).text)
                form = re.search(r'<form[^>]+action="([^"]+)"(.*?)</form>', page, re.S)
                if not form:
                    raise RuntimeError(re.sub(r"<[^>]+>", " ", page)[:200])
                url_used, params = form.group(1), dict(re.findall(r'name="([^"]+)"\s+value="([^"]*)"', form.group(2)))
            else:
                url_used, params = url, {"confirm": "t"}
            with session.get(url_used, params=params, stream=True, timeout=120) as r:
                r.raise_for_status()
                if "text/html" in r.headers.get("Content-Type", ""):
                    text = re.sub(r"<[^>]+>", " ", r.text)
                    raise RuntimeError("Drive quota exceeded" if "Quota exceeded" in text else text[:200])
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
            os.replace(tmp, path)
            return "ok"
        except Exception as error:  # network hiccup or Drive throttling: back off and retry
            last = error
            time.sleep(3 * 2 ** attempt)
    if os.path.exists(tmp):
        os.remove(tmp)
    return f"failed: {last}"


def evenly_spaced(items, n):
    if len(items) <= n:
        return items
    step = len(items) / n
    return [items[int(i * step)] for i in range(n)]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", required=True)
    p.add_argument("--distances", nargs="+", default=["a10", "a30", "a50"], help="a10 a30 a50 a70 a90 (metres)")
    p.add_argument("--per-folder", type=int, default=12, help="frames per actor and distance (about 8 MB each)")
    p.add_argument("--actors", type=int, default=100, help="use the first N actors")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--skip-tn", action="store_true", help="don't download TN.zip")
    args = p.parse_args()

    frames_dir = os.path.join(args.out, "frames")
    ann_dir = os.path.join(args.out, "annotations")
    os.makedirs(frames_dir, exist_ok=True)
    os.makedirs(ann_dir, exist_ok=True)

    root = list_folder(ROOT_FOLDER)
    annotations = list_folder(root["annotations"])
    for name in ("annotations.json", "metadata.json"):
        print(name, download(annotations[name], os.path.join(ann_dir, name)))
    with open(os.path.join(ann_dir, "annotations.json")) as f:
        annotated = {r["file_name"] for r in json.load(f) if r["annotations"]}

    if not args.skip_tn:
        zips = list_folder(list_folder(root["zip_files"])["images"])
        print("TN.zip (3.2 GB) ...", flush=True)
        print("TN.zip", download(zips["TN.zip"], os.path.join(args.out, "TN.zip"), big=True), flush=True)

    actors = sorted(n for n in list_folder(root["images"]) if n.startswith("Actor"))[: args.actors]
    images = list_folder(root["images"])
    jobs = []
    for actor in actors:
        sub = list_folder(images[actor])
        for dist in args.distances:
            folder = f"{actor}_{dist}"
            if folder not in sub:
                continue
            files = list_folder(sub[folder])
            names = sorted(n for n in files if n in annotated)
            for name in evenly_spaced(names, args.per_folder):
                jobs.append((files[name], os.path.join(frames_dir, name)))
        print(f"listed {actor}: {len(jobs)} frames so far", flush=True)

    print(f"Downloading {len(jobs)} frames (about {len(jobs) * 8 / 1000:.0f} GB) ...", flush=True)
    failed = 0
    with ThreadPoolExecutor(args.workers) as pool:
        futures = [pool.submit(download, fid, path) for fid, path in jobs]
        for i, fut in enumerate(as_completed(futures), 1):
            if fut.result().startswith("failed"):
                failed += 1
            if i % 100 == 0 or i == len(jobs):
                print(f"  {i}/{len(jobs)} done, {failed} failed", flush=True)
    if failed:
        print(f"{failed} frames failed (Drive throttling?). Run the script again to retry them.")
        sys.exit(1)


if __name__ == "__main__":
    main()

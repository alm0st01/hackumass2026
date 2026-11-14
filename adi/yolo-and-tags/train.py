import os
import random
import shutil
import zipfile

import yaml
from ultralytics import YOLO

# ---- settings ----
FREEZE = 10          # layers to freeze (10 = backbone; 22 = train only the final head)
EPOCHS = 30
IMGSZ = 640
AUTO_CONF = 0.70     # person frames are auto-labeled only when the model is this sure
# ------------------

IMG_EXT = (".jpg", ".jpeg", ".png")

# unzip raw.zip if the raw/ folder isn't there yet
if not os.path.isdir("raw") and os.path.exists("raw.zip"):
    with zipfile.ZipFile("raw.zip") as z:
        z.extractall(".")

base = YOLO("yolov8n.pt")

# a) auto-label the person images using the model's own confident detections
base.predict(source="raw/person", classes=[0], conf=AUTO_CONF, save_txt=True,
             save=False, imgsz=IMGSZ, project="auto", name="lbl", exist_ok=True)

# b) build the dataset folders
shutil.rmtree("ds", ignore_errors=True)
for s in ("train", "val"):
    os.makedirs(f"ds/images/{s}")
    os.makedirs(f"ds/labels/{s}")

items = []
for f in os.listdir("raw/person"):
    if not f.lower().endswith(IMG_EXT):
        continue
    lbl = f"auto/lbl/labels/{os.path.splitext(f)[0]}.txt"
    if os.path.exists(lbl):               # skip frames with no confident label
        items.append((f"raw/person/{f}", lbl))
for f in os.listdir("raw/jacket"):
    if f.lower().endswith(IMG_EXT):
        items.append((f"raw/jacket/{f}", None))   # negative: empty label file

random.seed(0)
random.shuffle(items)   
cut = int(len(items) * 0.8)
for i, (img, lbl) in enumerate(items):
    s = "train" if i < cut else "val"
    name = f"{i:05d}"
    shutil.copy(img, f"ds/images/{s}/{name}.jpg")
    out = f"ds/labels/{s}/{name}.txt"
    if lbl:
        shutil.copy(lbl, out)
    else:
        open(out, "w").close()

print(f"{len(items)} images total, {cut} train / {len(items) - cut} val")

# c) keep all 80 original class names so the pretrained head is reused
with open("ds/data.yaml", "w") as f:
    yaml.dump({"path": os.path.abspath("ds"), "train": "images/train",
               "val": "images/val", "names": dict(base.names)}, f)

# d) train with the backbone frozen
model = YOLO("yolov8n.pt")
model.train(data="ds/data.yaml", epochs=EPOCHS, imgsz=IMGSZ, freeze=FREEZE)

print("Done. Your model is in runs/detect/train/weights/best.pt")
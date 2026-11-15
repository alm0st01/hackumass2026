import cv2
from ultralytics import YOLO

# ---- settings to tune ----
MODEL = "yolov8n.pt"      # try "yolov8s.pt" for fewer false alarms
IMGSZ = 640
HIGH = 0.60               # strong detection: counts double
LOW = 0.35                # weak detection: counts once; below this is ignored
CONFIRM_FRAMES = 10       # streak points needed to confirm
MIN_BOX_FRAC = 0.0        # ignore boxes smaller than this fraction of the frame (try 0.02)
# --------------------------

model = YOLO(MODEL)
cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)  # remove CAP_DSHOW on the Pi

streak = 0

while True:
    ok, frame = cap.read()
    if not ok:
        print("Couldn't read from camera")
        break

    results = model(frame, imgsz=IMGSZ, conf=0.25, verbose=False)[0]
    frame_area = frame.shape[0] * frame.shape[1]

    # best "person" confidence in this frame (ignoring tiny boxes if enabled)
    best_conf = 0.0
    for b in results.boxes:
        if model.names[int(b.cls)] != "person":
            continue
        x1, y1, x2, y2 = b.xyxy[0].tolist()
        if (x2 - x1) * (y2 - y1) < MIN_BOX_FRAC * frame_area:
            continue
        best_conf = max(best_conf, float(b.conf))

    # two-tier confirmation (this is the part that replaces the old streak lines)
    if best_conf >= HIGH:
        streak += 2
    elif best_conf >= LOW:
        streak += 1
    else:
        streak = max(0, streak - 1)

    if best_conf > 0:
        print(f"person {best_conf:.2f}  streak {streak}")

    if streak >= CONFIRM_FRAMES:
        print("TARGET CONFIRMED")
        # later: stop the robot / send a signal here
        break

    cv2.imshow("view", results.plot())
    if cv2.waitKey(1) == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
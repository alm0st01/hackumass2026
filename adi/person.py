import cv2
from ultralytics import YOLO

TARGET = "person"        # YOLO class name (or "person_down" if you train your own model)
CONF_THRESHOLD = 0.6
CONFIRM_FRAMES = 5

model = YOLO("yolov8n.pt")                # or "best.pt" once you've trained one
cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)  # remove CAP_DSHOW on the Pi

streak = 0
while True:
    ok, frame = cap.read()
    if not ok:
        break

    results = model(frame, imgsz=320, verbose=False)[0]
    seen = any(
        model.names[int(b.cls)] == TARGET and float(b.conf) > CONF_THRESHOLD
        for b in results.boxes
    )
    streak = streak + 1 if seen else max(0, streak - 1)

    if streak >= CONFIRM_FRAMES:
        print("TARGET CONFIRMED")
        break

    cv2.imshow("view", results.plot())
    if cv2.waitKey(1) == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
"""Camera + detector running in a background thread, so slow detection never blocks the radio
or the motor keepalive in the main loop.

    vision = VisionThread(PersonDetector(), source=0)
    vision.start()
    result = vision.latest   # None, or a Detection(frame, confidence, box) for the newest frame

A detector is any callable: frame (BGR numpy array) -> (confidence 0..1, [x, y, w, h]) or None.
"""
import threading
import time
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Detection:
    frame: int                     # frame number, counts up; use it to tell new results from old
    confidence: float              # 0..1, or 0 if nothing was found
    box: Optional[List[int]]       # [x, y, w, h] in pixels, or None


class PersonDetector:
    """YOLOv8 nano, person class only. Same model and settings as vision/yolo-and-tags/person.py."""

    def __init__(self, weights="yolov8n.pt", min_confidence=0.6, img_size=320):
        from ultralytics import YOLO  # slow import, so only when used

        self.model = YOLO(weights)  # downloads yolov8n.pt (6 MB) the first time
        self.min_confidence = min_confidence
        self.img_size = img_size
        self.person_classes = [i for i, name in self.model.names.items() if name == "person"]

    def __call__(self, frame):
        result = self.model(frame, imgsz=self.img_size, classes=self.person_classes, verbose=False)[0]
        best = None
        for box in result.boxes:
            confidence = float(box.conf)
            if confidence >= self.min_confidence and (best is None or confidence > best[0]):
                x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
                best = (confidence, [x1, y1, x2 - x1, y2 - y1])
        return best


class AprilTagDetector:
    """Finds one AprilTag (36h11 family) by ID. Same settings as vision/yolo-and-tags/april-tags.py."""

    def __init__(self, target_id=0):
        import cv2

        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
        self.detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())
        self.target_id = target_id
        self.cv2 = cv2

    def __call__(self, frame):
        gray = self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2GRAY)
        corners, ids, _ = self.detector.detectMarkers(gray)
        if ids is None:
            return None
        for tag_corners, tag_id in zip(corners, ids.flatten()):
            if tag_id == self.target_id:
                x, y, w, h = self.cv2.boundingRect(tag_corners.astype("float32"))
                return 1.0, [int(x), int(y), int(w), int(h)]
        return None


class VisionThread(threading.Thread):
    def __init__(self, detector, source=0, width=640, height=480):
        super().__init__(daemon=True)
        self.detector = detector
        self.source = source
        self.width = width
        self.height = height
        self.latest: Optional[Detection] = None
        self.fps = 0.0
        self.error: Optional[str] = None
        self._running = True

    def run(self):
        import cv2

        cap = cv2.VideoCapture(self.source)
        if isinstance(self.source, int):
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        if not cap.isOpened():
            self.error = f"could not open camera/video {self.source!r}"
            print(f"[vision] {self.error}")
            return
        frame_number = 0
        started = time.time()
        while self._running:
            ok, frame = cap.read()
            if not ok:
                self.error = "camera stopped sending frames" if isinstance(self.source, int) else "end of video"
                print(f"[vision] {self.error}")
                break
            found = self.detector(frame)
            frame_number += 1
            if found:
                self.latest = Detection(frame_number, found[0], found[1])
            else:
                self.latest = Detection(frame_number, 0.0, None)
            self.fps = frame_number / max(1e-6, time.time() - started)
        cap.release()

    def stop(self):
        self._running = False

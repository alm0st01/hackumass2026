# camera_robot.py - AprilTag detection + robot radio, in one loop.
#
# Laptop test (no Pi, no Heltec):   python camera_robot.py --sim
# On the Pi with the Heltec:        python camera_robot.py --port /dev/ttyUSB0 --no-view
#
# Needs robot.py and common.py in the same folder.
# Needs OpenCV 4.7+:  pip install -U opencv-contrib-python

import argparse
import platform
import time

import cv2

from common import MeshRadio, SimRadio
from robot import Robot

TARGET_ID = 0        # the tag ID the robot is looking for
CONFIRM_FRAMES = 5   # frames in a row needed to confirm

parser = argparse.ArgumentParser()
parser.add_argument("--id", type=int, default=1, help="robot ID")
parser.add_argument("--sim", action="store_true", help="fake radio, for testing on a laptop")
parser.add_argument("--port", default="/dev/ttyUSB0", help="serial port of the Heltec")
parser.add_argument("--camera", type=int, default=0, help="camera index")
parser.add_argument("--no-view", action="store_true", help="no preview window (use on the Pi)")
args = parser.parse_args()

# --- radio / robot ---
radio = SimRadio() if args.sim else MeshRadio(args.port)
robot = Robot(args.id, radio)
robot.state = "EXPLORING"

# --- camera ---
system = platform.system()
if system == "Windows":
    cap = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
elif system == "Linux":
    cap = cv2.VideoCapture(args.camera, cv2.CAP_V4L2)
else:
    cap = cv2.VideoCapture(args.camera)

if not cap.isOpened():
    raise SystemExit(f"Couldn't open camera {args.camera}. Try --camera 1, or on Linux check: ls /dev/video*")

# --- detector ---
dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())

streak = 0
box = None
confirmed_before = False

try:
    while True:
        robot.update()  # every loop: handshake, heartbeats, retries

        ok, frame = cap.read()
        if not ok:
            print("Couldn't read from camera")
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = detector.detectMarkers(gray)

        seen = False
        if ids is not None:
            id_list = ids.flatten().tolist()
            if TARGET_ID in id_list:
                seen = True
                c = corners[id_list.index(TARGET_ID)][0]
                x, y = int(c[:, 0].min()), int(c[:, 1].min())
                box = [x, y, int(c[:, 0].max()) - x, int(c[:, 1].max()) - y]

        streak = streak + 1 if seen else 0

        if streak >= CONFIRM_FRAMES:
            if not confirmed_before:
                print(f"TARGET CONFIRMED: tag {TARGET_ID}")
                confirmed_before = True
            # send_detection rate-limits itself (1 per 3 s) and returns False
            # if the robot isn't connected to the base yet.
            if robot.send_detection(1.0, box):
                print(f"  -> detection sent to base, box={box}")
        elif streak == 0:
            confirmed_before = False

        # --- commands from the base ---
        command = robot.next_command()
        if command == "STOP":
            robot.state = "STOPPED"   # motor code would stop the motors here
        elif command == "HOME":
            robot.state = "RETURNING"
        elif command in ("RESUME", "SCAN"):
            robot.state = "EXPLORING"

        # --- preview ---
        if not args.no_view:
            if ids is not None:
                cv2.aruco.drawDetectedMarkers(frame, corners, ids)
            cv2.putText(frame, f"{robot.state}  connected={robot.connected}  streak={streak}",
                        (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.imshow("view", frame)
            if cv2.waitKey(1) == ord("q"):
                break
        else:
            time.sleep(0.01)

except KeyboardInterrupt:
    pass
finally:
    cap.release()
    cv2.destroyAllWindows()

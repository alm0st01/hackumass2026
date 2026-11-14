import cv2

TARGET_ID = 0            # the tag ID the robot is looking for
CONFIRM_FRAMES = 5       # frames in a row needed to confirm

dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())

cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)  # remove CAP_DSHOW on the Pi

streak = 0

while True:
    ok, frame = cap.read()
    if not ok:
        print("Couldn't read from camera")
        break

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    corners, ids, _ = detector.detectMarkers(gray)

    seen = ids is not None and TARGET_ID in ids.flatten()
    streak = streak + 1 if seen else 0

    if ids is not None:
        cv2.aruco.drawDetectedMarkers(frame, corners, ids)  # boxes + IDs on video

    if streak >= CONFIRM_FRAMES:
        print(f"TARGET CONFIRMED: tag {TARGET_ID}")
        # later: stop the robot / send a signal here
        break

    cv2.imshow("view", frame)
    if cv2.waitKey(1) == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
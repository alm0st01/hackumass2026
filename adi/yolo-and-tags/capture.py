import cv2, os, sys, time

folder = sys.argv[1]            # "raw/person" or "raw/jacket"
os.makedirs(folder, exist_ok=True)
cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)

n = len(os.listdir(folder))
last = 0
while True:
    ok, frame = cap.read()
    if not ok:
        break
    if time.time() - last >= 1:
        cv2.imwrite(f"{folder}/{n:04d}.jpg", frame)
        n += 1
        last = time.time()
    cv2.putText(frame, f"{n} saved - q to stop", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    cv2.imshow("capture", frame)
    if cv2.waitKey(1) == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
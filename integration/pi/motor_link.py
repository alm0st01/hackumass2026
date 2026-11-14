"""Talks to the ESP32 motor controller over USB serial. Protocol: shared/serial_protocol.md

    link = MotorLink("/dev/ttyUSB0")
    link.wait_ready()
    link.drive(180, 180)    # call at least every 300 ms, or the ESP32 stops the motors
    link.status             # latest STATUS from the ESP32, e.g. {"left": 180, "right": 180, "distance": 812, "state": "OK"}
"""
import threading
import time

BAUD = 115200
STATUS_STALE_S = 1.0  # STATUS normally arrives every 100 ms


class MotorLink:
    def __init__(self, port, baud=BAUD):
        import serial  # pyserial

        self.serial = serial.Serial(port, baud, timeout=0.2)
        self.status = None
        self.status_time = 0.0
        self._ready = threading.Event()
        self._pong = threading.Event()
        self._write_lock = threading.Lock()
        self._running = True
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self):
        while self._running:
            try:
                raw = self.serial.readline()
            except Exception as error:  # cable pulled
                print(f"[motors] serial read failed: {error}")
                self._running = False
                break
            if not raw:
                continue
            text = raw.decode("ascii", errors="replace").strip()
            parts = text.split()
            if not parts:
                continue
            if parts[0] == "STATUS" and len(parts) == 5:
                try:
                    self.status = {"left": int(parts[1]), "right": int(parts[2]),
                                   "distance": int(parts[3]), "state": parts[4]}
                    self.status_time = time.time()
                except ValueError:
                    pass
                self._ready.set()  # a STATUS also proves the firmware is running
            elif parts[0] == "READY":
                self._ready.set()
            elif parts[0] == "PONG":
                self._pong.set()
            elif parts[0] == "ERR":
                print(f"[motors] ESP32 says: {text}")

    def wait_ready(self, timeout=5.0):
        """Wait for the ESP32 to boot (opening the port usually resets it). Returns True if it answered."""
        if self._ready.wait(timeout):
            return True
        self._pong.clear()
        self._send("PING")
        return self._pong.wait(1.0)

    def _send(self, text):
        with self._write_lock:
            self.serial.write((text + "\n").encode("ascii"))

    def drive(self, left, right):
        left = max(-255, min(255, int(left)))
        right = max(-255, min(255, int(right)))
        self._send(f"DRIVE {left} {right}")

    def stop(self):
        self._send("STOP")

    def set_obstacle_stop(self, enabled):
        self._send(f"OBSTACLE {1 if enabled else 0}")

    @property
    def connected(self):
        return self._running and time.time() - self.status_time < STATUS_STALE_S

    def close(self):
        try:
            self.stop()
            time.sleep(0.05)
        except Exception:
            pass
        self._running = False
        self._reader.join(timeout=1.0)  # readline() returns within its 0.2 s timeout
        self.serial.close()


class FakeMotorLink:
    """Stands in for the ESP32 when testing without hardware. Prints speed changes."""

    def __init__(self):
        self.status = {"left": 0, "right": 0, "distance": 0, "state": "WAITING"}
        self.status_time = time.time()
        self._last = None

    def wait_ready(self, timeout=5.0):
        return True

    def drive(self, left, right):
        speeds = (int(left), int(right))
        if speeds != self._last:
            print(f"[motors] (fake) drive {speeds[0]} {speeds[1]}")
            self._last = speeds
        self.status = {"left": speeds[0], "right": speeds[1], "distance": 0, "state": "OK"}
        self.status_time = time.time()

    def stop(self):
        self.drive(0, 0)

    def set_obstacle_stop(self, enabled):
        pass

    @property
    def connected(self):
        return True

    def close(self):
        self.stop()

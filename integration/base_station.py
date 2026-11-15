"""Piku's base station (comms/meshtastic-testing/base.py), plus robot positions.

Same commands and options as base.py:
    python integration/base_station.py            (real radio, add --port if needed)
    python integration/base_station.py --sim      (testing on one computer)

Differences:
  - a detection alert also shows where the robot was:
        !!! ALERT: robot 1 sees a PERSON (84% sure) !!!
            at x 12.3 m, y 30.1 m from the start (+-2 m)
  - `status` shows each robot's last reported position
Positions come from the x / y / err fields that integration/pi/located_robot.py adds to
HEARTBEAT and DETECTION messages. Robots that don't send them show "position unknown".
"""
import argparse
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "comms", "meshtastic-testing"))

import base as piku_base  # noqa: E402  (Piku's code)
from base import COMMANDS, Base  # noqa: E402
from common import MeshRadio, SimRadio  # noqa: E402


def describe(position):
    if position is None:
        return "position unknown"
    x, y, err = position
    return f"x {x:.1f} m, y {y:.1f} m from the start (+-{err} m)"


class LocatedBase(Base):
    def __init__(self, radio):
        super().__init__(radio)
        self.positions = {}       # robot id -> (x, y, err)
        self._new_detections = []

    def check_inbox(self):
        messages = super().check_inbox()
        for msg in messages:
            if msg["type"] in ("HEARTBEAT", "DETECTION") and "x" in msg and "y" in msg:
                position = (float(msg["x"]), float(msg["y"]), msg.get("err", "?"))
                self.positions[msg["from"]] = position
                if msg["type"] == "DETECTION":
                    self._new_detections.append(position)
            elif msg["type"] == "DETECTION":
                self._new_detections.append(None)
        return messages

    def update(self):
        super().update()  # prints the ALERT line
        for position in self._new_detections:
            print(f"    at {describe(position)}\n")
        self._new_detections.clear()

    def print_status(self):
        super().print_status()
        for robot_id in self.robots:
            print(f"    robot {robot_id} last at {describe(self.positions.get(robot_id))}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sim", action="store_true", help="fake radio for testing on one laptop")
    parser.add_argument("--port", default=None, help="serial port of the Heltec, e.g. /dev/ttyUSB0")
    args = parser.parse_args()

    base = LocatedBase(SimRadio() if args.sim else MeshRadio(args.port))
    threading.Thread(target=piku_base.read_keyboard, daemon=True).start()
    print("base station running. type: status | stop 1 | resume 1 | home 1 | scan 1")
    while True:
        base.update()
        while piku_base.typed_lines:
            words = piku_base.typed_lines.pop(0).split()
            if words == ["status"]:
                base.print_status()
            elif len(words) == 2 and words[0].upper() in COMMANDS and words[1].isdigit():
                base.send_command(int(words[1]), words[0].upper())
            elif words:
                print("?")
        time.sleep(0.05)


if __name__ == "__main__":
    main()

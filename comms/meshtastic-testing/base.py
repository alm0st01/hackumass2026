# base.py - runs on the laptop with the base-station Heltec plugged in.
#
#     python base.py            (real radio)
#     python base.py --sim      (testing on one laptop)
#
# Commands you can type:
#     status          list robots
#     stop 1          send STOP to robot 1  (also: resume, home, scan)

import argparse
import threading
import time

from common import BASE_ID, MeshRadio, Node, SimRadio

COMMANDS = ["STOP", "RESUME", "HOME", "SCAN"]


class Base(Node):
    def __init__(self, radio):
        super().__init__(BASE_ID, radio)
        self.heartbeat_every = 10
        self.robots = {}  # robot id -> dict of its latest info

    def update(self):
        for msg in self.check_inbox():
            robot_id = msg["from"]
            if robot_id not in self.robots:
                self.robots[robot_id] = {"battery": "?", "state": "?", "detections": 0, "online": True}
            robot = self.robots[robot_id]
            robot["last_seen"] = time.time()
            if not robot["online"]:
                robot["online"] = True
                print(f"robot {robot_id} is back ONLINE")

            if msg["type"] == "HELLO":
                print(f"robot {robot_id} joined")
                self.send({"type": "WELCOME", "to": robot_id, "heartbeat_every": self.heartbeat_every})
            elif msg["type"] == "HEARTBEAT":
                robot["battery"] = msg["battery"]
                robot["state"] = msg["state"]
            elif msg["type"] == "DETECTION":
                robot["detections"] += 1
                print(f"\n!!! ALERT: robot {robot_id} sees a PERSON ({msg['conf']}% sure) !!!\n")

        # Offline after 3 missed heartbeats.
        for robot_id, robot in self.robots.items():
            if robot["online"] and time.time() - robot["last_seen"] > 3 * self.heartbeat_every:
                robot["online"] = False
                print(f"robot {robot_id} went OFFLINE")

        self.resend_unacked()

    def send_command(self, robot_id, command):
        self.send({"type": "COMMAND", "to": robot_id, "command": command}, needs_ack=True)

    def got_ack(self, msg):
        print(f"robot {msg['to']} confirmed {msg['command']}")

    def gave_up(self, msg):
        print(f"robot {msg['to']} never confirmed {msg['command']} (out of range?)")

    def print_status(self):
        if not self.robots:
            print("no robots yet")
        for robot_id, r in self.robots.items():
            print(f"robot {robot_id}: {'online' if r['online'] else 'OFFLINE'}, battery {r['battery']}%, "
                  f"{r['state']}, {r['detections']} detections")


# input() waits until you press Enter, which would freeze the radio loop.
# So one small background thread reads the keyboard and puts lines in a list.
typed_lines = []


def read_keyboard():
    while True:
        typed_lines.append(input())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sim", action="store_true", help="fake radio for testing on one laptop")
    parser.add_argument("--port", default=None, help="serial port of the Heltec, e.g. /dev/ttyUSB0")
    args = parser.parse_args()

    base = Base(SimRadio() if args.sim else MeshRadio(args.port))
    threading.Thread(target=read_keyboard, daemon=True).start()
    print("base station running. type: status | stop 1 | resume 1 | home 1 | scan 1")

    while True:
        base.update()

        while typed_lines:
            words = typed_lines.pop(0).split()
            if words == ["status"]:
                base.print_status()
            elif len(words) == 2 and words[0].upper() in COMMANDS and words[1].isdigit():
                base.send_command(int(words[1]), words[0].upper())
            elif words:
                print("?")

        time.sleep(0.05)

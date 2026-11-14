# robot.py - runs on each robot's Raspberry Pi.
#
# How your teammates use it, inside the robot's main loop:
#
#     from robot import Robot
#     from common import MeshRadio
#
#     robot = Robot(1, MeshRadio())
#
#     while True:
#         robot.update()                       # call every loop; it never waits
#
#         # vision code, when YOLO finds a person:
#         robot.send_detection(0.87, [x, y, w, h])
#
#         # motor code:
#         command = robot.next_command()       # "STOP", "RESUME", "HOME", "SCAN" or None
#         if command == "STOP":
#             motors.stop()
#
#         robot.battery = 82                   # anyone can update these;
#         robot.state = "EXPLORING"            # they go out in the next heartbeat
#
# Run this file by itself to get a fake robot for testing:
#     python robot.py --sim --id 1

import argparse
import random
import time

from common import BASE_ID, MeshRadio, Node, SimRadio


class Robot(Node):
    def __init__(self, robot_id, radio):
        super().__init__(robot_id, radio)
        self.connected = False
        self.heartbeat_every = 10  # the base can change this in its WELCOME
        self.last_hello = 0
        self.last_heartbeat = 0
        self.last_detection = 0
        self.started = time.time()
        self.commands = []  # commands from the base, waiting for the motor code

        # status sent in each heartbeat
        self.battery = 100
        self.state = "IDLE"
        self.heading = 0

    def update(self):
        now = time.time()

        for msg in self.check_inbox():
            if msg["type"] == "WELCOME":
                self.connected = True
                self.heartbeat_every = msg["heartbeat_every"]
                print(f"[robot {self.my_id}] connected to base")
            elif msg["type"] == "COMMAND":
                print(f"[robot {self.my_id}] got command {msg['command']}")
                self.commands.append(msg["command"])

        # Handshake: say HELLO every 5 s until the base answers with WELCOME.
        if not self.connected and now - self.last_hello > 5:
            print(f"[robot {self.my_id}] HELLO -> base")
            self.send({"type": "HELLO", "to": BASE_ID})
            self.last_hello = now

        # Once connected, send a heartbeat every few seconds.
        if self.connected and now - self.last_heartbeat > self.heartbeat_every:
            self.send({"type": "HEARTBEAT", "to": BASE_ID, "battery": self.battery,
                       "state": self.state, "heading": self.heading,
                       "uptime": int(now - self.started)})
            self.last_heartbeat = now

        self.resend_unacked()

    def send_detection(self, confidence, box):
        """confidence: 0.0 to 1.0. box: [x, y, w, h] in pixels.
        Returns False if skipped (not connected, or we sent one under 3 s ago, since LoRa is slow)."""
        if not self.connected or time.time() - self.last_detection < 3:
            return False
        self.last_detection = time.time()
        self.send({"type": "DETECTION", "to": BASE_ID, "conf": round(confidence * 100),
                   "box": [int(v) for v in box]}, needs_ack=True)
        return True

    def next_command(self):
        if self.commands:
            return self.commands.pop(0)
        return None

    def got_ack(self, msg):
        print(f"[robot {self.my_id}] base confirmed our {msg['type']}")

    def gave_up(self, msg):
        print(f"[robot {self.my_id}] base never confirmed {msg['type']}, reconnecting")
        self.connected = False


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", type=int, default=1)
    parser.add_argument("--sim", action="store_true", help="fake radio for testing on one laptop")
    parser.add_argument("--port", default=None, help="serial port of the Heltec, e.g. /dev/ttyUSB0")
    args = parser.parse_args()

    radio = SimRadio() if args.sim else MeshRadio(args.port)
    robot = Robot(args.id, radio)
    robot.state = "EXPLORING"
    next_fake_detection = time.time() + 8

    while True:
        robot.update()

        command = robot.next_command()
        if command == "STOP":
            robot.state = "STOPPED"
        elif command == "HOME":
            robot.state = "RETURNING"
        elif command in ("RESUME", "SCAN"):
            robot.state = "EXPLORING"

        # pretend YOLO saw a person now and then
        if robot.state == "EXPLORING" and time.time() > next_fake_detection:
            confidence = random.uniform(0.5, 0.95)
            if robot.send_detection(confidence, [120, 80, 60, 140]):
                print(f"[robot {args.id}] fake person detection sent ({confidence:.0%})")
            next_fake_detection = time.time() + random.uniform(8, 15)

        time.sleep(0.05)

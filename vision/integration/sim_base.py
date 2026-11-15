# sim_base.py - minimal fake base station, for testing the robot on one laptop.
# Only use this if you don't have your team's real base script.
#
# Run it in a SECOND terminal, next to: python integration.py --sim
# Keys: s = send STOP to robot 1, r = RESUME, h = HOME (type the letter + Enter)

import sys
import threading
import time

from common import BASE_ID, Node, SimRadio


class FakeBase(Node):
    def got_ack(self, msg):
        print(f"[base] robot confirmed our {msg['type']}")


base = FakeBase(BASE_ID, SimRadio())
typed = []


def read_keys():
    for line in sys.stdin:
        typed.append(line.strip().lower())


threading.Thread(target=read_keys, daemon=True).start()
print("[base] running. Type s / r / h + Enter to send STOP / RESUME / HOME to robot 1. Ctrl+C to quit.")

commands = {"s": "STOP", "r": "RESUME", "h": "HOME"}

while True:
    for msg in base.check_inbox():
        if msg["type"] == "HELLO":
            print(f"[base] HELLO from robot {msg['from']}, sending WELCOME")
            base.send({"type": "WELCOME", "to": msg["from"], "heartbeat_every": 10})
        elif msg["type"] == "HEARTBEAT":
            print(f"[base] heartbeat from robot {msg['from']}: battery={msg['battery']} state={msg['state']}")
        elif msg["type"] == "DETECTION":
            print(f"[base] DETECTION from robot {msg['from']}: conf={msg['conf']}% box={msg['box']}")

    while typed:
        key = typed.pop(0)
        if key in commands:
            print(f"[base] sending {commands[key]} to robot 1")
            base.send({"type": "COMMAND", "to": 1, "command": commands[key]}, needs_ack=True)

    base.resend_unacked()
    time.sleep(0.05)
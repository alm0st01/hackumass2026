"""Piku's Robot, plus the robot's estimated position in its messages.

Adds three fields to every HEARTBEAT and DETECTION:
    "x", "y"  metres from the start point (x = east, y = north), 1 decimal
    "err"     1-sigma position uncertainty in metres, 1 decimal

A DETECTION carries the position at the moment the target was confirmed, and its resends keep
that same position. Piku's base.py ignores fields it doesn't know, so it keeps working;
integration/base_station.py shows them.

Piku's files are unchanged. If Piku adds these fields to robot.py himself, this file can go.
"""
from robot import Robot


class LocatedRobot(Robot):
    LOCATED_TYPES = ("HEARTBEAT", "DETECTION")

    def __init__(self, robot_id, radio):
        super().__init__(robot_id, radio)
        self.x = 0.0
        self.y = 0.0
        self.position_err = 0.0

    def send(self, msg, needs_ack=False):
        # Every message goes through Node.send, so this is the one place to add the fields.
        if msg.get("type") in self.LOCATED_TYPES:
            msg["x"] = round(self.x, 1)
            msg["y"] = round(self.y, 1)
            msg["err"] = round(self.position_err, 1)
        super().send(msg, needs_ack)

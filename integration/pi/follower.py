"""Drives through a list of waypoints, using the position estimate.

Turns in place when the next waypoint is well off to one side, otherwise drives forward and
steers. Gives up on a waypoint it keeps hitting obstacles near, so one blocked spot can't stall
the whole search.
"""
import math

from estimator import wrap

CRUISE_SPEED = 180        # match shared/config.h
TURN_SPEED = 150


class WaypointFollower:
    def __init__(self, waypoints, arrive_radius=1.5, turn_in_place_deg=30.0, steer_gain=2.0,
                 cruise=CRUISE_SPEED, turn=TURN_SPEED, max_obstacles_per_waypoint=4):
        self.waypoints = list(waypoints)
        self.index = 0
        self.arrive_radius = arrive_radius
        self.turn_in_place = math.radians(turn_in_place_deg)
        self.steer_gain = steer_gain              # PWM difference per degree of heading error
        self.cruise = cruise
        self.turn = turn
        self.max_obstacles = max_obstacles_per_waypoint
        self.obstacles_here = 0
        self.skipped = []

    @property
    def done(self):
        return self.index >= len(self.waypoints)

    @property
    def current(self):
        return None if self.done else self.waypoints[self.index]

    def _advance(self):
        self.index += 1
        self.obstacles_here = 0

    def obstacle(self):
        """Call when an obstacle forced a detour. Returns True if this waypoint was given up on."""
        self.obstacles_here += 1
        if self.obstacles_here >= self.max_obstacles and not self.done:
            self.skipped.append(self.index)
            self._advance()
            return True
        return False

    def speeds(self, x, y, heading_deg):
        """Motor speeds (left, right) to head for the current waypoint. (0, 0) when done."""
        while not self.done:
            tx, ty = self.waypoints[self.index]
            if math.hypot(tx - x, ty - y) > self.arrive_radius:
                break
            self._advance()
        if self.done:
            return 0, 0
        tx, ty = self.waypoints[self.index]
        error = wrap(math.atan2(tx - x, ty - y) - math.radians(heading_deg))  # > 0: target is to the right
        if abs(error) > self.turn_in_place:
            return (self.turn, -self.turn) if error > 0 else (-self.turn, self.turn)
        correction = max(-self.cruise / 2, min(self.cruise / 2, self.steer_gain * math.degrees(error)))
        return int(self.cruise + correction), int(self.cruise - correction)

    def distance_to_current(self, x, y):
        if self.done:
            return 0.0
        tx, ty = self.waypoints[self.index]
        return math.hypot(tx - x, ty - y)

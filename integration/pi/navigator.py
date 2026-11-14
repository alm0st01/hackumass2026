"""Position estimate (IMU + timed driving) + waypoint following + obstacle detours, in one step() per loop.

main.py and sim_search.py both use this class, so the simulation tests the same code that runs
on the robot.
"""
import math
import random

from estimator import PoseEstimator
from follower import CRUISE_SPEED, TURN_SPEED, WaypointFollower

DETOUR_TURN_S = (0.6, 1.2)   # turn away from an obstacle for this long (random) ...
DETOUR_FORWARD_S = 2.0       # ... then drive straight this long before heading for the waypoint again


class Navigator:
    def __init__(self, speed_mps, turn_rate_dps, imu=None, estimator=None, arrive_radius=1.5, rng=None):
        """speed_mps:     measured forward speed at CRUISE_SPEED (see README: calibration)
        turn_rate_dps: measured turn rate when spinning in place at TURN_SPEED
        imu:           object with heading() -> degrees or None"""
        self.speed_mps = speed_mps
        self.turn_rate = math.radians(turn_rate_dps)
        self.imu = imu
        self.estimator = estimator or PoseEstimator()
        self.arrive_radius = arrive_radius
        self.follower = None
        self.rng = rng or random.Random()
        self.last_time = None
        self.detour = None           # list of (end_time, left, right) steps
        self.log = []                # messages for the caller to print

    # ------------------------------------------------------------------ plans
    def follow(self, waypoints):
        self.follower = WaypointFollower(waypoints, arrive_radius=self.arrive_radius)
        self.detour = None

    def stop(self):
        self.detour = None

    @property
    def done(self):
        return self.follower is None or self.follower.done

    # ------------------------------------------------------------------ estimate
    def _estimate(self, now, applied_left, applied_right):
        dt = 0.0 if self.last_time is None else now - self.last_time
        self.last_time = now
        speed = self.speed_mps * (applied_left + applied_right) / 2 / CRUISE_SPEED
        turn = self.turn_rate * (applied_left - applied_right) / 2 / TURN_SPEED  # left faster = clockwise
        self.estimator.predict(speed, turn, dt)

        if self.imu is not None:
            heading = self.imu.heading()
            if heading is not None:
                self.estimator.update_heading(heading, getattr(self.imu, "heading_sigma", 3.0))

    # ------------------------------------------------------------------ driving
    def _start_detour(self, now):
        direction = self.rng.choice((-1, 1))
        turn_end = now + self.rng.uniform(*DETOUR_TURN_S)
        self.detour = [(turn_end, direction * TURN_SPEED, -direction * TURN_SPEED),
                       (turn_end + DETOUR_FORWARD_S, CRUISE_SPEED, CRUISE_SPEED)]
        if self.follower is not None and self.follower.obstacle():
            self.log.append(f"waypoint {self.follower.index} kept being blocked; skipping it")

    def step(self, now, applied_left, applied_right, motor_state="OK"):
        """Update the estimate, then return the motor speeds (left, right) to command."""
        self._estimate(now, applied_left, applied_right)
        if self.done:
            return 0, 0
        if motor_state == "OBSTACLE":
            # Blocked going forward: start a detour (or restart it if the detour's own
            # forward leg is blocked too).
            if self.detour is None or now >= self.detour[0][0]:
                self._start_detour(now)
        if self.detour is not None:
            while self.detour and now >= self.detour[0][0]:
                self.detour.pop(0)
            if self.detour:
                return self.detour[0][1], self.detour[0][2]
            self.detour = None
        e = self.estimator
        return self.follower.speeds(e.x, e.y, e.heading_deg)

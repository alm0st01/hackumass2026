"""A simulated robot in a field, for testing without hardware.

Stands in for the ESP32 (same methods as MotorLink, including the obstacle stop) and the IMU,
with deliberately imperfect behaviour:
  - the real speed differs from the calibrated one (default 10% slower), with random wheel slip
  - turns overshoot or undershoot at random
  - imu="compass" (BNO055-like): fixed bias plus noise (magnetometers near motors are never perfect)
    imu="gyro" (MPU6050-like): starts right but drifts, like an integrated gyro
  - optional round obstacles that trigger the ESP32-style obstacle stop
"""
import math
import random

from follower import CRUISE_SPEED, TURN_SPEED

OBSTACLE_SENSOR_RANGE_M = 0.6


class _SimImu:
    def __init__(self, world):
        self.world = world

    @property
    def heading_sigma(self):
        w = self.world
        return 3.0 + (0.05 * w.time if w.imu_kind == "gyro" else 0.0)

    def heading(self):
        w = self.world
        error = w.gyro_drift if w.imu_kind == "gyro" else w.heading_bias
        return (math.degrees(w.h) + error + w.rng.gauss(0, w.heading_noise)) % 360.0


class SimWorld:
    def __init__(self, speed_mps=0.5, turn_rate_dps=90.0, true_speed_scale=0.90, slip=0.08,
                 turn_error=0.10, imu="compass", heading_bias_deg=3.0, heading_noise_deg=1.5,
                 gyro_drift_dps=0.05, obstacles=(), start_heading_deg=0.0, seed=0):
        self.rng = random.Random(seed)
        self.speed_mps = speed_mps
        self.turn_rate = math.radians(turn_rate_dps)
        self.true_speed_scale = true_speed_scale
        self.slip = slip
        self.turn_error = turn_error
        self.imu_kind = imu
        self.heading_bias = heading_bias_deg
        self.heading_noise = heading_noise_deg
        self.gyro_drift_rate = gyro_drift_dps * self.rng.choice((-1, 1))
        self.gyro_drift = 0.0
        self.obstacles = list(obstacles)  # (x, y, radius)
        self.x = self.y = 0.0
        self.h = math.radians(start_heading_deg)
        self.time = 0.0
        self.commanded = (0, 0)
        self.applied = (0, 0)
        self.state = "WAITING"
        self.obstacle_stop = True
        self.imu = _SimImu(self)

    # ---------------------------------------------------------------- MotorLink interface
    def wait_ready(self, timeout=5.0):
        return True

    def drive(self, left, right):
        self.commanded = (int(left), int(right))

    def stop(self):
        self.drive(0, 0)

    def set_obstacle_stop(self, enabled):
        self.obstacle_stop = enabled

    @property
    def status(self):
        return {"left": self.applied[0], "right": self.applied[1],
                "distance": 3000 if self._blocked_ahead() else 300, "state": self.state}

    @property
    def connected(self):
        return True

    def close(self):
        self.stop()

    # ---------------------------------------------------------------- physics
    def _blocked_ahead(self):
        ax = self.x + OBSTACLE_SENSOR_RANGE_M * math.sin(self.h)
        ay = self.y + OBSTACLE_SENSOR_RANGE_M * math.cos(self.h)
        return any(math.hypot(ax - ox, ay - oy) < r for ox, oy, r in self.obstacles)

    def advance(self, dt):
        left, right = self.commanded
        forward = left + right > 0
        if self.obstacle_stop and forward and self._blocked_ahead():
            self.applied, self.state = (0, 0), "OBSTACLE"
        else:
            self.applied, self.state = (left, right), "OK"
        left, right = self.applied
        speed = self.speed_mps * self.true_speed_scale * (left + right) / 2 / CRUISE_SPEED
        speed *= 1 + self.rng.gauss(0, self.slip)
        turn = self.turn_rate * (left - right) / 2 / TURN_SPEED * (1 + self.rng.gauss(0, self.turn_error))
        self.h = (self.h + turn * dt) % (2 * math.pi)
        self.x += speed * dt * math.sin(self.h)
        self.y += speed * dt * math.cos(self.h)
        self.time += dt
        # Gyro drift: a steady rate plus a random walk, as a cheap MEMS gyro does after bias calibration.
        self.gyro_drift += self.gyro_drift_rate * dt + self.rng.gauss(0, 0.02 * math.sqrt(dt))

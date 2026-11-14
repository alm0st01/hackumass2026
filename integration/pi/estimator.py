"""Position estimate: a Kalman filter combining timed driving with IMU heading. No GPS.

There are no wheel encoders, so distance comes from "how fast the robot goes at this motor
speed" x time (dead reckoning). The filter:

  - predicts the next position and heading from the motor speeds the ESP32 actually applied
  - corrects the heading from the IMU every loop, weighting the IMU against the motor-based
    guess by how noisy each is
  - tracks how uncertain the position is (`position_sigma`)

Nothing measures position directly, so position errors are never corrected: `position_sigma`
grows with distance driven. Its size is mostly set by how well --speed-mps is calibrated.

State: x, y (metres, x = east, y = north, (0, 0) = start), heading (radians, compass:
0 = north, clockwise), speed scale (1.0 = as calibrated).
"""
import math

import numpy as np


def wrap(angle):
    """Wrap radians to (-pi, pi]."""
    return (angle + math.pi) % (2 * math.pi) - math.pi


class PoseEstimator:
    def __init__(self, x=0.0, y=0.0, heading_deg=0.0, start_sigma_m=0.3, heading_known=False,
                 speed_error=0.10, slip=0.03, heading_rate_noise_dps=3.0, turn_rate_noise_dps=25.0):
        """speed_error: how far off the calibrated --speed-mps may be, as a fraction (0.10 = 10%).
        It's one unknown number for the whole run (grass, slope, battery), not random per step,
        so it's kept as a 4th state, a speed scale. Nothing measures it, so it stays at 1.0, but the
        filter then knows the resulting error grows with distance from the start and partly
        cancels on out-and-back legs, which is what really happens."""
        self.state = np.array([x, y, math.radians(heading_deg), 1.0])
        heading_sigma = math.radians(5.0) if heading_known else math.pi
        self.P = np.diag([start_sigma_m ** 2, start_sigma_m ** 2, heading_sigma ** 2, speed_error ** 2])
        self.heading_initialized = heading_known
        self.slip = slip                                    # random wheel slip, fraction of each step
        self.heading_rate_noise = math.radians(heading_rate_noise_dps)
        self.turn_rate_noise = math.radians(turn_rate_noise_dps)

    def predict(self, speed_mps, turn_rate_rad_s, dt):
        """speed_mps, turn_rate: what the applied motor speeds should produce (as calibrated)."""
        if dt <= 0:
            return
        x, y, h, scale = self.state
        v = scale * speed_mps
        self.state = np.array([x + v * dt * math.sin(h), y + v * dt * math.cos(h),
                               wrap(h + turn_rate_rad_s * dt), scale])
        F = np.eye(4)
        F[0, 2] = v * dt * math.cos(h)
        F[0, 3] = speed_mps * dt * math.sin(h)
        F[1, 2] = -v * dt * math.sin(h)
        F[1, 3] = speed_mps * dt * math.cos(h)
        step_noise = (self.slip * abs(v) * dt) ** 2
        rate_noise = self.turn_rate_noise if abs(turn_rate_rad_s) > 1e-3 else self.heading_rate_noise
        Q = np.diag([step_noise, step_noise, (rate_noise * dt) ** 2, 0.0])
        self.P = F @ self.P @ F.T + Q

    def update_heading(self, heading_deg, sigma_deg=3.0):
        measured = math.radians(heading_deg)
        if not self.heading_initialized:
            self.state[2] = wrap(measured)
            self.P[2, 2] = math.radians(sigma_deg) ** 2
            self.heading_initialized = True
            return
        H = np.array([[0.0, 0.0, 1.0, 0.0]])
        R = np.array([[math.radians(sigma_deg) ** 2]])
        S = H @ self.P @ H.T + R
        K = self.P @ H.T / S.item()
        self.state = self.state + (K * wrap(measured - self.state[2])).ravel()
        self.state[2] = wrap(self.state[2])
        I_KH = np.eye(4) - K @ H
        self.P = I_KH @ self.P @ I_KH.T + K @ R @ K.T  # Joseph form: stays symmetric and positive

    def reset_position(self, x, y, sigma_m=0.3):
        """Set the position outright, e.g. when the robot is put back at a known spot."""
        self.state[0], self.state[1] = x, y
        self.P[:2, :] = 0.0
        self.P[:, :2] = 0.0
        self.P[0, 0] = self.P[1, 1] = sigma_m ** 2

    @property
    def x(self):
        return float(self.state[0])

    @property
    def y(self):
        return float(self.state[1])

    @property
    def heading_deg(self):
        return math.degrees(self.state[2]) % 360.0

    @property
    def position_sigma(self):
        """1-sigma position uncertainty in metres (the larger axis of the error ellipse)."""
        return float(math.sqrt(max(np.linalg.eigvalsh(self.P[:2, :2]))))

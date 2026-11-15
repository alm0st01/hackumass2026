"""Drives the two motors straight from the Raspberry Pi 5's GPIO pins, through the L298N.

A stand-in for the ESP32 (integration/pi/motor_link.py): same methods, same -255..255 speeds,
same status dict, so the rest of the Pi code doesn't change.

    motors = PiMotors()
    motors.wait_ready()
    motors.drive(180, 180)  # repeat at least every 300 ms, or the motors stop
    motors.status           # {"left": 180, "right": 180, "distance": 0, "state": "OK"}
    motors.close()

It copies the ESP32 firmware's safety (integration/firmware/main.cpp) with a background thread:
  - motors stop if drive() isn't called for COMMAND_TIMEOUT_S ("TIMEOUT")
  - forward driving stops while the obstacle sensor sees something ("OBSTACLE");
    turning in place and reversing are still allowed
Wiring and setup: drive/pi/README.md
"""
import atexit
import signal
import sys
import threading
import time

# Pins: BCM GPIO numbers (what gpiozero uses), with the physical header pin in brackets.
# All six are at the bottom end of the header, next to GND on pins 34 and 39.
# GPIO 2/3 (pins 3/5) stay free for the IMU's I2C.
LEFT_EN = 12      # [32] L298N ENA
LEFT_IN1 = 5      # [29] L298N IN1
LEFT_IN2 = 6      # [31] L298N IN2
RIGHT_EN = 13     # [33] L298N ENB
RIGHT_IN1 = 20    # [38] L298N IN3
RIGHT_IN2 = 21    # [40] L298N IN4
OBSTACLE_PIN = None  # digital IR obstacle module, e.g. 17 [11]. None = no sensor.

# Same meaning as shared/config.h and drive/control/motors.cpp; tune once the robot is built.
MOTOR_MIN_PWM = 90       # lowest PWM that still turns the wheels
MOTOR_MAX_PWM = 255
INVERT_LEFT = False      # flip if that side drives backwards
INVERT_RIGHT = False
LEFT_MULTIPLIER = 1.00   # lower the stronger side until it drives straight
RIGHT_MULTIPLIER = 1.00
COMMAND_TIMEOUT_S = 0.3  # COMMAND_TIMEOUT_MS
CONTROL_PERIOD_S = 0.02  # CONTROL_PERIOD_MS
PWM_FREQUENCY_HZ = 1000  # same as the ESP32. Lower (e.g. 200) gives more torque at low speed but buzzes.


def apply_min_pwm(speed):
    """Maps 1..255 onto MOTOR_MIN_PWM..MOTOR_MAX_PWM, like the Arduino map() in motors.cpp."""
    if speed == 0:
        return 0
    magnitude = MOTOR_MIN_PWM + (abs(speed) - 1) * (MOTOR_MAX_PWM - MOTOR_MIN_PWM) // 254
    return magnitude if speed > 0 else -magnitude


class _Motor:
    """One L298N channel: EN gets the PWM (speed), IN1/IN2 set the direction."""

    def __init__(self, en_pin, in1_pin, in2_pin, invert):
        from gpiozero import DigitalOutputDevice, PWMOutputDevice

        self.en = PWMOutputDevice(en_pin, frequency=PWM_FREQUENCY_HZ)
        self.in1 = DigitalOutputDevice(in1_pin)
        self.in2 = DigitalOutputDevice(in2_pin)
        self.invert = invert

    def set(self, pwm):
        """pwm: -255..255, after min-PWM mapping."""
        if self.invert:
            pwm = -pwm
        self.in1.value = pwm > 0
        self.in2.value = pwm < 0
        self.en.value = abs(pwm) / 255  # gpiozero wants a duty cycle from 0 to 1

    def close(self):
        self.set(0)
        for device in (self.en, self.in1, self.in2):
            device.close()


class PiMotors:
    def __init__(self):
        self._lock = threading.Lock()
        self._left = _Motor(LEFT_EN, LEFT_IN1, LEFT_IN2, INVERT_LEFT)
        self._right = _Motor(RIGHT_EN, RIGHT_IN1, RIGHT_IN2, INVERT_RIGHT)
        self._obstacle = None
        if OBSTACLE_PIN is not None:
            from gpiozero import DigitalInputDevice

            # Most IR obstacle modules pull their output LOW when they see something,
            # and with pull_up=True gpiozero counts LOW as "active".
            self._obstacle = DigitalInputDevice(OBSTACLE_PIN, pull_up=True)

        self._commanded = (0, 0)
        self._applied = (0, 0)
        self._got_command = False
        self._last_command = 0.0
        self._obstacle_stop = True
        self.status = {"left": 0, "right": 0, "distance": 0, "state": "WAITING"}
        self.status_time = time.time()

        self._running = True
        self._thread = threading.Thread(target=self._control_loop, daemon=True)
        self._thread.start()

        # Stop the motors however the program ends: normal exit, Ctrl+C, or `kill`.
        atexit.register(self.close)
        try:
            if signal.getsignal(signal.SIGTERM) is signal.SIG_DFL:
                signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))  # runs atexit, unlike the default
        except ValueError:
            pass  # not created on the main thread; signals can only be set up there

    # --- same methods as MotorLink ---

    def wait_ready(self, timeout=5.0):
        return True  # nothing to boot

    def drive(self, left, right):
        left = max(-255, min(255, int(left)))
        right = max(-255, min(255, int(right)))
        with self._lock:
            self._commanded = (left, right)
            self._got_command = True
            self._last_command = time.monotonic()
        self._update()  # apply now instead of waiting for the next tick

    def stop(self):
        self.drive(0, 0)

    def set_obstacle_stop(self, enabled):
        with self._lock:
            self._obstacle_stop = bool(enabled)

    @property
    def connected(self):
        return self._running

    def close(self):
        if not self._running:
            return
        self._running = False
        self._thread.join(timeout=1.0)
        self._left.close()
        self._right.close()
        if self._obstacle is not None:
            self._obstacle.close()

    # --- the ESP32 firmware's updateMotors(), run every CONTROL_PERIOD_S ---

    def _control_loop(self):
        while self._running:
            self._update()
            time.sleep(CONTROL_PERIOD_S)

    def _update(self):
        with self._lock:
            if not self._running:
                return
            left, right = self._commanded
            blocked = self._obstacle is not None and self._obstacle.is_active

            if not self._got_command:
                state = "WAITING"
            elif time.monotonic() - self._last_command > COMMAND_TIMEOUT_S:
                state = "TIMEOUT"
            elif self._obstacle_stop and blocked and left + right > 0:
                state = "OBSTACLE"
            else:
                state = "OK"
            if state != "OK":
                left, right = 0, 0

            if (left, right) != self._applied:
                self._set_speeds(left, right)
                self._applied = (left, right)
            # "distance" is 1 or 0 here: a digital sensor only says blocked or not.
            self.status = {"left": left, "right": right, "distance": int(blocked), "state": state}
            self.status_time = time.time()

    def _set_speeds(self, left, right):
        """motors::setSpeeds() from motors.cpp."""
        self._left.set(apply_min_pwm(int(left * LEFT_MULTIPLIER)))
        self._right.set(apply_min_pwm(int(right * RIGHT_MULTIPLIER)))

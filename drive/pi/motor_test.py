"""Motor test for the Pi 5: both motors forward for 10 s, stop for 2 s, repeat. Ctrl+C to quit.
Prop the robot up so the wheels are off the ground.

    python motor_test.py              # speed 200
    python motor_test.py --speed 120
"""
import argparse
import time

from pi_motors import PiMotors

RUN_S = 10.0
REST_S = 2.0
RESEND_S = 0.1  # PiMotors stops the motors after 0.3 s without a command, so keep repeating it


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--speed", type=int, default=200, help="-255..255 (default 200)")
    args = p.parse_args()

    motors = PiMotors()
    print(f"motor_test: {RUN_S:.0f} s forward, {REST_S:.0f} s stop, repeating. Ctrl+C to quit.")
    try:
        while True:
            print(f"forward at {args.speed} for {RUN_S:.0f} s")
            end = time.monotonic() + RUN_S
            while time.monotonic() < end:
                motors.drive(args.speed, args.speed)
                time.sleep(RESEND_S)

            print(f"stop for {REST_S:.0f} s")
            motors.stop()
            time.sleep(REST_S)
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        motors.close()


if __name__ == "__main__":
    main()

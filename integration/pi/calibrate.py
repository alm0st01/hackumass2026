"""Measure the two numbers dead reckoning needs: forward speed and spin rate.

    python calibrate.py --motor-port /dev/serial/by-id/<esp32> forward --seconds 10
        Drives straight at CRUISE_SPEED. Measure the distance with a tape: speed = metres / seconds.
        Pass it to main.py as --speed-mps. Do it on the surface you'll search (grass is slower).

    python calibrate.py --motor-port /dev/serial/by-id/<esp32> spin --seconds 4
        Spins in place at TURN_SPEED. With --imu bno055 it measures the turn itself; otherwise
        count the turns: rate = degrees / seconds. Pass it to main.py as --turn-rate.
"""
import argparse
import time

from follower import CRUISE_SPEED, TURN_SPEED
from motor_link import MotorLink


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--motor-port", required=True)
    p.add_argument("--imu", choices=["bno055", "none"], default="none")
    p.add_argument("--no-obstacle-stop", action="store_true")
    p.add_argument("test", choices=["forward", "spin"])
    p.add_argument("--seconds", type=float, default=10.0)
    args = p.parse_args()

    imu = None
    if args.imu == "bno055":
        from sensors import BNO055
        imu = BNO055()
    link = MotorLink(args.motor_port)
    if not link.wait_ready():
        raise SystemExit("ESP32 didn't answer")
    if args.no_obstacle_stop:
        link.set_obstacle_stop(False)

    speeds = (CRUISE_SPEED, CRUISE_SPEED) if args.test == "forward" else (TURN_SPEED, -TURN_SPEED)
    input(f"Robot will {'drive forward' if args.test == 'forward' else 'spin clockwise'} for {args.seconds:.0f} s. "
          "Clear the area and press Enter...")
    turned, last_heading = 0.0, imu.heading() if imu else None
    end = time.monotonic() + args.seconds
    try:
        while time.monotonic() < end:
            link.drive(*speeds)  # repeat well inside the ESP32's 300 ms timeout
            if imu:
                heading = imu.heading()
                if heading is not None and last_heading is not None:
                    turned += (heading - last_heading + 180) % 360 - 180
                    last_heading = heading
            time.sleep(0.05)
    finally:
        link.close()
    if args.test == "forward":
        print(f"Measure the distance driven (metres) and divide by {args.seconds:.0f}: that's --speed-mps.")
    elif imu:
        print(f"Turned {turned:.0f} degrees: --turn-rate {abs(turned) / args.seconds:.0f}")
    else:
        print(f"Count how far it turned (degrees) and divide by {args.seconds:.0f}: that's --turn-rate.")


if __name__ == "__main__":
    main()

"""IMU check for the Pi 5: prints the heading while you turn the robot by hand. Ctrl+C to quit.
Uses Will's IMU drivers (integration/pi/sensors.py), so it tests exactly what main.py uses.

    python imu_test.py                # MPU6050: keep it still for 2 s while it calibrates
    python imu_test.py --imu bno055

Headings are compass degrees: turning right (clockwise, seen from above) makes them go up.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "integration", "pi"))
from sensors import BNO055, MPU6050  # noqa: E402

READ_PERIOD_S = 0.005  # the MPU6050 heading is integrated each read, so read often
PRINT_PERIOD_S = 0.2


def scan_i2c(bus_number=1):
    from smbus2 import SMBus

    found = []
    with SMBus(bus_number) as bus:
        for address in range(0x03, 0x78):
            try:
                bus.read_byte(address)
                found.append(f"0x{address:02X}")
            except OSError:
                pass
    return found


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--imu", choices=["mpu6050", "bno055"], default="mpu6050")
    args = p.parse_args()

    try:
        if args.imu == "mpu6050":
            print("Calibrating the MPU6050: keep it completely still...")
            imu = MPU6050()
        else:
            imu = BNO055()
    except (OSError, RuntimeError) as error:
        print(f"Couldn't start the {args.imu}: {error}")
        print("Devices on I2C bus 1:", ", ".join(scan_i2c()) or "none. Check VCC/GND and that SDA/SCL aren't swapped.")
        print("(MPU6050 = 0x68, BNO055 = 0x28. If nothing at all shows, is I2C enabled in raspi-config?)")
        sys.exit(1)

    print("Ready. Turn it by hand: right (clockwise) should go up.")
    last_print = 0.0
    try:
        while True:
            heading = imu.heading()
            now = time.monotonic()
            if now - last_print >= PRINT_PERIOD_S:
                last_print = now
                extra = f"   calibration (sys, gyro, accel, mag) {imu.calibration()}" if args.imu == "bno055" else ""
                print(f"heading {heading:6.1f} deg{extra}" if heading is not None else "read failed")
            time.sleep(READ_PERIOD_S)
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()

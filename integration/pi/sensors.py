"""IMU drivers for the Raspberry Pi (I2C; enable with `sudo raspi-config` -> Interface Options -> I2C).

  BNO055   recommended. Has a magnetometer and does its own sensor fusion, so it gives an absolute
           compass heading that doesn't drift. Address 0x28 (0x29 if ADR is pulled high).
  MPU6050  gyro only, no magnetometer. Heading is integrated from the gyro, so it drifts
           (a few degrees per minute) and starts at whatever --start-heading says.

Headings are compass degrees, clockwise from north.
"""
import time


class BNO055:
    heading_sigma = 3.0  # degrees; absolute heading, doesn't drift

    CHIP_ID = 0xA0
    REG_CHIP_ID = 0x00
    REG_EULER_HEADING = 0x1A
    REG_CALIB_STAT = 0x35
    REG_OPR_MODE = 0x3D
    MODE_CONFIG = 0x00
    MODE_NDOF = 0x0C  # full fusion: accelerometer + gyro + magnetometer

    def __init__(self, bus=1, address=0x28, declination_deg=0.0):
        from smbus2 import SMBus

        self.bus = SMBus(bus)
        self.address = address
        self.declination = declination_deg
        chip = self.bus.read_byte_data(address, self.REG_CHIP_ID)
        if chip != self.CHIP_ID:
            raise RuntimeError(f"no BNO055 at 0x{address:02x} (chip id 0x{chip:02x})")
        self.bus.write_byte_data(address, self.REG_OPR_MODE, self.MODE_CONFIG)
        time.sleep(0.03)
        self.bus.write_byte_data(address, self.REG_OPR_MODE, self.MODE_NDOF)
        time.sleep(0.03)

    def heading(self):
        """True-north compass heading in degrees, or None if the read failed."""
        try:
            lo, hi = self.bus.read_i2c_block_data(self.address, self.REG_EULER_HEADING, 2)
        except OSError:
            return None  # I2C glitch (the BNO055 stretches the clock); try again next loop
        return ((lo | hi << 8) / 16.0 + self.declination) % 360.0

    def calibration(self):
        """(system, gyro, accel, mag), each 0 (uncalibrated) to 3 (fully calibrated)."""
        value = self.bus.read_byte_data(self.address, self.REG_CALIB_STAT)
        return value >> 6 & 3, value >> 4 & 3, value >> 2 & 3, value & 3


class MPU6050:
    REG_PWR_MGMT_1 = 0x6B
    REG_GYRO_CONFIG = 0x1B
    REG_GYRO_ZOUT_H = 0x47
    LSB_PER_DPS = 131.0  # +-250 deg/s range

    def __init__(self, bus=1, address=0x68, start_heading_deg=0.0, calibrate_s=2.0):
        from smbus2 import SMBus

        self.bus = SMBus(bus)
        self.address = address
        self.bus.write_byte_data(address, self.REG_PWR_MGMT_1, 0x00)   # wake up
        self.bus.write_byte_data(address, self.REG_GYRO_CONFIG, 0x00)  # +-250 deg/s
        time.sleep(0.1)
        # Gyro bias: the robot must be still while this runs.
        samples = []
        end = time.monotonic() + calibrate_s
        while time.monotonic() < end:
            samples.append(self._rate_dps())
            time.sleep(0.005)
        self.bias = sum(samples) / len(samples)
        self._heading = start_heading_deg
        self._last = time.monotonic()
        self._started = self._last

    DRIFT_DPS = 0.05  # typical leftover drift after bias calibration

    @property
    def heading_sigma(self):
        """How far off the integrated heading may be by now, in degrees."""
        return 3.0 + self.DRIFT_DPS * (time.monotonic() - self._started)

    def _rate_dps(self):
        hi, lo = self.bus.read_i2c_block_data(self.address, self.REG_GYRO_ZOUT_H, 2)
        raw = hi << 8 | lo
        if raw >= 0x8000:
            raw -= 0x10000
        return raw / self.LSB_PER_DPS

    def heading(self):
        now = time.monotonic()
        try:
            rate = self._rate_dps() - self.bias
        except OSError:
            return None
        # Chip z axis up: positive rate = counter-clockwise, so it lowers the compass heading.
        self._heading = (self._heading - rate * (now - self._last)) % 360.0
        self._last = now
        return self._heading

# Motors straight from the Raspberry Pi 5 (no ESP32)

`pi_motors.py` drives the L298N from the Pi's GPIO pins. It has the same methods as the ESP32's
`MotorLink` (`integration/pi/motor_link.py`), so the search code works with either.
It also copies the ESP32's safety: motors stop 300 ms after the last command, and forward
driving stops while the obstacle sensor sees something.

## Wiring

Pin numbers are the physical header pins. Pin 1 is at the end of the header away from the
USB ports; odd pins are on the inner row, even pins on the board edge. The motor pins are
all at the USB-port end (pins 29-40). `pinout` in a Pi terminal prints a map.

| L298N | Pi 5 GPIO | Header pin |
|---|---|---|
| ENA (jumper cap off) | GPIO 12 | 32 |
| IN1 | GPIO 5 | 29 |
| IN2 | GPIO 6 | 31 |
| ENB (jumper cap off) | GPIO 13 | 33 |
| IN3 | GPIO 20 | 38 |
| IN4 | GPIO 21 | 40 |
| GND | GND | 34 or 39 |

- Motor wiring on the L298N is the same as before: left motor on OUT1/OUT2, right on OUT3/OUT4,
  motor battery + into 12V, battery − into GND.
- **The L298N GND must also connect to a Pi GND**, the same as with the ESP32.
- **Leave the L298N's 5V pin unconnected.** 5 V on any Pi GPIO pin can kill the Pi.
- Power the Pi separately (its own USB-C supply or a 5 V power bank), never from the motor battery.
- IMU (MPU6050 or BNO055): VCC to pin 1 (3.3 V), GND to pin 6, SDA to pin 3, SCL to pin 5.
- Optional digital IR obstacle module (the kind with a DO pin and a little blue trim pot):
  VCC to pin 17 (3.3 V, **not** 5 V, or its output puts 5 V on the GPIO), GND to GND,
  DO to pin 11 (GPIO 17), then set `OBSTACLE_PIN = 17` in `pi_motors.py`.
  An analog IR sensor won't work directly: the Pi has no analog inputs. It needs an ADS1115 ADC.

## Setup (on the Pi)

In the same virtual environment as the rest of the Pi code (`integration/README.md`):

```sh
source ~/sar/bin/activate
pip install gpiozero lgpio      # lgpio is the GPIO backend that works on the Pi 5
```

The old `RPi.GPIO` library does **not** work on a Pi 5.

## Tests

Prop the robot up so the wheels are off the ground.

```sh
cd alan/pi
python motor_test.py              # 10 s forward at 200, 2 s stop, repeating; Ctrl+C stops
python motor_test.py --speed 120
python imu_test.py                # MPU6050 (or --imu bno055); turn it by hand
```

## Tuning

The constants at the top of `pi_motors.py` mean the same as in `shared/config.h` and
`alan/control/motors.cpp` (`MOTOR_MIN_PWM`, `INVERT_LEFT`/`RIGHT`, `LEFT`/`RIGHT_MULTIPLIER`).
If the team switches for good, tune them here instead.

## Difference from the ESP32

The ESP32 kept the robot safe even when the Pi crashed. Here the safety runs inside the
Python program. It stops the motors on a normal exit, Ctrl+C, `kill`, or if the main loop
stops sending commands. But if the Pi itself freezes or the program is killed with `kill -9`,
nothing is left to stop the motors. Keep a switch on the motor battery for the demo.

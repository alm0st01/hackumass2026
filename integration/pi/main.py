"""Main program for the robot's Raspberry Pi.

Ties together:
  - Piku's LoRa messaging (piku/meshtastic-testing/robot.py) for talking to the base station
  - a camera detector (vision.py) looking for a person or an AprilTag
  - the ESP32 motor controller over USB serial (motor_link.py, shared/serial_protocol.md)

What it does:
  IDLE       waits for SCAN or RESUME from the base (or starts right away with --autostart)
  EXPLORING  drives forward; when the ESP32 reports an obstacle, turns in place for a moment.
             This is a placeholder until a real search planner exists.
  FOUND      a target was seen in --confirm-frames frames in a row: stops and reports it to the
             base with send_detection(). Waits for RESUME.
  STOPPED    after STOP or HOME from the base. Motors off. (HOME isn't implemented yet: the robot
             doesn't know where home is, so it just stops.)

Examples:
  python main.py --id 1 --radio-port /dev/serial/by-id/<heltec> --motor-port /dev/serial/by-id/<esp32>
  python main.py --sim-radio --no-motors --vision none --autostart     # no hardware at all
"""
import argparse
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "piku", "meshtastic-testing"))

from common import MeshRadio, SimRadio  # noqa: E402  (Piku's code)
from robot import Robot  # noqa: E402

from motor_link import FakeMotorLink, MotorLink  # noqa: E402
from vision import AprilTagDetector, PersonDetector, VisionThread  # noqa: E402

# Match shared/config.h
CRUISE_SPEED = 180
TURN_SPEED = 150

LOOP_PERIOD_S = 0.05        # 20 Hz main loop
MOTOR_KEEPALIVE_S = 0.1     # ESP32 stops the motors after 300 ms without a command
OBSTACLE_TURN_S = (0.6, 1.4)  # random turn length after an obstacle, seconds


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--id", type=int, default=1, help="robot ID, must be unique (the base is 0)")
    radio = p.add_mutually_exclusive_group()
    radio.add_argument("--radio-port", help="serial port of the Heltec LoRa board (strongly recommended, see README)")
    radio.add_argument("--sim-radio", action="store_true", help="Piku's fake radio, to test with base.py --sim on one computer")
    motors = p.add_mutually_exclusive_group()
    motors.add_argument("--motor-port", help="serial port of the ESP32 motor controller")
    motors.add_argument("--no-motors", action="store_true", help="fake motors (prints speeds instead)")
    p.add_argument("--vision", choices=["person", "apriltag", "none"], default="person")
    p.add_argument("--tag-id", type=int, default=0, help="AprilTag ID to look for (--vision apriltag)")
    p.add_argument("--camera", default="0", help="camera index, or a video file for testing")
    p.add_argument("--min-confidence", type=float, default=0.6, help="person detector threshold")
    p.add_argument("--confirm-frames", type=int, default=5, help="frames in a row needed to count as found")
    p.add_argument("--autostart", action="store_true", help="start exploring without waiting for the base")
    p.add_argument("--no-obstacle-stop", action="store_true",
                   help="turn off the ESP32's obstacle stop (use when no distance sensor is connected)")
    args = p.parse_args()
    if not args.no_motors and not args.motor_port:
        p.error("give --motor-port (the ESP32's serial port) or --no-motors")
    return args


class RobotBrain:
    def __init__(self, args, robot, motors, vision):
        self.args = args
        self.robot = robot
        self.motors = motors
        self.vision = vision
        self.state = "IDLE"
        self.target = (0, 0)
        self.last_motor_send = 0.0
        self.turn_until = 0.0
        self.turn_direction = 1
        self.streak = 0
        self.last_frame = 0
        self.found = None          # (confidence, box) of the confirmed target
        self.reported = False      # base has been sent the detection
        self.motor_link_ok = True
        if args.autostart:
            self.set_state("EXPLORING")

    def set_state(self, state):
        if state != self.state:
            print(f"[robot {self.args.id}] {self.state} -> {state}")
        self.state = state
        self.robot.state = state  # goes out in the next heartbeat

    def handle_commands(self):
        while True:
            command = self.robot.next_command()
            if command is None:
                return
            if command == "STOP":
                self.set_state("STOPPED")
            elif command == "HOME":
                print(f"[robot {self.args.id}] HOME isn't implemented yet (no position tracking); stopping")
                self.set_state("STOPPED")
            elif command in ("RESUME", "SCAN"):
                self.found = None
                self.streak = 0
                self.set_state("EXPLORING")

    def check_vision(self):
        if self.vision is None:
            return
        result = self.vision.latest
        if result is None or result.frame == self.last_frame:
            return  # no new frame since last time
        self.last_frame = result.frame
        if result.box is None:
            self.streak = 0
            return
        self.streak += 1
        if self.streak >= self.args.confirm_frames and self.state == "EXPLORING":
            self.found = (result.confidence, result.box)
            self.reported = False
            print(f"[robot {self.args.id}] TARGET CONFIRMED ({result.confidence:.0%}, box {result.box})")
            self.set_state("FOUND")

    def report_found(self):
        # send_detection() refuses if we're not connected to the base yet, or sent one under 3 s ago,
        # so keep trying until it goes out. Piku's code then resends it until the base ACKs.
        if self.state == "FOUND" and not self.reported and self.found:
            if self.robot.send_detection(*self.found):
                self.reported = True
                print(f"[robot {self.args.id}] detection sent to base")

    def choose_speeds(self, now):
        if self.state != "EXPLORING":
            return 0, 0
        status = self.motors.status or {}
        if status.get("state") == "OBSTACLE" and now >= self.turn_until:
            self.turn_direction = random.choice((-1, 1))
            self.turn_until = now + random.uniform(*OBSTACLE_TURN_S)
            print(f"[robot {self.args.id}] obstacle, turning {'left' if self.turn_direction < 0 else 'right'}")
        if now < self.turn_until:
            return self.turn_direction * TURN_SPEED, -self.turn_direction * TURN_SPEED
        return CRUISE_SPEED, CRUISE_SPEED

    def drive_motors(self, now):
        target = self.choose_speeds(now)
        # Send on every change, and repeat at least every 100 ms so the ESP32's safety timeout doesn't trip.
        if target != self.target or now - self.last_motor_send >= MOTOR_KEEPALIVE_S:
            self.motors.drive(*target)
            self.target = target
            self.last_motor_send = now
        if self.motor_link_ok and not self.motors.connected:
            print("[motors] no STATUS from the ESP32 for 1 s; is it plugged in?")
        self.motor_link_ok = self.motors.connected

    def step(self):
        now = time.time()
        self.robot.update()  # Piku: radio in/out, heartbeats, resends
        self.handle_commands()
        self.check_vision()
        self.report_found()
        self.drive_motors(now)


def main():
    args = parse_args()

    if args.sim_radio:
        radio = SimRadio()
    else:
        if not args.radio_port:
            print("Warning: no --radio-port given. Meshtastic will guess, and it may pick the ESP32 instead of the Heltec.")
        radio = MeshRadio(args.radio_port)
    robot = Robot(args.id, radio)

    motors = FakeMotorLink() if args.no_motors else MotorLink(args.motor_port)
    if not motors.wait_ready():
        sys.exit(f"The ESP32 on {args.motor_port} didn't answer. Is the firmware flashed and the port right?")
    print("[motors] ESP32 ready")
    if args.no_obstacle_stop:
        motors.set_obstacle_stop(False)
        print("[motors] obstacle stop OFF")

    vision = None
    if args.vision != "none":
        detector = PersonDetector(min_confidence=args.min_confidence) if args.vision == "person" else AprilTagDetector(args.tag_id)
        source = int(args.camera) if args.camera.isdigit() else args.camera
        vision = VisionThread(detector, source)
        vision.start()
        print(f"[vision] looking for {'a person' if args.vision == 'person' else f'AprilTag {args.tag_id}'}")

    brain = RobotBrain(args, robot, motors, vision)
    print(f"[robot {args.id}] running. Waiting for the base{' (autostart on)' if args.autostart else ''}. Ctrl-C to quit.")
    try:
        while True:
            brain.step()
            time.sleep(LOOP_PERIOD_S)
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        motors.close()
        if vision:
            vision.stop()


if __name__ == "__main__":
    main()

"""Main program for the robot's Raspberry Pi.

Ties together:
  - Piku's LoRa messaging (piku/meshtastic-testing/robot.py) for talking to the base station
  - a camera detector (vision.py) looking for a person or an AprilTag
  - a search pattern (planner.py) and position estimate (estimator.py: IMU heading + timed driving, no GPS)
  - the ESP32 motor controller over USB serial (motor_link.py, shared/serial_protocol.md)

States (sent to the base in every heartbeat):
  IDLE         waiting for SCAN or RESUME from the base (or starts right away with --autostart)
  EXPLORING    following the search pattern; detours around obstacles the ESP32 reports
  FOUND        target confirmed (Adi's two-tier streak, see check_vision): stops and reports it. RESUME continues.
  SEARCH_DONE  reached the end of the pattern
  RETURNING    after HOME: drives back to the start point, then STOPPED
  STOPPED      after STOP, or when back home

Every HEARTBEAT and DETECTION also carries the estimated position (x, y, err), see
located_robot.py. Use integration/base_station.py on the laptop to see it.

Base commands: SCAN starts the pattern from the beginning, RESUME continues it where it left off.

Examples:
  python main.py --id 1 --radio-port /dev/serial/by-id/<heltec> --motor-port /dev/serial/by-id/<esp32> \\
      --imu bno055 --speed-mps 0.45 --turn-rate 85 --pattern grid --width 30 --length 40 --spacing 6
  python main.py --sim-radio --sim --vision none --autostart     # no hardware at all
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "piku", "meshtastic-testing"))

from common import MeshRadio, SimRadio  # noqa: E402  (Piku's code)

from estimator import PoseEstimator  # noqa: E402
from located_robot import LocatedRobot  # noqa: E402  (Piku's Robot + x / y / err in messages)
from motor_link import MotorLink  # noqa: E402
from navigator import Navigator  # noqa: E402
from planner import grid_search, path_length, radial_search, sector_search  # noqa: E402

LOOP_PERIOD_S = 0.05        # 20 Hz main loop
MOTOR_KEEPALIVE_S = 0.1     # ESP32 stops the motors after 300 ms without a command
STATUS_PRINT_S = 5.0


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--id", type=int, default=1, help="robot ID, must be unique (the base is 0)")

    g = p.add_argument_group("hardware")
    radio = g.add_mutually_exclusive_group()
    radio.add_argument("--radio-port", help="serial port of the Heltec LoRa board (strongly recommended, see README)")
    radio.add_argument("--sim-radio", action="store_true", help="Piku's fake radio, to test with base.py --sim on one computer")
    motors = g.add_mutually_exclusive_group()
    motors.add_argument("--motor-port", help="serial port of the ESP32 motor controller")
    motors.add_argument("--sim", action="store_true", help="simulated robot: motors and IMU (no hardware)")
    g.add_argument("--imu", choices=["bno055", "mpu6050", "none"], default="bno055")
    g.add_argument("--declination", type=float, default=-14.0,
                   help="magnetic declination in degrees, added to the BNO055 heading (-14 for Massachusetts)")
    g.add_argument("--start-heading", type=float, default=0.0,
                   help="compass heading the robot faces at start (needed with --imu mpu6050 or none)")
    g.add_argument("--no-obstacle-stop", action="store_true",
                   help="turn off the ESP32's obstacle stop (use when no distance sensor is connected)")

    g = p.add_argument_group("calibration (measure these, see README)")
    g.add_argument("--speed-mps", type=float, default=0.5, help="forward speed at CRUISE_SPEED, m/s")
    g.add_argument("--turn-rate", type=float, default=90.0, help="spin-in-place rate at TURN_SPEED, degrees/s")

    g = p.add_argument_group("search pattern (metres; x = east, y = north, (0, 0) = start point)")
    g.add_argument("--pattern", choices=["grid", "sector", "radial"], default="grid")
    g.add_argument("--width", type=float, default=30.0, help="grid: box width across the tracks")
    g.add_argument("--length", type=float, default=40.0, help="grid: track length")
    g.add_argument("--spacing", type=float, default=6.0, help="grid: distance between tracks (~2x camera detection range)")
    g.add_argument("--side", choices=["right", "left"], default="right", help="grid: which side of the first track to search")
    g.add_argument("--radius", type=float, default=15.0, help="sector: leg length; radial: spoke length")
    g.add_argument("--spokes", type=int, default=8, help="radial: number of spokes")
    g.add_argument("--pattern-heading", type=float, default=0.0, help="compass direction of the first track / leg / spoke")
    g.add_argument("--datum", type=float, nargs=2, default=(0.0, 0.0), metavar=("X", "Y"),
                   help="grid: start corner; sector/radial: centre")
    g.add_argument("--arrive-radius", type=float, default=1.5, help="waypoint counts as reached within this distance")

    g = p.add_argument_group("vision")
    g.add_argument("--vision", choices=["person", "apriltag", "none"], default="person")
    g.add_argument("--tag-id", type=int, default=0, help="AprilTag ID to look for (--vision apriltag)")
    g.add_argument("--camera", default="0", help="camera index, or a video file for testing")
    # Same two-tier confirmation as adi/yolo-and-tags/person.py
    g.add_argument("--min-confidence", type=float, default=0.35,
                   help="weak detection: adds 1 to the streak. Below this is ignored (Adi's LOW)")
    g.add_argument("--high-confidence", type=float, default=0.60,
                   help="strong detection: adds 2 to the streak (Adi's HIGH)")
    g.add_argument("--confirm-frames", type=int, default=10,
                   help="streak points needed to confirm (Adi's CONFIRM_FRAMES). A frame without a detection takes 1 off")

    p.add_argument("--autostart", action="store_true", help="start the search without waiting for SCAN from the base")
    args = p.parse_args()
    if not args.sim and not args.motor_port:
        p.error("give --motor-port (the ESP32's serial port) or --sim")
    return args


def make_waypoints(args):
    datum = tuple(args.datum)
    if args.pattern == "grid":
        return grid_search(args.width, args.length, args.spacing, corner=datum,
                           heading_deg=args.pattern_heading, side=args.side)
    if args.pattern == "sector":
        return sector_search(args.radius, datum=datum, heading_deg=args.pattern_heading)
    return radial_search(args.radius, spokes=args.spokes, center=datum, heading_deg=args.pattern_heading)


class RobotBrain:
    def __init__(self, args, robot, motors, navigator, vision, sim=None):
        self.args = args
        self.robot = robot
        self.motors = motors
        self.nav = navigator
        self.vision = vision
        self.sim = sim
        self.state = "IDLE"
        self.pattern = make_waypoints(args)
        self.pattern_index = 0     # where to RESUME the pattern
        self.target = (0, 0)
        self.last_motor_send = 0.0
        self.last_print = 0.0
        self.last_time = None
        self.streak = 0
        self.last_frame = 0
        self.found = None          # (confidence, box) of the confirmed target
        self.reported = False
        self.motor_link_ok = True
        print(f"[plan] {args.pattern} search: {len(self.pattern)} waypoints, {path_length(self.pattern):.0f} m, "
              f"about {path_length(self.pattern) / args.speed_mps / 60:.0f} min at {args.speed_mps} m/s")
        if args.autostart:
            self.start_pattern(from_start=True)

    def say(self, text):
        print(f"[robot {self.args.id}] {text}")

    def set_state(self, state):
        if state != self.state:
            self.say(f"{self.state} -> {state}")
        self.state = state
        self.robot.state = state  # goes out in the next heartbeat

    # ------------------------------------------------------------------ commands
    def start_pattern(self, from_start):
        if from_start:
            self.pattern_index = 0
        self.nav.follow(self.pattern[self.pattern_index:])
        self.found, self.streak = None, 0
        self.set_state("EXPLORING")

    def remember_progress(self):
        if self.state == "EXPLORING" and self.nav.follower is not None:
            self.pattern_index = min(len(self.pattern), self.pattern_index + self.nav.follower.index)

    def handle_commands(self):
        while True:
            command = self.robot.next_command()
            if command is None:
                return
            if command == "STOP":
                self.remember_progress()
                self.nav.follow([])
                self.set_state("STOPPED")
            elif command == "HOME":
                self.remember_progress()
                self.nav.follow([(0.0, 0.0)])
                self.set_state("RETURNING")
            elif command == "SCAN":
                self.start_pattern(from_start=True)
            elif command == "RESUME":
                if self.state == "EXPLORING":
                    continue
                self.start_pattern(from_start=False)

    # ------------------------------------------------------------------ vision
    def check_vision(self):
        if self.vision is None:
            return
        result = self.vision.latest
        if result is None or result.frame == self.last_frame:
            return  # no new frame since last time
        self.last_frame = result.frame
        # Adi's two-tier streak: strong detections count double, weak ones once, and a miss
        # only takes 1 off, so a flickering detection on a moving robot still adds up.
        if result.box is None:
            self.streak = max(0, self.streak - 1)
            return
        self.streak += 2 if result.confidence >= self.args.high_confidence else 1
        if self.streak >= self.args.confirm_frames and self.state == "EXPLORING":
            self.remember_progress()
            self.nav.follow([])
            self.update_position()  # the DETECTION carries the position at this moment
            self.found = (result.confidence, result.box)
            self.reported = False
            e = self.nav.estimator
            self.say(f"TARGET CONFIRMED ({result.confidence:.0%}) at x {e.x:.1f} m, y {e.y:.1f} m from the start "
                     f"(+-{e.position_sigma:.1f} m)")
            self.set_state("FOUND")

    def report_found(self):
        # send_detection() refuses if we're not connected to the base yet, or sent one under 3 s ago,
        # so keep trying until it goes out. Piku's code then resends it until the base ACKs.
        if self.state == "FOUND" and not self.reported and self.found:
            if self.robot.send_detection(*self.found):
                self.reported = True
                self.say("detection sent to base")

    def update_position(self):
        """Copy the estimate into the robot, so the next HEARTBEAT / DETECTION carries it."""
        e = self.nav.estimator
        self.robot.x, self.robot.y = e.x, e.y
        self.robot.position_err = e.position_sigma
        self.robot.heading = int(round(e.heading_deg)) % 360

    # ------------------------------------------------------------------ driving
    def drive(self, now):
        status = self.motors.status or {}
        applied = (status.get("left", 0), status.get("right", 0))
        left, right = self.nav.step(now, *applied, status.get("state", "OK"))
        for message in self.nav.log:
            self.say(message)
        self.nav.log.clear()

        if self.nav.done:
            if self.state == "EXPLORING":
                self.pattern_index = len(self.pattern)
                self.set_state("SEARCH_DONE")
            elif self.state == "RETURNING":
                self.set_state("STOPPED")
            left, right = 0, 0

        # Send on every change, and repeat at least every 100 ms so the ESP32's safety timeout doesn't trip.
        target = (int(left), int(right))
        if target != self.target or now - self.last_motor_send >= MOTOR_KEEPALIVE_S:
            self.motors.drive(*target)
            self.target = target
            self.last_motor_send = now
        if self.motor_link_ok and not self.motors.connected:
            print("[motors] no STATUS from the ESP32 for 1 s; is it plugged in?")
        self.motor_link_ok = self.motors.connected

        self.update_position()
        e = self.nav.estimator
        if now - self.last_print >= STATUS_PRINT_S:
            self.last_print = now
            waypoint = ""
            if self.nav.follower is not None and not self.nav.done:
                waypoint = f", next waypoint {self.nav.follower.distance_to_current(e.x, e.y):.1f} m away"
            truth = f" (sim truth: x {self.sim.x:.1f}, y {self.sim.y:.1f})" if self.sim else ""
            self.say(f"{self.state}: x {e.x:.1f} m, y {e.y:.1f} m, heading {e.heading_deg:.0f}, "
                     f"+-{e.position_sigma:.1f} m{waypoint}{truth}")

    def step(self):
        now = time.monotonic()
        if self.sim is not None:
            if self.last_time is not None:
                self.sim.advance(now - self.last_time)
        self.last_time = now
        self.robot.update()  # Piku: radio in/out, heartbeats, resends
        self.handle_commands()
        self.check_vision()
        self.report_found()
        self.drive(now)


def make_imu(args):
    if args.imu == "bno055":
        from sensors import BNO055
        imu = BNO055(declination_deg=args.declination)
        print(f"[imu] BNO055 ready. Calibration (sys, gyro, accel, mag): {imu.calibration()} (3 = calibrated)")
        return imu
    if args.imu == "mpu6050":
        from sensors import MPU6050
        print("[imu] MPU6050: calibrating the gyro, keep the robot still for 2 s...")
        return MPU6050(start_heading_deg=args.start_heading)
    print("[imu] none: heading comes from the motor commands only and will drift quickly")
    return None


def main():
    args = parse_args()

    radio = SimRadio() if args.sim_radio else None
    if radio is None:
        if not args.radio_port:
            print("Warning: no --radio-port given. Meshtastic will guess, and it may pick the ESP32 instead of the Heltec.")
        radio = MeshRadio(args.radio_port)
    robot = LocatedRobot(args.id, radio)

    sim = None
    if args.sim:
        from sim import SimWorld
        sim = SimWorld(speed_mps=args.speed_mps, turn_rate_dps=args.turn_rate, start_heading_deg=args.start_heading)
        motors, imu = sim, sim.imu
        print("[sim] simulated motors and IMU")
    else:
        motors = MotorLink(args.motor_port)
        if not motors.wait_ready():
            sys.exit(f"The ESP32 on {args.motor_port} didn't answer. Is the firmware flashed and the port right?")
        print("[motors] ESP32 ready")
        imu = make_imu(args)
    if args.no_obstacle_stop:
        motors.set_obstacle_stop(False)
        print("[motors] obstacle stop OFF")

    estimator = PoseEstimator(heading_deg=args.start_heading, heading_known=imu is None or args.imu == "mpu6050")
    navigator = Navigator(args.speed_mps, args.turn_rate, imu=imu, estimator=estimator,
                          arrive_radius=args.arrive_radius)

    vision = None
    if args.vision != "none":
        from vision import AprilTagDetector, PersonDetector, VisionThread
        detector = PersonDetector(min_confidence=args.min_confidence) if args.vision == "person" else AprilTagDetector(args.tag_id)
        source = int(args.camera) if args.camera.isdigit() else args.camera
        vision = VisionThread(detector, source)
        vision.start()
        print(f"[vision] looking for {'a person' if args.vision == 'person' else f'AprilTag {args.tag_id}'}")

    brain = RobotBrain(args, robot, motors, navigator, vision, sim)
    print(f"[robot {args.id}] running.{' Autostart on.' if args.autostart else ' Waiting for SCAN from the base.'} Ctrl-C to quit.")
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

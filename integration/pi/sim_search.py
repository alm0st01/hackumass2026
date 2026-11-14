"""Simulates the search patterns with imperfect sensors (no GPS) and reports how well each setup
works. Uses the same Navigator as the robot, with a simulated clock (runs in seconds).

    python sim_search.py                 # table of results
    python sim_search.py --plot out.png  # also draw the paths (needs matplotlib)

Setups compared:
  compass      BNO055-style IMU (absolute heading, small fixed bias) + timed driving
  gyro         MPU6050-style IMU (heading drifts over time) + timed driving
  no IMU       heading from motor commands only
and, for the compass setup, how much the speed calibration matters (10% vs 3% off).
"""
import argparse
import math
import random
import statistics

from estimator import PoseEstimator
from navigator import Navigator
from planner import grid_search, path_length, radial_search, sector_search
from sim import SimWorld

DT = 0.05
SPEED_MPS = 0.5           # calibrated speed at CRUISE
TURN_RATE_DPS = 90.0
DETECTION_RADIUS_M = 3.0  # camera spots a person within this distance of the path
TIME_LIMIT_S = 1800

SETUPS = {
    # name: (sim IMU kind, navigator gets an IMU, true speed / calibrated speed)
    "compass, speed 10% off": ("compass", True, 0.90),
    "compass, speed 3% off": ("compass", True, 0.97),
    "gyro, speed 10% off": ("gyro", True, 0.90),
    "no IMU, speed 10% off": ("compass", False, 0.90),
}


def patterns():
    return {
        "grid 30x40 m, 6 m tracks": (grid_search(width=30, length=40, spacing=6), ("rect", 30, 40)),
        "sector, 15 m legs": (sector_search(radius=15), ("circle", 15)),
        "radial, 8 spokes x 15 m": (radial_search(radius=15, spokes=8), ("circle", 15)),
    }


def random_obstacles(rng, area, count=5):
    obstacles = []
    while len(obstacles) < count:
        if area[0] == "rect":
            x, y = rng.uniform(0, area[1]), rng.uniform(0, area[2])
        else:
            angle, r = rng.uniform(0, 2 * math.pi), rng.uniform(3, area[1])
            x, y = r * math.sin(angle), r * math.cos(angle)
        if math.hypot(x, y) > 3:
            obstacles.append((x, y, rng.uniform(0.4, 0.9)))
    return obstacles


def coverage(path, area, radius=DETECTION_RADIUS_M, cell=1.0):
    """Fraction of the intended search area within `radius` of a path (where the robot really went)."""
    if area[0] == "rect":
        cells = [(x + 0.5, y + 0.5) for x in range(int(area[1] / cell)) for y in range(int(area[2] / cell))]
    else:
        r = area[1]
        cells = [(x + 0.5, y + 0.5) for x in range(-int(r), int(r)) for y in range(-int(r), int(r))
                 if math.hypot(x + 0.5, y + 0.5) <= r]
    buckets = {}
    for px, py in path:
        buckets.setdefault((int(px // radius), int(py // radius)), []).append((px, py))
    seen = 0
    for cx, cy in cells:
        bx, by = int(cx // radius), int(cy // radius)
        near = (p for dx in (-1, 0, 1) for dy in (-1, 0, 1) for p in buckets.get((bx + dx, by + dy), ()))
        if any(math.hypot(cx - px, cy - py) <= radius for px, py in near):
            seen += 1
    return seen / len(cells)


def planned_coverage(waypoints, area, step=0.5):
    """Coverage if the robot followed the planned path exactly: the best the pattern can do."""
    points, previous = [], (0.0, 0.0)
    for point in waypoints:
        n = max(1, int(math.dist(previous, point) / step))
        points += [(previous[0] + (point[0] - previous[0]) * i / n, previous[1] + (point[1] - previous[1]) * i / n)
                   for i in range(n)]
        previous = point
    return coverage(points, area)


def run(waypoints, area, setup, seed):
    imu_kind, use_imu, speed_scale = SETUPS[setup]
    rng = random.Random(seed)
    world = SimWorld(speed_mps=SPEED_MPS, turn_rate_dps=TURN_RATE_DPS, true_speed_scale=speed_scale,
                     imu=imu_kind, obstacles=random_obstacles(rng, area), seed=seed)
    estimator = PoseEstimator(heading_known=not use_imu or imu_kind == "gyro")
    nav = Navigator(SPEED_MPS, TURN_RATE_DPS, imu=world.imu if use_imu else None, estimator=estimator, rng=rng)
    nav.follow(waypoints)
    true_path, est_path, errors = [], [], []
    while not nav.done and world.time < TIME_LIMIT_S:
        left, right = nav.step(world.time, *world.applied, world.state)
        world.drive(left, right)
        world.advance(DT)
        true_path.append((world.x, world.y))
        est_path.append((nav.estimator.x, nav.estimator.y))
        errors.append(math.hypot(world.x - nav.estimator.x, world.y - nav.estimator.y))
    return {
        "completed": nav.done, "time": world.time, "max_err": max(errors), "final_err": errors[-1],
        "sigma": nav.estimator.position_sigma, "coverage": coverage(true_path[::4], area),
        "true_path": true_path, "est_path": est_path, "obstacles": world.obstacles,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--seeds", type=int, default=8, help="runs per case (different noise and obstacles)")
    p.add_argument("--plot", help="save a PNG of the paths (first seed)")
    args = p.parse_args()

    first_runs = {}
    print(f"{'setup':24} {'done':>5} {'time':>6} {'worst err':>9} {'end err':>8} {'filter sigma':>12} {'covered':>8}")
    for name, (waypoints, area) in patterns().items():
        print(f"{name}: planned path {path_length(waypoints):.0f} m, covers {planned_coverage(waypoints, area):.0%} if followed exactly")
        for setup in SETUPS:
            results = [run(waypoints, area, setup, seed) for seed in range(1, args.seeds + 1)]
            first_runs[(name, setup)] = results[0]
            mean = lambda key: statistics.fmean(r[key] for r in results)
            done = sum(r["completed"] for r in results)
            print(f"  {setup:22} {done:>3}/{len(results)} {mean('time'):5.0f}s {mean('max_err'):8.1f}m "
                  f"{mean('final_err'):7.1f}m {mean('sigma'):11.1f}m {mean('coverage'):7.0%}")

    if args.plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        shown = ["compass, speed 10% off", "gyro, speed 10% off"]
        fig, axes = plt.subplots(len(shown), 3, figsize=(15, 5 * len(shown)))
        for col, name in enumerate(patterns()):
            waypoints = patterns()[name][0]
            for row, setup in enumerate(shown):
                ax = axes[row][col]
                r = first_runs[(name, setup)]
                ax.plot([0] + [w[0] for w in waypoints], [0] + [w[1] for w in waypoints], "k--", lw=1, label="planned")
                ax.plot(*zip(*r["true_path"]), color="tab:blue", lw=1.5, label="where it really went")
                ax.plot(*zip(*r["est_path"]), color="tab:orange", lw=1, label="where it thought it was")
                for ox, oy, rad in r["obstacles"]:
                    ax.add_patch(plt.Circle((ox, oy), rad, color="tab:red", alpha=0.6))
                ax.set_aspect("equal")
                ax.set_title(f"{name}\n{setup}: covered {r['coverage']:.0%}", fontsize=10)
                ax.grid(alpha=0.3)
                if row == 0 and col == 0:
                    ax.legend(fontsize=8, loc="lower right")
        fig.tight_layout()
        fig.savefig(args.plot, dpi=90)
        print(f"saved {args.plot}")


if __name__ == "__main__":
    main()

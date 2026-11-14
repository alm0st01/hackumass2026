"""Search patterns, as lists of waypoints.

Coordinates are metres in a local frame: x = east, y = north, origin = where the robot was
started (normally next to the base). Bearings are compass degrees: 0 = north, 90 = east.

    grid_search(width=20, length=30, spacing=6)       # back-and-forth tracks over a box
    sector_search(radius=15)                          # IAMSAR "VS" pattern: 3 triangles through the datum
    radial_search(radius=15, spokes=8)                # out and back along evenly spaced spokes

"spacing" is the distance between grid tracks. Set it to about twice the distance at which the
camera reliably spots a person, so neighbouring tracks' views overlap.
"""
import math
from typing import List, Tuple

Point = Tuple[float, float]


def offset(point: Point, bearing_deg: float, distance: float) -> Point:
    """The point `distance` metres from `point` in compass direction `bearing_deg`."""
    b = math.radians(bearing_deg)
    return point[0] + distance * math.sin(b), point[1] + distance * math.cos(b)


def grid_search(width: float, length: float, spacing: float, corner: Point = (0.0, 0.0),
                heading_deg: float = 0.0, side: str = "right") -> List[Point]:
    """Parallel-track ("lawnmower") search over a width x length rectangle.

    corner:      the rectangle's starting corner
    heading_deg: direction of the long tracks
    side:        which side of the first track the rest of the box lies ("right" or "left")

    Tracks are at most `spacing` apart, the outer ones spacing/2 in from the edge.
    """
    if width <= 0 or length <= 0 or spacing <= 0:
        raise ValueError("width, length and spacing must be positive")
    across = heading_deg + (90.0 if side == "right" else -90.0)
    tracks = max(1, math.ceil(width / spacing))
    step = width / tracks
    waypoints = []
    for i in range(tracks):
        start = offset(corner, across, (i + 0.5) * step)
        end = offset(start, heading_deg, length)
        waypoints += [start, end] if i % 2 == 0 else [end, start]
    return waypoints


def sector_search(radius: float, datum: Point = (0.0, 0.0), heading_deg: float = 0.0,
                  turn: str = "right") -> List[Point]:
    """IAMSAR sector ("VS") search: legs of length `radius`, 120 degree turns, every third leg
    passing back through the datum. Makes three equilateral triangles that share the datum.
    Use it when the person's last known position is good: coverage is densest at the datum.
    """
    if radius <= 0:
        raise ValueError("radius must be positive")
    sign = 1.0 if turn == "right" else -1.0
    waypoints = [datum]
    for k in range(3):
        # Each triangle starts by carrying straight on through the datum, so the start
        # direction moves round by 240 degrees (= -120) per triangle.
        h = heading_deg + sign * 240.0 * k
        a = offset(datum, h, radius)
        b = offset(a, h + sign * 120.0, radius)
        waypoints += [a, b, datum]
    return waypoints


def radial_search(radius: float, spokes: int = 8, center: Point = (0.0, 0.0),
                  heading_deg: float = 0.0) -> List[Point]:
    """Out-and-back legs along `spokes` evenly spaced bearings, returning to the centre each time."""
    if radius <= 0 or spokes < 1:
        raise ValueError("radius must be positive and spokes at least 1")
    waypoints = [center]
    for i in range(spokes):
        waypoints += [offset(center, heading_deg + 360.0 * i / spokes, radius), center]
    return waypoints


def path_length(waypoints: List[Point], start: Point = (0.0, 0.0)) -> float:
    total, previous = 0.0, start
    for point in waypoints:
        total += math.dist(previous, point)
        previous = point
    return total

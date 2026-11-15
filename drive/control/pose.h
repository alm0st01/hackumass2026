#pragma once
#include <math.h>

// Where a robot is on the floor, relative to where it started.
// Estimated on the robot: gyro (IMU) for heading, drive commands for distance.
//
// Coordinate convention:
//   x, y in cm. The robot starts at (0, 0) facing +x.
//   headingDeg: 0 = facing +x, counterclockwise positive, range -180..180.
struct Pose {
    float x;
    float y;
    float headingDeg;
};

// Wraps an angle into -180..180 degrees (e.g. 270 -> -90).
// `inline` lets a function body live in a header that several .cpp files
// include, without the linker complaining it was defined more than once.
inline float wrapDeg(float deg) {
    deg = fmodf(deg + 180.0f, 360.0f);   // fmodf can return negatives...
    if (deg < 0.0f) deg += 360.0f;       // ...so bring it into 0..360
    return deg - 180.0f;
}

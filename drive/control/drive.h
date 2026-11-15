#pragma once
#include <stdint.h>
#include "pose.h"

// Drive-to-a-point controller. Plain C++ (no Arduino) so the laptop
// simulator and the robot firmware run exactly the same code.

// Motor commands, same -255..255 scale as motors::setSpeeds().
struct WheelCommand {
    int16_t left;
    int16_t right;
};

class DriveController {
public:
    // One control step: call every CONTROL_PERIOD_MS with the latest pose.
    // Passing a different target than last time starts a fresh approach.
    WheelCommand update(const Pose& pose, float targetX, float targetY);

    // True once the robot is within ARRIVE_RADIUS_CM of the target.
    bool arrived() const { return arrived_; }

private:
    bool hasTarget_ = false;
    float targetX_ = 0.0f;
    float targetY_ = 0.0f;
    bool turning_ = false;   // currently turning in place
    bool arrived_ = false;
};

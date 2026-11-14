#include "drive.h"
#include <math.h>
#include "config.h"

namespace {
    const float RAD_TO_DEG = 57.2957795f;

    int16_t clampCommand(float value) {
        if (value > MOTOR_MAX_PWM) value = MOTOR_MAX_PWM;
        if (value < -MOTOR_MAX_PWM) value = -MOTOR_MAX_PWM;
        return static_cast<int16_t>(lroundf(value));
    }
}

WheelCommand DriveController::update(const Pose& pose, float targetX, float targetY) {
    // New target: forget the old approach.
    if (!hasTarget_ || targetX != targetX_ || targetY != targetY_) {
        hasTarget_ = true;
        targetX_ = targetX;
        targetY_ = targetY;
        turning_ = false;
        arrived_ = false;
    }

    float dx = targetX - pose.x;
    float dy = targetY - pose.y;
    float dist = sqrtf(dx * dx + dy * dy);

    // Arrival, with hysteresis: once arrived, only start moving again if
    // pushed well outside the radius, so camera noise can't make it twitch.
    if (arrived_ && dist < 2.0f * ARRIVE_RADIUS_CM) return {0, 0};
    if (dist < ARRIVE_RADIUS_CM) {
        arrived_ = true;
        turning_ = false;
        return {0, 0};
    }
    arrived_ = false;

    // Heading error: positive means the target is to our left.
    float targetDeg = atan2f(dy, dx) * RAD_TO_DEG;
    float error = wrapDeg(targetDeg - pose.headingDeg);

    // Turn in place for big errors. Two thresholds (enter above one, leave
    // below the other) stop it flickering between modes near the boundary.
    if (fabsf(error) > TURN_IN_PLACE_DEG) turning_ = true;
    else if (fabsf(error) < TURN_EXIT_DEG) turning_ = false;

    if (turning_) {
        int16_t s = (error > 0) ? TURN_SPEED : -TURN_SPEED;
        return {static_cast<int16_t>(-s), s};   // left back, right forward = turn left
    }

    // Proportional steering: speed up the outside wheel, slow the inside one.
    float correction = STEER_GAIN * error;
    return {clampCommand(CRUISE_SPEED - correction),
            clampCommand(CRUISE_SPEED + correction)};
}

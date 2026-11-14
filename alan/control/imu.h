#pragma once

// MPU6050 gyro, used to track heading (which way the robot faces).
// Mount it flat, chip side up: turning left (counterclockwise seen from
// above) then reads as positive.
namespace imu {
    // Starts I2C and wakes the chip. Returns false if nothing answers.
    bool begin();

    // Measures the gyro's zero offset. The robot must be completely still.
    // Takes about 1 second and blocks, so only call it from setup().
    void calibrate();

    // Reads the gyro and adds the rotation since the last call to the
    // heading. Call it every loop, at least every 20 ms.
    void update();

    float headingDeg();                     // -180..180, counterclockwise positive
    float yawRateDps();                     // latest turn rate, degrees per second
    void resetHeading(float deg = 0.0f);
}

#include <Arduino.h>
#include <Wire.h>
#include <math.h>
#include "config.h"
#include "imu.h"
#include "pose.h"

namespace {
    const uint8_t MPU_ADDR = 0x68;        // 0x69 if the module's AD0 pin is tied to 3.3 V

    // MPU6050 registers (numbers from the datasheet's register map)
    const uint8_t REG_CONFIG      = 0x1A;
    const uint8_t REG_GYRO_CONFIG = 0x1B;
    const uint8_t REG_GYRO_ZOUT_H = 0x47;
    const uint8_t REG_PWR_MGMT_1  = 0x6B;

    // At the +/-500 deg/s range, 65.5 raw units = 1 deg/s. The finer
    // +/-250 range could be exceeded by a fast turn in place.
    const float LSB_PER_DPS = 65.5f;

    // Turn rates smaller than this are treated as noise and ignored,
    // which stops the heading creeping while the robot sits still.
    const float NOISE_DPS = 0.5f;

    float biasRaw = 0.0f;     // gyro reading when perfectly still
    float heading = 0.0f;
    float rate = 0.0f;
    uint32_t lastMicros = 0;

    void writeReg(uint8_t reg, uint8_t value) {
        Wire.beginTransmission(MPU_ADDR);
        Wire.write(reg);
        Wire.write(value);
        Wire.endTransmission();
    }

    int16_t readGyroZRaw() {
        Wire.beginTransmission(MPU_ADDR);
        Wire.write(REG_GYRO_ZOUT_H);
        Wire.endTransmission(false);              // false: keep the bus for the read
        Wire.requestFrom(MPU_ADDR, (uint8_t)2);
        // Two separate reads on purpose: in (Wire.read() << 8) | Wire.read()
        // C++ doesn't guarantee which read happens first.
        uint8_t high = Wire.read();
        uint8_t low  = Wire.read();
        return static_cast<int16_t>((high << 8) | low);
    }
}

bool imu::begin() {
    Wire.begin(PIN_IMU_SDA, PIN_IMU_SCL);
    Wire.setClock(400000);

    Wire.beginTransmission(MPU_ADDR);
    if (Wire.endTransmission() != 0) return false;   // nothing answered at 0x68

    writeReg(REG_PWR_MGMT_1, 0x01);   // wake up, clock from the gyro (more stable)
    writeReg(REG_CONFIG, 0x03);       // ~44 Hz low-pass filter: smooths motor vibration
    writeReg(REG_GYRO_CONFIG, 0x08);  // +/-500 deg/s range
    delay(100);                       // let it settle (setup only)

    lastMicros = micros();
    return true;
}

void imu::calibrate() {
    const int SAMPLES = 500;
    long sum = 0;
    for (int i = 0; i < SAMPLES; i++) {
        sum += readGyroZRaw();
        delay(2);
    }
    biasRaw = static_cast<float>(sum) / SAMPLES;
    heading = 0.0f;
    lastMicros = micros();
}

void imu::update() {
    uint32_t now = micros();
    float dt = (now - lastMicros) * 1e-6f;   // seconds since the last update
    lastMicros = now;

    rate = (readGyroZRaw() - biasRaw) / LSB_PER_DPS;
    if (fabsf(rate) < NOISE_DPS) rate = 0.0f;

    heading = wrapDeg(heading + rate * dt);
}

float imu::headingDeg() { return heading; }
float imu::yawRateDps() { return rate; }
void imu::resetHeading(float deg) { heading = wrapDeg(deg); }

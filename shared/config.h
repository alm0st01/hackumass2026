#pragma once
#include <stdint.h>

const uint8_t NUM_ROBOTS = 1;

#ifndef ROBOT_ID
#define ROBOT_ID 1
#endif


// Pins: one block per board, chosen by a -D flag in platformio.ini.
// Motor driver: L298N or L293D. Both use EN (PWM speed) + IN1/IN2 (direction).
//
// L298N wiring: one motor per channel, never two motors on the same pair.
//   Channel A = LEFT motor:  wires on OUT1 + OUT2, controlled by ENA, IN1, IN2
//   Channel B = RIGHT motor: wires on OUT3 + OUT4, controlled by ENB, IN3, IN4
// Pull the ENA/ENB jumper caps off and wire each EN pin with a single jumper
// to the pin in line with IN1-IN4. The other header pin is 5 V: leave it
// empty, since 5 V on an ESP32 pin can damage it.

#ifdef BOARD_S3
// Freenove ESP32-S3 (temporary dev board).
// Avoids the camera pins (4-13, 15-18), flash/PSRAM (26-37), USB (19, 20),
// serial (43, 44), strapping pins (0, 3, 45, 46) and the RGB LED (48).
const int PIN_LEFT_EN   = 14;    // L298N ENA
const int PIN_LEFT_IN1  = 21;    // L298N IN1
const int PIN_LEFT_IN2  = 47;    // L298N IN2
const int PIN_RIGHT_EN  = 41;    // L298N ENB
const int PIN_RIGHT_IN1 = 42;    // L298N IN3
const int PIN_RIGHT_IN2 = 2;     // L298N IN4 (also lights the onboard LED)
const int PIN_DISTANCE  = 1;     // analog (ADC1)
const int PIN_IMU_SDA   = 39;    // MPU6050 I2C data  (39/40 are SD-card pins; no SD card used)
const int PIN_IMU_SCL   = 40;    // MPU6050 I2C clock
#else
// Regular ESP32 (final robots)
const int PIN_LEFT_EN   = 25;
const int PIN_LEFT_IN1  = 26;
const int PIN_LEFT_IN2  = 27;
const int PIN_RIGHT_EN  = 4;
const int PIN_RIGHT_IN1 = 16;
const int PIN_RIGHT_IN2 = 17;
const int PIN_DISTANCE  = 34;    // IR distance sensor (analog; must be GPIO 32-39)
const int PIN_IMU_SDA   = 21;    // MPU6050 I2C (the classic ESP32's usual I2C pins)
const int PIN_IMU_SCL   = 22;
#endif

// Drive constants
const int MOTOR_MIN_PWM = 90;
const int MOTOR_MAX_PWM = 255;
const int CRUISE_SPEED = 180;
const int TURN_SPEED = 150;

// Control loop
const uint32_t CONTROL_PERIOD_MS = 20;
const uint32_t COMMAND_TIMEOUT_MS = 300;
const float STEER_GAIN = 2.0f;           // motor command per degree of heading error
const float ARRIVE_RADIUS_CM = 3.0f;
const float TURN_IN_PLACE_DEG = 45.0f;   // turn on the spot when heading error is above this...
const float TURN_EXIT_DEG = 20.0f;       // ...until it drops below this, then drive

// Sensors
const int OBSTACLE_THRESHOLD = 2000;

// Robot geometry?
const float WHEEL_DIAMETER_CM = 6.5f;
const float WHEEL_SPACING_CM  = 12.0f;

// Serial
const uint32_t SERIAL_BAUD = 115200;
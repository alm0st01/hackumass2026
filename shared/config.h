#pragma once
#include <stdint.h>

const uint8_t NUM_ROBOTS = 1;

#ifndef ROBOT_ID
#define ROBOT_ID 1
#endif


// Pins: one block per board, chosen by a -D flag in platformio.ini.
// Motor driver: L298N or L293D. Both use EN (PWM speed) + IN1/IN2 (direction).
// On the L298N, pull the ENA/ENB jumper caps off so the EN pins get our PWM.

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
#else
// Regular ESP32 (final robots)
const int PIN_LEFT_EN   = 25;
const int PIN_LEFT_IN1  = 26;
const int PIN_LEFT_IN2  = 27;
const int PIN_RIGHT_EN  = 4;
const int PIN_RIGHT_IN1 = 16;
const int PIN_RIGHT_IN2 = 17;
const int PIN_DISTANCE  = 34;    // IR distance sensor (analog; must be GPIO 32-39)
#endif

// Drive constants
const int MOTOR_MIN_PWM = 90;
const int MOTOR_MAX_PWM = 255;
const int CRUISE_SPEED = 180;
const int TURN_SPEED = 150;

// Control loop
const uint32_t CONTROL_PERIOD_MS = 20;
const uint32_t COMMAND_TIMEOUT_MS = 300;
const float STEER_GAIN = 2.0f;
const float ARRIVE_RADIUS_CM = 3.0f;

// Sensors
const int OBSTACLE_THRESHOLD = 2000;

// Robot geometry?
const float WHEEL_DIAMETER_CM = 6.5f;
const float WHEEL_SPACING_CM  = 12.0f;

// Serial
const uint32_t SERIAL_BAUD = 115200;
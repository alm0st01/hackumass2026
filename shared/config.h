#pragma once
#include <stdint.h>

const uint8_t NUM_ROBOTS = 1;

#ifndef ROBOT_ID
#define ROBOT_ID 1
#endif


// Pins and board-specific values: one block per board.
// The board is chosen by a -D flag in platformio.ini (BOARD_UNO, BOARD_S3);
// with no flag (bot envs, simulator) you get the regular ESP32.

#if defined(BOARD_UNO)
// Arduino Uno + Adafruit Motor Shield V1 (or L293D clone).
// Motors are addressed by shield port (M1-M4), not pins. The shield itself
// uses pins 3, 4, 5, 6, 7, 8, 11, 12 (and 9, 10 for servos).
// Free for us: A0-A5, 2, 13.
const uint8_t MOTOR_PORT_LEFT  = 3;    // M3
const uint8_t MOTOR_PORT_RIGHT = 4;    // M4
const int PIN_DISTANCE  = 14;          // A0
const int OBSTACLE_THRESHOLD = 500;    // 10-bit ADC (0-1023)

#elif defined(BOARD_S3)
// ESP32-S3 dev board (temporary)
const int PIN_LEFT_EN   = 4;
const int PIN_LEFT_IN1  = 5;
const int PIN_LEFT_IN2  = 6;
const int PIN_RIGHT_EN  = 7;
const int PIN_RIGHT_IN1 = 15;
const int PIN_RIGHT_IN2 = 16;
const int PIN_DISTANCE  = 1;
const int OBSTACLE_THRESHOLD = 2000;   // 12-bit ADC (0-4095)

#else
// Regular ESP32 (final robots)
const int PIN_LEFT_EN   = 25;
const int PIN_LEFT_IN1  = 26;
const int PIN_LEFT_IN2  = 27;
const int PIN_RIGHT_EN  = 4;
const int PIN_RIGHT_IN1 = 16;
const int PIN_RIGHT_IN2 = 17;
const int PIN_DISTANCE  = 34;          // IR distance sensor (analog; must be GPIO 32-39)
const int OBSTACLE_THRESHOLD = 2000;   // 12-bit ADC (0-4095)
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

// Robot geometry?
const float WHEEL_DIAMETER_CM = 6.5f;
const float WHEEL_SPACING_CM  = 12.0f;

// Serial
const uint32_t SERIAL_BAUD = 115200;
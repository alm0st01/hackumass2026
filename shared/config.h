#include <stdint.h>

const uint8_t NUM_ROBOTS = 1;

#ifndef ROBOT_ID
#define ROBOT_ID 1
#endif


// Motor pins

#ifdef BOARD_S3
// ESP32-S3 dev board (temporary)
const int PIN_LEFT_EN   = 4;
const int PIN_LEFT_IN1  = 5;
const int PIN_LEFT_IN2  = 6;
const int PIN_RIGHT_EN  = 7;
const int PIN_RIGHT_IN1 = 15;
const int PIN_RIGHT_IN2 = 16;
const int PIN_DISTANCE  = 1;
#else
const int PIN_LEFT_EN = 25;
const int PIN_LEFT_IN1 = 26;
const int PIN_LEFT_IN2 = 27;
const int PIN_RIGHT_EN = 4;
const int PIN_RIGHT_IN1 = 16;
const int PIN_RIGHT_IN2 = 17;
#endif 

// Sensor pins
const int PIN_DISTANCE = 34;       // IR distance sensor (analog; must be GPIO 32-39)

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
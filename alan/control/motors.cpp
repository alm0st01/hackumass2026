#include <Arduino.h>
#include "config.h"
#include "motors.h"

#ifdef BOARD_UNO
#include <AFMotor.h>   // Adafruit Motor Shield V1 library
#endif

namespace {
    const bool INVERT_LEFT = false;
    const bool INVERT_RIGHT = false;

    const float LEFT_MULTIPLIER = 1.00f;
    const float RIGHT_MULTIPLIER = 1.00f;

    int applyMinPwm(int speed) {
        if (speed == 0) return 0;
        int mag = map(abs(speed), 1, 255, MOTOR_MIN_PWM, MOTOR_MAX_PWM);
        return speed > 0 ? mag : -mag;
    }

#ifdef BOARD_UNO
    // Uno + Motor Shield V1: the library talks to the shield for us.
    AF_DCMotor leftMotor(MOTOR_PORT_LEFT);
    AF_DCMotor rightMotor(MOTOR_PORT_RIGHT);

    void driveMotors(AF_DCMotor& motor, int speed, bool invert) {
        if (invert) speed = -speed;

        motor.setSpeed(abs(speed));
        if (speed > 0)      motor.run(FORWARD);
        else if (speed < 0) motor.run(BACKWARD);
        else                motor.run(RELEASE);   // coast
    }
#else
    // ESP32 + bare L293D/L298N: drive the pins directly.
    void driveMotors(int pinNum, int input1, int input2, int speed, bool invert) {
        if (invert) speed = -speed;

        digitalWrite(input1, speed > 0 ? HIGH : LOW);
        digitalWrite(input2, speed < 0 ? HIGH : LOW);

        analogWrite(pinNum, abs(speed));
    }
#endif
}

void motors::begin() { // init motors
#ifndef BOARD_UNO
    const int pins[] = {PIN_LEFT_EN, PIN_LEFT_IN1, PIN_LEFT_IN2, PIN_RIGHT_EN, PIN_RIGHT_IN1, PIN_RIGHT_IN2};
    for (int pin : pins) pinMode(pin, OUTPUT);
#endif
    // On the Uno, the AF_DCMotor objects above set up the shield themselves.

    stop();
}


void motors::setSpeeds(int left, int right) {
    left = constrain(left, -255, 255);
    right = constrain(right, -255, 255);

    left = applyMinPwm(static_cast<int>(left * LEFT_MULTIPLIER));
    right = applyMinPwm(static_cast<int>(right * RIGHT_MULTIPLIER));

#ifdef BOARD_UNO
    driveMotors(leftMotor,  left,  INVERT_LEFT);
    driveMotors(rightMotor, right, INVERT_RIGHT);
#else
    driveMotors(PIN_LEFT_EN,  PIN_LEFT_IN1,  PIN_LEFT_IN2, left,  INVERT_LEFT);
    driveMotors(PIN_RIGHT_EN, PIN_RIGHT_IN1, PIN_RIGHT_IN2, right, INVERT_RIGHT);
#endif
}

void motors::stop() {
    setSpeeds(0,0);
}

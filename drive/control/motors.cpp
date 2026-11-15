#include <Arduino.h>
#include "config.h"
#include "motors.h"

namespace {
    const bool INVERT_LEFT = false;
    const bool INVERT_RIGHT = false;

    const float LEFT_MULTIPLIER = 1.00f;
    const float RIGHT_MULTIPLIER = 1.00f;

    void driveMotors(int pinNum, int input1, int input2, int speed, bool invert) {
        if (invert) speed = -speed;
        speed = constrain(speed, -255, 255);
        

        digitalWrite(input1, speed > 0 ? HIGH : LOW);
        digitalWrite(input2, speed < 0 ? HIGH : LOW);

        analogWrite(pinNum, abs(speed));
    }

    int applyMinPwm(int speed) {
    if (speed == 0) return 0;
    int mag = map(abs(speed), 1, 255, MOTOR_MIN_PWM, MOTOR_MAX_PWM);
    return speed > 0 ? mag : -mag;
}
}

void motors::begin() { // init motors
    const int pins[] = {PIN_LEFT_EN, PIN_LEFT_IN1, PIN_LEFT_IN2, PIN_RIGHT_EN, PIN_RIGHT_IN1, PIN_RIGHT_IN2};
    for (int pin : pins) pinMode(pin, OUTPUT);

    stop();
}


void motors::setSpeeds(int left, int right) {
    left = constrain(left, -255, 255);
    right = constrain(right, -255, 255);

    left = applyMinPwm(static_cast<int>(left * LEFT_MULTIPLIER));
    right = applyMinPwm(static_cast<int>(right * RIGHT_MULTIPLIER));

    driveMotors(PIN_LEFT_EN,  PIN_LEFT_IN1,  PIN_LEFT_IN2, left,  INVERT_LEFT);
    driveMotors(PIN_RIGHT_EN, PIN_RIGHT_IN1, PIN_RIGHT_IN2, right, INVERT_RIGHT);
}

void motors::stop() {
    setSpeeds(0,0);
}
// Motor test: both motors forward for 10 s, stop for 2 s, repeat forever.
// Prop the robot up so the wheels/treads are off the ground.
//   pio run -e motor_test -t upload      (regular ESP32; motor_test_s3 for the S3)
//   pio device monitor
#include <Arduino.h>
#include "config.h"
#include "motors.h"

const int TEST_SPEED = 200;          // -255..255; change to try other speeds
const uint32_t RUN_MS = 10000;
const uint32_t REST_MS = 2000;

void setup() {
    Serial.begin(SERIAL_BAUD);
    motors::begin();
#ifdef BOARD_S3
    rgbLedWrite(48, 0, 0, 0);        // onboard RGB LED off, so motor noise can't flicker it
#endif
    delay(1000);                     // time to open the serial monitor
    Serial.println("motor_test: 10 s forward, 2 s stop, repeating");
}

void loop() {
    Serial.printf("forward at %d for %lu s\n", TEST_SPEED, RUN_MS / 1000);
    motors::setSpeeds(TEST_SPEED, TEST_SPEED);
    delay(RUN_MS);                   // fine in a test program

    Serial.printf("stop for %lu s\n", REST_MS / 1000);
    motors::stop();
    delay(REST_MS);
}

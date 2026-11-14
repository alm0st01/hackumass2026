#include <Arduino.h>
#include "config.h"
#include "motors.h"

void setup() {
  Serial.begin(SERIAL_BAUD);
  motors::begin();
}

void loop() {
}

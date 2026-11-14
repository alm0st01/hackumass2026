#include <Arduino.h>
#include "config.h"
#include "motors.h"

void setup() {
  Serial.begin(SERIAL_BAUD);
  motors::begin();
}

void loop() {
  Serial.println("forward");   motors::setSpeeds(255, 255);   delay(1500);
  Serial.println("stop");      motors::stop();                delay(1000);
  Serial.println("backward");  motors::setSpeeds(-255, -255); delay(1500);
  Serial.println("stop");      motors::stop();                delay(1000);
  Serial.println("spin left"); motors::setSpeeds(-255, 255);  delay(1500);
  Serial.println("stop");      motors::stop();                delay(1000);
}

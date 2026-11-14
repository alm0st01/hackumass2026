#include <Arduino.h>
#include "config.h"
#include "motors.h"

void setup() {
  Serial.begin(SERIAL_BAUD);
  motors::begin();
}

void loop() {
  Serial.println("forward");   motors::setSpeeds(150, 150);   delay(1500);
  Serial.println("stop");      motors::stop();                delay(1000);
  Serial.println("backward");  motors::setSpeeds(-150, -150); delay(1500);
  Serial.println("stop");      motors::stop();                delay(1000);
  Serial.println("spin left"); motors::setSpeeds(-150, 150);  delay(1500);
  Serial.println("stop");      motors::stop();                delay(1000);
}

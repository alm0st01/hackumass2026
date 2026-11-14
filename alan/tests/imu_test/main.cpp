// IMU check: prints the heading while you turn the board by hand.
//   pio run -e imu_test -t upload
//   pio device monitor
#include <Arduino.h>
#include <Wire.h>
#include "config.h"
#include "imu.h"

void setup() {
    Serial.begin(SERIAL_BAUD);
    delay(1500);   // time to open the serial monitor

    if (!imu::begin()) {
        Serial.println("MPU6050 not found at 0x68. Devices on the I2C bus:");
        int found = 0;
        for (uint8_t addr = 1; addr < 127; addr++) {
            Wire.beginTransmission(addr);
            if (Wire.endTransmission() == 0) {
                Serial.printf("  0x%02X\n", addr);
                found++;
            }
        }
        if (found == 0) Serial.println("  none. Check VCC/GND, and that SDA/SCL aren't swapped.");
        while (true) delay(1000);
    }

    Serial.println("Found MPU6050. Calibrating: keep it completely still...");
    imu::calibrate();
    Serial.println("Done. Turn it by hand: left (counterclockwise) should go positive.");
}

void loop() {
    imu::update();

    static uint32_t lastPrint = 0;
    if (millis() - lastPrint >= 200) {
        lastPrint = millis();
        Serial.printf("heading %7.1f deg   turn rate %7.1f deg/s\n",
                      imu::headingDeg(), imu::yawRateDps());
    }
    delay(5);   // fine in a test program
}

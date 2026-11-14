// ESP32 robot firmware: drives the motors on commands from the Raspberry Pi over USB serial.
// Protocol: shared/serial_protocol.md
//
// Safety, handled here so it works even if the Pi crashes:
//   - motors stop if no command arrives for COMMAND_TIMEOUT_MS
//   - forward motion stops if the IR distance sensor sees something closer than OBSTACLE_THRESHOLD
#include <Arduino.h>
#include <stdlib.h>
#include <string.h>
#include "config.h"
#include "motors.h"

namespace {

const uint32_t STATUS_PERIOD_MS = 100;
const size_t MAX_LINE = 64;

char line[MAX_LINE];
size_t lineLength = 0;
bool lineTooLong = false;

int commandedLeft = 0;
int commandedRight = 0;
bool gotCommand = false;  // false until the first command after boot
uint32_t lastCommandMs = 0;
bool obstacleStopEnabled = true;

int appliedLeft = 0;
int appliedRight = 0;
int distanceReading = 0;
const char* state = "WAITING";

uint32_t lastControlMs = 0;
uint32_t lastStatusMs = 0;

// Parses a whole number in [-255, 255]. Returns false if the text isn't one.
bool parseSpeed(const char* text, int& out) {
  if (text == nullptr) return false;
  char* end = nullptr;
  long value = strtol(text, &end, 10);
  if (end == text || *end != '\0' || value < -255 || value > 255) return false;
  out = static_cast<int>(value);
  return true;
}

void handleCommand(char* text) {
  char* command = strtok(text, " \t");
  if (command == nullptr) return;  // empty line

  if (strcasecmp(command, "DRIVE") == 0) {
    int left, right;
    char* a = strtok(nullptr, " \t");
    char* b = strtok(nullptr, " \t");
    if (!parseSpeed(a, left) || !parseSpeed(b, right) || strtok(nullptr, " \t") != nullptr) {
      Serial.println("ERR DRIVE needs two numbers -255..255");
      return;
    }
    commandedLeft = left;
    commandedRight = right;
    gotCommand = true;
    lastCommandMs = millis();
  } else if (strcasecmp(command, "STOP") == 0) {
    commandedLeft = 0;
    commandedRight = 0;
    gotCommand = true;
    lastCommandMs = millis();
    Serial.println("OK STOP");
  } else if (strcasecmp(command, "PING") == 0) {
    Serial.println("PONG");
  } else if (strcasecmp(command, "OBSTACLE") == 0) {
    char* value = strtok(nullptr, " \t");
    if (value != nullptr && (strcmp(value, "0") == 0 || strcmp(value, "1") == 0)) {
      obstacleStopEnabled = value[0] == '1';
      Serial.println(obstacleStopEnabled ? "OK OBSTACLE 1" : "OK OBSTACLE 0");
    } else {
      Serial.println("ERR OBSTACLE needs 0 or 1");
    }
  } else {
    Serial.println("ERR unknown command");
  }
}

// Reads whatever has arrived without waiting, and handles each complete line.
void readSerial() {
  while (Serial.available() > 0) {
    char c = static_cast<char>(Serial.read());
    if (c == '\r') continue;
    if (c == '\n') {
      if (lineTooLong) {
        Serial.println("ERR line too long");
      } else {
        line[lineLength] = '\0';
        handleCommand(line);
      }
      lineLength = 0;
      lineTooLong = false;
    } else if (lineLength < MAX_LINE - 1) {
      line[lineLength++] = c;
    } else {
      lineTooLong = true;  // keep reading until the newline, then report it
    }
  }
}

void updateMotors() {
  distanceReading = analogRead(PIN_DISTANCE);

  bool timedOut = gotCommand && millis() - lastCommandMs > COMMAND_TIMEOUT_MS;
  bool movingForward = commandedLeft + commandedRight > 0;  // turning in place and reversing are allowed
  bool blocked = obstacleStopEnabled && movingForward && distanceReading >= OBSTACLE_THRESHOLD;

  if (!gotCommand) {
    state = "WAITING";
  } else if (timedOut) {
    state = "TIMEOUT";
  } else if (blocked) {
    state = "OBSTACLE";
  } else {
    state = "OK";
  }

  bool drive = strcmp(state, "OK") == 0;
  int left = drive ? commandedLeft : 0;
  int right = drive ? commandedRight : 0;
  if (left != appliedLeft || right != appliedRight) {
    motors::setSpeeds(left, right);
    appliedLeft = left;
    appliedRight = right;
  }
}

void sendStatus() {
  Serial.printf("STATUS %d %d %d %s\n", appliedLeft, appliedRight, distanceReading, state);
}

}  // namespace

void setup() {
  Serial.begin(SERIAL_BAUD);
  motors::begin();  // motors start stopped
  Serial.println();  // end any boot-ROM noise on the line
  Serial.println("READY");
}

void loop() {
  readSerial();

  uint32_t now = millis();
  if (now - lastControlMs >= CONTROL_PERIOD_MS) {
    lastControlMs = now;
    updateMotors();
  }
  if (now - lastStatusMs >= STATUS_PERIOD_MS) {
    lastStatusMs = now;
    sendStatus();
  }
}

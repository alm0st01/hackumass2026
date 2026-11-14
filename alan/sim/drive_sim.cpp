// Laptop simulator for the drive-to-a-point controller (alan/control/drive).
// Fakes a two-wheeled robot and an overhead camera so the controller can be
// tuned before the chassis exists.
//
// Build and run from the repo root:
//   g++ -std=c++17 -Wall -I shared -I alan/control alan/control/drive.cpp alan/sim/drive_sim.cpp -o drive_sim && ./drive_sim
//   ./drive_sim -v    also prints a trace every 0.5 s

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <random>
#include <string>
#include <vector>

#include "config.h"
#include "drive.h"

namespace {

// ---- Simulated robot. Guesses: measure the real robot and update these. ----
const float MAX_WHEEL_SPEED_CM_S = 30.0f;   // wheel speed at command 255
const float MOTOR_LAG_S          = 0.15f;   // how long a wheel takes to (mostly) reach a new speed
const float RIGHT_WHEEL_SCALE    = 0.95f;   // right side 5% weaker, like a real robot

// ---- Simulated camera ----
const uint32_t VISION_PERIOD_MS = 100;      // new pose 10 times a second
const float    VISION_NOISE_CM  = 0.5f;
const float    VISION_NOISE_DEG = 1.5f;

const uint32_t PHYSICS_STEP_MS     = 5;
const uint32_t WAYPOINT_TIMEOUT_MS = 15000;
const float    PI_F = 3.14159265f;

struct Point { float x, y; };

struct Scenario {
    const char* name;
    Pose start;
    std::vector<Point> waypoints;
};

struct SimRobot {
    Pose pose;              // where the robot really is
    float vLeft = 0.0f;     // current wheel speeds, cm/s
    float vRight = 0.0f;
};

// Advances the robot by dt seconds under the given motor commands.
void stepPhysics(SimRobot& r, const WheelCommand& cmd, float dt) {
    // Wheels ease toward their commanded speed; motors can't change speed instantly.
    float targetLeft  = cmd.left  / 255.0f * MAX_WHEEL_SPEED_CM_S;
    float targetRight = cmd.right / 255.0f * MAX_WHEEL_SPEED_CM_S * RIGHT_WHEEL_SCALE;
    float blend = dt / (MOTOR_LAG_S + dt);
    r.vLeft  += (targetLeft  - r.vLeft)  * blend;
    r.vRight += (targetRight - r.vRight) * blend;

    // Differential drive: the average wheel speed moves it, the difference turns it.
    float v     = (r.vLeft + r.vRight) / 2.0f;                 // cm/s
    float omega = (r.vRight - r.vLeft) / WHEEL_SPACING_CM;     // rad/s, counterclockwise
    float heading = r.pose.headingDeg * PI_F / 180.0f;
    r.pose.x += v * cosf(heading) * dt;
    r.pose.y += v * sinf(heading) * dt;
    r.pose.headingDeg = wrapDeg(r.pose.headingDeg + omega * dt * 180.0f / PI_F);
}

// Draws the path as text. Terminal characters are about twice as tall as they
// are wide, so one row covers twice the distance of one column.
void plotPath(const std::vector<Point>& path, const Scenario& s, const Pose& end) {
    const int MAX_COLS = 60, MAX_ROWS = 20;

    float minX = s.start.x, maxX = s.start.x, minY = s.start.y, maxY = s.start.y;
    auto grow = [&](float x, float y) {
        minX = std::min(minX, x); maxX = std::max(maxX, x);
        minY = std::min(minY, y); maxY = std::max(maxY, y);
    };
    for (const Point& p : path) grow(p.x, p.y);
    for (const Point& w : s.waypoints) grow(w.x, w.y);
    minX -= 5; maxX += 5; minY -= 5; maxY += 5;

    float cmPerCol = std::max((maxX - minX) / (MAX_COLS - 1),
                              (maxY - minY) / (2.0f * (MAX_ROWS - 1)));
    int cols = static_cast<int>((maxX - minX) / cmPerCol) + 1;
    int rows = static_cast<int>((maxY - minY) / (2.0f * cmPerCol)) + 1;
    std::vector<std::string> grid(rows, std::string(cols, ' '));

    auto put = [&](float x, float y, char c) {
        int col = static_cast<int>(lroundf((x - minX) / cmPerCol));
        int row = rows - 1 - static_cast<int>(lroundf((y - minY) / (2.0f * cmPerCol)));
        if (col >= 0 && col < cols && row >= 0 && row < rows) grid[row][col] = c;
    };
    for (const Point& p : path) put(p.x, p.y, '.');
    for (size_t i = 0; i < s.waypoints.size(); i++) put(s.waypoints[i].x, s.waypoints[i].y, '1' + i);
    put(s.start.x, s.start.y, 'S');
    put(end.x, end.y, '@');

    printf("  +%s+\n", std::string(cols, '-').c_str());
    for (const std::string& line : grid) printf("  |%s|\n", line.c_str());
    printf("  +%s+\n", std::string(cols, '-').c_str());
    printf("  S start, 1-9 waypoints, @ end, . path   (1 column = %.1f cm)\n\n", cmPerCol);
}

bool runScenario(const Scenario& s, bool verbose, std::mt19937& rng) {
    std::normal_distribution<float> noiseCm(0.0f, VISION_NOISE_CM);
    std::normal_distribution<float> noiseDeg(0.0f, VISION_NOISE_DEG);

    SimRobot robot;
    robot.pose = s.start;
    DriveController controller;
    Pose seen = s.start;                 // what the camera last reported
    WheelCommand cmd = {0, 0};
    std::vector<Point> path;
    size_t wp = 0;
    uint32_t t = 0, wpStartMs = 0;
    bool ok = true;

    printf("=== %s ===\n", s.name);
    while (wp < s.waypoints.size()) {
        if (t % VISION_PERIOD_MS == 0) {
            seen.x = robot.pose.x + noiseCm(rng);
            seen.y = robot.pose.y + noiseCm(rng);
            seen.headingDeg = wrapDeg(robot.pose.headingDeg + noiseDeg(rng));
        }

        if (t % CONTROL_PERIOD_MS == 0) {
            const Point& goal = s.waypoints[wp];
            cmd = controller.update(seen, goal.x, goal.y);

            if (verbose && t % 500 == 0) {
                printf("  t=%5.2fs  x=%6.1f y=%6.1f hdg=%7.1f  cmd L=%4d R=%4d\n",
                       t / 1000.0f, robot.pose.x, robot.pose.y, robot.pose.headingDeg,
                       cmd.left, cmd.right);
            }
            if (controller.arrived()) {
                float miss = std::hypot(goal.x - robot.pose.x, goal.y - robot.pose.y);
                printf("  reached %zu (%.0f, %.0f) at %5.2f s, true distance %.1f cm\n",
                       wp + 1, goal.x, goal.y, t / 1000.0f, miss);
                wp++;
                wpStartMs = t;
            }
        }

        if (t - wpStartMs > WAYPOINT_TIMEOUT_MS) {
            printf("  TIMED OUT going to waypoint %zu\n", wp + 1);
            ok = false;
            break;
        }

        stepPhysics(robot, cmd, PHYSICS_STEP_MS / 1000.0f);
        if (t % 50 == 0) path.push_back({robot.pose.x, robot.pose.y});
        t += PHYSICS_STEP_MS;
    }

    plotPath(path, s, robot.pose);
    return ok;
}

}  // namespace

int main(int argc, char** argv) {
    bool verbose = argc > 1 && strcmp(argv[1], "-v") == 0;
    std::mt19937 rng(42);   // fixed seed: same "random" noise every run, so runs compare fairly

    std::vector<Scenario> scenarios = {
        {"Straight ahead",                      {0, 0, 0}, {{100, 0}}},
        {"Target behind (turns in place first)", {0, 0, 0}, {{-60, 0}}},
        {"Target off to the side",              {0, 0, 0}, {{40, 60}}},
        {"Square, 60 cm sides",                 {0, 0, 0}, {{60, 0}, {60, 60}, {0, 60}, {0, 0}}},
    };

    int passed = 0;
    for (const Scenario& s : scenarios) passed += runScenario(s, verbose, rng) ? 1 : 0;
    printf("%d/%zu scenarios reached every waypoint\n", passed, scenarios.size());
    return passed == static_cast<int>(scenarios.size()) ? 0 : 1;
}

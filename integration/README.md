# integration: putting the robot together

```
              ROBOT                                                 BASE
 ┌─────────────────────────────────────────────┐
 │ Logitech camera ─USB─┐                      │
 │                 Raspberry Pi: pi/main.py ─USB─ Heltec ~~LoRa~~ Heltec ─USB─ Laptop: piku/.../base.py
 │                      │                      │
 │            USB serial│ DRIVE / STATUS        │
 │                      ▼                      │
 │   ESP32: firmware/main.cpp ── L298N ── motors│
 │          + IR distance sensor               │
 └─────────────────────────────────────────────┘
```

| Part | Runs on | Code | Owner |
|---|---|---|---|
| Robot main program | Raspberry Pi | `integration/pi/main.py` | |
| Radio messages (Meshtastic) | Pi + laptop | `piku/meshtastic-testing/` | Piku |
| Person / AprilTag detection | Pi | `integration/pi/vision.py` (same settings as `adi/person.py`, `adi/main.py`) | Adi |
| Motor control + safety stops | ESP32 | `integration/firmware/main.cpp`, `alan/control/` | Alan |
| Pi ↔ ESP32 message format | | `shared/serial_protocol.md` | |

## What the robot does

`pi/main.py` loops 20 times a second. Detection runs in a background thread, so a slow camera
or a slow YOLO never delays the radio or the motor commands.

| State | Behavior | Leaves on |
|---|---|---|
| `IDLE` | Motors off. Waiting. | `SCAN` or `RESUME` from the base |
| `EXPLORING` | Drives forward. When the ESP32 reports `OBSTACLE`, turns in place for 0.6–1.4 s in a random direction. | target confirmed, `STOP`, `HOME` |
| `FOUND` | Motors off. Sends a `DETECTION` to the base (Piku's code resends it until the base confirms). | `RESUME` / `SCAN` |
| `STOPPED` | Motors off. | `RESUME` / `SCAN` |

A target counts as found after 5 frames in a row (`--confirm-frames`). The state goes out in
every heartbeat, so `status` on the base shows it.

**Safety is on the ESP32, not the Pi.** The ESP32 stops the motors if the Pi stops sending
commands for 300 ms (crash, frozen program, unplugged cable). It also refuses to drive forward
when the distance sensor sees something close. See `shared/serial_protocol.md`.

## 1. Flash the ESP32

Install PlatformIO (`pip install platformio`, or the VS Code extension), plug in the ESP32,
and from the repo root:

```sh
pio run -e bot1 -t upload       # regular ESP32 (esp32dev)
pio run -e s3test -t upload     # the temporary ESP32-S3 dev board
```

Test it by hand before involving the Pi:

```sh
pio device monitor -b 115200 --echo --eol LF
```

You should see `READY`, then a `STATUS ...` line every 100 ms. Type `DRIVE 150 150` with
the wheels off the ground. They should spin for 0.3 s and stop with `TIMEOUT`. That stop
is the safety timeout working.

## 2. Set up the Raspberry Pi

1. Install **Raspberry Pi OS (64-bit)** with Raspberry Pi Imager. In its settings, enable SSH
   and set up Wi-Fi so you can work on the Pi from your laptop (only needed for setup).
2. Copy the repo over (`git clone`, or `scp -r`).
3. Install the Python packages in a virtual environment. Pi OS refuses `pip install` without one.
   ```sh
   cd hackumass2026/integration/pi
   python3 -m venv ~/sar
   source ~/sar/bin/activate
   pip install -r requirements.txt     # ultralytics pulls in PyTorch; this takes a while
   sudo usermod -aG dialout $USER      # serial port access; log out and back in after
   ```
4. Prepare the Heltec as in `piku/meshtastic-testing/README.md` (region, channel URL, and
   `SECRET` in `common.py`, which must match the base).

### Find the serial ports

The Pi has **two USB serial devices**: the Heltec and the ESP32. Both often use the same
CP210x USB chip, so Meshtastic's auto-detect can grab the ESP32. Always give both ports, using
the stable names under `/dev/serial/by-id/` (`/dev/ttyUSB0` and `/dev/ttyUSB1` can swap on reboot):

```sh
ls -l /dev/serial/by-id/
# unplug one board, run it again, and see which entry disappeared
```

## 3. Run

On the laptop (Heltec plugged in): `python piku/meshtastic-testing/base.py --port <heltec port>`

On the Pi:

```sh
source ~/sar/bin/activate
cd hackumass2026/integration/pi
python main.py --id 1 \
  --radio-port /dev/serial/by-id/usb-Silicon_Labs_CP2102...-port0 \
  --motor-port /dev/serial/by-id/usb-Silicon_Labs_CP2102...-port0
```

Then on the base, type `scan 1` to start the search, `stop 1` to stop, and `status` for the list.

| Option | Default | Notes |
|---|---|---|
| `--id N` | 1 | unique per robot; 0 is the base |
| `--radio-port` | auto-detect | Heltec port. Give it (see above). |
| `--motor-port` | (required) | ESP32 port |
| `--vision` | `person` | `person` (YOLOv8n), `apriltag`, or `none` |
| `--tag-id` | 0 | AprilTag ID for `--vision apriltag` |
| `--camera` | 0 | camera index, or a video file |
| `--min-confidence` | 0.6 | person detector threshold |
| `--confirm-frames` | 5 | frames in a row needed for a detection |
| `--autostart` | off | start exploring without waiting for `scan` |
| `--no-obstacle-stop` | off | use when no distance sensor is wired up. An unconnected analog pin reads random values that can block forward driving. |
| `--sim-radio` | | Piku's fake radio, instead of `--radio-port` |
| `--no-motors` | | fake motors, instead of `--motor-port` |

YOLO downloads `yolov8n.pt` (6 MB) on its first run, so do one run with internet before
heading out.

### Testing without hardware

On one computer, in two terminals:

```sh
python piku/meshtastic-testing/base.py --sim
python integration/pi/main.py --sim-radio --no-motors --vision person --camera 0
```

Type `scan 1` in the base window and step in front of the camera.

## Tested so far

All on a laptop. **Not yet on a real Pi, ESP32, or Heltec.**

- Firmware builds for `bot1` and `s3test` (PlatformIO).
- Firmware logic, run on the laptop against a fake serial port and motors:
  - `DRIVE` / `STOP` / `PING` / `OBSTACLE` work, and bad commands get `ERR`.
  - The 300 ms timeout stops the motors.
  - The obstacle stop blocks forward driving, but still allows turning and reversing.
- Full chain: `base.py --sim` ↔ `main.py` ↔ that emulated ESP32, with a test video:
  - `scan 1` starts the robot.
  - YOLO finds the person, and the robot stops and reports it. The base shows the alert.
  - `resume 1` and `stop 1` work.
  - An obstacle makes the robot turn.
  - Killing `main.py` with `kill -9` stops the motors within 300 ms.

## Not done yet

- **Search planner.** `EXPLORING` is "forward, turn at obstacles". `alan/search/planner.cpp` is empty.
- **HOME.** The robot doesn't track its position, so `home 1` just stops it.
- **Battery and heading.** The heartbeat always reports battery 100% and heading 0. Nothing measures them yet.
- **Dashboard.** `dat/ui` isn't connected. `base.py` is the base station for now.
- **Speed on a Pi.** YOLOv8n at 320×320 hasn't been timed on a Pi yet. If it's too slow, try
  `--vision apriltag`, which is much lighter.

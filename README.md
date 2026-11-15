# Search mini-bots (HackUMass 2026)

Small ground robots that run standard search-and-rescue patterns, spot a person with a camera,
and radio the find and its estimated position back to a base laptop over LoRa. No GPS, Wi-Fi,
or cell service needed.

```
 Robot:  camera + IMU ── Raspberry Pi 5 ──USB── ESP32 ── L298N ── motors
                              │                   └── IR distance sensor
                            Heltec LoRa (Meshtastic)
                              ┆  radio
 Base:                      Heltec LoRa ──USB── laptop: dashboard (browser)
```

## Where things are

| Folder | What's in it | Owner |
|---|---|---|
| `integration/` | Everything joined up. `pi/main.py` (robot program), `firmware/main.cpp` (ESP32), `dashboard_server.py` / `base_station.py` (base laptop). **Start with `integration/README.md`.** | |
| `shared/` | `config.h` (pins and constants), `serial_protocol.md` (Pi ↔ ESP32 messages) | |
| `drive/` | Motor driver, IMU and drive code for the ESP32; `pi/` runs the motors from the Pi's GPIO instead; tests; pitch brief | Alan |
| `comms/` | LoRa messaging over Meshtastic: signing, ACKs, resends (`meshtastic-testing/`) | Piku |
| `vision/` | Vision: YOLO person and AprilTag scripts, the SARD/NOMAD-trained classifier and its C++ camera app | Adi |
| `dashboard/` | Dashboard web page (`ui/`), served by `integration/dashboard_server.py` | Dat |

## Quick start (no hardware)

```sh
python integration/dashboard_server.py --sim        # then open http://localhost:8000
python integration/pi/main.py --sim-radio --sim --pattern sector --radius 5 --vision person --camera 0
```

Press **Start Search** on the dashboard and step in front of the camera. Setup on real
hardware is in `integration/README.md`. `pio run -e bot1 -t upload` flashes the ESP32.

## How the control loop works

Four loops run at different speeds, each feeding the next:

1. **ESP32 safety loop, 50 times a second.** Applies the motor speeds, reads the distance
   sensor, stops the motors if the Pi goes quiet for 300 ms, and refuses to drive forward into
   an obstacle. It reports what it actually did every 100 ms.
2. **Pi navigation loop, 20 times a second.**
   - Updates a Kalman filter: it predicts the position from the speeds the ESP32 applied, then
     corrects the heading with the IMU.
   - Steers toward the next waypoint: it turns in place if the waypoint is more than 30° off,
     otherwise it steers in proportion to the heading error.
   - Sends a drive command every 100 ms.
3. **Vision loop, as fast as the camera and YOLO allow** (in its own thread). Strong
   detections add 2 points and weak ones add 1. A frame with no person takes 1 point off.
   10 points confirms a find.
4. **Mission loop over LoRa, every few seconds.**
   - The base sends SCAN, STOP, RESUME, or HOME.
   - The robot sends a heartbeat (state, heading, position, uncertainty) every 10 s and on
     every state change.
   - A find is resent until the base confirms it.

More detail and simulation results: `integration/README.md`.

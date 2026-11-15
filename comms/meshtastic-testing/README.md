# SAR robot comms (LoRa via Meshtastic)

```
 [Robot Pi] --USB-- [Heltec] ~~LoRa~~ [Heltec] --USB-- [Laptop: base.py]
                                ~~ any extra Heltec relays automatically (mesh) ~~
```

Files: `common.py` (message signing, radios, ACK/resend logic), `robot.py` (runs on the Pi), `base.py` (runs on the laptop). Keep all three in the same folder.

## 0. Test with no hardware (do this first)
Open three terminals on one laptop:
```
python base.py --sim
python robot.py --sim --id 1
python robot.py --sim --id 2
```
Type `status` or `stop 1` in the base window.

## 1. Prepare each Heltec
1. **Screw the antenna on before powering the board.** Transmitting without an antenna can damage the radio.
2. Check that it's the 915 MHz version (the US band). It's on the box or listing.
3. Flash Meshtastic: go to https://flasher.meshtastic.org in Chrome or Edge, plug the board in over USB, pick **Heltec V3** (or whichever version you have) and flash it.
4. `pip install meshtastic` (on both the Pi and the laptop)

## 2. Configure the radios (one at a time, each plugged in over USB)
```
meshtastic --set lora.region US                 # required, the radio won't transmit until this is set
meshtastic --set lora.modem_preset SHORT_FAST   # faster and less range; fine for a building
meshtastic --set-owner "SAR-Base"                # or SAR-Robot-1, etc.
```
**Encryption.** The default channel key is public, so every Meshtastic user at the event can read it. On the **first** board:
```
meshtastic --ch-set name SARNET --ch-index 0
meshtastic --ch-set psk random --ch-index 0
meshtastic --info        # copy the "Primary channel URL"
```
On **every other** board: `meshtastic --seturl "<that URL>"`

Now radio traffic is AES-256 encrypted, and only your boards can read it.

## 3. Run for real
Laptop: `python base.py` (it auto-detects the board; otherwise add `--port /dev/ttyUSB0`, or `COM3` on Windows, or `/dev/cu.usbserial-XXXX` on a Mac)

Pi: `python robot.py --id 1`

On the Pi, if you get a permission error opening the port: `sudo usermod -aG dialout $USER`, then log out and back in.

Change `SECRET` at the top of `common.py` to something long, and use the same value on every device.

## How the protocol works
- **Messages** are plain dicts sent as JSON, plus a signature at the end. The largest is about 130 bytes, and Meshtastic allows about 230.
- **Handshake:** the robot sends `HELLO` every 5 s until the base replies `WELCOME`. After that it sends a `HEARTBEAT` (battery, state, heading, uptime) every 10 s. If the base hears nothing from a robot for 30 s, it marks it OFFLINE.
- **Reliable messages** (`DETECTION`, `CMD`): the receiver replies with an `ACK` with that message's `seq` number. The sender resends after 5 s, up to 3 tries. A resend reuses the same `seq`, so the receiver acts on it only once.
- **Security, two layers:**
  1. Meshtastic channel key: AES-256. Nobody without the key can *read* the traffic.
  2. An HMAC-SHA256 tag (8 bytes) on every packet, from `SECRET`. Nobody without the secret can *forge* or *modify* a packet, for example to send a fake STOP. AES-CTR alone doesn't prevent tampering, which is why this second layer exists.
  - Duplicate filtering on (from, seq) also blocks simple replays of recent packets.
- Packets are about 20 bytes, small enough for LoRa. Detections are rate-limited to one every 3 s.

## Integration (give this to teammates)
```python
from robot import Robot
from common import MeshRadio

robot = Robot(1, MeshRadio())

while True:
    robot.update()                                  # every loop; never waits
    robot.send_detection(0.87, [x, y, w, h])        # vision, when YOLO sees a person
    command = robot.next_command()                  # motors: "STOP", "RESUME", "HOME", "SCAN" or None
    robot.battery = 82; robot.state = "EXPLORING"   # included in the next heartbeat
```

## Troubleshooting
- No messages arriving: check that both boards have the same region, preset and channel URL (`meshtastic --info`), and that the antennas are attached.
- Long delays are normal. LoRa round trips take 1–3 s, and longer with retries or relays.
- To add a message type, send a dict with a new `"type"` and add an `elif` for it in the receiver's `update()`.

# Pi ↔ ESP32 serial protocol

The robot's Raspberry Pi sends drive commands to the ESP32 over a USB cable. The ESP32 drives
the motors and stops them by itself if the Pi goes quiet or something is in front of the robot.

- USB serial, **115200 baud** (`SERIAL_BAUD` in `config.h`).
- Plain text, one message per line, ending in `\n` (`\r\n` is fine too). Max 63 characters.
- Commands are case-insensitive; the ESP32 always replies in upper case.

## Pi → ESP32

| Command | Reply | Meaning |
|---|---|---|
| `DRIVE <left> <right>` | none (see `STATUS`) | Motor speeds, each -255 (full reverse) to 255 (full forward). 0 stops that side. |
| `STOP` | `OK STOP` | Both motors off. |
| `PING` | `PONG` | Check the link. |
| `OBSTACLE 0` / `OBSTACLE 1` | `OK OBSTACLE 0` / `OK OBSTACLE 1` | Turn the obstacle stop off or on (on at boot). |

Anything else gets `ERR <reason>`, for example `ERR unknown command` or `ERR DRIVE needs two numbers -255..255`.

**The Pi must repeat `DRIVE` (or `STOP`) at least every 300 ms** (`COMMAND_TIMEOUT_MS`).
If it doesn't, the ESP32 stops the motors and reports `TIMEOUT`. The Pi program sends one every
100 ms. This way a crashed Pi program or a pulled cable stops the robot instead of letting it
drive away.

## ESP32 → Pi

| Message | When |
|---|---|
| `READY` | Once at boot, after the motors are initialized. Opening the serial port resets most ESP32 boards, so wait for this line before sending commands. |
| `STATUS <left> <right> <distance> <state>` | Every 100 ms. |
| `PONG`, `OK ...`, `ERR ...` | Replies to commands, as above. |

In `STATUS`:

- `left`, `right`: speeds actually applied (0 if stopped for safety), -255..255.
- `distance`: raw IR distance sensor reading, 0–4095. Higher means closer.
- `state`:
  - `WAITING`: no command received since boot. Motors off.
  - `OK`: driving as commanded.
  - `TIMEOUT`: no command for more than 300 ms. Motors off until the next command.
  - `OBSTACLE`: something is closer than `OBSTACLE_THRESHOLD` and the command was to move
    forward. Motors off. Turning in place (`DRIVE -150 150`) and reversing are still allowed,
    so the robot can get away from it.

Example:

```
READY
STATUS 0 0 812 WAITING
> DRIVE 180 180
STATUS 180 180 830 OK
STATUS 0 0 2412 OBSTACLE
> DRIVE -150 150
STATUS -150 150 2390 OK
```

Lines starting with `>` are sent by the Pi.

## Testing by hand

PlatformIO's serial monitor sends what you type:

```sh
pio device monitor -b 115200 --echo --eol LF
```

Type `DRIVE 150 150` and the wheels should turn for 300 ms, then stop with `TIMEOUT`.
That's the safety timeout working.

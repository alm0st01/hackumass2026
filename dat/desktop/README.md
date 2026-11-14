# Desktop app (dat)

Runs the dashboard in `../ui` as an offline desktop app (Electron). It talks to the
LoRa base station plugged into the laptop over USB serial, using the Web Serial API
(see `../ui/js/robot.js`, 115200 baud, newline-terminated text lines).

## Run

Needs Node.js (`brew install node` on macOS).

```sh
cd dat/desktop
npm install
npm start
```

Click **Connect** and pick the base station's port. Lines it sends appear in the Activity Log.

## Build an app

```sh
npm run dist
```

Output goes to `dist/` (macOS `.dmg`, Windows portable `.exe`, Linux AppImage; build on
the matching OS). The macOS build is unsigned, so the first launch needs right-click → Open.

You can also open `../ui/index.html` directly in Chrome or Edge; serial works there too.
In other browsers the Connect button falls back to a simulated connection.


const startButton = document.getElementById("start-btn");
const stopButton = document.getElementById("stop-btn");

const robotStatus = document.getElementById("robot-status");
const activityLog = document.getElementById("activity-log");

// Search Controls: each button sends a command to the selected robot through the base station
// (POST /api/command), which sends it over LoRa. The robot's real state comes back in its
// heartbeats and shows in the Robot Status card, so nothing here pretends it changed.
async function sendCommand(command) {

    if (selectedRobot === null) {
        addLog("No robot connected yet.");
        return;
    }

    try {
        await fetch("/api/command", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ robot: selectedRobot, command: command }),
        });
        // The base station adds "Sent ..." and "Robot confirmed ..." to the activity log itself.
    } catch (error) {
        addLog("Could not reach the base station.");
    }
}

startButton.addEventListener("click", function () { sendCommand("SCAN"); });
stopButton.addEventListener("click", function () { sendCommand("STOP"); });
document.getElementById("resume-btn").addEventListener("click", function () { sendCommand("RESUME"); });
document.getElementById("home-btn").addEventListener("click", function () { sendCommand("HOME"); });


// Add messages to Activity Log
function addLog(message, kind) {

    const newItem = document.createElement("li");

    newItem.textContent = message;
    newItem.className = "log-" + (kind || "info");

    activityLog.appendChild(newItem);
    activityLog.scrollTop = activityLog.scrollHeight;

}


// Target Detection
// Detections come from integration/dashboard_server.py, which receives them from the
// robot over the radio and pushes them here as Server-Sent Events on /events.
const detectionStatus = document.getElementById("detection-status");
const detectionRobot = document.getElementById("detection-robot");
const detectionConfidence = document.getElementById("detection-confidence");
const detectionPosition = document.getElementById("detection-position");
const detectionTime = document.getElementById("detection-time");

function showDetection(detection) {

    detectionStatus.textContent = "Detected";
    detectionStatus.classList.add("detected");

    detectionRobot.textContent = detection.robot;
    detectionConfidence.textContent = detection.conf + "%";

    let position = "unknown";
    if (detection.x !== null && detection.y !== null) {
        position = "x " + detection.x + " m, y " + detection.y + " m from the start";
        if (detection.err !== null) {
            position += " (±" + detection.err + " m)";
        }
    }
    detectionPosition.textContent = position;

    const time = new Date(detection.time * 1000).toLocaleTimeString();
    detectionTime.textContent = time;

    addLog(time + ": Robot " + detection.robot + " found the target (" + detection.conf + "% sure), at " + position + ".");

    drawDetectionBox(detection.box, detection.conf, time);

    showAlertBanner(detection, position);

}


// Robot Camera: draws where the target was in the robot's camera picture.
// The box is [x, y, w, h] in pixels of a 640x480 frame (VisionThread's default size
// in integration/pi/vision.py), so it is converted to percentages of the frame.
const CAMERA_WIDTH = 640;
const CAMERA_HEIGHT = 480;

const cameraPlaceholder = document.getElementById("camera-placeholder");
const cameraStatus = document.getElementById("camera-status");
const detectionBox = document.getElementById("detection-box");
const detectionBoxLabel = document.getElementById("detection-box-label");

function drawDetectionBox(box, conf, time) {

    if (!Array.isArray(box) || box.length !== 4) {
        return;
    }

    // Keep the box inside the frame, in case the camera ran at a different size.
    const x = Math.min(Math.max(box[0], 0), CAMERA_WIDTH);
    const y = Math.min(Math.max(box[1], 0), CAMERA_HEIGHT);
    const w = Math.min(Math.max(box[2], 0), CAMERA_WIDTH - x);
    const h = Math.min(Math.max(box[3], 0), CAMERA_HEIGHT - y);

    detectionBox.style.left = (x / CAMERA_WIDTH * 100) + "%";
    detectionBox.style.top = (y / CAMERA_HEIGHT * 100) + "%";
    detectionBox.style.width = (w / CAMERA_WIDTH * 100) + "%";
    detectionBox.style.height = (h / CAMERA_HEIGHT * 100) + "%";
    detectionBox.style.display = "block";

    detectionBoxLabel.textContent = "Target " + conf + "%";

    cameraPlaceholder.style.display = "none";
    cameraStatus.textContent = "LAST DETECTION " + time;
    cameraStatus.style.backgroundColor = "#166534";

}


// Connection to the base station (dashboard_server.py)

const connectButton = document.getElementById("connect-btn");
const disconnectButton = document.getElementById("disconnect-btn");

const connectionStatus = document.getElementById("connection-status");

// Track connection state
let isConnected = false;
let eventSource = null;

function setConnectionStatus(text, color) {
    connectionStatus.textContent = text;
    connectionStatus.style.color = color;
}


// Connect to the base station
connectButton.addEventListener("click", function () {

    if (eventSource) {
        return;
    }

    // The page has to be served by dashboard_server.py, not opened as a file.
    if (window.location.protocol === "file:") {
        addLog("Open the dashboard at http://localhost:8000 (run integration/dashboard_server.py first).");
        return;
    }

    setConnectionStatus("Connecting...", "#facc15");
    eventSource = new EventSource("/events");

    eventSource.onopen = function () {
        isConnected = true;
        setConnectionStatus("Connected", "#22c55e");
        addLog("Connected to base station.");
    };

    // EventSource retries by itself after an error, so only report it.
    eventSource.onerror = function () {
        if (isConnected) {
            addLog("Lost connection to base station. Retrying...");
        }
        isConnected = false;
        setConnectionStatus("Reconnecting...", "#facc15");
    };

    eventSource.addEventListener("detection", function (event) {
        showDetection(JSON.parse(event.data));
    });

});


// Disconnect from the base station
disconnectButton.addEventListener("click", function () {

    if (!eventSource) {
        return;
    }

    eventSource.close();
    eventSource = null;
    isConnected = false;

    setConnectionStatus("Disconnected", "#ef4444");

    addLog("Disconnected from base station.");

});


// ================================================================ live robot status + map
// Once a second the page asks the base station for /api/state: each robot's state, battery,
// heading and position (from its heartbeats), every detection (for the map), and the
// base station's activity log (commands sent, confirmed, robots joining or going offline).

const robotSelect = document.getElementById("robot-select");
const robotLink = document.getElementById("robot-link");
const robotBattery = document.getElementById("robot-battery");
const robotPosition = document.getElementById("robot-position");
const robotHeading = document.getElementById("robot-heading");
const alertBanner = document.getElementById("alert-banner");
const alertText = document.getElementById("alert-text");
const mapCanvas = document.getElementById("map");

let selectedRobot = null;   // robot the status card and buttons are for
let lastEventId = 0;        // newest base-station log entry already shown
let latestState = null;     // last /api/state answer, for redrawing the map
const trails = {};          // robot id -> list of [x, y] it has reported, to draw its path

const STATE_COLORS = {
    IDLE: "#facc15",
    EXPLORING: "#22c55e",
    FOUND: "#ef4444",
    SEARCH_DONE: "#60a5fa",
    RETURNING: "#60a5fa",
    STOPPED: "#9ca3af",
};

async function refreshState() {
    if (window.location.protocol === "file:") {
        return;  // opened as a file: there's no base station to ask
    }
    try {
        const response = await fetch("/api/state");
        latestState = await response.json();
        showRobots(latestState.robots);
        showBaseEvents(latestState.events);
        drawMap();
    } catch (error) {
        // base station not running; the Connect button reports that
    }
}

setInterval(refreshState, 1000);
refreshState();


// ---- Robot Status card

function showRobots(robots) {

    // Keep the dropdown in step with the robots the base knows about
    const ids = robots.map(function (robot) { return robot.id; });
    if (robotSelect.options.length !== ids.length) {
        robotSelect.innerHTML = "";
        ids.forEach(function (id) {
            const option = document.createElement("option");
            option.value = id;
            option.textContent = "Robot " + id;
            robotSelect.appendChild(option);
        });
    }
    if (selectedRobot === null && ids.length > 0) {
        selectedRobot = ids[0];
    }
    robotSelect.value = selectedRobot;
    robotSelect.style.display = ids.length > 1 ? "block" : "none";

    // Remember each robot's path for the map
    robots.forEach(function (robot) {
        if (robot.x === null) {
            return;
        }
        const trail = trails[robot.id] || (trails[robot.id] = []);
        const last = trail[trail.length - 1];
        if (!last || last[0] !== robot.x || last[1] !== robot.y) {
            trail.push([robot.x, robot.y]);
        }
    });

    const robot = robots.find(function (r) { return r.id === selectedRobot; });

    if (!robot) {
        robotStatus.textContent = "--";
        robotLink.textContent = "No robots yet";
        robotLink.style.color = "#facc15";
        return;
    }

    const state = robot.state === "?" ? "WAITING" : robot.state;
    robotStatus.textContent = state.replace("_", " ");
    robotStatus.style.color = STATE_COLORS[state] || "#facc15";

    if (robot.online) {
        robotLink.textContent = "Robot online (heard " + Math.round(robot.last_seen) + " s ago)";
        robotLink.style.color = "#22c55e";
    } else {
        robotLink.textContent = "Robot OFFLINE (last heard " + Math.round(robot.last_seen) + " s ago)";
        robotLink.style.color = "#ef4444";
    }

    robotBattery.textContent = robot.battery === "?" ? "--" : robot.battery + "%";
    robotPosition.textContent = robot.x === null ? "--"
        : "x " + robot.x.toFixed(1) + " m, y " + robot.y.toFixed(1) + " m (±" + robot.err + " m)";
    robotHeading.textContent = robot.heading === null ? "--" : robot.heading + "°";
}

robotSelect.addEventListener("change", function () {
    selectedRobot = Number(robotSelect.value);
    if (latestState) {
        showRobots(latestState.robots);
        drawMap();
    }
});


// ---- Activity Log entries from the base station

function showBaseEvents(events) {
    events.forEach(function (event) {
        if (event.id > lastEventId) {
            addLog(new Date(event.time * 1000).toLocaleTimeString() + ": " + event.text, event.kind);
            lastEventId = event.id;
        }
    });
}


// ---- Banner when a target is found (called from showDetection)

function showAlertBanner(detection, position) {
    alertText.textContent = "TARGET FOUND by robot " + detection.robot + " (" + detection.conf + "% sure)"
        + (position === "unknown" ? "" : " at " + position);
    alertBanner.hidden = false;
}

document.getElementById("alert-dismiss").addEventListener("click", function () {
    alertBanner.hidden = true;
});


// ---- Map

function drawMap() {

    const ctx = mapCanvas.getContext("2d");
    const width = mapCanvas.clientWidth;
    const height = mapCanvas.clientHeight;
    const scaleForScreen = window.devicePixelRatio || 1;
    mapCanvas.width = width * scaleForScreen;
    mapCanvas.height = height * scaleForScreen;
    ctx.setTransform(scaleForScreen, 0, 0, scaleForScreen, 0, 0);
    ctx.clearRect(0, 0, width, height);

    if (!latestState) {
        return;
    }

    // Every point to fit on screen: the base, the robots' paths, and the detections
    const points = [[0, 0]];
    Object.values(trails).forEach(function (trail) { points.push.apply(points, trail); });
    latestState.alerts.forEach(function (a) {
        if (a.x !== null && a.x !== undefined) { points.push([a.x, a.y]); }
    });

    const xs = points.map(function (p) { return p[0]; });
    const ys = points.map(function (p) { return p[1]; });
    const span = Math.max(Math.max.apply(null, xs) - Math.min.apply(null, xs),
                          Math.max.apply(null, ys) - Math.min.apply(null, ys), 10);  // at least 10 m
    const centerX = (Math.max.apply(null, xs) + Math.min.apply(null, xs)) / 2;
    const centerY = (Math.max.apply(null, ys) + Math.min.apply(null, ys)) / 2;
    const pixelsPerMetre = Math.min(width, height) / (span * 1.25);  // leave a margin

    // metres -> pixels (north is up, so y is flipped)
    function toScreen(x, y) {
        return [width / 2 + (x - centerX) * pixelsPerMetre, height / 2 - (y - centerY) * pixelsPerMetre];
    }

    // Grid lines every 1, 5, 10, 20 or 50 m, whichever fits
    const step = [1, 5, 10, 20, 50].find(function (s) { return s * pixelsPerMetre > 40; }) || 100;
    ctx.strokeStyle = "#1f2a3c";
    ctx.lineWidth = 1;
    ctx.fillStyle = "#4b5563";
    ctx.font = "11px Arial";
    const left = centerX - width / 2 / pixelsPerMetre, right = centerX + width / 2 / pixelsPerMetre;
    const bottom = centerY - height / 2 / pixelsPerMetre, top = centerY + height / 2 / pixelsPerMetre;
    for (let x = Math.ceil(left / step) * step; x <= right; x += step) {
        const sx = toScreen(x, 0)[0];
        ctx.beginPath(); ctx.moveTo(sx, 0); ctx.lineTo(sx, height); ctx.stroke();
        ctx.fillText(x + " m", sx + 3, height - 4);
    }
    for (let y = Math.ceil(bottom / step) * step; y <= top; y += step) {
        const sy = toScreen(0, y)[1];
        ctx.beginPath(); ctx.moveTo(0, sy); ctx.lineTo(width, sy); ctx.stroke();
        ctx.fillText(y + " m", 3, sy - 3);
    }

    // Base (start point)
    const base = toScreen(0, 0);
    ctx.fillStyle = "#facc15";
    ctx.fillRect(base[0] - 6, base[1] - 6, 12, 12);
    ctx.fillText("BASE", base[0] + 9, base[1] + 4);

    // Robots: path, uncertainty circle, position, heading
    latestState.robots.forEach(function (robot) {
        const trail = trails[robot.id] || [];

        ctx.strokeStyle = robot.id === selectedRobot ? "#60a5fa" : "#334155";
        ctx.lineWidth = 2;
        ctx.beginPath();
        trail.forEach(function (p, i) {
            const s = toScreen(p[0], p[1]);
            if (i === 0) { ctx.moveTo(s[0], s[1]); } else { ctx.lineTo(s[0], s[1]); }
        });
        ctx.stroke();

        if (robot.x === null) {
            return;
        }
        const s = toScreen(robot.x, robot.y);

        if (robot.err) {
            ctx.fillStyle = "rgba(96, 165, 250, 0.15)";
            ctx.beginPath();
            ctx.arc(s[0], s[1], Math.max(robot.err * pixelsPerMetre, 4), 0, 2 * Math.PI);
            ctx.fill();
        }

        ctx.fillStyle = robot.online ? "#60a5fa" : "#6b7280";
        ctx.beginPath();
        ctx.arc(s[0], s[1], 7, 0, 2 * Math.PI);
        ctx.fill();

        if (robot.heading !== null) {
            const angle = robot.heading * Math.PI / 180;   // compass: 0 = north, clockwise
            ctx.strokeStyle = ctx.fillStyle;
            ctx.beginPath();
            ctx.moveTo(s[0], s[1]);
            ctx.lineTo(s[0] + Math.sin(angle) * 20, s[1] - Math.cos(angle) * 20);
            ctx.stroke();
        }

        ctx.fillStyle = "#e5e7eb";
        ctx.fillText("Robot " + robot.id, s[0] + 10, s[1] - 10);
    });

    // Detections
    latestState.alerts.forEach(function (a) {
        if (a.x === null || a.x === undefined) {
            return;
        }
        const s = toScreen(a.x, a.y);
        ctx.strokeStyle = "#ef4444";
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.moveTo(s[0] - 7, s[1] - 7); ctx.lineTo(s[0] + 7, s[1] + 7);
        ctx.moveTo(s[0] + 7, s[1] - 7); ctx.lineTo(s[0] - 7, s[1] + 7);
        ctx.stroke();
        ctx.fillStyle = "#fca5a5";
        ctx.fillText(a.conf + "%", s[0] + 10, s[1] + 4);
    });
}

window.addEventListener("resize", drawMap);


// Connect to the base station's detection stream as soon as the page opens
// (the Connect / Disconnect buttons still work after that).
if (window.location.protocol !== "file:") {
    connectButton.click();
}

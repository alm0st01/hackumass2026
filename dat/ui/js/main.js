
const startButton = document.getElementById("start-btn");
const stopButton = document.getElementById("stop-btn");

const robotStatus = document.getElementById("robot-status");
const activityLog = document.getElementById("activity-log");

// Track the robot's current state
let isSearching = false;



// Start Search
startButton.addEventListener("click", function () {

    // Check if robot is connected
    if (!isConnected) {
        addLog("Cannot start search: Robot is disconnected.");
        return;
    }

    // Prevent starting if already searching
    if (isSearching) {
        return;
    }

    isSearching = true;

    robotStatus.textContent = "SEARCHING";
    robotStatus.style.color = "#22c55e";

    addLog("Search started.");

});


// Stop Search
stopButton.addEventListener("click", function () {

    if (!isSearching) {
        return;
    }

    isSearching = false;

    robotStatus.textContent = "IDLE";
    robotStatus.style.color = "#facc15";

    addLog("Search stopped.");

});


// Add messages to Activity Log
function addLog(message) {

    const newItem = document.createElement("li");

    newItem.textContent = message;

    activityLog.appendChild(newItem);

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

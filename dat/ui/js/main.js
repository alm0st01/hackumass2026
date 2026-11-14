
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


// AprilTag Detection
const detectButton = document.getElementById("detect-btn");

const detectionStatus = document.getElementById("detection-status");
const tagId = document.getElementById("tag-id");
const tagDistance = document.getElementById("tag-distance");


detectButton.addEventListener("click", function () {

    detectionStatus.textContent = "Detected";
    tagId.textContent = "5";
    tagDistance.textContent = "1.25 m";

    addLog("AprilTag detected. ID: 5");

});


// Robot Connection System

const connectButton = document.getElementById("connect-btn");
const disconnectButton = document.getElementById("disconnect-btn");

const connectionStatus = document.getElementById("connection-status");

// Track connection state
let isConnected = false;


function setConnected(connected) {
    isConnected = connected;
    connectionStatus.textContent = connected ? "Connected" : "Disconnected";
    connectionStatus.style.color = connected ? "#22c55e" : "#ef4444";
}
// Lines received from the base station go to the Activity Log.
robotLink.onLine = function (line) {
    addLog("Robot: " + line);
};
// Port closed or unplugged.
robotLink.onClose = function () {
    if (isConnected) {
        setConnected(false);
        addLog("Robot disconnected.");
    }
};
// Connect Robot
connectButton.addEventListener("click", async function () {
    if (isConnected) {
        return;
    }
    if (!robotLink.isSupported()) {
        // Plain browser without Web Serial: keep the simulated connection.
        setConnected(true);
        addLog("Robot connected (simulated: serial not available).");
        return;
    }
    try {
        await robotLink.connect();
        setConnected(true);
        addLog("Robot connected over serial.");
    } catch (error) {
        addLog("Could not connect: " + error.message);
    }
});
// Disconnect Robot
disconnectButton.addEventListener("click", async function () {
    if (!isConnected) {
        return;
    }
    setConnected(false);
    await robotLink.disconnect();
    addLog("Robot disconnected.");
});
// Laptop Camera System
const video = document.getElementById("camera-video");
const placeholder = document.getElementById("camera-placeholder");
const cameraStatus = document.getElementById("camera-status");

const startCameraButton = document.getElementById("start-camera-btn");
const stopCameraButton = document.getElementById("stop-camera-btn");

let cameraStream = null;

// Start Camera
startCameraButton.addEventListener("click", async function () {

    try {
        cameraStream = await navigator.mediaDevices.getUserMedia({
            video: true
        });

        video.srcObject = cameraStream;

        video.style.display = "block";
        placeholder.style.display = "none";

        cameraStatus.textContent = "LIVE";
        cameraStatus.style.backgroundColor = "#16a34a";

        addLog("Laptop camera started.");

    } catch (error) {
        addLog("Could not access camera: " + error.message);
        alert("Unable to access your camera. Please check your camera permissions.");
    }

});

// Stop Camera
stopCameraButton.addEventListener("click", function () {

    if (cameraStream) {
        cameraStream.getTracks().forEach(function (track) {
            track.stop();
        });

        cameraStream = null;
    }

    video.srcObject = null;

    video.style.display = "none";
    placeholder.style.display = "block";

    cameraStatus.textContent = "OFFLINE";
    cameraStatus.style.backgroundColor = "#991b1b";

    addLog("Laptop camera stopped.");

});
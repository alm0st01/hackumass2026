// Electron entry point: opens dat/ui in a desktop window, fully offline.
// Serial access uses the Web Serial API inside the page; this file only
// grants permissions and asks the user which port to open.
const { app, BrowserWindow, dialog, session } = require("electron");
const path = require("path");

const UI_DIR = app.isPackaged
    ? path.join(process.resourcesPath, "ui")
    : path.join(__dirname, "..", "ui");

function createWindow() {
    const win = new BrowserWindow({
        width: 1280,
        height: 860,
        title: "Mini Search Robot",
        webPreferences: {
            contextIsolation: true,
            nodeIntegration: false,
            sandbox: true
        }
    });
    win.removeMenu();
    win.loadFile(path.join(UI_DIR, "index.html"));

    // Called when the page runs navigator.serial.requestPort().
    win.webContents.session.on("select-serial-port", async (event, portList, _wc, callback) => {
        event.preventDefault();
        if (portList.length === 0) {
            await dialog.showMessageBox(win, {
                type: "warning",
                message: "No serial ports found.",
                detail: "Plug in the LoRa base station over USB and try again."
            });
            callback("");
            return;
        }
        const labels = portList.map((p) => p.displayName ? `${p.displayName} (${p.portName})` : p.portName);
        const { response } = await dialog.showMessageBox(win, {
            type: "question",
            message: "Select the robot base station port",
            buttons: [...labels, "Cancel"],
            cancelId: labels.length
        });
        callback(response < portList.length ? portList[response].portId : "");
    });
}

app.whenReady().then(() => {
    // Only the local dashboard page is loaded, so grant serial and camera access.
    const allowed = new Set(["serial", "media"]);
    session.defaultSession.setPermissionCheckHandler((_wc, permission) => allowed.has(permission));
    session.defaultSession.setPermissionRequestHandler((_wc, permission, callback) => callback(allowed.has(permission)));
    session.defaultSession.setDevicePermissionHandler((details) => details.deviceType === "serial");

    createWindow();
    app.on("activate", () => {
        if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
});

app.on("window-all-closed", () => {
    if (process.platform !== "darwin") app.quit();
});

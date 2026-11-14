// Serial link to the LoRa base station plugged into the laptop over USB.
// Uses the Web Serial API (works in the desktop app and in Chrome/Edge).
// Messages are newline-terminated text lines; the format is still to be
// agreed with the communication (piku) and client brains (adi) code.
const robotLink = (function () {
    const BAUD_RATE = 115200;
    let port = null;
    let reader = null;
    let onLine = function () {};
    let onClose = function () {};

    function isSupported() {
        return "serial" in navigator;
    }

    async function readLoop() {
        const decoder = new TextDecoder();
        let buffer = "";
        while (port && port.readable) {
            reader = port.readable.getReader();
            try {
                while (true) {
                    const { value, done } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });
                    let newline;
                    while ((newline = buffer.indexOf("\n")) >= 0) {
                        const line = buffer.slice(0, newline).replace(/\r$/, "");
                        buffer = buffer.slice(newline + 1);
                        if (line.length > 0) onLine(line);
                    }
                }
            } catch (error) {
                // Device unplugged or read error; fall through and close.
                break;
            } finally {
                reader.releaseLock();
                reader = null;
            }
        }
    }

    async function connect() {
        port = await navigator.serial.requestPort();
        await port.open({ baudRate: BAUD_RATE });
        readLoop().then(function () {
            if (port) {
                disconnect();
            }
        });
    }

    async function disconnect() {
        const closing = port;
        port = null;
        if (!closing) return;
        try {
            if (reader) await reader.cancel();
            await closing.close();
        } catch (error) {
            // Port already gone.
        }
        onClose();
    }

    async function send(line) {
        if (!port || !port.writable) throw new Error("Not connected");
        const writer = port.writable.getWriter();
        try {
            await writer.write(new TextEncoder().encode(line + "\n"));
        } finally {
            writer.releaseLock();
        }
    }

    return {
        isSupported: isSupported,
        connect: connect,
        disconnect: disconnect,
        send: send,
        set onLine(fn) { onLine = fn; },
        set onClose(fn) { onClose = fn; }
    };
})();

"""Base station with the web dashboard (dat/ui): base_station.py plus live detections in a browser.

    python integration/dashboard_server.py --sim          (testing on one computer)
    python integration/dashboard_server.py --port COM5    (real radio: the base Heltec's port)

Then open http://localhost:8000 and press Connect.

Everything base_station.py does still works in this terminal: alerts print here, and you can
type status | stop 1 | resume 1 | home 1 | scan 1.

Each DETECTION a robot sends over the radio is pushed to the page as a Server-Sent Event
("detection") on /events:
    {"robot": 1, "conf": 84, "box": [41, 170, 127, 226], "x": 12.3, "y": 30.1, "err": 2.4,
     "time": 1731600000.0}
conf is 0-100. x / y / err are null if the robot didn't send a position. time is when the base
received it (Unix seconds). Only the Python standard library is needed.
"""
import argparse
import json
import os
import queue
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from base_station import LocatedBase  # also puts Piku's folder on sys.path

import base as piku_base  # noqa: E402  (Piku's code)
from base import COMMANDS  # noqa: E402
from common import MeshRadio, SimRadio  # noqa: E402

UI_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dat", "ui"))
KEEPALIVE_S = 15  # comment line sent this often so idle connections aren't dropped


class EventHub:
    """Hands each published event to every open browser tab."""

    def __init__(self):
        self._lock = threading.Lock()
        self._clients = []

    def subscribe(self):
        q = queue.Queue(maxsize=100)
        with self._lock:
            self._clients.append(q)
        return q

    def unsubscribe(self, q):
        with self._lock:
            if q in self._clients:
                self._clients.remove(q)

    def publish(self, event):
        data = json.dumps(event)
        with self._lock:
            for q in self._clients:
                try:
                    q.put_nowait(data)
                except queue.Full:
                    pass  # a tab that stopped reading misses this one


class DashboardBase(LocatedBase):
    def __init__(self, radio, hub):
        super().__init__(radio)
        self.hub = hub

    def check_inbox(self):
        messages = super().check_inbox()  # duplicates and resends are already filtered out
        for msg in messages:
            if msg["type"] == "DETECTION":
                self.hub.publish({
                    "robot": msg["from"],
                    "conf": msg.get("conf"),
                    "box": msg.get("box"),
                    "x": msg.get("x"),
                    "y": msg.get("y"),
                    "err": msg.get("err"),
                    "time": time.time(),
                })
        return messages


class DashboardHandler(SimpleHTTPRequestHandler):
    hub = None  # set in main()

    # Windows can map .js to text/plain through the registry, so set the types explicitly.
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".html": "text/html",
        ".js": "text/javascript",
        ".css": "text/css",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=UI_DIR, **kwargs)

    def do_GET(self):
        if self.path.split("?", 1)[0] == "/events":
            self.stream_events()
        else:
            super().do_GET()

    def stream_events(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        q = self.hub.subscribe()
        try:
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            while True:
                try:
                    data = q.get(timeout=KEEPALIVE_S)
                    self.wfile.write(f"event: detection\ndata: {data}\n\n".encode())
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # tab closed or Disconnect pressed
        finally:
            self.hub.unsubscribe(q)

    def log_message(self, format, *args):
        pass  # keep the terminal for radio alerts


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sim", action="store_true", help="fake radio for testing on one laptop")
    parser.add_argument("--port", default=None, help="serial port of the Heltec, e.g. COM5 or /dev/ttyUSB0")
    parser.add_argument("--http-port", type=int, default=8000, help="port for the dashboard web page")
    parser.add_argument("--host", default="127.0.0.1",
                        help="address to serve the dashboard on. 0.0.0.0 lets other devices on the network open it.")
    args = parser.parse_args()

    hub = EventHub()
    DashboardHandler.hub = hub
    server = ThreadingHTTPServer((args.host, args.http_port), DashboardHandler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()

    base = DashboardBase(SimRadio() if args.sim else MeshRadio(args.port), hub)
    threading.Thread(target=piku_base.read_keyboard, daemon=True).start()
    shown_host = "localhost" if args.host in ("127.0.0.1", "0.0.0.0") else args.host
    print(f"dashboard: http://{shown_host}:{args.http_port}")
    print("base station running. type: status | stop 1 | resume 1 | home 1 | scan 1")
    try:
        while True:
            base.update()
            while piku_base.typed_lines:
                words = piku_base.typed_lines.pop(0).split()
                if words == ["status"]:
                    base.print_status()
                elif len(words) == 2 and words[0].upper() in COMMANDS and words[1].isdigit():
                    base.send_command(int(words[1]), words[0].upper())
                elif words:
                    print("?")
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()

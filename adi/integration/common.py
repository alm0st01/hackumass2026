# common.py - code shared by the robots and the base station.
#
# Messages are plain Python dicts, sent as JSON text, for example:
#   {"type": "DETECTION", "from": 1, "to": 0, "seq": 5012, "conf": 87, "box": [120, 80, 60, 140]}
#
# Every message gets a signature added to the end. If someone doesn't know SECRET,
# they can't make a message with a valid signature, so they can't fake commands.

import hashlib
import hmac
import json
import queue
import random
import socket
import struct
import time

SECRET = "hackumass-change-me"  # must be the same on every robot and the base
BASE_ID = 0
ACK_TIMEOUT = 5   # seconds to wait for an ACK before resending
MAX_TRIES = 3     # give up after this many sends


# ---------------------------------------------------------------- packing messages

def sign(text):
    return hmac.new(SECRET.encode(), text.encode(), hashlib.sha256).hexdigest()[:16]


def make_packet(msg):
    """dict -> bytes ready to send. Looks like: {"type":"HELLO",...}|3f9a0c1d2b4e5f60"""
    text = json.dumps(msg, separators=(",", ":"))  # no spaces, to keep it short
    return (text + "|" + sign(text)).encode()


def read_packet(data):
    """bytes -> dict, or None if it's junk or the signature is wrong."""
    try:
        text, signature = data.decode().rsplit("|", 1)
        if not hmac.compare_digest(signature, sign(text)):
            print("!! rejected a message with a bad signature")
            return None
        return json.loads(text)
    except ValueError:  # covers bad UTF-8, a missing "|", and bad JSON
        return None


# ---------------------------------------------------------------- radios
# Both radios have the same two methods:
#   send(data)  -> sends bytes
#   receive()   -> returns bytes, or None if nothing has arrived. Never waits.

class MeshRadio:
    """The real thing: a Heltec running Meshtastic, plugged in over USB."""

    def __init__(self, port=None):  # port=None means find the board automatically
        import meshtastic.serial_interface
        from pubsub import pub

        self.inbox = queue.Queue()  # Meshtastic drops received packets in here
        pub.subscribe(self.on_packet, "meshtastic.receive")
        self.device = meshtastic.serial_interface.SerialInterface(port)

    def on_packet(self, packet, interface):
        # Meshtastic calls this whenever anything arrives. We only want our own app's
        # messages (PRIVATE_APP), not the chat/position packets Meshtastic sends by itself.
        decoded = packet.get("decoded", {})
        if decoded.get("portnum") == "PRIVATE_APP":
            self.inbox.put(decoded["payload"])

    def send(self, data):
        self.device.sendData(data, portNum=256)  # 256 = PRIVATE_APP

    def receive(self):
        if self.inbox.empty():
            return None
        return self.inbox.get()


class SimRadio:
    """Fake radio for testing on one laptop. Every program using SimRadio hears
    everything the others send, the same way LoRa works. You don't need to
    understand the socket setup below; it only makes that happen."""

    GROUP, PORT = "239.255.42.42", 47000

    def __init__(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        s.bind(("", self.PORT))
        local = socket.inet_aton("127.0.0.1")
        s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(self.GROUP) + local)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, local)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        s.setblocking(False)
        self.sock = s

    def send(self, data):
        self.sock.sendto(data, (self.GROUP, self.PORT))

    def receive(self):
        try:
            return self.sock.recv(1024)
        except BlockingIOError:  # nothing has arrived
            return None


# ---------------------------------------------------------------- node
# A Node is anything with a radio: a robot or the base. This class handles the
# boring parts both of them need: numbering messages, ACKs, resending, and
# ignoring duplicates.

class Node:
    def __init__(self, my_id, radio):
        self.my_id = my_id
        self.radio = radio
        self.seq = random.randint(0, 1_000_000)  # random start, so numbers aren't reused after a reboot
        self.waiting_for_ack = {}  # seq -> {"packet", "msg", "last_sent", "tries"}
        self.already_seen = []     # (from, seq) of recent messages, to spot duplicates

    def send(self, msg, needs_ack=False):
        self.seq += 1
        msg["from"] = self.my_id
        msg["seq"] = self.seq
        if needs_ack:
            msg["needs_ack"] = True
        packet = make_packet(msg)
        self.radio.send(packet)
        if needs_ack:
            self.waiting_for_ack[self.seq] = {"packet": packet, "msg": msg,
                                              "last_sent": time.time(), "tries": 1}

    def resend_unacked(self):
        """Resend anything that hasn't been ACKed in time. Call this regularly."""
        now = time.time()
        for seq in list(self.waiting_for_ack):  # list() because we may delete while looping
            entry = self.waiting_for_ack[seq]
            if now - entry["last_sent"] < ACK_TIMEOUT:
                continue
            if entry["tries"] >= MAX_TRIES:
                del self.waiting_for_ack[seq]
                self.gave_up(entry["msg"])
            else:
                self.radio.send(entry["packet"])  # the same packet, with the same seq number
                entry["tries"] += 1
                entry["last_sent"] = now

    def check_inbox(self):
        """Return a list of new messages meant for us. ACKs and duplicates are handled here."""
        new_messages = []
        while True:
            data = self.radio.receive()
            if data is None:
                break
            msg = read_packet(data)
            if msg is None or msg["from"] == self.my_id:
                continue
            if msg["to"] != self.my_id and msg["to"] != "all":
                continue  # meant for someone else

            if msg["type"] == "ACK":
                acked = self.waiting_for_ack.pop(msg["ack"], None)
                if acked:
                    self.got_ack(acked["msg"])
                continue

            if msg.get("needs_ack"):
                # Always reply, even to a duplicate: maybe our first ACK got lost.
                self.send({"type": "ACK", "to": msg["from"], "ack": msg["seq"]})

            key = (msg["from"], msg["seq"])
            if key in self.already_seen:
                continue  # a resend we've already handled
            self.already_seen.append(key)
            self.already_seen = self.already_seen[-200:]  # remember only the last 200
            new_messages.append(msg)
        return new_messages

    # Robot and Base replace these two with their own versions.
    def got_ack(self, msg):
        pass

    def gave_up(self, msg):
        print(f"no ACK for {msg['type']} after {MAX_TRIES} tries")

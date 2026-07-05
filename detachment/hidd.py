"""
detachment root HID emitter (`detachment-hidd`).

Holds the classic Bluetooth HID link to the target and serves a tiny line protocol on a unix socket
so the unprivileged session agent can drive it:

  A x y b w p   absolute pointer: x,y in 0..32767, 5-bit button mask b, wheel w, pan p
  K mod c1..c6  keyboard report: modifier byte + up to 6 HID keycodes (0-padded)

Runs as root (binds L2CAP PSMs 17/19, talks to BlueZ). The target pairs once (auto-accept agent +
HID SDP record). Installed as the system service `detachment-hidd` by the gcunix module.
"""
import os
import signal
import socket
import sys
import threading
import time

import dbus
import dbus.mainloop.glib
from gi.repository import GLib

from . import bluez, config, hid

SOCK_PATH = config.SOCKET_PATH


def log(msg):
    print(f"[hidd] {msg}", flush=True)


def handle_line(link, line):
    parts = line.split()
    if not parts:
        return
    cmd = parts[0]
    try:
        if cmd == "A":                     # A x y buttons [wheel] [pan]
            x, y, b = int(parts[1]), int(parts[2]), int(parts[3])
            w = int(parts[4]) if len(parts) > 4 else 0
            pan = int(parts[5]) if len(parts) > 5 else 0
            link.send(hid.pointer_abs_report(b, x, y, w, pan))
        elif cmd == "K":                   # K mod c1..c6
            mod = int(parts[1])
            keys = [int(c) for c in parts[2:8]]
            link.send(hid.keyboard_report(mod, keys))
        else:
            log(f"unknown command {cmd!r}")
    except Exception as e:   # never let one malformed line kill the serve loop
        log(f"bad command {line!r}: {e}")


def keepalive(link):
    """Nudge a no-op mouse report every 20s so Windows doesn't idle-drop the BT HID link
    (the classic BT/USB-HID selective-suspend disconnect)."""
    while True:
        time.sleep(20)
        if link.interrupt:
            try:
                link.interrupt.send(hid.mouse_rel_report(0, 0, 0))
            except OSError:
                pass


def serve(link):
    sockdir = os.path.dirname(SOCK_PATH)
    if sockdir:
        os.makedirs(sockdir, exist_ok=True)
    if os.path.exists(SOCK_PATH):
        os.unlink(SOCK_PATH)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(SOCK_PATH)
    os.chmod(SOCK_PATH, 0o666)   # let the session-user agent connect
    srv.listen(1)
    log(f"command socket at {SOCK_PATH}")
    while True:
        conn, _ = srv.accept()
        log("agent connected")
        buf = b""
        try:
            with conn:
                while True:
                    data = conn.recv(4096)
                    if not data:
                        break
                    buf += data
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        handle_line(link, line.decode(errors="replace").strip())
        except OSError as e:
            log(f"agent connection error: {e}")
        log("agent disconnected — waiting for reconnect")


def main():
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))   # -> finally: cleanup on kill/stop
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    profilemgr, agentmgr, registered = bluez.setup_bluez(bus)

    loop = GLib.MainLoop()
    threading.Thread(target=loop.run, daemon=True).start()

    link = bluez.HidLink()
    ready = threading.Event()
    threading.Thread(target=bluez.accept_channels, args=(link, ready.set), daemon=True).start()

    log("waiting for the Windows target to pair + connect… (Ctrl-C to quit)")
    try:
        ready.wait()
        log("HID link up — serving commands")
        threading.Thread(target=keepalive, args=(link,), daemon=True).start()
        serve(link)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        bluez.cleanup(profilemgr, agentmgr, registered)
        if os.path.exists(SOCK_PATH):
            os.unlink(SOCK_PATH)
        log("bye")


if __name__ == "__main__":
    main()

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
import random
import signal
import socket
import sys
import threading
import time

import dbus
import dbus.mainloop.glib
from gi.repository import GLib

from . import bluez, config, hid, led

SOCK_PATH = config.SOCKET_PATH
LEDCTL = None     # LedController instance (resolves its own LED path)


def log(msg):
    print(f"[hidd] {msg}", flush=True)


def handle_line(link, jiggler, line):
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
        elif cmd == "J":                   # J on|off [interval_sec] [pixels] — mouse jiggler
            on = parts[1].lower() in ("on", "1", "true")
            interval = float(parts[2]) if len(parts) > 2 else jiggler.interval
            pixels = int(parts[3]) if len(parts) > 3 else jiggler.pixels
            jiggler.configure(on, interval, pixels)
        elif cmd == "E":                   # E 1|0 — capture state for the status LED
            if LEDCTL:
                LEDCTL.captured = parts[1].lower() not in ("0", "off", "false")
        else:
            log(f"unknown command {cmd!r}")
    except Exception as e:   # never let one malformed line kill the serve loop
        log(f"bad command {line!r}: {e}")


class Jiggler:
    """Keep the target awake: every ~interval (±30% jitter) a tiny relative move, alternating
    direction so it stays put over pairs. Off by default; the agent/tray toggles it via `J`."""
    def __init__(self, link):
        self.link = link
        self.enabled = False
        self.interval = 30.0
        self.pixels = 2
        self._dir = 1
        self._wake = threading.Event()

    def configure(self, enabled, interval, pixels):
        self.enabled = bool(enabled)
        self.interval = max(1.0, float(interval))
        self.pixels = max(1, int(pixels))
        self._wake.set()   # re-evaluate the wait immediately
        log(f"jiggler {'on' if self.enabled else 'off'} ({self.pixels}px / ~{self.interval:.0f}s)")

    def run(self):
        while True:
            if not self.enabled:
                self._wake.wait(timeout=5)
                self._wake.clear()
                continue
            wait = self.interval * (1 + (random.random() * 2 - 1) * 0.3)   # ±30% jitter
            reconfigured = self._wake.wait(timeout=wait)
            self._wake.clear()
            if reconfigured or not self.enabled:
                continue
            if self.link.interrupt:
                move = self.pixels * self._dir
                self.link.send(hid.mouse_rel_report(0, move, move))
                self._dir = -self._dir


class LedController:
    """Three-state status LED: off = no HID link, green heartbeat = connected/idle, solid red =
    driving the target. `captured` is set by the agent's E command; link state is read from the
    HidLink. Resolves the LED lazily (keyd re-creates input devices, so it may appear after startup)
    and hands it back to firmware on exit via `restore()`."""
    def __init__(self, link):
        self.link = link
        self.captured = False
        self.led = None

    def restore(self):
        if self.led:
            self.led.restore()

    def run(self):
        while True:
            if self.led is None:
                d = led.find_led()
                if d:
                    self.led = led.Led(d)
                    log(f"status LED: {d} ({'rgb' if self.led.multicolor else 'mono'})")
                else:
                    time.sleep(2)
                    continue
            if not self.link.interrupt:
                self.led.off()
                time.sleep(0.7)
            elif self.captured:
                self.led.color("red")              # solid red — input redirected to the target
                time.sleep(0.7)
            else:
                self.led.color("green")            # connected/idle green heartbeat
                time.sleep(0.12)
                self.led.off()
                time.sleep(1.8)


def _keepalive_ok(link):
    """No-op report keeps Windows from idle-dropping the link; a failure means the link is gone."""
    try:
        if link.interrupt:
            link.interrupt.send(hid.mouse_rel_report(0, 0, 0))
        return True
    except OSError:
        return False


def link_manager(bus, link):
    """Keep the HID link up. Prefer DEVICE-INITIATED reconnect to the paired host (so a daemon
    restart re-establishes the link itself — no "toggle it on Windows" dance); fall back to
    LISTENING for a host-initiated connect; reconnect on drop (detected via the keepalive)."""
    ctl_l = bluez.l2cap_listen(bluez.PSM_CONTROL)
    itr_l = bluez.l2cap_listen(bluez.PSM_INTERRUPT)
    log("listening on PSM 17/19 (host-initiated fallback)")
    while True:
        if not link.interrupt:
            mac = bluez.paired_device_mac(bus, config.load()["target"].get("mac"))
            if mac:
                try:
                    log(f"device-initiated connect to {mac}…")
                    link.control, link.interrupt = bluez.connect_to_host(mac)
                    log(f"HID link up (device-initiated → {mac})")
                except OSError as e:
                    log(f"device-initiated connect failed ({e}); waiting for host-initiated")
            if not link.interrupt:                      # fall back: wait for the host to connect
                c, _ = ctl_l.accept()
                i, ia = itr_l.accept()
                link.control, link.interrupt = c, i
                log(f"HID link up (host-initiated ← {ia[0]})")
        time.sleep(15)
        if not _keepalive_ok(link):
            log("HID link lost — re-establishing")
            for s in (link.control, link.interrupt):
                try:
                    if s:
                        s.close()
                except OSError:
                    pass
            link.control = link.interrupt = None


def serve(link, jiggler):
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
                        handle_line(link, jiggler, line.decode(errors="replace").strip())
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

    global LEDCTL
    link = bluez.HidLink()
    # The link manager maintains the BT HID link in the background (device-initiated + fallback +
    # reconnect). The command socket + jiggler run immediately — commands to a down link just drop.
    threading.Thread(target=link_manager, args=(bus, link), daemon=True).start()
    LEDCTL = LedController(link)
    threading.Thread(target=LEDCTL.run, daemon=True).start()
    jiggler = Jiggler(link)
    threading.Thread(target=jiggler.run, daemon=True).start()
    jc = config.load()["jiggler"]     # daemon-side default; the agent relays the user's config
    jiggler.configure(jc["enable"], jc["interval_sec"], jc["pixels"])

    log("serving commands (BT link maintained in background) — Ctrl-C to quit")
    try:
        serve(link, jiggler)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        if LEDCTL:
            LEDCTL.restore()
        bluez.cleanup(profilemgr, agentmgr, registered)
        if os.path.exists(SOCK_PATH):
            os.unlink(SOCK_PATH)
        log("bye")


if __name__ == "__main__":
    main()

"""
Session capture agent (part of `detachment`, the user service).

Subclasses `capture.InputCapture` and, while captured, integrates the relative libei deltas into an
absolute position in the target's PRIMARY-monitor space (`geometry`) and streams `A`/`K` commands to
the root HID emitter (`detachment-hidd`) over its unix socket. The cursor crosses the configured
screen edge and drives the target — with no software on it.

Config (`~/.config/detachment/config.json`): barrier edge, target primary size, release options
(walk-back to the entry edge + CapsLock+Esc), scroll (invert/speed). CapsLock is never forwarded.
"""
import socket
import time

import dbus
from gi.repository import GLib

import snegg.ei as ei

from . import capture, config, evdev_hid, geometry

SOCK_PATH = config.SOCKET_PATH

KEY_ESC, KEY_CAPSLOCK = 1, 58
# HID mouse buttons: bit0 L, bit1 R, bit2 M, bit3 Back(4), bit4 Forward(5).
# libinput/evdev back/forward vary (SIDE/BACK -> back; EXTRA/FORWARD -> forward), so map all.
BTN_BIT = {
    272: 0x01,   # BTN_LEFT
    273: 0x02,   # BTN_RIGHT
    274: 0x04,   # BTN_MIDDLE
    275: 0x08,   # BTN_SIDE    -> back
    278: 0x08,   # BTN_BACK    -> back
    276: 0x10,   # BTN_EXTRA   -> forward
    277: 0x10,   # BTN_FORWARD -> forward
}
ABS_MIN_INTERVAL = 0.008   # coalesce absolute motion to ~125 Hz (BT interrupt channel is narrow)


def log(msg):
    print(f"[agent] {msg}", flush=True)


class Agent(capture.InputCapture):
    def __init__(self, bus, loop):
        super().__init__(bus, loop)          # sets self.edge from config
        cfg = config.load()
        tgt = cfg["target"]
        self._tw, self._th = int(tgt["width"]), int(tgt["height"])
        self._walk_back = bool(cfg["release"]["walk_back"])
        self._capslock_esc = bool(cfg["release"]["capslock_esc"])
        sc = cfg["scroll"]
        self._scroll_sign = -1.0 if sc["invert_vertical"] else 1.0   # HID wheel +up = -dy already
        self._detent = float(sc["detent_120"])
        self._smooth = float(sc["smooth_px"])

        self.captured = False
        self.activation_id = 0
        self.vc = None
        self.buttons = 0
        self.capslock_down = False
        self.kmod = 0
        self.kkeys = []
        self._wheel_acc = 0.0
        self._pan_acc = 0.0
        self._last_abs = 0.0
        self._hid_ok = False
        self.hidsock = None
        self._connect_hid()

    # ── target output ────────────────────────────────────────────────────────────────────────
    def _connect_hid(self):
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(SOCK_PATH)
            self.hidsock = s
            if not self._hid_ok:
                log(f"connected to HID daemon at {SOCK_PATH}")
            self._hid_ok = True
            return True
        except OSError as e:
            if self._hid_ok or self.hidsock is None:
                log(f"HID daemon unavailable at {SOCK_PATH} ({e}); is detachment-hidd running?")
            self.hidsock = None
            self._hid_ok = False
            return False

    def _send(self, msg):
        """Send a line; transparently reconnect once if the daemon restarted (stale socket)."""
        data = msg.encode()
        try:
            if self.hidsock:
                self.hidsock.sendall(data)
                return
        except OSError:
            self._hid_ok = False
        if self._connect_hid():
            try:
                self.hidsock.sendall(data)
            except OSError:
                self._hid_ok = False

    def _send_abs(self, wheel=0, pan=0):
        if not self.vc:
            return
        x, y = self.vc.hid()
        self._send(f"A {x} {y} {self.buttons} {wheel} {pan}\n")

    def _scroll(self, wheel_units, pan_units):
        """Accumulate fractional scroll and emit integer HID wheel/pan steps (clamped int8)."""
        self._wheel_acc += wheel_units
        self._pan_acc += pan_units
        w, p = int(self._wheel_acc), int(self._pan_acc)   # trunc toward zero
        if w or p:
            self._wheel_acc -= w
            self._pan_acc -= p
            self._send_abs(wheel=max(-127, min(127, w)), pan=max(-127, min(127, p)))

    def _send_keys(self):
        keys = (self.kkeys[:6] + [0, 0, 0, 0, 0, 0])[:6]
        self._send("K " + str(self.kmod) + " " + " ".join(str(c) for c in keys) + "\n")

    def release(self):
        if not self.captured:
            return
        self.captured = False
        self.buttons = 0
        self.kmod = 0
        self.kkeys = []
        self._send_abs()   # drop held buttons on the target
        self._send_keys()  # release held keys on the target
        try:
            self.portal.Release(self.session,
                                {"activation_id": dbus.UInt32(self.activation_id)},
                                signature="oa{sv}")
        except dbus.DBusException as e:
            log(f"Release failed: {e.get_dbus_name()}")
        log("released -> LOCAL")

    # ── portal activation ───────────────────────────────────────────────────────────────────
    def _on_activated(self, session, options):
        self.activation_id = int(options.get("activation_id", 0))
        pos = options.get("cursor_position")
        zw, zh, _, _ = (int(v) for v in self.zones[0])   # this box's zone size
        self.vc = geometry.VirtualCursor(self._tw, self._th, self.edge)
        # fraction along the barrier where we crossed: vertical edge -> Y/zh, horizontal -> X/zw
        if pos:
            frac = (float(pos[1]) / zh) if self.vc.vertical_barrier() else (float(pos[0]) / zw)
        else:
            frac = 0.5
        self.vc.seed(frac)
        self.buttons = 0
        self.kmod = 0
        self.kkeys = []
        self.captured = True
        self._send_abs()
        log(f"╔═ CAPTURED — driving target (edge={self.edge})")

    def _on_deactivated(self, session, options):
        self.captured = False
        log("╚═ LOCAL")

    # ── the event glue ──────────────────────────────────────────────────────────────────────
    def _on_ei_event(self, *_):
        self.receiver.dispatch()
        for e in self.receiver.events:
            t = e.event_type
            if t == ei.EventType.SEAT_ADDED:
                self._seat = e.seat
                self._seat.bind()
                log(f"SEAT_ADDED -> bound {self._seat.capabilities}")
            elif t == ei.EventType.DEVICE_ADDED:
                self._devices.append(e.device)
            elif t == ei.EventType.POINTER_MOTION and self.captured:
                p = e.pointer_event
                self.vc.move(p.dx, p.dy)
                if self._walk_back and self.vc.at_exit_edge():
                    log("walked back to entry edge")
                    self.release()
                else:
                    now = time.monotonic()   # coalesce: only the latest position matters
                    if now - self._last_abs >= ABS_MIN_INTERVAL:
                        self._send_abs()
                        self._last_abs = now
            elif t == ei.EventType.BUTTON_BUTTON and self.captured:
                b = e.button_event
                bit = BTN_BIT.get(b.button, 0)
                if bit:
                    self.buttons = (self.buttons | bit) if b.is_press else (self.buttons & ~bit)
                    self._send_abs()
            elif t == ei.EventType.SCROLL_DISCRETE and self.captured:
                s = e.scroll_discrete_event            # 120ths of a detent; HID wheel +up = -dy
                self._scroll(-s.dy / self._detent * self._scroll_sign, s.dx / self._detent)
            elif t == ei.EventType.SCROLL_DELTA and self.captured:
                s = e.scroll_event                     # smooth px
                self._scroll(-s.dy / self._smooth * self._scroll_sign, s.dx / self._smooth)
            elif t == ei.EventType.KEYBOARD_KEY:
                self._on_key(e.key_event)
        return True

    def _on_key(self, k):
        code, press = k.key, k.is_press
        # CapsLock is the detachment leader — never forwarded; CapsLock+Esc = panic release.
        if code == KEY_CAPSLOCK:
            self.capslock_down = press
            return
        if code == KEY_ESC and press and self.capslock_down and self._capslock_esc:
            log("CapsLock+Esc panic release")
            self.release()
            return
        if not self.captured:
            return
        # keyboard passthrough: translate evdev -> HID and stream the full report state
        if code in evdev_hid.MOD:
            bit = evdev_hid.MOD[code]
            self.kmod = (self.kmod | bit) if press else (self.kmod & ~bit)
            self._send_keys()
            return
        usage = evdev_hid.HID.get(code)
        if usage is None:
            return   # unmapped key
        if press:
            if usage not in self.kkeys:
                self.kkeys.append(usage)
        elif usage in self.kkeys:
            self.kkeys.remove(usage)
        self._send_keys()


def run(bus=None, loop=None):
    """Create + start the agent on a session bus and GLib loop (reused by the tray app)."""
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = bus or dbus.SessionBus()
    loop = loop or GLib.MainLoop()
    ag = Agent(bus, loop)
    ag.start()
    return ag, loop


def main():
    try:
        _, loop = run()
        loop.run()
    except dbus.DBusException as e:
        log(f"D-Bus error: {e.get_dbus_name()}: {e.get_dbus_message()}")
    except KeyboardInterrupt:
        pass
    log("bye")


if __name__ == "__main__":
    main()

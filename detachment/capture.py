"""
Wayland input capture — the ``org.freedesktop.portal.InputCapture`` portal + libei (via snegg).

Arms a pointer barrier on the configured screen edge (config `barrier_edge`); on crossing, the
portal hands an EIS socket we feed to snegg's Receiver. `InputCapture` is the base class — the agent
subclasses it to turn captured events into HID. Must run inside the graphical session (the portal
talks to the session bus + mutter). oeffis only speaks the RemoteDesktop portal, so we drive
InputCapture directly over D-Bus and use snegg only for the EIS event stream.
"""
import os

import dbus
import dbus.mainloop.glib
from gi.repository import GLib

import snegg.ei as ei

from . import config

PORTAL_NAME = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
IC_IFACE = "org.freedesktop.portal.InputCapture"
REQ_IFACE = "org.freedesktop.portal.Request"

CAP_KEYBOARD = 1
CAP_POINTER = 2

BARRIER_ID = 1


def log(msg):
    print(f"[capture] {msg}", flush=True)


class _FdHolder:
    """Wrap a raw fd int so snegg's Receiver.create_for_fd (which calls fd.fileno()) accepts it."""
    def __init__(self, fd):
        self._fd = fd

    def fileno(self):
        return self._fd


class InputCapture:
    def __init__(self, bus, loop):
        self.bus = bus
        self.loop = loop
        self.portal = dbus.Interface(bus.get_object(PORTAL_NAME, PORTAL_PATH), IC_IFACE)
        self.props = dbus.Interface(bus.get_object(PORTAL_NAME, PORTAL_PATH),
                                    "org.freedesktop.DBus.Properties")
        self.sender_token = bus.get_unique_name()[1:].replace(".", "_")
        self.edge = config.load().get("barrier_edge", "right")
        self.session = None
        self.zone_set = None
        self.zones = None
        self.receiver = None
        self._seat = None
        self._devices = []   # keep device refs alive (snegg refcounts; GC would drop them)
        self._req_serial = 0
        self.ready = False        # portal session set up (barrier can be armed)
        self.armed = False        # barrier currently enabled
        self.on_state_change = None  # callback (tray) invoked on ready/armed/captured changes

    # ── portal Request/Response helper ───────────────────────────────────────────────────────
    def _new_token(self, kind):
        self._req_serial += 1
        return f"detach_{kind}_{self._req_serial}"

    def call(self, method, sig, args, token, on_response):
        """Call a portal method whose options dict already carries handle_token=`token` (positioned
        correctly within `args`); wire the one-shot Response matched on the Request path."""
        expected = f"{PORTAL_PATH}/request/{self.sender_token}/{token}"
        match = None

        def handler(response, results):
            if match:
                match.remove()
            if response != 0:
                log(f"{method} FAILED (response={response})")
                self.loop.quit()
                return
            on_response(results)

        match = self.bus.add_signal_receiver(
            handler, signal_name="Response", dbus_interface=REQ_IFACE, path=expected)
        getattr(self.portal, method)(*args, signature=sig)

    # ── flow: CreateSession → GetZones → SetPointerBarriers → ConnectToEIS → Enable ─────────
    def start(self):
        caps = self.props.Get(IC_IFACE, "SupportedCapabilities")
        log(f"portal SupportedCapabilities = {int(caps)} (POINTER=2, KEYBOARD=1)")
        log("CreateSession…")
        token = self._new_token("req")
        # CreateSession(IN s parent_window, IN a{sv} options) — parent_window "" (no parent).
        self.call("CreateSession", "sa{sv}",
                  ["", {"handle_token": token,
                        "session_handle_token": self._new_token("session"),
                        "capabilities": dbus.UInt32(CAP_POINTER | CAP_KEYBOARD)}],
                  token, self._on_session)

    def _on_session(self, results):
        self.session = dbus.ObjectPath(results["session_handle"])
        log(f"session = {self.session}")
        log("GetZones…")
        token = self._new_token("req")
        self.call("GetZones", "oa{sv}", [self.session, {"handle_token": token}],
                  token, self._on_zones)

    def _on_zones(self, results):
        self.zone_set = results["zone_set"]
        self.zones = results["zones"]   # a(uuii): width, height, x, y
        log(f"zones (set {int(self.zone_set)}): {[tuple(int(v) for v in z) for z in self.zones]}")
        # Barrier on the RIGHT edge of the first zone: a vertical line x=right, y=top..bottom.
        w, h, zx, zy = (int(v) for v in self.zones[0])
        pos = self._barrier_line(w, h, zx, zy)   # line sits ON the edge, not one pixel inside
        barrier = {"barrier_id": dbus.UInt32(BARRIER_ID),
                   "position": dbus.Struct(pos, signature="iiii")}
        log(f"SetPointerBarriers ({self.edge} edge): {pos}")
        token = self._new_token("req")
        self.call("SetPointerBarriers", "oa{sv}aa{sv}u",
                  [self.session, {"handle_token": token},
                   dbus.Array([barrier], signature="a{sv}"), dbus.UInt32(self.zone_set)],
                  token, self._on_barriers)

    def _barrier_line(self, w, h, zx, zy):
        """A line along the requested edge of the (first) zone, as (x1,y1,x2,y2)."""
        if self.edge == "left":
            return (zx, zy, zx, zy + h)
        if self.edge == "top":
            return (zx, zy, zx + w, zy)
        if self.edge == "bottom":
            return (zx, zy + h, zx + w, zy + h)
        return (zx + w, zy, zx + w, zy + h)   # right (default)

    def _on_barriers(self, results):
        failed = [int(x) for x in results.get("failed_barriers", [])]
        if failed:
            log(f"WARNING failed barriers: {failed}")
        else:
            log("barrier accepted")
        # ConnectToEIS returns a fd directly (not a Request).
        log("ConnectToEIS…")
        fd = self.portal.ConnectToEIS(self.session, {}, signature="oa{sv}")
        eis_fd = fd.take()
        log(f"EIS fd = {eis_fd}; creating snegg Receiver")
        self._eis = _FdHolder(eis_fd)   # keep a ref so the fd isn't GC'd/closed
        self.receiver = ei.Receiver.create_for_fd(self._eis, "detachment-capture")
        GLib.io_add_watch(self.receiver.fd, GLib.IO_IN, self._on_ei_event)
        # Activation signals.
        self.bus.add_signal_receiver(self._on_activated, signal_name="Activated",
                                     dbus_interface=IC_IFACE)
        self.bus.add_signal_receiver(self._on_deactivated, signal_name="Deactivated",
                                     dbus_interface=IC_IFACE)
        self.ready = True
        log("capture session ready")
        self._on_ready()

    def _on_ready(self):
        """Hook fired once the portal session is set up. Default: arm immediately (CLI/standalone).
        The tray overrides this to stay disarmed until the user enables it."""
        self.enable()

    def enable(self):
        """Arm the barrier (portal Enable)."""
        if not self.ready or self.armed:
            return
        self.portal.Enable(self.session, {}, signature="oa{sv}")
        self.armed = True
        log(f"barrier ARMED on the {self.edge} edge")
        self._notify()

    def disable(self):
        """Disarm the barrier (release if captured, then portal Disable)."""
        if not self.armed:
            return
        if getattr(self, "captured", False) and hasattr(self, "release"):
            self.release()
        try:
            self.portal.Disable(self.session, {}, signature="oa{sv}")
        except dbus.DBusException as e:
            log(f"Disable failed: {e.get_dbus_name()}")
        self.armed = False
        log("barrier DISARMED")
        self._notify()

    def _notify(self):
        if self.on_state_change:
            self.on_state_change()

    def _on_activated(self, session, options):
        pos = options.get("cursor_position")
        log(f"╔═ CAPTURED (activation {int(options.get('activation_id', 0))}) at {tuple(pos) if pos else '?'}")

    def _on_deactivated(self, session, options):
        log("╚═ released back to LOCAL")

    def _on_ei_event(self, *_):
        self.receiver.dispatch()
        events = self.receiver.events
        for e in events:
            t = e.event_type
            if t == ei.EventType.POINTER_MOTION:
                p = e.pointer_event
                print(f"    move dx={p.dx:+.1f} dy={p.dy:+.1f}", flush=True)
            elif t == ei.EventType.BUTTON_BUTTON:
                b = e.button_event
                print(f"    button {b.button} {'down' if b.is_press else 'up'}", flush=True)
            elif t == ei.EventType.KEYBOARD_KEY:
                k = e.key_event
                print(f"    key {k.key} {'down' if k.is_press else 'up'}", flush=True)
            elif t in (ei.EventType.SCROLL_DELTA, ei.EventType.SCROLL_DISCRETE):
                s = e.scroll_event
                print(f"    scroll {s}", flush=True)
            elif t == ei.EventType.SEAT_ADDED:
                # MUST bind the seat's capabilities or the EIS never creates devices (no motion).
                self._seat = e.seat
                self._seat.bind()   # None => bind all offered caps
                log(f"SEAT_ADDED -> bound {self._seat.capabilities}")
            elif t == ei.EventType.DEVICE_ADDED:
                self._devices.append(e.device)
                log(f"DEVICE_ADDED: {e.device.name} caps={e.device.capabilities}")
            elif t in (ei.EventType.CONNECT, ei.EventType.DEVICE_RESUMED, ei.EventType.DEVICE_PAUSED,
                       ei.EventType.DEVICE_REMOVED, ei.EventType.DISCONNECT):
                log(f"lifecycle: {t.name}")
            # FRAME + others ignored silently
        return True


def main():
    if not os.environ.get("WAYLAND_DISPLAY") and not os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        log("WARNING: no session bus / Wayland display in env — must run inside jt's GNOME session")
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    loop = GLib.MainLoop()
    ic = InputCapture(bus, loop)
    try:
        ic.start()
        loop.run()
    except dbus.DBusException as e:
        log(f"D-Bus error: {e.get_dbus_name()}: {e.get_dbus_message()}")
    except KeyboardInterrupt:
        pass
    log("bye")


if __name__ == "__main__":
    main()

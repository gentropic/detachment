"""
GlobalShortcuts portal client — register global shortcuts that the compositor handles ABOVE the
capture layer, so they fire even while detachment is capturing input (unlike keys in the captured
stream). With keyd mapping CapsLock→Hyper, "Hyper+Esc" reaches GNOME as Ctrl+Alt+Shift+Super+Escape;
we register that as the release shortcut (and Hyper+F1..F12 as target-switch stubs for later).

GNOME may prompt once to allow/confirm the shortcut, and you may need to set the actual trigger in
Settings → Keyboard the first time (portals expose `preferred_trigger` as a hint only).
"""
import dbus
from gi.repository import GLib  # noqa: F401

PORTAL_NAME = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
GS_IFACE = "org.freedesktop.portal.GlobalShortcuts"
REQ_IFACE = "org.freedesktop.portal.Request"

# Hyper (keyd's C-A-M-S) + Escape, in the portal's accelerator syntax.
RELEASE_TRIGGER = "CTRL+ALT+SHIFT+SUPER+Escape"


def log(msg):
    print(f"[shortcuts] {msg}", flush=True)


class GlobalShortcuts:
    def __init__(self, bus, on_activated):
        self.bus = bus
        self.on_activated = on_activated          # callback(shortcut_id: str)
        self.portal = dbus.Interface(bus.get_object(PORTAL_NAME, PORTAL_PATH), GS_IFACE)
        self.sender_token = bus.get_unique_name()[1:].replace(".", "_")
        self.session = None
        self._serial = 0

    def _token(self, kind):
        self._serial += 1
        return f"detach_gs_{kind}_{self._serial}"

    def _call(self, method, sig, args, token, on_response):
        expected = f"{PORTAL_PATH}/request/{self.sender_token}/{token}"
        match = None

        def handler(response, results):
            if match:
                match.remove()
            if response != 0:
                log(f"{method} failed (response={response})")
                return
            on_response(results)

        match = self.bus.add_signal_receiver(
            handler, signal_name="Response", dbus_interface=REQ_IFACE, path=expected)
        getattr(self.portal, method)(*args, signature=sig)

    def start(self):
        try:
            token = self._token("req")
            self._call("CreateSession", "a{sv}",
                       [{"handle_token": token, "session_handle_token": self._token("session")}],
                       token, self._on_session)
        except dbus.DBusException as e:
            log(f"GlobalShortcuts unavailable: {e.get_dbus_name()}")

    def _on_session(self, results):
        self.session = dbus.ObjectPath(results["session_handle"])
        shortcuts = dbus.Array([
            dbus.Struct(("release", {
                "description": dbus.String("detachment: release capture back to this box"),
                "preferred_trigger": dbus.String(RELEASE_TRIGGER),
            }), signature="sa{sv}"),
        ], signature="(sa{sv})")
        token = self._token("req")
        self._call("BindShortcuts", "oa(sa{sv})sa{sv}",
                   [self.session, shortcuts, "", {"handle_token": token}],
                   token, self._on_bound)

    def _on_bound(self, results):
        log("global shortcuts bound (Hyper+Esc → release)")
        self.bus.add_signal_receiver(self._on_act, signal_name="Activated", dbus_interface=GS_IFACE)

    def _on_act(self, session, shortcut_id, timestamp, options):
        log(f"activated: {shortcut_id}")
        self.on_activated(str(shortcut_id))

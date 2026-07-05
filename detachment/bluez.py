"""
Classic Bluetooth HID *device* over BlueZ + L2CAP.

Makes this box advertise itself as a Bluetooth keyboard + mouse: an auto-accept pairing agent, the
HID SDP record (via ProfileManager1), and the two HID L2CAP channels (control 17 / interrupt 19) a
paired host connects to. `HidLink.send()` pushes input reports on the interrupt channel.

Requires bluetoothd running with `--noplugin=input` (so BlueZ yields the HID role and frees PSMs
17/19) — set declaratively by the gcunix detachment module.
"""
import socket

import dbus
import dbus.service
from gi.repository import GLib  # noqa: F401  (imported so callers can rely on GI being initialised)

from . import hid

BUS_NAME = "org.bluez"
ADAPTER_IFACE = "org.bluez.Adapter1"
PROFILEMGR_IFACE = "org.bluez.ProfileManager1"
AGENTMGR_IFACE = "org.bluez.AgentManager1"

HID_UUID = "00001124-0000-1000-8000-00805f9b34fb"
AGENT_PATH = "/detachment/agent"
PROFILE_PATH = "/detachment/profile"

PSM_CONTROL = 0x11    # 17
PSM_INTERRUPT = 0x13  # 19
BDADDR_ANY = "00:00:00:00:00:00"

ADAPTER_ALIAS = "detachment"


def log(msg):
    print(f"[bluez] {msg}", flush=True)


# ── BlueZ pairing agent: auto-accept (we pair deliberately, to chosen targets) ───────────────
class AutoAgent(dbus.service.Object):
    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Release(self):
        pass

    @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="")
    def AuthorizeService(self, device, uuid):
        log(f"authorize service {uuid} for {device} -> yes")

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="")
    def RequestAuthorization(self, device):
        log(f"authorize device {device} -> yes")

    @dbus.service.method("org.bluez.Agent1", in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        log(f"confirm passkey {passkey:06} for {device} -> yes")

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="u")
    def RequestPasskey(self, device):
        return dbus.UInt32(0)

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="s")
    def RequestPinCode(self, device):
        return "0000"

    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Cancel(self):
        log("pairing cancelled")


# ── A no-op HID Profile1 (registered only to publish the SDP record) ─────────────────────────
class HidProfile(dbus.service.Object):
    @dbus.service.method("org.bluez.Profile1", in_signature="", out_signature="")
    def Release(self):
        pass

    @dbus.service.method("org.bluez.Profile1", in_signature="oha{sv}", out_signature="")
    def NewConnection(self, device, fd, properties):
        # We service the fixed HID PSMs (17/19) with our own L2CAP sockets; this is informational.
        log(f"profile NewConnection from {device}")

    @dbus.service.method("org.bluez.Profile1", in_signature="o", out_signature="")
    def RequestDisconnection(self, device):
        log(f"profile RequestDisconnection {device}")


def find_adapter(bus):
    mgr = dbus.Interface(bus.get_object(BUS_NAME, "/"), "org.freedesktop.DBus.ObjectManager")
    for path, ifaces in mgr.GetManagedObjects().items():
        if ADAPTER_IFACE in ifaces:
            return path
    raise RuntimeError("no Bluetooth adapter found")


def setup_bluez(bus):
    """Make the adapter discoverable/pairable, register the auto-accept agent + HID SDP record.
    Returns (profilemgr, agentmgr, registered) for cleanup()."""
    adapter_path = find_adapter(bus)
    log(f"adapter {adapter_path}")
    props = dbus.Interface(bus.get_object(BUS_NAME, adapter_path),
                           "org.freedesktop.DBus.Properties")
    props.Set(ADAPTER_IFACE, "Alias", ADAPTER_ALIAS)
    props.Set(ADAPTER_IFACE, "Powered", dbus.Boolean(True))
    props.Set(ADAPTER_IFACE, "Pairable", dbus.Boolean(True))
    props.Set(ADAPTER_IFACE, "Discoverable", dbus.Boolean(True))
    props.Set(ADAPTER_IFACE, "DiscoverableTimeout", dbus.UInt32(0))

    AutoAgent(bus, AGENT_PATH)
    agentmgr = dbus.Interface(bus.get_object(BUS_NAME, "/org/bluez"), AGENTMGR_IFACE)
    agentmgr.RegisterAgent(AGENT_PATH, "NoInputNoOutput")
    agentmgr.RequestDefaultAgent(AGENT_PATH)
    log("auto-accept agent registered")

    HidProfile(bus, PROFILE_PATH)
    profilemgr = dbus.Interface(bus.get_object(BUS_NAME, "/org/bluez"), PROFILEMGR_IFACE)
    opts = {
        "ServiceRecord": hid.SDP_RECORD_XML,
        "Role": "server",
        "RequireAuthentication": dbus.Boolean(False),
        "RequireAuthorization": dbus.Boolean(False),
    }
    registered = False
    try:
        profilemgr.RegisterProfile(PROFILE_PATH, HID_UUID, opts)
        registered = True
        log("HID SDP record registered")
    except dbus.DBusException as e:
        # Usually a prior run didn't clean up; we unregister on exit, but a hard kill can strand it:
        # `systemctl restart bluetooth` (or reset-bt) clears it.
        log(f"RegisterProfile failed ({e.get_dbus_name()}); continuing with L2CAP only")
    return profilemgr, agentmgr, registered


def cleanup(profilemgr, agentmgr, registered):
    """Unregister so a killed run never leaves 0x1124 'already registered' for the next one."""
    try:
        if registered:
            profilemgr.UnregisterProfile(PROFILE_PATH)
        agentmgr.UnregisterAgent(AGENT_PATH)
        log("unregistered profile + agent")
    except dbus.DBusException as e:
        log(f"cleanup warning: {e.get_dbus_name()}")


def l2cap_listen(psm):
    s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((BDADDR_ANY, psm))
    s.listen(1)
    return s


class HidLink:
    """Holds the accepted control+interrupt sockets and sends input reports to the host."""
    def __init__(self):
        self.control = None
        self.interrupt = None

    def send(self, report: bytes):
        if not self.interrupt:
            return
        try:
            self.interrupt.send(report)
        except OSError as e:
            log(f"send failed: {e}")


def accept_channels(link, on_ready):
    """Blocking: accept control(17) then interrupt(19), then call on_ready()."""
    ctl = l2cap_listen(PSM_CONTROL)
    itr = l2cap_listen(PSM_INTERRUPT)
    log("listening on PSM 17 (control) + 19 (interrupt); waiting for a target to connect…")
    link.control, caddr = ctl.accept()
    log(f"control connected from {caddr[0]}")
    link.interrupt, iaddr = itr.accept()
    log(f"interrupt connected from {iaddr[0]} — HID link up")
    on_ready()

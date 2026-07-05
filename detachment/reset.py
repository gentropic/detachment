"""
`detachment-reset` — remove all Bluetooth pairings from this box.

Use when a host can't reconnect after removing + re-adding the device: the host generates new
pairing keys, but this box keeps the old bond, so they mismatch ("can't connect"). Clearing the
bond lets you pair fresh. The daemon keeps the adapter discoverable/pairable, so just re-pair from
the host afterwards. Run as root:  sudo detachment-reset
"""
import sys

import dbus
import dbus.mainloop.glib

from . import bluez


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    try:
        bus = dbus.SystemBus()
        removed = bluez.remove_all_bonds(bus)
    except dbus.DBusException as e:
        print(f"detachment-reset: {e.get_dbus_name()} — run as root?", file=sys.stderr)
        sys.exit(1)
    print("removed bonds: " + ", ".join(removed) if removed else "no bonds to remove")
    print("Adapter stays discoverable/pairable — re-pair the target from the host now.")


if __name__ == "__main__":
    main()

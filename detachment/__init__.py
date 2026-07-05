"""detachment — a Linux box presents itself as a Bluetooth HID device and a screen-edge capture
region drives another computer, with no software on the target.

Package layout (graduating from the poc1/2/3 dirs):
  hid          — HID report descriptor, report builders, keymap
  bluez        — classic Bluetooth HID *device* over BlueZ + L2CAP
  hidd         — root HID-emitter daemon (BT link + unix-socket command server)
  capture      — Wayland InputCapture portal + libei (snegg) receiver
  geometry     — target coordinate space + deltas->absolute mapper
  evdev_hid    — evdev keycode -> HID usage map
  config       — ~/.config/detachment/config.json (barrier edge, target, release, scroll)
  agent        — session capture agent (integrate deltas -> HID commands)
  tray         — GTK tray + settings UI
"""

__version__ = "0.1.0"

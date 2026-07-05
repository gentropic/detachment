"""
evdev keycode -> USB HID usage (keyboard page 0x07), for detachment keyboard passthrough.

libei hands us Linux evdev keycodes (linux/input-event-codes.h); the BT HID keyboard report wants
HID usage IDs. MOD maps the 8 modifier keys to their HID modifier-byte bits; HID maps everything
else to its usage. US layout; extend as needed.
"""

# evdev modifier keycode -> HID modifier bit
MOD = {
    29: 0x01,   # KEY_LEFTCTRL
    42: 0x02,   # KEY_LEFTSHIFT
    56: 0x04,   # KEY_LEFTALT
    125: 0x08,  # KEY_LEFTMETA (Super/Win)
    97: 0x10,   # KEY_RIGHTCTRL
    54: 0x20,   # KEY_RIGHTSHIFT
    100: 0x40,  # KEY_RIGHTALT (AltGr)
    126: 0x80,  # KEY_RIGHTMETA
}

# evdev keycode -> HID usage
HID = {
    # letters
    30: 0x04, 48: 0x05, 46: 0x06, 32: 0x07, 18: 0x08, 33: 0x09, 34: 0x0A, 35: 0x0B,
    23: 0x0C, 36: 0x0D, 37: 0x0E, 38: 0x0F, 50: 0x10, 49: 0x11, 24: 0x12, 25: 0x13,
    16: 0x14, 19: 0x15, 31: 0x16, 20: 0x17, 22: 0x18, 47: 0x19, 17: 0x1A, 45: 0x1B,
    21: 0x1C, 44: 0x1D,
    # number row
    2: 0x1E, 3: 0x1F, 4: 0x20, 5: 0x21, 6: 0x22, 7: 0x23, 8: 0x24, 9: 0x25, 10: 0x26, 11: 0x27,
    # editing / whitespace / punctuation
    28: 0x28,   # enter
    1: 0x29,    # esc
    14: 0x2A,   # backspace
    15: 0x2B,   # tab
    57: 0x2C,   # space
    12: 0x2D, 13: 0x2E, 26: 0x2F, 27: 0x30, 43: 0x31,   # - = [ ] backslash
    39: 0x33, 40: 0x34, 41: 0x35, 51: 0x36, 52: 0x37, 53: 0x38,  # ; ' ` , . /
    # function keys
    59: 0x3A, 60: 0x3B, 61: 0x3C, 62: 0x3D, 63: 0x3E, 64: 0x3F,
    65: 0x40, 66: 0x41, 67: 0x42, 68: 0x43, 87: 0x44, 88: 0x45,
    # navigation / control
    99: 0x46, 70: 0x47, 119: 0x48, 110: 0x49, 102: 0x4A, 104: 0x4B,
    111: 0x4C, 107: 0x4D, 109: 0x4E, 106: 0x4F, 105: 0x50, 108: 0x51, 103: 0x52,
}

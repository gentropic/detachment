"""
detachment PoC-1 — HID layer.

The combined report descriptor jt advertises as a classic Bluetooth HID device, the SDP record
that wraps it, and a keymap for turning text into keyboard reports.

Three input reports (both mice are 5-button with vertical wheel + horizontal AC Pan):
  ID 1  Keyboard          modifier, reserved, keycode[6]
  ID 2  Mouse (relative)  buttons(5), dx, dy, wheel, pan                  (int8)
  ID 3  Pointer (abs)     buttons(5), x_lo,x_hi, y_lo,y_hi, wheel, pan    (x/y 0..32767)

Report 3 drives the capture edge (absolute = 1:1 with the target's PRIMARY monitor — Windows binds an
absolute pointer to a single display; see README limitations). Buttons: bit0 L, bit1 R, bit2 M,
bit3 Back(button 4), bit4 Forward(button 5). Quirk: coords floor at 1 (an all-zero report is dropped
by Windows).
"""

# ── HID report descriptor ───────────────────────────────────────────────────────────────────
REPORT_DESCRIPTOR = bytes([
    # ---- Report ID 1: Keyboard --------------------------------------------------------------
    0x05, 0x01,        # Usage Page (Generic Desktop)
    0x09, 0x06,        # Usage (Keyboard)
    0xA1, 0x01,        # Collection (Application)
    0x85, 0x01,        #   Report ID (1)
    0x05, 0x07,        #   Usage Page (Keyboard/Keypad)
    0x19, 0xE0,        #   Usage Minimum (Left Control)
    0x29, 0xE7,        #   Usage Maximum (Right GUI)
    0x15, 0x00,        #   Logical Minimum (0)
    0x25, 0x01,        #   Logical Maximum (1)
    0x75, 0x01,        #   Report Size (1)
    0x95, 0x08,        #   Report Count (8)
    0x81, 0x02,        #   Input (Data,Var,Abs)  ; 8 modifier bits
    0x95, 0x01,        #   Report Count (1)
    0x75, 0x08,        #   Report Size (8)
    0x81, 0x01,        #   Input (Const)         ; reserved byte
    0x95, 0x06,        #   Report Count (6)
    0x75, 0x08,        #   Report Size (8)
    0x15, 0x00,        #   Logical Minimum (0)
    0x25, 0x65,        #   Logical Maximum (101)
    0x05, 0x07,        #   Usage Page (Keyboard/Keypad)
    0x19, 0x00,        #   Usage Minimum (0)
    0x29, 0x65,        #   Usage Maximum (101)
    0x81, 0x00,        #   Input (Data,Array)    ; 6 keycodes
    0xC0,              # End Collection

    # ---- Report ID 2: Mouse (relative) — 5 buttons + wheel + AC Pan -------------------------
    0x05, 0x01,        # Usage Page (Generic Desktop)
    0x09, 0x02,        # Usage (Mouse)
    0xA1, 0x01,        # Collection (Application)
    0x85, 0x02,        #   Report ID (2)
    0x09, 0x01,        #   Usage (Pointer)
    0xA1, 0x00,        #   Collection (Physical)
    0x05, 0x09,        #     Usage Page (Button)
    0x19, 0x01,        #     Usage Minimum (1)
    0x29, 0x05,        #     Usage Maximum (5)    ; L, R, M, Back(4), Forward(5)
    0x15, 0x00,        #     Logical Minimum (0)
    0x25, 0x01,        #     Logical Maximum (1)
    0x95, 0x05,        #     Report Count (5)
    0x75, 0x01,        #     Report Size (1)
    0x81, 0x02,        #     Input (Data,Var,Abs)  ; 5 buttons
    0x95, 0x01,        #     Report Count (1)
    0x75, 0x03,        #     Report Size (3)
    0x81, 0x01,        #     Input (Const)         ; padding to a byte
    0x05, 0x01,        #     Usage Page (Generic Desktop)
    0x09, 0x30,        #     Usage (X)
    0x09, 0x31,        #     Usage (Y)
    0x15, 0x81,        #     Logical Minimum (-127)
    0x25, 0x7F,        #     Logical Maximum (127)
    0x75, 0x08,        #     Report Size (8)
    0x95, 0x02,        #     Report Count (2)
    0x81, 0x06,        #     Input (Data,Var,Rel)  ; dx, dy
    0x09, 0x38,        #     Usage (Wheel)         ; vertical scroll
    0x95, 0x01,        #     Report Count (1)
    0x81, 0x06,        #     Input (Data,Var,Rel)  ; wheel
    0x05, 0x0C,        #     Usage Page (Consumer)
    0x0A, 0x38, 0x02,  #     Usage (AC Pan)        ; horizontal scroll
    0x81, 0x06,        #     Input (Data,Var,Rel)  ; pan
    0xC0,              #   End Collection (Physical)
    0xC0,              # End Collection

    # ---- Report ID 3: Pointer (absolute) — 5 buttons + wheel + AC Pan -----------------------
    0x05, 0x01,        # Usage Page (Generic Desktop)
    0x09, 0x02,        # Usage (Mouse)
    0xA1, 0x01,        # Collection (Application)
    0x85, 0x03,        #   Report ID (3)
    0x09, 0x01,        #   Usage (Pointer)
    0xA1, 0x00,        #   Collection (Physical)
    0x05, 0x09,        #     Usage Page (Button)
    0x19, 0x01,        #     Usage Minimum (1)
    0x29, 0x05,        #     Usage Maximum (5)    ; L, R, M, Back(4), Forward(5)
    0x15, 0x00,        #     Logical Minimum (0)
    0x25, 0x01,        #     Logical Maximum (1)
    0x95, 0x05,        #     Report Count (5)
    0x75, 0x01,        #     Report Size (1)
    0x81, 0x02,        #     Input (Data,Var,Abs)  ; 5 buttons
    0x95, 0x01,        #     Report Count (1)
    0x75, 0x03,        #     Report Size (3)
    0x81, 0x01,        #     Input (Const)         ; padding
    0x05, 0x01,        #     Usage Page (Generic Desktop)
    0x09, 0x30,        #     Usage (X)
    0x09, 0x31,        #     Usage (Y)
    0x15, 0x00,        #     Logical Minimum (0)
    0x26, 0xFF, 0x7F,  #     Logical Maximum (32767)
    0x75, 0x10,        #     Report Size (16)
    0x95, 0x02,        #     Report Count (2)
    0x81, 0x02,        #     Input (Data,Var,Abs)  ; X, Y absolute
    0x09, 0x38,        #     Usage (Wheel)         ; vertical scroll
    0x15, 0x81,        #     Logical Minimum (-127)
    0x25, 0x7F,        #     Logical Maximum (127)
    0x75, 0x08,        #     Report Size (8)
    0x95, 0x01,        #     Report Count (1)
    0x81, 0x06,        #     Input (Data,Var,Rel)  ; wheel
    0x05, 0x0C,        #     Usage Page (Consumer)
    0x0A, 0x38, 0x02,  #     Usage (AC Pan)        ; horizontal scroll
    0x81, 0x06,        #     Input (Data,Var,Rel)  ; pan
    0xC0,              #   End Collection (Physical)
    0xC0,              # End Collection
])

# HID transaction header for an input report over the L2CAP interrupt channel:
#   (HIDP_TRANS_DATA 0xA0) | (HIDP_DATA_RTYPE_INPUT 0x01) = 0xA1
HIDP_INPUT = 0xA1

REPORT_ID_KEYBOARD = 0x01
REPORT_ID_MOUSE_REL = 0x02
REPORT_ID_POINTER_ABS = 0x03


def keyboard_report(modifier: int, keycodes) -> bytes:
    """0xA1, id=1, modifier, reserved, 6 keycodes (padded/truncated)."""
    keys = (list(keycodes) + [0, 0, 0, 0, 0, 0])[:6]
    return bytes([HIDP_INPUT, REPORT_ID_KEYBOARD, modifier & 0xFF, 0x00, *keys])


def mouse_rel_report(buttons: int, dx: int, dy: int, wheel: int = 0, pan: int = 0) -> bytes:
    return bytes([HIDP_INPUT, REPORT_ID_MOUSE_REL,
                  buttons & 0x1F, dx & 0xFF, dy & 0xFF, wheel & 0xFF, pan & 0xFF])


def pointer_abs_report(buttons: int, x: int, y: int, wheel: int = 0, pan: int = 0) -> bytes:
    x = max(1, min(32767, int(x)))   # floor at 1: an all-zero report is dropped by Windows
    y = max(1, min(32767, int(y)))
    return bytes([HIDP_INPUT, REPORT_ID_POINTER_ABS,
                  buttons & 0x1F, x & 0xFF, (x >> 8) & 0xFF,
                  y & 0xFF, (y >> 8) & 0xFF, wheel & 0xFF, pan & 0xFF])


# ── SDP record ──────────────────────────────────────────────────────────────────────────────
# Classic HID (HumanInterfaceDeviceService, 0x1124) service record. The report descriptor is
# embedded in the HIDDescriptorList (attribute 0x0206) as a hex string. Registered with BlueZ via
# ProfileManager1.RegisterProfile(..., {"ServiceRecord": SDP_RECORD_XML}).
SDP_RECORD_XML = """<?xml version="1.0" encoding="UTF-8" ?>
<record>
  <attribute id="0x0001">
    <sequence><uuid value="0x1124" /></sequence>
  </attribute>
  <attribute id="0x0004">
    <sequence>
      <sequence><uuid value="0x0100" /><uint16 value="0x0011" /></sequence>
      <sequence><uuid value="0x0011" /></sequence>
    </sequence>
  </attribute>
  <attribute id="0x0006">
    <sequence><uint16 value="0x656e" /><uint16 value="0x006a" /><uint16 value="0x0100" /></sequence>
  </attribute>
  <attribute id="0x0009">
    <sequence>
      <sequence><uuid value="0x1124" /><uint16 value="0x0100" /></sequence>
    </sequence>
  </attribute>
  <attribute id="0x000d">
    <sequence>
      <sequence>
        <sequence><uuid value="0x0100" /><uint16 value="0x0013" /></sequence>
        <sequence><uuid value="0x0011" /></sequence>
      </sequence>
    </sequence>
  </attribute>
  <attribute id="0x0100"><text value="detachment" /></attribute>
  <attribute id="0x0101"><text value="jt Bluetooth HID" /></attribute>
  <attribute id="0x0201"><uint16 value="0x0100" /></attribute>
  <attribute id="0x0202"><uint8 value="0x40" /></attribute>
  <attribute id="0x0203"><uint8 value="0x00" /></attribute>
  <attribute id="0x0204"><boolean value="true" /></attribute>
  <attribute id="0x0205"><boolean value="true" /></attribute>
  <attribute id="0x0206">
    <sequence>
      <sequence>
        <uint8 value="0x22" />
        <text encoding="hex" value="{descriptor_hex}" />
      </sequence>
    </sequence>
  </attribute>
  <attribute id="0x0207">
    <sequence>
      <sequence><uint16 value="0x0409" /><uint16 value="0x0100" /></sequence>
    </sequence>
  </attribute>
  <attribute id="0x020b"><uint16 value="0x0100" /></attribute>
  <attribute id="0x020c"><uint16 value="0x0c80" /></attribute>
  <attribute id="0x020d"><boolean value="false" /></attribute>
  <attribute id="0x020e"><boolean value="true" /></attribute>
  <attribute id="0x020f"><uint16 value="0x0640" /></attribute>
  <attribute id="0x0210"><uint16 value="0x0320" /></attribute>
</record>
""".replace("{descriptor_hex}", REPORT_DESCRIPTOR.hex())


# ── Keymap (subset ported from RelayKVM's relaykvm-adapter.js) ───────────────────────────────
MOD = {"ctrl": 0x01, "shift": 0x02, "alt": 0x04, "gui": 0x08, "win": 0x08, "meta": 0x08,
       "rctrl": 0x10, "rshift": 0x20, "ralt": 0x40, "altgr": 0x40, "rgui": 0x80}

KEYCODE = {
    **{c: 0x04 + i for i, c in enumerate("abcdefghijklmnopqrstuvwxyz")},
    "1": 0x1E, "2": 0x1F, "3": 0x20, "4": 0x21, "5": 0x22,
    "6": 0x23, "7": 0x24, "8": 0x25, "9": 0x26, "0": 0x27,
    "enter": 0x28, "return": 0x28, "esc": 0x29, "escape": 0x29,
    "backspace": 0x2A, "tab": 0x2B, "space": 0x2C, " ": 0x2C,
    "-": 0x2D, "=": 0x2E, "[": 0x2F, "]": 0x30, "\\": 0x31,
    ";": 0x33, "'": 0x34, "`": 0x35, ",": 0x36, ".": 0x37, "/": 0x38,
    "left": 0x50, "right": 0x4F, "up": 0x52, "down": 0x51,
    "home": 0x4A, "end": 0x4D, "pageup": 0x4B, "pagedown": 0x4E,
    "delete": 0x4C, "insert": 0x49,
    **{f"f{n}": 0x39 + n for n in range(1, 13)},  # f1..f12 -> 0x3A..0x45
}

# Characters that require Shift, and their unshifted base key.
_SHIFTED = {
    "!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7", "*": "8",
    "(": "9", ")": "0", "_": "-", "+": "=", "{": "[", "}": "]", "|": "\\",
    ":": ";", '"': "'", "<": ",", ">": ".", "?": "/", "~": "`",
}


def char_to_report(ch: str):
    """Return (modifier, keycode) for a single character, or None if unmappable."""
    if ch in _SHIFTED:
        return (MOD["shift"], KEYCODE[_SHIFTED[ch]])
    if ch.isalpha() and ch.isupper():
        return (MOD["shift"], KEYCODE[ch.lower()])
    code = KEYCODE.get(ch.lower())
    return None if code is None else (0, code)

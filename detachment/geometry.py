"""
Capture → target coordinate mapping.

libei gives relative deltas while captured; we integrate them into an absolute position in the
target's PRIMARY-monitor pixel space and emit that as an absolute HID report. (Absolute is
single-monitor on Windows — see README; multi-monitor would need relative mode.)

`VirtualCursor` is parameterised by the target size and the **barrier edge** — where the target
sits relative to this box. You enter the target from the *opposite* edge and return to local
control by walking the cursor back to that entry edge. Pure module: the agent feeds it the size +
edge from config.
"""
HID_ABS_MAX = 32767

# where you enter the target, given which of THIS box's edges you crossed:
#   barrier "right"  → target is on the right → you enter it from its LEFT edge, return to LEFT
_ENTRY = {"right": "left", "left": "right", "bottom": "top", "top": "bottom"}


def to_hid_abs(px, py, w, h):
    """0-based pixel (px,py) in a w×h space → 0..32767 HID coord. Floors at 1 (an all-zero report
    is dropped by Windows), so the top-left corner is reachable as (1,1)."""
    x = max(1, min(HID_ABS_MAX, round(px / w * HID_ABS_MAX)))
    y = max(1, min(HID_ABS_MAX, round(py / h * HID_ABS_MAX)))
    return x, y


class VirtualCursor:
    def __init__(self, width, height, edge="right"):
        self.w = float(width)
        self.h = float(height)
        self.edge = edge if edge in _ENTRY else "right"
        self.entry = _ENTRY[self.edge]
        self.x = self.w / 2
        self.y = self.h / 2

    def seed(self, frac):
        """frac ∈ [0,1] = where along this box's barrier the pointer crossed. Place the cursor at
        the corresponding point on the target's entry edge."""
        frac = max(0.0, min(1.0, frac))
        if self.entry == "left":
            self.x, self.y = 1.0, frac * self.h
        elif self.entry == "right":
            self.x, self.y = self.w - 1, frac * self.h
        elif self.entry == "top":
            self.x, self.y = frac * self.w, 1.0
        elif self.entry == "bottom":
            self.x, self.y = frac * self.w, self.h - 1

    def move(self, dx, dy):
        self.x = max(0.0, min(self.w - 1, self.x + dx))
        self.y = max(0.0, min(self.h - 1, self.y + dy))
        return self.x, self.y

    def hid(self):
        return to_hid_abs(self.x, self.y, self.w, self.h)

    def at_exit_edge(self):
        """True when the cursor has walked back to the entry edge → return control to this box."""
        if self.entry == "left":
            return self.x <= 0
        if self.entry == "right":
            return self.x >= self.w - 1
        if self.entry == "top":
            return self.y <= 0
        if self.entry == "bottom":
            return self.y >= self.h - 1
        return False

    def vertical_barrier(self):
        """True if the barrier is a vertical screen edge (left/right) → crossing fraction is along Y."""
        return self.edge in ("left", "right")

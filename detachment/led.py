"""
Status LED. Drives a multicolor power-button LED (Framework / ChromeOS EC: `chromeos:multicolor:power`)
to reflect capture state:

    off            no Bluetooth HID link
    green heartbeat connected / idle
    solid red      driving the target (your input is redirected — the alarming state)

Falls back to a plain on/off LED (e.g. `*::capslock`) if no multicolor LED is present, in which case
color names collapse to on/off. On exit the LED is handed back to its firmware trigger (the power LED
returns to its default white) rather than left dark.

The physical CapsLock key light on the Framework is EC-owned and NOT drivable via sysfs — hence the
power-button LED. `find_led()` prefers a multicolor power LED, then any multicolor, then capslock.
"""
import glob
import os

# color -> per-channel weights (matched against multi_index names, so channel order doesn't matter)
_COLORS = {
    "red":   {"red": 1.0},
    "green": {"green": 1.0},
    "blue":  {"blue": 1.0},
    "amber": {"amber": 1.0},
    "white": {"white": 1.0},   # falls back to red+green+blue if there's no white channel
}


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


def _write(path, val):
    try:
        with open(path, "w") as f:
            f.write(val)
        return True
    except OSError:
        return False


def find_led():
    """Directory of the best status LED, or None."""
    for pat in ("*multicolor*power*", "*multicolor*", "*power*", "*capslock*"):
        hits = sorted(glob.glob(f"/sys/class/leds/{pat}"))
        hits = [h for h in hits if os.path.isdir(h)]
        if hits:
            return hits[0]
    return None


class Led:
    """A status LED at a `/sys/class/leds/<name>` directory. Multicolor if it exposes `multi_index`."""

    def __init__(self, leddir):
        self.dir = leddir
        self.maxb = int(_read(os.path.join(leddir, "max_brightness")) or 1)
        self.channels = _read(os.path.join(leddir, "multi_index")).split()
        self.multicolor = bool(self.channels)
        self._orig_trigger = self._active_trigger()
        self._claimed = False

    def _p(self, name):
        return os.path.join(self.dir, name)

    def _active_trigger(self):
        t = _read(self._p("trigger"))
        if "[" in t and "]" in t:
            return t[t.find("[") + 1:t.find("]")]
        return "none"

    def _claim(self):
        # free the LED from its trigger so manual writes take effect (once)
        if not self._claimed:
            _write(self._p("trigger"), "none")
            self._claimed = True

    def _set_intensity(self, color):
        weights = _COLORS.get(color, {})
        if color == "white" and "white" not in self.channels:
            weights = {"red": 1.0, "green": 1.0, "blue": 1.0}
        vals = [str(int(self.maxb * weights.get(ch, 0.0))) for ch in self.channels]
        _write(self._p("multi_intensity"), " ".join(vals))

    def color(self, name):
        """Show a solid color (multicolor) or just turn on (mono)."""
        self._claim()
        if self.multicolor:
            self._set_intensity(name)
        _write(self._p("brightness"), str(self.maxb))

    def off(self):
        self._claim()
        _write(self._p("brightness"), "0")

    def restore(self):
        """Hand the LED back to firmware (power LED -> default white) instead of leaving it dark."""
        for trig in (self._orig_trigger, "chromeos-auto", "default"):
            if trig and trig != "none" and _write(self._p("trigger"), trig):
                self._claimed = False
                return
        self.off()

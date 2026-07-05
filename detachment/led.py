"""
Optional status LED. On a laptop with a CapsLock key light (e.g. the Framework), the root daemon
drives it to reflect capture state — a lit key means "your input is going to the target." Auto-
detects a `*::capslock` LED; no-op if there's none. (The light only stays reliably ours once
CapsLock is remapped away from its lock function — see the keyd Hyper mapping.)
"""
import glob


def find_led():
    for p in sorted(glob.glob("/sys/class/leds/*capslock*/brightness")):
        return p
    return None


def set_led(path, on):
    if not path:
        return
    try:
        with open(path, "w") as f:
            f.write("1" if on else "0")
    except OSError:
        pass

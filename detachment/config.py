"""
detachment configuration — ``~/.config/detachment/config.json``.

One JSON file, read by both the session agent and (the socket path) the root daemon. Plain stdlib
json so the GTK settings window can rewrite it trivially. Unknown keys are preserved; missing keys
fall back to DEFAULTS via a deep merge, so old config files keep working as the schema grows.

The schema is shaped for the multi-target future (a list of targets), but v1 ships a single active
target. "barrier_edge" is where the target sits *relative to jt's screen* — you cross that edge to
drive it (target is to my right → "right"; you re-enter jt by walking back through it).
"""
import copy
import json
import os
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "detachment"
CONFIG_PATH = CONFIG_DIR / "config.json"

SOCKET_PATH = "/run/detachment/hid.sock"   # where hidd listens; /run so it survives /tmp cleaners

EDGES = ("left", "right", "top", "bottom")

DEFAULTS = {
    "version": 1,
    # The active target. (Future: "targets": [ … ] + "active" index; v1 keeps one inline.)
    "target": {
        "name": "target",
        "width": 1920,          # target PRIMARY monitor size (absolute is single-monitor on Windows)
        "height": 1080,
        "mac": None,            # BT address to (re)connect to; None = whatever paired host connects
    },
    "barrier_edge": "right",    # left | right | top | bottom  — where the target is, relative to jt
    "release": {
        "walk_back": True,      # return to jt by walking the cursor back through the entry edge
        "capslock_esc": True,   # CapsLock+Esc panic release
    },
    "scroll": {
        "invert_vertical": False,
        "detent_120": 120.0,    # libei discrete units per HID wheel step
        "smooth_px": 60.0,      # smooth-scroll px per HID wheel step
    },
    "jiggler": {                # keep the target awake: a tiny move every ~interval (±30% jitter)
        "enable": False,
        "interval_sec": 30,
        "pixels": 2,
    },
    "socket": SOCKET_PATH,
}


def _deep_merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load():
    """Return the config: DEFAULTS deep-merged with the on-disk file (if any)."""
    try:
        raw = json.loads(CONFIG_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        raw = {}
    return _deep_merge(DEFAULTS, raw)


def save(cfg):
    """Write the config atomically (temp + replace)."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, indent=2) + "\n")
    tmp.replace(CONFIG_PATH)


def ensure():
    """Create the config file from DEFAULTS if it doesn't exist yet; return the loaded config."""
    if not CONFIG_PATH.exists():
        save(DEFAULTS)
    return load()

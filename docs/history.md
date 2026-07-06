# detachment — build history

The narrative the README no longer carries. detachment went from a "what if jt could pretend to be a
keyboard?" musing to a shipped two-service NixOS package in a single stretch on **2026-07-05**. Dates
below are that day unless noted; commit messages hold the fine detail.

## Origin

A sibling to [RelayKVM](https://github.com/endarthur/RelayKVM). RelayKVM offloads "be a HID device"
to a Pico dongle because browsers can't emit HID. The musing: jt (the gcunix Framework 13) runs
Linux/BlueZ, which *can* present as a Bluetooth HID device in software — so drop the dongle entirely
and drive another machine directly, with a Wayland screen-edge capture region as the "controller"
front-end. Named for the geologic detachment surface (RelayKVM = relay ramp).

Locked early: first target **Windows 11**; **classic BR/EDR HID** (profile `0x1124`), not BLE-HOGP;
capture via the **Wayland InputCapture portal + libei** (no X11); **absolute** pointer (1:1 mapping);
**Python**.

## PoC-1 — Bluetooth HID out

jt drives Windows 11 over classic BT HID: keyboard + relative mouse + **absolute pointer** all
confirmed. BlueZ over D-Bus (auto-accept `Agent1`, HID profile via `ProfileManager1.RegisterProfile`),
L2CAP PSMs 17/19 via stdlib `socket.AF_BLUETOOTH`.

Gotchas solved: `bluetoothd --noplugin=input` (+ `--compat`) to be an HID *device* and free the PSMs;
audio profiles (a2dp/avrcp/sap) stripped by default (else Windows shows "audio, mic" and may grab jt
as a speaker); the daemon must run during pairing and self-unregisters on `SIGTERM` so killed runs
don't strand `0x1124`; `abs 0 0` is a no-op (all-zero report dropped) → floor the mapper at 1.
**Absolute worked with a plain absolute-mouse report — no digitizer needed.**

## PoC-2 — Wayland input capture

jt captures its own kbd/mouse at the right screen edge and reports deltas. Python path settled on
**snegg** (Peter Hutterer's ctypes libei wrapper, git-only, not on PyPI/nixpkgs). snegg's `oeffis`
only drives the RemoteDesktop portal, so capture drives **InputCapture directly over D-Bus**
(CreateSession → GetZones → SetPointerBarriers → ConnectToEIS → Enable) and feeds the EIS fd to
`snegg.ei.Receiver`.

Portal-flow gotchas: `CreateSession` takes `(s parent_window, a{sv})`; `SetPointerBarriers` options
sit in the *middle* of its args; the barrier line must be *on* the edge (x = zone_x + zone_w);
`create_for_fd` needs an object with `.fileno()`; **must** call `seat.bind()` on `SEAT_ADDED` or no
devices/motion arrive. Runs in jt's live GNOME session.

**Multi-monitor finding:** on Windows, *both* a plain absolute mouse and a pen digitizer map to the
**primary monitor only** — an absolute pointing device binds to one display. Decision: keep absolute,
accept single-monitor (the real use is driving a headless/single-screen box). Multi-monitor would need
relative mode — deliberately not built (documented as a limitation, now a roadmap item).

## PoC-3 — the glue

Two processes, a privilege split: a **root HID emitter** (the PoC-1 BT link) serving a line protocol
on a unix socket, and a **user-session capture agent** (PoC-2) integrating libei deltas → target-space
absolute (`geometry.py`) → socket. Entry/exit state machine (walk-back release), keyboard passthrough,
scroll (5-button mouse: back/forward + vertical wheel + horizontal AC Pan; discrete 120ths + smooth
px, fractional-accumulate → int8 HID). Throttled absolute motion to ~125 Hz (the BT interrupt channel
is narrow; one report per motion event timed the link out).

## Productization (1.0)

Graduated `poc1/2/3` into the `detachment/` Python package with console scripts and config
(`~/.config/detachment/config.json`, deep-merged):

- **Package + config** — `pyproject.toml`, `config.py`, modules migrated to `detachment/{hid,bluez,
  hidd,capture,geometry,evdev_hid,agent,tray}.py`.
- **NixOS services** — `nix/snegg.nix` (buildPythonPackage from GitLab), `nix/package.nix`
  (buildPythonApplication; wraps the agent with `LD_LIBRARY_PATH=libei` since snegg dlopens it, +
  GTK/AppIndicator typelibs via `wrapGAppsHook3`), `nix/module.nix` (`services.detachment`: system
  `detachment-hidd` + user `detachment` + the `bluetoothd` tweaks). Run scripts retired.
- **Tray** — GTK3 AppIndicator (`tray.py`): the user service runs the capture agent in-process, comes
  up **disarmed**, menu = Enable / Jiggler / Settings… / Quit with live state. GTK3 because
  AppIndicator is GTK3-only; GNOME needs `gnomeExtensions.appindicator`.
- **Web arrangement editor** — retired the GTK settings *window* for a local web app (`websettings.py`
  + `web/`): a basalt-themed canvas that draws jt's monitors and lets you click an outer edge to
  attach the target, config form, live state; applies live via `GLib.idle_add`. `barrier_monitor`
  picks which of jt's monitors the edge attaches to.

## Spin-out

Moved from the (local-only) `agents` repo to its own **public** repo, **`github.com/gentropic/detachment`**,
consumed by gcunix as a flake input (`github:gentropic/detachment`). Public because it's a
general-purpose KVM tool with no secrets.

## Post-1.0 polish

- **Jiggler** — daemon-side keep-awake (tiny alternating move every ~30 s ±jitter), tray-toggleable.
- **keyd CapsLock → Hyper** — `overload(hyper, esc)` (hold = Ctrl+Alt+Super+Shift, tap = Esc) as a
  conflict-free command leader (gcunix `modules/keyd.nix`).
- **Device-initiated reconnect** — jt re-connects to the paired host on startup (like a real keyboard
  waking), so a daemon restart re-establishes the link itself; host-initiated listen as fallback +
  keepalive-driven reconnect. Plus a `detachment-reset` CLI to clear stale jt-side bonds (the usual
  "can't connect" cause).
- **Status LED** — the physical CapsLock key light is EC/firmware-owned (not sysfs-drivable), so
  status moved to the `chromeos:multicolor:power` RGB LED: off / green-heartbeat-over-white / solid
  red, restoring firmware white on exit. (Diagnostic: `scripts/led-test.sh`.)
- **Release saga** — the one that took iterations:
  1. **GlobalShortcuts portal** (Hyper+Esc) — dead end: `BindShortcuts` returns response 2, never
     honours `preferred_trigger`; the raw chord leaked to a **logout**. Deleted.
  2. **dconf custom keybinding → SIGUSR1** — better, but Escape is mutter-reserved (unreliable);
     switched to **Hyper+`** (backtick).
  3. Still flaky **during capture** — because mutter routes keys into the libei stream, so a
     keybinding fires only intermittently. Final design: **detect Hyper+backtick IN the captured
     stream** (`agent._on_key`) and `disable()` (release + disarm). The backtick keybinding was
     *removed* (it would steal the key from the stream). Arming stays a keybinding (**Hyper+F1** →
     SIGUSR2) because it happens when *not* capturing.
  4. **`cursor_position` on Release** — without the portal's `(dd)` option the local pointer returns
     *onto* the barrier and instantly re-crosses ("release does nothing"); re-home to jt's zone centre.

## State

Built, packaged, deployed on jt, confirmed working: keyboard + 5-button mouse + scroll + absolute
pointer over classic BT HID to Windows 11; self-healing link; live-applied config; web arrangement
editor; RGB status LED; Hyper+F1 arm / Hyper+backtick stand-down. Open: multi-target and cross-platform
relative mode (see the README roadmap).

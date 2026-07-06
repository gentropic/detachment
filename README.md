# detachment

> A *detachment* is the low-angle surface along which one crustal block slides a long way over
> another — the blocks stay coupled across it but move independently. Sibling to
> **[RelayKVM](https://github.com/endarthur/RelayKVM)** (named for relay ramps): same fault-structure
> naming whim, opposite topology.

**One machine's keyboard and mouse "detach" at a screen edge and slide onto a second machine —
which sees only a Bluetooth keyboard/mouse and runs no software at all.**

Software-free-on-the-target multi-machine input sharing, self-hosted. Think Synergy / Barrier /
Apple Universal Control, but the *target installs nothing* because the controlling box
(**jt** — the gcunix Framework 13) impersonates a Bluetooth HID device directly.

**Status: built and running.** Full keyboard + 5-button mouse + scroll + absolute pointer over
classic Bluetooth HID to a Windows 11 target, driven by a Wayland screen-edge capture region on jt.
Packaged as a NixOS flake (two systemd services), consumed by gcunix. Deployed on jt 2026-07-05.

---

## Why this is not RelayKVM

RelayKVM is a **relay**: a browser controller → (Web Bluetooth) → a Pico/Cardputer dongle →
(USB HID) → target. The dongle exists because a browser can't emit USB HID, and USB HID is
*universal* (works at BIOS, on any machine, no pairing). That universality is RelayKVM's
superpower and its reason to exist.

**detachment removes the relay.** There is no browser, no controller, no dongle:

```
   ┌──────────────────────────────┐                         ┌───────────────┐
   │  jt (gcunix Framework 13)     │      Bluetooth HID      │  Windows PC   │
   │  · you're sitting at it       │  (classic BR/EDR,       │  (target)     │
   │  · Wayland InputCapture grabs │   keyboard + absolute   │  · no software│
   │    kbd/mouse at the R edge    │   pointer)              │  · paired once│
   │  · emits BT HID to the target │ ──────────────────────► │  · own monitor│
   └──────────────────────────────┘                         └───────────────┘
        look at jt's screen                                   look at its screen
        cursor here…                    …cross the edge →      …cursor appears here
```

detachment is a **complement** to the RelayKVM Pico, not a replacement: it's the zero-hardware,
always-on, "drive the machines that live on my desk" node. The Pico still owns pre-boot / BIOS /
disk-unlock / dark-machine scenarios (see constraints below).

## Honest constraints (what this is *not*)

Because the target is reached over **Bluetooth HID**, not USB:

- **Post-boot only.** The target must be booted with its OS Bluetooth stack up. No BIOS/UEFI,
  no LUKS/BitLocker unlock, no rescuing a hung boot. (That's the Pico's job — keep it for that.)
- **Pair once, trust always.** The target must be Bluetooth-capable and paired a single time.
- **Can't wake a fully-off machine.** BT-HID activity may wake a *sleeping, paired* host if it
  allows BT wake; it can't power on a dark one.
- **Absolute pointer = the target's PRIMARY monitor only.** An absolute HID pointing device binds
  to a single display on Windows (tested: both a plain absolute mouse *and* a pen digitizer map to
  primary). This suits the intended use — a laptop driving a *headless / single-screen* box with
  true 1:1 tracking. Spanning a target's secondary monitors needs **relative mode** (the target
  moves its own cursor, trading strict 1:1); that's on the roadmap, not built. Absolute is the
  chosen design.
- **First-class target is Windows.** Other hosts (Android, macOS, Linux, iOS) accept BT keyboard +
  *relative* mouse fine, but ignore our absolute reports — so they also wait on relative mode. See
  the roadmap.

## How it works

Two processes that meet over a unix socket — a **privilege split**, because emitting HID needs
Bluetooth/root and capturing input needs the live user session:

### `detachment-hidd` — the root HID emitter (system service)

Holds the classic Bluetooth HID link to the target and does nothing UI.

- **BlueZ over D-Bus** (`dbus-python`): an auto-accept pairing `Agent1` and an HID profile
  registered via `ProfileManager1.RegisterProfile` (UUID `0x1124`) whose SDP record embeds our
  report descriptor. `bluetoothd` runs with `--noplugin=input` (+ `--compat`) so jt is an HID
  *device*, not a host, and frees the HID L2CAP PSMs.
- **L2CAP** PSMs **17 (control) / 19 (interrupt)** via stdlib `socket.AF_BLUETOOTH`; input reports
  go out on the interrupt channel with the `0xA1` DATA-input header.
- **Report descriptor** — three reports: **(1)** boot-compatible keyboard; **(2)** 5-button
  relative mouse + wheel + AC Pan; **(3)** 5-button **absolute** pointer (X/Y 0–32767) + wheel +
  pan. Buttons: left / right / middle / back / forward.
- **Self-healing link:** prefers **device-initiated reconnect** (jt re-connects to the paired host
  on startup, like a real keyboard waking) with a host-initiated listen as fallback, and a keepalive
  that re-establishes a dropped link — so a daemon restart doesn't need a "toggle it on Windows"
  dance.
- **Line protocol** on `/run/detachment/hid.sock` (mode 0666, so the session agent can connect):
  `A x y buttons wheel pan` (absolute pointer), `K mod k1..k6` (keyboard), `J on|off …` (jiggler),
  `E 0|1` (capture state, for the LED).
- Also runs the **jiggler** and drives the **status LED** (below).

### `detachment` — the capture agent + tray (user service, in GNOME)

- **Wayland input capture:** drives `org.freedesktop.portal.InputCapture` directly over D-Bus
  (CreateSession → GetZones → SetPointerBarriers → ConnectToEIS → Enable) and feeds the returned EIS
  fd to **libei** via [**snegg**](https://gitlab.freedesktop.org/libinput/snegg). A pointer barrier
  sits on jt's chosen screen edge (default **right**); crossing it emits `Activated` and hands the
  exclusive input stream. No virtual monitor — you look at the target's own screen.
- **Coordinate mapper:** libei gives relative deltas; we integrate them into a virtual **absolute**
  cursor in the *target's* coordinate space, scale to 0–32767, and emit report 3. Absolute keeps
  jt's virtual cursor and the target's real cursor locked 1:1 (relative would desync when the
  target clamps at its own edge). Keyboard / buttons / scroll pass straight through (evdev → HID).
- **Tray** (GTK3 AppIndicator) + a **web settings/arrangement editor** (see below). Comes up
  **disarmed** so it doesn't hijack the edge until you enable it.

### Controls

| Action | How | Notes |
|---|---|---|
| **Arm / disarm** the edge | **Hyper+F1**, or tray → *Enable capture* | Hyper = keyd's CapsLock (hold). Arm makes the barrier live. |
| **Drive the target** | cross the armed edge | `CAPTURED`; your kbd+mouse now go to the target. |
| **Stand down** | **Hyper+`** (CapsLock+backtick) | Releases *and* disarms; cursor re-homes to jt's screen centre. |
| **…or walk back** | return the cursor to the entry edge | `release.walk_back` (default on). |
| **Jiggler** | tray → *Jiggler*, or config | Tiny keep-awake move every ~30 s. |

**Status LED** (Framework power button, `chromeos:multicolor:power` RGB): **off** = no BT link ·
**green heartbeat over white** = connected / idle · **solid red** = driving the target · returns to
firmware **white** when the daemon stops. (The physical CapsLock key light is EC-owned and not
sysfs-drivable — hence the power LED.)

**Web arrangement editor** — the user service serves a small HTML/JS app at `http://127.0.0.1:8730`
(basalt-themed canvas): it draws jt's actual monitors and lets you click an outer edge to attach the
target, plus a config form and live state. Changes apply live (no restart). Set `web.bind` to jt's
tailnet IP to configure it from another machine.

## Install (NixOS / gcunix)

detachment is a flake, consumed by [gcunix](https://github.com/endarthur/gcunix) as an input:

```nix
# flake.nix
inputs.detachment.url = "github:gentropic/detachment";
inputs.detachment.inputs.nixpkgs.follows = "nixpkgs";

# host config
imports = [ detachment.nixosModules.default ];
services.detachment.enable = true;   # + services.detachment.audio = true; to keep A2DP/AVRCP
```

That brings up `detachment-hidd` (system) and `detachment` (user, in the graphical session), and the
BlueZ device-role tweaks. On jt it pairs with the recommended companion setup:

- **keyd** maps **CapsLock → Hyper** (`overload(hyper, esc)`; hold = Ctrl+Alt+Super+Shift, tap =
  Esc) so CapsLock is a conflict-free command leader. gcunix `modules/keyd.nix`.
- A **GNOME custom keybinding** (gcunix dconf) binds **Hyper+F1** → arm/disarm. Release is *not* a
  keybinding — see design notes.

Config lives at `~/.config/detachment/config.json` (deep-merged over defaults): `barrier_edge`,
`barrier_monitor` (which of jt's monitors the edge attaches to), `target` (name / width / height /
mac), `release` (walk_back, capslock_esc), `scroll` (invert / detent / smoothing), `jiggler`
(enable / interval / pixels), `web` (bind / port). Re-pair after changing `audio`.

Re-pairing gotcha: clear a stale jt-side bond with `detachment-reset` (or `bluetoothctl remove`)
before re-pairing if Windows says "can't connect."

## Repo layout

```
detachment/
  hid.py          report descriptor + report builders
  bluez.py        BlueZ agent/profile, L2CAP, device-initiated reconnect, bond reset
  hidd.py         detachment-hidd: link manager, LED controller, jiggler, socket server
  capture.py      InputCapture portal flow (base class)
  agent.py        capture agent: libei deltas → absolute HID; in-stream release; signal hooks
  geometry.py     pure virtual-cursor / target-space mapping
  evdev_hid.py    evdev keycode → HID usage maps
  led.py          multicolor power-LED driver
  websettings.py  local HTTP + JSON API (state / config / action), serves web/
  web/            the arrangement editor (index.html, app.js, style.css)
  tray.py         GTK3 AppIndicator tray
  config.py       config schema + load/save
  reset.py        detachment-reset CLI
nix/{snegg,package,module}.nix · flake.nix · pyproject.toml · scripts/led-test.sh
```

Console scripts: `detachment-hidd` (root), `detachment` (tray+agent), `detachment-reset`.

## Security

A paired BT-HID that can type into your target is keystroke-injection capability by design. Gates:
the daemon connects only to the one interactively-paired target; **Hyper+`** force-releases capture;
it runs on jt (endar's own full-ops box) and holds no secrets. The repo is public precisely because
it's a general-purpose KVM tool with nothing sensitive in it. GNOME also gates input capture behind a
per-login consent prompt (portal-enforced; no supported "remember forever").

## Roadmap

- **Multi-target — one jt controlling several computers.** Keep every target **paired** at once; the
  UI **explicitly selects** the active target (deterministic — no auto-connect race), switching the
  BT HID connection to the chosen host. Capture side is easy (the portal already does multiple
  barriers → an *arrangement*: e.g. left edge → machine A, right edge → machine B, each with its own
  geometry). The open question is the BT layer: whether jt can hold **simultaneous** HID links to
  several hosts (piconet master, ~≤7) for instant edge-crossing — worth a feasibility spike — or falls
  back to switch-on-select (reliable, ~1–2 s reconnect). Start with paired-all + explicit select.
  The web editor is already the UI foundation (drop N target tiles); Hyper+F2..F12 would select the
  Nth target the same dconf-keybinding way F1 arms today.
- **Cross-platform targets (relative mode) — Android, macOS, Linux, iOS.** Today the target is
  Windows because detachment sends an **absolute** pointer (1:1 into the target's screen space), which
  Windows honours via a plain absolute-mouse report — that's what makes the edge-cross land the cursor
  at the *same spot*. Other hosts treat a BT pointer as **relative** and largely ignore absolute/
  digitizer reports; **Android** is the sharpest case (relative-only, plus rotation/DPI/variable screen
  size break a fixed target-space mapping). Keyboard + relative mouse *are* portable — classic BT HID
  is host-agnostic, and Android/macOS/Linux pair a BT keyboard/mouse fine — so the unlock is a
  **relative pointer mode**: feed motion deltas and let the target move its own cursor. Trade-offs:
  you lose strict 1:1 edge-crossing and must cope with the target's own pointer acceleration (desync).
  The relative report already exists in the descriptor (report 2); the work is a delta mapper +
  per-target geometry + a mode toggle. Android is the most likely reason we'd finally build it. This
  also happens to be the same relative-mode path that would let a *single* Windows target span **all**
  its monitors (see "Honest constraints").
- **Smaller:** GTK tray settings window (retired in favour of the web editor — could return);
  Meshtastic-style out-of-band; a proper multi-target arrangement in the web editor.

## Design notes & lessons

Things that cost time and are worth not re-learning:

- **Absolute is single-monitor on Windows.** Both a plain absolute mouse and a pen digitizer bind to
  the primary display; the digitizer bought nothing (still primary-only) while costing middle-click /
  hover semantics, so we use the plain absolute mouse. `abs 0 0` is a no-op (all-zero report dropped)
  → floor the mapper at 1.
- **libei from Python = snegg.** Peter Hutterer's ctypes wrapper, git-only (not on PyPI/nixpkgs),
  packaged in `nix/snegg.nix`; needs `libei` on `LD_LIBRARY_PATH` (it dlopens it). snegg's `oeffis`
  only speaks the RemoteDesktop portal, so InputCapture is driven directly over D-Bus. Must call
  `seat.bind()` on `SEAT_ADDED` or no devices/motion ever arrive.
- **Release is detected in the capture stream, not via a keybinding.** During active capture mutter
  routes keys into the libei stream, so a GNOME custom keybinding fires only *intermittently* (looked
  like "release does nothing"). Since keyd maps CapsLock→Hyper, the agent already sees the four Hyper
  modifiers + backtick in-stream — `agent._on_key` catches **Hyper+`** and stands down. A GNOME
  backtick keybinding would actively *hurt* (it'd steal the key from the stream), so it's absent.
  **Arming** *is* a keybinding (Hyper+F1) because it happens when not capturing, where mutter
  delivers shortcuts normally.
- **GNOME GlobalShortcuts portal is a dead end here** — `BindShortcuts` returns response 2 and never
  honours `preferred_trigger`; the raw chord then leaked to a logout. Use dconf custom-keybindings.
- **Release must pass `cursor_position`.** The portal's `Release` takes a `(dd)` option; without it
  the local pointer is dropped back *onto* the barrier and the next move instantly re-crosses. We
  re-home to jt's zone centre and also disarm.
- **The CapsLock key light is EC/firmware-owned** (not sysfs-drivable) — status uses the RGB
  power-button LED instead.
- **Re-pairing:** a stale jt-side bond (mismatched keys) is the usual "can't connect" — `detachment-reset`.

## References

- **RelayKVM** — `docs/RG34XX.md` (the Linux BT-HID PoC), `relaykvm-adapter.js` (`moveMouseAbsolute`
  digitizer approach), seamless/portal mode. detachment reuses its Windows-absolute descriptor
  lessons.
- **[EmuBTHID](https://github.com/Alkaid-Benetnash/EmuBTHID)** — classic BT HID keyboard/mouse
  emulation on Linux via BlueZ + L2CAP (the target-side backbone).
- **[BlueZ D-Bus API](https://git.kernel.org/pub/scm/bluetooth/bluez.git/tree/doc)** —
  `ProfileManager1`, SDP records.
- **InputCapture portal** — `org.freedesktop.portal.InputCapture` spec ·
  **[libei](https://gitlab.freedesktop.org/libinput/libei)** · **[snegg](https://gitlab.freedesktop.org/libinput/snegg)**.
- **[Deskflow](https://github.com/deskflow/deskflow)** (ex-Synergy/Barrier) — reference Wayland
  edge-switch capture via portal + libei, and the relative-delta → remote-absolute cursor model.
```
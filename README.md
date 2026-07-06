# detachment

> **Provisional name** (a *detachment* is the low-angle surface along which one crustal block
> slides a long way over another — the blocks stay coupled across it but move independently).
> Sibling to **[RelayKVM](https://github.com/endarthur/RelayKVM)** (named for relay ramps): same
> fault-structure naming whim, opposite topology. Bikeshed freely — candidates: *décollement,
> heave, throw, slip, transfer-zone*.

**One machine's keyboard and mouse "detach" at a screen edge and slide onto a second machine —
which sees only a Bluetooth keyboard/mouse and runs no software at all.**

Software-free-on-the-target multi-machine input sharing, self-hosted. Think Synergy / Barrier /
Apple Universal Control, but the *target installs nothing* because the controlling box
(**jt** — the gcunix Framework 13) impersonates a Bluetooth HID device directly.

Status: **SPEC / pre-PoC.** Lives in the `agents` repo for now; spins out to its own repo once
PoC-1 lands. No code yet — this document is the design.

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

You already **proved the hard half** of this: `RelayKVM/docs/RG34XX.md` is a working PoC of a
Linux box being a classic-Bluetooth-HID keyboard that Windows 11 pairs with and accepts keystrokes
from. Its "Software TODO" list is all unchecked. **detachment finishes that daemon, adds a mouse
(absolute), replaces the BLE-relay front-end with local input capture, and makes the whole thing
declarative on NixOS.** jt is the ideal host: always-on, config-as-code, Python-native.

## Honest constraints (what this is *not*)

Because the target is reached over **Bluetooth HID**, not USB:

- **Post-boot only.** The target must be booted with its OS Bluetooth stack up. No BIOS/UEFI,
  no LUKS/BitLocker unlock, no rescuing a hung boot. (That's the Pico's job — keep it for that.)
- **Pair once, trust always.** The target must be Bluetooth-capable and paired a single time.
- **Can't wake a fully-off machine.** BT-HID activity may wake a *sleeping, paired* host if it
  allows BT wake; it can't power on a dark one.
- **Absolute pointer = the target's PRIMARY monitor only.** An absolute HID pointing device (mouse
  *or* digitizer) binds to a single display on Windows — TESTED, both map to primary; there's no
  reliable way to span multiple real monitors. This is fine for the intended use — a laptop driving
  a *headless/single-screen* box (a work PC controlled over BLE with no monitors attached, or its
  primary): you get true 1:1 absolute tracking. If you need to reach a target's secondary monitors,
  that's the RELATIVE-mode path (Windows moves its own cursor across the whole desktop, trading strict
  1:1) — deliberately not built; absolute is the chosen design.

→ detachment is a **complement** to the RelayKVM Pico, not a replacement. It's the zero-hardware,
always-on, "drive the machines that live on my desk" node.

## Decisions locked for the first build

| Axis | Choice | Why |
|---|---|---|
| **First target** | **Windows PC** | On the desk; classic BR/EDR HID is RG34XX-proven against Win11 |
| **Target HID profile** | **Classic Bluetooth HID (BR/EDR, HID profile 0x1124)** | Best desktop compatibility; matches the PoC |
| **Input capture** | **Pure Wayland — `InputCapture` portal + libei** | GNOME/mutter path; no X11 fallback even though it's more work |
| **"Monitor"** | **Capture *region* only — a barrier on jt's edge, no dummy HDMI / virtual display** | Portal barriers sit on the real layout boundary; you look at the target's own screen |
| **Pointer mode** | **Absolute (digitizer descriptor), relative as PoC-shortcut/fallback** | 1:1 mapping, no edge-clamp desync; RelayKVM's proven Windows-absolute approach |
| **Language** | **Python** | jt's default; BlueZ D-Bus + L2CAP sockets are ergonomic from Python |

Roads not taken (revisit later): BLE HID-over-GATT (HOGP) for phone/tablet targets; X11 pointer
barriers for a faster spike; the RelayKVM NUS/WebSocket relay front-end (a different project).

---

## Architecture

Two halves that meet in a coordinate mapper.

### 1. Target side — jt as a classic Bluetooth HID device

The RG34XX-proven path, generalized from keyboard-only to a full combo device.

- **Profile registration:** register an HID profile with BlueZ over D-Bus
  (`org.bluez.ProfileManager1.RegisterProfile`, UUID `0x1124`) carrying an SDP record that embeds
  our **HID report descriptor**. (The RG34XX PoC used the legacy `sdptool add KEYB` + `bluetoothd
  --compat`; registering via `ProfileManager1` is the modern way and may avoid `--compat` — spike
  both.)
- **L2CAP channels:** listen on the two HID PSMs — **0x11 (control)** and **0x13 (interrupt)** —
  via `socket.socket(AF_BLUETOOTH, SOCK_SEQPACKET, BTPROTO_L2CAP)`. On connect from the paired
  host, push input reports on the interrupt channel (`0xA1` DATA-input transaction header).
- **Adapter prep (declarative on NixOS):** set device class to keyboard/mouse combo
  (`0x0025C0`-ish), **disable BlueZ's `input` plugin** (`bluetoothd --noplugin=input`) so jt acts
  as an HID *device* and doesn't try to be an HID *host*, discoverable + pairable for the one-time
  pair.
- **Report descriptor** (multi-report; reuse RelayKVM's proven Windows-absolute digitizer):
  - Report 1 — **Keyboard** (modifier byte, reserved, 6 keycodes) — standard boot-compatible.
  - Report 2 — **Mouse, relative** (buttons, dx, dy, wheel) — fallback / gaming toggle.
  - Report 3 — **Pointer, absolute / digitizer** (buttons, X 0–32767, Y 0–32767, wheel) — the
    default; what the capture edge drives.
  - Report 4 — **Consumer/Media** (volume, play/pause, etc.) — cheap to include.

### 2. Controller side — Wayland input capture on jt

- **`org.freedesktop.portal.InputCapture`** (xdg-desktop-portal + the GNOME backend). Create a
  session, `SetPointerBarriers` along jt's chosen edge (default **right**). On barrier hit the
  portal emits `Activated` and hands an **EIS** socket; connect **libei** to it and receive the
  exclusive input stream (relative motion, buttons, keys, scroll) while captured.
- **No virtual monitor.** The barrier is on the boundary of jt's *existing* display. Nothing is
  rendered beyond the edge; you watch the target's own monitor.
- **State machine:**
  - `LOCAL` — normal jt use; barrier armed on the right edge.
  - `CAPTURED` — entered when the pointer crosses the barrier. Local kbd+mouse are grabbed and
    fed to the target instead of jt. Entry seeds the virtual cursor at the mapped edge position.
  - **Exit** back to `LOCAL` — no monitor beyond the edge, so *we* decide the exit: virtual cursor
    walked back to the entry edge (x ≤ 0), **or** a panic hotkey (e.g. `ScrollLock` / a chord).
    Release the capture session; jt's cursor resumes.

### 3. The coordinate mapper (why absolute)

libei gives **relative deltas** while captured. We integrate them into a virtual absolute cursor
in the **target's** coordinate space (`screen = {width, height}`, configured per target), clamp to
`[0, w) × [0, h)`, scale to `0–32767`, and emit an **absolute** HID report (Report 3).

Sending *relative* to Windows instead would desync: when Windows' own cursor hits its screen edge
it clamps, but our integrated position keeps travelling, so the two drift apart. Absolute keeps
jt's virtual cursor and Windows' real cursor locked 1:1 — the whole reason the edge-cross feels
right. (Relative stays available as a toggle for raw-input games that dislike absolute/digitizer.)

Keyboard + scroll + buttons pass straight through (libei event → HID report), no integration needed.

---

## NixOS packaging (the config-as-code payoff)

Every manual RG34XX step becomes flake config. Fits gcunix's droppable-module pattern.

- **System module** (`hardware.bluetooth` + a `bluetoothd --noplugin=input` ExecStart override +
  adapter class); options: `services.detachment = { enable; targetMac; screen = { width; height; };
  entryEdge = "right"; panicHotkey; }`.
- **User-session agent** — the capture half needs the live Wayland session (portal + libei), so it
  runs as a **user** systemd service inside GNOME, not a system service.
- **Privilege split to resolve:** L2CAP/HID emission needs Bluetooth access (`bluetooth` group or a
  small privileged helper); input capture needs the user session. Likely one user-service process
  if the user has Bluetooth socket access — otherwise a thin privileged HID-emitter + an unprivileged
  capture agent over a local socket. **Decide during PoC-1.**

## Security

A paired BT-HID that can type into your Windows box is keystroke-injection capability by design.
Gates: the daemon only ever connects to **one explicitly configured, interactively-paired target
MAC**; a **panic hotkey** force-releases capture; it runs on jt (endar's own full-ops box), holds
no secrets, and the pairing itself is a deliberate one-time trust event. Nothing here is committed
plaintext.

---

## Build order

1. **PoC-1 — BT HID out (no capture yet). ✅ DONE (2026-07-05).** BlueZ classic HID *device* daemon
   on jt (`poc1/`), paired to the Windows target; **keyboard, relative mouse, and absolute pointer
   all confirmed** driving Windows 11. Absolute worked with a plain absolute-mouse report — **no
   digitizer swap needed**. (Lone quirk: `abs 0 0` is a no-op — all-zero report dropped by Windows;
   floor the clamp at 1 in the mapper.) Audio profiles made optional via `services.detachment.audio`
   (default off) so jt presents as a clean keyboard/mouse. Pairing must happen with the daemon
   running (it registers the agent + HID SDP); it self-cleans on exit.
2. **PoC-2 — Wayland input capture (no target yet). ✅ DONE (2026-07-05).** `poc2/` — `InputCapture`
   portal (driven directly over D-Bus; oeffis only does RemoteDesktop) + libei via **snegg** on jt:
   right-edge barrier → `Activated` → EIS fd → `snegg.ei.Receiver`; `seat.bind()` on SEAT_ADDED
   creates the device; captured `move`/`button`/`key` deltas print. Runs in jt's GNOME session.
3. **Glue (PoC-3) — TWO processes** (privilege split, since HID needs root and capture needs the
   user session): a **root HID emitter** (PoC-1's BT link) listening on a unix socket for
   `abs/key/button` commands, and a **user-session capture agent** (PoC-2) that integrates libei
   deltas → target-space absolute (`geometry.py`) and sends them over the socket. Plus the entry/exit
   state machine (release when the virtual cursor walks back to the left edge, or a hotkey), keyboard
   passthrough, abs/rel toggle, and the small status GUI (LOCAL vs CAPTURED).
4. **NixOS-ify.** The BlueZ tweaks + daemon + options become a gcunix module; add a status line /
   tray hint for LOCAL vs CAPTURED; gatus is N/A (it's a desktop feature, not a service).

## Roadmap

- **Multi-target — one jt controlling several computers.** Keep every target **paired** at once; the
  UI **explicitly selects** the active target (deterministic — no auto-connect race), switching the
  BT HID connection to the chosen host. Capture side is easy (the portal already does multiple
  barriers → an *arrangement*: e.g. left edge → machine A, right edge → machine B, each with its own
  geometry). The open question is the BT layer: whether jt can hold **simultaneous** HID links to
  several hosts (piconet master, ~≤7) for instant edge-crossing — worth a feasibility spike — or falls
  back to switch-on-select (reliable, ~1–2 s reconnect). Start with paired-all + explicit select.
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
- **Status GUI** (LOCAL vs CAPTURED, target picker) and **NixOS module** (two systemd units).

## Validated on jt (probe, 2026-07-05)

Read-only capability check of jt's current image — the locked path is viable:

- **BT peripheral role: ✅** `bluetoothctl show` → `Roles: central` *and* `peripheral`. jt's adapter
  can be an HID device (same capability the RG34XX PoC used).
- **InputCapture portal: ✅ (package level)** GNOME Shell 50.2, `xdg-desktop-portal` 1.20.4,
  `xdg-desktop-portal-gnome` 50.0 whose `gnome.portal` manifest advertises **InputCapture** — the
  mutter backend implements it. Still needs a live in-session functional test.
- **libei client: ⚠️ add it.** Not surfaced by the probe; mutter uses it internally but we must pull
  `libei` explicitly and settle the Python-client question (see Risks #1).

## Risks / to spike

- **libei from Python.** libei is a C library; mature Python bindings are the open question.
  Options: GObject-Introspection bindings if present, a small Rust/C helper exposing a socket, or
  follow Deskflow's (C++) implementation. **This is the #1 thing PoC-2 must answer.**
- **Portal availability.** Needs a recent `xdg-desktop-portal` + `xdg-desktop-portal-gnome` with
  `InputCapture` support on our GNOME (26.05). Verify the version implements it.
- **Windows absolute quirks.** Absolute pointer registers as a digitizer/touch device on Windows
  (press-hold = right-click, no hover) and multi-monitor maps to the whole virtual-desktop bounding
  box. Reuse RelayKVM's tuned descriptor; keep the relative toggle.
- **BlueZ device-vs-host role.** Must disable the `input` plugin cleanly and confirm no re-grab
  after suspend/resume; `--compat` may or may not be needed depending on registration path.

## References

- **RelayKVM** — `docs/RG34XX.md` (the Linux BT-HID PoC + "Software TODO"), `relaykvm-adapter.js`
  (NanoKVM protocol, keycodes, `moveMouseAbsolute` digitizer approach), seamless/portal mode.
- **[EmuBTHID](https://github.com/Alkaid-Benetnash/EmuBTHID)** — classic BT HID keyboard/mouse
  emulation on Linux via BlueZ + L2CAP (the target-side backbone).
- **[BlueZ D-Bus API](https://git.kernel.org/pub/scm/bluetooth/bluez.git/tree/doc)** —
  `ProfileManager1`, SDP records.
- **InputCapture portal** — `org.freedesktop.portal.InputCapture` spec; **[libei](https://gitlab.freedesktop.org/libinput/libei)**.
- **[Deskflow](https://github.com/deskflow/deskflow)** (ex-Synergy/Barrier) — reference Wayland
  edge-switch capture via portal + libei, and the relative-delta → remote-absolute cursor model.

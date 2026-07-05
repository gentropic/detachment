"use strict";
// detachment settings/editor. jt's monitors are read-only (rearrange in GNOME Displays); you only
// attach the target to a valid OUTER edge of one of them. Starter — iterate freely.
const $ = (id) => document.getElementById(id);
const canvas = $("canvas");
const ctx = canvas.getContext("2d");

let state = null;               // {armed, captured, monitors, config}
let cfg = null;                 // config (server copy; form is only read on Save)
let placement = null;          // {monitor:{x,y,w,h}|null, edge}
let handles = [];              // clickable outer edges

async function post(path, body) {
  await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

async function poll() {
  state = await fetch("/api/state").then((r) => r.json());
  cfg = state.config;
  if (!placement) placement = { monitor: cfg.barrier_monitor || null, edge: cfg.barrier_edge || "right" };
  renderState();
  draw();
}

function renderState() {
  const p = $("state");
  p.className = "pill";
  if (state.captured) { p.textContent = "CAPTURED"; p.classList.add("captured"); }
  else if (state.armed) { p.textContent = "armed"; p.classList.add("armed"); }
  else p.textContent = "disabled";
  $("toggle").textContent = state.armed ? "Disable capture" : "Enable capture";
  $("toggle").classList.toggle("on", state.armed);
  $("jiggler").classList.toggle("on", cfg.jiggler.enable);
}

function syncForm() {
  $("tw").value = cfg.target.width; $("th").value = cfg.target.height;
  $("walk").checked = cfg.release.walk_back; $("cesc").checked = cfg.release.capslock_esc;
  $("inv").checked = cfg.scroll.invert_vertical;
  $("jig").checked = cfg.jiggler.enable; $("jint").value = cfg.jiggler.interval_sec; $("jpx").value = cfg.jiggler.pixels;
}

// ── canvas ────────────────────────────────────────────────────────────────────────────────
const same = (a, b) => a && b && a.x === b.x && a.y === b.y && a.w === b.w && a.h === b.h;
const overlapY = (a, b) => a.y < b.y + b.h && b.y < a.y + a.h;
const overlapX = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w;

function isOuter(m, edge, mons) {
  for (const n of mons) {
    if (n === m) continue;
    if (edge === "right" && Math.abs(n.x - (m.x + m.w)) < 2 && overlapY(n, m)) return false;
    if (edge === "left" && Math.abs((n.x + n.w) - m.x) < 2 && overlapY(n, m)) return false;
    if (edge === "top" && Math.abs((n.y + n.h) - m.y) < 2 && overlapX(n, m)) return false;
    if (edge === "bottom" && Math.abs(n.y - (m.y + m.h)) < 2 && overlapX(n, m)) return false;
  }
  return true;
}

function draw() {
  const mons = state.monitors || [];
  handles = [];
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!mons.length) {
    ctx.fillStyle = "#8A8F96"; ctx.font = "13px 'Space Mono',monospace";
    ctx.fillText("no monitors reported yet — enable capture / wait a moment", 20, 30);
    return;
  }
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const m of mons) { x0 = Math.min(x0, m.x); y0 = Math.min(y0, m.y); x1 = Math.max(x1, m.x + m.w); y1 = Math.max(y1, m.y + m.h); }
  const pad = 90;
  const scale = Math.min((canvas.width - pad * 2) / ((x1 - x0) || 1), (canvas.height - pad * 2) / ((y1 - y0) || 1));
  const ox = (canvas.width - (x1 - x0) * scale) / 2 - x0 * scale;
  const oy = (canvas.height - (y1 - y0) * scale) / 2 - y0 * scale;
  const S = (x, y) => [ox + x * scale, oy + y * scale];

  const activeMon = placement.monitor ? mons.find((m) => same(m, placement.monitor)) || mons[0] : mons[0];

  for (const m of mons) {
    const [x, y] = S(m.x, m.y);
    const w = m.w * scale, h = m.h * scale;
    ctx.fillStyle = "#1D2024"; ctx.strokeStyle = "#2A2E33"; ctx.lineWidth = 1.5;
    ctx.fillRect(x, y, w, h); ctx.strokeRect(x, y, w, h);
    ctx.fillStyle = "#8A8F96"; ctx.font = "11px 'Space Mono',monospace"; ctx.textAlign = "center";
    ctx.fillText(`${m.w}×${m.h}`, x + w / 2, y + h / 2 + 4);
    for (const edge of ["left", "right", "top", "bottom"]) {
      if (!isOuter(m, edge, mons)) continue;
      const t = 8;
      let hx = x, hy = y, hw = w, hh = h;
      if (edge === "right") { hx = x + w; hw = t; }
      else if (edge === "left") { hx = x - t; hw = t; }
      else if (edge === "top") { hy = y - t; hh = t; }
      else if (edge === "bottom") { hy = y + h; hh = t; }
      const active = placement.edge === edge && same(activeMon, m);
      ctx.fillStyle = active ? "#FB9044" : "rgba(251,144,68,.22)";
      ctx.fillRect(hx, hy, hw, hh);
      handles.push({ mon: m, edge, rect: { x: hx, y: hy, w: hw, h: hh } });
    }
  }

  // schematic target tile on the active edge
  const [mx, my] = S(activeMon.x, activeMon.y);
  const mw = activeMon.w * scale, mh = activeMon.h * scale, g = 10;
  let tx, ty, tw, th;
  if (placement.edge === "right") { tw = mw * 0.7; th = mh; tx = mx + mw + g; ty = my; }
  else if (placement.edge === "left") { tw = mw * 0.7; th = mh; tx = mx - g - tw; ty = my; }
  else if (placement.edge === "top") { tw = mw; th = mh * 0.7; tx = mx; ty = my - g - th; }
  else { tw = mw; th = mh * 0.7; tx = mx; ty = my + mh + g; }
  ctx.fillStyle = "rgba(92,203,128,.14)"; ctx.strokeStyle = "#5CCB80"; ctx.lineWidth = 1.5;
  ctx.fillRect(tx, ty, tw, th); ctx.strokeRect(tx, ty, tw, th);
  ctx.fillStyle = "#5CCB80"; ctx.font = "11px 'Space Mono',monospace"; ctx.textAlign = "center";
  ctx.fillText(`target ${cfg.target.width}×${cfg.target.height}`, tx + tw / 2, ty + th / 2 + 4);
}

canvas.addEventListener("click", (e) => {
  const r = canvas.getBoundingClientRect();
  const cx = (e.clientX - r.left) * (canvas.width / r.width);
  const cy = (e.clientY - r.top) * (canvas.height / r.height);
  for (const hd of handles) {
    const { x, y, w, h } = hd.rect;
    if (cx >= x - 4 && cx <= x + w + 4 && cy >= y - 4 && cy <= y + h + 4) {
      placement = { monitor: { x: hd.mon.x, y: hd.mon.y, w: hd.mon.w, h: hd.mon.h }, edge: hd.edge };
      draw();
      return;
    }
  }
});

// ── actions ──────────────────────────────────────────────────────────────────────────────
$("toggle").addEventListener("click", async () => {
  await post("/api/action", { action: state.armed ? "disable" : "enable" });
  setTimeout(poll, 150);
});
$("jiggler").addEventListener("click", async () => {
  await post("/api/action", { action: cfg.jiggler.enable ? "jiggler_off" : "jiggler_on" });
  setTimeout(poll, 150);
});
$("save").addEventListener("click", async () => {
  cfg.target.width = +$("tw").value; cfg.target.height = +$("th").value;
  cfg.release.walk_back = $("walk").checked; cfg.release.capslock_esc = $("cesc").checked;
  cfg.scroll.invert_vertical = $("inv").checked;
  cfg.jiggler.enable = $("jig").checked; cfg.jiggler.interval_sec = +$("jint").value; cfg.jiggler.pixels = +$("jpx").value;
  cfg.barrier_edge = placement.edge; cfg.barrier_monitor = placement.monitor;
  await post("/api/config", cfg);
  const b = $("save"); b.textContent = "Saved ✓"; setTimeout(() => (b.textContent = "Save"), 1200);
});

// ── boot ─────────────────────────────────────────────────────────────────────────────────
poll().then(syncForm);
setInterval(poll, 1500);   // keep armed/captured + monitors fresh (does NOT touch form fields)

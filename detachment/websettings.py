"""
Local web settings/editor server (RelayKVM-shaped): the tray process serves a small HTML/JS app
(config form + a canvas screen-arrangement editor) and a JSON API. Default bind 127.0.0.1; set
web.bind to jt's tailnet IP to configure from another machine.

  GET  /api/state    -> { armed, captured, jiggler, monitors:[{x,y,w,h}], config }
  POST /api/config   -> save the full config object
  POST /api/action   -> { action: enable | disable | jiggler_on | jiggler_off }

Static files are served from detachment/web/. Portal/D-Bus actions are marshalled to the GLib main
thread via idle_add (dbus isn't thread-safe from the HTTP worker).
"""
import http.server
import json
import mimetypes
import socketserver
import threading
from importlib.resources import files

from gi.repository import GLib

from . import config

WEB_DIR = files("detachment") / "web"


class _Backend:
    def __init__(self, agent):
        self.agent = agent

    def state(self):
        a = self.agent
        zones = a.zones or []
        return {
            "armed": bool(a.armed),
            "captured": bool(getattr(a, "captured", False)),
            "ready": bool(a.ready),
            "monitors": [{"w": int(z[0]), "h": int(z[1]), "x": int(z[2]), "y": int(z[3])}
                         for z in zones],
            "config": config.load(),
        }

    def action(self, name):
        def do():
            if name == "enable":
                self.agent.enable()
            elif name == "disable":
                self.agent.disable()
            elif name in ("jiggler_on", "jiggler_off"):
                on = name == "jiggler_on"
                self.agent.set_jiggler(on)
                cfg = config.load()
                cfg["jiggler"]["enable"] = on
                config.save(cfg)
            return False   # one-shot
        GLib.idle_add(do)


def _make_handler(backend):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def _send(self, data, ctype, code=200):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _json(self, obj, code=200):
            self._send(json.dumps(obj).encode(), "application/json", code)

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/api/state":
                self._json(backend.state())
                return
            fname = "index.html" if path in ("/", "") else path.lstrip("/")
            try:
                data = (WEB_DIR / fname).read_bytes()
            except (FileNotFoundError, OSError, IsADirectoryError):
                self.send_error(404)
                return
            self._send(data, mimetypes.guess_type(fname)[0] or "application/octet-stream")

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0) or 0)
            try:
                data = json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError:
                data = {}
            if self.path == "/api/config":
                config.save(data)
                self._json({"ok": True})
            elif self.path == "/api/action":
                backend.action(data.get("action", ""))
                self._json({"ok": True})
            else:
                self.send_error(404)

    return Handler


class _HTTP(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def start(agent):
    """Start the settings server (in a thread). Returns the URL, or None if disabled."""
    cfg = config.load()["web"]
    if not cfg.get("enable", True):
        return None
    httpd = _HTTP((cfg["bind"], int(cfg["port"])), _make_handler(_Backend(agent)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://{cfg['bind']}:{cfg['port']}/"
    print(f"[web] settings at {url}", flush=True)
    return url

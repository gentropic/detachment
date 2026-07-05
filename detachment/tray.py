"""
GTK3 AppIndicator tray (the `detachment` user service).

Runs the capture agent in-process (disarmed until you enable it) and a local web settings server
(RelayKVM-shaped: HTML/JS editor). The tray is a thin top-bar control — Enable capture / Jiggler /
Settings… (opens the web UI) / Quit — with live state. GTK3 because AppIndicator is GTK3-only; GNOME
needs the AppIndicator shell extension for the icon to appear.
"""
import webbrowser

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import Gtk  # noqa: E402
from gi.repository import AyatanaAppIndicator3 as AppIndicator  # noqa: E402

from . import agent, config, websettings  # noqa: E402

APP_ID = "detachment"


class Tray:
    def __init__(self):
        # Agent shares the default GLib context that Gtk.main() runs. Come up disarmed.
        self.agent, _ = agent.run(start_armed=False)
        self.agent.on_state_change = self._refresh
        self.web_url = websettings.start(self.agent)

        self.ind = AppIndicator.Indicator.new(
            APP_ID, "input-mouse-symbolic", AppIndicator.IndicatorCategory.HARDWARE)
        self.ind.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.ind.set_title("detachment")
        self._build_menu()
        self._refresh()

    def _build_menu(self):
        m = Gtk.Menu()
        self.status_item = Gtk.MenuItem(label="detachment")
        self.status_item.set_sensitive(False)
        m.append(self.status_item)
        m.append(Gtk.SeparatorMenuItem())

        self.enable_item = Gtk.CheckMenuItem(label="Enable capture")
        self._enable_h = self.enable_item.connect("toggled", self._on_enable)
        m.append(self.enable_item)

        self.jiggler_item = Gtk.CheckMenuItem(label="Jiggler")
        self._jiggler_h = self.jiggler_item.connect("toggled", self._on_jiggler)
        m.append(self.jiggler_item)

        m.append(Gtk.SeparatorMenuItem())
        s = Gtk.MenuItem(label="Settings…")
        s.connect("activate", self._open_settings)
        m.append(s)
        q = Gtk.MenuItem(label="Quit")
        q.connect("activate", self._quit)
        m.append(q)

        m.show_all()
        self.ind.set_menu(m)

    # ── menu actions ─────────────────────────────────────────────────────────────────────────
    def _on_enable(self, item):
        self.agent.enable() if item.get_active() else self.agent.disable()

    def _on_jiggler(self, item):
        on = item.get_active()
        self.agent.set_jiggler(on)
        cfg = config.load()
        cfg["jiggler"]["enable"] = on
        config.save(cfg)

    def _open_settings(self, *_):
        if self.web_url:
            webbrowser.open(self.web_url)

    def _quit(self, *_):
        try:
            self.agent.disable()
        except Exception:
            pass
        Gtk.main_quit()

    # ── state → UI ───────────────────────────────────────────────────────────────────────────
    def _refresh(self):
        a = self.agent
        if getattr(a, "captured", False):
            state, icon = "CAPTURED — driving target", "input-mouse"
        elif a.armed:
            state, icon = f"armed ({a.edge} edge)", "input-mouse"
        else:
            state, icon = "disabled", "input-mouse-symbolic"
        self.status_item.set_label(f"detachment — {state}")
        self.ind.set_icon_full(icon, "detachment")
        for item, handler, value in (
            (self.enable_item, self._enable_h, a.armed),
            (self.jiggler_item, self._jiggler_h, getattr(a, "_jig_on", False)),
        ):
            item.handler_block(handler)
            item.set_active(value)
            item.handler_unblock(handler)


def main():
    Tray()
    Gtk.main()


if __name__ == "__main__":
    main()

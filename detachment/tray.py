"""
GTK3 AppIndicator tray + settings window (the `detachment` user service).

Runs the capture agent in-process (disarmed until you enable it) and gives a top-bar indicator:
Enable capture, Jiggler, Settings…, Quit — with the state (disabled / armed / CAPTURED) reflected
live. GTK3 because AppIndicator (the only tray on GNOME) is GTK3-only; styled with the switchboard
basalt palette. GNOME needs the AppIndicator shell extension for the icon to appear.
"""
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import Gdk, Gtk  # noqa: E402
from gi.repository import AyatanaAppIndicator3 as AppIndicator  # noqa: E402

from . import agent, config  # noqa: E402

APP_ID = "detachment"
EDGES = ["left", "right", "top", "bottom"]

BASALT_CSS = b"""
window { background-color: #15171A; color: #DDDCDA; }
label { color: #DDDCDA; }
button { background-image: none; background-color: #1D2024; color: #DDDCDA;
         border: 1px solid #2A2E33; border-radius: 6px; padding: 4px 10px; }
button:hover { background-color: #FB9044; color: #0E1012; }
"""


class Tray:
    def __init__(self):
        # Agent shares the default GLib context that Gtk.main() runs. Come up disarmed.
        self.agent, _ = agent.run(start_armed=False)
        self.agent.on_state_change = self._refresh
        self.settings_win = None

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
        if self.settings_win is None:
            self.settings_win = SettingsWindow()
            self.settings_win.connect("destroy", lambda *_: setattr(self, "settings_win", None))
        self.settings_win.show_all()
        self.settings_win.present()

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


class SettingsWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="detachment settings")
        self.set_border_width(16)
        cfg = config.load()
        grid = Gtk.Grid(row_spacing=8, column_spacing=12)
        self.add(grid)
        r = 0

        def label(text):
            lbl = Gtk.Label(label=text)
            lbl.set_xalign(0)
            return lbl

        grid.attach(label("Target is to my:"), 0, r, 1, 1)
        self.edge = Gtk.ComboBoxText()
        for e in EDGES:
            self.edge.append_text(e)
        self.edge.set_active(EDGES.index(cfg["barrier_edge"]) if cfg["barrier_edge"] in EDGES else 1)
        grid.attach(self.edge, 1, r, 1, 1); r += 1

        grid.attach(label("Target width:"), 0, r, 1, 1)
        self.tw = Gtk.SpinButton.new_with_range(320, 16000, 1)
        self.tw.set_value(cfg["target"]["width"])
        grid.attach(self.tw, 1, r, 1, 1); r += 1

        grid.attach(label("Target height:"), 0, r, 1, 1)
        self.th = Gtk.SpinButton.new_with_range(240, 16000, 1)
        self.th.set_value(cfg["target"]["height"])
        grid.attach(self.th, 1, r, 1, 1); r += 1

        self.walk = Gtk.CheckButton(label="Return by walking back to the edge")
        self.walk.set_active(cfg["release"]["walk_back"])
        grid.attach(self.walk, 0, r, 2, 1); r += 1
        self.cesc = Gtk.CheckButton(label="CapsLock+Esc release")
        self.cesc.set_active(cfg["release"]["capslock_esc"])
        grid.attach(self.cesc, 0, r, 2, 1); r += 1
        self.inv = Gtk.CheckButton(label="Invert vertical scroll")
        self.inv.set_active(cfg["scroll"]["invert_vertical"])
        grid.attach(self.inv, 0, r, 2, 1); r += 1

        self.jig = Gtk.CheckButton(label="Jiggler enabled")
        self.jig.set_active(cfg["jiggler"]["enable"])
        grid.attach(self.jig, 0, r, 2, 1); r += 1
        grid.attach(label("Jiggler interval (s):"), 0, r, 1, 1)
        self.jint = Gtk.SpinButton.new_with_range(1, 600, 1)
        self.jint.set_value(cfg["jiggler"]["interval_sec"])
        grid.attach(self.jint, 1, r, 1, 1); r += 1
        grid.attach(label("Jiggler pixels:"), 0, r, 1, 1)
        self.jpx = Gtk.SpinButton.new_with_range(1, 50, 1)
        self.jpx.set_value(cfg["jiggler"]["pixels"])
        grid.attach(self.jpx, 1, r, 1, 1); r += 1

        note = Gtk.Label()
        note.set_xalign(0)
        note.set_markup("<small>Edge/target changes apply on restart:\n"
                        "<tt>systemctl --user restart detachment</tt></small>")
        grid.attach(note, 0, r, 2, 1); r += 1

        save = Gtk.Button(label="Save")
        save.connect("clicked", self._save)
        grid.attach(save, 0, r, 2, 1)

    def _save(self, *_):
        cfg = config.load()
        cfg["barrier_edge"] = self.edge.get_active_text()
        cfg["target"]["width"] = int(self.tw.get_value())
        cfg["target"]["height"] = int(self.th.get_value())
        cfg["release"]["walk_back"] = self.walk.get_active()
        cfg["release"]["capslock_esc"] = self.cesc.get_active()
        cfg["scroll"]["invert_vertical"] = self.inv.get_active()
        cfg["jiggler"]["enable"] = self.jig.get_active()
        cfg["jiggler"]["interval_sec"] = int(self.jint.get_value())
        cfg["jiggler"]["pixels"] = int(self.jpx.get_value())
        config.save(cfg)
        self.destroy()


def main():
    try:
        css = Gtk.CssProvider()
        css.load_from_data(BASALT_CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    except Exception:
        pass
    Tray()
    Gtk.main()


if __name__ == "__main__":
    main()

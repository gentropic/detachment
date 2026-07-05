"""
GTK tray + settings UI (the `detachment` user service entry point).

STAGE 4 will add the AppIndicator tray (LOCAL/CAPTURED state, target picker) and a libadwaita
settings window bound to config.py. For now this entry point just runs the capture agent in the
session so the service is usable end to end; the UI will wrap `agent.run()` and share its GLib loop.
"""
from . import agent


def main():
    agent.main()


if __name__ == "__main__":
    main()

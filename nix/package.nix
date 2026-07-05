{ lib, python3Packages, libei, gobject-introspection, gtk3, libayatana-appindicator
, wrapGAppsHook3, snegg }:
python3Packages.buildPythonApplication {
  pname = "detachment";
  version = "0.1.0";
  pyproject = true;
  src = ../.;

  build-system = [ python3Packages.setuptools ];
  dependencies = with python3Packages; [ dbus-python pygobject3 snegg ];

  # GTK3 + AppIndicator typelibs for the tray (runtime, via GObject-Introspection).
  nativeBuildInputs = [ gobject-introspection wrapGAppsHook3 ];
  buildInputs = [ gtk3 libayatana-appindicator ];

  # buildPythonApplication does its own wrapping; fold in the GApps env (GI_TYPELIB_PATH etc. for
  # the tray) and libei on LD_LIBRARY_PATH (snegg dlopens it) instead of a second wrapper pass.
  dontWrapGApps = true;
  makeWrapperArgs = [
    "\${gappsWrapperArgs[@]}"
    "--prefix" "LD_LIBRARY_PATH" ":" "${lib.makeLibraryPath [ libei ]}"
  ];

  # agent/capture/tray import snegg (dlopens libei) / GTK — absent in the sandbox; check the rest,
  # incl. hidd/bluez (dbus+gi only) so the build catches syntax/import errors in the daemon.
  pythonImportsCheck = [
    "detachment.config" "detachment.hid" "detachment.geometry" "detachment.evdev_hid"
    "detachment.bluez" "detachment.hidd"
  ];

  meta = {
    description = "A Linux box as a Bluetooth HID device driven by a Wayland screen-edge capture region";
    mainProgram = "detachment";
  };
}

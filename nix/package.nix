{ lib, python3Packages, libei, makeWrapper, snegg }:
python3Packages.buildPythonApplication {
  pname = "detachment";
  version = "0.1.0";
  pyproject = true;
  src = ../.;

  build-system = [ python3Packages.setuptools ];
  dependencies = with python3Packages; [ dbus-python pygobject3 snegg ];
  nativeBuildInputs = [ makeWrapper ];

  # The capture agent/tray dlopens libei via snegg's ctypes, so libei must be on the runtime linker
  # path. detachment-hidd doesn't touch snegg/libei, so only `detachment` needs the wrap.
  postFixup = ''
    wrapProgram $out/bin/detachment \
      --prefix LD_LIBRARY_PATH : ${lib.makeLibraryPath [ libei ]}
  '';

  # importing detachment.agent/capture dlopens libei (absent in the sandbox) — check the rest,
  # incl. hidd/bluez (dbus+gi only, no snegg) so build catches syntax/import errors in the daemon.
  pythonImportsCheck = [
    "detachment.config" "detachment.hid" "detachment.geometry" "detachment.evdev_hid"
    "detachment.bluez" "detachment.hidd"
  ];

  meta = {
    description = "A Linux box as a Bluetooth HID device driven by a Wayland screen-edge capture region";
    mainProgram = "detachment";
  };
}

{ config, lib, pkgs, ... }:
let
  cfg = config.services.detachment;
  # jt's radio is dedicated to being an HID *device*: the HID host (`input`) plugin is always off
  # (frees L2CAP 17/19). Audio profiles are optional (default off, so the target doesn't grab this
  # box as a speaker/mic). `sap` is never wanted.
  noPlugins = [ "input" ] ++ lib.optionals (!cfg.audio) [ "a2dp" "avrcp" "sap" ];
in
{
  options.services.detachment = {
    enable = lib.mkEnableOption "detachment — a Bluetooth HID device driven by a screen-edge capture region";

    package = lib.mkOption {
      type = lib.types.package;
      description = "The detachment package providing detachment-hidd + detachment.";
    };

    audio = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = lib.mdDoc ''
        Keep Bluetooth audio (A2DP/AVRCP) profiles alongside the HID device role. Off by default:
        a dedicated HID device shouldn't also advertise as an audio sink/mic. Re-pair the target
        after changing this.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    hardware.bluetooth = {
      enable = true;
      powerOnBoot = true;
    };

    # Run bluetoothd as an HID *device* (`--noplugin=input`, + audio plugins off by default).
    # `--compat` restores the deprecated SDP interface the HID registration path wants.
    systemd.services.bluetooth.serviceConfig.ExecStart = [
      ""
      "${config.hardware.bluetooth.package}/libexec/bluetooth/bluetoothd --compat --noplugin=${lib.concatStringsSep "," noPlugins}"
    ];

    # ── system service: root HID emitter ────────────────────────────────────────────────────
    systemd.services.detachment-hidd = {
      description = "detachment — Bluetooth HID emitter";
      after = [ "bluetooth.service" ];
      wants = [ "bluetooth.service" ];
      wantedBy = [ "multi-user.target" ];
      serviceConfig = {
        ExecStart = lib.getExe' cfg.package "detachment-hidd";
        Restart = "on-failure";
        RestartSec = 2;
        RuntimeDirectory = "detachment";      # /run/detachment for the command socket
        RuntimeDirectoryMode = "0755";
      };
    };

    # ── user service: capture agent + tray (needs the graphical session) ─────────────────────
    # NOT auto-started (no wantedBy): arming the screen-edge barrier on every login would hijack
    # the edge during normal desktop use. Start on demand — `systemctl --user start detachment`,
    # or the tray/shortcut (stage 4). Still stops cleanly with the session (partOf).
    systemd.user.services.detachment = {
      description = "detachment — capture agent + tray";
      partOf = [ "graphical-session.target" ];
      after = [ "graphical-session.target" ];
      serviceConfig = {
        ExecStart = lib.getExe cfg.package;
        Restart = "on-failure";
        RestartSec = 3;
      };
    };

    environment.systemPackages = [ cfg.package pkgs.bluez ];
  };
}

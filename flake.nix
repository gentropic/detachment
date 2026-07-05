{
  description = "detachment — a Linux box as a Bluetooth HID device driven by a Wayland screen-edge capture region (a KVM with no software on the target)";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAll = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      overlays.default = final: _prev: {
        snegg = final.python3Packages.callPackage ./nix/snegg.nix { };
        detachment = final.callPackage ./nix/package.nix { inherit (final) snegg; };
      };

      packages = forAll (pkgs:
        let
          snegg = pkgs.python3Packages.callPackage ./nix/snegg.nix { };
          detachment = pkgs.callPackage ./nix/package.nix { inherit snegg; };
        in
        {
          inherit snegg detachment;
          default = detachment;
        });

      # Import into a NixOS host, then `services.detachment.enable = true;`. Brings the overlay so
      # `pkgs.detachment` resolves and defaults the service package to it.
      nixosModules.default = { pkgs, lib, ... }: {
        imports = [ ./nix/module.nix ];
        nixpkgs.overlays = [ self.overlays.default ];
        services.detachment.package = lib.mkDefault pkgs.detachment;
      };
    };
}

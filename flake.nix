{
  description = "Blender with locked, Nix-resolved extensions";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.purifier = {
    url = "github:nix-purifiers/purifier";
    flake = false;
  };
  outputs =
    {
      self,
      nixpkgs,
      purifier,
    }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAll = nixpkgs.lib.genAttrs systems;
      overlay = final: prev: {
        blender-purifier = import ./nix/scope.nix {
          pkgs = final;
          nixpkgsSrc = nixpkgs;
          purifierSrc = purifier;
        };
      };
      pkgsFor =
        system:
        import nixpkgs {
          inherit system;
          overlays = [ overlay ];
        };
    in
    {
      overlays.default = overlay;
      packages = forAll (
        system:
        let
          p = (pkgsFor system).blender-purifier;
        in
        {
          default = p.cli;
          blender = p.original;
        }
      );
      apps = forAll (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/blender-purifier";
        };
      });
      lib.blender-purifier.readLock = import ./nix/read-lock.nix { lib = nixpkgs.lib; };
      checks = forAll (
        system:
        let
          p = (pkgsFor system).blender-purifier;
          build = p.buildBlenderProject { src = ./examples/minimal; };
        in
        {
          resource-projections = import ./tests/resource-projections.nix {
            pkgs = pkgsFor system;
            build = p.buildBlenderProject;
          };
          cli = p.cli;
          inherit (build.packages) environment project;
          release = build.release;
        }
      );
      formatter = forAll (system: (pkgsFor system).nixfmt-tree);
    };
}

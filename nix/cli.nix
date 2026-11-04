{
  lib,
  runCommand,
  writeText,
  makeWrapper,
  python3,
  original,
  scripts,
  sdk,
  nix,
  gh,
  cacert,
  nixpkgsSrc,
  purifierSrc,
}:
let
  integration = lib.fileset.toSource {
    root = ../.;
    fileset = lib.fileset.unions [
      ../blender_purifier
      ../native
      ./.
    ];
  };
  realize = writeText "blender-purifier-realize.nix" ''
    { lockPath, projectPath, target ? "environment" }:
    let
      pkgs = import (builtins.storePath "${nixpkgsSrc}") {};
      scope = import ${integration}/nix/scope.nix {
        inherit pkgs;
        nixpkgsSrc = builtins.storePath "${nixpkgsSrc}";
        purifierSrc = builtins.storePath "${purifierSrc}";
      };
      lockFile = builtins.toPath lockPath;
      src = if target == "environment" then builtins.toPath projectPath else builtins.path {
        path = builtins.toPath projectPath;
        name = "blender-project";
        filter = path: type: !(builtins.elem (baseNameOf path) [ ".git" ".blender-purifier" "__pycache__" "result" ]);
      };
      build = scope.buildBlenderProject { inherit src lockFile; };
    in if target == "environment" then scope.environment { lock = scope.readLock { inherit src lockFile; }; }
       else if target == "project" then build.packages.project
       else if target == "release" then build.release
       else throw "Unknown Blender purifier target"
  '';
in
runCommand "blender-purifier" { nativeBuildInputs = [ makeWrapper ]; } ''
  mkdir -p "$out/bin"
  for name in blender-purifier blender; do
    makeWrapper ${python3}/bin/python "$out/bin/$name" \
      --add-flags '-m blender_purifier.main' \
      --set PYTHONPATH ${integration} \
      --set BLENDER_PURIFIER_COMMAND "$name" \
      --set BLENDER_SYSTEM_RESOURCES ${scripts} \
      --set BLENDER_PURIFIER_NATIVE ${integration}/native \
      --set BLENDER_PURIFIER_BLENDER ${original}/bin/blender \
      --set BLENDER_PURIFIER_SDK ${sdk} \
      --set BLENDER_PURIFIER_REALIZE ${realize} \
      --set-default BLENDER_PURIFIER_GH ${gh}/bin/gh \
      --set-default SSL_CERT_FILE ${cacert}/etc/ssl/certs/ca-bundle.crt \
      --set-default NIX_SSL_CERT_FILE ${cacert}/etc/ssl/certs/ca-bundle.crt \
      --prefix PATH : ${
        lib.makeBinPath [
          nix
          gh
        ]
      }
  done
''

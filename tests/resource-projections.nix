{ pkgs, build }:
let
  config = builtins.fromJSON (builtins.readFile ./resource-spec.json);
  plain = build { src = ../examples/minimal; };
  args = {
    resourceRoots = config.roots;
    doCheck = true;
    checkCommand = "printf 'private sibling\\n' > \"$out/private.txt\"";
  };
  first = build (args // { src = ../examples/minimal; });
  second = build (args // { src = ./fixtures/resource-changed; });
  version = built: {
    native = toString built.packages.project;
    inherit (built.projections.resources) directory catalog;
    web = built.projections.web.documentRoot;
    jar = built.projections.java-resources.classPath;
  };
  spec = pkgs.writeText "native-resource-consumer-spec.json" (
    builtins.toJSON {
      inherit (config) roots;
      versions = [
        (version first)
        (version second)
      ];
    }
  );
  rejects =
    name: roots: messages:
    let
      actual =
        (build (
          args
          // {
            src = ../examples/minimal;
            resourceRoots = roots;
          }
        )).projections.resources;
    in
    actual.overrideAttrs (old: {
      name = "native-resource-reject-${name}";
      buildCommand = ''
        if ( ${old.buildCommand} ) > "$TMPDIR/rejection.log" 2>&1; then
          echo "unexpectedly accepted ${name}" >&2;exit 1
        fi
        ${pkgs.lib.concatMapStringsSep "\n" (
          message: "grep -F -- ${pkgs.lib.escapeShellArg message} \"$TMPDIR/rejection.log\""
        ) messages}
        mkdir -p "$out"
        cp "$TMPDIR/rejection.log" "$out/rejection.log"
      '';
    });
  missing = rejects "missing-output" { "missing-resource" = "missing-resource"; } [
    "FileNotFoundError:"
    "missing-resource"
  ];
  sourceTraversal = rejects "source-traversal" { "public" = "../private.txt"; } [
    "canonical relative resource path: ../private.txt"
  ];
  destinationTraversal = rejects "destination-traversal" {
    "../escape" = builtins.head (builtins.attrValues config.roots);
  } [ "canonical relative resource path: ../escape" ];
in
assert plain.projections == { };
assert first.projections.resources == first.packages.project.projections.resources;
pkgs.runCommand "native-export-resource-consumers"
  {
    nativeBuildInputs = [
      pkgs.python3
      pkgs.jdk25
    ];
  }
  ''
    set -euo pipefail
    test -e ${missing}
    test -e ${sourceTraversal}
    test -e ${destinationTraversal}
    cp ${./Resources.java} Resources.java
    python3 ${./resource-consumers.py} ${spec} "$out"
  ''

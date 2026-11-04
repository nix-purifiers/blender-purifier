"""Build an actual native extension archive with a wheel, then execute Nix code."""

import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

source = Path(__file__).resolve().parents[1]
original = Path(sys.argv[1]).resolve() / "bin/blender"

with tempfile.TemporaryDirectory(prefix="blender-wheels-") as temporary:
    root = Path(temporary)
    addon = root / "addon"
    (addon / "wheels").mkdir(parents=True)
    manifest = {
        "schema_version": "1.0.0",
        "id": "locked_probe",
        "version": "1.0.0",
        "name": "Locked Probe",
        "tagline": "Test native immutable wheel loading",
        "maintainer": "the nix-purifier developers",
        "type": "add-on",
        "blender_version_min": "5.2.0",
        "license": ["SPDX:MIT"],
        "wheels": ["./wheels/locked_dependency-1.0.0-py3-none-any.whl"],
    }
    (addon / "blender_manifest.toml").write_text(
        "\n".join(f"{key} = {json.dumps(value)}" for key, value in manifest.items())
        + "\n"
    )
    (addon / "__init__.py").write_text(
        "import bpy, locked_dependency\n"
        "assert locked_dependency.__file__.startswith('/nix/store/')\n"
        "assert locked_dependency.ANSWER == 42\n"
        "class LOCKED_OT_probe(bpy.types.Operator):\n"
        "    bl_idname = 'locked.probe'\n    bl_label = 'Locked Probe'\n"
        "    def execute(self,context):\n        context.scene['wheel_answer'] = locked_dependency.ANSWER\n        return {'FINISHED'}\n"
        "def register(): bpy.utils.register_class(LOCKED_OT_probe)\n"
        "def unregister(): bpy.utils.unregister_class(LOCKED_OT_probe)\n"
    )
    with zipfile.ZipFile(
        addon / "wheels/locked_dependency-1.0.0-py3-none-any.whl", "w"
    ) as wheel:
        wheel.writestr("locked_dependency/__init__.py", "ANSWER = 42\n")
        info = "locked_dependency-1.0.0.dist-info"
        wheel.writestr(
            info + "/WHEEL",
            "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        wheel.writestr(
            info + "/METADATA",
            "Metadata-Version: 2.1\nName: locked-dependency\nVersion: 1.0.0\n",
        )
        wheel.writestr(
            info + "/RECORD",
            "\n".join(
                f"{name},,"
                for name in [
                    "locked_dependency/__init__.py",
                    info + "/WHEEL",
                    info + "/METADATA",
                    info + "/RECORD",
                ]
            )
            + "\n",
        )
    env = os.environ.copy() | {
        "BLENDER_USER_RESOURCES": str(root / "user"),
        "XDG_CACHE_HOME": str(root / "cache"),
    }
    subprocess.run(
        [
            str(original),
            "-b",
            "--factory-startup",
            "--command",
            "extension",
            "build",
            "--source-dir",
            str(addon),
            "--output-dir",
            str(root),
        ],
        check=True,
        env=env,
    )
    archive = root / "locked_probe-1.0.0.zip"
    digest = (
        "sha256-"
        + base64.b64encode(hashlib.sha256(archive.read_bytes()).digest()).decode()
    )
    selection = {
        "repositories": [
            {
                "id": "locked",
                "url": "https://example.invalid/index.json",
                "extensions": ["locked_probe"],
            }
        ]
    }
    (root / "blender-purifier.json").write_text(json.dumps(selection))
    sdk = json.loads(
        (source / "examples/minimal/blender-purifier.lock.json").read_text()
    )["sdk"]
    lock = {
        "version": 1,
        "purifier": "blender",
        "sdk": sdk,
        "selection": selection,
        "entries": [
            {
                "path": "locked/locked_probe.zip",
                "url": "https://example.invalid/locked_probe.zip",
                "hash": digest,
                "mirrors": [],
                "blender": {"repository": "locked", "manifest": manifest},
            }
        ],
    }
    (root / "blender-purifier.lock.json").write_text(json.dumps(lock))
    expression = root / "test.nix"
    expression.write_text("""{ projectRoot, fixtureRoot, archivePath }:
let
  source = builtins.path { path = builtins.toPath projectRoot; name = "blender-purifier-source"; filter = path: type: baseNameOf path != ".git"; };
  flake = builtins.getFlake ("path:" + projectRoot);
  pkgs = import flake.inputs.nixpkgs {};
  scope = import (source + "/nix/scope.nix") {
    inherit pkgs;
    nixpkgsSrc = flake.inputs.nixpkgs;
    purifierSrc = flake.inputs.purifier;
  };
  lock = scope.readLock { src = builtins.toPath fixtureRoot; };
  archive = builtins.path { path = builtins.toPath archivePath; name = "probe.zip"; };
  profile = scope.environment { inherit lock; fetchers.fetchurl = args:
    assert args.hash == (builtins.head lock.entries).hash; archive;
  };
in pkgs.runCommand "blender-immutable-wheel-proof" {} \'\'
  export HOME="$TMPDIR/home" BLENDER_USER_RESOURCES="$TMPDIR/user" XDG_CACHE_HOME="$TMPDIR/cache"
  export BLENDER_SYSTEM_RESOURCES=${scope.scripts} BLENDER_PURIFIER_ENVIRONMENT=${profile}
  poison="$BLENDER_USER_RESOURCES/extensions/.local/lib/python3.13/site-packages"
  mkdir -p "$HOME" "$poison"
  printf '%s\\n' "raise RuntimeError('poisoned mutable wheel cache')" > "$poison/locked_dependency.py"
  ${scope.original}/bin/blender -b --factory-startup --python-exit-code 1 \\
    --python ${source}/native/startup.py \\
    --python-expr "import bpy,locked_dependency; assert bpy.ops.locked.probe()=={'FINISHED'}; assert bpy.context.scene['wheel_answer']==42; assert locked_dependency.__file__.startswith('/nix/store/')"
  test -f "$poison/locked_dependency.py"
  mkdir -p "$out"
  printf '%s\\n' passed > "$out/result"
\'\'
""")
    subprocess.run(
        [
            "nix",
            "build",
            "--impure",
            "--file",
            str(expression),
            "--argstr",
            "projectRoot",
            str(source),
            "--argstr",
            "fixtureRoot",
            str(root),
            "--argstr",
            "archivePath",
            str(archive),
            "--out-link",
            str(root / "result"),
            "-L",
        ],
        check=True,
        env=env,
    )
    assert (root / "result/result").read_text() == "passed\n"
print("native immutable Blender wheels passed")

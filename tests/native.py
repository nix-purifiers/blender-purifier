"""Exercise the native application, dependency isolation and ordinary fallback."""

import gzip
import hashlib
import http.server
import json
import os
import pickle
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

cli = Path(sys.argv[1]).resolve() / "bin"
original_binary = Path(sys.argv[2]).resolve() / "bin/blender"
source = Path(__file__).resolve().parents[1]


def command(args, *, env, cwd, success=True):
    result = subprocess.run(
        args, check=False, env=env, cwd=cwd, capture_output=True, text=True
    )
    if success and result.returncode:
        raise AssertionError(result.stdout + result.stderr)
    if not success and result.returncode == 0:
        raise AssertionError("expected command failure: " + repr(args))
    return result


with tempfile.TemporaryDirectory(prefix="blender-native-") as temporary:
    root = Path(temporary)
    project = root / "project"
    shutil.copytree(
        source / "examples/minimal",
        project,
        ignore=shutil.ignore_patterns(".blender-purifier"),
    )
    env = os.environ.copy()
    env.update(
        BLENDER_PURIFIER_PROJECT=str(project), XDG_CACHE_HOME=str(root / "cache")
    )
    lock = project / "blender-purifier.lock.json"
    digest = hashlib.sha256(lock.read_bytes()).hexdigest()
    # Native source edits preserve the exact frozen dependency lock.
    for answer in [42, 43, 42]:
        program = (
            "import bpy, bl_ext.community.boltfactory as extension; "
            "assert extension.__file__.startswith('/nix/store/'); "
            "assert bpy.ops.mesh.bolt_add()=={'FINISHED'}; "
            f"bpy.context.scene['answer']={answer}; "
            "print('ANSWER',bpy.context.scene['answer'],len(bpy.context.active_object.data.vertices))"
        )
        (project / "probe.py").write_text(program + "\n")
        result = command(
            [str(cli / "blender"), "-b", "--factory-startup", "--python", "probe.py"],
            env=env,
            cwd=project,
        )
        assert f"ANSWER {answer} 2736" in result.stdout, result.stdout
        assert hashlib.sha256(lock.read_bytes()).hexdigest() == digest
    profile = project / ".blender-purifier/environment"
    assert (
        profile.is_symlink()
        and (profile / "repositories/community/boltfactory").is_dir()
    )
    roots = command(
        ["nix-store", "--query", "--roots", str(profile.resolve())],
        env=env,
        cwd=project,
    )
    assert str(profile) in roots.stdout, roots.stdout
    # Existing user cache does not supply executable extension code.
    cache = project / ".blender-purifier/user/extensions/user_default/boltfactory"
    cache.mkdir(parents=True)
    (cache / "__init__.py").write_text(
        "raise RuntimeError('poisoned ambient extension')\n"
    )
    result = command(
        [
            str(cli / "blender"),
            "-b",
            "--python-expr",
            "import bpy; assert bpy.ops.mesh.bolt_add()=={'FINISHED'}",
        ],
        env=env,
        cwd=project,
    )
    assert (cache / "__init__.py").read_text().startswith("raise RuntimeError")
    # Saved preferences must be constrained before Blender's startup addon loader.
    poison = root / "poison/evil"
    poison.mkdir(parents=True)
    marker = root / "unlocked-startup-ran"
    (poison / "blender_manifest.toml").write_text(
        'schema_version="1.0.0"\nid="evil"\nname="Evil"\nversion="1.0.0"\n'
        'tagline="Startup isolation probe"\nmaintainer="test"\ntype="add-on"\n'
        'blender_version_min="5.2.0"\nlicense=["SPDX:MIT"]\n'
    )
    (poison / "__init__.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"
        "def register(): pass\ndef unregister(): pass\n"
    )
    stale = poison.parent / "boltfactory"
    stale.mkdir()
    (stale / "blender_manifest.toml").write_text(
        (poison / "blender_manifest.toml")
        .read_text()
        .replace('id="evil"', 'id="boltfactory"')
    )
    (stale / "__init__.py").write_text((poison / "__init__.py").read_text())
    setup = (
        "import bpy; repos=bpy.context.preferences.extensions.repos; "
        f"repos.new(name='poison',module='poison',custom_directory={str(poison.parent)!r},source='USER'); "
        "bpy.context.preferences.addons.new(module='bl_ext.poison.evil'); "
        f"repos.new(name='stale',module='community',custom_directory={str(poison.parent)!r},source='USER'); "
        "bpy.context.preferences.addons.new(module='bl_ext.community.boltfactory'); bpy.ops.wm.save_userpref()"
    )
    prefs_env = env | {
        "BLENDER_USER_RESOURCES": str(project / ".blender-purifier/user")
    }
    command(
        [str(original_binary), "-b", "--factory-startup", "--python-expr", setup],
        env=prefs_env,
        cwd=project,
    )

    class CacheProbe:
        def __reduce__(self):
            return (marker.write_text, ("mutable-pickle-executed",))

    compat = project / ".blender-purifier/user/extensions/.cache/compat.dat"
    compat.parent.mkdir(parents=True, exist_ok=True)
    cache_bytes = gzip.compress(pickle.dumps(CacheProbe()))
    compat.write_bytes(cache_bytes)
    command(
        [
            str(cli / "blender"),
            "-b",
            "--python-expr",
            "import bpy; assert bpy.ops.mesh.bolt_add()=={'FINISHED'}",
        ],
        env=env,
        cwd=project,
    )
    assert not marker.exists(), (
        "saved preferences executed an unlocked addon before the purifier initialized"
    )
    assert compat.read_bytes() == cache_bytes, (
        "ambient compatibility cache was overwritten"
    )

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"root-network-ok")

        def log_message(self, *args):
            pass

    with http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        program = (
            "import urllib.request; "
            f"assert urllib.request.urlopen('http://127.0.0.1:{server.server_port}/').read()==b'root-network-ok'"
        )
        try:
            command(
                [str(cli / "blender"), "-b", "--python-expr", program],
                env=env,
                cwd=project,
            )
        finally:
            server.shutdown()
            thread.join()
    mutation = (
        "import bl_ext.community.boltfactory as p; open(p.__file__,'w').write('poison')"
    )
    command(
        [str(cli / "blender"), "-b", "--python-expr", mutation],
        env=env,
        cwd=project,
        success=False,
    )
    manager = (
        "import bpy; bpy.context.preferences.extensions.repos.new(name='unlocked',module='unlocked',"
        f"custom_directory={str(root / 'unlocked')!r},source='USER'); bpy.ops.extensions.repo_refresh_all()"
    )
    command(
        [str(cli / "blender"), "-b", "--python-expr", manager],
        env=env,
        cwd=project,
        success=False,
    )
    # Manifest drift fails before executing project code.
    selection = project / "blender-purifier.json"
    original = selection.read_bytes()
    value = json.loads(original)
    value["repositories"][0]["extensions"].append("f2")
    selection.write_text(json.dumps(value))
    result = command(
        [str(cli / "blender"), "-b", "--python-expr", "print('SHOULD_NOT_EXECUTE')"],
        env=env,
        cwd=project,
        success=False,
    )
    assert "SHOULD_NOT_EXECUTE" not in result.stdout
    selection.write_bytes(original)
    # No-lock fallback has native streams/status plus exactly one stderr warning.
    empty = root / "empty"
    empty.mkdir()
    fallback_env = env | {"BLENDER_PURIFIER_PROJECT": str(empty)}
    args = [
        "-b",
        "--factory-startup",
        "--python-exit-code",
        "17",
        "--python-expr",
        "raise RuntimeError('native-probe')",
    ]
    expected = command(
        [str(original_binary), *args], env=fallback_env, cwd=empty, success=False
    )
    actual = command(
        [str(cli / "blender"), *args], env=fallback_env, cwd=empty, success=False
    )
    warning = "warning: no Blender purifier lock; using ordinary, impure extension resolution\n"
    assert actual.returncode == expected.returncode == 17
    assert actual.stdout == expected.stdout, (actual.stdout, expected.stdout)
    assert actual.stderr == warning + expected.stderr, (actual.stderr, expected.stderr)
print("native Blender integration passed")

"""Consume exported native geometry, external locks and exact release assets."""

import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

cli = Path(sys.argv[1]).resolve() / "bin/blender-purifier"
original = Path(sys.argv[2]).resolve() / "bin/blender"
source = Path(__file__).resolve().parents[1]


def call(arguments, *, env, cwd):
    result = subprocess.run(
        arguments, check=True, env=env, cwd=cwd, text=True, capture_output=True
    )
    return result.stdout.strip()


with tempfile.TemporaryDirectory(prefix="blender-artifacts-") as temporary:
    root = Path(temporary)
    project = root / "project"
    shutil.copytree(
        source / "examples/minimal",
        project,
        ignore=shutil.ignore_patterns(".blender-purifier"),
    )
    env = os.environ.copy() | {"XDG_CACHE_HOME": str(root / "cache")}
    args = [str(cli), "--project", str(project)]
    build = Path(call([*args, "build"], env=env, cwd=root))
    assert (build / "answer.txt").read_text() == "answer=42\n"
    program = (
        "import bpy; bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(); "
        f"bpy.ops.wm.obj_import(filepath={str(build / 'bolt.obj')!r}); "
        "assert len(bpy.context.active_object.data.vertices)==2736; print('NATIVE_OBJ_OK')"
    )
    output = call(
        [
            str(original),
            "-b",
            "--factory-startup",
            "--python-exit-code",
            "1",
            "--python-expr",
            program,
        ],
        env=env,
        cwd=root,
    )
    assert "NATIVE_OBJ_OK" in output
    release = Path(call([*args, "bundle"], env=env, cwd=root))
    archive = release / "blender-project.tar.gz"
    with tarfile.open(archive) as tar:
        assert tar.extractfile("./answer.txt").read() == b"answer=42\n"
        assert tar.extractfile("./bolt.obj").read() == (build / "bolt.obj").read_bytes()
    external = root / "external-lock.json"
    shutil.copyfile(project / "blender-purifier.lock.json", external)
    replay = Path(call([*args, "--lock", str(external), "bundle"], env=env, cwd=root))
    assert (replay / archive.name).read_bytes() == archive.read_bytes()
    fake = root / "gh"
    fake.write_text(
        f"#!{sys.executable}\nimport json,os,sys\nfrom pathlib import Path\n"
        "Path(os.environ['UPLOAD_RECORD']).write_text(json.dumps(sys.argv[1:]))\n"
        "Path(os.environ['UPLOAD_BYTES']).write_bytes(Path(sys.argv[4]).read_bytes())\n"
    )
    fake.chmod(0o755)
    publish_env = env | {
        "BLENDER_PURIFIER_GH": str(fake),
        "UPLOAD_RECORD": str(root / "upload.json"),
        "UPLOAD_BYTES": str(root / "upload.tar.gz"),
    }
    call([*args, "publish", "--tag", "proof"], env=publish_env, cwd=root)
    record = json.loads((root / "upload.json").read_text())
    assert record[:3] == ["release", "upload", "proof"] and record[3] == str(archive)
    assert (root / "upload.tar.gz").read_bytes() == archive.read_bytes()
print("native Blender artifact consumers passed")

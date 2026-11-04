"""Fresh native capture, cold replay and atomic failure against the public catalog."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

cli = Path(sys.argv[1]).resolve() / "bin/blender-purifier"
source = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="blender-capture-") as temporary:
    project = Path(temporary)
    shutil.copyfile(
        source / "examples/minimal/blender-purifier.json",
        project / "blender-purifier.json",
    )
    env = os.environ.copy() | {"BLENDER_PURIFIER_PROJECT": str(project)}
    subprocess.run([str(cli), "lock", "--update"], check=True, env=env, cwd=project)
    lock = project / "blender-purifier.lock.json"
    before = lock.read_bytes()
    subprocess.run([str(cli), "lock"], check=True, env=env, cwd=project)
    subprocess.run([str(cli), "prefetch"], check=True, env=env, cwd=project)
    assert lock.read_bytes() == before
    selection_file = project / "blender-purifier.json"
    selection = json.loads(selection_file.read_text())
    selection["repositories"][0]["extensions"].append(
        "purifier_missing_extension_probe"
    )
    selection_file.write_text(json.dumps(selection))
    failed = subprocess.run(
        [str(cli), "lock", "--update"], check=False, env=env, cwd=project
    )
    assert failed.returncode != 0 and lock.read_bytes() == before
    empty = project / "empty"
    empty.mkdir()
    (empty / "blender-purifier.json").write_text('{"repositories": []}\n')
    empty_env = env | {"BLENDER_PURIFIER_PROJECT": str(empty)}
    subprocess.run([str(cli), "lock", "--update"], check=True, env=empty_env, cwd=empty)
    subprocess.run(
        [
            str(cli),
            "exec",
            "--",
            "-b",
            "--python-expr",
            "import bpy; assert bpy.context.scene is not None",
        ],
        check=True,
        env=empty_env,
        cwd=empty,
    )
print("native Blender capture and atomic failure passed")

"""Dependency preparation must ignore unrelated working-tree payloads."""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

source = Path(__file__).resolve().parents[1]
cli = Path(sys.argv[1]).resolve() / "bin/blender-purifier"
with tempfile.TemporaryDirectory(prefix="blender-dependencies-") as temporary:
    project = Path(temporary) / "project"
    shutil.copytree(
        source / "examples/minimal",
        project,
        ignore=shutil.ignore_patterns(".blender-purifier", "output"),
    )
    os.mkfifo(project / "unrelated-live-stream")
    result = subprocess.run(
        [cli, "--project", project, "prefetch"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (project / "unrelated-live-stream").is_fifo()
print("blender dependency preparation leaves working-tree payloads outside Nix")

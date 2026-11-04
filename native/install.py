"""Native archive installation into the Nix output; never execute addon code."""

import json
import os
from pathlib import Path

from bl_pkg.bl_extension_cli import subcmd_pkg, subcmd_repo

data = json.loads(Path(os.environ["BLENDER_PURIFIER_INSTALL"]).read_text())
out = Path(os.environ["out"])
(out / "repositories").mkdir(parents=True, exist_ok=True)
for index, repo in enumerate(data["repositories"]):
    directory = out / "repositories" / repo
    directory.mkdir(parents=True)
    assert subcmd_repo.add(
        name=repo,
        repo_id=repo,
        directory=str(directory),
        url="",
        access_token="",
        source="USER",
        cache=False,
        clear_all=index == 0,
        no_prefs=True,
    )
    for item in data["entries"]:
        if item["repository"] != repo:
            continue
        assert subcmd_pkg.install_file(
            filepath=item["file"],
            repo_id=repo,
            enable_on_install=False,
            no_prefs=True,
        )
        import tomllib

        actual = tomllib.loads(
            (directory / item["id"] / "blender_manifest.toml").read_text()
        )
        if actual != item["manifest"]:
            raise RuntimeError(f"archive manifest changed: {repo}.{item['id']}")
    import shutil

    shutil.rmtree(directory / ".blender_ext", ignore_errors=True)

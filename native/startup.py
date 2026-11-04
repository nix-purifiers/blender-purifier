"""Initialize only the locked native system repositories in a private profile."""

import json
import os
import sys
from pathlib import Path

import addon_utils
import bpy

profile = Path(os.environ["BLENDER_PURIFIER_ENVIRONMENT"]).resolve()
lock = json.loads((profile / "lock.json").read_text())
wheels_root = (profile / "wheels").resolve()
version = (wheels_root / "python-version").read_text().strip()
site = wheels_root / f"lib/python{version}/site-packages"
allowed = {
    name: [str(Path(path).resolve()) for path in paths]
    for name, paths in json.loads((wheels_root / "wheels.json").read_text())
}


def frozen_wheels(*, local_dir, wheel_list, debug, error_fn):
    for name, paths in wheel_list:
        if [str(Path(path).resolve()) for path in paths] != allowed.get(name):
            raise RuntimeError(
                f"unlocked Blender wheels: {name}; update the purifier lock"
            )
    if site.is_dir() and str(site) not in sys.path:
        sys.path.insert(0, str(site))


addon_utils._extension_sync_wheels = frozen_wheels
repos = bpy.context.preferences.extensions.repos
expected_repos = {
    repo["id"]: (profile / "repositories" / repo["id"]).resolve()
    for repo in lock["selection"]["repositories"]
}
if {repo.module: Path(repo.directory).resolve() for repo in repos} != expected_repos:
    while repos:
        repos.remove(repos[0])
    for repo in lock["selection"]["repositories"]:
        repos.new(
            name=repo["id"],
            module=repo["id"],
            source="SYSTEM",
            custom_directory=str(profile / "repositories" / repo["id"]),
        )

# Restrict native extension management, while leaving application networking alone.
import bl_pkg

original_repo_paths = bl_pkg.repo_paths_or_none
locked_repos = {
    repo["id"]: (profile / "repositories" / repo["id"]).resolve()
    for repo in lock["selection"]["repositories"]
}


def locked_repo_paths(repo):
    expected = locked_repos.get(repo.module)
    if (
        expected is None
        or repo.source != "SYSTEM"
        or repo.use_remote_url
        or Path(repo.directory).resolve() != expected
    ):
        raise RuntimeError(
            "unlocked Blender repository; run blender-purifier lock --update"
        )
    return original_repo_paths(repo)


bl_pkg.repo_paths_or_none = locked_repo_paths
if repos:
    bpy.ops.extensions.repo_refresh_all()
for entry in lock["entries"]:
    item = entry["blender"]
    if item["manifest"]["type"] == "add-on":
        name = f"bl_ext.{item['repository']}.{item['manifest']['id']}"
        module = addon_utils.enable(name, default_set=True, persistent=True)
        if module is None:
            raise RuntimeError(f"failed to enable locked extension: {name}")

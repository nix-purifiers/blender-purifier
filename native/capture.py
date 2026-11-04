"""Run inside the pinned Blender: native repository selection and installation."""

import json
import os
from pathlib import Path

import bpy
from bl_pkg import repo_cache_store_ensure
from bl_pkg.bl_extension_cli import subcmd_pkg, subcmd_repo
from bl_pkg.bl_extension_utils import pkg_manifest_archive_url_abs_from_remote_url

request = json.loads(Path(os.environ["BLENDER_PURIFIER_REQUEST"]).read_text())
root = Path(os.environ["BLENDER_PURIFIER_CAPTURE"])
bpy.context.preferences.system.use_online_access = True
selected = []
for index, repo in enumerate(request["repositories"]):
    module = repo["id"]
    directory = root / module
    assert subcmd_repo.add(
        name=module,
        repo_id=module,
        directory=str(directory),
        url=repo["url"],
        access_token="",
        source="USER",
        cache=True,
        clear_all=index == 0,
        no_prefs=True,
    )
    if not repo["extensions"]:
        continue
    assert subcmd_pkg.install(
        sync=True,
        packages=[f"{module}.{name}" for name in repo["extensions"]],
        enable_on_install=False,
        no_prefs=True,
    )
    data = json.loads((directory / ".blender_ext/index.json").read_text())

    def error(exception):
        raise exception

    native_remote = list(
        repo_cache_store_ensure().pkg_manifest_from_remote_ensure(error_fn=error)
    )[index]
    for name in repo["extensions"]:
        import tomllib

        manifest = tomllib.loads(
            (directory / name / "blender_manifest.toml").read_text()
        )
        chosen = native_remote[name]
        matches = [
            item
            for item in data["data"]
            if item["id"] == name
            and item["version"] == manifest["version"]
            and item["archive_url"] == chosen.archive_url
        ]
        if len(matches) != 1:
            raise RuntimeError(f"ambiguous native selection: {module}.{name}")
        archive = dict(matches[0])
        archive["archive_url"] = pkg_manifest_archive_url_abs_from_remote_url(
            repo["url"], chosen.archive_url
        )
        selected.append(
            {"repository": module, "manifest": manifest, "archive": archive}
        )
(root / "selection.json").write_text(json.dumps(selected, indent=2) + "\n")

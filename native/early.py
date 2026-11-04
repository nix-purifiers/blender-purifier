"""Select immutable repositories and wheels before Blender loads saved add-ons."""

import json
import os
import sys
from pathlib import Path


def initialize(namespace):
    value = os.environ.get("BLENDER_PURIFIER_ENVIRONMENT")
    if not value:
        return
    profile = Path(value).resolve()
    lock = json.loads((profile / "lock.json").read_text())
    enabled = {
        f"bl_ext.{entry['blender']['repository']}.{entry['blender']['manifest']['id']}"
        for entry in lock["entries"]
    }
    preferences = namespace["_preferences"]
    for addon in list(preferences.addons):
        if addon.module.startswith("bl_ext.") and addon.module not in enabled:
            preferences.addons.remove(addon)
    repos = preferences.extensions.repos
    while repos:
        repos.remove(repos[0])
    for repo in lock["selection"]["repositories"]:
        repos.new(
            name=repo["id"],
            module=repo["id"],
            source="SYSTEM",
            custom_directory=str(profile / "repositories" / repo["id"]),
        )
    wheels = (profile / "wheels").resolve()
    version = (wheels / "python-version").read_text().strip()
    site = wheels / f"lib/python{version}/site-packages"
    allowed = {
        name: [str(Path(path).resolve()) for path in paths]
        for name, paths in json.loads((wheels / "wheels.json").read_text())
    }

    def site_packages(*, extensions_directory, create=False):
        if site.is_dir() and str(site) not in sys.path:
            sys.path.insert(0, str(site))
        return str(site) if site.is_dir() else None

    def sync_wheels(*, local_dir, wheel_list, debug, error_fn):
        for name, paths in wheel_list:
            if [str(Path(path).resolve()) for path in paths] != allowed.get(name):
                raise RuntimeError(f"unlocked Blender wheels: {name}")
        site_packages(extensions_directory="")

    namespace["_initialize_extensions_site_packages"] = site_packages
    namespace["_extension_sync_wheels"] = sync_wheels
    # Native compatibility checks still run against the locked manifests. Their
    # pickle cache must not become an executable input from mutable user state.
    namespace["_pickle_zlib_file_read"] = lambda path: None
    namespace["_pickle_zlib_file_write"] = lambda path, data: None

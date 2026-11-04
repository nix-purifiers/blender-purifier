"""Build wheel code using Blender's own wheel installer and compatibility filter."""

import json
import os
import sys
from pathlib import Path

import addon_utils
from bl_pkg.bl_extension_ops import pkg_wheel_filter

profile = Path(os.environ["BLENDER_PURIFIER_PROFILE"])
lock = json.loads(Path(os.environ["BLENDER_PURIFIER_LOCK_DATA"]).read_text())
wheels = []
for item in lock["entries"]:
    manifest = item["blender"]["manifest"]
    repo = item["blender"]["repository"]
    filtered = pkg_wheel_filter(
        repo,
        manifest["id"],
        str(profile / "repositories" / repo),
        manifest.get("wheels", []),
    )
    if filtered:
        wheels.append(filtered)


def error(exception):
    raise exception


addon_utils._extension_sync_wheels(
    local_dir=os.environ["out"],
    wheel_list=wheels,
    debug=False,
    error_fn=error,
)
Path(os.environ["out"], "wheels.json").write_text(
    json.dumps(wheels, sort_keys=True) + "\n"
)
Path(os.environ["out"], "python-version").write_text(
    f"{sys.version_info.major}.{sys.version_info.minor}\n"
)

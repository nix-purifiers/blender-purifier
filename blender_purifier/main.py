"""Blender's normal application workflow with a frozen native extension profile."""

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urljoin, urlsplit


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def public_url(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise ValueError(
            "extension repositories and archives must use public HTTPS URLs"
        )
    return url


def selection(project):
    value = json.loads((project / "blender-purifier.json").read_text())
    if set(value) != {"repositories"} or not isinstance(value["repositories"], list):
        raise ValueError("blender-purifier.json needs a repositories list")
    seen = set()
    for repo in value["repositories"]:
        if set(repo) != {"id", "url", "extensions"} or not re.fullmatch(
            r"[a-z][a-z0-9_]*", repo["id"]
        ):
            raise ValueError(
                "each repository needs an identifier, URL and extensions list"
            )
        if repo["id"] in seen:
            raise ValueError("duplicate repository identifier")
        seen.add(repo["id"])
        public_url(repo["url"])
        extensions = repo["extensions"]
        if not isinstance(extensions, list) or len(set(extensions)) != len(extensions):
            raise ValueError("extensions must be a list of unique identifiers")
        if any(
            not isinstance(item, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", item)
            for item in extensions
        ):
            raise ValueError("invalid extension identifier")
    return value


def project_path(explicit):
    if explicit:
        return Path(explicit).resolve()
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / "blender-purifier.json").exists() or (
            parent / "blender-purifier.lock.json"
        ).exists():
            return parent
    return current


def validate(project, lock):
    data = json.loads(lock.read_text())
    if data.get("version") != 1 or data.get("purifier") != "blender":
        raise ValueError("unsupported Blender lock")
    if data.get("sdk") != os.environ["BLENDER_PURIFIER_SDK"]:
        raise ValueError("Blender SDK changed; run blender-purifier lock --update")
    if data.get("selection") != selection(project):
        raise ValueError(
            "extension selection changed; run blender-purifier lock --update"
        )
    return data


def realize(project, lock, target="environment", out_link=None):
    args = [
        "nix",
        "build",
        "--impure",
        "--file",
        os.environ["BLENDER_PURIFIER_REALIZE"],
        "--argstr",
        "projectPath",
        str(project),
        "--argstr",
        "lockPath",
        str(lock),
        "--argstr",
        "target",
        target,
        "--json",
    ]
    args += ["--out-link", str(out_link)] if out_link else ["--no-link"]
    result = run(args, stdout=subprocess.PIPE, text=True)
    return Path(json.loads(result.stdout)[0]["outputs"]["out"])


def blender_env(resources):
    env = os.environ.copy()
    env.pop("BLENDER_PURIFIER_ENVIRONMENT", None)
    for name in [
        "BLENDER_USER_CONFIG",
        "BLENDER_USER_SCRIPTS",
        "BLENDER_USER_EXTENSIONS",
        "BLENDER_USER_DATAFILES",
        "BLENDER_SYSTEM_SCRIPTS",
        "BLENDER_SYSTEM_EXTENSIONS",
    ]:
        env.pop(name, None)
    env["BLENDER_USER_RESOURCES"] = str(resources)
    env["XDG_CACHE_HOME"] = str(resources / "cache")
    return env


def capture(project, lock):
    requested = selection(project)
    native = Path(os.environ["BLENDER_PURIFIER_NATIVE"])
    with tempfile.TemporaryDirectory(prefix="blender-purifier-") as temporary:
        root = Path(temporary)
        request = root / "request.json"
        request.write_text(json.dumps(requested))
        env = blender_env(root / "user")
        env.update(
            BLENDER_PURIFIER_REQUEST=str(request), BLENDER_PURIFIER_CAPTURE=str(root)
        )
        run(
            [
                os.environ["BLENDER_PURIFIER_BLENDER"],
                "-b",
                "--factory-startup",
                "--python-exit-code",
                "1",
                "--python",
                str(native / "capture.py"),
            ],
            env=env,
        )
        entries = []
        for item in json.loads((root / "selection.json").read_text()):
            manifest = item["manifest"]
            if manifest["type"] != "add-on":
                raise ValueError(
                    "the initial Blender integration supports add-on extensions"
                )
            repo = next(
                r for r in requested["repositories"] if r["id"] == item["repository"]
            )
            archive = item["archive"]
            url = public_url(urljoin(repo["url"], archive["archive_url"]))
            selected_hash = archive["archive_hash"]
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", selected_hash):
                raise ValueError(
                    "native repository did not provide a SHA256 archive hash"
                )
            expected = (
                "sha256-" + base64.b64encode(bytes.fromhex(selected_hash[7:])).decode()
            )
            fetched = json.loads(
                run(
                    ["nix", "store", "prefetch-file", "--json", url],
                    stdout=subprocess.PIPE,
                    text=True,
                ).stdout
            )
            if fetched["hash"] != expected:
                raise ValueError(
                    "Nix archive hash disagrees with Blender's native selection"
                )
            entries.append(
                {
                    "path": f"{repo['id']}/{manifest['id']}.zip",
                    "url": url,
                    "hash": expected,
                    "mirrors": [],
                    "blender": {"repository": repo["id"], "manifest": manifest},
                }
            )
        data = {
            "version": 1,
            "purifier": "blender",
            "sdk": os.environ["BLENDER_PURIFIER_SDK"],
            "selection": requested,
            "entries": sorted(entries, key=lambda e: e["path"]),
        }
        candidate = root / "blender-purifier.lock.json"
        candidate.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        realize(project, candidate)
        lock.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", dir=lock.parent, delete=False
        ) as output:
            output.write(candidate.read_text())
            pending = Path(output.name)
        try:
            os.replace(pending, lock)
        finally:
            pending.unlink(missing_ok=True)


def native_exec(project, lock, arguments):
    original = os.environ["BLENDER_PURIFIER_BLENDER"]
    if not lock.exists():
        print(
            "warning: no Blender purifier lock; using ordinary, impure extension resolution",
            file=sys.stderr,
        )
        env = os.environ.copy()
        env.pop("BLENDER_PURIFIER_ENVIRONMENT", None)
        os.execve(original, [original, *arguments], env)
    validate(project, lock)
    state = project / ".blender-purifier"
    state.mkdir(exist_ok=True)
    environment = realize(project, lock, out_link=state / "environment")
    env = blender_env(state / "user")
    env["BLENDER_PURIFIER_ENVIRONMENT"] = str(environment)
    script = str(Path(os.environ["BLENDER_PURIFIER_NATIVE"]) / "startup.py")
    os.execve(
        original,
        [original, "--python-exit-code", "1", "--python", script, *arguments],
        env,
    )


def main():
    if os.environ.get("BLENDER_PURIFIER_COMMAND") == "blender":
        project = project_path(os.environ.get("BLENDER_PURIFIER_PROJECT"))
        lock = Path(
            os.environ.get(
                "BLENDER_PURIFIER_LOCK", project / "blender-purifier.lock.json"
            )
        ).resolve()
        native_exec(project, lock, sys.argv[1:])
        return
    parser = argparse.ArgumentParser()
    parser.add_argument("--project")
    parser.add_argument("--lock")
    sub = parser.add_subparsers(dest="action", required=True)
    lock_parser = sub.add_parser("lock")
    lock_parser.add_argument("--update", action="store_true")
    sub.add_parser("prefetch")
    for name in ["build", "bundle"]:
        sub.add_parser(name)
    publish = sub.add_parser("publish")
    publish.add_argument("--tag", required=True)
    execute = sub.add_parser("exec")
    execute.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    project = project_path(args.project or os.environ.get("BLENDER_PURIFIER_PROJECT"))
    lock = Path(
        args.lock
        or os.environ.get(
            "BLENDER_PURIFIER_LOCK", project / "blender-purifier.lock.json"
        )
    ).resolve()
    if args.action == "lock" and args.update:
        capture(project, lock)
        return
    if args.action == "exec":
        arguments = (
            args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
        )
        native_exec(project, lock, arguments)
        return
    validate(project, lock)
    if args.action == "lock":
        realize(project, lock)
    elif args.action == "prefetch":
        print(realize(project, lock))
    elif args.action in {"build", "bundle"}:
        print(
            realize(project, lock, "project" if args.action == "build" else "release")
        )
    elif args.action == "publish":
        release = realize(project, lock, "release")
        run(
            [
                os.environ.get("BLENDER_PURIFIER_GH", "gh"),
                "release",
                "upload",
                args.tag,
                str(release / "blender-project.tar.gz"),
                "--clobber",
            ]
        )


if __name__ == "__main__":
    try:
        main()
    except (
        ValueError,
        KeyError,
        TypeError,
        OSError,
        subprocess.CalledProcessError,
    ) as error:
        print(f"blender-purifier: {error}", file=sys.stderr)
        sys.exit(1)

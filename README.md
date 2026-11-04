# blender-purifier

Run Blender with locked, Nix-resolved extensions.

## Quickstart

```sh
nix shell 'github:nix-purifiers/blender-purifier'
```

Add `blender-purifier.json` to your project:

```json
{
  "repositories": [
    {
      "id": "community",
      "url": "https://extensions.blender.org/api/v1/extensions/",
      "extensions": ["boltfactory"]
    }
  ]
}
```

```sh
blender-purifier lock --update
blender my-project.blend
```

Commit the selection and `blender-purifier.lock.json`. Blender's native resolver
selects compatible extension archives. Nix verifies and installs them using the
same Blender SDK. The wrapper activates the locked add-ons in a private profile;
extension code and bundled wheel code remain in the Nix store. Preferences and
other application state remain writable under `.blender-purifier/`.

Use `blender-purifier prefetch` to prepare the environment, or
`blender-purifier exec -- -b my-project.blend --python render.py` for an explicit
project command. The `blender` wrapper is required to activate the integration.
Without a lockfile it warns and runs ordinary Blender.

Run commands from the project or a descendant directory. To select another
project or lock location, set `BLENDER_PURIFIER_PROJECT` and
`BLENDER_PURIFIER_LOCK`, or pass `--project` and `--lock` before the adapter
subcommand. Native arguments and working directories are preserved.

Dependency preparation reads the selection and lock without copying the working
tree into Nix. Project files enter the store only for an explicit Nix build.

## Scope

The initial integration supports native add-on extensions from public HTTPS
repositories on Linux, using pinned Blender 5.2.2. It preserves Blender's native
manifest validation, platform and Python compatibility filtering, archive
installation and wheel installation. Bundled wheels must work with this Nix
Blender SDK; arbitrary vendor binary wheels may need additional Nix providers.
Legacy manually installed add-ons, themes, authenticated repositories and
extension-created external dependency managers are outside this initial scope.

Locked runs use native read-only system repositories. Change the selection and
run `lock --update` to change dependencies. Existing user extension caches and
preferences are kept separate. Application scripts retain ordinary network
access; the integration constrains extension management.

## Build and release

The optional `buildBlenderProject` Nix builder runs the project's `build.py` in
the sandbox. Write outputs to the directory in `BLENDER_PURIFIER_OUTPUT`, as in
`examples/minimal`. The builder exposes `packages.environment`,
`packages.project`, a checks derivation, a release directory and fetch metadata.

The example exports a mesh as OBJ. Native `.blend` saves contain process-specific
data and do not produce byte-identical files between builds. Select a suitable
export format when repeatable build artifacts matter.

`blender-purifier build` builds the project; `bundle` produces the
`blender-project.tar.gz`; `publish --tag TAG` uploads that exact archive to a
GitHub release.

## Credits

The purifier idea was inspired by nixcloud's
[cargo (libnix)](https://github.com/nixcloud/cargo).

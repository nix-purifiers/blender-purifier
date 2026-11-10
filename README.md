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

## Public output resources

Select generated project output files explicitly:

```nix
project = pkgs.blender-purifier.buildBlenderProject {
  src = ./.;
  resourceRoots."public/file" = "generated-file";
};
```

`project.projections.resources` exposes the selected file directory and its
catalog; `project.projections.web.documentRoot` is the HTTP serving root,
and `project.projections.java-resources.classPath` is the resource JAR.
The same projections are attached to `project.packages.project`.
`resourceDependencies` accepts additional typed resource views. Empty
`resourceRoots` preserves existing output behavior.

Paths are relative to the native project output. Selection copies actual
export bytes. Unselected siblings stay outside the exported tree, and proof
metadata stays outside HTTP and JAR payloads. A selected directory includes
its contents, so select only
public generated files or directories. Missing files, traversal, and resource
collisions fail.

Checks run two genuine native producer inputs, compare every selected byte
with native files, serve them over HTTP, and load the JAR through an isolated
Java class loader with exact origin and hash checks. They exclude a real
private sibling and reject a genuine changed producer's JAR against the
original byte contract. Native producers, resource views, and consumers are
rebuilt directly.

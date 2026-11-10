{
  lib,
  purifier,
  runCommand,
  python3,
  original,
  scripts,
  environment,
  readLock,
  gnutar,
  gzip,
}:
{
  src,
  lockFile ? src + "/blender-purifier.lock.json",
  script ? "build.py",
  fetchers ? { },
  doCheck ? false,
  checkCommand ? "",
  resourceRoots ? { },
  resourceDependencies ? [ ],
}:
let
  lock = readLock { inherit src lockFile; };
  profile = environment { inherit lock fetchers; };
  projectSource = lib.cleanSourceWith {
    inherit src;
    filter =
      path: type:
      !(builtins.elem (baseNameOf path) [
        ".git"
        ".blender-purifier"
        "__pycache__"
        "result"
      ]);
  };
  builtProject = runCommand "blender-project" { } ''
    export BLENDER_SYSTEM_RESOURCES=${scripts}
    export HOME="$TMPDIR/home" XDG_CACHE_HOME="$TMPDIR/cache" BLENDER_USER_RESOURCES="$TMPDIR/user"
    export BLENDER_PURIFIER_ENVIRONMENT=${profile} BLENDER_PURIFIER_OUTPUT="$out"
    mkdir -p "$HOME" "$out"
    cp -r ${projectSource} project
    chmod -R u+w project
    cd project
    ${original}/bin/blender -b --factory-startup --python-exit-code 1 \
      --python ${../native/startup.py} --python ${lib.escapeShellArg script}
    ${lib.optionalString doCheck checkCommand}
  '';
  projections = lib.optionalAttrs (resourceRoots != { }) (
    purifier.resourceProjections {
      producer = builtProject;
      roots = resourceRoots;
      dependencies = resourceDependencies;
      inherit runCommand python3;
    }
  );
  project = builtProject // {
    inherit projections;
  };
  release =
    runCommand "blender-project-release"
      {
        nativeBuildInputs = [
          gnutar
          gzip
        ];
      }
      ''
        mkdir -p "$out"
        tar --sort=name --mtime=@1 --owner=0 --group=0 --numeric-owner -cf - -C ${project} . | gzip -n > "$out/blender-project.tar.gz"
      '';
in
{
  packages = {
    default = project;
    inherit project;
    environment = profile;
  };
  tests = project;
  inherit release projections;
  fetches = lock.entries;
}

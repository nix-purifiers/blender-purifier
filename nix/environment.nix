{
  lib,
  runCommand,
  writeText,
  fetchurl,
  fetchgit,
  python3,
  original,
  scripts,
  purifier,
  sdk,
}:
{
  lock,
  fetchers ? { },
}:
let
  checked = purifier.checkLock lock;
  tree = purifier.tree (
    {
      name = "blender-locked-archives";
      entries = checked.entries;
      inherit
        runCommand
        writeText
        fetchurl
        fetchgit
        python3
        ;
    }
    // fetchers
  );
  lockData = writeText "blender-lock.json" (builtins.toJSON checked.data);
  installData = writeText "blender-native-install.json" (
    builtins.toJSON {
      repositories = map (r: r.id) checked.data.selection.repositories;
      entries = map (e: {
        inherit (e.blender) repository manifest;
        id = e.blender.manifest.id;
        file = "${tree}/${e.path}";
      }) checked.entries;
    }
  );
  repositories = runCommand "blender-native-extensions" { } ''
    export BLENDER_SYSTEM_RESOURCES=${scripts}
    export HOME="$TMPDIR/home" XDG_CACHE_HOME="$TMPDIR/cache" BLENDER_USER_RESOURCES="$TMPDIR/user"
    export BLENDER_PURIFIER_INSTALL=${installData}
    mkdir -p "$HOME" "$out"
    ${original}/bin/blender -b --factory-startup --python-exit-code 1 --python ${../native/install.py}
  '';
  wheels = runCommand "blender-native-wheel-environment" { } ''
    export BLENDER_SYSTEM_RESOURCES=${scripts}
    export HOME="$TMPDIR/home" XDG_CACHE_HOME="$TMPDIR/cache" BLENDER_USER_RESOURCES="$TMPDIR/user"
    export BLENDER_PURIFIER_PROFILE=${repositories} BLENDER_PURIFIER_LOCK_DATA=${lockData}
    mkdir -p "$HOME" "$out"
    ${original}/bin/blender -b --factory-startup --python-exit-code 1 --python ${../native/wheels.py}
  '';
in
assert lib.assertMsg (checked.data.sdk == sdk) "Blender SDK changed; update the purifier lock";
runCommand "blender-locked-environment" { passthru = { inherit repositories wheels tree; }; } ''
  mkdir -p "$out"
  ln -s ${repositories}/repositories "$out/repositories"
  ln -s ${wheels} "$out/wheels"
  ln -s ${lockData} "$out/lock.json"
''

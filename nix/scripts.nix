{
  runCommand,
  original,
  python3,
}:
runCommand "blender-purifier-native-scripts" { nativeBuildInputs = [ python3 ]; } ''
  resources=${original}/share/blender/5.2
  cp -rs "$resources" "$out"
  chmod u+w "$out" "$out/scripts" "$out/scripts/modules"
  rm "$out/scripts/modules/addon_utils.py"
  cp "$resources/scripts/modules/addon_utils.py" "$out/scripts/modules/addon_utils.py"
  chmod u+w "$out/scripts/modules/addon_utils.py"
  python ${../native/patch.py} "$out/scripts/modules/addon_utils.py"
  cp ${../native/early.py} "$out/scripts/modules/blender_purifier_bootstrap.py"
''

{ lib }:
{
  src,
  lockFile ? src + "/blender-purifier.lock.json",
}:
let
  raw = if builtins.pathExists lockFile then builtins.fromJSON (builtins.readFile lockFile) else { };
  data = if builtins.isAttrs raw then raw else { };
  entries = data.entries or [ ];
  component = s: builtins.isString s && builtins.match "[a-z][a-z0-9_]*" s != null;
  selection =
    if builtins.pathExists (src + "/blender-purifier.json") then
      builtins.fromJSON (builtins.readFile (src + "/blender-purifier.json"))
    else
      null;
  valid =
    (data.version or null) == 1
    && (data.purifier or null) == "blender"
    && builtins.isString (data.sdk or null)
    && builtins.isAttrs (data.selection or null)
    && builtins.isList (data.selection.repositories or null)
    && builtins.all (
      r:
      builtins.isAttrs r
      && component (r.id or null)
      && builtins.isString (r.url or null)
      && lib.hasPrefix "https://" r.url
      && builtins.isList (r.extensions or null)
      && builtins.all component r.extensions
      && builtins.length (lib.unique r.extensions) == builtins.length r.extensions
    ) data.selection.repositories
    &&
      builtins.length (lib.unique (map (r: r.id) data.selection.repositories))
      == builtins.length data.selection.repositories
    && data.selection == selection
    && builtins.isList entries
    && builtins.all (
      e:
      builtins.isAttrs e
      && builtins.isAttrs (e.blender or null)
      && component (e.blender.repository or null)
      && builtins.isAttrs (e.blender.manifest or null)
      && component (e.blender.manifest.id or null)
      && (e.blender.manifest.type or null) == "add-on"
      && (e.path or null) == "${e.blender.repository}/${e.blender.manifest.id}.zip"
      && builtins.isString (e.url or null)
      && lib.hasPrefix "https://" e.url
      && builtins.isString (e.hash or null)
      && builtins.match "sha256-[A-Za-z0-9+/]{43}=" e.hash != null
    ) entries
    && builtins.length (lib.unique (map (e: e.path) entries)) == builtins.length entries
    &&
      builtins.sort builtins.lessThan (map (e: e.path) entries) == builtins.sort builtins.lessThan (
        lib.concatMap (r: map (id: "${r.id}/${id}.zip") r.extensions) data.selection.repositories
      );
in
{
  purifier = "blender";
  inherit data entries;
  problems = lib.optional (
    !valid
  ) "Blender lock is missing, malformed, or stale; run blender-purifier lock --update";
  outputs = {
    packages = [
      "default"
      "environment"
      "project"
    ];
    tests = [ "default" ];
    release = [ "default" ];
  };
}

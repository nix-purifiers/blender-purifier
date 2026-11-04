import os
from pathlib import Path

import bpy

assert bpy.ops.mesh.bolt_add() == {"FINISHED"}
mesh = bpy.context.active_object.data
assert len(mesh.vertices) > 100
bpy.context.scene["answer"] = 42
out = Path(os.environ.get("BLENDER_PURIFIER_OUTPUT", "."))
bpy.ops.wm.obj_export(
    filepath=str((out / "bolt.obj").resolve()), export_selected_objects=True
)
(out / "answer.txt").write_text(f"answer={bpy.context.scene['answer']}\n")

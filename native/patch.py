import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text()
needle = "def _initialize_once():\n"
if text.count(needle) != 1:
    raise RuntimeError("Blender initialization hook changed")
text = text.replace(
    needle,
    needle
    + "    from blender_purifier_bootstrap import initialize\n    initialize(globals())\n",
)
path.write_text(text)

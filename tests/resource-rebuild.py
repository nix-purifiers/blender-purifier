"""Directly rebuild actual native exports, resource views, and consumers."""
import json
from pathlib import Path
import subprocess
repo=Path(__file__).resolve().parent.parent
system=subprocess.check_output(["nix","eval","--impure","--raw","--expr","builtins.currentSystem"],text=True).strip()
output=subprocess.check_output(["nix","build","--no-link","--print-out-paths",str(repo)+"#checks."+system+".resource-projections"],text=True).strip()
roots={output}
for version in json.loads((Path(output)/"origins.json").read_text()):
 for field in ("native","directory","web","jar"):roots.add("/".join(version[field].split("/")[:4]))
derivations=sorted({subprocess.check_output(["nix-store","-q","--deriver",root],text=True).strip() for root in roots})
assert len(derivations)==5 and all(d.endswith(".drv") for d in derivations),derivations
for derivation in derivations:
 print("Direct native export/resource/consumer rebuild",derivation,flush=True)
 subprocess.run(["nix","build","--no-link","--rebuild","-L",derivation+"^*"],check=True)
print("Five actual native export/resource/consumer rebuilds passed")

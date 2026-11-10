"""Read actual native exports through HTTP and isolated Java resources."""
import functools
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import zipfile
spec=json.loads(Path(sys.argv[1]).read_text());out=Path(sys.argv[2]);out.mkdir()
subprocess.run(["javac","Resources.java"],check=True)
observations=[]
for index,version in enumerate(spec["versions"]):
 catalog=json.loads(Path(version["catalog"]).read_text());expected={}
 assert sorted(catalog["files"])==sorted(spec["roots"])
 for name,source in sorted(spec["roots"].items()):
  native=Path(version["native"])/source;data=native.read_bytes();assert data
  digest=hashlib.sha256(data).hexdigest();assert catalog["files"][name]["sha256"]==digest
  assert (Path(version["directory"])/name).read_bytes()==data
  expected[name]=digest
  if name.endswith(".obj"):
   references=[line.split(maxsplit=1)[1] for line in data.decode().splitlines() if line.startswith("mtllib ")]
   assert references and all(reference in spec["roots"] for reference in references),references
 class Quiet(SimpleHTTPRequestHandler):
  def log_message(self,*_):pass
 server=ThreadingHTTPServer(("127.0.0.1",0),functools.partial(Quiet,directory=version["web"]))
 thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 try:
  base="http://127.0.0.1:"+str(server.server_port)
  for name,digest in expected.items():
   with urllib.request.urlopen(base+"/"+urllib.parse.quote(name),timeout=10) as response:data=response.read()
   assert hashlib.sha256(data).hexdigest()==digest
  for hidden in ("private.txt","catalog.json","nix-support/inputs"):
   try:urllib.request.urlopen(base+"/"+hidden,timeout=10)
   except urllib.error.HTTPError as error:assert error.code==404
   else:raise AssertionError("private/proof metadata served: "+hidden)
 finally:server.shutdown();thread.join();server.server_close()
 with zipfile.ZipFile(version["jar"]) as jar:
  assert {n for n in jar.namelist() if not n.endswith("/")}==set(expected)
  for name,digest in expected.items():assert hashlib.sha256(jar.read(name)).hexdigest()==digest
 listing=out/(str(index)+"-resources.tsv");listing.write_text("".join(n+"\t"+d+"\n" for n,d in sorted(expected.items())))
 result=subprocess.run(["java","Resources",version["jar"],listing],capture_output=True,text=True)
 assert result.returncode==0 and not result.stderr,result
 (out/(str(index)+"-java.stdout")).write_text(result.stdout)
 assert (Path(version["native"])/"private.txt").is_file()
 observations.append(dict(native=version["native"],directory=version["directory"],web=version["web"],jar=version["jar"],hashes=expected))
assert observations[0]["hashes"] != observations[1]["hashes"],"genuine native input change did not change selected output"
# The real second producer's resource JAR must fail the first native digest list.
result=subprocess.run(["java","Resources",spec["versions"][1]["jar"],out/"0-resources.tsv"],capture_output=True,text=True)
assert result.returncode and "AssertionError: bytes" in result.stderr,result
(out/"genuine-replacement.stderr").write_text(result.stderr)
(out/"origins.json").write_text(json.dumps(observations,sort_keys=True,indent=2)+"\n")
print("Both genuine native exports consumed through HTTP and isolated Java resource origins")

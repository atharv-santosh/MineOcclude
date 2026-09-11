"""CPU reconstruction of all preserved cohorts and the evidence extension."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

def main():
    root=Path(__file__).resolve().parent
    inventory=json.loads((root/'COMPLETE_SNAPSHOT_SHA256.json').read_text())
    def verify():
        for name,digest in inventory.items():
            path=(root/name).resolve()
            assert path.is_relative_to(root)
            assert hashlib.sha256(path.read_bytes()).hexdigest()==digest,name
    verify()
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
    for script in ['reproduce_all.py','extension/reproduce.py']:
        subprocess.run([sys.executable,str(root/script)],cwd=root,env=env,check=True)
    verify()
    print('ALL_PRESERVED_STUDIES_AND_EVIDENCE_EXTENSION_REPRODUCED_WITHOUT_GPU',flush=True)

if __name__=='__main__':main()

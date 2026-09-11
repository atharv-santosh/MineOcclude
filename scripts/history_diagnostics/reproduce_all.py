"""Reconstruct all three preserved studies from the reviewer snapshot."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def main():
    root=Path(__file__).resolve().parent
    for name,h in json.loads((root/'SNAPSHOT_SHA256.json').read_text()).items():
        path=(root/name).resolve()
        assert path.is_relative_to(root)
        assert hashlib.sha256(path.read_bytes()).hexdigest()==h,('Input changed',name)
    commands=[('central','scripts/rgb_replication/reproduce.py'),('fresh','reproduce.py'),('diagnostic','reproduce.py')]
    for directory,script in commands:
        print('REBUILD',directory,flush=True)
        subprocess.run([sys.executable,str(root/directory/script)],cwd=root/directory,check=True)
    print('ALL_THREE_STUDIES_REPRODUCED_WITHOUT_GPU',flush=True)


if __name__=='__main__':
    main()

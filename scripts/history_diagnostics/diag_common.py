from pathlib import Path
import hashlib
import json
import sys

SOURCE=Path(__file__).resolve().parents[2]
ROOT=Path('/home/bpcfno/mineocclude-history-diagnostic-20260911')
PREVIOUS=Path('/home/bpcfno/mineocclude-generalization-20260911')
sys.path.insert(0,str(SOURCE/'src'))
sys.path.append(str(SOURCE/'scripts/generalization'))
sys.path.append(str(SOURCE/'scripts/rgb_replication'))

def read(p):
    return json.loads(Path(p).read_text())

def save(p,v):
    p=Path(p)
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,indent=2,allow_nan=False,default=str)+'\n')

def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):
            h.update(b)
    return h.hexdigest()

def seal(v):
    return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def lines(p):
    return [json.loads(s) for s in Path(p).read_text().splitlines()]

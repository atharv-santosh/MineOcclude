import os
os.environ.setdefault('OPENBLAS_NUM_THREADS', '3')
os.environ.setdefault('OMP_NUM_THREADS', '3')
from pathlib import Path
import hashlib
import json
import sys

SOURCE = Path(__file__).resolve().parents[2]
ROOT = Path('/home/bpcfno/mineocclude-evidence-extension-20260911')
OLD = Path('/home/bpcfno/mineocclude-history-diagnostic-20260911')
MOTION_ROSTER = ROOT/'motion_production_v4.json'
MOTION_ADMISSION = ROOT/'MOTION_ADMISSION_V4.json'
sys.path.insert(0, str(SOURCE/'src'))
sys.path.append(str(SOURCE/'scripts/history_diagnostics'))
sys.path.append(str(SOURCE/'scripts/generalization'))
sys.path.append(str(SOURCE/'scripts/rgb_replication'))

def read(p):
    return json.loads(Path(p).read_text())

def save(p, value):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    assert not p.exists(), f'Preserve existing artifact: {p}'
    tmp = p.with_suffix(p.suffix+'.tmp')
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False, default=str)+'\n')
    tmp.replace(p)

def sha(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(8*1024*1024), b''):
            h.update(b)
    return h.hexdigest()

def seal(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

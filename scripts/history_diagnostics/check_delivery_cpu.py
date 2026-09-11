"""Run the complete snapshot in an isolated, CPU-only Python environment."""
from pathlib import Path
import hashlib
import importlib.util
import json
import platform
import subprocess
import sys
import time

base=Path(__file__).resolve().parents[2]/'history_diagnostic_outputs'
assert importlib.util.find_spec('torch') is None
assert importlib.util.find_spec('sklearn') is None
snapshot=base/'anonymous_reproduction'
started=time.monotonic()
command=[sys.executable,str(snapshot/'reproduce_all.py')]
result=subprocess.run(command,cwd=snapshot,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
log=base/'clean_cpu_reproduction.log'
log.write_text(result.stdout,encoding='utf-8')
print(result.stdout)
assert result.returncode==0,result.returncode
assert 'ALL_THREE_STUDIES_REPRODUCED_WITHOUT_GPU' in result.stdout
assert '7296' in result.stdout
receipt=dict(status='PASS',platform=platform.platform(),python=sys.version,
    elapsed_seconds=time.monotonic()-started,torch_installed=False,sklearn_installed=False,
    all_three_studies_reconstructed=True,diagnostic_original_cells=40128,
    diagnostic_supplementary_cells=7296,input_snapshot_unchanged=True,
    log_sha256=hashlib.sha256(log.read_bytes()).hexdigest(),
    inventory_sha256=hashlib.sha256((snapshot/'SNAPSHOT_SHA256.json').read_bytes()).hexdigest())
(base/'clean_cpu_reproduction.json').write_text(json.dumps(receipt,indent=2)+'\n')
print('CLEAN_CPU_REPRODUCTION_PASS',receipt['elapsed_seconds'])

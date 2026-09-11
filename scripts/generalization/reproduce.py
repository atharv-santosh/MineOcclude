"""Verify a compact snapshot and reconstruct primary/transfer statistics."""
import hashlib
import json
from pathlib import Path
import sys
from rebuild_statistics import rebuild as primary
from summarize_transfer import rebuild as transfer


def main():
    root=Path(__file__).resolve().parent
    manifest=json.loads((root/'FILES_SHA256.json').read_text())
    for name,expected in manifest.items():
        path=(root/name).resolve()
        assert path.is_relative_to(root)
        actual=hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual==expected,('Changed snapshot file',name)
    checks=[]
    for name,function in [('primary',primary),('transfer',transfer)]:
        actual=function(root/name/'predictions')
        expected=json.loads((root/name/'statistics.json').read_text())
        assert actual==expected,('Statistics differ',name)
        checks.append(dict(analysis=name,cells=actual['cells'],statistics_identical=True))
    print(json.dumps(dict(status='PASS',gpu_required=False,python=sys.version,files_verified=len(manifest),checks=checks),indent=2))


if __name__=='__main__':
    main()

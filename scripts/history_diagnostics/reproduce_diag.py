"""Verify this portable snapshot and exactly reconstruct its statistics."""
import hashlib
import json
from pathlib import Path
from statistics_diag import rebuild


def main():
    root=Path(__file__).resolve().parent
    inventory=json.loads((root/'FILES_SHA256.json').read_text())
    for name,h in inventory.items():
        path=(root/name).resolve()
        assert path.is_relative_to(root)
        assert hashlib.sha256(path.read_bytes()).hexdigest()==h,('Input changed',name)
    rows=json.loads((root/'configuration/roster.json').read_text())['identities']
    by={r['identity']:r for r in rows}
    assert len(by)==96
    for path in (root/'predictions').glob('*.json'):
        for cell in json.loads(path.read_text())['cells']:
            r=by[cell['identity']]
            assert r['partition']=='test'
            assert cell['target']==r['historical_FIR_reference_labels'][cell['age']-1]
            assert cell['donor']==r['donor']
    actual=rebuild(root/'predictions')
    expected=json.loads((root/'statistics.json').read_text())
    assert actual==expected,'Numerical reconstruction differs'
    print(json.dumps(dict(status='PASS',files_verified=len(inventory),prediction_cells=actual['cells'],test_identities=48,statistics_exactly_equal=True,gpu_required=False),indent=2))


if __name__=='__main__':
    main()

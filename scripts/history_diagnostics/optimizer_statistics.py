"""CPU-only reconstruction of the separately labeled optimizer-budget check."""
from collections import defaultdict
import json
from pathlib import Path
import sys
import numpy as np
from statistics_diag import BINS,scores,interval


def rebuild(folder,original_folder):
    files=sorted(Path(folder).glob('*.json')); assert len(files)==8
    cells=[r for p in files for r in json.loads(p.read_text())['cells']]
    assert len(cells)==7296
    original=[r for p in sorted(Path(original_folder).glob('*.json')) for r in json.loads(p.read_text())['cells'] if r['setting']=='native']
    groups=defaultdict(list)
    keys=set()
    for r in cells:
        key=(r['model'],r['condition'],r['phase'],r['identity'],r['age'])
        assert key not in keys and r['partition']=='test'
        keys.add(key)
    for r in cells+original:
        groups[r['model'],r['condition'],r['phase'],r['layout']].append(r)
        groups[r['model'],r['condition'],r['phase'],'pooled'].append(r)
    summary=[]; contrasts=[]
    for key,part in sorted(groups.items()):
        if not key[0].endswith('_OPT10K'): continue
        for label,ages in BINS.items():
            a=scores(part,ages)
            record=dict(model=key[0],condition=key[1],phase=key[2],layout=key[3],ages=label,identities=len(a))
            for metric in ['rmse','mae','r2']: record[metric]=interval([v[metric] for v in a.values()])
            summary.append(record)
            base=key[0].removesuffix('_OPT10K')
            for comparator in [base,base.removesuffix('_MLP')]:
                b=scores(groups[(comparator,)+key[1:]],ages)
                assert a.keys()==b.keys()
                paired=None if key[2]=='correct' else ['|'.join(sorted([i,a[i]['donor']])) for i in a]
                contrasts.append(dict(first=key[0],second=comparator,condition=key[1],phase=key[2],layout=key[3],ages=label,rmse_difference=interval([a[i]['rmse']-b[i]['rmse'] for i in a],paired)))
    # Every supplementary target must join the original target exactly.
    truth={(r['identity'],r['age']):r['target'] for r in original}
    assert all(r['target']==truth[r['identity'],r['age']] for r in cells)
    return dict(status='SUPPLEMENTARY_OPTIMIZER_CHECK_REBUILT',cells=7296,summaries=summary,contrasts=contrasts,interpretation='Training-diagnostic-triggered budget extension; original prospective results are unchanged and retained.')


if __name__=='__main__':
    result=rebuild(Path(sys.argv[1]),Path(sys.argv[2]))
    Path(sys.argv[3]).write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print('OPTIMIZER_STATISTICS_REBUILT',result['cells'],flush=True)

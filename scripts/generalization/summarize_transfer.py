"""CPU summary of unchanged-probe transfer, separate from refitted probes."""
import argparse
import json
from pathlib import Path
import numpy as np
from rebuild_statistics import identity_metrics, interval, digest


def rebuild(directory):
    paths=sorted(Path(directory).glob('*.json'))
    cells=[]
    for path in paths:
        record=json.loads(path.read_text())
        assert not set(record['source_identities'])&set(record['destination_identities'])
        assert len(record['source_identities'])==25 and len(record['destination_identities'])==50
        cells.extend(record['cells'])
    assert len(cells)==50*2*3*19,len(cells)
    grouped={}
    keys=set()
    for c in cells:
        k=(c['cohort'],c['condition_id'],c['model'],c['identity'])
        assert k+(c['row_index'],) not in keys
        keys.add(k+(c['row_index'],))
        grouped.setdefault(k,[]).append(c)
    metrics={}
    for k,rows in grouped.items():
        rows.sort(key=lambda r:r['row_index'])
        assert [r['row_index'] for r in rows]==list(range(19))
        metrics[k]=identity_metrics([r['target'] for r in rows],[r['prediction'] for r in rows])
    summaries=[]
    comparisons=[]
    for cohort in ['geometry','speed']:
        names=sorted({k[3] for k in metrics if k[0]==cohort})
        assert len(names)==25
        index=np.random.default_rng(20260911).integers(0,25,(10000,25))
        for condition in ['L0','L4']:
            for model in ['MW_RGB_L19','PIXEL_CURRENT','PIXEL_HISTORY16']:
                summaries.append(dict(cohort=cohort,condition=condition,model=model,
                    **{m:interval([metrics[cohort,condition,model,i][m] for i in names],index) for m in ['rmse','mae','r2']}))
            values=[metrics[cohort,condition,'MW_RGB_L19',i]['rmse']-metrics[cohort,condition,'PIXEL_HISTORY16',i]['rmse'] for i in names]
            comparisons.append(dict(cohort=cohort,condition=condition,contrast='MW-minus-history',**interval(values,index)))
    return dict(cells=len(cells),source_identities=25,destination_identities=50,
        input_sha256={p.name:digest(p) for p in paths},summaries=summaries,paired_contrasts=comparisons,
        bootstrap='10000 identity resamples, seed 20260911, conditional on source fit, not simultaneous',
        per_identity=[dict(cohort=k[0],condition=k[1],model=k[2],identity=k[3],**v) for k,v in sorted(metrics.items())])


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    args.output.write_text(json.dumps(rebuild(args.input),indent=2,allow_nan=False)+'\n')
    print('TRANSFER_STATISTICS_REBUILT')

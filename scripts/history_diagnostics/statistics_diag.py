"""Portable prediction-to-statistics rebuild. No training or private paths."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import numpy as np

BINS={'1-10':(1,10),'11-15':(11,15),'16-19':(16,19),'1-19':(1,19)}
SEED=930119
DRAWS=10000


def interval(values,groups=None):
    values=np.asarray(values,float)
    assert np.isfinite(values).all() and len(values)>1
    rng=np.random.default_rng(SEED)
    if groups is None:
        indices=rng.integers(0,len(values),size=(DRAWS,len(values)))
        draws=values[indices].mean(axis=1)
    else:
        unique=sorted(set(groups))
        arrays=[values[np.array(groups)==g] for g in unique]
        assert len({len(a) for a in arrays})==1
        grouped=np.array([a.mean() for a in arrays])
        indices=rng.integers(0,len(grouped),size=(DRAWS,len(grouped)))
        draws=grouped[indices].mean(axis=1)
    return dict(mean=float(values.mean()),ci95=np.quantile(draws,[.025,.975]).tolist())


def scores(cells,ages):
    by=defaultdict(list)
    for r in cells:
        if ages[0]<=r['age']<=ages[1]:
            by[r['identity']].append(r)
    result={}
    for i,rows in sorted(by.items()):
        rows=sorted(rows,key=lambda r:r['age'])
        y=np.array([r['target'] for r in rows]); p=np.array([r['prediction'] for r in rows])
        error=p-y
        den=float(np.sum((y-y.mean())**2))
        assert den>0
        result[i]=dict(rmse=float(np.sqrt(np.mean(error**2))),mae=float(np.mean(abs(error))),r2=float(1-np.sum(error**2)/den),donor=rows[0]['donor'])
    return result


def rebuild(folder):
    files=sorted(Path(folder).glob('*.json'))
    assert len(files)==30,('Expected all frozen fits and baselines',len(files))
    cells=[]
    coverage=[]
    for path in files:
        record=json.loads(path.read_text())
        cells.extend(record['cells'])
        coverage.extend(record.get('tracker_coverage',[]))
    assert len(cells)==40128,len(cells)
    unique=set()
    truth={}
    grouped=defaultdict(list)
    for r in cells:
        key=(r['model'],r['setting'],r['condition'],r['phase'],r['identity'],r['age'])
        assert key not in unique,key
        unique.add(key)
        assert r['partition']=='test' and np.isfinite(r['prediction']) and np.isfinite(r['target'])
        assert '_test_' in r['identity'] and r['identity']!=r['donor']
        pair=(r['identity'],r['age'])
        if pair in truth:
            assert truth[pair]==r['target']
        truth[pair]=r['target']
        grouped[r['model'],r['setting'],r['condition'],r['phase'],r['layout']].append(r)
        if r['setting']=='native':
            grouped[r['model'],r['setting'],r['condition'],r['phase'],'pooled'].append(r)
    assert len(truth)==48*19
    summary=[]; identity_scores={}
    for key,rows in sorted(grouped.items()):
        for label,ages in BINS.items():
            s=scores(rows,ages)
            assert len(s)==(48 if key[-1]=='pooled' else 24)
            identity_scores[key+(label,)]=s
            record=dict(model=key[0],setting=key[1],condition=key[2],phase=key[3],layout=key[4],ages=label,identities=len(s))
            for m in ['rmse','mae','r2']:
                record[m]=interval([v[m] for v in s.values()])
            summary.append(record)
    contrasts=[]
    pairs=[('MW_700M','PIXEL_HISTORY16'),('MW_300M','PIXEL_HISTORY16'),('MW_700M','DIRECTION_AGE'),('MW_300M','DIRECTION_AGE'),('MW_700M','IMAGE_TRACKER_CV'),('MW_300M','IMAGE_TRACKER_CV'),('MW_700M_MLP','MW_700M'),('MW_300M_MLP','MW_300M'),('MW_700M','MW_300M')]
    for layout in ['layout_01','layout_04','pooled']:
        for c in ['L0','L4']:
            for label in BINS:
                for first,second in pairs:
                    a=identity_scores[first,'native',c,'correct',layout,label]
                    b=identity_scores[second,'native',c,'correct',layout,label]
                    assert a.keys()==b.keys()
                    contrasts.append(dict(first=first,second=second,layout=layout,condition=c,ages=label,rmse_difference=interval([a[i]['rmse']-b[i]['rmse'] for i in a])))
    interventions=[]; responses=[]
    intervention_models=['MW_700M','MW_300M','MW_700M_MLP','MW_300M_MLP','PIXEL_CURRENT','PIXEL_HISTORY16','IMAGE_TRACKER_CV']
    for model in intervention_models:
        for layout in ['layout_01','layout_04','pooled']:
            original={(r['identity'],r['age']):r for r in grouped[model,'native','L4','correct',layout]}
            for label,ages in BINS.items():
                a=identity_scores[model,'native','L4','correct',layout,label]
                for phase in ['swapped','removed']:
                    b=identity_scores[model,'native','L4',phase,layout,label]
                    groups=['|'.join(sorted([i,a[i]['donor']])) for i in a]
                    interventions.append(dict(model=model,layout=layout,ages=label,phase=phase,contrast='intervened_minus_correct',rmse_difference=interval([b[i]['rmse']-a[i]['rmse'] for i in a],groups),resampling_unit='reciprocal donor pair'))
                response_by=defaultdict(list)
                for r in grouped[model,'native','L4','swapped',layout]:
                    if not ages[0]<=r['age']<=ages[1]:
                        continue
                    original_r=original[r['identity'],r['age']]
                    donor=original[r['donor'],r['age']]
                    true_delta=donor['target']-r['target']
                    pred_delta=r['prediction']-original_r['prediction']
                    assert true_delta!=0
                    response_by[r['identity']].append([abs(pred_delta),float(pred_delta*true_delta>0),abs(r['prediction']-donor['target']),abs(r['prediction']-r['target']),true_delta,pred_delta])
                ids=sorted(response_by)
                matrix=np.array([np.mean(response_by[i],axis=0) for i in ids])
                groups=['|'.join(sorted([i,a[i]['donor']])) for i in ids]
                responses.append(dict(model=model,layout=layout,ages=label,absolute_prediction_shift=interval(matrix[:,0],groups),donor_direction_agreement=interval(matrix[:,1],groups),swapped_donor_mae=interval(matrix[:,2],groups),swapped_recipient_mae=interval(matrix[:,3],groups)))
    tracker=[]
    for c in ['L0','L4']:
        for phase in (['correct'] if c=='L0' else ['correct','swapped','removed']):
            for label,(lo,hi) in BINS.items():
                rows=[r for r in coverage if r['condition']==c and r['phase']==phase and lo<=r['age']<=hi]
                tracker.append(dict(condition=c,phase=phase,ages=label,rows=len(rows),fallback_fraction=float(np.mean([r['fallback'] for r in rows])),mean_reliable_detections=float(np.mean([r['reliable_detections'] for r in rows]))))
    return dict(status='ALL_FROZEN_ANALYSES_REBUILT',cells=len(cells),test_identities=48,training_identities=48,bootstrap_draws=DRAWS,bootstrap_seed=SEED,summaries=summary,paired_contrasts=contrasts,interventions=interventions,history_responses=responses,tracker_coverage=tracker,interval_scope='Conditional on fitted models; paired whole-identity or reciprocal-donor-pair resampling, not simultaneous bounds')


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('predictions',type=Path); parser.add_argument('output',type=Path); args=parser.parse_args()
    result=rebuild(args.predictions)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print('STATISTICS_REBUILT',result['cells'],len(result['summaries']))


if __name__=='__main__':
    main()

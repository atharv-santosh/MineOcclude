"""CPU-only reconstruction of follow-up tables and paired uncertainty."""
import argparse
from collections import defaultdict
import numpy as np
from audit_recovery import ROOT,PKG,OUT,read,save,sha


def summarize(prediction_dir,output):
    cells=[]
    file_hashes={}
    for path in sorted(prediction_dir.glob('*.json')):
        item=read(path)
        if 'cells' in item:
            cells.extend(item['cells'])
            file_hashes[path.name]=sha(path)
    legacy=read(PKG/'prediction_lock/PREDICTION_LOCK.json')['cells']
    cells.extend([{**r,'model':'LEGACY_'+r['model']} for r in legacy])
    groups=defaultdict(list)
    seen=set()
    expected={(r['identity'],r['condition_id'],r['row_index']):r for r in read(PKG/'cohort/EXECUTED_TARGETS.json')['rows']}
    for r in cells:
        key=r['model'],r['condition_id'],r['identity'],r['row_index']
        assert key not in seen,key
        seen.add(key)
        target=expected[r['identity'],r['condition_id'],r['row_index']]
        assert r['target']==target['target'],('Target mismatch',key)
        if not r['model'].startswith('LEGACY_'):
            assert r['outer_fold']==target['outer_fold'],('Fold mismatch',key)
        groups[key[:3]].append(r)
    models=defaultdict(dict)
    for (model,cond,identity),rows in groups.items():
        rows=sorted(rows,key=lambda r:r['row_index'])
        assert [r['row_index'] for r in rows]==list(range(19))
        y=np.array([r['target'] for r in rows])
        p=np.array([r['prediction'] for r in rows])
        assert np.isfinite(p).all()
        error=p-y
        metrics={'rmse':float(np.sqrt(np.mean(error**2))),'mae':float(np.mean(abs(error))),'r2':float(1-np.sum(error**2)/np.sum((y-y.mean())**2))}
        metrics['age_rmse']={f'{lo}-{hi}':float(np.sqrt(np.mean(error[lo-1:hi]**2))) for lo,hi in ((1,5),(6,10),(11,15),(16,19),(12,15))}
        models[model].setdefault(cond,{})[identity]=metrics
    rng=np.random.default_rng(20260911)
    draws=rng.integers(0,25,size=(10000,25))
    def interval(values):
        assert len(values)==25
        values=np.array(values,dtype=np.float64)
        means=values[draws].mean(axis=1)
        return {'mean':float(values.mean()),'ci_low':float(np.percentile(means,2.5)),'ci_high':float(np.percentile(means,97.5))}
    summaries={}
    for model,conditions in models.items():
        summaries[model]={}
        for cond,ids in conditions.items():
            assert len(ids)==25
            names=sorted(ids)
            summaries[model][cond]={metric:interval([ids[i][metric] for i in names]) for metric in ('rmse','mae','r2')}
            summaries[model][cond]['rmse_range']=[min(ids[i]['rmse'] for i in names),max(ids[i]['rmse'] for i in names)]
            summaries[model][cond]['age_rmse']={age:interval([ids[i]['age_rmse'][age] for i in names]) for age in ('1-5','6-10','11-15','16-19','12-15')}
    comparisons={}
    if 'MW_RGB_L19' in models:
        for comparator in ('MW_BGR_L19','PIXEL_CURRENT','PIXEL_HISTORY16','LEGACY_MW_CURRENT','LEGACY_TIME_ONLY','LEGACY_LAST_SEEN','LEGACY_CONSTANT_VELOCITY','MW_RGB_L19_CTX1','MW_RGB_L19_CTX8'):
            if comparator not in models:
                continue
            comparisons[comparator]={}
            for cond in sorted(set(models['MW_RGB_L19'])&set(models[comparator])):
                names=sorted(models[comparator][cond])
                comparisons[comparator][cond]=interval([models['MW_RGB_L19'][cond][i]['rmse']-models[comparator][cond][i]['rmse'] for i in names])
    effects={}
    O=read(PKG/'results/primary_results.json')['O_c']
    def primary_estimands(rmse,coordinates):
        # Standalone copies of the three original estimands for a small CPU bundle.
        x=np.array([coordinates[f'L{k}'] for k in range(5)])
        y=np.array([rmse[f'L{k}'] for k in range(5)])
        centered=x-x.mean()
        return {'S_i':float(np.sum(centered*(y-y.mean()))/np.sum(centered**2)),
                'Dpartial_i':float(np.mean(y[1:4])-y[0]),'Dopaque_i':float(y[4]-y[3])}
    for model,conditions in models.items():
        if set(conditions)!=set(O):
            continue
        names=sorted(conditions['L0'])
        per_id={i:primary_estimands({c:conditions[c][i]['rmse'] for c in O},O) for i in names}
        effects[model]={e:interval([per_id[i][e] for i in names]) for e in ('S_i','Dpartial_i','Dopaque_i')}
    package={'schema':'mineocclude-rgb-history-summary-v1','bootstrap_seed':20260911,'replicates':10000,'resampling_unit':'whole identity; paired across conditions and predictors','interval_scope':'conditional on fitted probes','comparison_sign':'corrected RGB RMSE minus comparator RMSE; negative favors corrected RGB','prediction_files':file_hashes,'legacy_prediction_sha256':sha(PKG/'prediction_lock/PREDICTION_LOCK.json'),'cells':len(cells),'summary':summaries,'paired_differences':comparisons,'ladder_effects_descriptive':effects,'per_identity':models}
    save(output,package)
    for model in sorted(summaries):
        print(model,{c:round(v['rmse']['mean'],6) for c,v in summaries[model].items()},flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--predictions',type=__import__('pathlib').Path,default=OUT/'predictions')
    parser.add_argument('--output',type=__import__('pathlib').Path,default=OUT/'summary.json')
    args=parser.parse_args()
    summarize(args.predictions,args.output)

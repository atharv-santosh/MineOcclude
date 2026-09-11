"""Independent joins, saved-fit replay, source locks, and arithmetic audit."""
from diag_common import *
from collections import defaultdict
import math
import numpy as np
from fit_diag import predict_frozen,feature

OUT=ROOT/'analysis'


def main():
    freeze=read(ROOT/'analysis_freeze.json')
    for name,h in freeze['files'].items():
        assert sha(Path(__file__).parent/name)==h,('Frozen source changed',name)
    amendment=read(ROOT/'statistical_source_amendment.json')
    assert amendment['original_freeze_sha256']==sha(ROOT/'statistical_source_freeze.json')
    for name,h in amendment['current_files'].items():
        assert sha(Path(__file__).parent/name)==h,('Statistical source changed after correction',name)
    manifest=read(ROOT/'manifest.json')
    assert manifest['status']=='ALL_192_VERIFIED'
    assert len({json.dumps(v['action_payload'],sort_keys=True) for v in manifest['units'].values()})==1
    rows={r['identity']:r for r in read(ROOT/'roster.json')['identities']}
    cells=[]; replay_errors=[]
    for path in sorted((OUT/'predictions').glob('*.json')):
        record=read(path)
        cells.extend(record['cells'])
        for cell in record['cells']:
            r=rows[cell['identity']]
            assert r['partition']=='test' and r['donor']==cell['donor']
            info=manifest['units'][cell['identity']+'__'+cell['condition']]
            assert cell['target']==info['targets'][cell['age']-1]
        if 'selection_sha256' not in record:
            continue
        fitpath=OUT/'fits'/path.with_suffix('.npz').name
        selectionpath=OUT/'fits'/path.name
        sel=read(selectionpath)
        assert sha(fitpath)==record['fit_sha256']==sel['fit_sha256']
        assert sha(selectionpath)==record['selection_sha256']
        assert sel['alpha']==sel['candidates'][int(np.argmin(sel['mean_validation_rmse']))]
        assert all(rows[i]['partition']=='train' and rows[i]['layout_id']==sel['layout'] for i in sel['training_identities'])
        assert len(sel['training_identities'])==24
        model=sel['model']; feature_model=model.removesuffix('_MLP')
        for i,h in sel['training_feature_sha256'].items():
            assert sha(feature(feature_model,'correct',i,sel['condition']))==h
        for phase in sorted({r['phase'] for r in record['cells']}):
            part=[r for r in record['cells'] if r['phase']==phase]
            names=list(dict.fromkeys(r['identity'] for r in part))
            assert len(names)==24 and not set(names)&set(sel['training_identities'])
            q=np.concatenate([np.load(feature(feature_model,phase,i,sel['condition']),allow_pickle=False) for i in names])
            predicted=predict_frozen(fitpath,q)
            expected=np.array([r['prediction'] for r in part])
            delta=float(np.max(abs(predicted-expected)))
            assert delta<1e-8,(path.name,phase,delta)
            replay_errors.append(delta)
    assert len(cells)==40128
    grouped=defaultdict(list)
    for r in cells:
        grouped[r['model'],r['setting'],r['condition'],r['phase'],r['layout'],r['identity']].append(r)
        if r['setting']=='native':
            grouped[r['model'],r['setting'],r['condition'],r['phase'],'pooled',r['identity']].append(r)
    statistics=read(OUT/'statistics.json')
    errors=[]
    independent={}
    for row in statistics['summaries']:
        lower,upper=map(int,row['ages'].split('-'))
        values=[]
        for key,series in grouped.items():
            if key[:5]!=(row['model'],row['setting'],row['condition'],row['phase'],row['layout']):
                continue
            selected=sorted((r for r in series if lower<=r['age']<=upper),key=lambda r:r['age'])
            y=[r['target'] for r in selected]; error=[r['prediction']-r['target'] for r in selected]
            mean=math.fsum(y)/len(y)
            value=dict(rmse=math.sqrt(math.fsum(v*v for v in error)/len(error)),mae=math.fsum(map(abs,error))/len(error),r2=1-math.fsum(v*v for v in error)/math.fsum((v-mean)**2 for v in y))
            values.append(value)
            independent[key+(row['ages'],)]=value
        assert len(values)==row['identities']
        for m in ['rmse','mae','r2']:
            errors.append(abs(math.fsum(v[m] for v in values)/len(values)-row[m]['mean']))
    assert max(errors)<1e-9,max(errors)
    bootstrap_errors=[]
    for row in statistics['interventions']:
        if row['ages']!='1-10' or row['layout']!='pooled':
            continue
        names=sorted({r['identity'] for r in cells if r['model']==row['model'] and r['setting']=='native'})
        pairs=sorted({tuple(sorted([i,rows[i]['donor']])) for i in names})
        assert len(pairs)==24
        differences=[]
        for pair in pairs:
            v=[]
            for i in pair:
                a=independent[row['model'],'native','L4','correct','pooled',i,'1-10']['rmse']
                b=independent[row['model'],'native','L4',row['phase'],'pooled',i,'1-10']['rmse']
                v.append(b-a)
            differences.append(math.fsum(v)/2)
        draws=np.random.default_rng(930119).integers(0,24,(10000,24))
        means=[math.fsum(differences[int(j)] for j in draw)/24 for draw in draws]
        quantiles=np.quantile(means,[.025,.975])
        bootstrap_errors.extend(abs(quantiles-np.array(row['rmse_difference']['ci95'])))
    assert max(bootstrap_errors)<1e-9,max(bootstrap_errors)
    receipt_count=0
    for path in (OUT/'feature_receipts').glob('*.json'):
        r=read(path)
        for model,h in r['features'].items():
            assert sha(OUT/'features'/model/r['phase']/f"{r['unit']}.npy")==h
        if r['phase']=='swapped':
            for evidence in r['evidence']:
                assert evidence['recipient_nonfull_frames']==max(16-evidence['age'],0)
                assert evidence['donor_nonfull_frames']==max(16-evidence['age'],0)
        receipt_count+=1
    assert receipt_count==864,receipt_count
    result=dict(status='PASS',prediction_cells=len(cells),feature_receipts=receipt_count,source_freeze='Unchanged',train_test_and_target_joins='PASS',saved_fit_replay_max_error=max(replay_errors),independent_summary_max_error=max(errors),independent_donor_pair_interval_max_error=float(max(bootstrap_errors)),all_action_tokens_constant=True)
    save(OUT/'independent_validation.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()

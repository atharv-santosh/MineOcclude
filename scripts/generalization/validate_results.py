"""Independently verify prediction/manifest joins and reported aggregate values."""
from collections import defaultdict
import math
import numpy as np
from prepare import ROOT,SOURCE,read,save,sha


def main():
    freeze=read(ROOT/'ANALYSIS_FREEZE.json')
    for name,expected in freeze['files'].items():
        assert sha(SOURCE/'scripts/generalization'/name)==expected,('Frozen analysis source changed',name)
    manifest=read(ROOT/'manifest.json')
    statistics=read(ROOT/'analysis/statistics.json')
    transferred=read(ROOT/'analysis/transfer_statistics.json')
    errors=[]
    groups=defaultdict(list)
    counts={}
    for mode in ['predictions','transfer']:
        all_keys=set()
        for path in sorted((ROOT/'analysis'/mode).glob('*.json')):
            payload=read(path)
            assert payload['manifest_sha256']==sha(ROOT/'manifest.json')
            if mode=='predictions' and 'selections' in payload:
                for selection in payload['selections']:
                    fold=selection['fold']
                    assert not set(selection['training_identities'])&set(selection['held_out_identities'])
                    selected=[.1,1.,10.,100.,1000.][int(np.argmin(selection['inner_scores']))]
                    assert selected==selection['alpha']
            if mode=='transfer':
                assert payload['reference_maximum_error']<1e-8
                assert not set(payload['source_identities'])&set(payload['destination_identities'])
                assert all(manifest['units'][i+'__L0']['cohort']=='replication' for i in payload['source_identities'])
            for cell in payload['cells']:
                key=(cell['cohort'],cell['condition_id'],cell['model'],cell['identity'],cell['row_index'])
                assert key not in all_keys
                all_keys.add(key)
                info=manifest['units'][cell['identity']+'__'+cell['condition_id']]
                j=cell['row_index']
                assert cell['target']==info['targets'][j]
                assert cell['model_frame_idx']==info['target_model_frame_indices'][j]
                assert cell['context_age']==info['context_ages'][j]
                if mode=='predictions':
                    assert cell['outer_fold']==info['outer_fold']
                    fold=manifest['folds'][info['cohort']][cell['outer_fold']]
                    assert cell['identity'] in fold['held_out_identities']
                    assert cell['identity'] not in fold['training_identities']
                groups[(mode,)+key[:-1]].append(cell)
        counts[mode]=len(all_keys)
    assert counts==dict(predictions=19950,transfer=5700),counts
    independent={}
    for key,rows in groups.items():
        assert len(rows)==19
        y=[r['target'] for r in rows]
        residual=[r['prediction']-r['target'] for r in rows]
        mean=math.fsum(y)/19
        mse=math.fsum(v*v for v in residual)/19
        independent[key]=dict(rmse=math.sqrt(mse),mae=math.fsum(map(abs,residual))/19,
            r2=1-math.fsum(v*v for v in residual)/math.fsum((v-mean)**2 for v in y))
    for mode,summary in [('predictions',statistics),('transfer',transferred)]:
        for row in summary['summaries']:
            values=[v for k,v in independent.items() if k[:4]==(mode,row['cohort'],row['condition'],row['model'])]
            assert len(values)==25
            for metric in ['rmse','mae','r2']:
                expected=math.fsum(v[metric] for v in values)/25
                errors.append(abs(expected-row[metric]['mean']))
    assert max(errors)<1e-11,max(errors)
    # Check primary paired bootstrap independently using explicit resampled sums.
    rng=np.random.default_rng(20260911)
    index=rng.integers(0,25,(10000,25))
    bootstrap_errors=[]
    for c in statistics['paired_contrasts']:
        if c['condition'] not in ['L0','L4']:
            continue
        other=c['contrast'].split('-minus-')[1]
        names=sorted({k[4] for k in independent if k[:4]==('predictions',c['cohort'],c['condition'],'MW_RGB_L19')})
        differences=[independent['predictions',c['cohort'],c['condition'],'MW_RGB_L19',i]['rmse']-independent['predictions',c['cohort'],c['condition'],other,i]['rmse'] for i in names]
        means=[math.fsum(differences[int(j)] for j in draw)/25 for draw in index]
        lo,hi=np.quantile(means,[.025,.975])
        bootstrap_errors.extend([abs(float(lo)-c['ci95'][0]),abs(float(hi)-c['ci95'][1])])
    assert max(bootstrap_errors)<1e-11,max(bootstrap_errors)
    save(ROOT/'analysis/independent_validation.json',dict(status='PASS',cells=counts,independent_mean_max_difference=max(errors),independent_paired_interval_max_difference=max(bootstrap_errors),target_fold_and_identity_joins='PASS',transfer_source_separation='PASS',known_legacy_test='154 passed; one existing bitwise historical FIR equality assertion differs only by floating-point summation. See arithmetic_audit.json and core_tests_git_resolved.xml.'))
    print('INDEPENDENT_RESULT_VALIDATION_PASS',counts,max(errors),max(bootstrap_errors))


if __name__=='__main__':
    main()

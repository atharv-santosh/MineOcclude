"""Fail closed on incomplete follow-up coverage or mismatched labels/folds."""
import json
import numpy as np
from audit_recovery import ROOT,PKG,OUT,read,save,sha

def main():
    expected=read(PKG/'cohort/EXECUTED_TARGETS.json')['rows']
    targets={(r['identity'],r['condition_id'],r['row_index']):r for r in expected}
    folds=read(PKG/'cohort/FOLD_ASSIGNMENTS.json')['folds']
    scope={m:[f'L{j}' for j in range(5)] for m in ['PIXEL_CURRENT','PIXEL_HISTORY16']+[f'MW_{o}_L{k:02d}' for o in ('RGB','BGR') for k in (4,10,19)]}
    scope.update({f'MW_RGB_L19_CTX{n}':['L0','L4'] for n in (1,8)})
    checks=[]
    for model,conditions in scope.items():
        for c in conditions:
            path=OUT/'predictions'/f'{model}__{c}.json'
            result=read(path)
            assert result['model']==model and result['condition']==c
            assert result['folds_sha256']==sha(PKG/'cohort/FOLD_ASSIGNMENTS.json')
            keys=[]
            for row in result['cells']:
                key=row['identity'],row['condition_id'],row['row_index']
                keys.append(key)
                target=targets[key]
                for field in ('target','outer_fold','model_frame_idx','server_tick','context_age','frame_sha256'):
                    assert row[field]==target[field],(path.name,key,field)
                assert np.isfinite(row['prediction'])
            assert len(keys)==len(set(keys))==475
            assert set(keys)=={k for k in targets if k[1]==c}
            for selection,fold in zip(result['selections'],folds):
                assert selection['held_out']==fold['held_out_identities']
                assert not set(fold['training_identities'])&set(selection['held_out'])
                assert selection['alpha'] in (.1,1,10,100,1000)
                inner=fold['inner_rotations'].values()
                assert sorted(i for block in inner for i in block)==sorted(fold['training_identities'])
            for identity,digest in result['feature_sha256'].items():
                file=OUT/'features'/model/f'{identity}__{c}.npy'
                assert sha(file)==digest
            checks.append({'model':model,'condition':c,'rows':475,'prediction_sha256':sha(path)})
    index=read(PKG/'cohort/CAPTURE_INDEX.json')['captures']
    windows=[]
    for unit,info in index.items():
        current=np.load(OUT/'features/PIXEL_CURRENT'/f'{unit}.npy')
        history=np.load(OUT/'features/PIXEL_HISTORY16'/f'{unit}.npy')
        assert np.array_equal(current,history[:,-4032:])
        base=ROOT/'recovery_inputs/corpus/captures'/unit/'raw/visibility.jsonl'
        visibility={r['model_frame_idx']:r for r in map(json.loads,base.read_text().splitlines())}
        last=info['last_preocclusion_model_frame_idx']
        for j,t in enumerate(info['target_model_frame_indices']):
            assert t-last==j+1
            extent=[visibility[k]['counterfactual_extent_class'] for k in range(t-15,t+1)]
            remaining=sum(s!='EXTENT_FULLY_OCCLUDED' for s in extent)
            assert remaining==max(0,15-j)
            windows.append({'capture':unit,'age':j+1,'target_frame':t,'window_start':t-15,'last_non_full_row':last,'non_full_extent_frames':remaining})
    for order in ('RGB','BGR'):
        profile=read(OUT/f'profile_{order}.json')
        assert len(profile['checks'])==30 and profile['cache_allowed']
        assert profile['actual_encoder_input_patch_checks']=='PASS'
        assert profile['future_action_invariance']=='PASS'
        assert all(r['repeat_max_abs_error']==0 for r in profile['checks'])
    report={'status':'PASS','planned_prediction_files':len(checks),'new_prediction_cells':sum(r['rows'] for r in checks),'checks':checks,'exact_targets_and_folds':True,'history_final_frame_equals_current':True,'age_and_window_geometry_verified':True,'window_count':len(windows)}
    save(OUT/'new_results_validation.json',report)
    save(OUT/'window_evidence_audit.json',{'note':'Renderer extent is not a guarantee of localizable image evidence. Magenta detector is not treated as ground truth.','windows':windows})
    print('VALIDATED',report['planned_prediction_files'],report['new_prediction_cells'],flush=True)

if __name__=='__main__':
    main()

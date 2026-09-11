"""Compare all current-pixel fits with the unmodified reference implementation."""
from fit_readouts import ROOT,PKG,OUT,read,save
import numpy as np
from mineocclude.experiment_iii.readout import FoldData,cross_validated_predictions

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--model',default='PIXEL_CURRENT')
    parser.add_argument('--conditions',nargs='+',default=['L0','L1','L2','L3','L4'])
    args=parser.parse_args()
    targets=read(PKG/'cohort/EXECUTED_TARGETS.json')['rows']
    folds=read(PKG/'cohort/FOLD_ASSIGNMENTS.json')['folds']
    names=sorted({r['identity'] for r in targets})
    old=read(PKG/'prediction_lock/PREDICTION_LOCK.json')['cells']
    lookup={(r['identity'],r['condition_id'],r['row_index']):r for r in old if r['model']=='LINEAR_CURRENT_PIXEL'}
    checks=[]
    for condition in args.conditions:
        ys={(r['identity'],r['row_index']):r['target'] for r in targets if r['condition_id']==condition}
        data={i:FoldData(identity=i,features=np.load(OUT/'features'/args.model/f'{i}__{condition}.npy'),targets=np.array([ys[i,j] for j in range(19)])) for i in names}
        preds,selections=cross_validated_predictions(data,folds)
        new=read(OUT/'predictions'/f'{args.model}__{condition}.json')
        fast_error=max(abs(r['prediction']-preds[r['identity']][r['row_index']]) for r in new['cells'])
        old_error=max(abs(preds[i][j]-lookup[i,condition,j]['prediction']) for i in names for j in range(19)) if args.model=='PIXEL_CURRENT' else None
        checks.append({'condition':condition,'reference_vs_optimized_max_error':float(fast_error),'reference_vs_original_host_max_error':old_error,'reference_alphas':{k:v.alpha for k,v in selections.items()}})
        print(checks[-1],flush=True)
    suffix='' if args.model=='PIXEL_CURRENT' else '_'+args.model
    assert max(x['reference_vs_optimized_max_error'] for x in checks)<1e-8,checks
    save(OUT/f'reference_solver_check{suffix}.json',{'model':args.model,'checks':checks,'status':'PASS'})

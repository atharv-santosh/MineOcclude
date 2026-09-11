from common import *
import numpy as np
from fit_diag import predict_frozen

def main():
    rows=read(SOURCE/'reproducibility/experiment_iii_a/cohort/EXECUTED_TARGETS.json')['rows']
    target={(r['identity'],r['row_index']):r['target'] for r in rows if r['condition_id']=='L0'}
    maxerr=0.; diagonal=0.; count=0
    for p in sorted((ROOT/'transfer').glob('L?.json')):
        result=read(p);source=p.stem
        for fold in result['selections']:
            fit=ROOT/'transfer'/f'{source}_fold{fold["outer_fold"]}.npz'
            assert sha(fit)==fold['fit_sha256']
            assert not set(fold['training_identities'])&set(fold['held_out_identities'])
            for c in ['L0','L1','L2','L3','L4']:
                for i in fold['held_out_identities']:
                    x=np.load(SOURCE/'replication_outputs/features/MW_RGB_L19'/f'{i}__{c}.npy',allow_pickle=False)
                    pred=predict_frozen(fit,x)
                    selected=sorted([r for r in result['cells'] if r['identity']==i and r['destination']==c],key=lambda r:r['row_index'])
                    assert len(selected)==19
                    maxerr=max(maxerr,float(np.max(abs(pred-[r['prediction'] for r in selected]))))
                    assert all(r['target']==target[i,r['row_index']] for r in selected)
                    count+=len(selected)
        legacy=read(SOURCE/'replication_outputs/predictions'/f'MW_RGB_L19__{source}.json')['cells']
        old={(r['identity'],r['row_index']):r['prediction'] for r in legacy}
        diagonal=max(diagonal,max(abs(r['prediction']-old[r['identity'],r['row_index']]) for r in result['cells'] if r['destination']==source))
    assert maxerr<1e-8 and diagonal<1e-7,(maxerr,diagonal)
    for model in ['FRAME_DIFF16','FLOW16','VIDEOMAE_S','OPACITY_PIXELS','OPACITY_MW']:
        for p in sorted((ROOT/'central/predictions').glob(f'{model}__*.json')):
            data=read(p); source=p.stem.split('__')[1]
            for f in data['selections']:
                fit=ROOT/'central/fits'/f'{model}__{source}__{f["fold"]}.npz'
                assert sha(fit)==f['fit_sha256'] and not set(f['training'])&set(f['held'])
                for c in sorted({r['condition'] for r in data['cells']}):
                    for i in f['held']:
                        x=np.load(ROOT/'central/features'/model/f'{i}__{c}.npy',allow_pickle=False)
                        pred=predict_frozen(fit,x)
                        selected=sorted([r for r in data['cells'] if r['identity']==i and r['condition']==c],key=lambda r:r['row_index'])
                        assert all(r['target']==target[i,r['row_index']] for r in selected)
                        maxerr=max(maxerr,float(np.max(abs(pred-[r['prediction'] for r in selected]))))
                        count+=len(selected)
    assert maxerr<1e-7,maxerr
    for p in (ROOT/'central/features/OPACITY_PIXELS').glob('*__A000.npy'):
        i=p.name.split('__')[0]
        assert np.array_equal(np.load(p),np.load(SOURCE/'replication_outputs/features/PIXEL_HISTORY16'/f'{i}__L0.npy'))
    mwzero=[]
    for p in (ROOT/'central/features/OPACITY_MW').glob('*__A000.npy'):
        i=p.name.split('__')[0]
        delta=float(np.max(abs(np.load(p)-np.load(SOURCE/'replication_outputs/features/MW_RGB_L19'/f'{i}__L0.npy'))))
        assert delta==0.,delta
        mwzero.append(delta)
    save(ROOT/f'central_validation_{count}.json',dict(status='PASS',prediction_rows=count,saved_fit_replay_max_error=maxerr,legacy_diagonal_max_error=diagonal,opacity_zero_mw_count=len(mwzero),source_only_splits_verified=True))
    print('CENTRAL_VALIDATION_PASS',count,maxerr,diagonal,flush=True)

if __name__=='__main__':main()

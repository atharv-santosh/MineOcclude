from common import *
import numpy as np
from fit_diag import Ridge, predict_frozen
import time

CONDITIONS = ['L0','L1','L2','L3','L4']
ALPHAS = np.array([.1,1.,10.,100.,1000.])

def main():
    pkg = SOURCE/'reproducibility/experiment_iii_a/cohort'
    old = SOURCE/'replication_outputs'
    targets = read(pkg/'EXECUTED_TARGETS.json')['rows']
    folds = read(pkg/'FOLD_ASSIGNMENTS.json')['folds']
    names = sorted({r['identity'] for r in targets})
    model = 'MW_RGB_L19'
    candidates = sorted(p.name for p in (old/'features').iterdir())
    if model not in candidates:
        raise RuntimeError(('Inspect exact verified feature name', candidates))
    x = {(c,i): np.load(old/'features'/model/f'{i}__{c}.npy', allow_pickle=False) for c in CONDITIONS for i in names}
    mapping = {(r['condition_id'],r['identity'],r['row_index']):r for r in targets}
    y = {(c,i):np.array([mapping[c,i,j]['target'] for j in range(19)]) for c in CONDITIONS for i in names}
    for c in CONDITIONS:
        for i in names:
            assert x[c,i].shape == (19,24576) and np.isfinite(x[c,i]).all()
            assert np.array_equal(y[c,i],y['L0',i])
    out = ROOT/'transfer'
    out.mkdir(parents=True,exist_ok=True)
    manifest = out/'INPUT_LOCK.json'
    if not manifest.exists():
        save(manifest, dict(protocol_sha256=sha(Path(__file__).with_name('PROTOCOL.md')), script_sha256=sha(Path(__file__)), folds_sha256=sha(pkg/'FOLD_ASSIGNMENTS.json'), targets_sha256=sha(pkg/'EXECUTED_TARGETS.json'), features={f'{c}/{i}':sha(old/'features'/model/f'{i}__{c}.npy') for c in CONDITIONS for i in names}))
    else:
        assert read(manifest)['script_sha256']==sha(Path(__file__))
    start = time.monotonic()
    for source in CONDITIONS:
        dest = out/f'{source}.json'
        if dest.exists():
            continue
        cells=[]
        selections=[]
        for fold in folds:
            train,held=fold['training_identities'],fold['held_out_identities']
            assert not set(train)&set(held)
            scores=[]
            for _,val in sorted(fold['inner_rotations'].items()):
                fit=[i for i in train if i not in val]
                fitted=Ridge(np.concatenate([x[source,i] for i in fit]),np.concatenate([y[source,i] for i in fit]))
                p=fitted.predict(np.concatenate([x[source,i] for i in val]),ALPHAS)
                truth=np.concatenate([y[source,i] for i in val])
                scores.append(np.sqrt(((p-truth[:,None])**2).reshape(len(val),19,5).mean(axis=1)).mean(axis=0))
            means=np.mean(scores,axis=0)
            alpha=float(ALPHAS[np.argmin(means)])
            fitted=Ridge(np.concatenate([x[source,i] for i in train]),np.concatenate([y[source,i] for i in train]))
            path=out/f'{source}_fold{fold["outer_fold"]}.npz'
            assert not path.exists()
            fitted.freeze(path,alpha)
            for destination in CONDITIONS:
                q=np.concatenate([x[destination,i] for i in held])
                p=fitted.predict(q,[alpha])[:,0]
                assert np.max(abs(p-predict_frozen(path,q)))<1e-8
                for n,i in enumerate(held):
                    for j in range(19):
                        cells.append(dict(source=source,destination=destination,identity=i,row_index=j,outer_fold=fold['outer_fold'],target=float(y[destination,i][j]),prediction=float(p[n*19+j])))
            selections.append(dict(outer_fold=fold['outer_fold'],training_identities=train,held_out_identities=held,alpha=alpha,inner_scores=means.tolist(),fit_sha256=sha(path)))
            print('TRANSFER',source,fold['outer_fold'],alpha,round(time.monotonic()-start,1),flush=True)
        save(dest,dict(cells=cells,selections=selections,source_only_tuning=True,input_lock_sha256=sha(manifest)))
    allcells=[v for c in CONDITIONS for v in read(out/f'{c}.json')['cells']]
    assert len(allcells)==11875
    rng=np.random.default_rng(94111)
    draws=rng.integers(0,len(names),(10000,len(names)))
    statistics=[]
    errors={}
    for s in CONDITIONS:
        for d in CONDITIONS:
            rows=[r for r in allcells if r['source']==s and r['destination']==d]
            e=np.array([[r['prediction']-r['target'] for r in rows if r['identity']==i] for i in names])
            errors[s,d]=np.sqrt((e**2).mean(axis=1))
    for s in CONDITIONS:
        for d in CONDITIONS:
            rows=[r for r in allcells if r['source']==s and r['destination']==d]
            rmse=errors[s,d]
            penalty=rmse-errors[d,d]
            statistics.append(dict(source=s,destination=d,rmse=float(rmse.mean()),rmse_ci=np.quantile(rmse[draws].mean(axis=1),[.025,.975]).tolist(),mae=float(np.mean([abs(r['prediction']-r['target']) for r in rows])),transfer_penalty=float(penalty.mean()),penalty_ci=np.quantile(penalty[draws].mean(axis=1),[.025,.975]).tolist()))
    save(out/'statistics.json',dict(cells=statistics,prediction_rows=len(allcells),bootstrap_unit='identity',bootstrap_draws=10000,seed=94111))
    print('TRANSFER_COMPLETE',json.dumps(statistics),flush=True)

if __name__=='__main__':
    main()

"""Preserved-budget sensitivity check triggered only by training nonconvergence."""
from diag_common import *
import argparse
from datetime import datetime,timezone
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','4')
os.environ.setdefault('OMP_NUM_THREADS','4')
import time
import warnings
import numpy as np
from sklearn.decomposition import PCA
from sklearn.neural_network import MLPRegressor
from sklearn.exceptions import ConvergenceWarning
from fit_diag import Nonlinear,standardize,feature,make_cells,predict_frozen,SEEDS

OUT=ROOT/'analysis'
DEST=OUT/'optimizer_check'


class Extended(Nonlinear):
    def __init__(self,x,y,alpha):
        z,self.mask,self.mean,self.scale=standardize(x)
        self.pca=PCA(n_components=min(64,len(x)-1,z.shape[1]),svd_solver='randomized',random_state=93011)
        projected=self.pca.fit_transform(z)
        self.ymean=float(y.mean()); self.yscale=float(y.std())
        self.models=[]; self.warnings=[]; self.diagnostics=[]
        for seed in SEEDS:
            model=MLPRegressor(hidden_layer_sizes=(32,),activation='tanh',solver='lbfgs',alpha=alpha,random_state=seed,max_iter=10000,max_fun=250000,tol=1e-5)
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always',ConvergenceWarning)
                model.fit(projected,(y-self.ymean)/self.yscale)
            messages=[str(w.message) for w in caught]
            self.models.append(model); self.warnings.extend(messages)
            self.diagnostics.append(dict(seed=seed,iterations=int(model.n_iter_),training_loss=float(model.loss_),warnings=messages))


def freeze():
    assert not DEST.exists()
    records=list((OUT/'fits').glob('MW_300M_MLP__*.json'))
    assert len(records)==4 and all(read(p)['convergence_warnings'] for p in records)
    source=Path(__file__).parent
    save(ROOT/'optimizer_check_freeze.json',dict(status='SUPPLEMENTARY_TRAINING_DIAGNOSTIC_NOT_ORIGINAL_PREREGISTRATION',utc=datetime.now(timezone.utc).isoformat(),reason='All 300M nonlinear training searches reported iteration-limit warnings. No test scores were consulted for this change.',changes=dict(max_iter=[500,10000],max_fun=[25000,250000]),unchanged=['architecture','training-only PCA and scaling','selected penalty from original training folds','three seeds','train/test split','all test conditions'],selection='Retain both budgets; do not choose between them using test results.',original_fit_records={p.name:sha(p) for p in records},source_sha256={name:sha(source/name) for name in ['optimizer_check.py','optimizer_statistics.py']}))
    print('TRAINING_DIAGNOSTIC_CHECK_FROZEN',flush=True)


def run(model):
    assert read(OUT/'analysis_complete.json')['status']=='PASS'
    freeze_record=read(ROOT/'optimizer_check_freeze.json')
    for name,h in freeze_record['source_sha256'].items():
        assert sha(Path(__file__).parent/name)==h
    started=time.monotonic()
    rows=read(ROOT/'roster.json')['identities']
    replay=[]
    for layout in ['layout_01','layout_04']:
        train=[r for r in rows if r['partition']=='train' and r['layout_id']==layout]
        test=[r for r in rows if r['partition']=='test' and r['layout_id']==layout]
        assert not {r['identity'] for r in train}&{r['identity'] for r in test}
        for c in ['L0','L4']:
            original=OUT/'fits'/f'{model}_MLP__{layout}__{c}.json'
            selected=read(original)
            assert selected['training_identities']==[r['identity'] for r in train]
            x=np.concatenate([np.load(feature(model,'correct',r['identity'],c),allow_pickle=False) for r in train])
            y=np.concatenate([r['historical_FIR_reference_labels'] for r in train])
            fitted=Extended(x,y,selected['alpha'])
            name=f'{model}_MLP_OPT10K__{layout}__{c}'
            fitpath=DEST/'fits'/f'{name}.npz'
            assert not fitpath.exists(); fitpath.parent.mkdir(parents=True,exist_ok=True)
            fitted.freeze(fitpath,selected['alpha'])
            # Persist fit and training diagnostics before any test prediction.
            save(fitpath.with_suffix('.json'),dict(model=model+'_MLP_OPT10K',layout=layout,condition=c,alpha=selected['alpha'],original_selection_sha256=sha(original),fit_sha256=sha(fitpath),training_identities=selected['training_identities'],training_only_diagnostics=fitted.diagnostics,penalty_search_reopened=False,freeze_sha256=sha(ROOT/'optimizer_check_freeze.json')))
            cells=[]
            for phase in (['correct'] if c=='L0' else ['correct','swapped','removed']):
                q=np.concatenate([np.load(feature(model,phase,r['identity'],c),allow_pickle=False) for r in test])
                pred=fitted.predict(q)
                delta=float(np.max(abs(pred-predict_frozen(fitpath,q))))
                assert delta<1e-8,delta
                replay.append(delta)
                cells.extend(make_cells(test,pred,model+'_MLP_OPT10K',c,phase))
            save(DEST/'predictions'/f'{name}.json',dict(cells=cells,fit_sha256=sha(fitpath),supplementary_optimizer_check=True,original_budget_preserved=True))
            print('OPTIMIZER_CHECK',name,'iterations',[d['iterations'] for d in fitted.diagnostics],'warnings',len(fitted.warnings),flush=True)
    save(DEST/f'{model}_complete.json',dict(status='PASS',seconds=time.monotonic()-started,max_saved_fit_replay_error=max(replay),cells=3648))


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('mode',choices=['freeze','MW_700M','MW_300M']); a=p.parse_args()
    freeze() if a.mode=='freeze' else run(a.mode)

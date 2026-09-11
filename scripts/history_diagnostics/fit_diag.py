import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','6')
os.environ.setdefault('OMP_NUM_THREADS','6')
from diag_common import *
import argparse
import time
import warnings
import numpy as np
from scipy.linalg import eigh
from sklearn.decomposition import PCA
from sklearn.neural_network import MLPRegressor
from sklearn.exceptions import ConvergenceWarning

OUT=ROOT/'analysis'
ALPHAS=np.array([.1,1.,10.,100.,1000.])
MLP_ALPHAS=[.001,.1]
SEEDS=[1301,1302,1303]


def standardize(x):
    mask=np.ptp(x,axis=0)>0
    mean=x[:,mask].mean(axis=0)
    scale=x[:,mask].std(axis=0)
    assert np.all(scale>0)
    return (x[:,mask]-mean)/scale,mask,mean,scale


class Ridge:
    def __init__(self,x,y):
        z,self.mask,self.mean,self.scale=standardize(x)
        self.ymean=float(y.mean())
        self.z=z
        self.values,self.vectors=eigh(z@z.T,check_finite=True)
        assert self.values.min()>-1e-5*max(1,self.values.max())
        self.values=np.maximum(self.values,0)
        self.projected=self.vectors.T@(y-self.ymean)

    def predict(self,q,alphas):
        standardized=(q[:,self.mask]-self.mean)/self.scale
        values=[]
        for alpha in alphas:
            weights=self.z.T@(self.vectors@(self.projected/(self.values+alpha)))
            values.append(np.concatenate([standardized[k:k+19]@weights+self.ymean for k in range(0,len(q),19)]))
        return np.stack(values,axis=1)

    def freeze(self,path,alpha):
        weights=self.z.T@(self.vectors@(self.projected/(self.values+alpha)))
        np.savez_compressed(path,mask=self.mask,mean=self.mean,scale=self.scale,ymean=self.ymean,weights=weights,alpha=alpha)


class Nonlinear:
    def __init__(self,x,y,alpha):
        z,self.mask,self.mean,self.scale=standardize(x)
        assert z.shape[1]>0
        self.pca=PCA(n_components=min(64,len(x)-1,z.shape[1]),svd_solver='randomized',random_state=93011)
        projected=self.pca.fit_transform(z)
        self.ymean=float(y.mean())
        self.yscale=float(y.std())
        assert self.yscale>0
        self.models=[]
        self.warnings=[]
        for seed in SEEDS:
            model=MLPRegressor(hidden_layer_sizes=(32,),activation='tanh',solver='lbfgs',alpha=alpha,random_state=seed,max_iter=500,max_fun=25000,tol=1e-5)
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always',ConvergenceWarning)
                model.fit(projected,(y-self.ymean)/self.yscale)
            self.warnings.extend(str(w.message) for w in caught)
            self.models.append(model)

    def predict(self,q):
        z=(q[:,self.mask]-self.mean)/self.scale
        p=self.pca.transform(z)
        return np.mean([m.predict(p) for m in self.models],axis=0)*self.yscale+self.ymean

    def freeze(self,path,alpha):
        payload=dict(mask=self.mask,mean=self.mean,scale=self.scale,ymean=self.ymean,yscale=self.yscale,pca_components=self.pca.components_,pca_mean=self.pca.mean_,alpha=alpha)
        for s,m in enumerate(self.models):
            for layer,(w,b) in enumerate(zip(m.coefs_,m.intercepts_)):
                payload[f'w{s}_{layer}']=w
                payload[f'b{s}_{layer}']=b
        np.savez_compressed(path,**payload)


def train_model(x,y,rows,kind):
    candidates=ALPHAS if kind=='ridge' else MLP_ALPHAS
    scores=[]
    convergence=[]
    for fold in range(4):
        fit=[r['identity'] for r in rows if r['outer_fold']!=fold]
        val=[r['identity'] for r in rows if r['outer_fold']==fold]
        assert len(fit)==18 and len(val)==6 and not set(fit)&set(val)
        tx=np.concatenate([x[i] for i in fit])
        ty=np.concatenate([y[i] for i in fit])
        q=np.concatenate([x[i] for i in val])
        truth=np.concatenate([y[i] for i in val])
        if kind=='ridge':
            pred=Ridge(tx,ty).predict(q,candidates)
        else:
            columns=[]
            for alpha in candidates:
                model=Nonlinear(tx,ty,alpha)
                columns.append(model.predict(q))
                convergence.extend(model.warnings)
            pred=np.stack(columns,axis=1)
        score=np.sqrt(((pred-truth[:,None])**2).reshape(6,19,len(candidates)).mean(axis=1)).mean(axis=0)
        scores.append(score)
    means=np.mean(scores,axis=0)
    alpha=float(candidates[np.argmin(means)])
    names=[r['identity'] for r in rows]
    tx=np.concatenate([x[i] for i in names])
    ty=np.concatenate([y[i] for i in names])
    fitted=Ridge(tx,ty) if kind=='ridge' else Nonlinear(tx,ty,alpha)
    if kind!='ridge':
        convergence.extend(fitted.warnings)
    return fitted,alpha,dict(candidates=list(map(float,candidates)),mean_validation_rmse=means.tolist(),fold_scores=np.array(scores).tolist(),alpha=alpha,training_identities=names,training_folds={r['identity']:r['outer_fold'] for r in rows},convergence_warnings=convergence)


def feature(model,phase,i,c):
    return OUT/'features'/model/phase/f'{i}__{c}.npy'


def make_cells(rows,pred,model,c,phase,setting='native'):
    cells=[]
    for n,r in enumerate(rows):
        for j in range(19):
            cells.append(dict(identity=r['identity'],layout=r['layout_id'],partition=r['partition'],direction=r['direction'],donor=r['donor'],condition=c,phase=phase,setting=setting,model=model,age=j+1,target=float(r['historical_FIR_reference_labels'][j]),prediction=float(pred[n*19+j])))
    return cells


def fit_one(feature_model,layout,c,kind,roster):
    model_name=feature_model+('_MLP' if kind=='mlp' else '')
    destination=OUT/'predictions'/f'{model_name}__{layout}__{c}.json'
    if destination.exists():
        return
    train=[r for r in roster if r['layout_id']==layout and r['partition']=='train']
    test=[r for r in roster if r['layout_id']==layout and r['partition']=='test']
    assert len(train)==len(test)==24
    x={r['identity']:np.load(feature(feature_model,'correct',r['identity'],c),allow_pickle=False) for r in train}
    y={r['identity']:np.array(r['historical_FIR_reference_labels']) for r in train}
    fitted,alpha,selection=train_model(x,y,train,kind)
    folder=OUT/'fits'
    folder.mkdir(parents=True,exist_ok=True)
    fitted_path=folder/f'{model_name}__{layout}__{c}.npz'
    fitted.freeze(fitted_path,alpha)
    selection.update(model=model_name,layout=layout,condition=c,fit_sha256=sha(fitted_path),training_feature_sha256={r['identity']:sha(feature(feature_model,'correct',r['identity'],c)) for r in train},analysis_spec_sha256=sha(Path(__file__).parent/'ANALYSIS_FREEZE.md'),roster_sha256=sha(ROOT/'roster.json'))
    save(folder/f'{model_name}__{layout}__{c}.json',selection)
    cells=[]
    for phase in (['correct','swapped','removed'] if c=='L4' else ['correct']):
        q=np.concatenate([np.load(feature(feature_model,phase,r['identity'],c),allow_pickle=False) for r in test])
        pred=fitted.predict(q,[alpha])[:,0] if kind=='ridge' else fitted.predict(q)
        assert np.isfinite(pred).all()
        cells.extend(make_cells(test,pred,model_name,c,phase))
    save(destination,dict(cells=cells,selection_sha256=sha(folder/f'{model_name}__{layout}__{c}.json'),fit_sha256=sha(fitted_path),test_used_for_selection=False))
    print('FITTED',model_name,layout,c,'alpha',alpha,'warnings',len(selection['convergence_warnings']),flush=True)


def predict_frozen(path,q):
    with np.load(path,allow_pickle=False) as f:
        z=(q[:,f['mask']]-f['mean'])/f['scale']
        if 'weights' in f:
            return np.concatenate([z[k:k+19]@f['weights']+f['ymean'] for k in range(0,len(q),19)])
        p=(z-f['pca_mean'])@f['pca_components'].T
        values=[]
        for s in range(3):
            a=np.tanh(p@f[f'w{s}_0']+f[f'b{s}_0'])
            values.append((a@f[f'w{s}_1']+f[f'b{s}_1']).ravel())
        return np.mean(values,axis=0)*f['yscale']+f['ymean']


def transfer(model,rows):
    path=OUT/'predictions'/f'{model}__transfer.json'
    if path.exists():
        return
    cal=[r for r in rows if r['partition']=='train' and r['layout_id']=='layout_04' and r['rank'] in (0,4,8)]
    test=[r for r in rows if r['partition']=='test' and r['layout_id']=='layout_04']
    assert len(cal)==6 and not {r['identity'] for r in cal}&{r['identity'] for r in test}
    q=np.concatenate([np.load(feature(model,'correct',r['identity'],'L0'),allow_pickle=False) for r in cal])
    p=predict_frozen(OUT/'fits'/f'{model}__layout_01__L0.npz',q)
    truth=np.concatenate([r['historical_FIR_reference_labels'] for r in cal])
    coefficients=np.linalg.lstsq(np.column_stack([np.ones(len(p)),p]),truth,rcond=None)[0]
    save(OUT/'fits'/f'{model}__transfer_calibration.json',dict(coefficients=coefficients.tolist(),calibration_identities=[r['identity'] for r in cal],condition='L0',hidden_calibration_labels_used=False))
    cells=[]
    for c in ['L0','L4']:
        q=np.concatenate([np.load(feature(model,'correct',r['identity'],c),allow_pickle=False) for r in test])
        p=predict_frozen(OUT/'fits'/f'{model}__layout_01__{c}.npz',q)
        cells.extend(make_cells(test,p,model,c,'correct','frozen_transfer'))
        cells.extend(make_cells(test,coefficients[0]+coefficients[1]*p,model,c,'correct','visible_calibrated_transfer'))
    save(path,dict(cells=cells,calibration=coefficients.tolist(),calibration_identities=[r['identity'] for r in cal]))
    print('TRANSFER_PREDICTIONS',model,flush=True)


def verify_math():
    from sklearn.linear_model import Ridge as Reference
    rng=np.random.default_rng(210)
    x=rng.normal(size=(57,119)); x[:,0]=3.; x[:,1]=x[:,2]
    q=rng.normal(size=(38,119)); q[:,0]=99.; q[:,1]=q[:,2]
    y=rng.normal(size=57)
    fit=Ridge(x,y)
    pred=fit.predict(q,ALPHAS)
    z,mask,mean,scale=standardize(x)
    error=[]
    for j,a in enumerate(ALPHAS):
        ref=Reference(alpha=a,solver='svd').fit(z,y).predict((q[:,mask]-mean)/scale)
        error.append(float(np.max(abs(pred[:,j]-ref))))
    assert max(error)<1e-8,error
    empty=Ridge(np.ones((57,4)),y).predict(np.ones((19,4))*100,ALPHAS)
    assert np.allclose(empty,y.mean(),atol=1e-12)
    folder=OUT/'tests'; folder.mkdir(parents=True,exist_ok=True)
    f=folder/'synthetic_ridge.npz'; fit.freeze(f,1.)
    assert np.max(abs(predict_frozen(f,q)-pred[:,1]))<1e-8
    mlp=Nonlinear(x,y,.1)
    f=folder/'synthetic_mlp.npz'; mlp.freeze(f,.1)
    delta=float(np.max(abs(predict_frozen(f,q)-mlp.predict(q))))
    assert delta<1e-8
    save(folder/'solver_validation.json',dict(status='PASS',ridge_reference_max_error=max(error),mlp_serialized_max_error=delta,constant_training_features='Removed without consulting test values',test_labels_not_used=True))
    print('SOLVER_PASS',max(error),delta,flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--models',nargs='+',default=['PIXEL_CURRENT','PIXEL_HISTORY16','MW_700M','MW_300M'])
    p.add_argument('--mlp',action='store_true')
    p.add_argument('--test-only',action='store_true')
    a=p.parse_args()
    if a.test_only:
        verify_math(); return
    rows=read(ROOT/'roster.json')['identities']
    for model in a.models:
        for layout in ['layout_01','layout_04']:
            for c in ['L0','L4']:
                fit_one(model,layout,c,'ridge',rows)
                if a.mlp and model.startswith('MW_'):
                    fit_one(model,layout,c,'mlp',rows)
        transfer(model,rows)


if __name__=='__main__':
    main()

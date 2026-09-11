from common import *
import argparse
import numpy as np
from fit_diag import Ridge,predict_frozen

ALPHAS=np.array([.1,1.,10.,100.,1000.])

def main():
    p=argparse.ArgumentParser();p.add_argument('--model',required=True);a=p.parse_args()
    roster=read(MOTION_ROSTER)['rows']
    out=ROOT/'motion'
    for layout in ['layout_01','layout_04']:
        train=[r for r in roster if r['partition']=='train' and r['layout_id']==layout]
        test=[r for r in roster if r['partition']=='test' and r['layout_id']==layout]
        assert len(train)==len(test)==64
        for source in ['L0','L4']:
            path=out/'predictions'/f'{a.model}__{layout}__{source}.json'
            if path.exists():continue
            def matrix(rs,c):return np.concatenate([np.load(out/'features'/a.model/f'{r["identity"]}__{c}.npy',allow_pickle=False) for r in rs])
            def labels(rs):return np.concatenate([r['historical_FIR_reference_labels'] for r in rs])
            scores=[]
            for fold in range(4):
                fit=[r for r in train if r['outer_fold']!=fold];val=[r for r in train if r['outer_fold']==fold]
                assert not {r['family_id'] for r in fit}&{r['family_id'] for r in val}
                m=Ridge(matrix(fit,source),labels(fit))
                pred=m.predict(matrix(val,source),ALPHAS)
                errors=np.sqrt(((pred-labels(val)[:,None])**2).reshape(len(val),19,5).mean(1))
                scores.append(errors.mean(0))
            means=np.mean(scores,0);alpha=float(ALPHAS[np.argmin(means)])
            model=Ridge(matrix(train,source),labels(train))
            fitpath=out/'fits'/f'{a.model}__{layout}__{source}.npz'
            fitpath.parent.mkdir(parents=True,exist_ok=True);assert not fitpath.exists()
            model.freeze(fitpath,alpha)
            cells=[]
            for c in ['L0','L4']:
                q=matrix(test,c);pred=model.predict(q,[alpha])[:,0]
                assert np.max(abs(pred-predict_frozen(fitpath,q)))<1e-7
                for n,r in enumerate(test):
                    for j in range(19):cells.append(dict(identity=r['identity'],family_id=r['family_id'],family=r['family'],variant=r['variant'],layout=layout,direction=r['direction'],age=j+1,model=a.model,source=source,condition=c,target=r['historical_FIR_reference_labels'][j],prediction=float(pred[n*19+j])))
            save(path,dict(cells=cells,alpha=alpha,scores=means.tolist(),training_ids=[r['identity'] for r in train],fit_sha256=sha(fitpath),roster_sha256=sha(MOTION_ROSTER),analysis_sha256=sha(Path(__file__).with_name('MOTION_ANALYSIS.md'))))
            print('MOTION_FIT',a.model,layout,source,alpha,flush=True)

if __name__=='__main__':main()

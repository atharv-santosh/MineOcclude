from common import *
import numpy as np
from central_features import images,opacity_assets,blend

def main():
    out=ROOT/'central'
    names=sorted({r['identity'] for r in read(SOURCE/'reproducibility/experiment_iii_a/cohort/EXECUTED_TARGETS.json')['rows']})
    rng=np.random.default_rng(94114);draws=rng.integers(0,25,(10000,25))
    comparisons=[]
    for c in ['L0','L1','L2','L3','L4']:
        mw=read(ROOT/'transfer'/f'{c}.json')['cells']
        def rmse(cells,condition):
            return np.array([np.sqrt(np.mean([(r['prediction']-r['target'])**2 for r in cells if r['identity']==i and r.get('condition',r.get('destination'))==condition])) for i in names])
        neural=rmse(mw,c)
        for model in ['FRAME_DIFF16','FLOW16','VIDEOMAE_S']:
            baseline=rmse(read(out/'predictions'/f'{model}__{c}.json')['cells'],c)
            delta=neural-baseline
            comparisons.append(dict(condition=c,baseline=model,rmse_difference=float(delta.mean()),ci=np.quantile(delta[draws].mean(1),[.025,.975]).tolist(),interpretation='negative favors MineWorld'))
    save(out/'paired_comparisons.json',dict(results=comparisons,bootstrap_seed=94114,bootstrap_draws=10000,unit='paired identity'))
    mask,texture,receipt=opacity_assets()
    captures=read(SOURCE/'reproducibility/experiment_iii_a/cohort/CAPTURE_INDEX.json')['captures']
    covered=[]
    def magenta(f):
        r,g,b=f.astype(float).transpose(2,0,1)
        return (r>45)&(b>30)&(r>1.4*g)&(b>1.25*g)
    for unit,info in sorted(captures.items()):
        if info['condition_id']!='L0':continue
        raw=images(unit,info)
        for t in info['target_model_frame_indices']:
            obj=magenta(raw[t]);opaque=blend(raw[t],mask,texture,1.)
            assert obj.sum()>20 and not (obj&~mask).any(),(unit,t,'Mask does not cover target')
            assert not magenta(opaque).any(),(unit,t,'Residual target pixels')
            covered.append(dict(unit=unit,index=t,target_pixels=int(obj.sum()),uncovered_target_pixels=0,opaque_target_pixels=0))
    save(out/'opacity_coverage.json',dict(status='PASS',rows=covered,mask=receipt,note='Geometry-only fixed mask covers all scored magenta sheep pixels. Texture residual is not an object-only evidence metric.'))
    print('CENTRAL_REPORT_PASS',len(covered),flush=True)

if __name__=='__main__':main()

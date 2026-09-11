from common import *
import numpy as np
from mineocclude.experiment_iii.fir import fir_labels

KINDS=['META_LINEAR','META_CUBIC','META_FAMILY','ORACLE_LAST','ORACLE_CV']
FAMILIES=['velocity','acceleration','stop_resume','reversal']

def design(r,kind):
    a=np.arange(1,20,dtype=float)/19
    d=1. if r['direction']=='LEFT_TO_RIGHT' else -1.
    columns=[np.ones(19),np.full(19,d),a,d*a]
    if kind!='META_LINEAR': columns += [a*a,d*a*a,a**3,d*a**3]
    if kind=='META_FAMILY':
        base=columns.copy()
        for f in FAMILIES[1:]: columns += [v*float(r['family']==f) for v in base]
    return np.stack(columns,axis=1)

def oracle(r,kind):
    first=r['target_model_frame_indices'][0]
    observed=list(r['state_positions'][:first])
    velocity=0. if kind=='ORACLE_LAST' else observed[-1]-observed[-2]
    forecast=observed+[observed[-1]+velocity*(j+1) for j in range(19)]
    return np.array(fir_labels(forecast,r['target_model_frame_indices'],r['direction']))

def main():
    assert read(MOTION_ADMISSION)['status']=='PASS'
    rows=read(MOTION_ROSTER)['rows']
    out=ROOT/'motion'
    for layout in ['layout_01','layout_04']:
        train=[r for r in rows if r['layout_id']==layout and r['partition']=='train']
        test=[r for r in rows if r['layout_id']==layout and r['partition']=='test']
        for kind in KINDS:
            coefficients=None
            if kind.startswith('META'):
                x=np.concatenate([design(r,kind) for r in train])
                y=np.concatenate([r['historical_FIR_reference_labels'] for r in train])
                coefficients=np.linalg.lstsq(x,y,rcond=None)[0]
            cells=[]
            for r in test:
                pred=design(r,kind)@coefficients if coefficients is not None else oracle(r,kind)
                for c in ['L0','L4']:
                    for j in range(19):
                        cells.append(dict(identity=r['identity'],family_id=r['family_id'],family=r['family'],variant=r['variant'],layout=layout,direction=r['direction'],age=j+1,model=kind,source='METADATA',condition=c,target=r['historical_FIR_reference_labels'][j],prediction=float(pred[j])))
            p=out/'predictions'/f'{kind}__{layout}.json'
            if not p.exists():save(p,dict(cells=cells,coefficients=None if coefficients is None else coefficients.tolist(),training_ids=[r['identity'] for r in train],information='Pre-occlusion physical state only' if coefficients is None else 'Direction, occlusion age'+(', privileged motion family' if kind=='META_FAMILY' else ''),roster_sha256=sha(MOTION_ROSTER),analysis_sha256=sha(Path(__file__).with_name('MOTION_ANALYSIS.md'))))
    print('MOTION_BASELINES_COMPLETE',flush=True)

if __name__=='__main__':main()

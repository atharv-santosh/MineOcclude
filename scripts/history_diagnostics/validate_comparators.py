"""Additional frozen replay audit of transfer, tracking, and motion predictions."""
from diag_common import *
from datetime import datetime,timezone
import argparse
import math
import numpy as np
from fit_diag import predict_frozen,feature
from mineocclude.experiment_iii.fir import fir_labels

OUT=ROOT/'analysis'


def line(x,y,t):
    x=np.asarray(x,float); y=np.asarray(y,float)
    slope=np.sum((x-x.mean())*(y-y.mean()))/np.sum((x-x.mean())**2)
    return float(y.mean()+slope*(t-x.mean()))


def audit():
    freeze=read(ROOT/'comparator_audit_freeze.json')
    assert freeze['script_sha256']==sha(Path(__file__))
    assert read(OUT/'independent_validation.json')['status']=='PASS'
    rows=read(ROOT/'roster.json')['identities']; by={r['identity']:r for r in rows}
    manifest=read(ROOT/'manifest.json')['units']
    errors=[]; cal_errors=[]; covered=set()
    def check(cell,value):
        errors.append(abs(cell['prediction']-value))
        key=(cell['model'],cell['setting'],cell['condition'],cell['phase'],cell['identity'],cell['age'])
        assert key not in covered
        covered.add(key)
    for model in ['MW_700M','MW_300M','PIXEL_CURRENT','PIXEL_HISTORY16']:
        record=read(OUT/'predictions'/f'{model}__transfer.json')
        cal=read(OUT/'fits'/f'{model}__transfer_calibration.json')
        names=[r['identity'] for r in rows if r['partition']=='train' and r['layout_id']=='layout_04' and r['rank'] in (0,4,8)]
        assert cal['calibration_identities']==record['calibration_identities']==names
        assert cal['hidden_calibration_labels_used'] is False and cal['condition']=='L0'
        q=np.concatenate([np.load(feature(model,'correct',i,'L0'),allow_pickle=False) for i in names])
        p=predict_frozen(OUT/'fits'/f'{model}__layout_01__L0.npz',q)
        y=np.concatenate([by[i]['historical_FIR_reference_labels'] for i in names])
        intercept=line(p,y,0); slope=line(p,y,1)-intercept
        cal_errors.extend(abs(np.array([intercept,slope])-cal['coefficients']))
        test=[r['identity'] for r in rows if r['partition']=='test' and r['layout_id']=='layout_04']
        assert not set(names)&set(test)
        for c in ['L0','L4']:
            q=np.concatenate([np.load(feature(model,'correct',i,c),allow_pickle=False) for i in test])
            prediction=predict_frozen(OUT/'fits'/f'{model}__layout_01__{c}.npz',q)
            indexed={(i,j+1):prediction[n*19+j] for n,i in enumerate(test) for j in range(19)}
            for cell in (r for r in record['cells'] if r['condition']==c):
                value=indexed[cell['identity'],cell['age']]
                if cell['setting']=='visible_calibrated_transfer':
                    value=cal['coefficients'][0]+cal['coefficients'][1]*value
                else:
                    assert cell['setting']=='frozen_transfer'
                check(cell,value)
    transfer_cells=len(covered)
    detections={}
    for path in (OUT/'detections').glob('*.json'):
        r=read(path); assert r['bank_sha256']==manifest[r['unit']]['bank_sha256']
        assert r['script_sha256']==sha(Path(__file__).parent/'baselines_diag.py')
        detections[r['unit']]=r['detections']
    assert len(detections)==192
    for layout in ['layout_01','layout_04']:
        train=[r for r in rows if r['partition']=='train' and r['layout_id']==layout]
        cal=read(OUT/'fits'/f'TRACKER__{layout}.json')
        metadata=read(OUT/'fits'/f'METADATA__{layout}.json')
        assert cal['calibration_identities']==metadata['training_identities']==[r['identity'] for r in train]
        assert metadata['commanded_speed_used'] is False
        targets=[v for r in train for v in r['historical_FIR_reference_labels']]
        mean=math.fsum(targets)/len(targets)
        cal_errors.append(abs(mean-cal['target_mean']))
        ux=[]; yy=[]; dims=[]
        for row in train:
            info=manifest[row['identity']+'__L0']; ds=detections[info['unit']]
            ys=fir_labels(info['state_positions'],list(range(15,180)),row['direction'])
            for n,t in enumerate(range(15,180)):
                d=ds[t]
                if d is not None and abs(info['state_positions'][t])<6:
                    ux.append(d['u']); yy.append(ys[n]); dims.append([d['width'],d['height'],d['area']])
        a=line(ux,yy,0); b=line(ux,yy,1)-a
        cal_errors.extend(abs(np.array([a,b])-cal['beta']))
        assert len(ux)==cal['calibration_frames']
        assert np.array_equal(np.median(dims,axis=0),[cal['width'],cal['height'],cal['area']])
        design=[]
        for row in train:
            sign=1 if row['direction']=='LEFT_TO_RIGHT' else -1
            design.extend([[1,sign,j,sign*j] for j in range(1,20)])
        beta=np.linalg.lstsq(np.array(design,float),np.array(targets),rcond=None)[0]
        cal_errors.extend(abs(beta-metadata['beta']))
        for cell in read(OUT/'predictions'/f'BASELINES__{layout}.json')['cells']:
            row=by[cell['identity']]; info=manifest[cell['identity']+'__'+cell['condition']]
            t=info['target_model_frame_indices'][cell['age']-1]
            model=cell['model']
            if model=='TRAINING_MEAN':
                value=mean
            elif model=='DIRECTION_AGE':
                sign=1 if row['direction']=='LEFT_TO_RIGHT' else -1
                value=float(np.dot([1,sign,cell['age'],sign*cell['age']],beta))
            elif model.startswith('ORACLE_'):
                visible=[j for j in range(t) if not info['fully_occluded'][j]]
                if model=='ORACLE_LAST_SEEN': value=info['state_positions'][visible[-1]]
                else:
                    assert model=='ORACLE_CONSTANT_VELOCITY'
                    used=visible[-10:]
                    value=line(used,[info['state_positions'][j] for j in used],t)
            else:
                assert model=='IMAGE_TRACKER_CV'
                ds=detections[info['unit']]
                if cell['phase']=='correct': window=ds[t-15:t+1]
                elif cell['phase']=='removed': window=[ds[t]]*16
                else:
                    donor=manifest[row['donor']+'__'+cell['condition']]
                    td=donor['target_model_frame_indices'][cell['age']-1]
                    window=detections[donor['unit']][td-15:td]+[ds[t]]
                reliable=[(j,d) for j,d in enumerate(window) if d is not None and d['width']>=.85*cal['width'] and d['height']>=.85*cal['height'] and d['area']>=.65*cal['area']][-10:]
                positions=[cal['beta'][0]+cal['beta'][1]*d['u'] for j,d in reliable]
                value=mean if not reliable else positions[0] if len(reliable)==1 else line([j for j,d in reliable],positions,15)
            check(cell,value)
    assert transfer_cells==7296 and len(covered)==18240
    assert max(errors)<1e-7 and max(cal_errors)<1e-7,(max(errors),max(cal_errors))
    result=dict(status='PASS',transfer_cells=transfer_cells,baseline_cells=len(covered)-transfer_cells,additional_cells_replayed=len(covered),native_cells_replayed_by_primary_audit=21888,total_cells_with_replay=40128,max_prediction_error=max(errors),max_independent_calibration_error=max(cal_errors),training_only_calibration='PASS',detector_receipts=192,script_sha256=sha(Path(__file__)))
    save(OUT/'comparator_replay_validation.json',result)
    print(json.dumps(result,indent=2),flush=True)


def freeze():
    assert not list((OUT/'predictions').glob('*.json'))
    path=ROOT/'comparator_audit_freeze.json'; assert not path.exists()
    save(path,dict(status='ADDITIONAL_VALIDATION_ONLY_BEFORE_TEST_PREDICTIONS',utc=datetime.now(timezone.utc).isoformat(),script_sha256=sha(Path(__file__)),scope='No estimator, split, outcome, or statistical change. Adds replay checks for baseline and transfer cells.'))
    print('COMPARATOR_AUDIT_SEALED',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('mode',choices=['freeze','audit']); a=p.parse_args()
    {'freeze':freeze,'audit':audit}[a.mode]()

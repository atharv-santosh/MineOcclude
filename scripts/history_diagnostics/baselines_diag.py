import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','4')
from diag_common import *
import argparse
import time
import cv2
import numpy as np
from PIL import Image
from features_diag import get_info
from fit_diag import make_cells
from mineocclude.experiment_iii.fir import fir_labels
from mineocclude.experiment_iii.baselines_motion import last_seen,constant_velocity,fit_time_only,predict_time_only

OUT=ROOT/'analysis'


def detect(rgb):
    r,g,b=rgb.astype(np.float32).transpose(2,0,1)
    mask=((r>45)&(b>30)&(r>1.4*g)&(b>1.25*g)).astype(np.uint8)
    n,labels,stats,centers=cv2.connectedComponentsWithStats(mask,8)
    if n<=1:
        return None
    idx=1+int(np.argmax(stats[1:,cv2.CC_STAT_AREA]))
    x,y,w,h,area=map(int,stats[idx])
    return dict(u=x+(w-1)/2,v=y+(h-1)/2,width=w,height=h,area=area)


def detections(info):
    destination=OUT/'detections'/f"{info['unit']}.json"
    if destination.exists():
        cached=read(destination)
        assert cached['bank_sha256']==info['bank_sha256']
        return cached['detections']
    base=ROOT/'captures'/info['unit']
    bank=read(base/'BANKED.json')
    values=[]
    for t in range(180):
        rel=f'client/frames/{t:06d}.png'
        assert sha(base/rel)==bank['files'][rel]
        with Image.open(base/rel) as image:
            values.append(detect(np.asarray(image.convert('RGB'))))
    save(destination,dict(unit=info['unit'],detections=values,bank_sha256=info['bank_sha256'],detector='Fixed largest magenta connected component',script_sha256=sha(Path(__file__))))
    return values


def calibrate(train,info,det):
    us=[]; targets=[]; widths=[]; heights=[]; areas=[]
    for row in train:
        r=info[row['identity'],'L0']; ds=det[row['identity'],'L0']
        labels=fir_labels(r['state_positions'],list(range(15,180)),r['direction'])
        for j,t in enumerate(range(15,180)):
            d=ds[t]
            if d is not None and abs(r['state_positions'][t])<6:
                us.append(d['u']); targets.append(labels[j]); widths.append(d['width']); heights.append(d['height']); areas.append(d['area'])
    beta=np.linalg.lstsq(np.column_stack([np.ones(len(us)),us]),targets,rcond=None)[0]
    assert len(us)>100
    return dict(beta=beta.tolist(),width=float(np.median(widths)),height=float(np.median(heights)),area=float(np.median(areas)),calibration_frames=len(us),calibration_identities=[r['identity'] for r in train],target_mean=float(np.mean([v for r in train for v in r['historical_FIR_reference_labels']])))


def track(window,cal):
    valid=[(j,d) for j,d in enumerate(window) if d is not None and d['width']>=.85*cal['width'] and d['height']>=.85*cal['height'] and d['area']>=.65*cal['area']][-10:]
    if not valid:
        return cal['target_mean'],0
    positions=np.array([cal['beta'][0]+cal['beta'][1]*d['u'] for j,d in valid])
    if len(valid)==1:
        return float(positions[0]),1
    times=np.array([j for j,d in valid],float)
    beta=np.linalg.lstsq(np.column_stack([np.ones(len(times)),times]),positions,rcond=None)[0]
    return float(beta[0]+15*beta[1]),len(valid)


def main():
    p=argparse.ArgumentParser(); p.add_argument('--watch',action='store_true'); a=p.parse_args()
    rows=read(ROOT/'roster.json')['identities']
    info={}; det={}
    for row in rows:
        for c in ['L0','L4']:
            unit=f"{row['identity']}__{c}"
            while not (ROOT/'captures'/unit/'BANKED.json').exists():
                assert a.watch,unit
                time.sleep(5)
            r=get_info(row,c)
            info[row['identity'],c]=r
            det[row['identity'],c]=detections(r)
        print('DETECTIONS',row['identity'],flush=True)
    for layout in ['layout_01','layout_04']:
        path=OUT/'predictions'/f'BASELINES__{layout}.json'
        if path.exists():
            continue
        train=[r for r in rows if r['partition']=='train' and r['layout_id']==layout]
        test=[r for r in rows if r['partition']=='test' and r['layout_id']==layout]
        cal=calibrate(train,info,det)
        save(OUT/'fits'/f'TRACKER__{layout}.json',cal)
        beta=fit_time_only([j+1 for r in train for j in range(19)],[r['direction'] for r in train for j in range(19)],[v for r in train for v in r['historical_FIR_reference_labels']])
        save(OUT/'fits'/f'METADATA__{layout}.json',dict(beta=beta.tolist(),training_identities=[r['identity'] for r in train],inputs=['direction','occlusion_age'],commanded_speed_used=False))
        cells=[]; coverage=[]
        for c in ['L0','L4']:
            for phase in (['correct','swapped','removed'] if c=='L4' else ['correct']):
                prediction=[]
                for row in test:
                    r=info[row['identity'],c]; ds=det[row['identity'],c]
                    donor=info[row['donor'],c]; dd=det[row['donor'],c]
                    for j,t in enumerate(r['target_model_frame_indices']):
                        if phase=='correct':
                            window=ds[t-15:t+1]
                        elif phase=='removed':
                            window=[ds[t]]*16
                        else:
                            td=donor['target_model_frame_indices'][j]
                            window=dd[td-15:td]+[ds[t]]
                        value,n=track(window,cal)
                        prediction.append(value)
                        coverage.append(dict(identity=row['identity'],condition=c,phase=phase,age=j+1,reliable_detections=n,fallback=n==0))
                cells.extend(make_cells(test,np.array(prediction),'IMAGE_TRACKER_CV',c,phase))
            models={k:[] for k in ['TRAINING_MEAN','DIRECTION_AGE','ORACLE_LAST_SEEN','ORACLE_CONSTANT_VELOCITY']}
            for row in test:
                r=info[row['identity'],c]
                models['TRAINING_MEAN'].extend([cal['target_mean']]*19)
                models['DIRECTION_AGE'].extend(predict_time_only(beta,list(range(1,20)),[row['direction']]*19))
                models['ORACLE_LAST_SEEN'].extend(last_seen(r['state_positions'],r['fully_occluded'],t) for t in r['target_model_frame_indices'])
                models['ORACLE_CONSTANT_VELOCITY'].extend(constant_velocity(r['state_positions'],r['fully_occluded'],t) for t in r['target_model_frame_indices'])
            for name,pred in models.items():
                cells.extend(make_cells(test,np.array(pred),name,c,'correct'))
        save(path,dict(cells=cells,tracker_coverage=coverage,tracker_calibration_sha256=sha(OUT/'fits'/f'TRACKER__{layout}.json'),oracle_input='Raw pre-occlusion server state, privileged, not history-window matched',tracker_input='Images only, exactly 16 frames, AIR-training-only target calibration'))
    print('BASELINES_COMPLETE',flush=True)


if __name__=='__main__':
    main()

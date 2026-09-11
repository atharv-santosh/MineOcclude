"""Independent frame/state/geometry diagnostics, not neural evaluation."""
import json
import math
from pathlib import Path
import sys
import numpy as np
from PIL import Image

SOURCE=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(SOURCE/'src'))
from mineocclude.experiment_iii.cohort import generate_path
from mineocclude.experiment_iii.fir import fir_labels
from mineocclude.experiment_iii.target_manifest import build_target_window
from plan_cohort import layout_config
ROOT=Path('/home/bpcfno/mineocclude-generalization-20260911')


def read(path):
    return json.loads(path.read_text())


def lines(path):
    return [json.loads(s) for s in path.read_text().splitlines()]


def measure(path):
    rgb=np.asarray(Image.open(path).convert('RGB')).astype(float)
    r,g,b=rgb.transpose(2,0,1)
    mask=(r>45)&(b>30)&(r>g*1.4)&(b>g*1.25)
    y,x=np.where(mask)
    return dict(area=len(x),u=float((x.min()+x.max())/2) if len(x) else None,v=float((y.min()+y.max())/2) if len(x) else None)


def audit(directory):
    spec=read(directory/'spec.json')
    state=lines(directory/'server/server_state.jsonl')
    ticks=lines(directory/'client/client_tick.jsonl')
    actions=lines(directory/'client/raw_actions.jsonl')
    physical=read(directory/'server/physical_receipt.json')
    frames=sorted((directory/'client/frames').glob('*.png'))
    assert len(state)==len(ticks)==len(actions)==len(frames)==180
    assert [r['server_tick'] for r in state]==list(range(180))
    assert [r['server_tick'] for r in ticks]==list(range(180))
    assert all(r['tick_queue_depth_at_capture']==0 for r in ticks)
    assert physical['wall']['mismatch_count']==0
    assert physical['target']['valid']
    expected,_=generate_path(spec['seed'],.05,direction=spec['direction'],start_world_x=spec['start_world_x'],speed=spec['speed_blocks_per_second'])
    observed=np.array([r['sheep_x'] for r in state])
    delta=float(np.max(np.abs(expected-observed)))
    assert delta<1e-9,delta
    camera=physical['camera']['observed']
    eye=[camera['feet_x'],camera['eye_y'],camera['feet_z']]
    layout=layout_config(spec['layout_id'])
    win=build_target_window(spec['identity'],spec['direction'],observed,layout=layout,camera=eye)
    measurements=[measure(f) for f in frames]
    label_indices=np.arange(15,180)
    labels=np.array(fir_labels(observed,label_indices.tolist(),spec['direction']))
    focal=180/math.tan(math.radians(35))
    estimated=np.array([.5-(m['u']-320)*(layout['wall_ortho_const']-eye[2])/focal if m['u'] is not None else np.nan for m in measurements])
    valid=np.isfinite(estimated[label_indices]) & (np.abs(observed[label_indices])<6)
    offsets=estimated[label_indices][valid]-labels[valid]
    result=dict(unit=directory.name,status='FRAME_STATE_CHECKS_PASS_ALIGNMENT_NOT_YET_QUALIFIED',exact_path_max_error=delta,camera=eye,condition=spec['condition_id'],layout=spec['layout_id'],speed=spec['speed_blocks_per_second'],target_indices=list(win.target_model_frame_indices),target_magenta_areas=[measurements[t]['area'] for t in win.target_model_frame_indices],historical_FIR_pixel_offset_median=float(np.median(offsets)) if len(offsets) else None,historical_FIR_pixel_centered_rmse=float(np.sqrt(np.mean((offsets-np.median(offsets))**2))) if len(offsets) else None,measurements=measurements)
    return result


if __name__=='__main__':
    reports=[]
    for directory in sorted((ROOT/'pilots').glob('*')):
        if (directory/'spec.json').exists():
            r=audit(directory)
            reports.append(r)
            print(json.dumps({k:v for k,v in r.items() if k!='measurements'}),flush=True)
    (ROOT/'pilot_audit.json').write_text(json.dumps(reports,indent=2,allow_nan=False)+'\n')

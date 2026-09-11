"""Exact legacy area resizing; 16 actual images per matched-history row."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('OMP_NUM_THREADS','1')
from concurrent.futures import ProcessPoolExecutor
import json
import time
import numpy as np
from PIL import Image
from audit_recovery import ROOT, PKG, OUT, read, save, sha
from mineocclude.experiment_iii.baselines_pixel import pixel_features


def build_unit(item):
    unit,info=item
    outputs=[OUT/'features'/m/f'{unit}.npy' for m in ('PIXEL_CURRENT','PIXEL_HISTORY16')]
    if all(p.exists() for p in outputs):
        return unit,'preserved'
    base=ROOT/'recovery_inputs/corpus/captures'/unit
    fmap={int(r['model_frame_idx'] if 'model_frame_idx' in r else r['render_frame_idx']):r for r in [json.loads(s) for s in (base/'raw/frame_map.jsonl').read_text().splitlines()]}
    targets=info['target_model_frame_indices']
    needed=sorted({t-k for t in targets for k in range(16)})
    features={}
    for t in needed:
        path=base/'raw/frames'/f'{fmap[t]["render_frame_idx"]:06d}.png'
        assert sha(path)==fmap[t]['frame_sha256']
        with Image.open(path) as image:
            frame=np.array(image.convert('RGB'))
        features[t]=pixel_features(frame)
    arrays=[np.stack([features[t] for t in targets]),np.stack([np.concatenate([features[k] for k in range(t-15,t+1)]) for t in targets])]
    assert arrays[0].shape==(19,4032) and arrays[1].shape==(19,64512)
    for path,array in zip(outputs,arrays):
        assert np.isfinite(array).all()
        path.parent.mkdir(parents=True,exist_ok=True)
        temp=path.with_suffix('.tmp.npy')
        np.save(temp,array,allow_pickle=False)
        temp.replace(path)
    return unit,'built'


if __name__=='__main__':
    audit=read(OUT/'recovery_audit.json')
    assert audit['unique_action_payloads']==1,'Nonconstant actions require revised history baseline'
    assert read(OUT/'corpus_audit.json')['status']=='FULL_CORPUS_VERIFIED'
    started=time.perf_counter()
    items=sorted(read(PKG/'cohort/CAPTURE_INDEX.json')['captures'].items())
    with ProcessPoolExecutor(max_workers=4) as pool:
        for i,result in enumerate(pool.map(build_unit,items)):
            print('PIXELS',i+1,125,*result,'seconds',round(time.perf_counter()-started,1),flush=True)
    save(OUT/'pixel_build_receipt.json',{'units':125,'rows':2375,'elapsed_seconds':time.perf_counter()-started,'history_frames':16,'action_payload_constant':True,'action_omission_reason':'All recorded model actions are identical; adding constant columns supplies no discriminative information.','resize':'Original float64 overlap-weighted area implementation','order':'time,row,column,channel','dimensions':{'PIXEL_CURRENT':4032,'PIXEL_HISTORY16':64512}})

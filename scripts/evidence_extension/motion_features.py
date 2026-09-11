from common import *
import argparse
import numpy as np
import cv2
import time
from PIL import Image
from central_features import store
from mineocclude.experiment_iii.baselines_pixel import pixel_features
from mineocclude.experiment_iii.extent_geometry import counterfactual_extent_classes

def info(row,c):
    base=ROOT/'captures'/f'{row["identity"]}__{c}'
    bank=read(base/'BANKED.json')
    assert bank['spec_hash']==row['spec_hash']
    assert all(sha(base/k)==v for k,v in bank['files'].items())
    state=[json.loads(s) for s in (base/'server/server_state.jsonl').read_text().splitlines()]
    ticks=[json.loads(s) for s in (base/'client/client_tick.jsonl').read_text().splitlines()]
    actions=[json.loads(s) for s in (base/'client/raw_actions.jsonl').read_text().splitlines()]
    assert len(state)==len(ticks)==len(actions)==180
    assert [r['server_tick'] for r in ticks]==list(range(180))
    assert all(r['tick_queue_depth_at_capture']==0 for r in ticks)
    assert np.max(abs(np.array([r['sheep_x'] for r in state])-row['state_positions']))<1e-9
    complete=read(base/'client/capture_complete.json')
    physical=read(base/'server/physical_receipt.json')
    assert complete['drained'] and complete['writer_errors']==0
    assert physical['wall']['mismatch_count']==0 and physical['target']['valid']
    needed=sorted({t-k for t in row['target_model_frame_indices'] for k in range(16)})
    raw={t:np.asarray(Image.open(base/'client/frames'/f'{t:06d}.png').convert('RGB')) for t in needed}
    areas={}
    for t,f in raw.items():
        r,g,b=f.astype(float).transpose(2,0,1)
        areas[t]=int(((r>45)&(b>30)&(r>1.4*g)&(b>1.25*g)).sum())
    for t in row['target_model_frame_indices']:
        area=areas[t]
        assert (area==0 if c=='L4' else area>20),(base,t,area)
    counts=[sum(areas[t-k]>20 for k in range(1,16)) for t in row['target_model_frame_indices']]
    assert c!='L4' or counts[0]>=3,(base,'Insufficient visible approach in production')
    return raw,actions,sha(base/'BANKED.json'),counts

def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['pixels','700M','300M','video'],required=True);p.add_argument('--watch',action='store_true');a=p.parse_args()
    rows=read(MOTION_ROSTER)['rows']
    assert read(ROOT/'MOTION_ADMISSION.json')['status']=='PASS'
    ext=None; video=None
    if a.mode in ('700M','300M'):
        import features_diag as f
        import extract_features as ex
        f.OUT=ROOT/'motion/model_receipts'
        ex.OUT=f.OUT/a.mode
        ext=f.Extractor(f.load(a.mode))
    elif a.mode=='video':
        from video_encoder import VideoEncoder
        video=VideoEncoder()
    started=time.monotonic()
    for n,row in enumerate(rows):
        for c in ['L0','L4']:
            unit=f'{row["identity"]}__{c}'
            receipt=ROOT/'motion/receipts'/f'{a.mode}__{unit}.json'
            if receipt.exists():
                rec=read(receipt)
                assert all(sha(ROOT/'motion/features'/model/f'{unit}.npy')==digest for model,digest in rec['features'].items())
                continue
            while not (ROOT/'captures'/unit/'BANKED.json').exists():
                assert a.watch,(unit,'capture absent')
                time.sleep(5)
            raw,actions,bank,visible_counts=info(row,c)
            indices=row['target_model_frame_indices']
            if ext:
                import extract_features as ex
                cache=ext.cached_tokens({t:ex.preprocess(f,'RGB') for t,f in raw.items()})
                act={}
                for t in raw:
                    official,_=ext.converter.json_action_to_env_action(ext.flat_converter(actions[t],prev_hotbar=None))
                    act[t]=ext.converter.get_action_index_from_actiondict(official,action_vocab_offset=8192)
                assert len({tuple(v) for v in act.values()})==1
                values={f'MW_{a.mode}':np.stack([ext.forward(np.stack([cache[k] for k in range(t-15,t+1)]),act,t)[19] for t in indices])}
            elif video:
                values={'VIDEOMAE_S':np.stack([video([raw[k] for k in range(t-15,t+1)]) for t in indices])}
            else:
                pix={t:pixel_features(f) for t,f in raw.items()}
                gray={t:cv2.cvtColor(cv2.resize(f,(96,56),interpolation=cv2.INTER_AREA),cv2.COLOR_RGB2GRAY) for t,f in raw.items()}
                flows={t:cv2.resize(cv2.calcOpticalFlowFarneback(gray[t-1],gray[t],None,.5,3,15,3,5,1.2,0),(24,14),interpolation=cv2.INTER_AREA).ravel().astype(float) for t in gray if t-1 in gray}
                values={'PIXEL_CURRENT':np.stack([pix[t] for t in indices]),'PIXEL_HISTORY16':np.stack([np.concatenate([pix[k] for k in range(t-15,t+1)]) for t in indices]),'FRAME_DIFF16':np.stack([np.concatenate([pix[t]]+[pix[k]-pix[k-1] for k in range(t-14,t+1)]) for t in indices]),'FLOW16':np.stack([np.concatenate([pix[t]]+[flows[k] for k in range(t-14,t+1)]) for t in indices])}
            hashes={}
            for model,v in values.items():
                path=ROOT/'motion/features'/model/f'{unit}.npy'
                store(path,v);hashes[model]=sha(path)
            save(receipt,dict(unit=unit,features=hashes,bank_sha256=bank,context=16,channel_order='RGB',indices=indices,visible_prior_counts=visible_counts,script_sha256=sha(Path(__file__))))
            print('MOTION_FEATURES',a.mode,n+1,len(rows),unit,round(time.monotonic()-started,1),flush=True)

if __name__=='__main__':main()

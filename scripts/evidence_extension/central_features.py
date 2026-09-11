from common import *
import argparse
import time
import numpy as np
import cv2
from PIL import Image
from mineocclude.experiment_iii.baselines_pixel import pixel_features
from mineocclude.experiment_iii.conditions import as_built_wall_cells
from plan_cohort import layout_config

cv2.setNumThreads(2)

def store(path,array):
    path.parent.mkdir(parents=True,exist_ok=True)
    assert not path.exists()
    assert np.isfinite(array).all()
    np.save(path,array,allow_pickle=False)

def images(unit,info):
    base=SOURCE/'recovery_inputs/corpus/captures'/unit/'raw'
    maps={int(r.get('model_frame_idx',r['render_frame_idx'])):r for r in [json.loads(s) for s in (base/'frame_map.jsonl').read_text().splitlines()]}
    needed=sorted({t-k for t in info['target_model_frame_indices'] for k in range(16)})
    result={}
    for t in needed:
        f=base/'frames'/f'{maps[t]["render_frame_idx"]:06d}.png'
        assert sha(f)==maps[t]['frame_sha256']
        result[t]=np.asarray(Image.open(f).convert('RGB'))
    return result

def opacity_assets():
    layout=layout_config('layout_01')
    cells=np.array(as_built_wall_cells(layout))
    lo=cells.min(0); hi=cells.max(0)+1
    vertices=np.array([[x,y,z] for x in (lo[0],hi[0]) for y in (lo[1],hi[1]) for z in (lo[2],hi[2])])
    focal=180/np.tan(np.deg2rad(35))
    points=np.column_stack([320-focal*(vertices[:,0]-.5)/(vertices[:,2]+5.5),180-focal*(vertices[:,1]-5.6200000048)/(vertices[:,2]+5.5)])
    mask=np.zeros((360,640),np.uint8)
    cv2.fillConvexPoly(mask,cv2.convexHull(np.rint(points).astype(np.int32)),1)
    reference=SOURCE/'recovery_inputs/corpus/captures/e3_t01__L4/raw/frames/000000.png'
    texture=np.asarray(Image.open(reference).convert('RGB'))
    r,g,b=texture.astype(float).transpose(2,0,1)
    assert not (((r>45)&(b>30)&(r>1.4*g)&(b>1.25*g)) & mask.astype(bool)).any()
    return mask.astype(bool),texture,dict(reference_sha256=sha(reference),polygon=np.rint(points).astype(int).tolist(),mask_sha256=hashlib.sha256(mask.tobytes()).hexdigest(),mask_area=int(mask.sum()),geometry_only=True)

def blend(frame,mask,texture,alpha):
    if alpha==0: return frame.copy()
    result=frame.copy()
    result[mask]=np.rint((1-alpha)*frame[mask].astype(float)+alpha*texture[mask]).astype(np.uint8)
    assert np.array_equal(result[~mask],frame[~mask])
    if alpha==1: assert np.array_equal(result[mask],texture[mask])
    return result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',choices=['baselines','video','opacity_pixels','opacity_mw'],required=True)
    args=parser.parse_args()
    index=read(SOURCE/'reproducibility/experiment_iii_a/cohort/CAPTURE_INDEX.json')['captures']
    root=ROOT/'central'
    start=time.monotonic()
    video=None; ext=None
    if args.mode=='video':
        from video_encoder import VideoEncoder
        video=VideoEncoder()
    if args.mode=='opacity_mw':
        import extract_features as ex
        from features_diag import Extractor
        ex.OUT=root/'opacity_model_receipts'
        ext=Extractor(ex.load_model())
    if args.mode.startswith('opacity'):
        mask,texture,receipt=opacity_assets()
        if not (root/'opacity_assets.json').exists(): save(root/'opacity_assets.json',receipt)
        items=[(u,i) for u,i in sorted(index.items()) if i['condition_id']=='L0']
    else: items=sorted(index.items())
    for unit,info in items:
        if args.mode=='baselines': models=['FRAME_DIFF16','FLOW16']
        elif args.mode=='video': models=['VIDEOMAE_S']
        else: models=['OPACITY_MW' if ext else 'OPACITY_PIXELS']
        levels=[0,.25,.5,.75,1] if args.mode.startswith('opacity') else [None]
        raw=None
        for level in levels:
            output_unit=f'{info["identity"]}__A{int(level*100):03d}' if level is not None else unit
            paths={m:root/'features'/m/f'{output_unit}.npy' for m in models}
            recpath=root/'receipts'/f'{args.mode}__{output_unit}.json'
            if recpath.exists():
                assert all(sha(p)==read(recpath)['features'][m] for m,p in paths.items())
                continue
            if raw is None: raw=images(unit,info)
            frames={t:blend(f,mask,texture,level) for t,f in raw.items()} if level is not None else raw
            if args.mode=='opacity_pixels':
                p={t:pixel_features(f) for t,f in frames.items()}
                values={models[0]:np.stack([np.concatenate([p[k] for k in range(t-15,t+1)]) for t in info['target_model_frame_indices']])}
            elif ext:
                import extract_features as ex
                _,actions=ext.frames(unit,info,'RGB')
                cache=ext.cached_tokens({t:ex.preprocess(f,'RGB') for t,f in frames.items()})
                values={models[0]:np.stack([ext.forward(np.stack([cache[k] for k in range(t-15,t+1)]),actions,t)[19] for t in info['target_model_frame_indices']])}
            elif video:
                values={models[0]:np.stack([video([frames[k] for k in range(t-15,t+1)]) for t in info['target_model_frame_indices']])}
            else:
                p={t:pixel_features(f) for t,f in frames.items()}
                gray={t:cv2.cvtColor(cv2.resize(f,(96,56),interpolation=cv2.INTER_AREA),cv2.COLOR_RGB2GRAY) for t,f in frames.items()}
                flow={}
                for t in sorted(gray):
                    if t-1 in gray:
                        f=cv2.calcOpticalFlowFarneback(gray[t-1],gray[t],None,.5,3,15,3,5,1.2,0)
                        flow[t]=cv2.resize(f,(24,14),interpolation=cv2.INTER_AREA).ravel().astype(np.float64)
                diffs=[]; flows=[]
                for t in info['target_model_frame_indices']:
                    diffs.append(np.concatenate([p[t]]+[p[k]-p[k-1] for k in range(t-14,t+1)]))
                    flows.append(np.concatenate([p[t]]+[flow[k] for k in range(t-14,t+1)]))
                values={'FRAME_DIFF16':np.stack(diffs),'FLOW16':np.stack(flows)}
            for m,path in paths.items(): store(path,values[m])
            extra={}
            if level is not None:
                inside=np.concatenate([(frames[t][mask].astype(float)-texture[mask]).ravel() for t in info['target_model_frame_indices']])
                extra=dict(opacity=level,inside_texture_rmse=float(np.sqrt(np.mean(inside**2))),mask_area=int(mask.sum()),outside_identical=all(np.array_equal(frames[t][~mask],raw[t][~mask]) for t in frames))
            save(recpath,dict(unit=unit,target_indices=info['target_model_frame_indices'],context=16,features={m:sha(p) for m,p in paths.items()},script_sha256=sha(Path(__file__)),**extra))
            print('FEATURES',args.mode,output_unit,round(time.monotonic()-start,1),flush=True)
    print('COMPLETE',args.mode,flush=True)

if __name__=='__main__': main()

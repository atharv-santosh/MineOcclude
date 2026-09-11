"""Fixed RGB features from verified fresh captures; no targets enter MineWorld."""
import argparse
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','4')
os.environ.setdefault('OMP_NUM_THREADS','4')
import json
from pathlib import Path
import sys
import time
import numpy as np
from PIL import Image
from prepare import ROOT,SOURCE,read,lines,save,sha
sys.path.insert(0,str(SOURCE/'scripts/rgb_replication'))
import extract_features as ex
from mineocclude.experiment_iii.baselines_pixel import pixel_features

OUT=ROOT/'analysis'


def store(path,array):
    path.parent.mkdir(parents=True,exist_ok=True)
    assert not path.exists(),path
    tmp=path.with_suffix('.tmp.npy')
    np.save(tmp,array,allow_pickle=False)
    tmp.replace(path)


def frames(info):
    needed=sorted({t-k for t in info['target_model_frame_indices'] for k in range(16)})
    base=ROOT/'captures'/info['unit']
    bank=read(base/'BANKED.json')
    result={}
    for t in needed:
        rel=f'client/frames/{t:06d}.png'
        assert sha(base/rel)==bank['files'][rel]
        result[t]=np.asarray(Image.open(base/rel).convert('RGB'))
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',choices=['pixels','mineworld'],required=True)
    args=parser.parse_args()
    manifest=read(ROOT/'manifest.json')
    assert manifest['status']=='ALL_150_VERIFIED'
    items=sorted(manifest['units'].items())
    started=time.monotonic()
    if args.mode=='mineworld':
        ex.OUT=OUT
        model=ex.load_model()
        ext=ex.Extractor(model)
        boundary=[]
        handle=model.tokenizer.model.encoder.register_forward_pre_hook(lambda module,inputs: boundary.append(inputs[0].detach().cpu().numpy()))
        for channel in (0,2):
            patch=np.zeros((360,640,3),dtype=np.uint8)
            patch[:,:,channel]=255
            expected=ex.preprocess(patch,'RGB')
            ext.tokens([expected]*16)
            assert np.array_equal(boundary[-1],np.stack([expected]*16))
        handle.remove()
        del boundary
        save(OUT/'encoder_boundary_validation.json',dict(red_patch='PASS',blue_patch='PASS',verified_at='actual tokenizer encoder input',order='RGB'))
    for n,(unit,info) in enumerate(items):
        models=['PIXEL_CURRENT','PIXEL_HISTORY16'] if args.mode=='pixels' else ['MW_RGB_L19']
        paths={m:OUT/'features'/m/f'{unit}.npy' for m in models}
        if all(p.exists() for p in paths.values()):
            receipt=read(OUT/'feature_receipts'/f'{args.mode}__{unit}.json')
            assert receipt['capture_bank_sha256']==info['bank_sha256']
            assert all(sha(p)==receipt['features'][m] for m,p in paths.items())
            print('PRESERVED',args.mode,unit,flush=True)
            continue
        raw=frames(info)
        targets=info['target_model_frame_indices']
        if args.mode=='pixels':
            current={t:pixel_features(rgb) for t,rgb in raw.items()}
            store(paths['PIXEL_CURRENT'],np.stack([current[t] for t in targets]))
            store(paths['PIXEL_HISTORY16'],np.stack([np.concatenate([current[k] for k in range(t-15,t+1)]) for t in targets]))
        else:
            visual={t:ex.preprocess(rgb,'RGB') for t,rgb in raw.items()}
            recorded=lines(ROOT/'captures'/unit/'client/raw_actions.jsonl')
            actions={}
            for t in visual:
                official,_=ext.converter.json_action_to_env_action(ext.flat_converter(recorded[t],prev_hotbar=None))
                actions[t]=ext.converter.get_action_index_from_actiondict(official,action_vocab_offset=8192)
                assert len(actions[t])==11
            assert len({tuple(a) for a in actions.values()})==1
            cache=ext.cached_tokens(visual)
            for t in (targets[0],targets[-1]):
                full=ext.tokens([visual[k] for k in range(t-15,t+1)])
                assert np.array_equal(full,np.stack([cache[k] for k in range(t-15,t+1)])),('Token-cache mismatch',unit,t)
            outputs=[]
            for t in targets:
                tokens=np.stack([cache[k] for k in range(t-15,t+1)])
                result=ext.forward(tokens,actions,t)
                outputs.append(result[19])
                if n==0 and t==targets[0]:
                    again=ext.forward(tokens,actions,t)
                    assert np.array_equal(result[19],again[19]),'Reset-repeat mismatch'
            array=np.stack(outputs)
            assert array.shape==(19,24576) and np.isfinite(array).all()
            store(paths['MW_RGB_L19'],array)
        save(OUT/'feature_receipts'/f'{args.mode}__{unit}.json',dict(unit=unit,features={m:sha(p) for m,p in paths.items()},capture_bank_sha256=info['bank_sha256'],targets=list(targets),context_pairs=16,order='RGB',no_target_or_metadata_inputs=True))
        print('FEATURES',args.mode,n+1,150,unit,round(time.monotonic()-started,1),flush=True)
    memory={} if args.mode=='pixels' else dict(peak_allocated_bytes=ext.torch.cuda.max_memory_allocated(),peak_reserved_bytes=ext.torch.cuda.max_memory_reserved())
    save(OUT/f'{args.mode}_complete.json',dict(units=150,target_windows=2850,elapsed_seconds=time.monotonic()-started,manifest_sha256=sha(ROOT/'manifest.json'),source_sha256=sha(Path(__file__)),**memory))


if __name__=='__main__':
    main()

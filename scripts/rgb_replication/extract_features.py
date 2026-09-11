"""New RGB follow-up using pinned upstream modules and verified original inputs."""
import argparse
import gc
import os
import subprocess
import sys
import time
from pathlib import Path
os.environ.setdefault('OMP_NUM_THREADS','4')
os.environ.setdefault('OPENBLAS_NUM_THREADS','4')
os.environ.setdefault('TORCH_FORCE_WEIGHTS_ONLY_LOAD','1')
import numpy as np
from PIL import Image
from audit_recovery import ROOT, PKG, OUT, read, save, sha


def preprocess(frame,order):
    import cv2
    if order=='BGR':
        frame=frame[:,:,::-1]
    resized=cv2.resize(np.ascontiguousarray(frame),(384,224),interpolation=cv2.INTER_LINEAR)
    return np.ascontiguousarray((resized.transpose(2,0,1).astype(np.float32)/np.float32(255)-np.float32(.5))/np.float32(.5))


def test_preprocess():
    from mineocclude.models._mineworld_adapter_wave2 import _preprocess_bgr_frame
    red=np.zeros((360,640,3),np.uint8)
    red[:,:,0]=255
    blue=red[:,:,::-1].copy()
    assert np.array_equal(preprocess(red,'RGB')[:,0,0],[1,-1,-1])
    assert np.array_equal(preprocess(blue,'RGB')[:,0,0],[-1,-1,1])
    rng=np.random.default_rng(71)
    fixture=rng.integers(0,256,(360,640,3),dtype=np.uint8)
    assert np.array_equal(preprocess(fixture,'BGR'),_preprocess_bgr_frame(fixture)[0])
    assert np.array_equal(preprocess(fixture,'RGB'),_preprocess_bgr_frame(fixture[:,:,::-1].copy())[0])
    return {'red_patch':'PASS','blue_patch':'PASS','legacy_reference_bitwise':'PASS','only_change':'Channel swap omitted for decoded RGB input'}


def load_model():
    import torch
    from omegaconf import OmegaConf
    from omegaconf import DictConfig, ListConfig
    from omegaconf.base import ContainerMetadata, Metadata
    from omegaconf.nodes import AnyNode
    from collections import defaultdict
    from typing import Any
    # The hash-pinned VAE carries an OmegaConf training configuration alongside
    # its tensors. Permit only these inspected container classes, not arbitrary
    # checkpoint globals or unrestricted pickle loading.
    torch.serialization.add_safe_globals([DictConfig,ListConfig,ContainerMetadata,Metadata,AnyNode,defaultdict,Any,list,dict,int])
    source=ROOT/'recovery_inputs/MineWorld-Upstream'
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()
    assert revision=='9f49efbcc68a5f0cf60e78f0abc566eac409282f'
    weights=Path(os.environ.get('MINEOCCLUDE_WEIGHTS',str(ROOT/'recovery_inputs/weights')))
    main_path=weights/'700M_16f.verified.ckpt'
    vae_path=weights/'vae.verified.ckpt'
    provenance=read(PKG/'provenance/MODEL_PROVENANCE.json')
    for path,key in [(main_path,'main_checkpoint'),(vae_path,'vae_checkpoint'),(weights/'config.json','vae_config')]:
        assert sha(path)==provenance[key]['sha256'],path.name
    import hashlib
    config_blob=subprocess.check_output(['git','show','HEAD:configs/700M_16f.yaml'],cwd=source)
    assert hashlib.sha256(config_blob).hexdigest()==provenance['model_config']['sha256']
    assert (source/'configs/700M_16f.yaml').read_bytes().replace(b'\r\n',b'\n')==config_blob
    sys.path.insert(0,str(source))
    from utils import instantiate_from_config
    config=OmegaConf.load(source/'configs/700M_16f.yaml')
    config.model.params.tokenizer_config.params.config_path=str(weights/'config.json')
    config.model.params.tokenizer_config.params.ckpt_path=str(vae_path)
    model=instantiate_from_config(config.model)
    payload=torch.load(main_path,map_location='cpu',weights_only=True)
    state=payload.get('state_dict',payload)
    missing,unexpected=model.load_state_dict(state,strict=False)
    del state,payload
    payload=torch.load(vae_path,map_location='cpu',weights_only=True)
    missing_vae,unexpected_vae=model.tokenizer.load_state_dict(payload.get('state_dict',payload),strict=False)
    from mineocclude.models.phase2_evidence import classify_checkpoint_load_state
    load_state={'transformer_missing_keys':list(missing),'transformer_unexpected_keys':list(unexpected),'vae_missing_keys':list(missing_vae),'vae_unexpected_keys':list(unexpected_vae)}
    classification=classify_checkpoint_load_state(load_state,{'source_revision':revision,'asset_revision':provenance['modelscope_asset_revision'],'main_checkpoint_sha256':provenance['main_checkpoint']['sha256'],'vae_checkpoint_sha256':provenance['vae_checkpoint']['sha256']})
    assert classification['final_decision']=='PASS',classification
    save(OUT/'checkpoint_load_validation.json',{'load_state':load_state,'classification':classification})
    del payload
    model.cuda().to(dtype=torch.float16).eval()
    model.requires_grad_(False)
    gc.collect()
    report={'torch':torch.__version__,'cuda':torch.version.cuda,'gpu':torch.cuda.get_device_name(),'capability':torch.cuda.get_device_capability(),'python':sys.version,'upstream_revision':revision,'precision':'float16','main_missing_keys':len(missing),'main_training_only_extra_keys':len(unexpected),'vae_missing_keys':len(missing_vae),'vae_training_only_extra_keys':len(unexpected_vae),'load_classification':classification['final_decision'],'preprocess':test_preprocess(),'script_sha256':sha(Path(__file__))}
    save(OUT/'runtime_validation.json',report)
    print('MODEL_LOADED',report,flush=True)
    return model


class Extractor:
    def __init__(self,model):
        import torch
        from mcdataset import MCDataset
        from mineocclude.data.convert_mineworld import flat_to_official_raw_action
        self.model=model
        self.torch=torch
        self.converter=MCDataset()
        self.converter.make_action_vocab(action_vocab_offset=8192)
        self.flat_converter=flat_to_official_raw_action
        self.captured={}
        self.pool_checked=False
        self.handles=[]
        for layer in (4,10,19):
            self.handles.append(model.transformer.model.layers[layer].register_forward_hook(self.hook(layer)))

    def hook(self,layer):
        def capture(module,args,output):
            x=output[0,-347:-11,:].detach()
            assert x.shape==(336,2048)
            # Preserve the original binary64 CPU summation exactly. GPU means
            # differed by rounding in validation, so that optimization is not used.
            from mineocclude.experiment_iii.representations import coarse_2x6_concat
            self.captured[layer]=coarse_2x6_concat(x.cpu().numpy())
            self.pool_checked=True
        return capture

    def frames(self,unit,info,order):
        import json
        base=ROOT/'recovery_inputs/corpus/captures'/unit
        rows=[json.loads(s) for s in (base/'raw/frame_map.jsonl').read_text().splitlines()]
        maps={int(r['render_frame_idx']):r for r in rows}
        actions={int(r['render_frame_idx']):r for r in [json.loads(s) for s in (base/'raw/actions.jsonl').read_text().splitlines()]}
        needed=sorted({t-k for t in info['target_model_frame_indices'] for k in range(16)})
        frames={}
        for t in needed:
            path=base/'raw/frames'/f'{t:06d}.png'
            assert sha(path)==maps[t]['frame_sha256']
            with Image.open(path) as im:
                raw=np.array(im.convert('RGB'))
            frames[t]=preprocess(raw,order)
        act={}
        for t in needed:
            raw=self.flat_converter(actions[t],prev_hotbar=None)
            official,_=self.converter.json_action_to_env_action(raw)
            act[t]=self.converter.get_action_index_from_actiondict(official,action_vocab_offset=8192)
            assert len(act[t])==11
        assert len({tuple(a) for a in act.values()})==1
        return frames,act

    def tokens(self,frames):
        torch=self.torch
        array=np.stack(frames)
        tensor=torch.from_numpy(array).cuda()
        assert tuple(tensor.shape)==(16,3,224,384)
        assert tensor.dtype==torch.float32
        with torch.no_grad(),torch.autocast('cuda',dtype=torch.float16):
            token=self.model.tokenizer.tokenize_images(tensor)
        token=token.reshape(16,336).cpu().numpy()
        assert token.min()>=0 and token.max()<8192
        return token

    def cached_tokens(self,frames):
        keys=sorted(frames)
        cache={}
        for start in range(0,len(keys),16):
            ids=keys[start:start+16]
            padded=ids+[ids[-1]]*(16-len(ids))
            encoded=self.tokens([frames[t] for t in padded])
            cache.update({t:encoded[j] for j,t in enumerate(ids)})
        return cache

    def forward(self,visual,actions,t,pairs=16):
        torch=self.torch
        ids=np.concatenate([np.concatenate([visual[j],actions[k]]) for j,k in enumerate(range(t-pairs+1,t+1))])
        assert ids.shape==(347*pairs,)
        self.captured.clear()
        self.model.transformer.refresh_kvcache()
        with torch.inference_mode(),torch.autocast('cuda',dtype=torch.float16):
            output=self.model.transformer(input_ids=torch.tensor(ids[None,:],device='cuda',dtype=torch.long),position_ids=torch.arange(347*pairs,device='cuda'))
        del output
        torch.cuda.synchronize()
        assert set(self.captured)=={4,10,19}
        return {k:v.copy() for k,v in self.captured.items()}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--profile',action='store_true')
    parser.add_argument('--order',choices=['RGB','BGR'],default='RGB')
    parser.add_argument('--pairs',type=int,choices=[1,8,16],default=16)
    args=parser.parse_args()
    assert read(OUT/'corpus_audit.json')['status']=='FULL_CORPUS_VERIFIED'
    model=load_model()
    ext=Extractor(model)
    items=sorted(read(PKG/'cohort/CAPTURE_INDEX.json')['captures'].items())
    started=time.perf_counter()
    if args.profile:
        boundary=[]
        handle=model.tokenizer.model.encoder.register_forward_pre_hook(lambda module,inputs: boundary.append(inputs[0].detach().cpu().numpy()))
        for channel in (0,2):
            patch=np.zeros((360,640,3),dtype=np.uint8)
            patch[:,:,channel]=255
            expected=preprocess(patch,args.order)
            ext.tokens([expected]*16)
            assert np.array_equal(boundary[-1],np.stack([expected]*16))
        handle.remove()
        del boundary
        checks=[]
        first_direction=items[0][1]['direction']
        other_identity=next(info['identity'] for _,info in items if info['direction']!=first_direction)
        profile_items=items[:5]+[(unit,info) for unit,info in items if info['identity']==other_identity]
        for n,(unit,info) in enumerate(profile_items):
            frames,actions=ext.frames(unit,info,args.order)
            cache=ext.cached_tokens(frames)
            for j in ((0,5,10,18) if n<5 else (0,18)):
                t=info['target_model_frame_indices'][j]
                model.cuda()
                ext.torch.cuda.synchronize()
                before=time.perf_counter()
                full=ext.tokens([frames[k] for k in range(t-15,t+1)])
                cached=np.stack([cache[k] for k in range(t-15,t+1)])
                equal=np.array_equal(full,cached)
                a=ext.forward(full,actions,t)
                elapsed=time.perf_counter()-before
                b=ext.forward(full,actions,t)
                delta=max(float(abs(a[k]-b[k]).max()) for k in a)
                assert delta==0,('reset-repeat failed',delta)
                if j==0:
                    changed=dict(actions)
                    changed[t]=[8192]*11
                    future=ext.forward(full,changed,t)
                    assert all(np.array_equal(a[k],future[k]) for k in a),'Future action leakage'
                checks.append({'unit':unit,'row_index':j,'cached_tokens_equal':equal,'repeat_max_abs_error':delta,'uncached_window_seconds':elapsed})
                print('PROFILE',checks[-1],flush=True)
        short_times={}
        for pairs in (1,8):
            before=time.perf_counter()
            short=ext.forward(full[-pairs:],actions,t,pairs=pairs)
            repeated=ext.forward(full[-pairs:],actions,t,pairs=pairs)
            assert all(np.array_equal(short[k],repeated[k]) for k in short)
            short_times[str(pairs)]=(time.perf_counter()-before)/2
        receipt={'checks':checks,'cache_allowed':all(c['cached_tokens_equal'] for c in checks),'profile_seconds':time.perf_counter()-started,'mean_uncached_window_seconds':float(np.mean([c['uncached_window_seconds'] for c in checks])),'maximum_gpu_allocated_bytes':ext.torch.cuda.max_memory_allocated(),'order':args.order,'actual_encoder_input_patch_checks':'PASS','pooling':'Original CPU binary64 implementation; GPU mean optimization rejected due to rounding differences','future_action_invariance':'PASS','short_context_seconds':short_times,'script_sha256':sha(Path(__file__))}
        save(OUT/f'profile_{args.order}.json',receipt)
        return
    profile=read(OUT/f'profile_{args.order}.json')
    if args.pairs!=16:
        items=[(u,i) for u,i in items if i['condition_id'] in ('L0','L4')]
    suffix='' if args.pairs==16 else f'_CTX{args.pairs}'
    for n,(unit,info) in enumerate(items):
        outputs={layer:OUT/'features'/f'MW_{args.order}_L{layer:02d}{suffix}'/f'{unit}.npy' for layer in (4,10,19)}
        if all(p.exists() for p in outputs.values()):
            print('PRESERVED',unit,flush=True)
            continue
        before=time.perf_counter()
        frames,actions=ext.frames(unit,info,args.order)
        cache=ext.cached_tokens(frames) if profile['cache_allowed'] else None
        results={k:[] for k in outputs}
        for t in info['target_model_frame_indices']:
            visual=np.stack([cache[k] for k in range(t-15,t+1)]) if cache is not None else ext.tokens([frames[k] for k in range(t-15,t+1)])
            features=ext.forward(visual[-args.pairs:],actions,t,pairs=args.pairs)
            for layer in results:
                results[layer].append(features[layer])
        hashes={}
        for layer,path in outputs.items():
            array=np.stack(results[layer])
            assert array.shape==(19,24576) and np.isfinite(array).all()
            path.parent.mkdir(parents=True,exist_ok=True)
            temp=path.with_suffix('.tmp.npy')
            np.save(temp,array,allow_pickle=False)
            temp.replace(path)
            hashes[str(layer)]=sha(path)
        save(OUT/'extraction_receipts'/f'{args.order}{suffix}__{unit}.json',{'unit':unit,'rows':19,'seconds':time.perf_counter()-before,'hashes':hashes,'target_frames':info['target_model_frame_indices'],'cached':cache is not None,'context_pairs':args.pairs,'protocol_sha256':sha(Path(__file__).parent/'PROTOCOL.md'),'script_sha256':sha(Path(__file__))})
        print('EXTRACTED',args.order,n+1,125,unit,'unit_seconds',round(time.perf_counter()-before,1),'total_seconds',round(time.perf_counter()-started,1),flush=True)
    save(OUT/f'extraction_{args.order}{suffix}_complete.json',{'units':len(items),'rows':len(items)*19,'seconds':time.perf_counter()-started,'order':args.order,'layers':[4,10,19],'context_pairs':args.pairs})


if __name__=='__main__':
    main()

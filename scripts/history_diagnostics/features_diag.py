import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','4')
os.environ.setdefault('OMP_NUM_THREADS','4')
os.environ.setdefault('TORCH_FORCE_WEIGHTS_ONLY_LOAD','1')
from diag_common import *
import argparse
import gc
import subprocess
import time
import numpy as np
from PIL import Image
import extract_features as ex
import prepare as inherited
from mineocclude.experiment_iii.baselines_pixel import pixel_features

OUT=ROOT/'analysis'


def store(path,array):
    path.parent.mkdir(parents=True,exist_ok=True)
    assert not path.exists(),path
    tmp=path.with_suffix('.tmp.npy')
    np.save(tmp,array,allow_pickle=False)
    tmp.replace(path)


def get_info(row,c,pilot=False):
    unit=f"{row['identity']}__{c}"
    directory=ROOT/('pilots' if pilot else 'captures')/unit
    inherited.ROOT=ROOT
    path=ROOT/'verified_units'/f'{unit}.json'
    if path.exists():
        info=read(path)
        assert info['bank_sha256']==sha(directory/'BANKED.json')
        return info
    return inherited.verify(directory,row)


def frames(info,pilot=False):
    directory=ROOT/('pilots' if pilot else 'captures')/info['unit']
    bank=read(directory/'BANKED.json')
    needed=sorted({t-k for t in info['target_model_frame_indices'] for k in range(16)})
    result={}
    for t in needed:
        rel=f'client/frames/{t:06d}.png'
        assert sha(directory/rel)==bank['files'][rel]
        with Image.open(directory/rel) as image:
            result[t]=np.asarray(image.convert('RGB'))
    return result


def load(model_size):
    ex.OUT=OUT/model_size
    if model_size=='700M':
        return ex.load_model()
    import torch
    from omegaconf import OmegaConf,DictConfig,ListConfig
    from omegaconf.base import ContainerMetadata,Metadata
    from omegaconf.nodes import AnyNode
    from collections import defaultdict
    from typing import Any
    torch.serialization.add_safe_globals([DictConfig,ListConfig,ContainerMetadata,Metadata,AnyNode,defaultdict,Any,list,dict,int])
    source=SOURCE/'recovery_inputs/MineWorld-Upstream'
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()
    assert revision=='9f49efbcc68a5f0cf60e78f0abc566eac409282f'
    sys.path.insert(0,str(source))
    from utils import instantiate_from_config
    weights=Path(os.environ['MINEOCCLUDE_WEIGHTS'])
    main=ROOT/'weights/300M_16f.verified.ckpt'
    assert sha(main)=='ab3a10cdd18373b26e60debb70112f4a190ae56559f906829ffb94ad9fdce0ff'
    vae=weights/'vae.verified.ckpt'
    assert sha(vae)=='370d06be427e034476b6b95ba0080a4b48266e876c4776a757b944b87b87d9ab'
    config_blob=subprocess.check_output(['git','show','HEAD:configs/300M_16f.yaml'],cwd=source)
    assert (source/'configs/300M_16f.yaml').read_bytes().replace(b'\r\n',b'\n')==config_blob
    config=OmegaConf.load(source/'configs/300M_16f.yaml')
    config.model.params.tokenizer_config.params.config_path=str(weights/'config.json')
    config.model.params.tokenizer_config.params.ckpt_path=str(vae)
    model=instantiate_from_config(config.model)
    payload=torch.load(main,map_location='cpu',weights_only=True)
    missing,unexpected=model.load_state_dict(payload.get('state_dict',payload),strict=False)
    del payload
    payload=torch.load(vae,map_location='cpu',weights_only=True)
    vm,vu=model.tokenizer.load_state_dict(payload.get('state_dict',payload),strict=False)
    del payload
    state=dict(transformer_missing_keys=list(missing),transformer_unexpected_keys=list(unexpected),vae_missing_keys=list(vm),vae_unexpected_keys=list(vu))
    expected=read(PREVIOUS/'analysis/checkpoint_load_validation.json')['load_state']
    save(OUT/model_size/'checkpoint_load_observed.json',state)
    assert all(sorted(state[k])==sorted(expected[k]) for k in state), 'Secondary checkpoint key profile differs: inspect before proceeding'
    assert not missing and not vm
    assert len(model.transformer.model.layers)==20
    save(OUT/model_size/'checkpoint_load_validation.json',dict(status='PASS',load_state=state,main_sha256=sha(main),vae_sha256=sha(vae),config_sha256=hashlib.sha256(config_blob).hexdigest(),upstream_revision=revision,validation='Every inference parameter loaded; exact training-only extra-key sets match inspected upstream profile',preprocess=ex.test_preprocess()))
    model.cuda().to(dtype=torch.float16).eval().requires_grad_(False)
    gc.collect()
    return model


class Extractor(ex.Extractor):
    def hook(self,layer):
        def capture(module,args,output):
            x=output[0,-347:-11,:].detach()
            assert x.shape[0]==336 and x.shape[1] in (1024,2048)
            from mineocclude.experiment_iii.representations import coarse_2x6_concat
            self.captured[layer]=coarse_2x6_concat(x.cpu().numpy())
        return capture


def action_tokens(ext,info,pilot=False):
    base=ROOT/('pilots' if pilot else 'captures')/info['unit']
    recorded=lines(base/'client/raw_actions.jsonl')
    result={}
    for t in range(180):
        official,_=ext.converter.json_action_to_env_action(ext.flat_converter(recorded[t],prev_hotbar=None))
        result[t]=ext.converter.get_action_index_from_actiondict(official,action_vocab_offset=8192)
    assert len({tuple(a) for a in result.values()})==1
    return result


def encode(ext,info,raw):
    visual={t:ex.preprocess(rgb,'RGB') for t,rgb in raw.items()}
    cache=ext.cached_tokens(visual)
    for t in (info['target_model_frame_indices'][0],info['target_model_frame_indices'][-1]):
        full=ext.tokens([visual[k] for k in range(t-15,t+1)])
        assert np.array_equal(full,np.stack([cache[k] for k in range(t-15,t+1)])),('Token cache mismatch',info['unit'])
    return cache


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',choices=['pixels','700M','300M'],required=True)
    parser.add_argument('--profile',action='store_true')
    parser.add_argument('--watch',action='store_true')
    args=parser.parse_args()
    roster=read(ROOT/'roster.json')
    assert roster['protocol_sha256']==sha(Path(__file__).parent/'PROTOCOL.md')
    rows=roster['pilots' if args.profile else 'identities']
    by_id={r['identity']:r for r in rows}
    started=time.monotonic()
    ext=None
    if args.mode!='pixels':
        model=load(args.mode)
        ext=Extractor(model)
        boundary=[]
        handle=model.tokenizer.model.encoder.register_forward_pre_hook(lambda module,inputs: boundary.append(inputs[0].detach().cpu().numpy()))
        for channel in [0,2]:
            patch=np.zeros((360,640,3),np.uint8)
            patch[:,:,channel]=255
            expected=ex.preprocess(patch,'RGB')
            ext.tokens([expected]*16)
            assert np.array_equal(boundary[-1],np.stack([expected]*16))
        handle.remove()
        del boundary
        save(OUT/args.mode/'encoder_boundary_validation.json',dict(status='PASS',actual_encoder_input='RGB',patches=['red','blue']))
    if args.profile:
        assert ext is not None
        row=rows[0]
        info=get_info(row,'L4',True)
        raw=frames(info,True)
        cache=encode(ext,info,raw)
        actions=action_tokens(ext,info,True)
        t=info['target_model_frame_indices'][0]
        tok=np.stack([cache[k] for k in range(t-15,t+1)])
        a=ext.forward(tok,actions,t)[19]
        b=ext.forward(tok,actions,t)[19]
        assert np.array_equal(a,b)
        altered=dict(actions)
        altered[t]=[8192]*11
        assert np.array_equal(a,ext.forward(tok,altered,t)[19])
        save(OUT/args.mode/'pilot_profile.json',dict(status='PASS',repeat_bitwise=True,future_action_invariance=True,shape=list(a.shape),seconds=time.monotonic()-started))
        print('PROFILE_PASS',args.mode,flush=True)
        return
    phases=['correct','swapped','removed']
    count=0
    for phase in phases:
        for row in rows:
            if phase!='correct' and row['partition']!='test':
                continue
            for c in (['L0','L4'] if phase=='correct' else ['L4']):
                unit=f"{row['identity']}__{c}"
                names=['PIXEL_CURRENT','PIXEL_HISTORY16'] if args.mode=='pixels' else [f'MW_{args.mode}']
                paths={m:OUT/'features'/m/phase/f'{unit}.npy' for m in names}
                receipt=OUT/'feature_receipts'/f'{args.mode}__{phase}__{unit}.json'
                if receipt.exists():
                    r=read(receipt)
                    assert all(sha(p)==r['features'][m] for m,p in paths.items())
                    continue
                needed=[unit]
                if phase=='swapped':
                    needed.append(f"{row['donor']}__L4")
                while not all((ROOT/'captures'/u/'BANKED.json').exists() for u in needed):
                    assert args.watch,('Capture not ready',needed)
                    time.sleep(5)
                info=get_info(row,c)
                raw=frames(info)
                donor=get_info(by_id[row['donor']],c) if phase=='swapped' else None
                donor_raw=frames(donor) if donor else None
                if ext:
                    cache=encode(ext,info,raw)
                    donor_cache=encode(ext,donor,donor_raw) if donor else None
                    actions=action_tokens(ext,info)
                else:
                    cache={t:pixel_features(rgb) for t,rgb in raw.items()}
                    donor_cache={t:pixel_features(rgb) for t,rgb in donor_raw.items()} if donor else None
                outputs={m:[] for m in names}
                evidence=[]
                for j,t in enumerate(info['target_model_frame_indices']):
                    if phase=='correct':
                        history=[cache[k] for k in range(t-15,t+1)]
                    elif phase=='removed':
                        history=[cache[t]]*16
                    else:
                        td=donor['target_model_frame_indices'][j]
                        history=[donor_cache[k] for k in range(td-15,td)]+[cache[t]]
                    assert np.array_equal(history[-1],cache[t])
                    if ext:
                        outputs[names[0]].append(ext.forward(np.stack(history),actions,t)[19])
                    else:
                        outputs['PIXEL_CURRENT'].append(history[-1])
                        outputs['PIXEL_HISTORY16'].append(np.concatenate(history))
                    record=dict(age=j+1,recipient_frame=t,recipient_nonfull_frames=sum(not info['fully_occluded'][k] for k in range(t-15,t+1)))
                    if donor:
                        record.update(donor_frame=td,donor_nonfull_frames=sum(not donor['fully_occluded'][k] for k in range(td-15,td)),current_pair_pixel_mae=float(np.abs(raw[t].astype(float)-donor_raw[td]).mean()))
                        if j>=15:
                            assert record['recipient_nonfull_frames']==record['donor_nonfull_frames']==0
                    evidence.append(record)
                for m,p in paths.items():
                    array=np.stack(outputs[m])
                    assert array.shape[0]==19 and np.isfinite(array).all()
                    store(p,array)
                save(receipt,dict(unit=unit,phase=phase,donor=row['donor'] if donor else None,features={m:sha(p) for m,p in paths.items()},capture_bank_sha256=info['bank_sha256'],donor_bank_sha256=donor['bank_sha256'] if donor else None,evidence=evidence,order='RGB',context_pairs=16,labels_enter_features=False,script_sha256=sha(Path(__file__))))
                count+=1
                print('FEATURES',args.mode,phase,count,unit,round(time.monotonic()-started,1),flush=True)
    save(OUT/f'{args.mode}_complete.json',dict(status='PASS',units=288,seconds=time.monotonic()-started,roster_sha256=sha(ROOT/'roster.json'),script_sha256=sha(Path(__file__))))


if __name__=='__main__':
    main()

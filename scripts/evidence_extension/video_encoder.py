from common import *
import numpy as np
from PIL import Image
import torch
import subprocess
from functools import partial

class VideoEncoder:
    def __init__(self):
        vendor=ROOT/'vendor/VideoMAE'
        assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=vendor,text=True).strip()=='14ef8d856287c94ef1f985fe30f958eb4ec2c55d'
        sys.path.insert(0,str(vendor))
        from modeling_pretrain import PretrainVisionTransformerEncoder
        self.model=PretrainVisionTransformerEncoder(embed_dim=384,depth=12,num_heads=6,qkv_bias=True,norm_layer=partial(torch.nn.LayerNorm,eps=1e-6),init_values=0.)
        path=ROOT/'vendor/videomae_small_k400_pretrain.pth'
        payload=torch.load(path,map_location='cpu',weights_only=True)
        state=payload.get('model',payload)
        encoder={k[len('encoder.'):]:v for k,v in state.items() if k.startswith('encoder.')}
        self.model.load_state_dict(encoder,strict=True)
        self.model.eval().requires_grad_(False).cuda()
        self.hash=sha(path)
        receipt=ROOT/'videomae_provenance.json'
        if not receipt.exists():
            save(receipt,dict(source='https://github.com/MCG-NJU/VideoMAE',revision='14ef8d856287c94ef1f985fe30f958eb4ec2c55d',checkpoint_url='https://drive.google.com/file/d/1nU-H1u3eJ-VuyCveU7v-WIOcAVxs5Hww/view',sha256=self.hash,bytes=path.stat().st_size,license='CC-BY-NC-4.0; noncommercial academic research',load='weights_only=True, every encoder tensor strict',pretraining='Kinetics-400 self-supervised 1600 epochs; no classification fine-tuning',representation='Final normalized tokens, mean over 8 temporal tubelets then adaptive 2x6 spatial means; 4608 dimensions',preprocess='Full-field RGB bicubic resize 224x224, ImageNet mean/std; no crop; all exact 16 consecutive frames',resolution_caveat='224x224 versus MineWorld 384x224; field of view matched, resolution not matched'))

    @torch.inference_mode()
    def __call__(self,frames):
        assert len(frames)==16
        a=np.stack([np.asarray(Image.fromarray(f).resize((224,224),Image.Resampling.BICUBIC),dtype=np.float32)/255 for f in frames])
        a=(a-np.array([.485,.456,.406],dtype=np.float32))/np.array([.229,.224,.225],dtype=np.float32)
        tensor=torch.from_numpy(a.transpose(3,0,1,2)[None].copy()).cuda()
        mask=torch.zeros((1,1568),dtype=torch.bool,device='cuda')
        result=self.model(tensor,mask)[0].reshape(8,14,14,384).mean(0).permute(2,0,1)[None]
        return torch.nn.functional.adaptive_avg_pool2d(result,(2,6))[0].permute(1,2,0).cpu().numpy().reshape(-1).astype(np.float64)

if __name__=='__main__':
    v=VideoEncoder()
    frames=[np.zeros((360,640,3),dtype=np.uint8)]*16
    a=v(frames); b=v(frames)
    assert a.shape==(4608,) and np.isfinite(a).all() and np.array_equal(a,b)
    print('VIDEOMAE_ENCODER_PASS',v.hash,a.shape,flush=True)

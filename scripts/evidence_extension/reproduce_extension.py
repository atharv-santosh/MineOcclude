"""CPU-only reconstruction of extension statistics from locked predictions."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from statistics_core import summarize_motion

def read(p):return json.loads(Path(p).read_text())

def compare(a,b,path='root'):
    if isinstance(a,dict):
        assert set(a)==set(b),(path,'keys')
        for k in a:compare(a[k],b[k],path+'/'+k)
    elif isinstance(a,list):
        assert len(a)==len(b),(path,'length')
        for i,(x,y) in enumerate(zip(a,b)):compare(x,y,path+'/'+str(i))
    elif isinstance(a,(int,float)) and not isinstance(a,bool):
        assert abs(a-b)<1e-8,(path,a,b)
    else:assert a==b,(path,a,b)

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parent);a=p.parse_args();root=a.root
    if (root/'FILES_SHA256.json').exists():
        for name,digest in read(root/'FILES_SHA256.json').items():
            f=(root/name).resolve();assert f.is_relative_to(root.resolve())
            assert hashlib.sha256(f.read_bytes()).hexdigest()==digest,name
    sources=['L0','L1','L2','L3','L4']
    transfer=[r for s in sources for r in read(root/'transfer'/f'{s}.json')['cells']]
    ids=sorted({r['identity'] for r in transfer})
    def errors(rows,c):
        return np.array([[r['prediction']-r['target'] for r in rows if r['identity']==i and r.get('condition',r.get('destination'))==c] for i in ids])
    scores={}
    for s in sources:
        for d in sources:scores[s,d]=np.sqrt((errors([r for r in transfer if r['source']==s],d)**2).mean(1))
    draws=np.random.default_rng(94111).integers(0,25,(10000,25));results=[]
    for s in sources:
        for d in sources:
            rmse=scores[s,d];penalty=rmse-scores[d,d]
            results.append(dict(source=s,destination=d,rmse=float(rmse.mean()),rmse_ci=np.quantile(rmse[draws].mean(1),[.025,.975]).tolist(),mae=float(np.mean(abs(errors([r for r in transfer if r['source']==s],d)))),transfer_penalty=float(penalty.mean()),penalty_ci=np.quantile(penalty[draws].mean(1),[.025,.975]).tolist()))
    compare(results,read(root/'transfer/statistics.json')['cells'])
    for model in ['FRAME_DIFF16','FLOW16','VIDEOMAE_S','OPACITY_MW','OPACITY_PIXELS']:
        levels=['A000','A025','A050','A075','A100'] if model.startswith('OPACITY') else sources
        draws=np.random.default_rng(94112).integers(0,25,(10000,25));results=[]
        for source in levels:
            rows=read(root/'central/predictions'/f'{model}__{source}.json')['cells']
            for c in levels if model.startswith('OPACITY') else [source]:
                e=errors(rows,c);rmse=np.sqrt((e**2).mean(1))
                results.append(dict(source=source,condition=c,rmse=float(rmse.mean()),rmse_ci=np.quantile(rmse[draws].mean(1),[.025,.975]).tolist(),mae=float(abs(e).mean())))
        compare(results,read(root/'central'/f'{model}_statistics.json')['results'])
    draws=np.random.default_rng(94114).integers(0,25,(10000,25));results=[]
    for c in sources:
        for model in ['FRAME_DIFF16','FLOW16','VIDEOMAE_S']:
            e=errors(read(root/'central/predictions'/f'{model}__{c}.json')['cells'],c)
            delta=scores[c,c]-np.sqrt((e**2).mean(1))
            results.append(dict(condition=c,baseline=model,rmse_difference=float(delta.mean()),ci=np.quantile(delta[draws].mean(1),[.025,.975]).tolist(),interpretation='negative favors MineWorld'))
    compare(results,read(root/'central/paired_comparisons.json')['results'])
    print('CENTRAL_EXTENSION_STATISTICS_REPRODUCED',flush=True)
    if (root/'motion/statistics.json').exists():
        rows=[]
        for p in sorted((root/'motion/predictions').glob('*.json')):rows.extend(read(p)['cells'])
        expected=read(root/'motion/statistics.json');expected.pop('inputs')
        compare(summarize_motion(rows),expected)
        print('MOTION_EXTENSION_STATISTICS_REPRODUCED',len(rows),flush=True)

if __name__=='__main__':main()

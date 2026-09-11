from common import *
import numpy as np
from PIL import Image

def main():
    reports=[]
    rows=[r for r in read(ROOT/'motion_pilots_v4.json')['rows'] if r['family']=='velocity' and r['variant']==0 and r['rank']==0]
    for row in rows:
        for condition in ['L0','L4']:
            unit=row['identity']+'__'+condition
            original=ROOT/'pilots_a4'/unit;replica=ROOT/'parallel_pilot'/unit
            a,b=read(original/'BANKED.json'),read(replica/'BANKED.json')
            assert a['spec_hash']==b['spec_hash']==row['spec_hash']
            assert all(sha(replica/k)==v for k,v in b['files'].items())
            ticks=[json.loads(s) for s in (replica/'client/client_tick.jsonl').read_text().splitlines()]
            assert len(ticks)==180 and all(r['tick_queue_depth_at_capture']==0 for r in ticks)
            maxdiff=0;different=0
            for t in range(180):
                relative=Path('client/frames')/f'{t:06d}.png'
                x=np.asarray(Image.open(original/relative),dtype=np.int16)
                y=np.asarray(Image.open(replica/relative),dtype=np.int16)
                d=int(np.max(abs(x-y)));maxdiff=max(maxdiff,d);different+=int(d>0)
            reports.append(dict(unit=unit,max_pixel_difference=maxdiff,differing_frames=different))
    status='PASS' if all(r['max_pixel_difference']==0 for r in reports) else 'FAIL_KEEP_SINGLE_CAPTURE_WORKER'
    save(ROOT/'PARALLEL_CAPTURE_VALIDATION.json',dict(status=status,reports=reports,frames_compared=len(reports)*180,threshold='Exact RGB array equality for every pixel of every frame'))
    print(status,reports,flush=True)

if __name__=='__main__':main()

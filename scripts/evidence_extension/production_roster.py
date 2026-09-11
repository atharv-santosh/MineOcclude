from common import *
from motion import make,FAMILIES
import numpy as np

def main():
    rows=[];rejected=[]
    for part in ['train','test']:
        for layout in ['layout_01','layout_04']:
            for family in FAMILIES:
                for rank in range(8):
                    pair=None
                    for attempt in range(40):
                        candidate=rank+8*attempt
                        try:
                            pair=[make(family,layout,part,candidate,v,True) for v in (0,1)]
                            break
                        except Exception as e:
                            rejected.append(dict(partition=part,layout=layout,family=family,rank=rank,candidate=candidate,error=str(e)))
                    assert pair is not None
                    for r in pair:
                        r['candidate_rank']=r['rank']; r['rank']=rank; r['outer_fold']=rank%4
                        r['spec_hash']=seal({k:v for k,v in r.items() if k!='spec_hash'})
                    assert abs(pair[0]['state_positions'][pair[0]['target_model_frame_indices'][0]]-pair[1]['state_positions'][pair[1]['target_model_frame_indices'][0]])<1e-10
                    rows.extend(pair)
    assert len(rows)==256 and len({r['family_id'] for r in rows})==128
    training={r['family_id'] for r in rows if r['partition']=='train'}
    held={r['family_id'] for r in rows if r['partition']=='test'}
    assert len(training)==len(held)==64 and not training&held
    old={r['seed'] for r in read(OLD/'roster.json')['identities']}
    assert not old&{r['seed'] for r in rows}
    save(ROOT/'motion_production.json',dict(status='PROSPECTIVE_DRAFT_REQUIRES_ADMISSION',rows=rows,geometry_rejections=rejected,protocol_sha256=sha(Path(__file__).with_name('PROTOCOL.md')),analysis_sha256=sha(Path(__file__).with_name('MOTION_ANALYSIS.md')),generator_sha256=sha(Path(__file__).with_name('motion.py'))))
    print('PRODUCTION_DRAFT',len(rows),'trajectories',len(rejected),'geometry rejects',flush=True)

if __name__=='__main__':main()

from common import *
import argparse
from audit_pilots import measure

p=argparse.ArgumentParser();p.add_argument('identity');p.add_argument('--folder',default='captures');p.add_argument('--roster',type=Path,default=MOTION_ROSTER);a=p.parse_args()
r=next(r for r in read(a.roster)['rows'] if r['identity']==a.identity)
first=r['target_model_frame_indices'][0]
print(json.dumps({k:r[k] for k in ['identity','partition','family','direction','speed_blocks_per_second','start_world_x','target_model_frame_indices']},indent=2))
for c in ['L0','L4']:
    base=ROOT/a.folder/f'{a.identity}__{c}'/'client/frames'
    areas={t:measure(base/f'{t:06d}.png')['area'] for t in range(first-15,first+19)}
    print(c,'prior_visible_counts',[sum(areas[t-k]>20 for k in range(1,16)) for t in r['target_model_frame_indices']])
    print(c,'frame_area_x_velocity',[(t,areas[t],round(r['state_positions'][t],5),round(r['signed_velocities'][t],5)) for t in range(first-15,first+2)])

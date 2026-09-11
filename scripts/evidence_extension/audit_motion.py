from common import *
import argparse
import math
import numpy as np
from audit_pilots import measure

def main():
    p=argparse.ArgumentParser(); p.add_argument('--attempt',type=int,default=0); a=p.parse_args()
    rows=read(ROOT/('motion_pilots_matched.json' if a.attempt==1 else 'motion_pilots.json'))['rows']
    reports=[]
    for row in rows:
        for c in ['L0','L4']:
            unit=f'{row["identity"]}__{c}'
            base=ROOT/f'pilots_a{a.attempt}'/unit
            if not (base/'BANKED.json').exists(): continue
            bank=read(base/'BANKED.json')
            assert all(sha(base/k)==v for k,v in bank['files'].items())
            state=[json.loads(s) for s in (base/'server/server_state.jsonl').read_text().splitlines()]
            ticks=[json.loads(s) for s in (base/'client/client_tick.jsonl').read_text().splitlines()]
            complete=read(base/'client/capture_complete.json')
            physical=read(base/'server/physical_receipt.json')
            assert len(state)==len(ticks)==180 and complete['drained'] and complete['writer_errors']==0
            assert [r['server_tick'] for r in state]==list(range(180))
            assert [r['server_tick'] for r in ticks]==list(range(180))
            assert all(r['tick_queue_depth_at_capture']==0 for r in ticks)
            assert physical['wall']['mismatch_count']==0 and physical['target']['valid']
            actual=np.array([s['sheep_x'] for s in state])
            error=float(np.max(abs(actual-row['state_positions'])))
            assert error<1e-9,error
            assert np.max(abs(np.array([s['commanded_v'] for s in state])-row['signed_velocities']))<1e-12
            measurements=[measure(base/'client/frames'/f'{t:06d}.png') for t in range(180)]
            idx=row['target_model_frame_indices']
            areas=[measurements[t]['area'] for t in idx]
            report=dict(unit=unit,family=row['family'],condition=c,exact_path_error=error,target_areas=areas,first_target=idx[0])
            if c=='L0':
                assert min(areas)>20
                focal=180/math.tan(math.radians(35))
                u=np.array([m['u'] if m['u'] is not None else np.nan for m in measurements])
                estimated=.5-(u-320)*(row['layout']['wall_ortho_const']-row['camera'][2])/focal
                labels=np.array(row['historical_FIR_reference_labels'])
                offset=estimated[idx]-labels
                report.update(fir_pixel_median_offset=float(np.median(offset)),fir_pixel_centered_rmse=float(np.std(offset)),rendered_position=estimated[idx].tolist())
            else:
                report['opaque_window_no_magenta']=max(areas)==0
            reports.append(report)
            print(json.dumps(report),flush=True)
    save(ROOT/f'pilot_audit_a{a.attempt}_{len(reports)}.json',dict(reports=reports,complete=len(reports)==len(rows)*2,status='ENGINEERING_AUDIT_NOT_PRODUCTION_ADMISSION'))

if __name__=='__main__': main()

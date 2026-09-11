from common import *
import argparse
import dataclasses
import shutil
import time
import signal
import numpy as np
import mineocclude.experiment_iii.a5_capture as driver
from pilot import CaptureRuntime,RuntimeConfig,FrameSink,CaptureUnitSpec,ConditionSpec,ConditionId

@dataclasses.dataclass(frozen=True)
class ScheduledSpec(CaptureUnitSpec):
    signed_velocities: tuple = ()
    state_positions: tuple = ()

    def replay(self):
        return np.array(self.state_positions,dtype='<f8'),np.zeros(self.frames,dtype='<f8')

    def as_dict(self):
        return {**super().as_dict(),'signed_velocities':list(self.signed_velocities),'state_positions':list(self.state_positions)}

def write_schedule(server_root,spec):
    path=Path(server_root)/driver.MOTION_SCHEDULE_DIRECTORY/f'episode_{spec.episode_id}.json'
    body=dict(schedule_format_version=driver.MOTION_SCHEDULE_FORMAT_VERSION,trajectory_spec_id=spec.capture_unit_id,spec_hash=spec.identity_spec_hash,expected_ticks=spec.frames,segments=[dict(start_model_frame_idx=t,stop_model_frame_idx_exclusive=t+1,signed_speed_blocks_per_second=v) for t,v in enumerate(spec.signed_velocities)])
    save(path,body)
    return dict(path=path,body=body,signed_speed_blocks_per_second=spec.signed_velocities[0])

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--production',action='store_true')
    p.add_argument('--limit',type=int)
    p.add_argument('--attempt',type=int,default=0)
    p.add_argument('--matched',action='store_true')
    p.add_argument('--retest-v2',action='store_true')
    p.add_argument('--retest-v3',action='store_true')
    p.add_argument('--retest-v4',action='store_true')
    p.add_argument('--retest-v5',action='store_true')
    p.add_argument('--retest-v6',action='store_true')
    p.add_argument('--engineering-identity')
    p.add_argument('--engineering-tag')
    p.add_argument('--worker',type=int,default=0)
    p.add_argument('--workers',type=int,default=1)
    p.add_argument('--parallel-check',action='store_true')
    p.add_argument('--regression-check',action='store_true')
    a=p.parse_args()
    if a.production:
        assert read(MOTION_ADMISSION)['status']=='PASS'
        assert read(MOTION_ADMISSION)['production_roster_sha256']==sha(MOTION_ROSTER)
    roster=MOTION_ROSTER if a.production or a.engineering_identity else ROOT/('motion_pilot_retests_v6.json' if a.retest_v6 else 'motion_pilot_retests_v5.json' if a.retest_v5 else 'motion_pilot_retests_v4.json' if a.retest_v4 else 'motion_pilot_retests_v3.json' if a.retest_v3 else 'motion_pilot_retests_v2.json' if a.retest_v2 else 'motion_pilots_matched.json' if a.matched else 'motion_pilots.json')
    rows=read(roster)['rows']
    if a.engineering_identity:
        assert not a.production and a.engineering_tag and a.engineering_tag.replace('_','').replace('-','').isalnum()
        rows=[r for r in rows if r['identity']==a.engineering_identity]
        assert len(rows)==1
    if a.parallel_check:
        rows=[r for r in read(ROOT/'motion_pilots_v4.json')['rows'] if r['family']=='velocity' and r['variant']==0 and r['rank']==0]
    if a.regression_check:
        rows=[r for r in read(MOTION_ROSTER)['rows'] if r['identity']=='e26_layout_01_train_velocity_04_v0']
    assert 0<=a.worker<a.workers and a.workers<=2
    if a.production and a.workers>1:assert read(ROOT/'PARALLEL_CAPTURE_VALIDATION.json')['status']=='PASS'
    if a.limit: rows=rows[:a.limit]
    config=RuntimeConfig.from_json(ROOT/('runtime_worker1.json' if a.worker else 'runtime.json'))
    config.output_root=ROOT/f'capture_logs_{"parallel_check" if a.parallel_check else "production" if a.production else "pilot"}_{a.attempt}_worker{a.worker}'
    original=driver.write_motion_schedule
    driver.write_motion_schedule=write_schedule
    try:
        with CaptureRuntime(config) as runtime:
            print('DISPLAY',runtime.start_display(),flush=True)
            print('SERVER',runtime.start_server(),flush=True)
            print('CLIENT',runtime.start_client(),flush=True)
            sink=FrameSink(config.client_root/'mineocclude_client_out')
            for n,row in enumerate(rows):
                if not a.parallel_check and n%a.workers!=a.worker:continue
                for c in (['L0','L4'] if n%2==0 else ['L4','L0']):
                    unit=f'{row["identity"]}__{c}'
                    destination=ROOT/(('engineering/'+a.engineering_tag) if a.engineering_identity else 'regression_pilot' if a.regression_check else 'parallel_pilot' if a.parallel_check else 'captures' if a.production else f'pilots_a{a.attempt}')/unit
                    if (destination/'BANKED.json').exists():
                        assert read(destination/'BANKED.json')['spec_hash']==row['spec_hash']
                        continue
                    assert not destination.exists()
                    episode=(12000000 if a.production else 11000000)+a.attempt*10000+n*10+int(c[1:])
                    cond=ConditionSpec(ConditionId(c),'NO_WALL' if c=='L0' else 'WALL','minecraft:air' if c=='L0' else 'minecraft:stone',c!='L0','EVIDENCE_EXTENSION')
                    for retry in range(3):
                        roots=[sink.root,config.server_root/'mineocclude_out']
                        witness=episode+3000000
                        if retry or any((root/f'episode_{episode}').exists() or any((root/f'episode_{witness+k}').exists() for k in range(3)) for root in roots):
                            episode=driver.next_witness_episode_base(*roots)
                            witness=episode+1
                        assert all(not (root/f'episode_{episode}').exists() for root in roots)
                        spec=ScheduledSpec(unit,row['identity'],cond,episode,row['seed'],row['direction'],row['start_world_x'],0.,row['speed_blocks_per_second'],.05,180,row['path_sha256'],row['noise_sha256'],tuple(row['target_model_frame_indices']),row['spec_hash'],row['layout_id'],tuple(row['signed_velocities']),tuple(row['state_positions']))
                        try:
                            evidence=driver.capture_a5_unit(runtime,sink,spec,warmup_ticks=60,frame_timeout_seconds=300,server_episode_root=config.server_root/'mineocclude_out',server_run_root=config.server_root,witness_episode_id=witness)
                            break
                        except Exception as error:
                            save(ROOT/'capture_failures'/f'{unit}_{episode}.json',dict(unit=unit,episode=episode,error=str(error),client_path=str(sink.episode_dir(episode)),server_path=str(config.server_root/'mineocclude_out'/f'episode_{episode}'),disposition='Preserved raw failed attempt; not banked or used scientifically'))
                            print('CAPTURE_REJECTED',unit,episode,str(error),flush=True)
                            if retry==2:raise
                    destination.mkdir(parents=True)
                    shutil.copytree(sink.episode_dir(episode),destination/'client')
                    shutil.copytree(config.server_root/'mineocclude_out'/f'episode_{episode}',destination/'server')
                    save(destination/'spec.json',spec.as_dict())
                    save(destination/'capture_evidence.json',evidence)
                    save(destination/'BANKED.json',dict(spec_hash=row['spec_hash'],files={str(f.relative_to(destination)):sha(f) for f in sorted(destination.rglob('*')) if f.is_file()}))
                    print('BANKED',n+1,len(rows),unit,flush=True)
    finally:
        driver.write_motion_schedule=original

if __name__=='__main__':
    def stop_owned_runtime(signum,frame):raise KeyboardInterrupt('Capture supervisor requested shutdown')
    signal.signal(signal.SIGTERM,stop_owned_runtime)
    main()

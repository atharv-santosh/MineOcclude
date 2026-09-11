from diag_common import *
import argparse
import dataclasses
import shutil
import time
from pilot import CaptureRuntime,RuntimeConfig,FrameSink,CaptureUnitSpec,ConditionSpec,ConditionId,capture_a5_unit


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--pilot',action='store_true')
    p.add_argument('--attempt',type=int,default=0)
    a=p.parse_args()
    roster=read(ROOT/'roster.json')
    assert roster['protocol_sha256']==sha(Path(__file__).parent/'PROTOCOL.md')
    if not a.pilot:
        admit=read(ROOT/'capture_admission.json')
        assert admit['status']=='PASS' and admit['roster_sha256']==sha(ROOT/'roster.json')
    rows=roster['pilots' if a.pilot else 'identities']
    config=RuntimeConfig.from_json(ROOT/'runtime.json')
    config.output_root=ROOT/f"{'pilot' if a.pilot else 'production'}_logs_{a.attempt}"
    save(config.output_root/'config.json',dataclasses.asdict(config))
    start=time.monotonic()
    with CaptureRuntime(config) as runtime:
        print(runtime.start_display(),runtime.start_server(),runtime.start_client(),flush=True)
        sink=FrameSink(config.client_root/'mineocclude_client_out')
        for n,row in enumerate(rows):
            for condition in (['L0','L4'] if n%2==0 else ['L4','L0']):
                episode=(6000000 if a.pilot else 9000000)+a.attempt*10000+n*10+int(condition[1:])
                unit=f"{row['identity']}__{condition}"
                destination=ROOT/('pilots' if a.pilot else 'captures')/unit
                if (destination/'BANKED.json').exists():
                    bank=read(destination/'BANKED.json')
                    assert bank['spec_hash']==row['spec_hash']
                    assert all(sha(destination/k)==v for k,v in bank['files'].items())
                    continue
                assert not destination.exists()
                assert not sink.episode_dir(episode).exists()
                cond=ConditionSpec(ConditionId(condition),'NO_WALL' if condition=='L0' else 'WALL','minecraft:air' if condition=='L0' else 'minecraft:stone',condition!='L0','HISTORY_DIAGNOSTIC')
                spec=CaptureUnitSpec(unit,row['identity'],cond,episode,row['seed'],row['direction'],row['start_world_x'],.05,row['speed_blocks_per_second'],.05,180,row['path_sha256'],row['noise_sha256'],tuple(row['target_model_frame_indices']),row['spec_hash'],row['layout_id'])
                evidence=capture_a5_unit(runtime,sink,spec,warmup_ticks=60,frame_timeout_seconds=300,server_episode_root=config.server_root/'mineocclude_out',server_run_root=config.server_root,witness_episode_id=episode+1000000)
                destination.mkdir(parents=True)
                shutil.copytree(sink.episode_dir(episode),destination/'client')
                shutil.copytree(config.server_root/'mineocclude_out'/f'episode_{episode}',destination/'server')
                save(destination/'spec.json',{**spec.as_dict(),'partition':row['partition'],'cohort':row['cohort']})
                save(destination/'capture_evidence.json',evidence)
                files={str(f.relative_to(destination)):sha(f) for f in sorted(destination.rglob('*')) if f.is_file()}
                save(destination/'BANKED.json',dict(spec_hash=row['spec_hash'],files=files,state='BANKED_PENDING_QA'))
                print('BANKED',n+1,len(rows),unit,round(time.monotonic()-start,1),flush=True)
                save(ROOT/('pilot_status.json' if a.pilot else 'capture_status.json'),dict(state='CAPTURING',identity_index=n+1,identities=len(rows),unit=unit,elapsed_seconds=time.monotonic()-start))
    save(ROOT/('pilot_status.json' if a.pilot else 'capture_status.json'),dict(state='COMPLETE_PENDING_QA',units=len(rows)*2,elapsed_seconds=time.monotonic()-start))

if __name__=='__main__':
    main()

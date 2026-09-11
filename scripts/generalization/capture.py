"""Fresh cohort capture with independent admission and immutable per-unit output."""
import argparse
import dataclasses
import hashlib
import json
from pathlib import Path
import shutil
import time
from pilot import SOURCE,ROOT,CaptureRuntime,RuntimeConfig,FrameSink,CaptureUnitSpec,ConditionSpec,ConditionId,capture_a5_unit,save


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--attempt',type=int,default=0)
    args=parser.parse_args()
    admission=json.loads((ROOT/'capture_admission.json').read_text())
    assert admission['admitted'] is True
    assert admission['protocol_sha256']==digest(Path(__file__).parent/'PROTOCOL.md')
    assert admission['cohort_sha256']==digest(ROOT/'cohort_geometry_draft.json')
    manifest=json.loads((ROOT/'cohort_geometry_draft.json').read_text())
    config=RuntimeConfig.from_json(ROOT/'runtime.json')
    config.output_root=ROOT/f'production_logs_a{args.attempt}'
    save(config.output_root/'config.json',dataclasses.asdict(config))
    planned=[]
    for n,row in enumerate(manifest['identities']):
        for condition in (['L0','L4'] if n%2==0 else ['L4','L0']):
            cond=ConditionSpec(ConditionId(condition),'NO_WALL' if condition=='L0' else 'WALL','minecraft:air' if condition=='L0' else 'minecraft:stone',condition!='L0','FRESH_GENERALIZATION')
            episode=4000000+args.attempt*10000+n*10+(0 if condition=='L0' else 4)
            unit=f"{row['identity']}__{condition}"
            spec=CaptureUnitSpec(unit,row['identity'],cond,episode,row['seed'],row['direction'],row['start_world_x'],.05,row['speed_blocks_per_second'],.05,180,row['path_sha256'],row['noise_sha256'],tuple(row['target_model_frame_indices']),row['spec_hash'],row['layout_id'])
            planned.append((row,spec))
    start=time.monotonic()
    with CaptureRuntime(config) as runtime:
        print('DISPLAY',runtime.start_display(),flush=True)
        print('SERVER',runtime.start_server(),flush=True)
        print('CLIENT',runtime.start_client(),flush=True)
        sink=FrameSink(config.client_root/'mineocclude_client_out')
        for n,(row,spec) in enumerate(planned):
            destination=ROOT/'captures'/spec.capture_unit_id
            if (destination/'BANKED.json').exists():
                bank=json.loads((destination/'BANKED.json').read_text())
                assert bank['spec_hash']==row['spec_hash']
                for filename,expected in bank['files'].items():
                    assert digest(destination/filename)==expected
                print('PRESERVED',n+1,spec.capture_unit_id,flush=True)
                continue
            assert not destination.exists(), 'Partial output must be investigated, not overwritten'
            for root in [sink.root,config.server_root/'mineocclude_out']:
                assert not (root/f'episode_{spec.episode_id}').exists(),'Use a new attempt ID for an interrupted capture'
            save(ROOT/'capture_status.json',dict(state='CAPTURING',unit=spec.capture_unit_id,index=n+1,total=150,elapsed_seconds=time.monotonic()-start))
            evidence=capture_a5_unit(runtime,sink,spec,warmup_ticks=60,frame_timeout_seconds=300,server_episode_root=config.server_root/'mineocclude_out',server_run_root=config.server_root,witness_episode_id=5000000+args.attempt*10000+n*10)
            destination.mkdir(parents=True)
            shutil.copytree(sink.episode_dir(spec.episode_id),destination/'client')
            shutil.copytree(config.server_root/'mineocclude_out'/f'episode_{spec.episode_id}',destination/'server')
            save(destination/'spec.json',{**spec.as_dict(),'cohort':row['cohort'],'outer_fold':row['outer_fold']})
            save(destination/'capture_evidence.json',evidence)
            # BANKED is a durability receipt, not scientific qualification.
            files={str(p.relative_to(destination)):digest(p) for p in sorted(destination.rglob('*')) if p.is_file()}
            save(destination/'BANKED.json',dict(spec_hash=row['spec_hash'],files=files,state='BANKED_PENDING_SCIENTIFIC_QA'))
            print('BANKED',n+1,150,spec.capture_unit_id,round(time.monotonic()-start,1),flush=True)
    save(ROOT/'capture_status.json',dict(state='ALL_150_BANKED_PENDING_QA',total=150,elapsed_seconds=time.monotonic()-start))


if __name__=='__main__':
    main()

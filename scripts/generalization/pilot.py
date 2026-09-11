"""Disjoint engineering captures; no pilot measurements enter paper results."""
import argparse
import dataclasses
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
import numpy as np

SOURCE=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(SOURCE/'src'))
from mineocclude.experiment_iii.capture_runtime import CaptureRuntime, RuntimeConfig
from mineocclude.experiment_iii.capture_driver import FrameSink
from mineocclude.experiment_iii.a5_capture import CaptureUnitSpec, capture_a5_unit
from mineocclude.experiment_iii.cohort import generate_path, path_sha256, noise_sha256
from mineocclude.experiment_iii.conditions import ConditionSpec
from mineocclude.experiment_iii.schema import ConditionId

ROOT=Path('/home/bpcfno/mineocclude-generalization-20260911')


def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,default=str,allow_nan=False)+'\n')


def spec_for(idx, condition, attempt):
    cohort=idx//2
    direction='LEFT_TO_RIGHT' if idx%2==0 else 'RIGHT_TO_LEFT'
    layout=['layout_01','layout_04','layout_01'][cohort]
    speed=[2.,2.,3.][cohort]
    seed=int.from_bytes(hashlib.sha256(f'mineocclude-generalization-pilot-20260911-{idx}'.encode()).digest()[:7],'big')
    start=-7.6 if idx%2==0 else 7.6
    path,noise=generate_path(seed,.05,direction=direction,start_world_x=start,speed=speed,frames=180)
    identity=f'g26_p{idx:02d}'
    unit=f'{identity}_{condition}_a{attempt}'
    body=dict(identity=identity,layout=layout,speed=speed,seed=seed,start=start,frames=180)
    bind=hashlib.sha256(json.dumps(body,sort_keys=True).encode()).hexdigest()
    cond=ConditionSpec(ConditionId(condition),'NO_WALL' if condition=='L0' else 'WALL', 'minecraft:air' if condition=='L0' else 'minecraft:stone',condition!='L0','ENGINEERING_ONLY')
    return CaptureUnitSpec(unit,identity,cond,2000000+attempt*1000+idx*10+(0 if condition=='L0' else 4),seed,direction,start,.05,speed,.05,180,path_sha256(path),noise_sha256(noise),(),bind,layout)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--indices',default='0')
    p.add_argument('--conditions',default='L0')
    p.add_argument('--attempt',type=int,default=0)
    args=p.parse_args()
    config=RuntimeConfig.from_json(ROOT/'runtime.json')
    config.output_root=ROOT/f'pilot_logs_a{args.attempt}'
    save(config.output_root/'config.json',dataclasses.asdict(config))
    with CaptureRuntime(config) as runtime:
        print('DISPLAY',runtime.start_display(),flush=True)
        print('SERVER',runtime.start_server(),flush=True)
        print('CLIENT',runtime.start_client(),flush=True)
        sink=FrameSink(config.client_root/'mineocclude_client_out')
        for idx in map(int,args.indices.split(',')):
            for condition in args.conditions.split(','):
                spec=spec_for(idx,condition,args.attempt)
                destination=ROOT/'pilots'/spec.capture_unit_id
                assert not destination.exists(), 'Use a new attempt ID; never overwrite pilots'
                for root in [sink.root,config.server_root/'mineocclude_out']:
                    assert not (root/f'episode_{spec.episode_id}').exists(), 'Episode already used'
                print('CAPTURE',spec.capture_unit_id,flush=True)
                started=time.monotonic()
                evidence=capture_a5_unit(runtime,sink,spec,warmup_ticks=60,frame_timeout_seconds=300,server_episode_root=config.server_root/'mineocclude_out',server_run_root=config.server_root,witness_episode_id=3000000+args.attempt*1000+idx*20+(0 if condition=='L0' else 10))
                destination.mkdir(parents=True)
                shutil.copytree(sink.episode_dir(spec.episode_id),destination/'client')
                shutil.copytree(config.server_root/'mineocclude_out'/f'episode_{spec.episode_id}',destination/'server')
                save(destination/'spec.json',spec.as_dict())
                save(destination/'evidence.json',evidence)
                print('CAPTURE_SAVED',spec.capture_unit_id,round(time.monotonic()-started,1),flush=True)


if __name__=='__main__':
    main()

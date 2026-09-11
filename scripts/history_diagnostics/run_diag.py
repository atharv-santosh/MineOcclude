"""Schedule existing feature jobs' downstream checks and analysis."""
from diag_common import *
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import os
import subprocess
import time

HERE=Path(__file__).parent
OUT=ROOT/'analysis'
ENV={**os.environ,'OPENBLAS_NUM_THREADS':'4','OMP_NUM_THREADS':'4'}


def wait(path):
    while not path.exists():
        if datetime.now(timezone.utc).hour>=19:
            raise RuntimeError(f'Analysis prerequisite not ready before final delivery window: {path.name}')
        time.sleep(5)


def run(name,*args,tag=None):
    label=tag or name.removesuffix('.py')
    folder=OUT/'job_logs'; folder.mkdir(parents=True,exist_ok=True)
    path=folder/f'{label}.log'
    assert not path.exists(),path
    started=time.monotonic()
    print('START',label,datetime.now(timezone.utc).isoformat(),flush=True)
    with path.open('w') as log:
        subprocess.run([sys.executable,str(HERE/name),*args],env=ENV,stdout=log,stderr=subprocess.STDOUT,check=True)
    elapsed=time.monotonic()-started
    save(folder/f'{label}.json',dict(status='PASS',elapsed_seconds=elapsed,finished_utc=datetime.now(timezone.utc).isoformat(),log_sha256=sha(path)))
    print('DONE',label,round(elapsed,1),flush=True)


def fit_job(mode):
    wait(OUT/f'{mode}_complete.json')
    assert read(OUT/f'{mode}_complete.json')['status']=='PASS'
    if mode=='pixels':
        run('fit_diag.py','--models','PIXEL_CURRENT','PIXEL_HISTORY16',tag='fit_pixels')
    else:
        run('fit_diag.py','--models',f'MW_{mode}','--mlp',tag='fit_'+mode)


def capture_verify():
    while True:
        try:
            if read(ROOT/'capture_status.json')['state']=='COMPLETE_PENDING_QA':
                break
        except (FileNotFoundError,json.JSONDecodeError):
            pass
        if datetime.now(timezone.utc).hour>=19:
            raise RuntimeError('Capture still incomplete')
        time.sleep(5)
    run('verify_capture.py')


def main():
    freeze=ROOT/'statistical_source_freeze.json'
    assert not freeze.exists()
    assert not list((OUT/'predictions').glob('*.json'))
    save(freeze,dict(utc=datetime.now(timezone.utc).isoformat(),status='BEFORE_TEST_PREDICTIONS',files={p.name:sha(p) for p in [HERE/'statistics_diag.py',HERE/'validate_diag.py',HERE/'test_diag.py']},analysis_freeze_sha256=sha(ROOT/'analysis_freeze.json')))
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs=[pool.submit(fit_job,m) for m in ['pixels','700M','300M']]+[pool.submit(capture_verify)]
        for j in jobs:
            j.result()
    for layout in ['layout_01','layout_04']:
        wait(OUT/'predictions'/f'BASELINES__{layout}.json')
    run('statistics_diag.py',str(OUT/'predictions'),str(OUT/'statistics.json'))
    run('validate_diag.py')
    save(OUT/'analysis_complete.json',dict(status='PASS',finished_utc=datetime.now(timezone.utc).isoformat(),statistics_sha256=sha(OUT/'statistics.json'),validation_sha256=sha(OUT/'independent_validation.json')))
    print('ANALYSIS_COMPLETE',flush=True)


if __name__=='__main__':
    main()

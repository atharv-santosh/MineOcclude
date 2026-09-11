"""Continue the verified capture-to-analysis workflow; fail closed at each stage."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=Path('/home/bpcfno/mineocclude-generalization-20260911')
ENV={**os.environ,'MINEOCCLUDE_WEIGHTS':'/home/bpcfno/mineocclude-rgb-runtime/weights',
     'OPENBLAS_NUM_THREADS':'4','OMP_NUM_THREADS':'4'}


def run(name,*args):
    start=time.monotonic()
    print('STAGE_START',name,datetime.now(timezone.utc).isoformat(),flush=True)
    subprocess.run([sys.executable,str(HERE/name),*args],check=True,env=ENV)
    print('STAGE_DONE',name,round(time.monotonic()-start,2),flush=True)


def main():
    while True:
        try:
            state=json.loads((ROOT/'capture_status.json').read_text())
            if state['state']=='ALL_150_BANKED_PENDING_QA':
                break
        except (FileNotFoundError,json.JSONDecodeError):
            pass
        if datetime.now(timezone.utc).hour>=19:
            raise RuntimeError('Capture wait exceeded planned analysis start window')
        time.sleep(5)
    started=time.monotonic()
    run('prepare.py')
    # Independent CPU pixel extraction can overlap the GPU forward pass.
    pixels=subprocess.Popen([sys.executable,str(HERE/'features.py'),'--mode','pixels'],env=ENV)
    try:
        run('features.py','--mode','mineworld')
        assert pixels.wait()==0,'Pixel extraction failed'
    except BaseException:
        if pixels.poll() is None:
            pixels.terminate()
            pixels.wait()
        raise
    run('fit.py')
    run('transfer.py')
    run('rebuild_statistics.py','--input',str(ROOT/'analysis/predictions'),'--output',str(ROOT/'analysis/statistics.json'))
    run('summarize_transfer.py','--input',str(ROOT/'analysis/transfer'),'--output',str(ROOT/'analysis/transfer_statistics.json'))
    run('package_results.py')
    run('build_paper.py')
    print('ANALYSIS_COMPLETE_PENDING_INDEPENDENT_QA',round(time.monotonic()-started,2),flush=True)


if __name__=='__main__':
    main()

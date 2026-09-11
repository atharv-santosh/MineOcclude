from common import *
import subprocess
import time

def main():
    assert read(ROOT/'MOTION_ADMISSION.json')['status']=='PASS'
    logs=ROOT/'production_jobs';logs.mkdir(exist_ok=True)
    env=os.environ.copy();env['MINEOCCLUDE_WEIGHTS']='/home/bpcfno/mineocclude-rgb-runtime/weights'
    active=[]
    def start(name,args):
        log=logs/f'{name}.log'
        handle=log.open('a')
        proc=subprocess.Popen([sys.executable,str(Path(__file__).parent/args[0]),*args[1:]],cwd=SOURCE,env=env,stdout=handle,stderr=subprocess.STDOUT)
        active.append((name,proc,handle));print('START',name,proc.pid,flush=True)
        return proc
    def wait(proc,name):
        result=proc.wait()
        assert result==0,(name,result)
        print('DONE',name,flush=True)
    start_time=time.monotonic()
    try:
        capture=start('capture',['capture.py','--production'])
        pixels=start('pixels',['motion_features.py','--mode','pixels','--watch'])
        neural=start('700M',['motion_features.py','--mode','700M','--watch'])
        while capture.poll() is None:
            volume=os.statvfs('/mnt/c')
            assert volume.f_bavail*volume.f_frsize>8*1024**3,'Physical Windows volume reserve below 8 GiB; preserve captures and stop'
            for name,proc,_ in active:
                assert proc.poll() in (None,0),(name,proc.returncode)
            if int(time.monotonic()-start_time)%60<10:
                print('PROGRESS',len(list((ROOT/'captures').glob('*/BANKED.json'))),512,flush=True)
            time.sleep(10)
        wait(capture,'capture');wait(pixels,'pixels');wait(neural,'700M')
        video=start('video',['motion_features.py','--mode','video']);wait(video,'video')
        for model in ['MW_700M','PIXEL_CURRENT','PIXEL_HISTORY16','FRAME_DIFF16','FLOW16','VIDEOMAE_S']:
            job=start('fit_'+model,['fit_motion.py','--model',model]);wait(job,'fit_'+model)
        for script in ['motion_baselines.py','verify_motion.py','motion_statistics.py','negative_control.py']:
            job=start(script[:-3],[script]);wait(job,script)
        save(ROOT/'PRODUCTION_COMPLETE.json',dict(status='PASS',wall_seconds=time.monotonic()-start_time,analysis_sha256=sha(Path(__file__).with_name('MOTION_ANALYSIS.md')),statistics_sha256=sha(ROOT/'motion/statistics.json')))
    finally:
        for name,proc,handle in active:
            if proc.poll() is None:
                proc.terminate()
                try:proc.wait(timeout=30)
                except subprocess.TimeoutExpired:proc.kill();proc.wait()
            handle.close()

if __name__=='__main__':main()

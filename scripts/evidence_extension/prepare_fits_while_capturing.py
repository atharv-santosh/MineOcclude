from common import *
import argparse
import subprocess
import time

def main():
    p=argparse.ArgumentParser();p.add_argument('--supervisor-pid',type=int,required=True);args=p.parse_args()
    rows=[r for r in read(MOTION_ROSTER)['rows'] if r['partition']=='train']
    models=['MW_700M','PIXEL_CURRENT','PIXEL_HISTORY16','FRAME_DIFF16','FLOW16','VIDEOMAE_S']
    receipts=[ROOT/'motion/receipts'/f'{mode}__{r["identity"]}__{c}.json' for r in rows for c in ['L0','L4'] for mode in ['pixels','700M','video']]
    while not all(p.exists() for p in receipts):
        os.kill(args.supervisor_pid,0)
        time.sleep(10)
    active=[]
    try:
        for index in range(0,len(models),2):
            jobs=[]
            for model in models[index:index+2]:
                handle=(ROOT/'production_jobs'/f'prepare_{model}.log').open('a')
                process=subprocess.Popen([sys.executable,str(Path(__file__).with_name('fit_motion.py')),'--model',model,'--prepare-only'],cwd=SOURCE,stdout=handle,stderr=subprocess.STDOUT)
                jobs.append((process,handle));active.append((process,handle))
                print('EARLY_FIT_START',model,process.pid,flush=True)
            for process,handle in jobs:
                while process.poll() is None:
                    os.kill(args.supervisor_pid,0)
                    time.sleep(2)
                assert process.returncode==0
                handle.close()
        save(ROOT/'EARLY_TRAINING_COMPLETE.json',dict(status='PASS',fits=24,test_features_read=False,roster_sha256=sha(MOTION_ROSTER),analysis_sha256=sha(Path(__file__).with_name('MOTION_ANALYSIS.md'))))
        print('EARLY_TRAINING_COMPLETE',flush=True)
    finally:
        for process,handle in active:
            if process.poll() is None:process.terminate();process.wait()
            handle.close()

if __name__=='__main__':main()

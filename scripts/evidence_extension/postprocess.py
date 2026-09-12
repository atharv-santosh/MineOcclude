from common import *
import argparse
import errno
import subprocess
import time

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--supervisor-pid',type=int,required=True);args=parser.parse_args()
    while not (ROOT/'PRODUCTION_COMPLETE.json').exists():
        try:os.kill(args.supervisor_pid,0)
        except ProcessLookupError:raise RuntimeError('Production stopped before completion. Preserve all outputs and resolve the capture/analysis failure before postprocessing.')
        time.sleep(10)
    assert read(ROOT/'PRODUCTION_COMPLETE.json')['status']=='PASS'
    jobs=[['final_data_audit.py'],['reproduce_extension.py','--root',str(ROOT)],['make_figures.py'],['make_tables.py'],['build_paper.py'],['package_extension.py']]
    for command in jobs:
        print('POSTPROCESS_START',command[0],flush=True)
        subprocess.run([sys.executable,str(Path(__file__).parent/command[0]),*command[1:]],cwd=SOURCE,check=True)
        print('POSTPROCESS_DONE',command[0],flush=True)
    for name in ['clean_cpu_replay.ps1','compile_paper.ps1']:
        script=SOURCE/'scripts/evidence_extension'/name
        windows=subprocess.check_output(['wslpath','-w',str(script)],text=True).strip()
        try:
            subprocess.run(['/mnt/c/Users/gensa/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe','-NoProfile','-File',windows],cwd=SOURCE,check=True)
        except OSError as exc:
            if exc.errno != errno.ENOEXEC:
                raise
            save(ROOT/'NATIVE_WINDOWS_HANDOFF_REQUIRED.json', dict(
                status='PENDING_NATIVE_WINDOWS_VALIDATION',
                completed='Scientific audit, numerical replay, manuscript generation, and reproduction archive',
                pending_scripts=['clean_cpu_replay.ps1','compile_paper.ps1'],
                reason='WSL cannot execute the Windows PowerShell binary on this host. Run these scripts through native Windows PowerShell; do not treat this handoff as validation success.',
            ))
            print('NATIVE_WINDOWS_HANDOFF_REQUIRED',flush=True)
            return
    save(ROOT/'POSTPROCESS_READY_FOR_REVIEW.json',dict(status='NUMERICAL_REPLAY_CLEAN_PACKAGE_REPLAY_AND_DRAFT_BUILD_COMPLETE',manual_full_pdf_visual_review_required=True,clean_package_replay_required=False,live_overleaf_update_required=True,anonymous_access_not_verified=True))
    print('POSTPROCESS_READY_FOR_MANUAL_REVIEW',flush=True)

if __name__=='__main__':main()

"""Rebuild the supplied statistics and figures without a GPU or model weights."""
import subprocess
import sys
from pathlib import Path
from audit_recovery import ROOT,OUT,read,save,sha

def main():
    manifest=ROOT/'FILES_SHA256.json'
    if manifest.exists():
        for name,expected in read(manifest).items():
            path=(ROOT/name).resolve()
            assert path.is_relative_to(ROOT.resolve())
            assert sha(path)==expected,('Snapshot input changed',name)
    expected=read(OUT/'summary.json') if (OUT/'summary.json').exists() else None
    here=Path(__file__).parent
    subprocess.run([sys.executable,str(here/'summarize.py')],check=True,cwd=ROOT)
    actual=read(OUT/'summary.json')
    if expected is not None:
        assert actual==expected,'Statistics differ from supplied snapshot'
    subprocess.run([sys.executable,str(here/'make_figures.py')],check=True,cwd=ROOT)
    subprocess.run([sys.executable,str(here/'make_tables.py')],check=True,cwd=ROOT)
    save(OUT/'cpu_reproduction_receipt.json',{'status':'PASS','statistics_identical':expected is not None,'prediction_cells':actual['cells'],'summary_sha256':sha(OUT/'summary.json'),'python':sys.version,'gpu_required':False})
    print('CPU_REPRODUCTION_PASS',flush=True)

if __name__=='__main__':
    main()

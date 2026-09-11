"""Assemble a local compact statistics snapshot without captures or model weights."""
import importlib.metadata
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from audit_recovery import ROOT,PKG,OUT,read,save,sha

def main():
    assert read(OUT/'new_results_validation.json')['status']=='PASS'
    deliver=ROOT/'output/pdf'
    deliver.mkdir(parents=True,exist_ok=True)
    staging=OUT/'compact_snapshot'
    if staging.exists():
        raise RuntimeError('Preserve previous package; choose a new staging directory for revisions')
    staging.mkdir()
    def copy(src):
        rel=src.relative_to(ROOT)
        dest=staging/rel
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,dest)
    for path in (ROOT/'scripts/rgb_replication').glob('*'):
        if path.is_file(): copy(path)
    for path in (OUT/'predictions').glob('*.json'): copy(path)
    keep=['summary.json','new_results_validation.json','recovery_audit.json','statistics_reconstruction_audit.json',
      'legacy_primary_reconstructed.json','corpus_audit.json','runtime_validation.json','profile_RGB.json','profile_BGR.json',
      'checkpoint_load_validation.json','pixel_build_receipt.json','reference_solver_check.json',
      'reference_solver_check_MW_RGB_L19.json','reference_solver_check_PIXEL_HISTORY16.json',
      'figure_capture_provenance.json','window_evidence_audit.json','scope_runtime_report.json']
    for name in keep: copy(OUT/name)
    for name in ('prediction_lock/PREDICTION_LOCK.json','cohort/EXECUTED_TARGETS.json','cohort/FOLD_ASSIGNMENTS.json',
      'cohort/CAPTURE_INDEX.json','cohort/FIR_ALIGNMENT.json','results/primary_results.json',
      'provenance/MODEL_PROVENANCE.json','provenance/ENVIRONMENT_PROVENANCE.json'):
        copy(PKG/name)
    for info in read(OUT/'figure_capture_provenance.json'):
        copy(ROOT/'recovery_inputs/corpus/captures'/info['unit']/'raw/frames'/f"{info['frame']:06d}.png")
    for path in (OUT/'paper').iterdir():
        if path.suffix in ('.tex','.bib','.sty','.pdf','.png') and path.name not in ('mineocclude_no_wall_capture.png','mineocclude_wall_capture.png','graded_visibility_review.pdf','paper.pdf'):
            copy(path)
    requirements='\n'.join(f'{name}=={importlib.metadata.version(name)}' for name in ('numpy','matplotlib','pillow'))+'\n'
    (staging/'requirements-cpu.txt').write_text(requirements)
    (staging/'README.md').write_text((ROOT/'scripts/rgb_replication/README.md').read_text())
    freeze='\n'.join(sorted(f'{d.metadata["Name"]}=={d.version}' for d in importlib.metadata.distributions()))+'\n'
    (staging/'requirements-executed.txt').write_text(freeze)
    manifest={str(p.relative_to(staging)).replace('\\','/'):sha(p) for p in sorted(staging.rglob('*')) if p.is_file()}
    save(staging/'FILES_SHA256.json',manifest)
    archive=deliver/'mineocclude_rgb_history_reproducibility.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as bundle:
        for path in sorted(staging.rglob('*')):
            if path.is_file(): bundle.write(path,path.relative_to(staging))
    save(OUT/'package_receipt.json',{'archive':archive.name,'sha256':sha(archive),'bytes':archive.stat().st_size,'files':len(manifest)+1,'includes_full_corpus':False,'includes_weights':False})
    print('PACKAGED',archive,archive.stat().st_size,flush=True)

if __name__=='__main__':
    main()

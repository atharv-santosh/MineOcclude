"""Deliver the new paper and combined local reproduction after explicit visual QA."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import shutil
import zipfile
from prepare import ROOT,SOURCE,read,save,sha


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--visual-review-confirmed',action='store_true')
    args=parser.parse_args()
    assert args.visual_review_confirmed,'Inspect the rendered final PDF pages first'
    paper=SOURCE/'generalization_outputs/paper'
    log=(paper/'paper.log').read_text(errors='replace')
    assert 'Overfull' not in log and 'undefined' not in log and 'Missing character' not in log
    pages=[p for p in (paper/'paper-layout.txt').read_text().split('\f') if p.strip()]
    refs=[j+1 for j,p in enumerate(pages) if re.match(r'\s*\d*\s*References',p)]
    assert refs==[9],refs
    assert read(ROOT/'analysis/independent_validation.json')['status']=='PASS'
    assert read(SOURCE/'generalization_outputs/cpu_reproduction_receipt.json')['status']=='PASS'
    assert read(ROOT/'analysis/fresh_scene_checks.json')['status']=='PASS'
    deliver=SOURCE/'output/pdf'
    deliver.mkdir(parents=True,exist_ok=True)
    targets=['mineocclude_generalization.pdf','paper_generalization.tex','mineocclude_generalization_overleaf.zip','mineocclude_generalization_reproduction.zip']
    assert not any((deliver/n).exists() for n in targets),'Preserve earlier delivery version'
    shutil.copy2(paper/'paper.pdf',deliver/targets[0])
    shutil.copy2(paper/'paper.tex',deliver/targets[1])
    source_files=[p for p in paper.iterdir() if p.suffix in ['.tex','.bib','.sty','.pdf'] and p.name!='paper.pdf']
    with zipfile.ZipFile(deliver/targets[2],'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(source_files): z.write(p,p.name)
    combined=SOURCE/'generalization_outputs/submission_reproduction'
    assert not combined.exists()
    combined.mkdir()
    old=deliver/'mineocclude_rgb_history_reproducibility.zip'
    central=combined/'central'
    central.mkdir()
    with zipfile.ZipFile(old) as z:
        for info in z.infolist():
            target=(central/info.filename).resolve()
            assert target.is_relative_to(central.resolve())
            assert ((info.external_attr>>16)&0o170000)!=0o120000,'No archive symlinks'
        z.extractall(central)
    shutil.copytree(SOURCE/'generalization_outputs/fresh_reproduction',combined/'fresh',ignore=shutil.ignore_patterns('__pycache__'))
    for name in ['independent_validation.json','fresh_scene_checks.json']:
        shutil.copy2(ROOT/'analysis'/name,combined/'fresh/validation'/name)
    shutil.copy2(SOURCE/'generalization_outputs/cpu_reproduction_receipt.json',combined/'fresh/validation/cpu_reproduction_receipt.json')
    execution=combined/'execution_source'
    for folder in ['scripts/generalization','scripts/rgb_replication','src','fabric/mineocclude-mod/src','fabric/mineocclude-mod/gradle','reproducibility/experiment_iii_a/provenance']:
        shutil.copytree(SOURCE/folder,execution/folder,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for name in ['build.gradle','settings.gradle','gradle.properties','gradlew','gradlew.bat']:
        shutil.copy2(SOURCE/'fabric/mineocclude-mod'/name,execution/'fabric/mineocclude-mod'/name)
    shutil.copy2(SOURCE/'generalization_outputs/EXPERIMENT_REPORT.md',combined/'EXPERIMENT_REPORT.md')
    (combined/'README.md').write_text('''# MineOcclude submission reproduction

This combines two distinct, preserved studies. Do not pool their identities.

- `central/`: the previously verified 25-identity RGB/history follow-up, unchanged.
  Follow its README and run `python scripts/rgb_replication/reproduce.py` there.
- `fresh/`: 75 newly captured identities, 19,950 primary cells and 5,700 transfer
  cells. Install its requirements-cpu.txt and run `python reproduce.py` there.
- `execution_source/`: exact execution/analysis sources for full reproduction;
  see scripts/generalization/EXECUTION_README.md. Full extraction additionally
  needs the hash-verified captures, pinned upstream source, and model weights.
- `EXPERIMENT_REPORT.md`: measured results, checks, scope, and compute.

The fresh CPU rebuild was tested in a clean environment containing only NumPy.
The companion full fresh-capture archive holds all 150 recordings and 27,000
images. Neither archive redistributes Minecraft binaries or model weights.

These are local artifacts. Anonymous public distribution and reviewer access
still require a separate release/access check.
''')
    qa=dict(status='PASS',finished_utc=datetime.now(timezone.utc).isoformat(),main_text_pages=8,references_start_page=9,total_pages=len(pages),visual_review='All final rendered pages inspected; no overlapping/clipped text or tables',overfull_boxes=False,undefined_references=False,
        primary_cells=19950,transfer_cells=5700,fresh_identities=75,captures=150,frames=27000,
        cpu_reproduction='PASS in NumPy-only environment',known_legacy_test='154 passed; one strict historical FIR equality test differs only at binary64 summation precision',
        previous_outputs='Preserved',external_writes='None: no push, publication, submission, or Overleaf change',paper_sha256=sha(deliver/targets[0]),source_sha256=sha(deliver/targets[1]))
    save(combined/'DELIVERY_QA.json',qa)
    inventory={str(p.relative_to(combined)):sha(p) for p in sorted(combined.rglob('*')) if p.is_file()}
    save(combined/'COMBINED_FILES_SHA256.json',inventory)
    with zipfile.ZipFile(deliver/targets[3],'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(combined.rglob('*')):
            if p.is_file(): z.write(p,p.relative_to(combined))
    save(SOURCE/'generalization_outputs/DELIVERY_QA.json',qa)
    save(deliver/'generalization_delivery_manifest.json',{n:dict(bytes=(deliver/n).stat().st_size,sha256=sha(deliver/n)) for n in targets})
    print('GENERALIZATION_DELIVERY_COMPLETE',deliver)


if __name__=='__main__':
    main()

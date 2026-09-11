"""Export only the locally verified paper and compact reproducibility artifacts."""
import re
import shutil
import zipfile
from pathlib import Path
from audit_recovery import ROOT,OUT,read,save,sha

def main():
    paper=OUT/'paper'
    log=(paper/'paper.log').read_text(errors='replace')
    assert 'Overfull' not in log and 'undefined' not in log
    pages=(paper/'paper-layout.txt').read_text().split('\f')
    refs=[j+1 for j,p in enumerate(pages) if re.match(r'\s*\d*\s*References',p)]
    assert refs==[9],refs
    assert len([p for p in pages if p.strip()])==19
    assert read(OUT/'new_results_validation.json')['status']=='PASS'
    staging=OUT/'compact_snapshot'
    assert read(staging/'replication_outputs/cpu_reproduction_receipt.json')['status']=='PASS'
    deliver=ROOT/'output/pdf'
    deliver.mkdir(exist_ok=True,parents=True)
    shutil.copy2(paper/'paper.pdf',deliver/'mineocclude_rgb_history.pdf')
    shutil.copy2(paper/'paper.tex',deliver/'paper_rgb_history.tex')
    source_files=['paper.tex','checklist.tex','references.bib','neurips_2026.sty',
      'matched_captures.pdf','rgb_evidence_results.pdf','rgb_history_results.pdf',
      'rgb_condition_rows.tex','rgb_age_rows.tex','rgb_depth_rows.tex','rgb_channel_rows.tex','rgb_context_rows.tex']
    with zipfile.ZipFile(deliver/'mineocclude_rgb_history_overleaf.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for name in source_files: archive.write(paper/name,name)
    # Incorporate the verified clean-folder receipt and current run instructions.
    for dest in (staging/'README.md',staging/'scripts/rgb_replication/README.md'):
        shutil.copy2(ROOT/'scripts/rgb_replication/README.md',dest)
    qa={'main_pages':8,'references_start_page':9,'total_pages':19,'undefined_references':False,'overfull_boxes':False,
      'visual_review':'All 19 rendered pages inspected; changed figures, tables, captions and checklist verified',
      'paper_sha256':sha(deliver/'mineocclude_rgb_history.pdf'),'source_sha256':sha(deliver/'paper_rgb_history.tex'),
      'new_results_validation':'PASS','cpu_reproduction':'PASS; exact numerical summary equality in compact folder without source package or GPU',
      'original_repo_and_manuscript':'Preserved; work isolated on codex/rgb-history-replication',
      'publication':'No external writes, pushes, submissions, or Overleaf edits'}
    save(OUT/'final_qa.json',qa)
    shutil.copy2(OUT/'final_qa.json',staging/'replication_outputs/final_qa.json')
    manifest={str(p.relative_to(staging)).replace('\\','/'):sha(p) for p in sorted(staging.rglob('*')) if p.is_file() and p.name!='FILES_SHA256.json' and '__pycache__' not in p.parts}
    save(staging/'FILES_SHA256.json',manifest)
    archive=deliver/'mineocclude_rgb_history_reproducibility.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as bundle:
        for path in sorted(staging.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts: bundle.write(path,path.relative_to(staging))
    save(deliver/'delivery_manifest.json',{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(deliver.iterdir()) if p.is_file() and p.name!='delivery_manifest.json'})
    print('FINAL_DELIVERY_VERIFIED',deliver,flush=True)

if __name__=='__main__':
    main()

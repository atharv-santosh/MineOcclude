from common import *
import subprocess

def main():
    assert read(ROOT/'MOTION_ADMISSION.json')['status']=='PASS'
    assert not list((ROOT/'captures').glob('*/BANKED.json'))
    rows=read(MOTION_ROSTER)['rows']
    train={r['family_id'] for r in rows if r['partition']=='train'}
    test={r['family_id'] for r in rows if r['partition']=='test'}
    assert len(train)==len(test)==64 and not train&test
    source={p.name:sha(p) for p in sorted(Path(__file__).parent.iterdir()) if p.suffix in ('.py','.md') and p.name not in ('build_paper.py','make_figures.py','package_extension.py','REPRODUCTION_README.md','freeze_production.py')}
    imports={str(p.relative_to(SOURCE)):sha(p) for p in [SOURCE/'scripts/history_diagnostics/fit_diag.py',SOURCE/'scripts/history_diagnostics/features_diag.py',SOURCE/'scripts/rgb_replication/extract_features.py',SOURCE/'src/mineocclude/experiment_iii/fir.py']}
    manifest=dict(status='LOCKED_BEFORE_PRODUCTION',roster_sha256=sha(MOTION_ROSTER),admission_sha256=sha(ROOT/'MOTION_ADMISSION.json'),source=source,imported_analysis_sources=imports,git_parent=subprocess.check_output(['git','--git-dir',str(SOURCE.parents[1]/'.git/worktrees'/SOURCE.name),'rev-parse','HEAD'],cwd=SOURCE,text=True).strip(),captures_present=0,heldout_outcomes_inspected=False)
    save(ROOT/'PRODUCTION_FREEZE.json',manifest)
    save(SOURCE/'evidence_extension_outputs/PRODUCTION_FREEZE.json',manifest)
    print('PRODUCTION_FREEZE_LOCKED',len(source),flush=True)

if __name__=='__main__':main()

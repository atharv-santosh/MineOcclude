from common import *

def main():
    assert read(MOTION_ADMISSION)['status']=='PASS'
    assert read(MOTION_ADMISSION)['production_roster_sha256']==sha(MOTION_ROSTER)
    assert read(ROOT/'VELOCITY_APPROACH_REGRESSION.json')['status']=='PASS'
    assert not list((ROOT/'motion/predictions').glob('*.json'))
    amendment=read(ROOT/'CAPTURE_AMENDMENT_V4.json')
    archive=ROOT/'preserved_production_v3';assert not archive.exists()
    archive.mkdir()
    moved=[]
    def preserve(path):
        if not path.exists():return
        assert path.resolve().is_relative_to(ROOT.resolve())
        target=archive/path.relative_to(ROOT)
        assert target.resolve().is_relative_to(archive.resolve()) and not target.exists()
        target.parent.mkdir(parents=True,exist_ok=True)
        path.rename(target)
        moved.append(str(target.relative_to(ROOT)))
    for identity in amendment['changed_identities']:
        for condition in ['L0','L4']:
            unit=identity+'__'+condition
            preserve(ROOT/'captures'/unit)
            for path in list((ROOT/'motion/features').glob('*/'+unit+'.npy')):preserve(path)
            for path in list((ROOT/'motion/receipts').glob('*__'+unit+'.json')):preserve(path)
    rows={r['identity']:r for r in read(MOTION_ROSTER)['rows']}
    for p in (ROOT/'captures').glob('*/BANKED.json'):
        identity=p.parent.name.rsplit('__',1)[0]
        assert read(p)['spec_hash']==rows[identity]['spec_hash']
    locked={p.name:sha(p) for p in sorted(Path(__file__).parent.iterdir()) if p.suffix in ('.py','.md') and p.name not in ('build_paper.py','make_figures.py','make_tables.py','package_extension.py','REPRODUCTION_README.md')}
    seal_record=dict(status='CAPTURE_AMENDMENT_LOCKED_BEFORE_HELDOUT_CAPTURE_AND_FITTING',previous_freeze_sha256=sha(ROOT/'PRODUCTION_FREEZE.json'),amendment_sha256=sha(ROOT/'CAPTURE_AMENDMENT_V4.json'),roster_sha256=sha(MOTION_ROSTER),admission_sha256=sha(MOTION_ADMISSION),analysis_sha256=sha(Path(__file__).with_name('MOTION_ANALYSIS.md')),preserved_paths=moved,reused_unchanged_training_captures=len(list((ROOT/'captures').glob('*/BANKED.json'))),source=locked,heldout_outcomes_inspected=False,acceptance_thresholds_unchanged=True)
    save(ROOT/'PRODUCTION_FREEZE_V4.json',seal_record)
    save(SOURCE/'evidence_extension_outputs/PRODUCTION_FREEZE_V4.json',seal_record)
    print('AMENDMENT_LOCKED',len(moved),'preserved paths',flush=True)

if __name__=='__main__':main()

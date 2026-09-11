"""Stage immutable fresh-cohort CPU reproduction and a separate full raw archive."""
import argparse
import json
from pathlib import Path
import shutil
import zipfile
from prepare import ROOT,SOURCE,read,save,sha


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--raw',action='store_true')
    args=parser.parse_args()
    manifest=read(ROOT/'manifest.json')
    assert manifest['status']=='ALL_150_VERIFIED'
    out=SOURCE/'generalization_outputs'
    out.mkdir(exist_ok=True)
    if args.raw:
        archive=out/'mineocclude_fresh_75_captures.zip'
        assert not archive.exists(),archive
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_STORED,allowZip64=True) as z:
            for unit in sorted(manifest['units']):
                bank=read(ROOT/'captures'/unit/'BANKED.json')
                for filename,h in bank['files'].items():
                    path=ROOT/'captures'/unit/filename
                    assert sha(path)==h
                    z.write(path,f'captures/{unit}/{filename}')
                z.write(ROOT/'captures'/unit/'BANKED.json',f'captures/{unit}/BANKED.json')
            for name in ['manifest.json','capture_admission.json','cohort_geometry_draft.json','seed_independence.json']:
                z.write(ROOT/name,name)
        save(out/'raw_archive_receipt.json',dict(archive=archive.name,bytes=archive.stat().st_size,sha256=sha(archive),captures=150,frames=27000,all_input_file_hashes_checked=True,contains_game_binaries=False))
        print('RAW_ARCHIVE',archive,archive.stat().st_size)
        return
    assert read(ROOT/'analysis/statistics.json')['cells']==19950
    assert read(ROOT/'analysis/transfer_statistics.json')['cells']==5700
    snapshot=out/'fresh_reproduction'
    assert not snapshot.exists(),'Preserve existing snapshot'
    snapshot.mkdir()
    def copy(src,relative):
        dest=snapshot/relative
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,dest)
    for name in ['rebuild_statistics.py','summarize_transfer.py','reproduce.py','test_statistics.py']:
        copy(SOURCE/'scripts/generalization'/name,name)
    for file in (ROOT/'analysis/predictions').glob('*.json'):
        copy(file,'primary/predictions/'+file.name)
    for file in (ROOT/'analysis/transfer').glob('*.json'):
        copy(file,'transfer/predictions/'+file.name)
    copy(ROOT/'analysis/statistics.json','primary/statistics.json')
    copy(ROOT/'analysis/transfer_statistics.json','transfer/statistics.json')
    for name in ['manifest.json','capture_admission.json','cohort_geometry_draft.json','seed_independence.json','capture_status.json','artifact_hashes.json','arithmetic_audit.json','ANALYSIS_FREEZE.json','mod_source_validation.json']:
        copy(ROOT/name,'configuration/'+name)
    copy(ROOT/'core_tests_git_resolved.xml','validation/core_tests_git_resolved.xml')
    for name in ['PROTOCOL.md','TRANSFER_PROTOCOL.md']:
        copy(SOURCE/'scripts/generalization'/name,'configuration/'+name)
    for name in ['runtime_validation.json','checkpoint_load_validation.json','encoder_boundary_validation.json','mineworld_complete.json','pixels_complete.json']:
        copy(ROOT/'analysis'/name,'validation/'+name)
    for file in (ROOT/'analysis/feature_receipts').glob('*.json'):
        copy(file,'feature_receipts/'+file.name)
    for unit in sorted(manifest['units']):
        copy(ROOT/'captures'/unit/'BANKED.json','capture_hashes/'+unit+'.json')
    # A genuinely matched pair from each setting, not synthesized illustrations.
    for cohort in ['replication','geometry','speed']:
        identity=f'g26_{cohort}_01'
        for condition in ['L0','L4']:
            unit=identity+'__'+condition
            t=manifest['units'][unit]['target_model_frame_indices'][0]
            copy(ROOT/'captures'/unit/'client/frames'/f'{t:06d}.png',f'examples/{unit}__frame{t:03d}.png')
    (snapshot/'requirements-cpu.txt').write_text('numpy==1.26.4\n')
    (snapshot/'README.md').write_text('''# MineOcclude fresh-cohort reproduction

This snapshot contains 75 newly captured identities: 25 original-setting,
25 changed-geometry, and 25 higher-speed identities. Every identity has paired
air and stone captures and 19 fixed target times. All predictions are measured,
not hypothetical. Engineering pilots are excluded.

## CPU-only verification

Use Python 3.10--3.12 in a clean environment:

```
python -m pip install -r requirements-cpu.txt
python test_statistics.py
python reproduce.py
```

The last command verifies every listed input hash and exactly rebuilds the
supplied statistics from 19,950 primary and 5,700 secondary transfer prediction
cells. It requires neither a GPU nor Minecraft, model weights, or activations.
Primary fits are identity-grouped and fitted separately within each setting.
Transfer fits use only the 25 fresh original-setting source identities; all
destination labels are scoring-only. These analyses must not be pooled.

The manifest contains targets, raw state history, target indices, and exact
outer/inner folds. Per-prediction files record alpha selection and source hashes.
Intervals use 10,000 paired identity resamples (seed 20260911), conditional on
fitted probes; they are not simultaneous or refitting intervals.

## Full capture and inference

The companion mineocclude_fresh_75_captures.zip contains the full 150 recordings,
27,000 actual Minecraft frames, state/action/tick logs, and per-file hashes.
It does not include Minecraft binaries or model weights. The accompanying
execution source and runtime receipts document full extraction and fitting.
The CPU-only command above reconstructs statistics, not neural inference.

The original graded-evidence RGB follow-up has a separate preserved reproduction
snapshot. This package is a fresh extension, not a replacement of its identities.
Anonymous public distribution has not been verified by creating these local files.
''')
    inventory={str(p.relative_to(snapshot)):sha(p) for p in sorted(snapshot.rglob('*')) if p.is_file()}
    save(snapshot/'FILES_SHA256.json',inventory)
    print('SNAPSHOT_STAGED',snapshot,len(inventory))


if __name__=='__main__':
    main()

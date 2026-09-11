"""Create a new, anonymous CPU snapshot; never modify earlier deliveries."""
from diag_common import *
import argparse
import re
import shutil
import subprocess
import zipfile

DEST=SOURCE/'history_diagnostic_outputs'
SNAP=DEST/'anonymous_reproduction'
OUT=ROOT/'analysis'
TEXT_EXT={'.py','.json','.jsonl','.md','.txt','.tex','.bib','.sty','.yaml','.yml','.toml','.xml','.gradle','.properties','.sh','.bat'}
PRIVATE=re.compile(r'gensa|sahilsinghthefirst|atharv-santosh|/home/bpcfno|[A-Z]:\\+Users\\+[^\\\s"\']+|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}',re.I)
SOURCE_FOLDERS=['scripts/history_diagnostics','scripts/generalization','scripts/rgb_replication','src','fabric/mineocclude-mod/src','fabric/mineocclude-mod/gradle','reproducibility/experiment_iii_a/provenance']


def copy(src,dest):
    dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(src,dest)


def inventory(root,name='FILES_SHA256.json'):
    files={str(p.relative_to(root)).replace('\\','/'):sha(p) for p in sorted(root.rglob('*')) if p.is_file() and p.name!=name and '__pycache__' not in p.parts}
    save(root/name,files)
    return files


def sanitize_tree(root):
    changes=[]
    for p in sorted(root.rglob('*')):
        if not p.is_file() or p.suffix.lower() not in TEXT_EXT:
            continue
        text=p.read_text(errors='strict')
        cleaned=text.replace('/home/bpcfno','/opt/mineocclude').replace('atharv-santosh/MineOcclude','ANONYMOUS/MineOcclude')
        cleaned=re.sub(r'(?i)[A-Z]:\\+Users\\+[^\\\s"\']+',r'C:\\research',cleaned)
        cleaned=cleaned.replace('sahilsinghthefirst','researcher').replace('gensa','researcher').replace('atharv-santosh','ANONYMOUS')
        if text!=cleaned:
            original=sha(p); p.write_text(cleaned)
            changes.append(dict(path=str(p.relative_to(root)),original_sha256=original,public_sha256=sha(p),change='Local account/path anonymization only'))
        assert not PRIVATE.search(cleaned),('Private identifier or credential-shaped text remains',str(p.relative_to(root)))
    return changes


def prestage():
    assert not SNAP.exists()
    SNAP.mkdir(parents=True)
    old=SOURCE/'generalization_outputs/submission_reproduction'
    for name in ['central','fresh']:
        shutil.copytree(old/name,SNAP/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    changes=sanitize_tree(SNAP)
    # Neither numerical prediction files nor central statistics may be rewritten.
    for name in ['central','fresh']:
        for p in (old/name).rglob('*.json'):
            if 'predictions' in p.parts or p.name in ('summary.json','statistics.json','PREDICTION_LOCK.json'):
                assert p.read_bytes()==(SNAP/name/p.relative_to(old/name)).read_bytes()
        inventory(SNAP/name)
    save(DEST/'prestage_privacy_changes.json',changes)
    print('PRESTAGED_OLD_STUDIES',len(changes),flush=True)


def complete():
    assert read(OUT/'independent_validation.json')['status']=='PASS'
    assert read(OUT/'comparator_replay_validation.json')['status']=='PASS'
    assert SNAP.exists() and not (SNAP/'diagnostic').exists()
    d=SNAP/'diagnostic'; d.mkdir()
    copy(Path(__file__).parent/'statistics_diag.py',d/'statistics_diag.py')
    copy(Path(__file__).parent/'reproduce_diag.py',d/'reproduce.py')
    for p in (OUT/'predictions').glob('*.json'): copy(p,d/'predictions'/p.name)
    copy(OUT/'statistics.json',d/'statistics.json')
    for name in ['roster.json','manifest.json','analysis_freeze.json','statistical_source_freeze.json','statistical_source_amendment.json','comparator_audit_freeze.json','capture_admission.json','capture_status.json']:
        copy(ROOT/name,d/'configuration'/name)
    for name in ['PROTOCOL.md','ANALYSIS_FREEZE.md']:
        copy(Path(__file__).parent/name,d/'configuration'/name)
    for folder in ['fits','feature_receipts','tests']:
        for p in (OUT/folder).glob('*'):
            if p.is_file() and (folder!='fits' or p.suffix=='.json'):
                copy(p,d/folder/p.name)
    for name in ['independent_validation.json','comparator_replay_validation.json','figure_provenance.json','analysis_complete.json','700M_complete.json','300M_complete.json','pixels_complete.json']:
        copy(OUT/name,d/'validation'/name)
    for model in ['700M','300M']:
        for p in (OUT/model).glob('*.json'): copy(p,d/'validation'/model/p.name)
    for p in (ROOT/'weights').glob('*provenance.json'): copy(p,d/'validation'/p.name)
    for p in (OUT/'job_logs').glob('*.json'): copy(p,d/'validation/timings'/p.name)
    copy(DEST/'diagnostic_figure_data.json',d/'figure_data.json') if (DEST/'diagnostic_figure_data.json').exists() else None
    # Store true input images selected before outcomes, without game binaries.
    provenance=read(OUT/'figure_provenance.json')['actual_capture_panels']
    for r in provenance:
        unit=r['identity']+'__L4'; t=r['frame']
        copy(ROOT/'captures'/unit/'client/frames'/f'{t:06d}.png',d/'examples'/f'{unit}__{t:06d}.png')
    for layout in ['layout_01','layout_04']:
        unit=f'h26_{layout}_test_0_00__L0'
        info=read(ROOT/'manifest.json')['units'][unit]
        t=info['target_model_frame_indices'][0]
        copy(ROOT/'captures'/unit/'client/frames'/f'{t:06d}.png',d/'examples'/f'{unit}__{t:06d}.png')
    execution=SNAP/'execution_source'
    for folder in SOURCE_FOLDERS:
        shutil.copytree(SOURCE/folder,execution/folder,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    for name in ['build.gradle','settings.gradle','gradle.properties','gradlew','gradlew.bat']:
        copy(SOURCE/'fabric/mineocclude-mod'/name,execution/'fabric/mineocclude-mod'/name)
    copy(Path(__file__).parent/'PUBLIC_README.md',SNAP/'README.md')
    copy(Path(__file__).parent/'reproduce_all.py',SNAP/'reproduce_all.py')
    (SNAP/'requirements-cpu.txt').write_text('numpy==1.26.4\nmatplotlib==3.10.9\npillow==11.3.0\n')
    changes=sanitize_tree(SNAP)
    # Public execution copies have local-account paths redacted. Keep numerical
    # and exact-execution hash provenance separate from this portable inventory.
    save(SNAP/'PUBLIC_SOURCE_ADAPTATIONS.json',dict(changes=changes,scope='Local account/path anonymization. Prediction values, target values, splits, and statistical code are unchanged.',execution_note='Full execution source requires capture/runtime root configuration. Exact executed source hashes remain in the frozen manifests; public source hashes are separately inventoried.'))
    for p in (OUT/'predictions').glob('*.json'):
        assert p.read_bytes()==(d/'predictions'/p.name).read_bytes()
    assert (OUT/'statistics.json').read_bytes()==(d/'statistics.json').read_bytes()
    inventory(d)
    for name in ['central','fresh']: inventory(SNAP/name)
    inventory(SNAP,'SNAPSHOT_SHA256.json')
    fitted=DEST/'mineocclude_fitted_readouts.zip'
    assert not fitted.exists()
    with zipfile.ZipFile(fitted,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted((OUT/'fits').glob('*')):
            if p.suffix in ('.npz','.json'):
                z.write(p,p.name)
    save(DEST/'fitted_readouts_receipt.json',dict(archive=fitted.name,bytes=fitted.stat().st_size,sha256=sha(fitted),scope='Optional fitted probes; feature arrays required for prediction replay. Not needed for the compact statistics rebuild.'))
    print('ANONYMOUS_SNAPSHOT_READY',sum(p.stat().st_size for p in SNAP.rglob('*') if p.is_file()),flush=True)


def privacy_preflight():
    import tempfile
    folder=Path(tempfile.mkdtemp(prefix='public-source-review-',dir=ROOT))
    for name in SOURCE_FOLDERS:
        shutil.copytree(SOURCE/name,folder/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    changes=sanitize_tree(folder)
    save(DEST/'source_privacy_preflight.json',dict(status='PASS',files=sum(p.is_file() for p in folder.rglob('*')),anonymized_files=len(changes),scope='Execution-source staging only; final snapshot is checked separately.'))
    print('SOURCE_PRIVACY_PREFLIGHT_PASS',len(changes),flush=True)


def raw():
    manifest=read(ROOT/'manifest.json')
    assert manifest['status']=='ALL_192_VERIFIED'
    path=DEST/'mineocclude_variable_speed_96_captures.zip'
    assert not path.exists()
    partial=path.with_suffix('.partial.zip')
    assert not partial.exists()
    with zipfile.ZipFile(partial,'w',zipfile.ZIP_STORED,allowZip64=True) as z:
        for unit in sorted(manifest['units']):
            base=ROOT/'captures'/unit
            bank=read(base/'BANKED.json')
            for name,h in bank['files'].items():
                assert sha(base/name)==h
                z.write(base/name,f'captures/{unit}/{name}')
            z.write(base/'BANKED.json',f'captures/{unit}/BANKED.json')
        for name in ['manifest.json','roster.json','capture_admission.json','analysis_freeze.json']:
            z.write(ROOT/name,name)
    partial.replace(path)
    save(DEST/'raw_archive_receipt.json',dict(status='PASS',archive=path.name,bytes=path.stat().st_size,sha256=sha(path),identities=96,captures=192,frames=34560,game_binaries_included=False,privacy='Unmodified local evidence archive; not the anonymous reviewer snapshot'))
    print('FULL_RAW_ARCHIVE_READY',path.stat().st_size,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('mode',choices=['prestage','complete','raw','privacy_preflight']); a=parser.parse_args()
    {'prestage':prestage,'complete':complete,'raw':raw,'privacy_preflight':privacy_preflight}[a.mode]()

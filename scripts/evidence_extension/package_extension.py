from common import *
import re
import shutil
import zipfile

DEST=SOURCE/'evidence_extension_outputs'
SNAP=DEST/'anonymous_reproduction'
TEXT={'.py','.json','.jsonl','.md','.txt','.tex','.bib','.sty','.yaml','.yml','.toml','.xml','.gradle','.properties','.sh','.bat'}

def copy(src,dst):
    dst.parent.mkdir(parents=True,exist_ok=True)
    assert not dst.exists(),dst
    shutil.copy2(src,dst)

def main():
    assert read(ROOT/'PRODUCTION_COMPLETE.json')['status']=='PASS'
    assert read(ROOT/'central_validation_42750.json')['status']=='PASS'
    assert not SNAP.exists()
    shutil.copytree(SOURCE/'history_diagnostic_outputs/anonymous_reproduction',SNAP,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    ex=SNAP/'extension';ex.mkdir()
    for p in (ROOT/'transfer').glob('*.json'):copy(p,ex/'transfer'/p.name)
    for p in (ROOT/'central').glob('*.json'):copy(p,ex/'central'/p.name)
    for p in (ROOT/'central/predictions').glob('*.json'):copy(p,ex/'central/predictions'/p.name)
    for p in (ROOT/'central/receipts').glob('*.json'):copy(p,ex/'central/receipts'/p.name)
    for folder in ['predictions','receipts']:
        for p in (ROOT/'motion'/folder).glob('*.json'):copy(p,ex/'motion'/folder/p.name)
    for p in (ROOT/'motion').glob('*.json'):copy(p,ex/'motion'/p.name)
    for p in ROOT.glob('*.json'):
        if p.name!='runtime.json':copy(p,ex/'configuration'/p.name)
    for p in Path(__file__).parent.iterdir():
        if p.suffix in ('.py','.md'):copy(p,ex/'source'/p.name)
    copy(Path(__file__).with_name('statistics_core.py'),ex/'statistics_core.py')
    copy(Path(__file__).with_name('reproduce_extension.py'),ex/'reproduce.py')
    for name in ['EXECUTED_TARGETS.json','FOLD_ASSIGNMENTS.json']:
        copy(SOURCE/'reproducibility/experiment_iii_a/cohort'/name,ex/'central/cohort'/name)
    changes=[]
    private=re.compile(r'gensa|sahilsinghthefirst|atharv-santosh|/home/bpcfno|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}',re.I)
    for p in ex.rglob('*'):
        if not p.is_file() or p.suffix not in TEXT:continue
        raw=p.read_text();clean=raw.replace('/home/bpcfno','/opt/research').replace('atharv-santosh','ANONYMOUS').replace('gensa','researcher').replace('sahilsinghthefirst','researcher')
        if raw!=clean:
            before=sha(p);p.write_text(clean);changes.append(dict(path=p.relative_to(ex).as_posix(),executed_sha256=before,distributed_sha256=sha(p),reason='Account/path anonymization only; numeric predictions unchanged'))
        assert not private.search(clean),p
    save(ex/'ANONYMIZATION.json',changes)
    copy(Path(__file__).with_name('REPRODUCTION_README.md'),ex/'README.md')
    save(ex/'FILES_SHA256.json',{p.relative_to(ex).as_posix():sha(p) for p in sorted(ex.rglob('*')) if p.is_file()})
    archive=DEST/'mineocclude_evidence_extension_reproduction.zip'
    assert not archive.exists()
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(SNAP.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(SNAP))
    save(DEST/'reproduction_package.json',dict(sha256=sha(archive),bytes=archive.stat().st_size,files=sum(p.is_file() for p in SNAP.rglob('*')),anonymous_host_access='NOT_VERIFIED; owner login required to update existing September 1 snapshot'))
    print('EXTENSION_PACKAGE_CREATED',archive,archive.stat().st_size,flush=True)

if __name__=='__main__':main()

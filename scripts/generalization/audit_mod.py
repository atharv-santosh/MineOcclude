"""Bind the built capture mod to unchanged project source and Java test reports."""
from pathlib import Path
import xml.etree.ElementTree as ET
from prepare import ROOT,SOURCE,read,save,sha


def main():
    original=SOURCE/'fabric/mineocclude-mod'
    built=ROOT/'mod'
    files=list((original/'src').rglob('*'))
    files += [original/n for n in ['build.gradle','settings.gradle','gradle.properties']]
    hashes={}
    for src in files:
        if not src.is_file():
            continue
        rel=src.relative_to(original)
        assert sha(src)==sha(built/rel),str(rel)
        hashes[str(rel)]=sha(src)
    tests=[]
    for path in sorted((built/'build/test-results/test').glob('*.xml')):
        suite=ET.parse(path).getroot()
        tests.append(dict(name=suite.attrib['name'],tests=int(suite.attrib['tests']),failures=int(suite.attrib['failures']),errors=int(suite.attrib['errors']),sha256=sha(path)))
    assert tests and all(t['failures']==t['errors']==0 for t in tests)
    jar=built/'build/libs/mineocclude-0.1.1.jar'
    assert sha(jar)==read(ROOT/'capture_admission.json')['mod_sha256']
    save(ROOT/'mod_source_validation.json',dict(status='PASS',source_files=hashes,tests=tests,total_tests=sum(t['tests'] for t in tests),jar_sha256=sha(jar),source_changes=False))
    print('UNCHANGED_MOD_VERIFIED',len(hashes),'files',sum(t['tests'] for t in tests),'Java tests')


if __name__=='__main__':
    main()

"""Compile the delivered Overleaf ZIP from an empty temporary project."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import zipfile

source=Path(__file__).resolve().parents[2]
output=source/'output/pdf'
archive=output/'mineocclude_history_diagnostic_overleaf.zip'
dest=Path(tempfile.mkdtemp(prefix='mineocclude-overleaf-check-'))
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for name in z.namelist():
        assert not Path(name).is_absolute() and '..' not in Path(name).parts
    z.extractall(dest)
commands=[['pdflatex','-interaction=nonstopmode','-halt-on-error','paper.tex'],
          ['bibtex','paper'],
          ['pdflatex','-interaction=nonstopmode','-halt-on-error','paper.tex'],
          ['pdflatex','-interaction=nonstopmode','-halt-on-error','paper.tex']]
for command in commands:
    command[0]=shutil.which(command[0])
    assert command[0]
    result=subprocess.run(command,cwd=dest,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    assert result.returncode==0,result.stdout[-5000:]
log=(dest/'paper.log').read_text(errors='replace')
assert not re.search(r'Overfull|undefined|Missing character|LaTeX Error',log)
subprocess.run([shutil.which('pdftotext'),'-layout',str(dest/'paper.pdf'),str(dest/'layout.txt')],check=True)
actual=(dest/'layout.txt').read_text(encoding='utf-8').replace('\r\n','\n')
expected=(source/'history_diagnostic_outputs/paper/paper-layout.txt').read_text(encoding='utf-8').replace('\r\n','\n')
assert actual==expected,'Archive compilation differs from delivered paper text'
pages=[p for p in actual.split('\f') if p.strip()]
assert len(pages)==29 and re.search(r'^\s*\d*\s*References\s*$',pages[8],re.M)
receipt=dict(status='PASS',archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
    compiled_from_empty_project=True,all_page_text_exactly_equal=True,
    main_pages=8,references_start_page=9,total_pages=29,
    temporary_project=str(dest),compiler='MiKTeX pdfLaTeX + BibTeX',
    no_missing_dependencies_in_zip=True)
(source/'history_diagnostic_outputs/overleaf_bundle_validation.json').write_text(json.dumps(receipt,indent=2)+'\n')
print('OVERLEAF_ZIP_COMPILES_AND_MATCHES_ALL_29_PAGES')

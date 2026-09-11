"""Isolate new dependencies so unrelated Overleaf drafts are not modified."""
from common import *
import re
import shutil
from finalize_delivery import PAPER, dependencies


def rewrite(text, names, prefix='evidence-extension/'):
    def file_name(name, extension=''):
        key = name if Path(name).suffix else name + extension
        return prefix + name if key in names else name

    text = re.sub(r'(\\(?:input|tablerows)\s*\{)([^}]+)(\})',
                  lambda m: m[1] + file_name(m[2], '.tex') + m[3], text)
    text = re.sub(r'(\\tablerows\s+)([^\s{}]+\.tex)',
                  lambda m: m[1] + file_name(m[2]) , text)
    text = re.sub(r'(\\includegraphics(?:\[[^\]]*\])?\{)([^}]+)(\})',
                  lambda m: m[1] + file_name(m[2], '.pdf') + m[3], text)
    text = re.sub(r'(\\bibliography\{)([^}]+)(\})',
                  lambda m: m[1] + ','.join(file_name(n.strip(), '.bib') for n in m[2].split(',')) + m[3], text)
    text = re.sub(r'(\\usepackage(?:\[[^\]]*\])?\{)([^}]+)(\})',
                  lambda m: m[1] + ','.join(file_name(n.strip(), '.sty') for n in m[2].split(',')) + m[3], text)
    return text


def main():
    review = read(PAPER / 'visual_review.json')
    assert review['status'] == 'PASS' and review['pdf_sha256'] == sha(PAPER / 'paper.pdf')
    staging = SOURCE / 'evidence_extension_outputs/overleaf_staging'
    assert not staging.exists()
    names = dependencies(PAPER)
    paths = []
    for name in names:
        src = PAPER / name
        dest_name = name if name == 'paper.tex' else 'evidence-extension/' + name
        dest = staging / dest_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix == '.tex':
            dest.write_text(rewrite(src.read_text(encoding='utf-8'), set(names)), encoding='utf-8')
        else:
            shutil.copy2(src, dest)
        paths.append(dict(local_path=str(dest), destination=dest_name, sha256=sha(dest)))
    save(SOURCE / 'evidence_extension_outputs/overleaf_staging_manifest.json', dict(
        files=paths, root_file='paper.tex',
        instruction='Upload isolated dependencies first. Refresh and use the current paper.tex baseSha for its replacement. Compile paper.tex explicitly with pdfLaTeX.',
        reviewed_pdf_sha256=sha(PAPER / 'paper.pdf'),
    ))
    print('OVERLEAF_STAGING_READY', len(paths), flush=True)


if __name__ == '__main__':
    main()

"""Package only the reviewed manuscript and its transitive local dependencies."""
from common import *
import re
import shutil
import zipfile

PAPER = SOURCE / 'evidence_extension_outputs/paper'
OUT = SOURCE / 'output/pdf'


def dependencies(root):
    root = Path(root).resolve()
    pending = ['paper.tex']
    found = set()
    while pending:
        name = pending.pop()
        if name in found:
            continue
        path = (root / name).resolve()
        assert path.is_relative_to(root) and path.is_file(), name
        found.add(name)
        if path.suffix != '.tex':
            continue
        text = path.read_text(encoding='utf-8')
        for command, names in re.findall(r'\\(input|tablerows|bibliography)\s*\{([^}]+)\}', text):
            for dep in names.split(','):
                dep = dep.strip()
                extension = '.bib' if command == 'bibliography' else '.tex'
                pending.append(dep if Path(dep).suffix else dep + extension)
        pending.extend(re.findall(r'\\tablerows\s+([^\s{}]+\.tex)', text))
        for dep in re.findall(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}', text):
            if not Path(dep).suffix:
                matches = [dep + ext for ext in ['.pdf', '.png', '.jpg'] if (root / (dep + ext)).is_file()]
                assert matches, dep
                dep = matches[0]
            pending.append(dep)
        for names in re.findall(r'\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}', text):
            pending.extend(name.strip() + '.sty' for name in names.split(',') if (root / (name.strip() + '.sty')).is_file())
    return sorted(found)


def main():
    report = json.loads((PAPER / 'draft_build_report.json').read_text(encoding='utf-8-sig'))
    review = read(PAPER / 'visual_review.json')
    replay = json.loads((SOURCE / 'evidence_extension_outputs/clean_cpu_replay.json').read_text(encoding='utf-8-sig'))
    assert report['eight_main_pages_verified'] and not report['undefined_citations_or_references']
    assert review['status'] == 'PASS' and review['pdf_sha256'] == sha(PAPER / 'paper.pdf')
    assert replay['status'] == 'PASS'
    names = dependencies(PAPER)
    OUT.mkdir(parents=True, exist_ok=True)
    archive = OUT / 'mineocclude_evidence_extension_overleaf.zip'
    assert not archive.exists()
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name in names:
            z.write(PAPER / name, name)
    targets = {
        PAPER / 'paper.pdf': OUT / 'mineocclude_evidence_extension.pdf',
        PAPER / 'paper.tex': OUT / 'paper_evidence_extension.tex',
        SOURCE / 'evidence_extension_outputs/mineocclude_evidence_extension_reproduction.zip': OUT / 'mineocclude_evidence_extension_reproduction.zip',
    }
    for source, dest in targets.items():
        assert not dest.exists(), dest
        shutil.copy2(source, dest)
        assert sha(source) == sha(dest)
    files = list(targets.values()) + [archive]
    save(OUT / 'evidence_extension_delivery_manifest.json', dict(
        status='LOCALLY_VERIFIED_LIVE_OVERLEAF_AND_ANONYMOUS_ACCESS_SEPARATE',
        files={p.name: dict(sha256=sha(p), bytes=p.stat().st_size) for p in files},
        overleaf_dependencies={name: sha(PAPER / name) for name in names},
        main_pages=8, references_start_page=9,
        clean_cpu_replay_sha256=sha(SOURCE / 'evidence_extension_outputs/clean_cpu_replay.json'),
        visual_review_sha256=sha(PAPER / 'visual_review.json'),
        anonymous_access_verified=False,
    ))
    print('REVIEWED_DELIVERY_PACKAGED', len(names), 'Overleaf dependencies', flush=True)


if __name__ == '__main__':
    main()

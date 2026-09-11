"""Verify delivered archives, unchanged earlier artifacts, and the clean TeX build."""
import hashlib
import json
from pathlib import Path
import zipfile


def main():
    source = Path(__file__).resolve().parents[2]
    output = source / 'output/pdf'
    checked = []
    for name in ['delivery_manifest.json', 'generalization_delivery_manifest.json']:
        manifest = json.loads((output / name).read_text())
        for filename, expected in manifest.items():
            data = (output / filename).read_bytes()
            assert len(data) == expected['bytes'], filename
            assert hashlib.sha256(data).hexdigest() == expected['sha256'], filename
            checked.append(filename)
    with zipfile.ZipFile(output / 'mineocclude_generalization_reproduction.zip') as archive:
        assert archive.testzip() is None
        inventory = json.loads(archive.read('COMBINED_FILES_SHA256.json'))
        for name, expected in inventory.items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == expected, name
        with zipfile.ZipFile(output / 'mineocclude_rgb_history_reproducibility.zip') as old:
            for info in old.infolist():
                if not info.is_dir():
                    assert old.read(info.filename) == archive.read('central/' + info.filename)
    paper = source / 'generalization_outputs/paper'
    clean = source / 'generalization_outputs/clean_overleaf_build'
    assert (paper / 'paper-layout.txt').read_text() == (clean / 'paper-layout.txt').read_text()
    log = (clean / 'paper.log').read_text(errors='replace')
    assert all(value not in log for value in ['Overfull', 'undefined', 'Missing character'])
    result = dict(status='PASS', delivered_and_preserved_files=checked,
                  combined_archive_files_verified=len(inventory), zip_crc='PASS',
                  original_central_package_byte_preservation='PASS',
                  clean_source_compile='PASS', clean_source_text_identical=True)
    (source / 'generalization_outputs/archive_verification.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

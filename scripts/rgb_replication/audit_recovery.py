"""Verify recovered artifacts; unpack only hash-verified safe archives."""
import argparse
import hashlib
import json
import math
import sys
import tarfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
PKG = ROOT / 'reproducibility/experiment_iii_a'
OUT = ROOT / 'replication_outputs'


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temp.replace(path)


def unpack(path, destination):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(path) as archive:
        members = archive.getmembers()
        for member in members:
            target = (destination / member.name).resolve()
            assert target.is_relative_to(destination), member.name
            assert member.isfile() or member.isdir(), member.name
            if target.is_file():
                incoming = archive.extractfile(member).read()
                assert hashlib.sha256(incoming).hexdigest() == sha(target), str(target)
        archive.extractall(destination, members=members)


def verify_list(base, manifest):
    count = 0
    for line in Path(manifest).read_text().splitlines():
        if not line.strip():
            continue
        expected, name = line.split(None, 1)
        name = name.lstrip('* ')
        path = (base / name).resolve()
        assert path.is_relative_to(base.resolve()), name
        assert sha(path) == expected, f'hash mismatch: {path}'
        count += 1
    return count


def audit_metadata():
    import numpy as np
    from mineocclude.experiment_iii.fir import frozen_kernel
    meta = ROOT / 'recovery_inputs/metadata'
    unpack(ROOT / 'recovery_inputs/trajectory_metadata.tar', meta)
    corpus = meta / 'data/experiment_iii/final_trajectories'
    lock_path = PKG / 'prediction_lock/PREDICTION_LOCK.json'
    assert sha(lock_path) == 'c3fc98384dfe9f69ac43c1b5436cd50f0eb353075c2460a2e3f40ef1f208800e'
    lock = read(lock_path)
    seal = lock.pop('prediction_lock_sha256')
    assert hashlib.sha256(json.dumps(lock, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest() == seal
    assert len(lock['cells']) == 23750
    targets = read(PKG / 'cohort/EXECUTED_TARGETS.json')['rows']
    index = read(PKG / 'cohort/CAPTURE_INDEX.json')['captures']
    folds = read(PKG / 'cohort/FOLD_ASSIGNMENTS.json')['folds']
    identities = {r['identity'] for r in targets}
    assert len(identities) == 25 and len(targets) == 2375
    held_all = []
    for fold in folds:
        held, train = map(set, (fold['held_out_identities'], fold['training_identities']))
        assert not held & train and held | train == identities
        assert len(held) == 5 and len(train) == 20
        held_all.extend(held)
        inner = [x for v in fold['inner_rotations'].values() for x in v]
        assert len(inner) == 20 and set(inner) == train
    assert len(held_all) == len(set(held_all)) == 25
    by_key = {(r['identity'], r['condition_id'], r['row_index']): r for r in targets}
    assert len(by_key) == 2375
    unique_cells = set()
    for cell in lock['cells']:
        key = cell['identity'], cell['condition_id'], cell['row_index']
        assert cell['target'] == by_key[key]['target']
        assert math.isfinite(cell['prediction'])
        full = (cell['model'],) + key
        assert full not in unique_cells
        unique_cells.add(full)
    max_fir_error = 0.0
    action_payloads = set()
    for unit, info in index.items():
        unit_path = corpus / 'captures' / unit
        coords = [json.loads(x) for x in (unit_path / 'coordinates.jsonl').read_text().splitlines()]
        positions = {int(x['server_tick']): x['axis_pos'] for x in coords}
        kernel = frozen_kernel(info['direction'])
        for row_idx, t in enumerate(info['target_model_frame_indices']):
            expected = math.fsum(kernel[k] * positions[t-k] for k in range(9))
            observed = by_key[(info['identity'], info['condition_id'], row_idx)]['target']
            max_fir_error = max(max_fir_error, abs(expected-observed))
        actions = [json.loads(x) for x in (unit_path / 'raw/actions.jsonl').read_text().splitlines()]
        for action in actions:
            action_payloads.add(json.dumps({k:v for k,v in action.items() if k not in {'episode_id','trajectory_id','server_tick','render_frame_idx','model_frame_idx','action_idx'}},sort_keys=True))
    assert max_fir_error < 1e-9, max_fir_error
    grouped = defaultdict(list)
    for cell in lock['cells']:
        grouped[(cell['model'],cell['condition_id'],cell['identity'])].append(cell)
    metrics = defaultdict(dict)
    for (model,cond,identity), rows in grouped.items():
        assert len(rows) == 19
        y = np.array([x['target'] for x in rows])
        p = np.array([x['prediction'] for x in rows])
        metrics[(model,cond)][identity] = {'rmse':float(np.sqrt(np.mean((y-p)**2))), 'mae':float(np.mean(abs(y-p))), 'r2':float(1-((y-p)**2).sum()/((y-y.mean())**2).sum())}
    summary = {f'{model}/{cond}': {metric:float(np.mean([r[metric] for r in entries.values()])) for metric in ('rmse','mae','r2')} for (model,cond),entries in metrics.items()}
    report = {'status':'METADATA_AND_PREDICTIONS_VERIFIED','prediction_raw_sha256':sha(lock_path),'canonical_seal':seal,'target_rows':len(targets),'prediction_cells':len(unique_cells),'fir_max_abs_error':max_fir_error,'unique_action_payloads':len(action_payloads),'action_examples':[json.loads(x) for x in sorted(action_payloads)[:3]],'legacy_summary':summary,'corpus_pngs_verified':False}
    save(OUT / 'recovery_audit.json',report)
    save(OUT / 'legacy_reconstructed_metrics.json',{'summary':summary,'per_identity':{f'{m}/{c}':v for (m,c),v in metrics.items()}})
    print(json.dumps(report,indent=2),flush=True)


def audit_frames():
    base = ROOT / 'recovery_inputs/metadata/data/experiment_iii/final_trajectories'
    dest = ROOT / 'recovery_inputs/corpus'
    for asset in read(base / 'ARCHIVES.json')['assets']:
        path = ROOT / 'recovery_inputs/archives' / asset['asset']
        assert path.stat().st_size == asset['bytes'], path
        assert sha(path) == asset['sha256'], path
        unpack(path,dest)
        print('ARCHIVE_VERIFIED',path.name,flush=True)
    count = verify_list(dest,base / 'SHA256SUMS.txt')
    assert count == 24500, count
    save(OUT / 'corpus_audit.json',{'status':'FULL_CORPUS_VERIFIED','files_verified':count,'pngs':len(list(dest.rglob('*.png'))),'manifest_sha256':sha(base / 'SHA256SUMS.txt')})
    print('FULL_CORPUS_VERIFIED',count,flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--frames',action='store_true')
    args = parser.parse_args()
    audit_frames() if args.frames else audit_metadata()

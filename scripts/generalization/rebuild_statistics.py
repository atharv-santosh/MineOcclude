"""Rebuild fresh-cohort statistics from compact held-out predictions, CPU only.

Usage: python rebuild_statistics.py --input predictions --output statistics.json
Requires only NumPy and the Python standard library. No Minecraft, weights,
activation tensors, or network access are required.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np

COHORTS = ['replication', 'geometry', 'speed']
CONDITIONS = ['L0', 'L4']
MODELS = ['MW_RGB_L19', 'PIXEL_CURRENT', 'PIXEL_HISTORY16', 'DIRECTION_AGE',
          'ORACLE_LAST_SEEN', 'ORACLE_CONSTANT_VELOCITY', 'TRAINING_MEAN']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity_metrics(target, prediction):
    target = np.asarray(target, dtype=np.float64)
    prediction = np.asarray(prediction, dtype=np.float64)
    residual = prediction - target
    denominator = np.sum((target - target.mean()) ** 2)
    assert denominator > 0
    return dict(rmse=float(np.sqrt(np.mean(residual ** 2))),
                mae=float(np.mean(np.abs(residual))),
                r2=float(1 - np.sum(residual ** 2) / denominator))


def interval(values, indices):
    values = np.asarray(values, dtype=np.float64)
    means = values[indices].mean(axis=1)
    lo, hi = np.quantile(means, [.025, .975])
    return dict(mean=float(values.mean()), ci95=[float(lo), float(hi)])


def rebuild(directory):
    directory = Path(directory)
    paths = sorted(directory.glob('*.json'))
    cells = []
    for path in paths:
        cells.extend(json.loads(path.read_text())['cells'])
    assert len(cells) == 75 * 2 * 19 * 7, len(cells)
    grouped = {}
    seen = set()
    truths = {}
    fold_ids = {}
    for c in cells:
        assert np.isfinite([c['target'], c['prediction']]).all()
        assert c['cohort'] in COHORTS and c['condition_id'] in CONDITIONS and c['model'] in MODELS
        key = (c['cohort'], c['condition_id'], c['model'], c['identity'])
        cell_key = key + (c['row_index'],)
        assert cell_key not in seen, cell_key
        seen.add(cell_key)
        grouped.setdefault(key, []).append(c)
        truth_key = (c['identity'], c['row_index'])
        value = (c['target'], c['model_frame_idx'], c['context_age'], c['outer_fold'])
        if truth_key in truths:
            assert truths[truth_key] == value, truth_key
        truths[truth_key] = value
        if c['identity'] in fold_ids:
            assert fold_ids[c['identity']] == c['outer_fold']
        fold_ids[c['identity']] = c['outer_fold']
    metrics = {}
    age_metrics = {}
    for key, rows in grouped.items():
        rows.sort(key=lambda c: c['row_index'])
        assert [r['row_index'] for r in rows] == list(range(19))
        assert [r['context_age'] for r in rows] == list(range(1, 20))
        metrics[key] = identity_metrics([r['target'] for r in rows], [r['prediction'] for r in rows])
        for lo, hi in [(1, 5), (6, 10), (11, 15), (16, 19)]:
            selection = [r for r in rows if lo <= r['context_age'] <= hi]
            age_metrics[key + (f'{lo}-{hi}',)] = float(np.sqrt(np.mean([(r['prediction'] - r['target']) ** 2 for r in selection])))
    summaries = []
    contrasts = []
    ages = []
    for cohort in COHORTS:
        ids = sorted({key[3] for key in metrics if key[0] == cohort})
        assert len(ids) == 25
        assert all(sum(fold_ids[i] == f for i in ids) == 5 for f in range(5))
        # Same index draws across all conditions and models preserve pairing.
        indices = np.random.default_rng(20260911).integers(0, 25, size=(10000, 25))
        for condition in CONDITIONS:
            for model in MODELS:
                summaries.append(dict(cohort=cohort, condition=condition, model=model,
                    **{m: interval([metrics[cohort, condition, model, i][m] for i in ids], indices)
                       for m in ['rmse', 'mae', 'r2']}))
                for bin_name in ['1-5', '6-10', '11-15', '16-19']:
                    ages.append(dict(cohort=cohort, condition=condition, model=model, age_bin=bin_name,
                        rmse=interval([age_metrics[cohort, condition, model, i, bin_name] for i in ids], indices)))
            for comparator in [m for m in MODELS if m != 'MW_RGB_L19']:
                values = [metrics[cohort, condition, 'MW_RGB_L19', i]['rmse'] -
                          metrics[cohort, condition, comparator, i]['rmse'] for i in ids]
                contrasts.append(dict(cohort=cohort, condition=condition,
                    contrast=f'MW_RGB_L19-minus-{comparator}', **interval(values, indices)))
        values = [metrics[cohort, 'L4', 'MW_RGB_L19', i]['rmse'] -
                  metrics[cohort, 'L0', 'MW_RGB_L19', i]['rmse'] for i in ids]
        contrasts.append(dict(cohort=cohort, condition='PAIRED', contrast='MW-stone-minus-air', **interval(values, indices)))
    return dict(schema='mineocclude-fresh-statistics-v1', cells=len(cells), identities=75,
                bootstrap=dict(seed=20260911, draws=10000, unit='identity within cohort',
                    interpretation='Percentile intervals conditional on fitted probes; not simultaneous and not probe-refitting intervals.'),
                input_sha256={p.name: digest(p) for p in paths}, summaries=summaries,
                paired_contrasts=contrasts, age_bins=ages,
                per_identity=[dict(cohort=k[0], condition=k[1], model=k[2], identity=k[3], **v) for k, v in sorted(metrics.items())])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = rebuild(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print('REBUILT', result['cells'], 'cells, 75 identities, 42 model/condition/cohort summaries')

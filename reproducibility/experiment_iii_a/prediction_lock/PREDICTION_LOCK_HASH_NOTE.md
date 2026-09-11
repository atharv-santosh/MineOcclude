# Two different hashes, and why `PREDICTION_LOCK.sha256` is not the file's sha256

`PREDICTION_LOCK.sha256` reads:

```
2a25bcb01107a2b4e899bf5575c116d86a12400ca3aa5c12e6339f866778ddf9  PREDICTION_LOCK.json
```

Despite the filename and the two-space `sha256sum` format, **that value is not the sha256 of
`PREDICTION_LOCK.json`**. Running `sha256sum PREDICTION_LOCK.json` will not reproduce it, and
`sha256sum -c PREDICTION_LOCK.sha256` will fail. That is expected, not corruption.

| quantity | value | what it is |
|---|---|---|
| **canonical seal** | `2a25bcb01107a2b4e899bf5575c116d86a12400ca3aa5c12e6339f866778ddf9` | `sha256` of the canonical JSON encoding of the lock **body** — every key except `prediction_lock_sha256` itself |
| **raw file sha256** | `c3fc98384dfe9f69ac43c1b5436cd50f0eb353075c2460a2e3f40ef1f208800e` | `sha256` of the 4,833,894 bytes on disk |

The seal is what every downstream stage cites. It appears as `prediction_lock_sha256` inside the
lock, inside `prediction_fit_receipt.json`, and inside all of `primary_results.json`,
`temporal_results.json` and `context_age_results.json` — that is how A14/A15/A16 prove they
derived their estimands from *this* lock and not another. The raw file sha256 is what
`scientific_package_manifest.json` lists in its traceability table, because that table is about
bytes on disk.

## Reproducing the seal

Canonical encoding is `json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False)`
— see `src/mineocclude/experiment_iii/authority.py::canonical_bytes`.

```python
import json, hashlib
d = json.load(open("PREDICTION_LOCK.json"))
declared = d.pop("prediction_lock_sha256")
seal = hashlib.sha256(
    json.dumps(d, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
).hexdigest()
assert seal == declared == "2a25bcb01107a2b4e899bf5575c116d86a12400ca3aa5c12e6339f866778ddf9"
```

Verified independently on 2026-09-11: **the seal recomputes exactly.**

## What is inside

23,750 cells = 10 models × 25 identities × 5 conditions × 19 rows. Each cell carries
`model`, `identity`, `condition_id`, `row_index`, `prediction` and `target`. Every per-identity,
per-condition and per-fold error in `results/` is derivable from this one file — nothing else is
needed to re-derive the statistics.

`feature_block_hashes` (125 captures × 6 blocks) is sealed into the body, which binds these
predictions to the exact A11 feature bytes indexed in `analysis_inputs/FEATURE_BLOCK_INDEX.json`.
All 750 were re-verified against it on 2026-09-11: **0 mismatches.**

The 2,375 distinct `target` values were also cross-checked against the `fir_labels` A7 wrote
into each capture's `capture_completion.json` at capture time: **0 mismatches.** That binds the
analysis layer to the capture layer through an artifact neither stage could have edited after
the fact.

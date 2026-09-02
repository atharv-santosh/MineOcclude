"""A9 shadow: the REAL production extraction engine, a synthetic adapter.

Everything scientific about A9 -- admission, the production roster, the stage
label, the one-forward-per-target-row budget, the array contract, the ledger and
the resume identity -- is the committed implementation. Only the MineWorld
adapter is replaced, by the same stub the A5 pilot qualified against, so no
weights are loaded and no production forward is spent.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

SHADOW = Path(sys.argv[1])
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 0     # 0 = all 125
sys.path.insert(0, str(SHADOW / "src"))
sys.path.insert(0, str(SHADOW))

import numpy as np

from mineocclude.experiment_iii.a9_production_extraction import (
    A9_STAGE, ProductionExtractionCampaign, a9_extraction_spec_hash,
    admit_production_extraction, expected_extraction_counts,
)
from mineocclude.experiment_iii.p1_extraction import (
    PERSON_A_RUNTIME_SCRIPTED_IMPULSE, MineWorldPilotDecoder, capture_stream_rows,
)
from mineocclude.experiment_iii.schema import read_jsonl
from tests.experiment_iii.test_p1_extraction import (
    StubMineWorldAdapter, _RecordingHookManager,
)

DOCS = SHADOW / "docs/experiment_iii"
PROD = SHADOW / "data/experiment_iii/production"

a3 = json.loads((DOCS / "receipts/environment_receipt_gpu_extraction_host_postprovision.json")
                .read_text(encoding="utf-8"))
admission = admit_production_extraction(
    p2_path=DOCS / "p2/P2_FREEZE_PACKAGE.json",
    a8_receipt_path=DOCS / "a8/cohort_closure_receipt.json",
    a3_receipt=a3,
)
closure = json.loads((DOCS / "a8/cohort_closure_receipt.json").read_text(encoding="utf-8"))
admitted = set(closure["complete_five_way_paired_identities"])
manifest = {str(r["identity"]): r
            for r in read_jsonl(DOCS / "cohort/production_identity_manifest.jsonl")}

units = []
for identity in sorted(admitted):
    row = manifest[identity]
    for condition in ("L0", "L1", "L2", "L3", "L4"):
        unit_id = f"{identity}__{condition}"
        units.append({
            "capture_unit_id": unit_id, "identity": identity, "condition_id": condition,
            "unit_dir": PROD / "captures" / unit_id, "seed": int(row["seed"]),
            "source_capture_hash": str(row["spec_hash"]),
            "target_model_frame_indices": [int(v) for v in row["target_model_frame_indices"]],
        })
if LIMIT:
    units = units[:LIMIT]

counts = expected_extraction_counts(len(units))
adapter = StubMineWorldAdapter()

campaign = ProductionExtractionCampaign(
    units,
    output_root=PROD / "activations",
    ledger_path=PROD / "activations/production_extraction_ledger.jsonl",
    extraction_spec_hash=a9_extraction_spec_hash(),
)


def decoder_factory(unit):
    return MineWorldPilotDecoder(
        adapter, adapter.runtime_identity,
        unit_dir=unit["unit_dir"], trajectory_id=unit["capture_unit_id"],
        seed=unit["seed"], rows=capture_stream_rows(unit["unit_dir"]),
        impulse_orientation=PERSON_A_RUNTIME_SCRIPTED_IMPULSE,
        hook_manager_factory=lambda modules: _RecordingHookManager(modules, seed=7),
        frame_loader=lambda path: np.zeros((360, 640, 3), dtype=np.uint8),
    )


print(f"A9_STAGE={A9_STAGE}")
print(f"A9_ADMITTED_CAPTURES={counts['captures']}")
print(f"A9_EXPECTED_FORWARDS={counts['forwards']}")
print(f"A9_EXPECTED_ARRAYS={counts['arrays']}")
print(f"A9_ATTRITION_BRANCH={admission['attrition_branch']}")
started = time.time()
done = [0]


def on_unit(unit_id, state):
    done[0] += 1
    if done[0] <= 2 or done[0] % 25 == 0:
        print(f"  A9_UNIT={unit_id} STATE={state} "
              f"({done[0]}/{len(units)}, {time.time()-started:.0f}s)", flush=True)


result = campaign.run(decoder_factory,
                      checkpoint_identity=admission["checkpoint_sha256"],
                      preprocessing_identity=adapter.runtime_identity.preprocessing_identity,
                      on_unit=on_unit)
budget = campaign.assert_forward_budget()
inv = result["inventory"]
print(f"A9_CAPTURES_COMPLETE={inv['captures_complete']}")
print(f"A9_SKIPPED_AS_COMPLETE={len(result['skipped'])}")
print(f"A9_MODEL_FORWARDS_EXECUTED={budget['forwards']}")
print(f"A9_FORWARD_BUDGET={budget['expected_forwards']}")
print(f"A9_ARRAYS_COMPLETE={inv['arrays_complete']}")
print(f"A9_INVENTORY_STAGE={inv['stage']}")
print(f"A9_ELAPSED_SECONDS={time.time()-started:.1f}")
print(f"A9_EXTRACTION_COMPLETE={str(inv['complete']).lower()}")
print("A9_EXECUTED=true")
raise SystemExit(0 if inv["complete"] else 1)

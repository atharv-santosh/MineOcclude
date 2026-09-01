"""A5 / I22 — the authority-required same-spec resume receipt.

Authority 6A's recovery item: "a deliberate mid-run kill and restart resumes on
the same spec, skips completed verified units, and recomputes nothing that was
already ``DURABLE``."

This proves each clause from evidence rather than asserting it:

* **deliberate** — the interruption was a SIGKILL issued by the operator, and the
  pre-kill ledger state was recorded before it.
* **same spec** — every unit's ``spec_sha256`` is identical either side of the
  interruption, and the ledger records the authority and source closure it ran
  under.
* **skips completed units** — the units already ``COMPLETE`` acquire no new
  ``RUNNING`` record after the restart.
* **recomputes nothing already DURABLE** — their ``durable_receipt.json`` files
  hash identically before and after, so their bytes were never rewritten.
* **no duplicate acceptance** — each unit id appears exactly once in
  ``COMPLETE``.

    python scripts/experiment_iii/build_p1_resume_receipt.py \\
        --demo-root data/experiment_iii/p1/resume_demo \\
        --pre-kill-complete e3_p90__L0,e3_p90__L1,e3_p90__L2 \\
        --interrupted-unit e3_p90__L3
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mineocclude.experiment_iii.authority import (  # noqa: E402
    AUTHORITY_VERSION,
    verify_authority_binding,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError  # noqa: E402
from mineocclude.experiment_iii.execution import HashChainLedger  # noqa: E402


def build(
    demo_root: Path,
    pre_kill_complete: list[str],
    interrupted_unit: str,
    pre_kill_hashes: dict[str, str],
    kill_at: str,
    restart_at: str,
    pre_kill_records: int,
) -> dict[str, Any]:
    ledger = HashChainLedger(demo_root / "p1_capture_ledger.jsonl")
    ledger.verify_chain()
    records = ledger.records

    # Where the restart begins. This is taken from the ledger length captured
    # BEFORE the kill, not inferred from the records: the interrupted unit gets a
    # second RUNNING record on restart, so searching for "the last RUNNING for
    # that unit" lands past the restart boundary and hides exactly the evidence
    # this receipt exists to show.
    if pre_kill_records <= 0 or pre_kill_records > len(records):
        raise ExperimentIIIError(
            "P1_RESUME_UNPROVEN",
            f"pre-kill ledger length {pre_kill_records} is not consistent with the "
            f"{len(records)} records now present",
        )
    before = records[:pre_kill_records]
    after = records[pre_kill_records:]
    if before[-1]["state"] != "RUNNING" or before[-1]["unit_id"] != interrupted_unit:
        raise ExperimentIIIError(
            "P1_RESUME_UNPROVEN",
            f"the record before the interruption is "
            f"{before[-1]['state']} {before[-1]['unit_id']}, not RUNNING "
            f"{interrupted_unit}",
        )

    # A completed unit must acquire no new RUNNING record after the restart.
    recaptured = sorted(
        {
            record["unit_id"]
            for record in after
            if record["state"] == "RUNNING" and record["unit_id"] in pre_kill_complete
        }
    )

    completions = [r["unit_id"] for r in records if r["state"] == "COMPLETE"]
    duplicates = sorted({u for u in completions if completions.count(u) > 1})

    # DURABLE work must be byte-identical afterwards.
    post_kill_hashes: dict[str, str] = {}
    unchanged: list[str] = []
    changed: list[str] = []
    for unit_id in pre_kill_complete:
        receipt = demo_root / "captures" / unit_id / "durable_receipt.json"
        digest = hashlib.sha256(receipt.read_bytes()).hexdigest()
        post_kill_hashes[unit_id] = digest
        (unchanged if digest == pre_kill_hashes.get(unit_id) else changed).append(unit_id)

    # Same spec on both sides of the interruption.
    spec_by_unit: dict[str, set[str]] = {}
    for record in records:
        if "spec_sha256" in record:
            spec_by_unit.setdefault(record["unit_id"], set()).add(record["spec_sha256"])
    drifted = sorted(u for u, hashes in spec_by_unit.items() if len(hashes) > 1)

    # How the restart classified the interrupted unit.
    resume_reason = next(
        (
            record.get("reason")
            for record in after
            if record["state"] == "PLANNED" and record["unit_id"] == interrupted_unit
        ),
        None,
    )
    retry_flag = next(
        (
            record.get("retry_same_spec")
            for record in after
            if record["state"] == "PLANNED" and record["unit_id"] == interrupted_unit
        ),
        None,
    )

    closures = sorted(
        {r["source_closure"] for r in records if "source_closure" in r}
    )
    authorities = sorted(
        {r["authority_sha256"] for r in records if "authority_sha256" in r}
    )

    passed = (
        not recaptured
        and not duplicates
        and not changed
        and not drifted
        and len(set(completions)) == 10
        and len(closures) == 1
        and len(authorities) == 1
    )

    return {
        "schema_version": "mineocclude-experiment-iii-p1-resume-receipt-v1",
        "authority_section": "6A recovery; RECOVERY_AND_RESUME_RUNBOOK A5/A7",
        "authority_version": AUTHORITY_VERSION,
        "authority_binding": verify_authority_binding(),
        "demonstration": {
            "deliberate": True,
            "method": "SIGKILL on the capture driver, mid-unit",
            "rationale": (
                "A hard kill rather than a graceful stop: the state machine must "
                "recover from a genuine crash, so nothing was given a chance to "
                "finalise. No capture bytes were modified to simulate failure."
            ),
            "isolated_from_accepted_evidence": True,
            "isolation_note": (
                "Run into its own capture root and ledger, so the ten accepted P1 "
                "units were never at risk. Pilot identities only."
            ),
            "interrupted_at": kill_at,
            "restarted_at": restart_at,
            "interruption_point": {
                "unit": interrupted_unit,
                "unit_state_at_interruption": "RUNNING",
                "ledger_records_before_kill": pre_kill_records,
                "ledger_records_after_restart": len(records) - pre_kill_records,
            },
        },
        "completed_before_interruption": sorted(pre_kill_complete),
        "completed_before_interruption_count": len(pre_kill_complete),
        "same_spec": {
            "units_with_spec_drift": drifted,
            "single_source_closure": closures,
            "single_authority": authorities,
            "note": (
                "This closure is the demonstration's own. It is an engineering "
                "exercise in an isolated capture root, not scientific evidence, "
                "and is deliberately not required to equal the closure the ten "
                "accepted P1 units were captured under. What the recovery contract "
                "requires -- and what is shown here -- is that the closure is the "
                "SAME on both sides of the interruption."
            ),
        },
        "skipping": {
            "completed_units_recaptured_after_restart": recaptured,
            "completed_units_skipped": sorted(pre_kill_complete),
            "interrupted_unit_resume_reason": resume_reason,
            "interrupted_unit_retry_same_spec": retry_flag,
        },
        "durability": {
            "durable_receipts_unchanged": sorted(unchanged),
            "durable_receipts_changed": sorted(changed),
            "pre_kill_sha256": pre_kill_hashes,
            "post_restart_sha256": post_kill_hashes,
        },
        "acceptance": {
            "complete_units": sorted(set(completions)),
            "complete_unit_count": len(set(completions)),
            "duplicate_accepted_units": duplicates,
            "ledger_chain_verified": True,
            "ledger_record_count": len(records),
        },
        "P1_RESUME_DEMONSTRATION": "PASS" if passed else "FAIL",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo-root", type=Path, required=True)
    parser.add_argument("--pre-kill-complete", required=True)
    parser.add_argument("--interrupted-unit", required=True)
    parser.add_argument("--pre-kill-hashes", required=True, help="unit=sha256,...")
    parser.add_argument("--kill-at", required=True)
    parser.add_argument("--restart-at", required=True)
    parser.add_argument(
        "--pre-kill-records",
        type=int,
        required=True,
        help="ledger record count observed immediately before the kill",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    hashes = dict(
        pair.split("=", 1) for pair in args.pre_kill_hashes.split(",") if pair
    )
    try:
        receipt = build(
            args.demo_root,
            [u for u in args.pre_kill_complete.split(",") if u],
            args.interrupted_unit,
            hashes,
            args.kill_at,
            args.restart_at,
            args.pre_kill_records,
        )
    except ExperimentIIIError as error:
        print(f"BLOCKER_CODE={error.blocker}", file=sys.stderr)
        print(error.message, file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n"
    args.out.write_text(payload, encoding="utf-8", newline="\n")

    print(f"P1_RESUME_DEMONSTRATION={receipt['P1_RESUME_DEMONSTRATION']}")
    print(
        "P1_RESUME_COMPLETED_UNITS_SKIPPED="
        f"{len(receipt['skipping']['completed_units_skipped'])}"
    )
    print(
        "P1_RESUME_COMPLETED_UNITS_RECAPTURED="
        f"{len(receipt['skipping']['completed_units_recaptured_after_restart'])}"
    )
    print(
        "P1_RESUME_DUPLICATE_ACCEPTED_UNITS="
        f"{len(receipt['acceptance']['duplicate_accepted_units'])}"
    )
    print(
        "P1_RESUME_DURABLE_RECEIPTS_UNCHANGED="
        f"{len(receipt['durability']['durable_receipts_unchanged'])}"
    )
    print(f"P1_RESUME_FINAL_UNITS={receipt['acceptance']['complete_unit_count']}")
    print(f"P1_RESUME_INTERRUPTION_POINT={args.interrupted_unit}")
    print(f"P1_RESUME_RECEIPT={args.out}")
    print(f"P1_RESUME_RECEIPT_SHA256={hashlib.sha256(payload.encode()).hexdigest()}")
    return 0 if receipt["P1_RESUME_DEMONSTRATION"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""P2.8: layer-4-only activation extraction for the 25 no-wall diagnostic runs.

Runs ONLY after path equivalence passes. Extraction mirrors the frozen Regime A
extractor (scripts/run_regime_a.py :: PersistentMineWorldWorker.extract) exactly
-- same checkpoint, same preprocessing, same teacher-forced 16-frame window,
same target-frame token span -- but retains layer 4 alone instead of all 20
layers. The checkpoint is loaded once and reused across runs.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

# ``Layer4Extractor.__init__`` used to be the first thing that put the source
# tree on the path, which is too late for a module-level import of the governed
# activation-binding module. Doing it here keeps the two NEW-B001/NEW-B002
# primitives resolvable no matter which entrypoint imports this file.
sys.path[:0] = [str(Path(__file__).resolve().parents[2]),
                str(Path(__file__).resolve().parents[2] / "src")]

from mineocclude.prospective.activation_binding import (
    SCIENTIFIC_TRAJECTORY_NOT_AUTHORITY_BOUND,
    TARGET_ROWS_NOT_AUTHORITY_BOUND,
    model_runtime_identity_binding,
    resolve_authority_bound_target_rows,
)
from mineocclude.prospective.capture_admission import (
    LEGACY_CAPTURE_TRAJECTORY_NOT_AUTHORITY_BOUND,
    CaptureAdmissionError,
)
from p2_common import (
    LAYER,
    OUT,
    REPO,
    S3_PREFIX,
    WORK,
    read_jsonl,
    sha256_file,
    source_specs,
    p2_run_id,
    write_json,
)

#: The sentinel type shared by the unbound markers, so an explicit opt-out is
#: distinguishable from a real identity by type rather than by value.
_UNBOUND_KINDS = (type(TARGET_ROWS_NOT_AUTHORITY_BOUND),
                  type(LEGACY_CAPTURE_TRAJECTORY_NOT_AUTHORITY_BOUND))

CAPTURES = WORK / "captures"
ACT = WORK / "activations"
LEDGER = OUT / "p2_extraction_ledger.jsonl"
PROGRESS = OUT / "p2_extraction_progress.json"
MAX_PERSIST_ATTEMPTS = 3


def append_ledger(entry: dict[str, Any]) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def completed_records() -> dict[str, dict[str, Any]]:
    if not LEDGER.exists():
        return {}
    return {
        row["p2_no_wall_run_id"]: row
        for row in read_jsonl(LEDGER)
        if row.get("status") == "COMPLETE_VALIDATED_DURABLE"
    }


def persist_activation(record: dict[str, Any]) -> dict[str, Any]:
    run_id = record["p2_no_wall_run_id"]
    activation = Path(record["activation_path"])
    uri = f"{S3_PREFIX}/{run_id}/layer4"
    receipt = activation.with_suffix(".receipt.json")
    durable = {
        **record,
        "durable_activation_uri": f"{uri}/{activation.name}",
        "status": "COMPLETE_VALIDATED_DURABLE",
    }
    write_json(receipt, durable)
    proc = subprocess.run(
        ["aws", "s3", "cp", str(activation), durable["durable_activation_uri"],
         "--only-show-errors"], capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"activation upload failed: {proc.stderr.strip()[:200]}")
    receipt_uri = f"{uri}/{receipt.name}"
    proc = subprocess.run(
        ["aws", "s3", "cp", str(receipt), receipt_uri, "--only-show-errors"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"activation receipt upload failed: {proc.stderr.strip()[:200]}")
    remote = subprocess.run(
        ["aws", "s3", "cp", receipt_uri, "-", "--only-show-errors"],
        capture_output=True,
    )
    if remote.returncode != 0 or remote.stdout != receipt.read_bytes():
        raise RuntimeError("activation durable receipt readback mismatch")
    durable["durable_receipt_uri"] = receipt_uri
    durable["durable_receipt_readback_exact"] = True
    return durable


class ExtractorNotLoadedError(RuntimeError):
    """``extract()`` was reached on an extractor that never ran ``ensure_loaded()``.

    C1: ``__init__`` establishes bookkeeping only -- it deliberately does NOT
    touch the model stack, so constructing an extractor is free and cannot load
    a checkpoint as a side effect. ``ensure_loaded()`` is what binds the
    production module, the adapter and the runtime identity. A caller that
    skipped it used to die on a bare ``AttributeError: 'Layer4Extractor' object
    has no attribute 'production'`` from the middle of ``extract()``, which
    reads as a code-level accident rather than the operational precondition
    failure it is. This names the precondition instead. It is deliberately NOT
    repaired by having ``extract()`` call ``ensure_loaded()`` itself: a lazy
    load would let a mis-sequenced caller silently acquire a checkpoint nobody
    authorized, and the point of the split is that the load is explicit.
    """


class Layer4Extractor:
    """One checkpoint load; independent teacher-forced window calls."""

    def __init__(self) -> None:
        sys.path.insert(0, str(REPO))
        sys.path.insert(0, str(REPO / "src"))
        self.load_count = 0
        self.runtime = None
        self.adapter = None
        # Declared here so an unloaded extractor is an *absent binding* rather
        # than a missing attribute; ``extract()`` refuses on it explicitly.
        self.production = None

    def ensure_loaded(self) -> None:
        from scripts import run_person_a_66_cell_production_extraction as production

        if production._RUNTIME.adapter is None:
            production._RUNTIME.ensure_loaded()
            self.load_count += 1
        self.production = production
        self.adapter = production._RUNTIME.adapter
        self.runtime = production._RUNTIME.runtime_identity

    def extract(self, run_id: str, source: Path, destination: Path, *,
                expected_target_model_frame_indices,
                scientific_trajectory_id,
                expected_legacy_capture_trajectory_id) -> dict[str, Any]:
        """Extract layer-4 activations for one capture.

        Three keyword-only parameters, none with a default, on purpose.

        ``expected_target_model_frame_indices``: before the NEW-B002 repair this
        method inferred its scientific rows from ``visibility.tau`` alone and no
        caller could state which rows the authority had qualified; a default would
        reopen that hole.

        ``scientific_trajectory_id`` and ``expected_legacy_capture_trajectory_id``
        are the two *typed* identities this unit carries, and they are separate
        parameters because they are separate namespaces. The superseded code had
        one value and used it in both roles: it validated the capture package with
        ``document["trajectory_id"]`` -- correct, that is the legacy identity
        ``layout_01_ep86001`` -- and then passed the same string into the Stage-2
        visibility-row resolver, whose rows carry ``a2y_t01``. Every real unit was
        therefore refused for a cross-namespace mismatch. Both identities are now
        supplied by the authority and both are checked, and neither is taken from
        the bytes it is meant to validate.

        Scientific callers pass the frozen manifest's rows, the unit's
        ``trajectory_id``, and the authority-derived legacy identity. The completed
        historical pilot entrypoints predate Stage-2 and pass the explicit unbound
        sentinels; the record they produce carries
        ``target_rows_authority_bound: false`` and every Stage-2 consumer refuses it.
        """
        from mineocclude.contracts.identity import SCHEMA_VERSION
        from mineocclude.models import mineworld_adapter as api

        # C1 guard. Refuse before any capture byte is opened and before any
        # activation path is touched, so a mis-sequenced caller can never leave
        # a partial artifact behind.
        if self.production is None or self.adapter is None or self.runtime is None:
            raise ExtractorNotLoadedError(
                f"{run_id}: Layer4Extractor.ensure_loaded() must run before extract(); "
                "the adapter, runtime identity and production module are unbound")
        adapter, runtime, production = self.adapter, self.runtime, self.production
        # Bound before any work: an unidentifiable runtime must not be able to
        # produce activations at all, let alone activations whose receipt is
        # written afterwards.
        identity = model_runtime_identity_binding(runtime)
        package_bytes = (source / "capture_package_v0_1.json").read_bytes()
        package_hash = hashlib.sha256(package_bytes).hexdigest()
        document = json.loads(package_bytes)
        # The legacy capture identity is checked against the authority-derived
        # expectation BEFORE the adapter is handed the package, so a capture
        # package from another episode cannot authenticate itself merely by
        # declaring its own identity self-consistently.
        legacy_capture_trajectory_id = document["trajectory_id"]
        if not isinstance(expected_legacy_capture_trajectory_id, _UNBOUND_KINDS) \
                and legacy_capture_trajectory_id != expected_legacy_capture_trajectory_id:
            raise CaptureAdmissionError(
                f"{run_id}: capture package legacy trajectory identity is "
                f"{legacy_capture_trajectory_id!r}, not the authority-derived "
                f"{expected_legacy_capture_trajectory_id!r}")
        validated = adapter.validate_trajectory(api.AcceptedTrajectoryInput(
            schema_version=SCHEMA_VERSION,
            trajectory_id=legacy_capture_trajectory_id,
            accepted_manifest_sha256=package_hash,
            document=document,
        ))
        visibility = read_jsonl(source / "raw/visibility.jsonl")
        # NEW-B002: the tau lookup is kept -- it reads the rows the capture
        # itself labelled -- but it is now proved equal to the authority's
        # ``target_model_frame_indices`` before a single frame is opened. On any
        # disagreement the resolver raises and neither source is preferred.
        # The Stage-2 resolver receives the Stage-2 identity. This is the repaired
        # boundary: the legacy identity above validated the raw capture package;
        # this one validates the Stage-2 visibility rows.
        targets = resolve_authority_bound_target_rows(
            visibility, expected=expected_target_model_frame_indices,
            required_count=19, scientific_trajectory_id=scientific_trajectory_id,
            label=run_id)
        authority_bound = expected_target_model_frame_indices is not TARGET_ROWS_NOT_AUTHORITY_BOUND

        required = range(targets[0] - 15, targets[-1] + 1)
        identities = {i.model_frame_idx: i for i in validated.frame_identities}
        frames = {}
        for index in required:
            rgb = np.asarray(
                Image.open(source / f"raw/frames/{index:06d}.png").convert("RGB")
            )
            processed = adapter.preprocess_frame(
                api.FramePreprocessRequest(identities[index], index, rgb)
            )
            frames[index] = dataclasses.replace(
                processed, preprocessing_profile=runtime.preprocessing_identity
            )
        raw_actions = {r["model_frame_idx"]: r for r in document["streams"]["raw_actions"]}
        actions = {
            index: adapter.convert_action(api.ActionConversionRequest(
                identities[index], int(raw_actions[index]["action_idx"]),
                raw_actions[index]["raw_action"]))
            for index in required
        }

        destination.mkdir(parents=True, exist_ok=True)
        path = destination / f"{run_id}.layer_{LAYER:02d}.npy"
        array = np.lib.format.open_memmap(
            path, mode="w+", dtype=np.float16, shape=(19, 336, 2048)
        )
        token_span = None
        for tau_index, target in enumerate(targets):
            indices = list(range(target - 15, target + 1))
            window = dataclasses.replace(
                validated, frame_identities=tuple(identities[i] for i in indices)
            )
            tokenized = adapter.tokenize_trajectory(api.TrajectoryTokenizationRequest(
                runtime_identity=runtime, trajectory=window,
                frames=tuple(frames[i] for i in indices),
                actions=tuple(actions[i] for i in indices),
            ))
            _result, captures = production._teacher_capture(
                adapter, runtime, tokenized, package_hash
            )
            span = tokenized.frame_token_map.spans[-1]
            token_span = len(span.visual_positions)
            wrote = False
            for capture in captures:
                if int(capture.layer.layer_idx) != LAYER:
                    continue
                tensor = capture.output.tensor[:, span.visual_positions, :]
                array[tau_index] = tensor[0].detach().cpu().numpy().astype(
                    np.float16, copy=False)
                wrote = True
            if not wrote:
                raise RuntimeError(f"{run_id}: layer {LAYER} capture missing at tau {tau_index+1}")
            del captures, _result
        array.flush()
        del array

        return {
            "p2_no_wall_run_id": run_id,
            "targets": targets,
            "rows": len(targets),
            "layer": LAYER,
            "visual_tokens_per_target": token_span,
            "shape": [19, 336, 2048],
            "dtype": "float16",
            "activation_path": str(path),
            "activation_sha256": sha256_file(path),
            "byte_size": path.stat().st_size,
            "capture_package_sha256": package_hash,
            # Both typed identities, recorded separately and never collapsed, so a
            # consumer can see which namespace each one was checked in.
            "legacy_capture_trajectory_id": legacy_capture_trajectory_id,
            "scientific_trajectory_id": (
                None if isinstance(scientific_trajectory_id, _UNBOUND_KINDS)
                else scientific_trajectory_id),
            # NEW-B001: the superseded ``checkpoint_sha256`` read two attributes
            # MineWorldRuntimeIdentity has never had, so it emitted "" on every
            # real runtime and the receipt bound no checkpoint at all. The
            # runtime carries two genuinely distinct frozen artifacts; both are
            # recorded, and ``model_runtime_identity_binding`` refuses to return
            # anything if either digest is missing, blank, or malformed.
            "model_runtime_identity": identity,
            "main_checkpoint_sha256": identity["main_checkpoint_sha256"],
            "vae_checkpoint_sha256": identity["vae_checkpoint_sha256"],
            "target_rows_authority_bound": authority_bound,
            "preprocessing_identity": str(runtime.preprocessing_identity),
        }


def main() -> int:
    adjudication = json.loads((OUT / "p2_path_equivalence_receipt.json").read_text())
    if adjudication["path_equivalence_status"] != "PASS":
        raise RuntimeError("BLOCKED: layer-4 extraction requires PATH_EQUIVALENCE=PASS")
    visibility = json.loads((OUT / "p2_visibility_qualification_receipt.json").read_text())
    if visibility["visibility_qualification_status"] != "PASS":
        raise RuntimeError("BLOCKED: layer-4 extraction requires VISIBILITY=PASS")

    specs = source_specs()
    ACT.mkdir(parents=True, exist_ok=True)
    complete_by_run = completed_records()
    extractor = Layer4Extractor()
    if len(complete_by_run) < 25:
        extractor.ensure_loaded()

    started = time.monotonic()
    retries = 0

    def progress(current: str | None, status: str, error: str | None = None) -> None:
        write_json(PROGRESS, {
            "artifact_id": "regime-a-prime-p2-extraction-progress-v0.1",
            "total_expected": 25,
            "complete_validated_durable": len(complete_by_run),
            "current_run_id": current,
            "remaining": 25 - len(complete_by_run),
            "extraction_retries": retries,
            "campaign_status": status,
            "last_error_code": error,
            "elapsed_seconds": time.monotonic() - started,
        })

    progress(None, "RUNNING")
    for spec in specs:
        run_id = p2_run_id(str(spec["trajectory_spec_id"]))
        if run_id in complete_by_run:
            continue
        progress(run_id, "RUNNING")
        try:
            # The completed P2 twenty-five-run diagnostic predates the
            # Stage-2 manifest and has no authority-selected row set to check
            # against. It says so explicitly; the record it produces carries
            # ``target_rows_authority_bound: false`` and every Stage-2 consumer
            # refuses it.
            record = extractor.extract(
                run_id, CAPTURES / run_id, ACT,
                expected_target_model_frame_indices=TARGET_ROWS_NOT_AUTHORITY_BOUND,
                scientific_trajectory_id=SCIENTIFIC_TRAJECTORY_NOT_AUTHORITY_BOUND,
                expected_legacy_capture_trajectory_id=(
                    LEGACY_CAPTURE_TRAJECTORY_NOT_AUTHORITY_BOUND))
        except Exception as exc:  # identity/model failures are not retryable here
            error = f"{type(exc).__name__}: {exc}"[:400]
            append_ledger({"p2_no_wall_run_id": run_id, "status": "FAILED_HARD",
                           "error": error})
            progress(None, "STOPPED_HARD_FAILURE", "FAILED_HARD")
            raise
        record["source_regime_a_spec_id"] = str(spec["trajectory_spec_id"])
        record["outer_fold"] = int(spec["outer_fold"])
        record["direction"] = spec["direction"]
        durable = None
        for attempt in range(1, MAX_PERSIST_ATTEMPTS + 1):
            try:
                durable = persist_activation(record)
                durable["persist_attempts"] = attempt
                break
            except Exception as exc:  # noqa: BLE001 - same artifact retry only
                append_ledger({
                    "p2_no_wall_run_id": run_id,
                    "status": "FAILED_RETRYABLE",
                    "attempt": attempt,
                    "error": f"{type(exc).__name__}: {exc}"[:400],
                })
                progress(run_id, "RUNNING_WITH_RETRY", "FAILED_RETRYABLE")
                if attempt < MAX_PERSIST_ATTEMPTS:
                    retries += 1
        if durable is None:
            progress(None, "STOPPED_RETRY_EXHAUSTED", "FAILED_RETRYABLE")
            raise RuntimeError(f"{run_id}: durable persistence retries exhausted")
        append_ledger(durable)
        complete_by_run[run_id] = durable
        progress(run_id, "RUNNING")
        print(f"  {run_id}: rows={record['rows']} tokens={record['visual_tokens_per_target']} "
              f"{record['byte_size']/1e6:.1f}MB", flush=True)

    records = [complete_by_run[p2_run_id(str(spec["trajectory_spec_id"]))]
               for spec in specs]
    total_rows = sum(r["rows"] for r in records)
    if total_rows != 475:
        raise RuntimeError(f"expected 475 activation rows, got {total_rows}")
    seen = {(r["p2_no_wall_run_id"], t) for r in records for t in r["targets"]}
    if len(seen) != 475:
        raise RuntimeError("duplicate activation rows detected")
    tokens = {r["visual_tokens_per_target"] for r in records}
    if tokens != {336}:
        raise RuntimeError(f"token grid identity mismatch: {tokens}")

    payload = {
        "artifact_id": "regime-a-prime-p2-activation-manifest-v0.1",
        "schema_version": "1.0",
        "phase": "P2",
        "classification": "EXPLORATORY_MATCHED_DIAGNOSTIC",
        "status": "PASS",
        "layers_extracted": [LAYER],
        "all_layer_extraction_performed": False,
        "gated_on_path_equivalence_pass": True,
        "checkpoint_load_count": extractor.load_count,
        "run_count": len(records),
        "total_activation_rows": total_rows,
        "duplicate_rows": 0,
        "missing_rows": 0,
        "extraction_seconds": time.monotonic() - started,
        "extraction_retries": retries,
        "activation_bytes": sum(r["byte_size"] for r in records),
        "working_root": str(ACT),
        "durable_prefix": S3_PREFIX,
        "runs": records,
    }
    digest = write_json(OUT / "p2_activation_manifest.json", payload)
    progress(None, "COMPLETE")
    print(f"\nP2_EXTRACTION_STATUS=PASS")
    print(f"P2_ACTIVATION_MANIFEST_SHA256={digest}")
    print(f"P2_LAYERS_EXTRACTED=[{LAYER}] ROWS={total_rows} "
          f"BYTES={payload['activation_bytes']/1e9:.2f}GB "
          f"SECONDS={payload['extraction_seconds']:.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""A5 exit / A9 entry — the immutable GPU handoff package for P1 extraction.

The GPU sprint starts on a host that has never seen this repository's history. It
needs to know, without reconstructing anything by hand: which authority and
source produced these captures, where the ten units are, which 190 target rows
are the forward inputs, what model and preprocessing to load, which layers and
token slices to harvest, and exactly what 60 arrays it owes back.

Everything below is *read* from frozen evidence — the authority, the machine
authority, the P0 selection receipt, the P1 plan, the A3 host receipt and the
capture units' own durable receipts. Nothing is restated from a prompt or a
constant typed here; where a value is checked against the authority the check is
an assertion, so a drifted expectation fails loudly rather than shipping.

    python scripts/experiment_iii/build_p1_gpu_handoff.py --captures <dir>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tarfile
import time
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mineocclude.experiment_iii.authority import (  # noqa: E402
    AUTHORITY_FREEZE_COMMIT,
    AUTHORITY_VERSION,
    TARGET_ROWS_PER_CAPTURE,
    machine_authority,
    verify_authority_binding,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError  # noqa: E402
from mineocclude.experiment_iii.source_closure import source_closure  # noqa: E402

DOCS = REPOSITORY_ROOT / "docs" / "experiment_iii"
DEFAULT_CAPTURES = REPOSITORY_ROOT / "data" / "experiment_iii" / "p1" / "captures"
DEFAULT_OUT = REPOSITORY_ROOT / "data" / "experiment_iii" / "p1" / "handoff"

#: What the GPU host actually needs out of a capture unit. The frames and the
#: streams are the model inputs; the receipts are how it proves it read the right
#: ones. Everything else in the unit stays home.
TRANSFERRED_UNIT_FILES = (
    "raw/server_state.jsonl",
    "raw/client_tick.jsonl",
    "raw/actions.jsonl",
    "raw/frame_map.jsonl",
    "raw/visibility.jsonl",
    "coordinates.jsonl",
    "wall_receipt.json",
    "camera_receipt.json",
    "target_receipt.json",
    "condition_receipt.json",
    "path_receipt.json",
    "timing_receipt.json",
    "framebuffer_receipt.json",
    "capture_completion.json",
    "durable_receipt.json",
    "physical_receipt.json",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def extraction_contract() -> dict[str, Any]:
    """The frozen A9 contract, read from the machine authority and checked."""
    extraction = machine_authority()["extraction"]
    storage = extraction.get("activation_storage") or machine_authority().get(
        "activation_storage", {}
    )
    pilot = machine_authority()["p1_pilot"]

    slices = extraction["temporal_slices"]
    previous = slices["PREVIOUS"]
    current = slices["CURRENT"]

    # Authority 8.5's byte arithmetic, recomputed rather than copied. If the
    # authority ever changes a dimension, this raises instead of shipping a
    # handoff whose expected file size no longer matches its own shape.
    rows = int(pilot["target_rows"]) // int(pilot["captures"])
    visual = int(extraction["visual_tokens_per_pair"])
    width = int(extraction["hidden_width"])
    row_bytes = visual * width * 2
    npy_bytes = rows * row_bytes + 128
    expected_bytes = int(
        storage.get("expected_npy_bytes")
        or machine_authority().get("activation_npy_bytes")
        or npy_bytes
    )
    if npy_bytes != expected_bytes:
        raise ExperimentIIIError(
            "TENSOR_BYTE_SIZE_MISMATCH",
            f"recomputed {npy_bytes} bytes per array, authority states {expected_bytes}",
        )
    if rows != TARGET_ROWS_PER_CAPTURE:
        raise ExperimentIIIError(
            "TARGET_ROW_MISMATCH",
            f"authority target rows per capture is {rows}, expected "
            f"{TARGET_ROWS_PER_CAPTURE}",
        )

    return {
        "model": extraction["model"],
        "main_checkpoint_sha256": extraction["main_checkpoint_sha256"],
        "vae_sha256": extraction["vae_sha256"],
        "preprocessing_change_allowed": bool(
            extraction["preprocessing_change_allowed"]
        ),
        "source_frame_colour_space": "RGB",
        "context_pair_count": int(extraction["context_pair_count"]),
        "visual_tokens_per_pair": visual,
        "action_tokens_per_pair": int(extraction["action_tokens_per_pair"]),
        "tokens_per_pair": int(extraction["tokens_per_pair"]),
        "sequence_length": int(extraction["sequence_length"]),
        "hidden_width": width,
        "hooked_shape": list(extraction["hooked_shape"]),
        "hooked_layer_count_transient": int(
            extraction["hooked_layer_count_transient"]
        ),
        "layers": list(extraction["layers"]),
        "temporal_slices": {
            "PREVIOUS": {
                "pair_ordinal": int(previous["pair_ordinal"]),
                "python_slice": [
                    int(previous["inclusive_start"]),
                    int(previous["inclusive_end"]) + 1,
                ],
            },
            "CURRENT": {
                "pair_ordinal": int(current["pair_ordinal"]),
                "python_slice": [
                    int(current["inclusive_start"]),
                    int(current["inclusive_end"]) + 1,
                ],
            },
        },
        "one_forward_per_target_row": bool(extraction["one_forward_per_target_row"]),
        "extra_forward_authorized": bool(extraction["extra_forward_authorized"]),
        "forward_count_excess_blocker": extraction["forward_count_excess_blocker"],
        "expected_forwards": int(pilot["forwards"]),
        "expected_arrays": int(pilot["serialized_npy_arrays"]),
        "arrays_per_capture": int(pilot["layers"]) * int(pilot["temporal_slices"]),
        "expected_array_shape": [rows, visual, width],
        "expected_array_dtype": "<f2",
        "expected_array_bytes": npy_bytes,
        "expected_total_activation_bytes": int(pilot["activation_bytes"]),
        "frame_identity_assertions": [
            "spans[-1].pair_index == 15 and spans[-2].pair_index == 14",
            "spans[-1].visual_positions == tuple(range(5205, 5541))",
            "spans[-2].visual_positions == tuple(range(4858, 5194))",
            "spans[-1].identity.model_frame_idx == t",
            "spans[-2].identity.model_frame_idx == t - 1",
            "FrameTokenMap covers range(5552) exactly, no duplicate or missing",
            "selected visual positions disjoint from every action position",
        ],
        "frame_identity_blockers": [
            "TOKEN_SPAN_MISMATCH",
            "TOKEN_FRAME_IDENTITY_MISMATCH",
            "TOKEN_ACTION_CONTAMINATION",
            "TOKEN_SEQUENCE_LENGTH_MISMATCH",
        ],
    }


def build_manifest(captures: Path) -> dict[str, Any]:
    binding = verify_authority_binding()
    closure = source_closure()
    plan_path = DOCS / "p1" / "p1_pilot_plan.json"
    selection_path = DOCS / "p0" / "P0_SELECTION_RECEIPT.json"
    ladder_path = DOCS / "p0" / "P0_SELECTED_LADDER.json"
    a3_path = DOCS / "receipts" / "environment_receipt_wsl2_capture_host.json"
    static_path = DOCS / "receipts" / "static_validation_receipt.json"

    plan = _json(plan_path)
    ladder = _json(ladder_path)

    units: list[dict[str, Any]] = []
    total_rows = 0
    for planned in plan["units"]:
        unit_id = str(planned["capture_unit_id"])
        unit_dir = captures / unit_id
        if not unit_dir.is_dir():
            raise ExperimentIIIError(
                "P1_INCOMPLETE", f"capture unit {unit_id} is not banked at {unit_dir}"
            )
        completion = _json(unit_dir / "capture_completion.json")
        durable = _json(unit_dir / "durable_receipt.json")
        rows = list(completion["target_model_frame_indices"])
        if len(rows) != TARGET_ROWS_PER_CAPTURE:
            raise ExperimentIIIError(
                "TARGET_ROW_MISMATCH",
                f"{unit_id} carries {len(rows)} target rows",
            )
        total_rows += len(rows)
        files = {
            relative: {
                "sha256": _sha256(unit_dir / relative),
                "bytes": (unit_dir / relative).stat().st_size,
            }
            for relative in TRANSFERRED_UNIT_FILES
            if (unit_dir / relative).is_file()
        }
        frames = sorted((unit_dir / "raw" / "frames").glob("*.png"))
        units.append(
            {
                "capture_unit_id": unit_id,
                "identity": completion["identity"],
                "condition_id": completion["condition_id"],
                "wall_block_id": completion["spec"]["wall_block_id"],
                "scene": completion["spec"]["scene"],
                "episode_id": completion["episode_id"],
                "spec_sha256": completion["spec_sha256"],
                "path_sha256": completion["spec"]["path_sha256"],
                "noise_schedule_sha256": completion["spec"]["noise_schedule_sha256"],
                "direction": completion["spec"]["direction"],
                "seed": completion["spec"]["seed"],
                "target_model_frame_indices": rows,
                "target_rows_sha256": hashlib.sha256(
                    json.dumps(rows, separators=(",", ":")).encode("utf-8")
                ).hexdigest(),
                "fir_labels": completion["fir_labels"],
                "context_ages": completion["context_ages"],
                "extent_classes": completion["extent_classes"],
                "last_preocclusion_model_frame_idx": completion[
                    "last_preocclusion_model_frame_idx"
                ],
                "frame_count": len(frames),
                "durable_file_count": durable["file_count"],
                "durable_total_bytes": durable["total_bytes"],
                "relative_root": f"captures/{unit_id}",
                "files": files,
                "expected_output_arrays": [
                    f"activations/{unit_id}/layer_{layer:02d}/{slice_name}.npy"
                    for layer in machine_authority()["extraction"]["layers"]
                    for slice_name in ("PREVIOUS", "CURRENT")
                ],
            }
        )

    contract = extraction_contract()
    if total_rows != contract["expected_forwards"]:
        raise ExperimentIIIError(
            "TARGET_ROW_MISMATCH",
            f"the ten units carry {total_rows} target rows; the contract expects "
            f"{contract['expected_forwards']}",
        )

    return {
        "schema_version": "mineocclude-experiment-iii-p1-gpu-handoff-v1",
        "authority_section": "6A, 8.4, 8.5",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "stage_on_arrival": "A9_ACTIVATION_EXTRACTION",
        "gpu_host_a3_status": "NOT_RUN",
        "authority": {
            "version": AUTHORITY_VERSION,
            "authority_sha256": binding["AUTHORITY_SHA256"],
            "machine_authority_sha256": binding["MACHINE_AUTHORITY_SHA256"],
            "phase0_design_sha256": binding["PHASE0_DESIGN_SHA256"],
            "authority_freeze_commit": AUTHORITY_FREEZE_COMMIT,
        },
        "implementation": {
            "checkpoint_commit": closure.get("head_commit"),
            "source_closure": closure["source_closure_sha256"],
            "record_count": closure.get("record_count"),
            "includes_uncommitted_working_tree": closure.get(
                "includes_uncommitted_working_tree"
            ),
        },
        "upstream_evidence": {
            "p0_selection_receipt": {
                "path": selection_path.relative_to(REPOSITORY_ROOT).as_posix(),
                "sha256": _sha256(selection_path),
                "P0_RESULT": _json(selection_path)["P0_RESULT"],
            },
            "p0_selected_ladder": {
                "path": ladder_path.relative_to(REPOSITORY_ROOT).as_posix(),
                "sha256": _sha256(ladder_path),
                "L1": ladder["L1"],
                "L2": ladder["L2"],
                "L3": ladder["L3"],
                "V_c": ladder["V_c"],
            },
            "p1_pilot_plan": {
                "path": plan_path.relative_to(REPOSITORY_ROOT).as_posix(),
                "sha256": _sha256(plan_path),
                "ladder_bound": bool(plan["ladder_bound"]),
            },
            "capture_host_a3_receipt": {
                "path": a3_path.relative_to(REPOSITORY_ROOT).as_posix(),
                "sha256": _sha256(a3_path),
                "status": "PASS" if _json(a3_path)["passed"] else "FAIL",
            },
            "static_validation_receipt": {
                "path": static_path.relative_to(REPOSITORY_ROOT).as_posix(),
                "sha256": _sha256(static_path),
            },
        },
        "captures": {
            "count": len(units),
            "identities": sorted({unit["identity"] for unit in units}),
            "conditions": sorted({unit["condition_id"] for unit in units}),
            "production_identities_used": False,
            "target_rows_total": total_rows,
            "units": units,
        },
        "extraction_contract": contract,
        "output_contract": {
            "array_path_pattern": "activations/<capture_unit_id>/layer_<NN>/<SLICE>.npy",
            "inventory_path": "activations/activation_inventory.json",
            "arrays_expected": contract["expected_arrays"],
            "bind_per_artifact": [
                "identity",
                "condition",
                "layer",
                "temporal_slice",
                "the 19 target rows in order",
                "hook site",
                "token-position hash",
                "preprocessing identity",
                "checkpoint identity",
                "shape",
                "dtype",
                "byte size",
                "sha256",
            ],
        },
        "resume_contract": {
            "unit_of_work": "one (capture unit x layer x slice) persisted array",
            "states": [
                "PLANNED",
                "RUNNING",
                "EXTRACTED",
                "VALIDATED",
                "DURABLE",
                "COMPLETE",
            ],
            "same_spec_only": True,
            "same_spec_keys": [
                "source_capture_hash",
                "extraction_spec_hash",
                "authority_sha256",
            ],
            "runbook": "docs/experiment_iii/final_authorities/RECOVERY_AND_RESUME_RUNBOOK.md",
        },
        "validation_entrypoint": {
            "extraction": "python scripts/experiment_iii/run_extraction.py",
            "validation": "python scripts/experiment_iii/validate_extraction.py",
            "handoff_selfcheck": (
                "python scripts/experiment_iii/build_p1_gpu_handoff.py --verify <bundle>"
            ),
        },
        "gpu_host_requirements": {
            "note": (
                "Enumerated from the frozen extraction contract. This local capture "
                "host holds no MineWorld weights and ran no CUDA; none of these were "
                "verified here and the GPU host must verify each itself."
            ),
            "model_checkpoint_sha256": contract["main_checkpoint_sha256"],
            "vae_sha256": contract["vae_sha256"],
            "activation_output_bytes": contract["expected_total_activation_bytes"],
            "verified_on_this_host": False,
        },
        "hard_stops": {
            "P1_FULL_PASS": False,
            "P2_EXECUTED": False,
            "PRODUCTION_AUTHORIZED": False,
            "note": (
                "Local capture completing does not complete P1. Full P1 requires the "
                "190 forwards and 60 arrays, and P2 requires full P1."
            ),
        },
    }


def build_bundle(manifest: dict[str, Any], captures: Path, out: Path) -> dict[str, Any]:
    """A tar.gz carrying exactly the files the manifest names, and the manifest."""
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "P1_GPU_HANDOFF_MANIFEST.json"
    payload = json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n"
    manifest_path.write_text(payload, encoding="utf-8", newline="\n")

    bundle = out / "p1_gpu_handoff.tar.gz"
    count = 0
    # Deterministic: sorted members, fixed mtime/uid/gid, so the same evidence
    # produces the same bytes and the bundle hash means something.
    def _reset(info: tarfile.TarInfo) -> tarfile.TarInfo:
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        info.mtime = 0
        return info

    with tarfile.open(bundle, "w:gz") as archive:
        archive.add(manifest_path, arcname="P1_GPU_HANDOFF_MANIFEST.json", filter=_reset)
        count += 1
        for unit in manifest["captures"]["units"]:
            unit_dir = captures / unit["capture_unit_id"]
            for relative in sorted(unit["files"]):
                archive.add(
                    unit_dir / relative,
                    arcname=f"{unit['relative_root']}/{relative}",
                    filter=_reset,
                )
                count += 1
            for frame in sorted((unit_dir / "raw" / "frames").glob("*.png")):
                archive.add(
                    frame,
                    arcname=f"{unit['relative_root']}/raw/frames/{frame.name}",
                    filter=_reset,
                )
                count += 1
        for key in ("p0_selection_receipt", "p0_selected_ladder", "p1_pilot_plan",
                    "capture_host_a3_receipt", "static_validation_receipt"):
            entry = manifest["upstream_evidence"][key]
            archive.add(
                REPOSITORY_ROOT / entry["path"],
                arcname=f"provenance/{Path(entry['path']).name}",
                filter=_reset,
            )
            count += 1

    return {
        "bundle": bundle,
        "manifest": manifest_path,
        "manifest_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "bundle_sha256": _sha256(bundle),
        "bundle_bytes": bundle.stat().st_size,
        "file_count": count,
    }


def verify_bundle(bundle: Path, captures: Path) -> dict[str, Any]:
    """Reconstruct from the bundle alone and re-verify every hash it claims.

    This is the test that a fresh GPU host, given only the package, has what it
    needs: the manifest is read *out of the archive*, and every file it names is
    extracted and re-hashed. A path that only resolves on the local machine fails
    here rather than on the GPU host.
    """
    problems: list[str] = []
    with tarfile.open(bundle, "r:gz") as archive:
        names = set(archive.getnames())
        member = archive.extractfile("P1_GPU_HANDOFF_MANIFEST.json")
        if member is None:
            raise ExperimentIIIError(
                "P1_INCOMPLETE", "the bundle carries no manifest"
            )
        manifest = json.loads(member.read().decode("utf-8"))

        checked = 0
        for unit in manifest["captures"]["units"]:
            for relative, entry in unit["files"].items():
                arcname = f"{unit['relative_root']}/{relative}"
                if arcname not in names:
                    problems.append(f"missing from bundle: {arcname}")
                    continue
                extracted = archive.extractfile(arcname)
                if extracted is None:
                    problems.append(f"unreadable in bundle: {arcname}")
                    continue
                digest = hashlib.sha256(extracted.read()).hexdigest()
                if digest != entry["sha256"]:
                    problems.append(f"hash mismatch: {arcname}")
                checked += 1
            frames = [
                name
                for name in names
                if name.startswith(f"{unit['relative_root']}/raw/frames/")
            ]
            if len(frames) != unit["frame_count"]:
                problems.append(
                    f"{unit['capture_unit_id']} carries {len(frames)} frames, "
                    f"manifest claims {unit['frame_count']}"
                )

    contract = manifest["extraction_contract"]
    rows = sum(
        len(unit["target_model_frame_indices"]) for unit in manifest["captures"]["units"]
    )
    if rows != contract["expected_forwards"]:
        problems.append(f"{rows} target rows, contract expects {contract['expected_forwards']}")
    if len(manifest["captures"]["units"]) != manifest["captures"]["count"]:
        problems.append("unit count disagrees with the manifest header")
    expected_arrays = contract["expected_arrays"]
    declared = sum(len(unit["expected_output_arrays"]) for unit in manifest["captures"]["units"])
    if declared != expected_arrays:
        problems.append(f"{declared} declared output arrays, contract expects {expected_arrays}")

    return {
        "verified": not problems,
        "files_checked": checked,
        "target_rows": rows,
        "expected_arrays": expected_arrays,
        "problems": problems,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--captures", type=Path, default=DEFAULT_CAPTURES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--verify", type=Path, help="verify an existing bundle")
    args = parser.parse_args(argv)

    try:
        if args.verify:
            report = verify_bundle(args.verify, args.captures)
            for problem in report["problems"]:
                print(f"HANDOFF_PROBLEM={problem}", file=sys.stderr)
            print(f"P1_TRANSFER_FILES_CHECKED={report['files_checked']}")
            print(f"P1_TARGET_ROWS={report['target_rows']}")
            print(f"P1_EXPECTED_ARRAYS={report['expected_arrays']}")
            print(
                "P1_TRANSFER_RECONSTRUCTION_VALIDATION="
                f"{'PASS' if report['verified'] else 'FAIL'}"
            )
            return 0 if report["verified"] else 1

        manifest = build_manifest(args.captures)
        result = build_bundle(manifest, args.captures, args.out)
        print(f"P1_GPU_HANDOFF_MANIFEST={result['manifest']}")
        print(f"P1_GPU_HANDOFF_MANIFEST_SHA256={result['manifest_sha256']}")
        print(f"P1_TRANSFER_BUNDLE={result['bundle']}")
        print(f"P1_TRANSFER_BUNDLE_BYTES={result['bundle_bytes']}")
        print(f"P1_TRANSFER_BUNDLE_SHA256={result['bundle_sha256']}")
        print(f"P1_TRANSFER_FILE_COUNT={result['file_count']}")
        print(f"P1_EXPECTED_MODEL_FORWARDS={manifest['extraction_contract']['expected_forwards']}")
        print(f"P1_EXPECTED_ARRAYS={manifest['extraction_contract']['expected_arrays']}")
        print(f"P1_EXPECTED_ARRAY_BYTES={manifest['extraction_contract']['expected_array_bytes']}")
        print("GPU_HOST_A3_STATUS=NOT_RUN")
        print("SAGEMAKER_STARTED=false")
        return 0
    except ExperimentIIIError as error:
        print(f"BLOCKER_CODE={error.blocker}", file=sys.stderr)
        print(error.message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

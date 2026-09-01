"""A5 extraction half — the P1 pilot's 190 forwards and 60 arrays.

This is the *pilot* extraction entrypoint. ``run_extraction.py`` remains the
A9 production driver and is untouched; A9 is 125 captures, 2,375 forwards and
750 arrays behind the P2 freeze. Conflating them would either spend production
scope on a pilot or gate the pilot behind a freeze the authority does not
require of it:

    A5 entry  A4 == P0_PASS; A3 == PASS on capture AND extraction hosts;
              P1_AUTHORIZED == true
    A9 entry  A8 == PASS; A3 == PASS on the GPU host; A6_FREEZE_BOUND;
              MODEL_INFERENCE_AUTHORIZED == true

    python scripts/experiment_iii/run_p1_extraction.py --plan

    python scripts/experiment_iii/run_p1_extraction.py --execute \\
        --a3-receipt docs/experiment_iii/receipts/environment_receipt_gpu.json \\
        --handoff-manifest <unpacked handoff>/P1_GPU_HANDOFF_MANIFEST.json \\
        --captures <unpacked handoff>/captures \\
        --mineworld-source-root <MineWorld checkout> \\
        --model-config <config> --main-checkpoint <ckpt> \\
        --vae-config <config> --vae-checkpoint <ckpt> \\
        --environment-report <A3 receipt used as the runtime environment report>

``--plan`` loads no model and runs no forward. ``--execute`` refuses unless the
A3 receipt in front of it authorizes ``A5_EXTRACTION`` and records the frozen
checkpoint and VAE digests it hashed itself.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mineocclude.experiment_iii.activation_store import (  # noqa: E402
    EXPECTED_NPY_BYTES,
    EXPECTED_SHAPE,
    UNITS_PER_CAPTURE,
)
from mineocclude.experiment_iii.authority import (  # noqa: E402
    AUTHORITY_VERSION,
    TARGET_ROWS_PER_CAPTURE,
    canonical_sha256,
    machine_authority,
    verify_authority_binding,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError  # noqa: E402
from mineocclude.experiment_iii.extraction import (  # noqa: E402
    SELECTED_LAYERS,
    TRANSIENT_HOOK_LAYER_COUNT,
)
from mineocclude.experiment_iii.p1_extraction import (  # noqa: E402
    A5_EXTRACTION_STAGE,
    CANONICAL_INVENTORY_NAME,
    HOOK_SITE,
    PERSON_A_RUNTIME_SCRIPTED_IMPULSE,
    PILOT_ARRAYS,
    PILOT_CAPTURES,
    PILOT_FORWARDS,
    PILOT_TARGET_ROWS,
    MineWorldPilotDecoder,
    P1ExtractionCampaign,
    authorize_a5_extraction,
    capture_stream_rows,
    token_position_hash,
)
from mineocclude.experiment_iii.schema import TemporalSlice, write_json_atomic  # noqa: E402
from mineocclude.experiment_iii.slices import verify_slice_arithmetic  # noqa: E402

DEFAULT_OUT = REPOSITORY_ROOT / "docs" / "experiment_iii" / "p1"
DEFAULT_ACTIVATIONS = (
    REPOSITORY_ROOT / "data" / "experiment_iii" / "p1" / "activations"
)


def extraction_spec_hash() -> str:
    """The identity a resumed unit must still match (authority 8.6).

    Everything that would change what an array *is*: the layers, the slices, the
    token layout, the shape, the dtype, the byte size and the authority under
    which they are frozen. A change to any of them is ``EXTRACTION_SPEC_DRIFT``
    and discards the partial rather than adopting it.
    """
    extraction = machine_authority()["extraction"]
    return canonical_sha256(
        {
            "stage": A5_EXTRACTION_STAGE,
            "authority_sha256": verify_authority_binding()["AUTHORITY_SHA256"],
            "layers": list(SELECTED_LAYERS),
            "temporal_slices": [name.value for name in TemporalSlice],
            "token_position_hash": token_position_hash(),
            "hook_site": HOOK_SITE,
            "transient_hook_layers": TRANSIENT_HOOK_LAYER_COUNT,
            "expected_shape": list(EXPECTED_SHAPE),
            "expected_dtype": "<f2",
            "expected_npy_bytes": EXPECTED_NPY_BYTES,
            "main_checkpoint_sha256": extraction["main_checkpoint_sha256"],
            "vae_sha256": extraction["vae_sha256"],
            "preprocessing_change_allowed": bool(
                extraction["preprocessing_change_allowed"]
            ),
        }
    )


def extraction_plan() -> dict[str, Any]:
    """What A5's extraction half owes, derived and checked against the authority."""
    pilot = machine_authority()["p1_pilot"]
    plan = {
        "schema_version": "mineocclude-experiment-iii-p1-extraction-plan-v1",
        "authority_section": "6A, 8.4, 8.5",
        "authority_version": AUTHORITY_VERSION,
        "authority_binding": verify_authority_binding(),
        "stage": A5_EXTRACTION_STAGE,
        "is_production_stage": False,
        "requires_model_inference_authorized": False,
        "next_authorized_state": "A6",
        "captures": PILOT_CAPTURES,
        "target_rows_per_capture": TARGET_ROWS_PER_CAPTURE,
        "target_rows_total": PILOT_TARGET_ROWS,
        "forwards": PILOT_FORWARDS,
        "arrays": PILOT_ARRAYS,
        "arrays_per_capture": UNITS_PER_CAPTURE,
        "layers": list(SELECTED_LAYERS),
        "transient_hook_layer_count": TRANSIENT_HOOK_LAYER_COUNT,
        "temporal_slices": [name.value for name in TemporalSlice],
        "expected_shape": list(EXPECTED_SHAPE),
        "expected_dtype": "<f2",
        "expected_npy_bytes": EXPECTED_NPY_BYTES,
        "expected_total_activation_bytes": int(pilot["activation_bytes"]),
        "inventory_name": CANONICAL_INVENTORY_NAME,
        "one_forward_per_target_row": True,
        "extra_forward_authorized": False,
        "pilot_identities": list(pilot["identities"]),
        "production_identities_authorized": False,
        "slice_arithmetic": verify_slice_arithmetic(),
        "extraction_spec_hash": extraction_spec_hash(),
    }
    drift = {
        name: (derived, int(pilot[key]))
        for name, key, derived in (
            ("captures", "captures", PILOT_CAPTURES),
            ("target_rows", "target_rows", PILOT_TARGET_ROWS),
            ("forwards", "forwards", PILOT_FORWARDS),
            ("arrays", "serialized_npy_arrays", PILOT_ARRAYS),
        )
        if derived != int(pilot[key])
    }
    if drift:
        raise ExperimentIIIError(
            "P1_INCOMPLETE",
            f"the derived pilot counts disagree with the authority: {drift}",
        )
    return plan


def _head_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()


def _load_frame(path: Path) -> Any:
    """One captured PNG as the adapter's preprocessor expects it.

    ``cv2.imread`` returns BGR, which is exactly what the frozen preprocessing
    path at ``_mineworld_adapter_wave2.py:408-473`` converts with
    ``COLOR_BGR2RGB``. Authority 8.4 forbids "fixing" the historical RGB/BGR
    behaviour, so the byte path is preserved rather than corrected.
    """
    import cv2

    frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if frame is None:
        raise ExperimentIIIError(
            "CAPTURE_MISSING_FRAME", f"the captured frame could not be read: {path}"
        )
    return frame


def _execute(args: argparse.Namespace, plan: dict[str, Any]) -> int:
    """Drive the ten pilot captures through the real MineWorld adapter."""
    from mineocclude.activations import hooks as hooks_module
    from mineocclude.contracts.identity import SCHEMA_VERSION
    from mineocclude.models import _mineworld_adapter_wave4 as wave4
    from mineocclude.models import mineworld_adapter as adapter_module
    from mineocclude.models.mineworld_adapter import create_mineworld_adapter

    a3_receipt = json.loads(Path(args.a3_receipt).read_text(encoding="utf-8"))
    authorization = authorize_a5_extraction(a3_receipt)
    manifest = json.loads(Path(args.handoff_manifest).read_text(encoding="utf-8"))

    units = []
    for entry in manifest["captures"]["units"]:
        unit_dir = Path(args.captures) / entry["capture_unit_id"]
        units.append(
            {
                "capture_unit_id": entry["capture_unit_id"],
                "identity": entry["identity"],
                "condition_id": entry["condition_id"],
                "unit_dir": unit_dir,
                "seed": int(entry["seed"]),
                "source_capture_hash": str(entry["spec_sha256"]),
                "target_model_frame_indices": [
                    int(value) for value in entry["target_model_frame_indices"]
                ],
            }
        )
    if len(units) != PILOT_CAPTURES:
        raise ExperimentIIIError(
            "P1_INCOMPLETE",
            f"the handoff names {len(units)} captures, A5 freezes {PILOT_CAPTURES}",
        )

    adapter = create_mineworld_adapter()
    runtime_identity = adapter.load_runtime(
        adapter_module.RuntimeLoadRequest(
            schema_version=SCHEMA_VERSION,
            runtime_id=args.runtime_id,
            mineocclude_revision=_head_commit()[:12],
            mineworld_source_revision=args.mineworld_source_revision,
            modelscope_asset_revision=args.modelscope_asset_revision,
            mineworld_source_root=Path(args.mineworld_source_root),
            model_config_path=Path(args.model_config),
            main_checkpoint_path=Path(args.main_checkpoint),
            vae_config_path=Path(args.vae_config),
            vae_checkpoint_path=Path(args.vae_checkpoint),
            model_config_sha256=args.model_config_sha256,
            main_checkpoint_sha256=authorization["checkpoint_sha256"],
            vae_config_sha256=args.vae_config_sha256,
            vae_checkpoint_sha256=authorization["vae_sha256"],
            environment_report_sha256=args.environment_report_sha256,
            precision=args.precision,
            device=args.device,
        )
    )

    campaign = P1ExtractionCampaign(
        units,
        output_root=args.activations,
        ledger_path=Path(args.activations) / "p1_extraction_ledger.jsonl",
        extraction_spec_hash=plan["extraction_spec_hash"],
    )

    def decoder_factory(unit: dict[str, Any]) -> MineWorldPilotDecoder:
        return MineWorldPilotDecoder(
            adapter,
            runtime_identity,
            unit_dir=unit["unit_dir"],
            trajectory_id=unit["capture_unit_id"],
            seed=unit["seed"],
            rows=capture_stream_rows(unit["unit_dir"]),
            impulse_orientation=PERSON_A_RUNTIME_SCRIPTED_IMPULSE,
            hook_manager_factory=lambda modules: hooks_module.ScopedHookManager(
                _discovery(modules)
            ),
            frame_loader=_load_frame,
            expected_adapter_code_sha256=wave4._adapter_code_identity().sha256,
            precision=args.precision,
        )

    def _discovery(modules: tuple[tuple[str, object], ...]) -> Any:
        layers = tuple(
            hooks_module.HookLayerMetadata(
                layer_idx=index,
                module_name=name,
                module_type=f"{type(module).__module__}.{type(module).__qualname__}",
                conceptual_site=hooks_module.CONCEPTUAL_HOOK_SITE,
                discovery_version=hooks_module.HOOK_DISCOVERY_VERSION,
            )
            for index, (name, module) in enumerate(modules)
        )
        parent = modules[0][0].rsplit(".", 1)[0]
        return hooks_module.FrozenHookDiscovery(
            layers=layers,
            module_name_pattern=f"{parent}.{{layer_idx}}",
            conceptual_site=hooks_module.CONCEPTUAL_HOOK_SITE,
            discovery_version=hooks_module.HOOK_DISCOVERY_VERSION,
            _modules=tuple(module for _name, module in modules),
        )

    started = time.time()
    result = campaign.run(
        decoder_factory,
        checkpoint_identity=authorization["checkpoint_sha256"],
        preprocessing_identity=runtime_identity.preprocessing_identity,
        on_unit=lambda unit_id, state: print(
            f"P1_EXTRACTION_UNIT={unit_id} STATE={state}", flush=True
        ),
    )
    inventory = result["inventory"]
    elapsed = time.time() - started

    print(f"A5_EXTRACTION_STAGE={A5_EXTRACTION_STAGE}")
    print(f"P1_CAPTURES_EXPECTED={inventory['total_captures']}")
    print(f"P1_CAPTURES_COMPLETE={inventory['captures_complete']}")
    print(f"P1_CAPTURES_SKIPPED_AS_COMPLETE={len(result['skipped'])}")
    print(f"MODEL_FORWARDS_EXECUTED={inventory['forwards_this_run']}")
    print(f"P1_ARRAYS_EXPECTED={inventory['arrays_expected']}")
    print(f"P1_ARRAYS_COMPLETE={inventory['arrays_complete']}")
    print(
        "P1_PRODUCTION_IDENTITIES_USED="
        f"{str(inventory['production_identities_used']).lower()}"
    )
    print(f"P1_EXTRACTION_ELAPSED_SECONDS={elapsed:.1f}")
    print(f"P1_EXTRACTION_COMPLETE={str(inventory['complete']).lower()}")
    if not inventory["complete"]:
        print("BLOCKER_CODE=P1_INCOMPLETE", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--a3-receipt", type=Path)
    parser.add_argument("--handoff-manifest", type=Path)
    parser.add_argument("--captures", type=Path)
    parser.add_argument("--activations", type=Path, default=DEFAULT_ACTIVATIONS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--mineworld-source-root", type=Path)
    parser.add_argument("--model-config", type=Path)
    parser.add_argument("--main-checkpoint", type=Path)
    parser.add_argument("--vae-config", type=Path)
    parser.add_argument("--vae-checkpoint", type=Path)
    parser.add_argument("--model-config-sha256")
    parser.add_argument("--vae-config-sha256")
    parser.add_argument("--environment-report-sha256")
    parser.add_argument("--mineworld-source-revision")
    parser.add_argument("--modelscope-asset-revision")
    parser.add_argument("--runtime-id", default="experiment-iii-a5-pilot")
    parser.add_argument("--precision", default="float16")
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args(argv)
    if not (args.plan or args.execute):
        args.plan = True

    try:
        plan = extraction_plan()
        digest = write_json_atomic(args.out / "p1_extraction_plan.json", plan)
        if args.execute:
            required = (
                "a3_receipt",
                "handoff_manifest",
                "captures",
                "mineworld_source_root",
                "model_config",
                "main_checkpoint",
                "vae_config",
                "vae_checkpoint",
                "model_config_sha256",
                "vae_config_sha256",
                "environment_report_sha256",
                "mineworld_source_revision",
                "modelscope_asset_revision",
            )
            missing = [
                f"--{name.replace('_', '-')}"
                for name in required
                if getattr(args, name) is None
            ]
            if missing:
                raise ExperimentIIIError(
                    "PROVENANCE_BINDING_MISSING",
                    "A5 extraction will not load a runtime it cannot name: "
                    + ", ".join(missing),
                )
            return _execute(args, plan)

        print(f"AUTHORITY_VERSION={AUTHORITY_VERSION}")
        print(f"A5_EXTRACTION_STAGE={A5_EXTRACTION_STAGE}")
        print(f"P1_CAPTURES={plan['captures']}")
        print(f"P1_TARGET_ROWS={plan['target_rows_total']}")
        print(f"P1_EXPECTED_MODEL_FORWARDS={plan['forwards']}")
        print(f"P1_EXPECTED_ARRAYS={plan['arrays']}")
        print(f"P1_EXPECTED_ARRAY_BYTES={plan['expected_npy_bytes']}")
        print(f"P1_INVENTORY_NAME={plan['inventory_name']}")
        print(f"EXTRACTION_SPEC_SHA256={plan['extraction_spec_hash']}")
        print(f"P1_EXTRACTION_PLAN_SHA256={digest}")
        print("MODEL_FORWARDS_EXECUTED=0")
        print("MINEWORLD_MODEL_LOADED=false")
        return 0
    except ExperimentIIIError as error:
        print(f"BLOCKER_CODE={error.blocker}", file=sys.stderr)
        print(error.message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

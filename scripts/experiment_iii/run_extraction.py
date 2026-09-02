"""I09 — the A9 PRODUCTION extraction driver.

A9 is production: 125 captures, **2,375 forwards**, 750 arrays. Its lifecycle
entry requires ``A8 == PASS``, the A6 freeze binding and
``MODEL_INFERENCE_AUTHORIZED == true``, and ``--execute`` supplies all three from
real evidence -- the A8 cohort closure receipt, the P2 freeze package and this
host's A3 receipt -- through :func:`admit_production_extraction`. None of them
can be asserted by a flag.

The forward budget is the arithmetic to protect. Six logical layer/slice outputs
come from **one** hooked forward per target row, so the campaign runs 2,375
forwards, not 14,250; ``assert_forward_budget`` refuses the excess rather than
discovering it in the GPU bill.

**This is not the P1 pilot entrypoint.** The A5 engineering pilot -- 10 captures,
190 forwards, 60 arrays -- is a different stage with a different gate and lives
in ``run_p1_extraction.py``.

    python scripts/experiment_iii/run_extraction.py --plan-only
    python scripts/experiment_iii/run_extraction.py --execute \\
        --p2 docs/experiment_iii/p2/P2_FREEZE_PACKAGE.json \\
        --a8-receipt docs/experiment_iii/a8/cohort_closure_receipt.json \\
        --a3-receipt docs/experiment_iii/receipts/environment_receipt_*.json \\
        --captures data/experiment_iii/production/captures
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mineocclude.experiment_iii.authority import (  # noqa: E402
    TARGET_ROWS_PER_CAPTURE,
    verify_authority_binding,
)
from mineocclude.experiment_iii.a9_production_extraction import (  # noqa: E402
    A9_STAGE,
    PRODUCTION_ARRAYS,
    PRODUCTION_CAPTURES,
    PRODUCTION_FORWARDS,
    ProductionExtractionCampaign,
    a9_extraction_spec_hash,
    admit_production_extraction,
    expected_extraction_counts,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError  # noqa: E402
from mineocclude.experiment_iii.extraction import SELECTED_LAYERS  # noqa: E402
from mineocclude.experiment_iii.schema import TemporalSlice, write_json_atomic  # noqa: E402
from mineocclude.experiment_iii.slices import verify_slice_arithmetic  # noqa: E402

DEFAULT_OUT = REPOSITORY_ROOT / "docs" / "experiment_iii" / "a1_receipts"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-only", action="store_true", default=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--p2",
        type=Path,
        default=REPOSITORY_ROOT
        / "docs" / "experiment_iii" / "p2" / "P2_FREEZE_PACKAGE.json",
    )
    parser.add_argument(
        "--a8-receipt",
        type=Path,
        default=REPOSITORY_ROOT
        / "docs" / "experiment_iii" / "a8" / "cohort_closure_receipt.json",
    )
    parser.add_argument("--a3-receipt", type=Path)
    parser.add_argument(
        "--captures",
        type=Path,
        default=REPOSITORY_ROOT
        / "data" / "experiment_iii" / "production" / "captures",
    )
    parser.add_argument(
        "--activations",
        type=Path,
        default=REPOSITORY_ROOT
        / "data" / "experiment_iii" / "production" / "activations",
    )
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
    parser.add_argument("--runtime-id", default="experiment-iii-a9-production")
    parser.add_argument("--precision", default="float16")
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args(argv)

    # --plan-only defaults True and execution is selected by --execute, so the
    # two together are a contradiction. Resolving it towards execution would
    # spend 2,375 production forwards for an operator who asked for a plan.
    if args.execute and "--plan-only" in (argv if argv is not None else sys.argv[1:]):
        print("BLOCKER_CODE=P2_PREREQUISITE_NOT_PASSED", file=sys.stderr)
        print("--plan-only and --execute are contradictory; A9 will not spend "
              "production forwards under an explicit plan-only request",
              file=sys.stderr)
        return 1
    if args.execute:
        return _execute(args)
    try:
        binding = verify_authority_binding()
        slices = verify_slice_arithmetic()
    except ExperimentIIIError as error:
        print(f"BLOCKER_CODE={error.blocker}", file=sys.stderr)
        print(error.message, file=sys.stderr)
        return 1

    captures = 125
    body = {
        "schema_version": "mineocclude-experiment-iii-extraction-plan-v1",
        "authority_section": "8.4",
        "authority_binding": binding,
        "selected_layers": list(SELECTED_LAYERS),
        "temporal_slices": [name.value for name in TemporalSlice],
        "target_rows_per_capture": TARGET_ROWS_PER_CAPTURE,
        "forwards_per_capture": TARGET_ROWS_PER_CAPTURE,
        "production_captures": captures,
        "total_forwards": captures * TARGET_ROWS_PER_CAPTURE,
        "arrays_per_capture": len(SELECTED_LAYERS) * len(TemporalSlice),
        "extra_forward_authorized": False,
        "mineworld_inference_run": False,
        "slice_arithmetic": slices,
    }
    digest = write_json_atomic(args.out / "extraction_plan.json", body)
    print(f"SELECTED_LAYERS={list(SELECTED_LAYERS)}")
    print(f"TOTAL_FORWARDS={body['total_forwards']}")
    print(f"ARRAYS_PER_CAPTURE={body['arrays_per_capture']}")
    print(f"EXTRACTION_PLAN_SHA256={digest}")
    print("MINEWORLD_INFERENCE_RUN=false")
    return 0


def _execute(args) -> int:
    """Drive the admitted production captures through the real MineWorld adapter."""
    import time

    from mineocclude.experiment_iii.p1_extraction import (
        PERSON_A_RUNTIME_SCRIPTED_IMPULSE,
        MineWorldPilotDecoder,
        capture_stream_rows,
    )
    from mineocclude.experiment_iii.schema import read_jsonl

    try:
        if args.a3_receipt is None:
            raise ExperimentIIIError(
                "ENV_GPU_UNAVAILABLE",
                "A9 requires this extraction host's A3 receipt; pass --a3-receipt",
            )
        a3_receipt = json.loads(Path(args.a3_receipt).read_text(encoding="utf-8"))
        admission = admit_production_extraction(
            p2_path=args.p2,
            a8_receipt_path=args.a8_receipt,
            a3_receipt=a3_receipt,
        )
        closure = json.loads(Path(args.a8_receipt).read_text(encoding="utf-8"))
        admitted = set(closure["complete_five_way_paired_identities"])
        manifest = read_jsonl(
            REPOSITORY_ROOT
            / "docs" / "experiment_iii" / "cohort"
            / "production_identity_manifest.jsonl"
        )
        by_identity = {str(row["identity"]): row for row in manifest}
        units = []
        for identity in sorted(admitted):
            row = by_identity[identity]
            for condition in ("L0", "L1", "L2", "L3", "L4"):
                unit_id = f"{identity}__{condition}"
                units.append(
                    {
                        "capture_unit_id": unit_id,
                        "identity": identity,
                        "condition_id": condition,
                        "unit_dir": Path(args.captures) / unit_id,
                        "seed": int(row["seed"]),
                        "source_capture_hash": str(row["spec_hash"]),
                        "target_model_frame_indices": [
                            int(value) for value in row["target_model_frame_indices"]
                        ],
                    }
                )
        counts = expected_extraction_counts(len(units))
    except (ExperimentIIIError, OSError, KeyError, json.JSONDecodeError) as error:
        blocker = getattr(error, "blocker", "P2_PREREQUISITE_NOT_PASSED")
        print(f"BLOCKER_CODE={blocker}", file=sys.stderr)
        print(getattr(error, "message", str(error)), file=sys.stderr)
        print("A9_EXECUTED=false", file=sys.stderr)
        return 1

    from mineocclude.activations import hooks as hooks_module
    from mineocclude.contracts.identity import SCHEMA_VERSION
    from mineocclude.models import _mineworld_adapter_wave4 as wave4
    from mineocclude.models import mineworld_adapter as adapter_module
    from mineocclude.models.mineworld_adapter import create_mineworld_adapter

    def _discovery(modules):
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

    def _load_frame(path: Path):
        from PIL import Image
        import numpy as _np

        with Image.open(path) as handle:
            return _np.asarray(handle.convert("RGB"))

    adapter = create_mineworld_adapter()
    runtime_identity = adapter.load_runtime(
        adapter_module.RuntimeLoadRequest(
            schema_version=SCHEMA_VERSION,
            runtime_id=args.runtime_id,
            mineocclude_revision=subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=REPOSITORY_ROOT,
                capture_output=True, text=True, check=False,
            ).stdout.strip(),
            mineworld_source_revision=args.mineworld_source_revision,
            modelscope_asset_revision=args.modelscope_asset_revision,
            mineworld_source_root=Path(args.mineworld_source_root),
            model_config_path=Path(args.model_config),
            main_checkpoint_path=Path(args.main_checkpoint),
            vae_config_path=Path(args.vae_config),
            vae_checkpoint_path=Path(args.vae_checkpoint),
            model_config_sha256=args.model_config_sha256,
            main_checkpoint_sha256=admission["checkpoint_sha256"],
            vae_config_sha256=args.vae_config_sha256,
            vae_checkpoint_sha256=admission["vae_sha256"],
            environment_report_sha256=args.environment_report_sha256,
            precision=args.precision,
            device=args.device,
        )
    )

    campaign = ProductionExtractionCampaign(
        units,
        output_root=args.activations,
        ledger_path=Path(args.activations) / "production_extraction_ledger.jsonl",
        extraction_spec_hash=a9_extraction_spec_hash(),
    )

    def decoder_factory(unit):
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

    print(f"A9_STAGE={A9_STAGE}")
    print(f"A9_ADMITTED_CAPTURES={counts['captures']}")
    print(f"A9_EXPECTED_FORWARDS={counts['forwards']}")
    print(f"A9_EXPECTED_ARRAYS={counts['arrays']}")
    print(f"A9_ATTRITION_BRANCH={admission['attrition_branch']}")

    started = time.time()
    try:
        result = campaign.run(
            decoder_factory,
            checkpoint_identity=admission["checkpoint_sha256"],
            preprocessing_identity=runtime_identity.preprocessing_identity,
            on_unit=lambda unit_id, state: print(
                f"A9_UNIT={unit_id} STATE={state}", flush=True
            ),
        )
        budget = campaign.assert_forward_budget()
    except ExperimentIIIError as error:
        print(f"BLOCKER_CODE={error.blocker}", file=sys.stderr)
        print(error.message, file=sys.stderr)
        print("A9_EXECUTED=true", file=sys.stderr)
        return 1
    elapsed = time.time() - started

    inventory = result["inventory"]
    print(f"A9_CAPTURES_COMPLETE={inventory['captures_complete']}")
    print(f"A9_CAPTURES_SKIPPED_AS_COMPLETE={len(result['skipped'])}")
    print(f"A9_MODEL_FORWARDS_EXECUTED={budget['forwards']}")
    print(f"A9_FORWARD_BUDGET={budget['expected_forwards']}")
    print(f"A9_ARRAYS_COMPLETE={inventory['arrays_complete']}")
    print(f"A9_ELAPSED_SECONDS={elapsed:.1f}")
    print(f"A9_EXTRACTION_COMPLETE={str(inventory['complete']).lower()}")
    print("A9_EXECUTED=true")
    if not inventory["complete"]:
        print("BLOCKER_CODE=EXTRACTION_INVENTORY_INCOMPLETE", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

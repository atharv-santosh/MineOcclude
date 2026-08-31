"""A4 -- the P0 analysis half: from captured frames to the selected ladder.

``I07`` is an ``A1`` task and its completion condition is "RVE computable **end
to end**". The measurement half was built; this is the analysis half that turns
252 captured units into the eight ``A4`` artifacts, ending at
``P0_SELECTION_RECEIPT`` -- ``A4``'s exit condition.

It exists as a separate module for one reason: **there is exactly one scientific
implementation of record.** Every formula here is called, not restated.
:mod:`rve` owns the mathematics and the nine validity rules, :mod:`p0_bindings`
owns the Amendment 3 bindings, :mod:`sentinels` owns the envelope, and
:mod:`placements` owns the coordinates. This module is orchestration and
provenance: it decides nothing scientific, and it must not, because it runs with
the measurements in hand.

The pipeline, in the frozen order:

    frames -> sRGB->linear (float64)
           -> per-state coordinate-wise medians
           -> L0 noise threshold per placement          (7.10c, tunable-free)
           -> shared support mask per placement          (union, dilate 2)
           -> D, N, E per (condition, placement, block)
           -> RVE = E / E(L0, p, b)
           -> placement median over blocks
           -> condition median over the nine placements
           -> nine validity rules per candidate triple   (7.5)
           -> exhaustive 1,320-permutation ladder search (7.6)
           -> P0_PASS | P0_NO_VALID_LADDER | P0_TECHNICAL_FAIL

L0 is analysed first because every placement's mask is derived from it and must
exist before any candidate is scored against it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from mineocclude.experiment_iii.authority import (
    AUTHORITY_FREEZE_COMMIT,
    AUTHORITY_VERSION,
    FRAMEBUFFER_HEIGHT,
    FRAMEBUFFER_WIDTH,
    verify_authority_binding,
)
from mineocclude.experiment_iii.conditions import ELIGIBLE_STAINED_GLASS
from mineocclude.experiment_iii.errors import ExperimentIIIError
from mineocclude.experiment_iii.p0_bindings import (
    background_gate,
    l0_noise_threshold,
    p0_bootstrap_seed,
)
from mineocclude.experiment_iii.placements import (
    placement_coordinates,
    sentinel_placement_indices,
)
from mineocclude.experiment_iii.rve import (
    ABBA_BLOCKS,
    ADJACENT_SEPARATION_MIN,
    BOOTSTRAP_REPLICATES,
    L3_SNR_MIN,
    L3_SNR_MIN_PLACEMENTS,
    LADDER_ZONES,
    ORDER_STABILITY_MIN_PLACEMENTS,
    PLACEMENT_COUNT,
    REPLICATE_CV_MAX,
    TARGET_RVE_POINTS,
    aggregate_condition,
    aggregate_placement,
    excess_energy,
    masked_energy,
    placement_mask,
    robust_median_image,
    rve,
    select_ladder,
    split_half_noise,
    srgb_to_linear,
)
from mineocclude.experiment_iii.schema import write_json_atomic
from mineocclude.experiment_iii.sentinels import sentinel_envelope_artifact
from mineocclude.experiment_iii.source_closure import closure_digest

__all__ = [
    "A4_ARTIFACTS",
    "L0_CONDITION_KEY",
    "P0_OUTCOMES",
    "P0_VALIDITY_RULE_IDS",
    "STONE_CONDITION_KEY",
    "CellFrames",
    "analyse_p0",
    "load_selected_ladder",
    "load_unit_frames",
    "read_frame_rgb",
    "write_a4_artifacts",
]

L0_CONDITION_KEY = "L0"
STONE_CONDITION_KEY = "L4"

#: The eight ``A4`` outputs, at the exact paths the frozen
#: EXPECTED_ARTIFACT_INVENTORY specifies. Every one has a producer here.
A4_ARTIFACTS = (
    "P0_MANIFEST.json",
    "P0_IMAGE_INVENTORY.jsonl",
    "P0_RVE_TABLE.json",
    "P0_BOOTSTRAP_RESULTS.json",
    "P0_MASK_INVENTORY.json",
    "P0_SELECTED_LADDER.json",
    "P0_SELECTION_RECEIPT.json",
    "P0_SENTINEL_ENVELOPE.json",
)

#: Authority 7.6 ``outcomes`` -- the only terminal states A4 may report. The
#: search returns the bare "NO_VALID_LADDER"; the taxonomy code and the runbook
#: entry are "P0_NO_VALID_LADDER", so the emitted state is normalised here rather
#: than leaving two spellings of one outcome in circulation.
P0_OUTCOMES = {
    "P0_PASS": "P0_PASS",
    "NO_VALID_LADDER": "P0_NO_VALID_LADDER",
    "P0_NO_VALID_LADDER": "P0_NO_VALID_LADDER",
    "P0_TECHNICAL_FAIL": "P0_TECHNICAL_FAIL",
}

#: The nine rules of authority 7.5, named so a validity record can be read
#: rule-by-rule rather than as one opaque boolean.
P0_VALIDITY_RULE_IDS = (
    "L1_zone",
    "L2_zone",
    "L3_zone",
    "adjacent_separation_L1_L2",
    "adjacent_separation_L2_L3",
    "strict_order_stability",
    "L3_snr",
    "replicate_repeatability",
    "background",
)

#: Which A4 blocker each failing rule raises when it is the reason no ladder
#: qualified. Without this the codes exist in the taxonomy with no producer.
_RULE_BLOCKERS = {
    "L3_snr": "RVE_SNR_INSUFFICIENT",
    "strict_order_stability": "RVE_ORDER_UNSTABLE",
    "bootstrap_lower_bounds_positive": "RVE_BOOTSTRAP_LOWER_BOUND_NOT_POSITIVE",
    "background": "RVE_BACKGROUND_TOLERANCE_EXCEEDED",
}


# --------------------------------------------------------------------------
# Frames in
# --------------------------------------------------------------------------


def read_frame_rgb(path: Path) -> np.ndarray:
    """Decode one captured PNG as source RGB, uint8, exactly 640x360.

    Authority 7.1: the input is the **source** RGB the client rendered, never a
    model-normalized tensor. The decode is therefore plain RGB with no resize, no
    channel reorder and no colour management; a frame of the wrong size is a
    blocker rather than something to correct.
    """
    from PIL import Image  # imported lazily: analysis-only dependency

    with Image.open(path) as handle:
        image = handle.convert("RGB")
        array = np.asarray(image, dtype=np.uint8)
    if array.shape[:2] != (FRAMEBUFFER_HEIGHT, FRAMEBUFFER_WIDTH):
        raise ExperimentIIIError(
            "ENV_FRAMEBUFFER_SIZE_MISMATCH",
            f"{path} decodes to {array.shape[1]}x{array.shape[0]}, not "
            f"{FRAMEBUFFER_WIDTH}x{FRAMEBUFFER_HEIGHT}",
        )
    return array


@dataclass(frozen=True)
class CellFrames:
    """One (condition, placement, block) cell's linearized frames.

    ``present`` and ``absent`` are in ascending capture index across the cell's
    ABBA slots, which is what the frozen split-half rule is defined over.
    """

    condition_key: str
    placement_index: int
    block_index: int
    present: tuple[np.ndarray, ...]
    absent: tuple[np.ndarray, ...]
    frame_paths: tuple[str, ...]
    frame_hashes: tuple[str, ...]

    @property
    def cell_id(self) -> str:
        return f"{self.condition_key}__p{self.placement_index}__b{self.block_index}"


def load_unit_frames(
    unit_evidence: Mapping[str, Any],
    *,
    loader: Callable[[Path], np.ndarray] = read_frame_rgb,
    frame_root: Path | None = None,
) -> CellFrames:
    """Turn one unit's capture evidence into a linearized cell.

    The evidence is the driver's own per-slot record, so the present/absent split
    follows the **realised** ABBA order rather than the planned one, and the
    frames arrive already bound to observed ticks.
    """
    slots = list(unit_evidence.get("slots") or [])
    if not slots:
        raise ExperimentIIIError(
            "P0_TECHNICAL_FAIL",
            f"unit {unit_evidence.get('unit_id')} carries no slots; there is "
            f"nothing to analyse",
        )
    present: list[np.ndarray] = []
    absent: list[np.ndarray] = []
    paths: list[str] = []
    hashes: list[str] = []
    for slot in sorted(slots, key=lambda row: int(row["slot_index"])):
        target_present = bool(slot["target_present"])
        for path_text, digest in zip(
            slot.get("frame_paths") or [], slot.get("frame_hashes") or [], strict=False
        ):
            path = Path(path_text)
            if frame_root is not None and not path.is_absolute():
                path = Path(frame_root) / path
            linear = srgb_to_linear(loader(path))
            (present if target_present else absent).append(linear)
            paths.append(path.as_posix())
            hashes.append(str(digest))
    if not present or not absent:
        raise ExperimentIIIError(
            "P0_TECHNICAL_FAIL",
            f"unit {unit_evidence.get('unit_id')} produced "
            f"{len(present)} present and {len(absent)} absent frames; a cell needs "
            f"both states",
        )
    return CellFrames(
        condition_key=str(unit_evidence["condition_key"]),
        placement_index=int(unit_evidence["placement_index"]),
        block_index=int(unit_evidence["block_index"]),
        present=tuple(present),
        absent=tuple(absent),
        frame_paths=tuple(paths),
        frame_hashes=tuple(hashes),
    )


# --------------------------------------------------------------------------
# The analysis
# --------------------------------------------------------------------------


def _finite_or_none(value: float) -> float | None:
    """Serialise a non-finite ratio as null rather than as a fabricated number.

    ``E / N`` is unbounded when the split-half noise is exactly zero, which
    authority 7.10c explicitly admits (``zero_threshold_admissible``). The rule
    comparison keeps the infinity -- an unbounded ratio passes an
    "at least 5.0" test -- but the artifact records ``null`` plus an explicit
    flag, because writing a large finite stand-in would misreport the measurement.
    """
    numeric = float(value)
    return None if not np.isfinite(numeric) else numeric


def _index_cells(cells: Sequence[CellFrames]) -> dict[tuple[str, int, int], CellFrames]:
    indexed: dict[tuple[str, int, int], CellFrames] = {}
    for cell in cells:
        key = (cell.condition_key, cell.placement_index, cell.block_index)
        if key in indexed:
            raise ExperimentIIIError(
                "P0_TECHNICAL_FAIL", f"cell {cell.cell_id} was supplied twice"
            )
        indexed[key] = cell
    return indexed


def analyse_p0(
    cells: Sequence[CellFrames],
    *,
    candidates: Sequence[str] = ELIGIBLE_STAINED_GLASS,
    bootstrap_seed: int | None = None,
) -> dict[str, Any]:
    """Run the whole frozen P0 analysis and return every A4 result body.

    Nothing is chosen here. The mask comes from L0, the threshold has no tunable
    constant, the validity rules and the search live in :mod:`rve`, and the seed
    is derived from the immutable Phase 0 design hash. That is deliberate: this
    code runs with the measurements available, so it must not be able to move
    anything that decides which materials become ``L1``/``L2``/``L3``.
    """
    indexed = _index_cells(cells)
    placements = [row["placement_index"] for row in placement_coordinates()]
    blocks = list(range(len(ABBA_BLOCKS)))
    seed = p0_bootstrap_seed() if bootstrap_seed is None else int(bootstrap_seed)

    roster = list(candidates)
    unsupported = sorted(set(roster) - set(ELIGIBLE_STAINED_GLASS))
    if unsupported:
        raise ExperimentIIIError(
            "P0_CANDIDATE_ID_UNSUPPORTED",
            f"candidates outside the twelve-item roster: {unsupported}",
        )
    measured = [L0_CONDITION_KEY, *roster, STONE_CONDITION_KEY]

    missing = [
        f"{condition}__p{placement}__b{block}"
        for condition in measured
        for placement in placements
        for block in blocks
        if (condition, placement, block) not in indexed
    ]
    if missing:
        raise ExperimentIIIError(
            "P0_TECHNICAL_FAIL",
            f"the P0 analysis needs every measured cell; {len(missing)} are "
            f"absent, first {missing[:4]}",
        )

    # -- L0 first: the threshold and the shared mask, per placement ---------
    masks: dict[int, np.ndarray] = {}
    mask_records: list[dict[str, Any]] = []
    medians: dict[tuple[str, int, int], tuple[np.ndarray, np.ndarray]] = {}

    def cell_medians(key: tuple[str, int, int]) -> tuple[np.ndarray, np.ndarray]:
        if key not in medians:
            cell = indexed[key]
            medians[key] = (
                robust_median_image(cell.present),
                robust_median_image(cell.absent),
            )
        return medians[key]

    for placement in placements:
        l0_absent_blocks = [
            list(indexed[(L0_CONDITION_KEY, placement, block)].absent)
            for block in blocks
        ]
        threshold = l0_noise_threshold(l0_absent_blocks)
        l0_pairs = [
            cell_medians((L0_CONDITION_KEY, placement, block)) for block in blocks
        ]
        mask = placement_mask(l0_pairs, threshold["threshold"], dilation=2)
        masks[placement] = mask
        mask_records.append(
            {
                "placement_index": placement,
                "l0_noise_threshold": threshold,
                "mask_pixels": int(mask.sum()),
                "mask_fraction_of_frame": float(mask.mean()),
                "dilation_pixels": 2,
                "source": "L0_PRESENT_MINUS_ABSENT_ABOVE_FROZEN_NOISE_THRESHOLD",
                "union_over_blocks": True,
                "shared_across_all_candidates": True,
                "per_candidate_mask_forbidden": True,
            }
        )

    # -- every cell's D, N, E, and the L0 normaliser ------------------------
    energies: dict[tuple[str, int, int], dict[str, float]] = {}
    background: dict[tuple[str, int, int], dict[str, Any]] = {}
    for condition in measured:
        for placement in placements:
            mask = masks[placement]
            for block in blocks:
                key = (condition, placement, block)
                cell = indexed[key]
                present_median, absent_median = cell_medians(key)
                d = masked_energy(present_median, absent_median, mask)
                n = split_half_noise(cell.absent, mask)
                e = excess_energy(d, n)
                energies[key] = {"D": d, "N": n, "E": e}
                background[key] = background_gate(
                    present_median, absent_median, cell.absent, mask
                )

    for placement in placements:
        for block in blocks:
            if energies[(L0_CONDITION_KEY, placement, block)]["E"] <= 0.0:
                raise ExperimentIIIError(
                    "RVE_MASK_DEGENERATE",
                    f"L0 excess energy at placement {placement} block {block} is "
                    f"not positive; RVE cannot be normalised against it",
                )

    # -- RVE, and the aggregations -----------------------------------------
    rve_rows: list[dict[str, Any]] = []
    placement_scores: dict[str, list[float]] = {}
    replicate_blocks: dict[str, list[list[float]]] = {}
    snr: dict[str, list[float]] = {}
    background_ok: dict[str, bool] = {}
    condition_medians: dict[str, float] = {}
    block_rve: dict[tuple[str, int], list[float]] = {}

    for condition in measured:
        per_placement: list[float] = []
        per_placement_blocks: list[list[float]] = []
        per_placement_snr: list[float] = []
        ok = True
        for placement in placements:
            values: list[float] = []
            snr_values: list[float] = []
            for block in blocks:
                key = (condition, placement, block)
                e_l0 = energies[(L0_CONDITION_KEY, placement, block)]["E"]
                value = rve(energies[key]["E"], e_l0)
                values.append(value)
                noise = energies[key]["N"]
                snr_values.append(
                    float("inf") if noise <= 0.0 else energies[key]["E"] / noise
                )
                ok = ok and bool(background[key]["passed"])
                rve_rows.append(
                    {
                        "condition_key": condition,
                        "placement_index": placement,
                        "block_index": block,
                        "D": energies[key]["D"],
                        "N": energies[key]["N"],
                        "E": energies[key]["E"],
                        "E_L0": e_l0,
                        "RVE": value,
                        "excess_energy_to_noise_ratio": _finite_or_none(snr_values[-1]),
                        "noise_free_cell": not np.isfinite(snr_values[-1]),
                        "background": background[key],
                    }
                )
            block_rve[(condition, placement)] = values
            per_placement.append(aggregate_placement(values))
            per_placement_blocks.append(values)
            per_placement_snr.append(float(np.median(np.asarray(snr_values))))
        placement_scores[condition] = per_placement
        replicate_blocks[condition] = per_placement_blocks
        snr[condition] = per_placement_snr
        background_ok[condition] = ok
        condition_medians[condition] = aggregate_condition(per_placement)

    # -- the deterministic search, in rve.py, over the twelve candidates ----
    selection = select_ladder(
        roster,
        {name: placement_scores[name] for name in roster},
        snr={name: snr[name] for name in roster},
        replicate_blocks={name: replicate_blocks[name] for name in roster},
        background_ok={name: background_ok[name] for name in roster},
        bootstrap_seed=seed,
    )

    validity = _validity_records(selection["all_evaluations"])
    # Authority 7.6 froze exactly three outcomes: P0_PASS, P0_NO_VALID_LADDER and
    # P0_TECHNICAL_FAIL. select_ladder returns the bare "NO_VALID_LADDER"; the
    # terminal state that reaches an artifact, a receipt or an operator must be
    # the authority's own string, because that is what the blocker taxonomy and
    # the recovery runbook are keyed on.
    result = P0_OUTCOMES[str(selection["P0_RESULT"])]
    blockers = (
        _no_valid_ladder_blockers(selection["all_evaluations"])
        if result == "P0_NO_VALID_LADDER"
        else []
    )

    return {
        "P0_RESULT": result,
        "PRODUCTION_AUTHORIZED": bool(selection["PRODUCTION_AUTHORIZED"]),
        "selection": selection,
        "validity_records": validity,
        "blockers": blockers,
        "rve_rows": rve_rows,
        "mask_records": mask_records,
        "condition_medians": condition_medians,
        "placement_scores": placement_scores,
        "replicate_blocks": replicate_blocks,
        "snr": snr,
        "background_ok": background_ok,
        "block_rve": block_rve,
        "bootstrap_seed": seed,
        "cells_analysed": len(indexed),
        "measured_conditions": measured,
        "placements": placements,
    }


def _validity_records(evaluations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """One machine-readable record per evaluated triple, rule by rule.

    Authority 7.5 has nine rules plus the bootstrap gate; a single ``valid``
    boolean cannot be audited, so every rule reports its own outcome and the
    threshold it was compared against.
    """
    references = {
        "L1_zone": list(LADDER_ZONES["L1"]),
        "L2_zone": list(LADDER_ZONES["L2"]),
        "L3_zone": list(LADDER_ZONES["L3"]),
        "adjacent_separation_L1_L2": ADJACENT_SEPARATION_MIN,
        "adjacent_separation_L2_L3": ADJACENT_SEPARATION_MIN,
        "strict_order_stability": ORDER_STABILITY_MIN_PLACEMENTS,
        "L3_snr": [L3_SNR_MIN, L3_SNR_MIN_PLACEMENTS],
        "replicate_repeatability": REPLICATE_CV_MAX,
        "background": "NOISE_RELATIVE_OUTSIDE_MASK_GATE_V1_6",
        "bootstrap_lower_bounds_positive": 0.0,
    }
    records = []
    for evaluation in evaluations:
        rules = evaluation["rules"]
        records.append(
            {
                "triple": list(evaluation["triple"]),
                "medians": dict(evaluation["medians"]),
                "valid": bool(evaluation["valid"]),
                "squared_distance_to_target": evaluation["squared_distance_to_target"],
                "bootstrap_lower_bounds": dict(
                    evaluation.get("bootstrap_lower_bounds") or {}
                ),
                "rules": [
                    {
                        "rule_id": name,
                        "outcome": "PASS" if rules[name] else "FAIL",
                        "reference": references.get(name),
                        "blocker": None
                        if rules[name]
                        else _RULE_BLOCKERS.get(name, "P0_NO_VALID_LADDER"),
                    }
                    for name in (*P0_VALIDITY_RULE_IDS, "bootstrap_lower_bounds_positive")
                ],
            }
        )
    return records


def _no_valid_ladder_blockers(
    evaluations: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Which rules eliminated every triple, as taxonomy codes with counts.

    ``RVE_SNR_INSUFFICIENT``, ``RVE_ORDER_UNSTABLE`` and
    ``RVE_BOOTSTRAP_LOWER_BOUND_NOT_POSITIVE`` are named ``A4`` blockers. They had
    no producer anywhere: their rules were evaluated as booleans and no code path
    ever raised them. This is that producer.
    """
    counts: dict[str, int] = {}
    for evaluation in evaluations:
        for name, passed in evaluation["rules"].items():
            if not passed:
                counts[name] = counts.get(name, 0) + 1
    total = len(evaluations)
    return [
        {
            "rule_id": name,
            "blocker": _RULE_BLOCKERS.get(name, "P0_NO_VALID_LADDER"),
            "triples_eliminated": count,
            "eliminated_every_triple": count == total,
        }
        for name, count in sorted(counts.items(), key=lambda row: (-row[1], row[0]))
    ]


# --------------------------------------------------------------------------
# Artifacts out
# --------------------------------------------------------------------------


def write_a4_artifacts(
    analysis: Mapping[str, Any],
    *,
    out_dir: Path,
    capture_manifest: Mapping[str, Any],
    campaign_state_sha256: str,
    host_receipt: Mapping[str, Any] | None = None,
    image_inventory: Sequence[Mapping[str, Any]] = (),
    namespace_root: Path | None = None,
) -> dict[str, str]:
    """Write all eight ``A4`` artifacts atomically and return their digests.

    ``P0_SELECTION_RECEIPT`` is written **last**: it is ``A4``'s exit condition,
    and it binds the digest of every artifact it depends on, so it cannot exist
    describing a state that was never written.
    """
    out_dir = Path(out_dir)
    binding = verify_authority_binding()
    closure = closure_digest()
    selection = analysis["selection"]
    result = str(analysis["P0_RESULT"])
    digests: dict[str, str] = {}

    provenance = {
        "authority_version": AUTHORITY_VERSION,
        "authority_binding": binding,
        "authority_freeze_commit": AUTHORITY_FREEZE_COMMIT,
        "source_closure": closure,
        "p0_campaign_state_sha256": campaign_state_sha256,
        "capture_manifest_sha256": capture_manifest.get("units_sha256"),
        "rve_implementation": "mineocclude.experiment_iii.rve",
        "rve_implementation_version": "authority-7.1-7.8-v1.6",
        "analysis_implementation": "mineocclude.experiment_iii.p0_analysis",
    }

    def _write(name: str, body: dict[str, Any]) -> str:
        return write_json_atomic(out_dir / name, body, root=namespace_root)

    digests["P0_MANIFEST.json"] = _write(
        "P0_MANIFEST.json",
        {
            "schema_version": "mineocclude-experiment-iii-p0-manifest-a4-v1",
            "authority_section": "7.1-7.11",
            "provenance": provenance,
            "measured_conditions": list(analysis["measured_conditions"]),
            "placements": list(analysis["placements"]),
            "sentinel_placement_indices": list(sentinel_placement_indices()),
            "replicate_blocks": len(ABBA_BLOCKS),
            "abba_blocks": [list(block) for block in ABBA_BLOCKS],
            "cells_analysed": analysis["cells_analysed"],
            "bootstrap_seed": analysis["bootstrap_seed"],
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "target_rve_points": list(TARGET_RVE_POINTS),
            "ladder_zones": {k: list(v) for k, v in LADDER_ZONES.items()},
            "source": "RAW_SOURCE_RGB_640x360_NEVER_MODEL_NORMALIZED",
            "p0_executed": True,
        },
    )

    inventory_path = out_dir / "P0_IMAGE_INVENTORY.jsonl"
    inventory_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        _canonical_line(row) for row in image_inventory
    ]
    payload = "".join(lines)
    tmp = inventory_path.with_suffix(inventory_path.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8", newline="\n")
    tmp.replace(inventory_path)
    digests["P0_IMAGE_INVENTORY.jsonl"] = hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()

    digests["P0_RVE_TABLE.json"] = _write(
        "P0_RVE_TABLE.json",
        {
            "schema_version": "mineocclude-experiment-iii-p0-rve-table-v1",
            "authority_section": "7.3, 7.4",
            "provenance": provenance,
            "energy": "D(c,p,b) = sum_{u in M_p} ||P_lin - A_lin||_2^2",
            "noise": "N from the deterministic split-half of the ABSENT frames",
            "excess_energy": "E = max(D - N, 0)",
            "normalization": "RVE = E / E(L0,p,b)",
            "placement_aggregation": "MEDIAN_OVER_REPLICATE_BLOCKS",
            "condition_aggregation": "MEDIAN_OVER_9_PLACEMENTS",
            "rows": list(analysis["rve_rows"]),
            "placement_scores": {
                key: list(value) for key, value in analysis["placement_scores"].items()
            },
            "condition_medians": dict(analysis["condition_medians"]),
            "excess_energy_to_noise_ratio": {
                key: [_finite_or_none(entry) for entry in value]
                for key, value in analysis["snr"].items()
            },
            "null_ratio_means": "ZERO_SPLIT_HALF_NOISE_UNBOUNDED_RATIO",
            "V_L0_defined": 1.0,
            "V_L4_measured_not_forced_to_zero": True,
            "uncapped_values_retained": True,
        },
    )

    digests["P0_BOOTSTRAP_RESULTS.json"] = _write(
        "P0_BOOTSTRAP_RESULTS.json",
        {
            "schema_version": "mineocclude-experiment-iii-p0-bootstrap-v1",
            "authority_section": "7.5",
            "provenance": provenance,
            "bootstrap_seed": analysis["bootstrap_seed"],
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "generator": "numpy.random.default_rng",
            "resampled_unit": "PLACEMENT",
            "lower_bound_must_exceed": 0.0,
            "per_triple": [
                {
                    "triple": record["triple"],
                    "bootstrap_lower_bounds": record["bootstrap_lower_bounds"],
                }
                for record in analysis["validity_records"]
                if record["bootstrap_lower_bounds"]
            ],
        },
    )

    digests["P0_MASK_INVENTORY.json"] = _write(
        "P0_MASK_INVENTORY.json",
        {
            "schema_version": "mineocclude-experiment-iii-p0-mask-inventory-v1",
            "authority_section": "7.3, 7.10c",
            "provenance": provenance,
            "one_mask_per_placement": True,
            "shared_by_every_candidate": True,
            "per_candidate_mask_forbidden": True,
            "derived_from": "L0_ONLY",
            "candidate_frames_consumed": False,
            "masks": list(analysis["mask_records"]),
        },
    )

    ladder_body: dict[str, Any] = {
        "schema_version": "mineocclude-experiment-iii-p0-selected-ladder-v1",
        "authority_section": "7.6",
        "provenance": provenance,
        "P0_RESULT": result,
        "PRODUCTION_AUTHORIZED": bool(analysis["PRODUCTION_AUTHORIZED"]),
        "selection_rule": "MIN_SQUARED_DISTANCE_THEN_LEXICOGRAPHIC_REGISTRY_ID",
        "target_points": list(TARGET_RVE_POINTS),
        "evaluated_triples": selection["evaluated_triples"],
        "candidate_roster": list(ELIGIBLE_STAINED_GLASS),
        "provisional_placeholder_materials_used": False,
    }
    if selection.get("selected"):
        ladder_body.update(
            {
                "L1": selection["selected"]["L1"],
                "L2": selection["selected"]["L2"],
                "L3": selection["selected"]["L3"],
                "V_c": selection["selected"]["V_c"],
            }
        )
    else:
        ladder_body["blockers"] = list(analysis["blockers"])
    digests["P0_SELECTED_LADDER.json"] = _write(
        "P0_SELECTED_LADDER.json", ladder_body
    )

    sentinel_body = _sentinel_body(analysis, binding=binding)
    digests["P0_SENTINEL_ENVELOPE.json"] = _write(
        "P0_SENTINEL_ENVELOPE.json", sentinel_body
    )

    receipt = {
        "schema_version": "mineocclude-experiment-iii-p0-selection-receipt-v1",
        "authority_section": "7.5, 7.6",
        "stage": "A4",
        "provenance": provenance,
        "P0_RESULT": result,
        "PRODUCTION_AUTHORIZED": bool(analysis["PRODUCTION_AUTHORIZED"]),
        "selected_ladder": selection.get("selected"),
        "selection_rule": "MIN_SQUARED_DISTANCE_THEN_LEXICOGRAPHIC_REGISTRY_ID",
        "target_points": list(TARGET_RVE_POINTS),
        "evaluated_triples": selection["evaluated_triples"],
        "exhaustive_search": True,
        "tie_break": "LEXICOGRAPHIC_REGISTRY_ID_L1_THEN_L2_THEN_L3",
        "tie_break_evidence": _tie_break_evidence(analysis),
        "validity_rule_ids": list(P0_VALIDITY_RULE_IDS),
        "validity_records": list(analysis["validity_records"]),
        "blockers": list(analysis["blockers"]),
        "condition_medians": dict(analysis["condition_medians"]),
        "capture_host_receipt": dict(host_receipt or {}),
        "capture_unit_inventory": {
            "cells_analysed": analysis["cells_analysed"],
            "measured_conditions": list(analysis["measured_conditions"]),
            "placements": list(analysis["placements"]),
            "replicate_blocks": len(ABBA_BLOCKS),
        },
        "artifact_sha256": dict(digests),
        "model_inference_used": False,
        "outcome_blind": True,
        "occurs_before_any_experiment_iii_model_inference": True,
        "is_provisional": False,
        "superseded": False,
        "geometric_fallback_on_failure": False,
    }
    digests["P0_SELECTION_RECEIPT.json"] = _write(
        "P0_SELECTION_RECEIPT.json", receipt
    )
    return digests


def _canonical_line(row: Mapping[str, Any]) -> str:
    return json.dumps(dict(row), sort_keys=True, allow_nan=False) + "\n"


def _sentinel_body(
    analysis: Mapping[str, Any], *, binding: Mapping[str, Any]
) -> dict[str, Any]:
    """The sentinel envelope, derived from the selected ladder's own replicates.

    When no ladder qualified there is nothing to derive an envelope from, and the
    artifact says so rather than inventing bounds a later batch would be measured
    against.
    """
    selection = analysis["selection"]
    if not selection.get("selected"):
        return {
            "schema_version": "mineocclude-experiment-iii-p0-sentinel-envelope-v1",
            "authority_section": "7.9, 7.10e",
            "authority_binding": dict(binding),
            "sentinel_placement_indices": list(sentinel_placement_indices()),
            "envelope": None,
            "P0_RESULT": analysis["P0_RESULT"],
            "reason": (
                "no valid ladder was selected, so there is no L1 replicate spread "
                "to derive a repeatability envelope from"
            ),
            "numeric_envelope_bound": False,
            "numeric_envelope_bound_in": "P2",
        }
    l1 = selection["selected"]["L1"]
    block_rve = analysis["block_rve"]
    scores = {
        index: list(block_rve[(l1, index)]) for index in sentinel_placement_indices()
    }
    body = sentinel_envelope_artifact(
        scores,
        authority_binding=binding,
        p0_selection_receipt_sha256="PENDING_SELECTION_RECEIPT",
    )
    body["derived_from_condition"] = l1
    body["P0_RESULT"] = analysis["P0_RESULT"]
    return body


def _tie_break_evidence(analysis: Mapping[str, Any]) -> dict[str, Any]:
    """Whether the lexicographic tie-break actually decided the selection."""
    valid = [
        record
        for record in analysis["validity_records"]
        if record["valid"]
    ]
    if not valid:
        return {"applied": False, "reason": "NO_VALID_TRIPLE"}
    best = min(row["squared_distance_to_target"] for row in valid)
    tied = sorted(
        tuple(row["triple"])
        for row in valid
        if row["squared_distance_to_target"] == best
    )
    return {
        "applied": len(tied) > 1,
        "valid_triples": len(valid),
        "minimum_squared_distance": best,
        "triples_at_minimum": [list(triple) for triple in tied],
        "selected": list(tied[0]),
        "rule": "LEXICOGRAPHIC_REGISTRY_ID_L1_THEN_L2_THEN_L3",
    }


# --------------------------------------------------------------------------
# Downstream consumption
# --------------------------------------------------------------------------


def load_selected_ladder(path: Path) -> dict[str, str]:
    """Load ``P0_SELECTED_LADDER.json`` for P1/P2/production, fail-closed.

    A schedule naming a placeholder material is indistinguishable from a real one,
    and that is exactly how a pre-P0 dry run once acquired ``white``/``lime``/
    ``blue`` across all 25 production identities. So a ladder is accepted only if
    it is a genuine A4 output: right schema, ``P0_PASS``, production authorized,
    materials inside the frozen roster, and bound to the current authority.
    """
    path = Path(path)
    if not path.is_file():
        raise ExperimentIIIError(
            "P0_CANDIDATE_ID_UNSUPPORTED", f"no selected ladder at {path}"
        )
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ExperimentIIIError(
            "P0_CANDIDATE_ID_UNSUPPORTED", f"{path} is malformed: {error}"
        ) from error
    if not isinstance(body, Mapping):
        raise ExperimentIIIError(
            "P0_CANDIDATE_ID_UNSUPPORTED", f"{path} is not a ladder object"
        )
    schema = str(body.get("schema_version", ""))
    if schema != "mineocclude-experiment-iii-p0-selected-ladder-v1":
        raise ExperimentIIIError(
            "P0_CANDIDATE_ID_UNSUPPORTED",
            f"{path} carries schema {schema!r}; only a real P0_SELECTED_LADDER "
            f"produced by A4 may resolve L1/L2/L3",
        )
    if str(body.get("P0_RESULT")) != "P0_PASS" or not body.get("PRODUCTION_AUTHORIZED"):
        raise ExperimentIIIError(
            "P0_NO_VALID_LADDER",
            f"{path} reports P0_RESULT={body.get('P0_RESULT')!r}; production may "
            f"only run against a passed P0",
        )
    if body.get("is_provisional") or body.get("superseded"):
        raise ExperimentIIIError(
            "P0_CANDIDATE_ID_UNSUPPORTED",
            f"{path} is a provisional or superseded ladder and must not enter P2",
        )
    binding = body.get("provenance", {}).get("authority_binding") or {}
    current = verify_authority_binding()
    if binding.get("AUTHORITY_SHA256") != current["AUTHORITY_SHA256"]:
        raise ExperimentIIIError(
            "PROVENANCE_AUTHORITY_DRIFT",
            f"{path} was produced under authority "
            f"{binding.get('AUTHORITY_SHA256')} and this run is bound to "
            f"{current['AUTHORITY_SHA256']}",
        )
    ladder = {level: body.get(level) for level in ("L1", "L2", "L3")}
    missing = sorted(level for level, value in ladder.items() if not value)
    if missing:
        raise ExperimentIIIError(
            "P0_CANDIDATE_ID_UNSUPPORTED", f"{path} does not name {missing}"
        )
    outside = sorted(set(ladder.values()) - set(ELIGIBLE_STAINED_GLASS))
    if outside:
        raise ExperimentIIIError(
            "P0_CANDIDATE_ID_UNSUPPORTED",
            f"{path} names materials outside the twelve-item roster: {outside}",
        )
    if len(set(ladder.values())) != 3:
        raise ExperimentIIIError(
            "P0_CANDIDATE_ID_UNSUPPORTED",
            f"{path} repeats a material across levels: {ladder}",
        )
    return {level: str(value) for level, value in ladder.items()}

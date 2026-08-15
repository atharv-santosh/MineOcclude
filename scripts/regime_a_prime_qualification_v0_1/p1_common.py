"""Shared helpers for Regime A prime qualification P1 (EXPLORATORY_EXISTING_DATA).

P1 is exploratory qualification on EXISTING data only. Nothing here may alter,
recompute, relabel, or supersede the closed confirmatory Regime A first25 result
(FAIL_NO_DEFENSIBLE_DECODING / REGIME_A_FIRST25_PASS_CONTINUE=NO), and nothing
here may be reinterpreted as confirmatory Regime A prime evidence.

Hard scope: no Minecraft, no MineWorld, no activation extraction, no decoder
fitting, no new model inference. Frozen held-out predictions are REUSED.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
INTEG = REPO / "docs/status/integration/regime_a_occlusion_extraction_v0_1"
CONF = INTEG / "first25_analysis"
PM = INTEG / "postmortem_v0_1"
OUT = REPO / "docs/status/integration/regime_a_prime_qualification_v0_1"

# Immutable capture metadata cache (outside the repository; re-downloadable and
# hash-verified against the P0-bound durable receipts on every use).
CACHE = Path("/home/sagemaker-user/.mineocclude_cache/p1_qualification_v0_1")
META = CACHE / "meta"

BRANCH = "exploration/regime-a-prime-qualification-v0-1"

# Frozen model-input semantics (scripts/run_regime_a.py :: extract, line 930):
#     indices = list(range(target - 15, target + 1))   # 16 pairs, incl. target
EFFECTIVE_PRECEDING = 15
CONTEXT_PAIRS = 16

BOOTSTRAP_SEED = 20260815
BOOTSTRAP_RESAMPLES = 10000

# Domains are named by the existing authority, not invented here.
#   FULL_EVIDENCE_BEARING_IN_CONTEXT -- tau 1..15. This is simultaneously the
#     frozen confirmatory primary domain ("primary_rows": "tau1..15") and,
#     empirically, the exact set of rows carrying any in-context rendered
#     sheep-pixel evidence (BEYOND_CONTEXT tau16..19 carries none, so the
#     last-rendered-evidence baseline is undefined there). The boundary is
#     forced by the data, not chosen.
#   SHORT -- the frozen duration bin SHORT (tau 1..4).
#   MATCHED_SPAN_TAU8_15 -- the previously defined matched temporal-span subset
#     used by the postmortem D6 visible-versus-hidden comparison
#     (d6_visible_positive_control.json :: matched_span_hidden_comparator,
#     tau_window [8, 15], 8 rows per trajectory).
DOMAINS: dict[str, dict[str, Any]] = {
    "FULL_EVIDENCE_BEARING_IN_CONTEXT": {"tau_min": 1, "tau_max": 15},
    "SHORT": {"tau_min": 1, "tau_max": 4},
    "MATCHED_SPAN_TAU8_15": {"tau_min": 8, "tau_max": 15},
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_obj(obj: Any) -> str:
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=_default)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _default(value: Any) -> Any:
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(repr(value))


def write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True, default=_default) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def run_git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=REPO, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def input_binding() -> dict:
    return json.loads((CONF / "analysis_input_binding.json").read_text())


def trajectory_ids() -> list[str]:
    return sorted(input_binding()["activation_provenance"].keys())


def s3_roots() -> dict[str, str]:
    """Per-trajectory S3 root, read from the bound activation provenance.

    t01-t03 sit under ...-first25-v2 and t04-t25 under ...-first25-v2-amendment-1,
    so roots are read from the binding rather than assumed uniform.
    """
    roots: dict[str, str] = {}
    for traj, artifacts in input_binding()["activation_provenance"].items():
        uri = next(a["s3_uri"] for a in artifacts if a["layer"] == 4)
        roots[traj] = uri.rsplit("/activations/", 1)[0]
    return roots


def ensure_capture_metadata() -> list[dict[str, Any]]:
    """Fetch + hash-verify the immutable per-frame capture metadata.

    Only ``coordinates.jsonl`` (world coordinates per model frame) and
    ``raw/visibility.jsonl`` (per-frame detector states) are read. Both are
    existing immutable capture artifacts. Every file is verified against
    ``durable_receipt.json``, which is itself verified against the P0-bound
    ``analysis_input_binding.json``. No activations are downloaded.
    """
    bound = {r["trajectory_id"]: r["sha256"] for r in input_binding()["durable_receipts"]}
    roots = s3_roots()
    records: list[dict[str, Any]] = []

    for traj in trajectory_ids():
        directory = META / traj
        directory.mkdir(parents=True, exist_ok=True)
        wanted = {
            "durable_receipt.json": "durable_receipt.json",
            "coordinates.jsonl": "coordinates.jsonl",
            "visibility.jsonl": "raw/visibility.jsonl",
        }
        for local, key in wanted.items():
            path = directory / local
            if not path.is_file():
                subprocess.run(
                    ["aws", "s3", "cp", f"{roots[traj]}/{key}", str(path), "--quiet"],
                    check=True,
                )

        receipt_path = directory / "durable_receipt.json"
        receipt_sha = sha256_file(receipt_path)
        if receipt_sha != bound[traj]:
            raise RuntimeError(
                f"durable receipt not bound by closed Regime A binding: {traj}"
            )
        receipt = json.loads(receipt_path.read_text())
        index = {
            o["key"].split(f"/{traj}/", 1)[1]: o
            for o in receipt["objects"] if f"/{traj}/" in o["key"]
        }
        for local, key in (("coordinates.jsonl", "coordinates.jsonl"),
                           ("visibility.jsonl", "raw/visibility.jsonl")):
            digest = sha256_file(directory / local)
            expected = index[key]["local_sha256"]
            if digest != expected:
                raise RuntimeError(f"capture metadata hash mismatch: {traj}/{local}")
            records.append({
                "trajectory_id": traj,
                "s3_uri": f"{roots[traj]}/{key}",
                "local_path": str(directory / local),
                "sha256": digest,
                "bound_by": "durable_receipt.json -> analysis_input_binding.json",
                "role": (
                    "per-frame world coordinates" if local == "coordinates.jsonl"
                    else "per-frame detector visibility states"
                ),
                "provenance_tier": "CLOSED_REGIME_A_IMMUTABLE_CAPTURE",
                "modified_by_p1": False,
            })
        records.append({
            "trajectory_id": traj,
            "s3_uri": f"{roots[traj]}/durable_receipt.json",
            "local_path": str(receipt_path),
            "sha256": receipt_sha,
            "bound_by": "analysis_input_binding.json :: durable_receipts",
            "role": "capture object hash authority",
            "provenance_tier": "CLOSED_REGIME_A_IMMUTABLE_CAPTURE",
            "modified_by_p1": False,
        })
    return records


def build_rows() -> pd.DataFrame:
    """Frozen held-out rows joined to causal last-evidence baselines.

    The frozen predictions are REUSED verbatim from the closed Regime A package.
    Nothing is refit. The only new columns are causal baselines derived from
    immutable capture metadata.

    Causality: for a target frame T the model input window is [T-15, T]. The
    baseline frame is the LATEST frame in that window carrying the relevant
    evidence. All 475 frozen targets are OCCLUDED_AGREEMENT with no rendered
    pixels at T itself, so the selected frame is always strictly prior to T.
    No frame after T is ever consulted.
    """
    preds = pd.read_parquet(CONF / "slice_predictions.parquet")
    rows: list[dict[str, Any]] = []

    for traj in trajectory_ids():
        coords = {
            int(r["model_frame_idx"]): r
            for r in read_jsonl(META / traj / "coordinates.jsonl")
        }
        vis = {
            int(r["model_frame_idx"]): r
            for r in read_jsonl(META / traj / "visibility.jsonl")
        }
        frame = preds[preds["trajectory_id"] == traj]
        for record in frame.to_dict("records"):
            target = int(record["model_frame_idx"])
            window = list(range(target - EFFECTIVE_PRECEDING, target + 1))
            evidence = [f for f in window
                        if f in vis and vis[f]["magenta_status"] == "detected"]
            clean = [f for f in window
                     if f in vis and vis[f]["visibility_class"] == "VISIBLE_AGREEMENT"]

            if vis[target]["visibility_class"] != "OCCLUDED_AGREEMENT":
                raise RuntimeError(f"frozen target row is not occluded: {traj}/{target}")
            if vis[target]["magenta_status"] == "detected":
                raise RuntimeError(f"rendered pixels at target frame: {traj}/{target}")

            out = dict(record)
            out["context_first_frame"] = window[0]
            out["context_last_frame"] = window[-1]
            out["n_rendered_pixel_evidence"] = len(evidence)
            out["n_clean_visible"] = len(clean)
            out["any_rendered_pixel_evidence"] = bool(evidence)
            out["any_clean_visible"] = bool(clean)
            out["last_rendered_evidence_frame"] = evidence[-1] if evidence else np.nan
            out["frames_since_last_rendered_evidence"] = (
                target - evidence[-1] if evidence else np.nan
            )
            out["last_rendered_evidence_position"] = (
                float(coords[evidence[-1]]["world_x"]) if evidence else np.nan
            )
            out["last_clean_visible_frame"] = clean[-1] if clean else np.nan
            out["frames_since_last_clean_visible"] = (
                target - clean[-1] if clean else np.nan
            )
            out["last_clean_visible_position"] = (
                float(coords[clean[-1]]["world_x"]) if clean else np.nan
            )
            rows.append(out)

    table = pd.DataFrame(rows).sort_values(["trajectory_id", "tau"]).reset_index(drop=True)
    table["displacement_from_last_rendered_evidence"] = (
        table["world_x"] - table["last_rendered_evidence_position"]
    )
    return table


def domain_frame(table: pd.DataFrame, name: str) -> pd.DataFrame:
    spec = DOMAINS[name]
    mask = (
        (table["tau"] >= spec["tau_min"])
        & (table["tau"] <= spec["tau_max"])
        & table["any_rendered_pixel_evidence"]
    )
    return table[mask].copy()


def _corr(a: np.ndarray, b: np.ndarray) -> float | None:
    if len(a) < 2 or np.std(a) == 0 or np.std(b) == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def error_stats(target: np.ndarray, prediction: np.ndarray) -> dict[str, Any]:
    residual = prediction - target
    return {
        "rmse_blocks": float(np.sqrt(np.mean(residual ** 2))),
        "mae_blocks": float(np.mean(np.abs(residual))),
        "signed_bias_blocks": float(np.mean(residual)),
        "correlation": _corr(target, prediction),
    }


def target_stats(target: np.ndarray) -> dict[str, float]:
    return {
        "target_min": float(target.min()),
        "target_max": float(target.max()),
        "target_range": float(target.max() - target.min()),
        "target_sd": float(target.std(ddof=0)),
    }


def r2_secondary(target: np.ndarray, prediction: np.ndarray) -> float | None:
    tss = float(((target - target.mean()) ** 2).sum())
    if tss <= 0:
        return None
    return float(1.0 - ((target - prediction) ** 2).sum() / tss)


def trajectory_bootstrap(
    values: dict[str, float],
    seed: int = BOOTSTRAP_SEED,
    resamples: int = BOOTSTRAP_RESAMPLES,
) -> dict[str, Any]:
    """Deterministic whole-trajectory paired bootstrap of the mean.

    Trajectories are the independent unit. Complete trajectories are resampled
    with replacement; frames are never resampled independently. Exploratory
    interval only -- it is not a confirmatory threshold and defines no gate.
    """
    keys = sorted(values)
    array = np.asarray([values[k] for k in keys], dtype=np.float64)
    rng = np.random.default_rng(seed)
    index = rng.integers(0, len(array), size=(resamples, len(array)))
    means = array[index].mean(axis=1)
    return {
        "statistic": "equal_trajectory_mean",
        "n_units_resampled": int(len(array)),
        "resampling_unit": "WHOLE_TRAJECTORY",
        "frame_level_resampling": False,
        "resamples": int(resamples),
        "seed": int(seed),
        "point_estimate": float(array.mean()),
        "ci95_low": float(np.percentile(means, 2.5)),
        "ci95_high": float(np.percentile(means, 97.5)),
        "interpretation_status": "EXPLORATORY_NOT_A_CONFIRMATORY_THRESHOLD",
    }

"""Re-key the Person C -> Person E handoff onto the frozen layout contract.

Corrects the legacy zero-based mod ids (``layout_00``-``layout_05``) to the
frozen ``configs/scenes/layouts.yaml`` ids (``layout_01``-``layout_06``) per
``docs/decisions/person_c_layout_id_supersession_v0_1.md``.

Semantic join keys are corrected; historical provenance (trajectory ids,
capture commands, real on-disk artifact paths) is preserved verbatim, so a
reader can always see what was actually executed.

Run once. Re-running on an already-migrated handoff exits without touching
anything: a second +1 shift would silently corrupt correct ids, so the
already-migrated state is detected and refused rather than reapplied.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HANDOFF = REPO / "data" / "handoff_e"
LAYOUTS = REPO / "configs" / "scenes" / "layouts.yaml"
DECISION = "docs/decisions/person_c_layout_id_supersession_v0_1.md"

# legacy -> frozen contract
MAPPING = {f"layout_{i:02d}": f"layout_{i + 1:02d}" for i in range(6)}

# Fields whose value is a semantic key that must resolve against the frozen
# contract. Everything not listed here is left byte-identical.
CORRECT_KEYS = {
    "layout_id",
    "canonical_camera_pose_id",
    "marker_set_id",
    "frame_id",
    "png_path",
}

CORRECTION_NOTE = {
    "applied": "legacy mod ids layout_00-layout_05 -> frozen contract layout_01-layout_06",
    "decision_record": DECISION,
    "corrected_fields": sorted(CORRECT_KEYS),
    "preserved_verbatim": [
        "trajectory_id", "source_trajectory_id", "source_artifact_id",
        "episode_id", "capture_command", "capture_package",
        "capture_provenance", "seed", "start_utc", "end_utc", "git_sha",
        "capturing_jar_sha256",
    ],
    "preserved_rationale": (
        "These record what was actually captured and executed against the "
        "prototype mod, and name real on-disk artifacts. Rewriting them "
        "would falsify provenance."
    ),
}


def remap(text: str) -> str:
    """Apply the legacy->frozen mapping to every layout token in ``text``."""
    return re.sub(r"layout_0[0-5]", lambda m: MAPPING[m.group(0)], text)


def pose_ids_from_contract() -> dict[str, str]:
    layouts = json.loads(LAYOUTS.read_text())["layouts"]
    return {l["layout_id"]: l["canonical_pose"]["pose_id"] for l in layouts}


def transform(node, poses: dict[str, str]):
    """Recursively correct only the whitelisted semantic keys."""
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if key in CORRECT_KEYS and isinstance(value, str):
                value = remap(value)
                # Reconcile pose ids with the contract's exact _v1 spelling.
                if key == "canonical_camera_pose_id":
                    layout = value.split("_canonical")[0]
                    value = poses.get(layout, value)
            else:
                value = transform(value, poses)
            out[key] = value
        return out
    if isinstance(node, list):
        return [transform(v, poses) for v in node]
    return node


def add_legacy_id(node):
    """Record the pre-correction id next to every corrected ``layout_id``."""
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            out[key] = add_legacy_id(value)
            if key == "layout_id" and isinstance(value, str):
                legacy = {v: k for k, v in MAPPING.items()}.get(value)
                if legacy:
                    out["legacy_layout_id"] = legacy
        return out
    if isinstance(node, list):
        return [add_legacy_id(v) for v in node]
    return node


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=1) + "\n")


def main() -> None:
    # Already migrated? A second run would shift correct ids to layout_07+.
    if not (HANDOFF / "markers_layout_00.json").exists() and \
            (HANDOFF / "markers_layout_06.json").exists():
        print("handoff already migrated (markers_layout_01..06 present); nothing to do")
        return

    poses = pose_ids_from_contract()
    changed: list[str] = []

    # 1. Rename calibration frame directories, descending so ids never collide.
    for legacy in sorted(MAPPING, reverse=True):
        for kind in ("visible", "negative"):
            src = HANDOFF / "calibration_frames" / kind / legacy
            dst = HANDOFF / "calibration_frames" / kind / MAPPING[legacy]
            if src.is_dir():
                if dst.exists():
                    raise SystemExit(f"refusing to overwrite existing {dst}")
                src.rename(dst)
                changed.append(f"dir {src.relative_to(REPO)} -> {dst.name}")

    # 2. Marker files: rename descending, correct keys, stamp the note.
    for legacy in sorted(MAPPING, reverse=True):
        src = HANDOFF / f"markers_{legacy}.json"
        dst = HANDOFF / f"markers_{MAPPING[legacy]}.json"
        if not src.exists():
            continue
        if dst.exists():
            raise SystemExit(f"refusing to overwrite existing {dst}")
        data = add_legacy_id(transform(json.loads(src.read_text()), poses))
        data["layout_id_correction"] = CORRECTION_NOTE
        write_json(dst, data)
        src.unlink()
        changed.append(f"{src.name} -> {dst.name}")

    # 3. Remaining handoff artifacts.
    for name in ("detector_calibration_inputs.json",
                 "independent_probe_points.json",
                 "provenance_calibration_clean.json",
                 "provenance_pilots_clean.json"):
        path = HANDOFF / name
        if not path.exists():
            continue
        data = add_legacy_id(transform(json.loads(path.read_text()), poses))
        data["layout_id_correction"] = CORRECTION_NOTE
        write_json(path, data)
        changed.append(name)

    # 4. Recompute marker_set_source_hash from the corrected marker files.
    cal = HANDOFF / "detector_calibration_inputs.json"
    if cal.exists():
        data = json.loads(cal.read_text())
        for entry in data.get("layouts", []):
            marker_file = HANDOFF / f"markers_{entry['layout_id']}.json"
            digest = hashlib.sha256(marker_file.read_bytes()).hexdigest()
            entry["marker_set_source_hash"] = digest
        write_json(cal, data)
        changed.append("detector_calibration_inputs.json: marker hashes recomputed")

    print(f"migrated {len(changed)} items")
    for item in changed:
        print("  ", item)


if __name__ == "__main__":
    main()

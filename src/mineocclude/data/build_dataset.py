"""Build the MineOcclude dataset from raw captures (Person C, C4.6/C4.8).

For each episode: strict-join -> visibility -> action normalization -> QA,
writing

  <out>/<trajectory_id>/frame_map.parquet          (C4.6 authoritative crosswalk)
  <out>/<trajectory_id>/mineworld_actions.jsonl
  <out>/<trajectory_id>/qa_report_<episode>.json   (C4.8 immutable QA result)

and aggregating an accepted manifest (trajectories_mvp.parquet) plus an
accepted/excluded ledger. Invalid episodes are recorded with reasons and left
OUT of the manifest — never repaired.

The frame map's unique key is the strict capture key; deterministic row order
(by ``server_tick``) is written for readability, but keys — not order —
define identity.

Usage:
  python -m mineocclude.data.build_dataset --out <dir> \
      --episode <server_dir> <client_dir> [--episode ...]
"""
from __future__ import annotations

import argparse
import json
import os

import pandas as pd

from mineocclude.data.align import align_episode
from mineocclude.data.convert_mineworld import write_mineworld_actions
from mineocclude.data.impulse import check_impulse, check_step_impulse
from mineocclude.data.preprocess import encode_canonical_mp4, normalize_episode
from mineocclude.data.qa_report import build_episode_report, write_report
from mineocclude.data.visibility import (
    add_interim_empirical_visibility,
    finalize_visibility,
    visibility_events,
)


def process_episode(server_dir: str, client_dir: str, out_root: str,
                    run_empirical: bool = True,
                    canonical_640: bool = True) -> dict:
    """Process one episode. Returns a summary dict (accepted flag + stats)."""
    frame_map, report = align_episode(server_dir, client_dir)
    summary = {
        "server_dir": server_dir, "client_dir": client_dir,
        "accepted": report.accepted,
        "n_frame": report.n_frame,
        "n_frames": report.n_frame,
        "problems": list(report.problems),
    }
    if not report.accepted or frame_map is None:
        return summary

    # Server-logged geometric channel; empirical channel from the interim
    # detector until E's frozen detector rows are supplied for these frames.
    if run_empirical:
        frame_map = add_interim_empirical_visibility(frame_map)
    else:
        frame_map = frame_map.copy()
        frame_map["empirical_visible"] = frame_map["geometric_visible"]
    frame_map = finalize_visibility(frame_map)
    events = visibility_events(list(frame_map["visible_flag"]))

    # QA gate: a sheep-bearing scene MUST actually show the sheep (visible
    # then hidden). If the magenta sheep was never detected, the trajectory
    # is invalid (e.g. the sheep failed to render) — reject for recollection.
    scene = str(frame_map["scene"].iloc[0]) if "scene" in frame_map.columns else "NORMAL"
    n_visible = int(frame_map["visible_flag"].sum())
    if scene != "NO_SHEEP" and n_visible == 0:
        summary["accepted"] = False
        summary["problems"] = [
            "no visible sheep frames: the sheep was never seen (recollect)"
        ]
        return summary

    # Reveal gate: an episode planned WITH a post-reveal window must contain
    # an empirical reveal (a hidden interval that ends). A geometric reveal
    # that the pixels never confirm (e.g. modeled-vs-built wall mismatch)
    # must reject the episode, not silently pass.
    reveal_ticks_planned = 0
    reset_result_path_early = os.path.join(server_dir, "reset_result.json")
    if os.path.isfile(reset_result_path_early):
        try:
            with open(reset_result_path_early, encoding="utf-8") as handle:
                reveal_ticks_planned = int(
                    json.load(handle).get("reveal_ticks", 0)
                )
        except (ValueError, OSError):
            reveal_ticks_planned = 0
    if reveal_ticks_planned > 0:
        has_reveal = any(
            event["reveal_idx"] is not None for event in events["events"]
        )
        if not has_reveal:
            summary["accepted"] = False
            summary["problems"] = [
                f"planned reveal window ({reveal_ticks_planned} ticks) "
                "captured no empirical reveal (missing_reveal)"
            ]
            return summary

    # Canonical 640x360 source frames (16:9), independent of the client window.
    if canonical_640:
        frame_map = normalize_episode(frame_map)

    # Impulse evidence: a scripted-impulse episode (declared in the server's
    # reset_result.json) is gated by the pixel-level step check; ordinary
    # episodes get the yaw-correlation diagnostic, whose abstention on a
    # still trajectory is not a failure.
    impulse = None
    reset_result_path = os.path.join(server_dir, "reset_result.json")
    impulse_tick = -1
    if os.path.isfile(reset_result_path):
        try:
            with open(reset_result_path, encoding="utf-8") as handle:
                impulse_tick = int(json.load(handle).get("impulse_tick", -1))
        except (ValueError, OSError):
            impulse_tick = -1
    if impulse_tick >= 0:
        impulse = check_step_impulse(frame_map, impulse_tick)
    elif "player_yaw" in frame_map.columns and "camera_dx" in frame_map.columns:
        impulse = check_impulse(frame_map)

    trajectory_id = str(frame_map["trajectory_id"].iloc[0])
    out_dir = os.path.join(out_root, trajectory_id)
    os.makedirs(out_dir, exist_ok=True)
    frame_map = frame_map.sort_values("server_tick").reset_index(drop=True)

    # C6A media gate: deterministic 20 fps 640x360 MP4, verified by ffprobe
    # in the QA report. Encoded only after the strict join and count checks
    # above; the canonical PNGs remain the preserved source evidence.
    media_path = None
    media_sha = None
    if canonical_640 and "frame_640_path" in frame_map.columns:
        media_path = os.path.join(out_dir, "video_640x360.mp4")
        try:
            media_sha = encode_canonical_mp4(frame_map, media_path)
        except Exception as error:  # encoding failure must reject, not pass
            summary["accepted"] = False
            summary["problems"] = [f"mp4 encode failed: {error}"]
            return summary

    frame_map.to_parquet(os.path.join(out_dir, "frame_map.parquet"), index=False)
    n_actions = write_mineworld_actions(
        frame_map, os.path.join(out_dir, "mineworld_actions.jsonl")
    )

    qa = build_episode_report(frame_map, report, events=events, impulse=impulse,
                              media_path=media_path)
    try:
        qa_path = write_report(qa, out_dir)
    except FileExistsError as error:
        summary["accepted"] = False
        summary["problems"] = [str(error)]
        return summary

    summary.update({
        "trajectory_id": trajectory_id,
        "episode_id": str(frame_map["episode_id"].iloc[0]),
        "layout_id": str(frame_map["layout_id"].iloc[0]),
        "seed": int(frame_map["seed"].iloc[0]),
        "v": float(frame_map["v"].iloc[0]),
        "q": float(frame_map["q"].iloc[0]),
        "n_frames": int(len(frame_map)),
        "n_visible": int(frame_map["visible_flag"].sum()),
        "n_hidden": int((~frame_map["visible_flag"].astype(bool)).sum()),
        "n_quarantine": int(frame_map["visibility_quarantine"].sum()),
        "n_onsets": len([e for e in events["events"]]),
        "n_offsets": len([e for e in events["events"] if e["reveal_idx"] is not None]),
        "n_actions": n_actions,
        "impulse_passed": None if impulse is None else bool(impulse["passed"]),
        "impulse_offset": None if impulse is None else impulse.get("offset"),
        "frame_map": os.path.join(out_dir, "frame_map.parquet"),
        "media": media_path,
        "media_sha256": media_sha,
        "qa_report": qa_path,
        "accepted": qa.accepted,
    })
    if not qa.accepted:
        summary["problems"] = [
            f"{check['name']}: {check['detail'] or check['measured']}"
            for check in qa.to_mapping()["checks"]
            if check["status"] == "fail"
        ]
    return summary


def build_dataset(episodes: list[tuple[str, str]], out_root: str,
                  run_empirical: bool = True) -> dict:
    os.makedirs(out_root, exist_ok=True)
    accepted, excluded = [], []
    for server_dir, client_dir in episodes:
        summary = process_episode(server_dir, client_dir, out_root, run_empirical)
        (accepted if summary["accepted"] else excluded).append(summary)

    if accepted:
        columns = ["trajectory_id", "episode_id", "layout_id", "seed", "v", "q",
                   "n_frames", "n_visible", "n_hidden", "n_quarantine",
                   "n_onsets", "n_offsets", "frame_map"]
        manifest = pd.DataFrame(accepted)[columns]
        manifest.to_parquet(
            os.path.join(out_root, "trajectories_mvp.parquet"), index=False
        )

    ledger = {"accepted": accepted, "excluded": excluded,
              "n_accepted": len(accepted), "n_excluded": len(excluded)}
    with open(os.path.join(out_root, "ledger.json"), "w", encoding="utf-8") as f:
        json.dump(ledger, f, indent=2)
    return ledger


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--episode", nargs=2, action="append",
                        metavar=("SERVER_DIR", "CLIENT_DIR"), required=True,
                        help="server_dir client_dir (repeatable)")
    parser.add_argument("--no-empirical", action="store_true",
                        help="skip the magenta detector (geometric only)")
    args = parser.parse_args()

    ledger = build_dataset([tuple(e) for e in args.episode], args.out,
                           run_empirical=not args.no_empirical)
    print(f"accepted={ledger['n_accepted']} excluded={ledger['n_excluded']}")
    for entry in ledger["excluded"]:
        print(f"  EXCLUDED {entry['server_dir']}: {entry['problems']}")
    return 0 if ledger["n_excluded"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

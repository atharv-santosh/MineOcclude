"""Immutable per-episode QA result (Person C, C4.8).

Runs every structural, media, conversion, and identity check for one episode
and stores each as pass/fail/not-applicable with measured and expected
values, so acceptance is reproducible from saved evidence rather than
remembered from a console screen.

A report is written once, hashed, and never edited into success; a
corrected/recollected episode creates a new report under a new episode
identity.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import asdict, dataclass, field
from typing import Any

QA_VALIDATOR_VERSION = "person-c-qa-v0.1"

PASS = "pass"
FAIL = "fail"
NOT_APPLICABLE = "not_applicable"


@dataclass
class QACheck:
    name: str
    status: str
    measured: Any = None
    expected: Any = None
    detail: str = ""


@dataclass
class QAReport:
    episode_id: str
    trajectory_id: str
    validator_version: str = QA_VALIDATOR_VERSION
    checks: list[QACheck] = field(default_factory=list)

    def add(self, name: str, ok: bool, measured=None, expected=None,
            detail: str = "") -> None:
        self.checks.append(
            QACheck(name, PASS if ok else FAIL, measured, expected, detail)
        )

    def add_na(self, name: str, detail: str = "") -> None:
        self.checks.append(QACheck(name, NOT_APPLICABLE, detail=detail))

    @property
    def accepted(self) -> bool:
        return all(check.status != FAIL for check in self.checks)

    def to_mapping(self) -> dict:
        return {
            "episode_id": self.episode_id,
            "trajectory_id": self.trajectory_id,
            "validator_version": self.validator_version,
            "accepted": self.accepted,
            "status": "accepted" if self.accepted else "excluded",
            "checks": [asdict(check) for check in self.checks],
        }


def ffprobe_media(path: str) -> dict | None:
    """Read width/height/rate/frame count from a media file via ffprobe.

    Returns ``None`` when ffprobe is unavailable or the file is unreadable —
    the caller records that as a failed media check, never a silent pass.
    """
    try:
        raw = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries",
                "stream=width,height,avg_frame_rate,nb_frames",
                "-of", "json", path,
            ],
            capture_output=True, text=True, timeout=60, check=True,
        ).stdout
        stream = json.loads(raw)["streams"][0]
        return {
            "width": int(stream["width"]),
            "height": int(stream["height"]),
            "avg_frame_rate": stream["avg_frame_rate"],
            "nb_frames": int(stream.get("nb_frames", -1)),
        }
    except (OSError, subprocess.SubprocessError, KeyError, ValueError,
            IndexError, json.JSONDecodeError):
        return None


def build_episode_report(
    frame_map,
    align_report,
    events: dict | None = None,
    impulse: dict | None = None,
    media_path: str | None = None,
    expected_frames: int | None = None,
) -> QAReport:
    """Assemble the QA report for one aligned episode.

    ``frame_map`` may be ``None`` for a rejected alignment; every downstream
    check is then recorded against the alignment failure instead of being
    silently skipped.
    """
    if frame_map is None or len(frame_map) == 0:
        report = QAReport(episode_id="unknown", trajectory_id="unknown")
        report.add(
            "alignment", False,
            measured=list(align_report.problems),
            expected="strict one-to-one join",
            detail="episode rejected before QA",
        )
        return report

    episode_id = str(frame_map["episode_id"].iloc[0])
    trajectory_id = str(frame_map["trajectory_id"].iloc[0])
    report = QAReport(episode_id=episode_id, trajectory_id=trajectory_id)

    report.add(
        "alignment", align_report.accepted,
        measured=list(align_report.problems),
        expected="strict one-to-one join",
    )
    counts = {
        "state": align_report.n_state,
        "action": align_report.n_action,
        "tick": align_report.n_tick,
        "frame": align_report.n_frame,
    }
    report.add(
        "cardinality",
        len(set(counts.values())) == 1,
        measured=counts,
        expected="all channel counts equal",
    )
    if expected_frames is not None:
        report.add(
            "planned_frame_count",
            len(frame_map) == expected_frames,
            measured=len(frame_map),
            expected=expected_frames,
        )

    ticks = list(frame_map.sort_values("server_tick")["server_tick"])
    report.add(
        "consecutive_ticks",
        ticks == list(range(len(ticks))),
        measured=f"{len(ticks)} ticks",
        expected="consecutive from 0",
    )

    for column in ("render_frame_idx", "action_idx", "model_frame_idx"):
        values = list(frame_map.sort_values("server_tick")[column])
        report.add(
            f"monotonic_{column}",
            values == list(range(len(values))),
            expected="complete zero-based sequence ordered by server_tick",
        )

    if "visible_flag" in frame_map.columns:
        n_quarantine = int(frame_map["visibility_quarantine"].sum()) \
            if "visibility_quarantine" in frame_map.columns else 0
        report.add(
            "visibility_labels_present", True,
            measured={
                "visible": int(frame_map["visible_flag"].sum()),
                "hidden": int((~frame_map["visible_flag"].astype(bool)).sum()),
                "quarantined": n_quarantine,
            },
        )
    else:
        report.add_na("visibility_labels_present", "visibility not computed")

    if events is not None:
        report.add(
            "events_derived", True,
            measured={
                "n_events": events["n_events"],
                "multiple_events": events["multiple_events"],
                "missing_reveal": events["missing_reveal"],
                "rule_version": events["rule_version"],
            },
        )
    else:
        report.add_na("events_derived", "events not computed")

    if impulse is not None:
        abstained = any(
            "insufficient" in reason for reason in impulse.get("reasons", [])
        )
        if abstained:
            # A still trajectory (the standard MVP shape: fixed canonical
            # camera, no-op actions) carries no impulse signal. Abstention is
            # not misalignment; decisive orientation evidence comes from the
            # designated scripted-impulse fixture (C3.6/C4.7), not from every
            # episode.
            report.add_na(
                "impulse_orientation",
                "no camera motion; orientation evidence comes from the "
                "designated impulse fixture",
            )
        else:
            measured_keys = (
                "best_lag", "residual_deg", "n_used",           # yaw diagnostic
                "action_idx", "effect_transition", "offset",    # pixel step check
                "action_step_deg", "effect_diff",
            )
            report.add(
                "impulse_orientation",
                bool(impulse.get("passed")),
                measured={k: impulse[k] for k in measured_keys if k in impulse},
                expected="the impulse effect lies exactly in visual_i -> visual_(i+1)",
                detail="; ".join(impulse.get("reasons", [])),
            )
    else:
        report.add_na("impulse_orientation", "no impulse evidence supplied")

    if media_path is not None:
        probe = ffprobe_media(media_path)
        ok = (
            probe is not None
            and probe["width"] == 640
            and probe["height"] == 360
            and probe["avg_frame_rate"] == "20/1"
            and (probe["nb_frames"] in (-1, len(frame_map)))
        )
        report.add(
            "media_ffprobe", ok,
            measured=probe,
            expected={"width": 640, "height": 360,
                      "avg_frame_rate": "20/1", "nb_frames": len(frame_map)},
        )
    else:
        report.add_na("media_ffprobe", "no encoded media for this episode")

    return report


def write_report(report: QAReport, out_dir: str) -> str:
    """Write the immutable report JSON plus its SHA-256 sidecar.

    Refuses to overwrite an existing report: a corrected episode gets a new
    identity and therefore a new report path.
    """
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"qa_report_{report.episode_id}.json")
    if os.path.exists(path):
        raise FileExistsError(
            f"QA report already exists: {path}; a corrected episode must use "
            "a new episode identity"
        )
    data = json.dumps(report.to_mapping(), indent=2, sort_keys=True).encode()
    with open(path, "wb") as handle:
        handle.write(data)
    digest = hashlib.sha256(data).hexdigest()
    with open(path + ".sha256", "w", encoding="utf-8") as handle:
        handle.write(digest + "\n")
    return path

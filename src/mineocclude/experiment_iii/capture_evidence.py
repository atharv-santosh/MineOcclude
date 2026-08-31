"""Physical capture evidence, read from the apparatus rather than restated.

The frozen ``capture_liveness_contract`` names seven ``required_evidence`` items.
Four of them -- tick identity, tick cardinality, framebuffer read success and
framebuffer dimensions -- are statements about what the *renderer physically did*.
They were previously satisfied by construction: the tick came from ``enumerate``,
the dimensions came from the ``FRAMEBUFFER_*`` constants and ``read_succeeded``
was the literal ``True``. Evidence produced by the consumer cannot disagree with
the consumer, so those checks could not fail on real data.

The apparatus already publishes all four. This module reads them:

``client_tick.jsonl``     one row per captured frame carrying the real
                          ``server_tick``, ``render_frame_idx``,
                          ``tick_queue_depth_at_capture`` and the ``frame_path``
                          that joins the row to the PNG on disk.
``capture_complete.json`` the episode drain receipt: ``frame_count``,
                          ``pending_writes``, ``writer_errors``, ``drained``.
``client_authority.json`` the client's own framebuffer size, FOV and HUD state.
the PNG headers           the dimensions the encoder actually wrote.

Everything here fails closed. A missing, malformed or contradictory evidence file
is a blocker, never a fallback to the requested configuration -- that fallback is
precisely the defect this module exists to remove.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any, Mapping, Sequence

from mineocclude.experiment_iii.authority import (
    FRAMEBUFFER_HEIGHT,
    FRAMEBUFFER_WIDTH,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError

__all__ = [
    "CAPTURE_COMPLETE_FILENAME",
    "CLIENT_AUTHORITY_FILENAME",
    "CLIENT_TICK_FILENAME",
    "MAX_TICK_QUEUE_DEPTH_AT_CAPTURE",
    "MAX_WRITER_ERRORS",
    "OBSERVED_PHYSICAL_EVIDENCE",
    "REQUESTED_CONFIGURATION",
    "evidence_binding_matrix",
    "join_frames_to_ticks",
    "png_dimensions",
    "read_capture_complete",
    "read_client_authority",
    "read_client_tick_ledger",
]

CLIENT_TICK_FILENAME = "client_tick.jsonl"
CAPTURE_COMPLETE_FILENAME = "capture_complete.json"
CLIENT_AUTHORITY_FILENAME = "client_authority.json"

#: The mod publishes ``writer_errors`` from ``FrameCapture``; a single failed PNG
#: write means a frame on disk may be absent or truncated, and P0 hashes bytes.
MAX_WRITER_ERRORS = 0

#: Under the lockstep gate the client consumes exactly one pending tick per
#: rendered frame, so the backlog at the moment of the framebuffer read is 0.
#: Any nonzero value is direct evidence that the world advanced past the state
#: the frame is joined to.
MAX_TICK_QUEUE_DEPTH_AT_CAPTURE = 0

#: Evidence items that are legitimately a restatement of what was asked for.
REQUESTED_CONFIGURATION = ("FRAME_HASH_RECORDED_AS_DIAGNOSTIC",)

#: Evidence items that must come from the apparatus, never from the request.
OBSERVED_PHYSICAL_EVIDENCE = (
    "SERVER_TICK_MONOTONIC_STEP_ONE",
    "ONE_ACCEPTED_FRAME_PER_EXPECTED_TICK",
    "TICK_IDENTITIES_COMPLETE_AND_UNIQUE",
    "CAPTURE_PROCESS_ALIVE",
    "FRAMEBUFFER_READ_SUCCEEDED",
    "FRAMEBUFFER_DIMENSIONS_640x360",
)

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


# --------------------------------------------------------------------------
# The written image is authoritative about its own dimensions
# --------------------------------------------------------------------------


def png_dimensions(path: Path) -> tuple[int, int]:
    """``(width, height)`` from the PNG's own IHDR chunk.

    Read from the bytes the encoder wrote, not from the size that was requested.
    A HiDPI or misconfigured surface yields a framebuffer larger than the
    requested one and ``FrameCapture`` warns rather than refuses, so the written
    header is the only place that discrepancy is observable.
    """
    path = Path(path)
    try:
        with path.open("rb") as handle:
            header = handle.read(24)
    except OSError as error:
        raise ExperimentIIIError(
            "CAPTURE_STALE_FRAME", f"frame {path} could not be read: {error}"
        ) from error
    if len(header) < 24 or header[:8] != _PNG_SIGNATURE:
        raise ExperimentIIIError(
            "CAPTURE_STALE_FRAME",
            f"frame {path} is not a PNG; the framebuffer read did not produce an "
            f"image",
        )
    if header[12:16] != b"IHDR":
        raise ExperimentIIIError(
            "CAPTURE_STALE_FRAME", f"frame {path} has no IHDR chunk"
        )
    width, height = struct.unpack(">II", header[16:24])
    return int(width), int(height)


# --------------------------------------------------------------------------
# client_tick.jsonl -- the real tick ledger
# --------------------------------------------------------------------------

_TICK_FIELDS = (
    "episode_id",
    "server_tick",
    "render_frame_idx",
    "tick_queue_depth_at_capture",
    "frame_path",
)


def read_client_tick_ledger(
    episode_dir: Path, *, episode_id: int | None = None
) -> list[dict[str, Any]]:
    """Parse and structurally validate the mod's per-episode tick ledger.

    This is the only artifact that binds a frame to the tick whose world state it
    photographed. Its rows are never synthesised: if the file is absent the unit
    has no tick identity and cannot be scientific evidence.
    """
    path = Path(episode_dir) / CLIENT_TICK_FILENAME
    if not path.is_file():
        raise ExperimentIIIError(
            "TIMING_CARDINALITY_MISMATCH",
            f"the capture produced no tick ledger at {path}; tick identity cannot "
            f"be reconstructed from frame order and must not be",
        )
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ExperimentIIIError(
                "TIMING_CARDINALITY_MISMATCH",
                f"{path}:{number} is not valid JSON: {error}",
            ) from error
        if not isinstance(row, Mapping):
            raise ExperimentIIIError(
                "TIMING_CARDINALITY_MISMATCH", f"{path}:{number} is not a tick object"
            )
        row = dict(row)
        missing = [key for key in _TICK_FIELDS if key not in row]
        if missing:
            raise ExperimentIIIError(
                "TIMING_CARDINALITY_MISMATCH",
                f"{path}:{number} is missing required tick fields {missing}",
            )
        try:
            row["episode_id"] = int(row["episode_id"])
            row["server_tick"] = int(row["server_tick"])
            row["render_frame_idx"] = int(row["render_frame_idx"])
            row["tick_queue_depth_at_capture"] = int(
                row["tick_queue_depth_at_capture"]
            )
        except (TypeError, ValueError) as error:
            raise ExperimentIIIError(
                "TIMING_CARDINALITY_MISMATCH",
                f"{path}:{number} carries a non-integer tick identity: {error}",
            ) from error
        row["frame_path"] = str(row["frame_path"]).replace("\\", "/")
        rows.append(row)
    if not rows:
        raise ExperimentIIIError(
            "TIMING_CARDINALITY_MISMATCH", f"{path} recorded no ticks"
        )
    if episode_id is not None:
        wrong = sorted({row["episode_id"] for row in rows} - {int(episode_id)})
        if wrong:
            raise ExperimentIIIError(
                "TIMING_CARDINALITY_MISMATCH",
                f"{path} carries rows for episodes {wrong}, not {episode_id}; the "
                f"ledger is bound to the wrong capture unit",
            )
    return rows


# --------------------------------------------------------------------------
# capture_complete.json -- the drain receipt
# --------------------------------------------------------------------------

_COMPLETE_FIELDS = (
    "episode_id",
    "frame_count",
    "pending_writes",
    "writer_errors",
    "drained",
)


def read_capture_complete(
    episode_dir: Path,
    *,
    episode_id: int | None = None,
    expected_frames: int | None = None,
) -> dict[str, Any]:
    """Parse the mod's drain receipt and fail closed on an incomplete capture.

    The mod encodes and writes PNGs on a background IO thread. A file exists at
    ``open``, not at completion, so waiting on a file *count* can hash a
    truncated image. ``drained`` is the apparatus telling us the queue emptied;
    ``writer_errors`` is it telling us a write failed. Neither can be inferred
    from the fact that the expected number of paths exist.
    """
    path = Path(episode_dir) / CAPTURE_COMPLETE_FILENAME
    if not path.is_file():
        raise ExperimentIIIError(
            "CAPTURE_STALE_FRAME",
            f"the capture published no completion receipt at {path}; the frame "
            f"writer may still be draining",
        )
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ExperimentIIIError(
            "CAPTURE_STALE_FRAME", f"{path} is malformed: {error}"
        ) from error
    if not isinstance(body, Mapping):
        raise ExperimentIIIError(
            "CAPTURE_STALE_FRAME", f"{path} is not a completion receipt object"
        )
    receipt = dict(body)
    missing = [key for key in _COMPLETE_FIELDS if key not in receipt]
    if missing:
        raise ExperimentIIIError(
            "CAPTURE_STALE_FRAME", f"{path} is missing completion fields {missing}"
        )
    if episode_id is not None and int(receipt["episode_id"]) != int(episode_id):
        raise ExperimentIIIError(
            "CAPTURE_STALE_FRAME",
            f"{path} reports episode {receipt['episode_id']}, not {episode_id}; the "
            f"completion receipt is bound to the wrong capture unit",
        )
    if not bool(receipt["drained"]):
        raise ExperimentIIIError(
            "CAPTURE_STALE_FRAME",
            f"episode {receipt['episode_id']} did not drain: "
            f"{receipt['pending_writes']} PNG writes were still pending when the "
            f"episode closed, so a frame on disk may be truncated",
        )
    if int(receipt["writer_errors"]) > MAX_WRITER_ERRORS:
        raise ExperimentIIIError(
            "CAPTURE_STALE_FRAME",
            f"episode {receipt['episode_id']} reported {receipt['writer_errors']} "
            f"frame-writer errors; at least one frame is absent or truncated",
        )
    if int(receipt["pending_writes"]) != 0:
        raise ExperimentIIIError(
            "CAPTURE_STALE_FRAME",
            f"episode {receipt['episode_id']} reports drained but still holds "
            f"{receipt['pending_writes']} pending writes",
        )
    if expected_frames is not None and int(receipt["frame_count"]) < int(
        expected_frames
    ):
        raise ExperimentIIIError(
            "TIMING_CARDINALITY_MISMATCH",
            f"episode {receipt['episode_id']} captured {receipt['frame_count']} "
            f"frames, expected at least {expected_frames}",
        )
    return receipt


def read_client_authority(episode_dir: Path) -> dict[str, Any]:
    """The client's own report of the framebuffer it rendered into."""
    path = Path(episode_dir) / CLIENT_AUTHORITY_FILENAME
    if not path.is_file():
        raise ExperimentIIIError(
            "ENV_FRAMEBUFFER_SIZE_MISMATCH",
            f"the client published no framebuffer authority at {path}",
        )
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ExperimentIIIError(
            "ENV_FRAMEBUFFER_SIZE_MISMATCH", f"{path} is malformed: {error}"
        ) from error
    width = int(body.get("framebuffer_width", -1))
    height = int(body.get("framebuffer_height", -1))
    if (width, height) != (FRAMEBUFFER_WIDTH, FRAMEBUFFER_HEIGHT):
        raise ExperimentIIIError(
            "ENV_FRAMEBUFFER_SIZE_MISMATCH",
            f"the client rendered into a {width}x{height} framebuffer, not "
            f"{FRAMEBUFFER_WIDTH}x{FRAMEBUFFER_HEIGHT}",
        )
    return dict(body)


# --------------------------------------------------------------------------
# The join
# --------------------------------------------------------------------------


def join_frames_to_ticks(
    frames: Sequence[Path],
    ledger: Sequence[Mapping[str, Any]],
    *,
    episode_dir: Path,
) -> list[dict[str, Any]]:
    """Join each PNG on disk to its ledger row on ``frame_path``.

    The join key is the mod's, not ours. A frame with no ledger row has no tick
    identity; a ledger row with no frame is a lost capture. Both are cardinality
    failures, and neither may be papered over by renumbering.
    """
    episode_dir = Path(episode_dir)
    by_path: dict[str, Mapping[str, Any]] = {}
    by_name: dict[str, Mapping[str, Any]] = {}
    for row in ledger:
        key = str(row["frame_path"]).replace("\\", "/")
        if key in by_path:
            raise ExperimentIIIError(
                "TIMING_CARDINALITY_MISMATCH",
                f"the tick ledger records {key} twice",
            )
        by_path[key] = row
        by_name.setdefault(key.rsplit("/", 1)[-1], row)

    joined: list[dict[str, Any]] = []
    seen: set[str] = set()
    for frame in frames:
        frame = Path(frame)
        try:
            key = frame.resolve().relative_to(episode_dir.resolve()).as_posix()
        except (ValueError, OSError):
            key = frame.name
        row = by_path.get(key) or by_name.get(frame.name)
        if row is None:
            raise ExperimentIIIError(
                "TIMING_CARDINALITY_MISMATCH",
                f"frame {key} has no row in {CLIENT_TICK_FILENAME}; it carries no "
                f"tick identity and cannot be used as evidence",
            )
        seen.add(str(row["frame_path"]).replace("\\", "/"))
        joined.append({"frame": frame, "tick_row": dict(row)})

    orphans = sorted(set(by_path) - seen)
    if orphans:
        raise ExperimentIIIError(
            "TIMING_CARDINALITY_MISMATCH",
            f"the tick ledger records {len(orphans)} frames that are not on disk, "
            f"first {orphans[:4]}",
        )
    return joined


def evidence_binding_matrix() -> list[dict[str, Any]]:
    """Which physical producer, file, parser and validator backs each item.

    Emitted into the liveness receipt so an independent reader can confirm that
    no ``required_evidence`` item is satisfied by restating the request.
    """
    return [
        {
            "evidence_id": "SERVER_TICK_MONOTONIC_STEP_ONE",
            "class": "OBSERVED_PHYSICAL_EVIDENCE",
            "physical_producer": (
                "ClientLogger.writeTick (server_tick from the lockstep PendingTick)"
            ),
            "artifact": CLIENT_TICK_FILENAME,
            "python_parser": "capture_evidence.read_client_tick_ledger",
            "validator": "capture_liveness.verify_tick_integrity",
            "runtime_call_site": "capture_driver.FrameSink.frame_records",
        },
        {
            "evidence_id": "ONE_ACCEPTED_FRAME_PER_EXPECTED_TICK",
            "class": "OBSERVED_PHYSICAL_EVIDENCE",
            "physical_producer": (
                "MineOccludeClient.captureOne (one pending tick per rendered frame)"
            ),
            "artifact": f"{CLIENT_TICK_FILENAME} joined to the PNGs on disk",
            "python_parser": "capture_evidence.join_frames_to_ticks",
            "validator": "capture_liveness.verify_tick_integrity(expected=...)",
            "runtime_call_site": "capture_driver.FrameSink.frame_records",
        },
        {
            "evidence_id": "TICK_IDENTITIES_COMPLETE_AND_UNIQUE",
            "class": "OBSERVED_PHYSICAL_EVIDENCE",
            "physical_producer": "ClientLogger.writeTick",
            "artifact": CLIENT_TICK_FILENAME,
            "python_parser": "capture_evidence.read_client_tick_ledger",
            "validator": "capture_liveness.verify_tick_integrity",
            "runtime_call_site": "capture_driver.FrameSink.frame_records",
        },
        {
            "evidence_id": "CAPTURE_PROCESS_ALIVE",
            "class": "OBSERVED_PHYSICAL_EVIDENCE",
            "physical_producer": "the server/client JVM processes",
            "artifact": "subprocess.poll()",
            "python_parser": "capture_runtime.CaptureRuntime.alive",
            "validator": "capture_liveness.verify_unit_liveness",
            "runtime_call_site": "capture_driver.capture_p0_unit",
        },
        {
            "evidence_id": "FRAMEBUFFER_READ_SUCCEEDED",
            "class": "OBSERVED_PHYSICAL_EVIDENCE",
            "physical_producer": "FrameCapture.writeErrors / awaitDrained",
            "artifact": CAPTURE_COMPLETE_FILENAME,
            "python_parser": "capture_evidence.read_capture_complete",
            "validator": "capture_liveness.verify_frame_dimensions (read_succeeded)",
            "runtime_call_site": "capture_driver.FrameSink.wait_for_frames",
        },
        {
            "evidence_id": "FRAMEBUFFER_DIMENSIONS_640x360",
            "class": "OBSERVED_PHYSICAL_EVIDENCE",
            "physical_producer": (
                "the PNG encoder, and MinecraftClient.getFramebuffer()"
            ),
            "artifact": f"the PNG IHDR chunks and {CLIENT_AUTHORITY_FILENAME}",
            "python_parser": "capture_evidence.png_dimensions / read_client_authority",
            "validator": "capture_liveness.verify_frame_dimensions",
            "runtime_call_site": "capture_driver.FrameSink.frame_records",
        },
        {
            "evidence_id": "FRAME_HASH_RECORDED_AS_DIAGNOSTIC",
            "class": "REQUESTED_CONFIGURATION",
            "physical_producer": "the PNG bytes on disk",
            "artifact": "the frame files",
            "python_parser": "capture_driver.FrameSink.frame_records",
            "validator": "diagnostic only; never a verdict (7.10f)",
            "runtime_call_site": "capture_driver.FrameSink.frame_records",
        },
    ]

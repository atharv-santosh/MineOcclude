"""Immutable Regime A noise schedules (Person C, phase C2.4 support).

The frozen RNG decision (`docs/decisions/person_c_rng_tick_lifecycle_v0_1.md`)
requires that the *Python capture-preparation step* is the only random-number
producer: a ``numpy.random.Generator`` over ``PCG64`` creates the complete
per-tick schedule before an episode starts, and the Java server verifies and
consumes the stored draws in increasing ``draw_idx`` order. The server never
recreates draws from a seed.

This module produces, serializes, hashes, and verifies that schedule. The
serialized bytes are canonical: the SHA-256 of ``serialize_schedule`` is the
``noise_schedule_hash`` recorded in the episode manifest. Verification never
repairs a schedule; any mismatch is a rejection.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from mineocclude.data.capture_contract import (
    TICK_INTERVAL_SECONDS,
)

SCHEDULE_FORMAT_VERSION = "person-c-noise-schedule-v0.1"
PRODUCER = "numpy.random.Generator"
BIT_GENERATOR = "PCG64"

#: Absolute tolerance for float comparisons between a stored schedule and an
#: independently recomputed or consumed copy. Draws are serialized with
#: ``repr`` round-trip fidelity, so equality should be exact; the tolerance
#: only absorbs decimal-text round trips by non-Python consumers.
CONSUMPTION_ABS_TOL = 1e-12


@dataclass(frozen=True)
class NoiseScheduleRow:
    """One immutable per-tick draw."""

    draw_idx: int
    standard_normal_draw: float
    q: float
    dt_seconds: float
    noise_std_blocks: float
    noise_draw: float

    def to_mapping(self, seed: int) -> dict[str, Any]:
        return {
            "seed": seed,
            "draw_idx": self.draw_idx,
            "standard_normal_draw": self.standard_normal_draw,
            "q": self.q,
            "dt_seconds": self.dt_seconds,
            "noise_std_blocks": self.noise_std_blocks,
            "noise_draw": self.noise_draw,
        }


@dataclass(frozen=True)
class NoiseSchedule:
    """A complete immutable episode schedule plus provenance."""

    seed: int
    q: float
    dt_seconds: float
    rows: tuple[NoiseScheduleRow, ...]
    numpy_version: str

    @property
    def n_draws(self) -> int:
        return len(self.rows)


def generate_noise_schedule(
    seed: int,
    n_draws: int,
    q: float,
    dt_seconds: float = TICK_INTERVAL_SECONDS,
) -> NoiseSchedule:
    """Create the complete schedule for one planned episode.

    ``q`` is a variance rate in blocks-squared/second; each per-tick draw has
    standard deviation ``sqrt(q * dt_seconds)`` blocks.
    """
    if n_draws <= 0:
        raise ValueError("n_draws must be a positive tick count.")
    if not math.isfinite(q) or q < 0:
        raise ValueError("q must be finite and non-negative.")
    if not math.isfinite(dt_seconds) or dt_seconds <= 0:
        raise ValueError("dt_seconds must be finite and positive.")

    generator = np.random.Generator(np.random.PCG64(seed))
    std = math.sqrt(q * dt_seconds)
    draws = generator.standard_normal(n_draws)
    rows = tuple(
        NoiseScheduleRow(
            draw_idx=index,
            standard_normal_draw=float(z),
            q=float(q),
            dt_seconds=float(dt_seconds),
            noise_std_blocks=std,
            noise_draw=float(z) * std,
        )
        for index, z in enumerate(draws)
    )
    return NoiseSchedule(
        seed=int(seed),
        q=float(q),
        dt_seconds=float(dt_seconds),
        rows=rows,
        numpy_version=np.__version__,
    )


def serialize_schedule(schedule: NoiseSchedule) -> bytes:
    """Canonical JSONL bytes: one header line, then one line per draw.

    Floats are serialized with ``repr`` round-trip fidelity so the exact
    binary values are recoverable. These exact bytes are what the hash and
    the Java-side verification cover.
    """
    header = {
        "schedule_format_version": SCHEDULE_FORMAT_VERSION,
        "producer": PRODUCER,
        "bit_generator": BIT_GENERATOR,
        "numpy_version": schedule.numpy_version,
        "seed": schedule.seed,
        "n_draws": schedule.n_draws,
        "q": schedule.q,
        "dt_seconds": schedule.dt_seconds,
    }
    lines = [json.dumps(header, sort_keys=True)]
    for row in schedule.rows:
        lines.append(json.dumps(row.to_mapping(schedule.seed), sort_keys=True))
    return ("\n".join(lines) + "\n").encode("utf-8")


def schedule_hash(schedule: NoiseSchedule) -> str:
    """SHA-256 of the canonical serialized bytes (the manifest hash)."""
    return hashlib.sha256(serialize_schedule(schedule)).hexdigest()


def write_schedule(schedule: NoiseSchedule, path: str) -> str:
    """Write the canonical bytes to ``path`` and return their SHA-256."""
    data = serialize_schedule(schedule)
    with open(path, "wb") as handle:
        handle.write(data)
    return hashlib.sha256(data).hexdigest()


def load_schedule(path: str) -> NoiseSchedule:
    """Load and structurally validate a serialized schedule.

    Raises ``ValueError`` with a specific reason on any structural defect.
    The file is never repaired.
    """
    with open(path, "rb") as handle:
        data = handle.read()
    lines = data.decode("utf-8").splitlines()
    if not lines:
        raise ValueError("noise schedule file is empty")
    header = json.loads(lines[0])
    for field in ("schedule_format_version", "producer", "bit_generator",
                  "numpy_version", "seed", "n_draws", "q", "dt_seconds"):
        if field not in header:
            raise ValueError(f"schedule header is missing {field}")
    if header["schedule_format_version"] != SCHEDULE_FORMAT_VERSION:
        raise ValueError(
            "unsupported schedule_format_version "
            f"{header['schedule_format_version']!r}"
        )
    if header["producer"] != PRODUCER or header["bit_generator"] != BIT_GENERATOR:
        raise ValueError("schedule producer/bit_generator violates the RNG decision")

    rows: list[NoiseScheduleRow] = []
    for index, line in enumerate(lines[1:]):
        record = json.loads(line)
        if record.get("seed") != header["seed"]:
            raise ValueError(f"row {index} seed does not match the header seed")
        if record.get("draw_idx") != index:
            raise ValueError(
                f"draw_idx must be consecutive from 0; row {index} has "
                f"{record.get('draw_idx')!r}"
            )
        rows.append(
            NoiseScheduleRow(
                draw_idx=record["draw_idx"],
                standard_normal_draw=record["standard_normal_draw"],
                q=record["q"],
                dt_seconds=record["dt_seconds"],
                noise_std_blocks=record["noise_std_blocks"],
                noise_draw=record["noise_draw"],
            )
        )
    if len(rows) != header["n_draws"]:
        raise ValueError(
            f"header declares {header['n_draws']} draws but the file has {len(rows)}"
        )

    schedule = NoiseSchedule(
        seed=int(header["seed"]),
        q=float(header["q"]),
        dt_seconds=float(header["dt_seconds"]),
        rows=tuple(rows),
        numpy_version=str(header["numpy_version"]),
    )
    problems = validate_schedule_invariants(schedule)
    if problems:
        raise ValueError("; ".join(problems))
    return schedule


def validate_schedule_invariants(schedule: NoiseSchedule) -> list[str]:
    """Check sqrt(q*dt) scaling and draw completeness. Returns problems."""
    problems: list[str] = []
    expected_std = math.sqrt(schedule.q * schedule.dt_seconds)
    for row in schedule.rows:
        if not math.isclose(row.q, schedule.q, rel_tol=0.0, abs_tol=1e-12):
            problems.append(f"draw {row.draw_idx}: q differs from the schedule q")
        if not math.isclose(
            row.dt_seconds, schedule.dt_seconds, rel_tol=0.0, abs_tol=1e-12
        ):
            problems.append(f"draw {row.draw_idx}: dt differs from the schedule dt")
        if not math.isclose(
            row.noise_std_blocks, expected_std, rel_tol=0.0, abs_tol=1e-12
        ):
            problems.append(
                f"draw {row.draw_idx}: noise_std_blocks violates sqrt(q*dt)"
            )
        if not math.isclose(
            row.noise_draw,
            row.standard_normal_draw * expected_std,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            problems.append(
                f"draw {row.draw_idx}: noise_draw != standard_normal_draw * std"
            )
    indices = [row.draw_idx for row in schedule.rows]
    if indices != list(range(len(indices))):
        problems.append("draw_idx sequence is not the complete zero-based schedule")
    return problems


def verify_consumption(
    schedule: NoiseSchedule,
    consumed: Sequence[Mapping[str, Any]],
) -> list[str]:
    """Verify a consumer's per-tick noise log against the immutable schedule.

    ``consumed`` rows need ``draw_idx`` and ``noise_draw`` (the exact value the
    consumer applied). Every schedule draw must be consumed exactly once, in
    order, byte-for-byte within ``CONSUMPTION_ABS_TOL``. Returns a list of
    problems; an empty list means the consumption matches.
    """
    problems: list[str] = []
    if len(consumed) != schedule.n_draws:
        problems.append(
            f"consumed {len(consumed)} draws but the schedule has {schedule.n_draws}"
        )
    for position, record in enumerate(consumed):
        if position >= schedule.n_draws:
            break
        expected = schedule.rows[position]
        if record.get("draw_idx") != expected.draw_idx:
            problems.append(
                f"position {position}: consumed draw_idx {record.get('draw_idx')!r} "
                f"but the schedule requires {expected.draw_idx} (order violation)"
            )
            continue
        value = record.get("noise_draw")
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            or not math.isclose(
                float(value),
                expected.noise_draw,
                rel_tol=0.0,
                abs_tol=CONSUMPTION_ABS_TOL,
            )
        ):
            problems.append(
                f"draw {expected.draw_idx}: consumed noise_draw {value!r} does not "
                f"match the immutable schedule value {expected.noise_draw!r}"
            )
    return problems

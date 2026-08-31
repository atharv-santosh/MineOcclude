"""The capture liveness contract (authority 7.10f, Amendment 3).

Authority v1.5 invalidated a block on "byte-identical consecutive frames beyond
the frozen tolerance". Amendment 3 **withdrew** that rule as unsound, and this
module implements the replacement.

Why the old rule was wrong, concretely:

* P0 deliberately captures a **static settled scene**. Fixed noon, weather
  controlled, zero random ticks, an AI-disabled target held at one placement --
  repeated framebuffer bytes are the *expected* observation.
* An opaque ``L4`` production condition can legitimately render pixel-identical
  frames while a fully hidden target moves behind the wall.

In both cases the correct observation was indistinguishable from a frozen
renderer, so the rule would have thrown away valid science while still failing to
detect the fault it was written for.

Liveness is therefore proven where it is actually observable:

* **tick integrity** -- the server tick advances by exactly one per step, and the
  accepted frames carry complete, unique tick identities;
* **transition probes** -- at points where the image *must* change (target
  present/absent, a wall material change, and a mandatory pre-capture probe) the
  settled framebuffer is required to differ.

``CAPTURE_STALE_FRAME`` is raised only when a tick advanced across a known scene
transition and the settled framebuffer did not change. Frame hashes are recorded
throughout as diagnostics and are never a verdict on their own.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from mineocclude.experiment_iii.authority import (
    FRAMEBUFFER_HEIGHT,
    FRAMEBUFFER_WIDTH,
    machine_authority,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError

__all__ = [
    "DIAGNOSTIC_TRANSITIONS",
    "GUARANTEED_CHANGE_TRANSITIONS",
    "TRANSITION_KINDS",
    "LivenessProbe",
    "assert_transition_observed",
    "liveness_contract",
    "OBSERVED_EVIDENCE_SOURCE",
    "verify_frame_dimensions",
    "verify_tick_integrity",
    "verify_unit_liveness",
]

#: Authority 7.10f -- every transition the contract knows about.
TRANSITION_KINDS = (
    "TARGET_PRESENT_TO_ABSENT",
    "TARGET_ABSENT_TO_PRESENT",
    "WALL_MATERIAL_CHANGE",
    "MANDATORY_PRE_CAPTURE_LIVENESS_WITNESS",
)

#: Amendment 4. Transitions whose framebuffer change the authority guarantees
#: INDEPENDENTLY of the scientific visibility condition being measured. Only these
#: may return a staleness verdict.
#:
#: * the witness runs NO_WALL at a fixed visible calibration position, so its
#:   change does not depend on any candidate material;
#: * a wall material change repaints a surface that is directly in view, so its
#:   change does not depend on whether the target is visible.
GUARANTEED_CHANGE_TRANSITIONS = (
    "MANDATORY_PRE_CAPTURE_LIVENESS_WITNESS",
    "WALL_MATERIAL_CHANGE",
)

#: Amendment 4. Recorded, never a verdict on their own. A correctly rendered
#: condition may occlude the target, so PRESENT and ABSENT legitimately produce
#: pixel-identical settled framebuffers; requiring inequality made liveness
#: conditional on the unknown visibility quantity P0 exists to measure.
DIAGNOSTIC_TRANSITIONS = (
    "TARGET_PRESENT_TO_ABSENT",
    "TARGET_ABSENT_TO_PRESENT",
)


def liveness_contract() -> dict[str, Any]:
    """The frozen contract, read from the authority rather than restated."""
    contract = machine_authority().get("capture_liveness_contract")
    if not contract:
        raise ExperimentIIIError(
            "AUTHORITY_INCOMPLETE",
            "the authority carries no capture_liveness_contract; Amendment 3 is absent",
        )
    return dict(contract)


class LivenessProbe:
    """One observed scene transition and the framebuffer hashes bracketing it."""

    def __init__(
        self,
        kind: str,
        *,
        before_hash: str,
        after_hash: str,
        before_tick: int,
        after_tick: int,
        before_episode: int | None = None,
        after_episode: int | None = None,
        before_sequence: int | None = None,
        after_sequence: int | None = None,
        settled: bool = True,
    ) -> None:
        if kind not in TRANSITION_KINDS:
            raise ExperimentIIIError(
                "CAPTURE_STALE_FRAME",
                f"{kind!r} is not a frozen transition kind {TRANSITION_KINDS}",
            )
        self.kind = kind
        self.before_hash = before_hash
        self.after_hash = after_hash
        self.before_tick = int(before_tick)
        self.after_tick = int(after_tick)
        self.before_episode = None if before_episode is None else int(before_episode)
        self.after_episode = None if after_episode is None else int(after_episode)
        self.before_sequence = None if before_sequence is None else int(before_sequence)
        self.after_sequence = None if after_sequence is None else int(after_sequence)
        self.settled = bool(settled)

    @property
    def tick_advanced(self) -> bool:
        """Did the world progress between the two settled observations?

        A transition is normally bracketed by two SEPARATE captures, and the mod
        restarts ``server_tick`` at 0 for each one -- its identity is the pair
        ``(episodeId, serverTick)``. Comparing the bare tick across captures
        therefore compared two unrelated counters: the mandatory probe read
        ``7 -> 7`` and every ABBA target transition read ``7 -> 0``, so a
        correctly captured transition was reported as a world that never
        advanced.

        The order of two separate captures is the order the driver captured them
        in, which is what the capture SEQUENCE records. It is deliberately NOT the
        episode id: ids are operator-assigned identities, and the P0 runner
        numbers the witness at ``slot_0 + 900_000``, so the witness that runs
        FIRST carries the LARGEST id. Ordering on the id called a correct
        wall-material transition a world that never advanced, on every unit that
        builds a wall. Within one capture it is exactly the tick comparison.
        """
        if (
            self.before_sequence is not None
            and self.after_sequence is not None
            and self.before_sequence != self.after_sequence
        ):
            return self.after_sequence > self.before_sequence
        if (
            self.before_episode is not None
            and self.after_episode is not None
            and self.before_episode != self.after_episode
        ):
            return self.after_episode > self.before_episode
        return self.after_tick > self.before_tick

    @property
    def framebuffer_changed(self) -> bool:
        return self.before_hash != self.after_hash

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "before_episode": self.before_episode,
            "after_episode": self.after_episode,
            "before_capture_sequence": self.before_sequence,
            "after_capture_sequence": self.after_sequence,
            "before_tick": self.before_tick,
            "after_tick": self.after_tick,
            "before_frame_sha256": self.before_hash,
            "after_frame_sha256": self.after_hash,
            "tick_advanced": self.tick_advanced,
            "framebuffer_changed": self.framebuffer_changed,
            "settled": self.settled,
        }


def assert_transition_observed(probe: LivenessProbe) -> dict[str, Any]:
    """Evaluate one transition under the Amendment 4 successor rule.

    A staleness verdict is available ONLY for a transition whose framebuffer
    change the authority guarantees independently of the scientific visibility
    condition being measured. For a scientific target present/absent transition
    the hashes are recorded and compared, but equality is technical evidence and
    diagnostics -- never, by itself, ``CAPTURE_STALE_FRAME``.

    The rule is uniform. Nothing here consults the wall material, its expected
    opacity, the candidate ranking, RVE, the selected ladder or model behaviour:
    liveness is decided by the witness, not by the measurement.
    """
    if not probe.tick_advanced:
        raise ExperimentIIIError(
            "TIMING_CARDINALITY_MISMATCH",
            f"the world did not advance across {probe.kind} "
            f"(episode {probe.before_episode} tick {probe.before_tick} -> "
            f"episode {probe.after_episode} tick {probe.after_tick})",
        )
    guaranteed = probe.kind in GUARANTEED_CHANGE_TRANSITIONS
    if guaranteed and not probe.framebuffer_changed:
        raise ExperimentIIIError(
            "CAPTURE_STALE_FRAME",
            f"the world advanced across {probe.kind}, whose framebuffer change is "
            f"guaranteed independently of the condition under measurement, but the "
            f"settled framebuffer is byte-identical ({probe.before_hash}); the "
            f"renderer is not presenting the scene",
        )
    report = probe.as_dict()
    report["change_guaranteed_by_authority"] = guaranteed
    report["verdict_bearing"] = guaranteed
    if not guaranteed:
        report["note"] = (
            "diagnostic only: equal settled hashes across a scientific "
            "present/absent transition are not evidence of a stale renderer"
        )
    return report


def verify_tick_integrity(ticks: Sequence[int], *, expected: int | None = None) -> dict[str, Any]:
    """Monotone step-one ticks, one accepted frame each, complete and unique."""
    values = [int(tick) for tick in ticks]
    if not values:
        raise ExperimentIIIError(
            "TIMING_CARDINALITY_MISMATCH", "a capture unit recorded no ticks"
        )
    if expected is not None and len(values) != int(expected):
        raise ExperimentIIIError(
            "TIMING_CARDINALITY_MISMATCH",
            f"expected {expected} accepted frames, got {len(values)}",
        )
    if len(set(values)) != len(values):
        duplicates = sorted({t for t in values if values.count(t) > 1})
        raise ExperimentIIIError(
            "TIMING_CARDINALITY_MISMATCH",
            f"duplicated tick identities: {duplicates[:8]}",
        )
    for previous, current in zip(values, values[1:]):
        if current != previous + 1:
            raise ExperimentIIIError(
                "TIMING_CARDINALITY_MISMATCH",
                f"ticks must advance by exactly one; {previous} -> {current}",
            )
    return {
        "accepted_frames": len(values),
        "first_tick": values[0],
        "last_tick": values[-1],
        "monotonic_step_one": True,
        "identities_unique": True,
        "identities_complete": True,
    }


def verify_capture_tick_integrity(
    frames: Sequence[Mapping[str, Any]], *, expected_total: int | None = None
) -> dict[str, Any]:
    """Tick integrity per CAPTURE, which is the scope the apparatus defines.

    ``server_tick`` is episode-relative: the mod restarts the counter at 0 for
    every capture, and its lockstep gate is keyed on the PAIR
    ``(episodeId, serverTick)`` -- ``EpisodeManager`` states outright that
    "(episodeId, serverTick) is complete". A capture unit is four independent
    captures, so those pairs are complete and unique across a unit.

    The previous implementation projected that identity onto the bare
    ``server_tick`` and then demanded one globally monotone step-one run across
    the whole unit. No real unit can satisfy that: slot 1 restarts at 0 while
    slot 0 already used it, so every unit failed with duplicated identities
    ``[0, 1, ... ]``. It passed only because every test fed it a single
    contiguous synthetic run and never the concatenation the driver actually
    builds. The frozen evidence -- monotone step-one ticks, one accepted frame
    per expected tick, complete and unique identities -- is unchanged; it is
    applied to the identity the apparatus emits rather than to half of it.
    """
    captures: dict[Any, list[int]] = {}
    for frame in frames:
        if "episode_id" not in frame:
            raise ExperimentIIIError(
                "TIMING_CARDINALITY_MISMATCH",
                "a frame record carries no episode_id, so its tick identity is "
                "only half of (episode_id, server_tick) and cannot be verified",
            )
        captures.setdefault(frame["episode_id"], []).append(int(frame["tick"]))
    if not captures:
        raise ExperimentIIIError(
            "TIMING_CARDINALITY_MISMATCH", "a capture unit recorded no ticks"
        )
    total = sum(len(ticks) for ticks in captures.values())
    if expected_total is not None and total != int(expected_total):
        raise ExperimentIIIError(
            "TIMING_CARDINALITY_MISMATCH",
            f"expected {expected_total} accepted frames across the unit, got {total}",
        )
    per_capture = {
        str(episode): verify_tick_integrity(ticks)
        for episode, ticks in captures.items()
    }
    return {
        "scope": "PER_CAPTURE_EPISODE",
        "tick_identity": "(episode_id, server_tick)",
        "captures": len(captures),
        "accepted_frames": total,
        "monotonic_step_one": True,
        "identities_unique": True,
        "identities_complete": True,
        "per_capture": per_capture,
    }


#: A frame record may only be scientific evidence if its tick and dimensions were
#: read from the apparatus. The previous implementation accepted records whose
#: ``tick`` came from ``enumerate`` and whose ``width``/``height`` came from the
#: FRAMEBUFFER_* constants, so ``verify_frame_dimensions`` compared the constants
#: against themselves and ENV_FRAMEBUFFER_SIZE_MISMATCH could never fire.
OBSERVED_EVIDENCE_SOURCE = "OBSERVED_PHYSICAL_EVIDENCE"


def verify_frame_dimensions(frames: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Every framebuffer read succeeded and is exactly 640 x 360."""
    count = 0
    for frame in frames:
        count += 1
        if frame.get("evidence_source") != OBSERVED_EVIDENCE_SOURCE:
            raise ExperimentIIIError(
                "CAPTURE_STALE_FRAME",
                f"the frame at tick {frame.get('tick')} is not marked "
                f"{OBSERVED_EVIDENCE_SOURCE}; framebuffer dimensions and tick "
                f"identity must be read from the apparatus (the PNG header and "
                f"client_tick.jsonl), never restated from the requested "
                f"configuration",
            )
        if not frame.get("read_succeeded", True):
            raise ExperimentIIIError(
                "CAPTURE_STALE_FRAME",
                f"framebuffer read failed at tick {frame.get('tick')}",
            )
        width, height = int(frame["width"]), int(frame["height"])
        if (width, height) != (FRAMEBUFFER_WIDTH, FRAMEBUFFER_HEIGHT):
            raise ExperimentIIIError(
                "ENV_FRAMEBUFFER_SIZE_MISMATCH",
                f"frame at tick {frame.get('tick')} is {width}x{height}, not "
                f"{FRAMEBUFFER_WIDTH}x{FRAMEBUFFER_HEIGHT}",
            )
    if count == 0:
        raise ExperimentIIIError(
            "TIMING_CARDINALITY_MISMATCH", "a capture unit recorded no frames"
        )
    return {"frames": count, "all_640x360": True, "all_reads_succeeded": True}


def verify_unit_liveness(
    *,
    frames: Sequence[Mapping[str, Any]],
    probes: Sequence[LivenessProbe],
    process_alive: bool,
    expected_frames: int | None = None,
    material_transition: bool = False,
) -> dict[str, Any]:
    """The whole 7.10f contract for one capture unit.

    Repeated frame hashes inside the unit are reported as a diagnostic and are
    deliberately **not** a failure: within one settled static state that is the
    expected observation.
    """
    if not process_alive:
        raise ExperimentIIIError(
            "CAPTURE_STALE_FRAME",
            "the capture process did not stay alive for the whole unit",
        )
    # Order matters. ``verify_frame_dimensions`` is the gate that asks whether
    # these records are observed physical evidence at all; a record fabricated
    # from the requested configuration must be refused as CAPTURE_STALE_FRAME by
    # that gate, not incidentally by a later structural check that happens to
    # notice the same record is also missing its episode.
    dimension_report = verify_frame_dimensions(frames)
    tick_report = verify_capture_tick_integrity(frames, expected_total=expected_frames)

    # Amendment 4: the unit's liveness is discharged by the WITNESS, which the
    # authority requires before every scientific capture unit. The scientific
    # target transitions are recorded but are not required to be present or to
    # change, because a condition that occludes the target legitimately produces
    # none of them at the pixel level.
    #
    # WALL_MATERIAL_CHANGE is required exactly when the unit actually changed the
    # material. Excluding it unconditionally meant the frozen probe was never
    # demanded of any unit, and a wall left standing at the previous material
    # would still pass every probe that WAS emitted.
    required = {"MANDATORY_PRE_CAPTURE_LIVENESS_WITNESS"}
    if material_transition:
        required.add("WALL_MATERIAL_CHANGE")
    observed_kinds = {probe.kind for probe in probes}
    missing = sorted(required - observed_kinds)
    if "MANDATORY_PRE_CAPTURE_LIVENESS_WITNESS" in missing:
        raise ExperimentIIIError(
            "CAPTURE_STALE_FRAME",
            "authority 7.10f (Amendment 4) requires a fixed ENGINEERING_ONLY "
            "pre-capture liveness witness before every scientific capture unit; "
            "none was recorded",
        )
    if "WALL_MATERIAL_CHANGE" in missing:
        raise ExperimentIIIError(
            "CAPTURE_STALE_FRAME",
            "this unit changed the wall material, and authority 7.10f requires an "
            "explicit pixel-level WALL_MATERIAL_CHANGE probe across that "
            "transition; the arena cache key is a claim about intent, not evidence",
        )
    probe_reports = [assert_transition_observed(probe) for probe in probes]

    hashes = [str(frame["frame_sha256"]) for frame in frames]
    distinct = len(set(hashes))
    return {
        "schema_version": "mineocclude-experiment-iii-capture-liveness-v1",
        "authority_section": "7.10f",
        "process_alive": True,
        "ticks": tick_report,
        "framebuffer": dimension_report,
        "probes": probe_reports,
        "probe_kinds_observed": sorted(observed_kinds),
        "required_probe_kinds": sorted(required),
        "required_probe_kinds_present": sorted(required & observed_kinds),
        "material_transition_probed": "WALL_MATERIAL_CHANGE" in observed_kinds,
        "guaranteed_change_transitions": sorted(
            observed_kinds & set(GUARANTEED_CHANGE_TRANSITIONS)
        ),
        "diagnostic_transitions": sorted(observed_kinds & set(DIAGNOSTIC_TRANSITIONS)),
        # Amendment 4. Recorded so a reader can see the scientific present/absent
        # comparison was made, and see that it carried no verdict.
        "scientific_present_absent_equal": [
            probe["kind"]
            for probe in probe_reports
            if not probe["verdict_bearing"] and not probe["framebuffer_changed"]
        ],
        "pixel_inequality_is_a_scientific_unit_validity_requirement": False,
        # Diagnostics only. A static settled state legitimately repeats bytes;
        # the withdrawn v1.5 rule treated this as failure and was unsound.
        "distinct_frame_hashes": distinct,
        "repeated_frame_hashes": len(hashes) - distinct,
        "repeated_bytes_within_static_state_is_stale": False,
        "passed": True,
    }

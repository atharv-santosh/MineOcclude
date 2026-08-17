"""Regression coverage for the Stage-1 BLOCKED operational repair.

Three demonstrated defects, each with the exploit that produced it:

* contract -- the v0.2 driver built a capture spec without ``spec_hash``, so the
  reused v0.1 ``capture_context`` raised ``KeyError: 'spec_hash'`` for every unit
  before a single frame was rendered;
* cleanup  -- ``launch_runtime`` raised from inside ``CaptureSession.__enter__``
  after starting the server, so ``__exit__`` never ran and the orphan kept the
  world ``session.lock``, which surfaced later as a misleading "already locked";
* preflight -- provenance reached FROZEN_VERIFIED without ever exercising the
  capture path, so it could not see either of the above.

Nothing here starts Minecraft or collects data.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import threading
import time
from copy import deepcopy
from pathlib import Path

import pytest

from mineocclude.prospective.source_provenance import ProvenanceViolation, verify_sources
from mineocclude.prospective.development_workflow import (
    CAPTURE_PATH_EXECUTABLES, CAPTURE_SPEC_REQUIRED_FIELDS, EvidenceError,
    OPERATIONAL_SMOKE_ARTIFACT_ID, OPERATIONAL_SMOKE_CLASSIFICATION,
    OPERATIONAL_SMOKE_DISPLAY_GEOMETRY, OPERATIONAL_SMOKE_HANDSHAKE_SCHEMA,
    OPERATIONAL_SMOKE_SCHEMA, OPERATIONAL_SMOKE_STAGES,
    RUNTIME_CRITICAL_SOURCE_PATHS,
    canonical_payload_sha256, capture_contract_preflight, capture_spec_hash,
    capture_toolchain_evidence, derive_effective_capture_spec, load_json,
    operational_smoke_namespace, refuse_operational_smoke_as_evidence,
    require_capture_spec_contract, require_capture_toolchain,
    require_operational_smoke, require_server_seed_contract,
    require_startspec_handshake, runtime_critical_source_closure_sha256,
)

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = (ROOT / "docs/status/integration/regime_a_prime_qualification_v0_1"
           / "prospective_development_authority_v0_2")
AUTHORITY_PATH = PACKAGE / "authority_parameters.json"
STAGE1_PATH = PACKAGE / "stage1_manifest.json"
V0_1_MANIFEST = (ROOT / "docs/status/integration/regime_a_occlusion_extraction_v0_1"
                 / "trajectory_manifest.jsonl")


@pytest.fixture
def authority():
    return load_json(AUTHORITY_PATH)


@pytest.fixture
def stage1():
    return load_json(STAGE1_PATH)


@pytest.fixture
def first_spec(stage1, authority):
    return derive_effective_capture_spec(stage1["units"][0], authority)


# ------------------------------------------------------------------ contract


def test_derivation_reproduces_the_frozen_v0_1_spec_hashes():
    """The derivation is the v0.1 one, not a plausible re-invention.

    Every frozen v0.1 trajectory spec must self-hash under the helper the v0.2
    path now uses. If this fails, the v0.2 identity is a different quantity
    wearing the same field name.
    """
    import json

    rows = [json.loads(line) for line in V0_1_MANIFEST.read_text().splitlines() if line.strip()]
    assert rows, "frozen v0.1 trajectory manifest is required for this test"
    for row in rows:
        body = {key: value for key, value in row.items() if key != "spec_hash"}
        assert capture_spec_hash(body) == row["spec_hash"]


def test_effective_capture_spec_carries_derived_hash_fields(first_spec):
    """1. The field whose absence produced the terminal KeyError."""
    for field in CAPTURE_SPEC_REQUIRED_FIELDS:
        assert field in first_spec, field
    assert first_spec["spec_hash"] == capture_spec_hash(first_spec)
    assert len(first_spec["spec_hash"]) == 64
    assert first_spec["spec_hash"] == first_spec["spec_hash"].lower()
    require_capture_spec_contract(first_spec)


def test_every_frozen_unit_derives_a_distinct_identity(stage1, authority):
    preflight = capture_contract_preflight(stage1, authority)
    assert preflight["units_checked"] == len(stage1["units"])
    hashes = preflight["capture_spec_sha256_by_unit"]
    assert len(set(hashes.values())) == len(hashes)


@pytest.mark.parametrize(
    "field, value",
    [("start_world_x", 999.0), ("speed_blocks_per_second", 9.5),
     ("direction", "RIGHT_TO_LEFT"), ("noise_seed", 12345), ("scene", "NO_WALL"),
     ("expected_frames", 17), ("episode_id", 424242)],
)
def test_scientific_mutation_changes_the_derived_hash(first_spec, field, value):
    """2. A changed capture contract must not keep its old identity."""
    mutated = deepcopy(first_spec)
    assert mutated[field] != value
    mutated[field] = value
    assert capture_spec_hash(mutated) != first_spec["spec_hash"]


def test_operational_dispatch_fields_do_not_move_the_identity(first_spec):
    """Relocating a receipt is not a scientific change.

    Those fields are bound separately by ``stage_run_inventory_sha256``; letting
    them into the capture identity would make it path-dependent.
    """
    moved = deepcopy(first_spec)
    moved["receipt_path"] = "/somewhere/else/receipt.json"
    moved["command"] = ["/usr/bin/false"]
    assert capture_spec_hash(moved) == first_spec["spec_hash"]


def test_copied_spec_hash_is_rejected(stage1, authority):
    """3. A hash lifted from a different unit must not authenticate this one."""
    first = derive_effective_capture_spec(stage1["units"][0], authority)
    second = derive_effective_capture_spec(stage1["units"][1], authority)
    forged = deepcopy(second)
    forged["spec_hash"] = first["spec_hash"]
    forged["raw_capture_spec_hash"] = first["spec_hash"]
    with pytest.raises(EvidenceError, match="not derived"):
        require_capture_spec_contract(forged)


def test_stale_spec_hash_after_a_scientific_edit_is_rejected(first_spec):
    """3. A spec edited after its identity was computed is caught."""
    stale = deepcopy(first_spec)
    stale["start_world_x"] = float(stale["start_world_x"]) + 2.5
    with pytest.raises(EvidenceError, match="not derived"):
        require_capture_spec_contract(stale)


def test_malformed_spec_hash_is_rejected(first_spec):
    for bad in ("NOTAHASH", "", "AB" * 32, "z" * 64):
        broken = deepcopy(first_spec)
        broken["spec_hash"] = bad
        with pytest.raises(EvidenceError):
            require_capture_spec_contract(broken)


def test_missing_spec_hash_is_rejected_before_any_launch(stage1, authority):
    """The original defect, now refused statically instead of at capture time."""
    naked = deepcopy(stage1["units"][0])
    naked.update({"trajectory_spec_id": naked["unit_id"],
                  "expected_max_frames": naked["expected_frames"],
                  "noise_schedule_sha256": "0" * 64})
    with pytest.raises(EvidenceError, match="missing required fields"):
        require_capture_spec_contract(naked)


def test_raw_capture_spec_hash_matches_the_v0_1_accessor(first_spec):
    """4. The v0.1 contract: physical identity, falling back to spec_hash."""
    from scripts.run_regime_a import ProductionCaptureWorker

    assert first_spec["raw_capture_spec_hash"] == first_spec["spec_hash"]
    assert ProductionCaptureWorker._raw_capture_spec_hash(first_spec) == first_spec["spec_hash"]
    # Absent is legal at the v0.1 interface and means "same as spec_hash".
    without = {k: v for k, v in first_spec.items() if k != "raw_capture_spec_hash"}
    assert ProductionCaptureWorker._raw_capture_spec_hash(without) == first_spec["spec_hash"]
    require_capture_spec_contract(without)


def test_divergent_raw_capture_spec_hash_is_rejected(first_spec):
    """v0.2 declares no versioned amendment, so the two identities must agree."""
    amended = deepcopy(first_spec)
    amended["raw_capture_spec_hash"] = "b" * 64
    with pytest.raises(EvidenceError, match="raw_capture_spec_hash"):
        require_capture_spec_contract(amended)


def test_first_unit_spec_crosses_the_former_keyerror(first_spec, tmp_path):
    """5. The exact call that terminated the blocked campaign now returns.

    ``capture_context`` is the frozen v0.1 function that raised
    ``KeyError: 'spec_hash'``. Building the context is strictly before any
    rendering, so this crosses the failing interface without capturing a frame.
    """
    from scripts.regime_a_prime_qualification_v0_1.p2_common import capture_context

    context = capture_context(first_spec, int(first_spec["episode_id"]), tmp_path)
    assert context["frames"] == first_spec["expected_frames"]
    assert context["motion_bytes"]
    # The motion document carries the derived identity through to the apparatus.
    import json

    motion = json.loads(context["motion_bytes"].decode())
    assert motion["spec_hash"] == first_spec["spec_hash"]


# ------------------------------------------------------------------- cleanup


class FakeProcess:
    """Minimal Popen stand-in: records the signals a teardown actually sent."""

    def __init__(self, pid: int, *, ignores_terminate: bool = False,
                 already_exited: bool = False):
        self.pid = pid
        self.ignores_terminate = ignores_terminate
        self._running = not already_exited
        self.terminated = False
        self.killed = False

    def poll(self):
        return None if self._running else 0

    def terminate(self):
        self.terminated = True
        if not self.ignores_terminate:
            self._running = False

    def kill(self):
        self.killed = True
        self._running = False

    def wait(self, timeout=None):
        if self._running:
            raise subprocess.TimeoutExpired("fake", timeout or 0)
        return 0


def _campaign():
    from scripts import run_large_scale_no_wall_campaign as live

    return live


def test_partial_startup_teardown_stops_every_acquired_process():
    """6. Everything a failed attempt started is stopped."""
    live = _campaign()
    processes = [FakeProcess(1), FakeProcess(2)]
    assert live.terminate_launched(processes) == []
    assert all(process.terminated for process in processes)
    assert all(process.poll() is not None for process in processes)


def test_partial_startup_teardown_escalates_to_kill():
    """A wedged JVM keeps holding session.lock unless it is killed."""
    live = _campaign()
    stubborn = FakeProcess(3, ignores_terminate=True)
    assert live.terminate_launched([stubborn], timeout=0.01) == []
    assert stubborn.killed
    assert stubborn.poll() is not None


def test_partial_startup_teardown_is_idempotent_and_partial_safe():
    """6. Safe when only some resources started, and when run twice."""
    live = _campaign()
    processes = [FakeProcess(4, already_exited=True), FakeProcess(5)]
    assert live.terminate_launched(processes) == []
    assert live.terminate_launched(processes) == []
    assert live.terminate_launched([]) == []


def test_partial_startup_teardown_touches_only_its_own_processes():
    """6. A pre-existing runtime someone else owns is never signalled."""
    live = _campaign()
    unrelated = FakeProcess(6)
    mine = FakeProcess(7)
    live.terminate_launched([mine])
    assert mine.terminated and not unrelated.terminated
    assert unrelated.poll() is None


def test_survivors_are_reported_rather_than_hidden():
    """Cleanup that could not finish must say so; session.lock may still be held."""
    live = _campaign()

    class Immortal(FakeProcess):
        def kill(self):
            self.killed = True  # refuses to die

    problems = live.terminate_launched([Immortal(8, ignores_terminate=True)], timeout=0.01)
    assert problems and any("session.lock" in problem for problem in problems)


def test_startup_root_exception_is_preserved(capsys):
    """7. Cleanup never replaces the exception that caused it."""
    live = _campaign()
    root = RuntimeError("original startup cause")

    class Immortal(FakeProcess):
        def kill(self):
            self.killed = True

    problems = live.release_partial_launch([Immortal(9, ignores_terminate=True)], root)
    assert problems
    # Reported on stderr, not raised: the caller still re-raises `root`.
    assert "partial-launch cleanup incomplete" in capsys.readouterr().err


def test_launch_runtime_releases_partial_startup_on_failure(monkeypatch):
    """6+7. The demonstrated exploit: precheck fails after the server started."""
    live = _campaign()
    started: list[FakeProcess] = []

    def fake_popen(*args, **kwargs):
        process = FakeProcess(100 + len(started))
        started.append(process)
        return process

    monkeypatch.setattr(live.subprocess, "Popen", fake_popen)
    # Display never becomes ready -> CampaignError after one process started.
    monkeypatch.setattr(live.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 1, b"", b""))
    monkeypatch.setattr(live.time, "sleep", lambda _seconds: None)

    with pytest.raises(live.CampaignError) as caught:
        live.launch_runtime(Path("/tmp/mineocclude-test-runtime-root"))

    assert "Xvfb launch timeout" in str(caught.value)  # root cause preserved
    assert started, "the exploit requires at least one process to have started"
    assert all(process.poll() is not None for process in started), \
        "a failed startup left a process running; this is the session.lock leak"


# ------------------------------------------------------------------ preflight


def _toolchain_evidence() -> dict:
    """A fully-present toolchain document, independent of this host.

    The negative cases below used to be built by mutating
    ``capture_toolchain_evidence()``, which probes the live host. On a machine
    where the operator-tools overlay is not mounted every tool reads absent, so
    the mutation was masked by a prior refusal and the test failed for a reason
    unrelated to what it asserts. The unit under test is
    ``require_capture_toolchain``, which adjudicates a document -- so the
    document, not the host, is what these tests should supply.
    """
    return {
        "schema": "mineocclude-capture-toolchain-v0.1",
        "tools": {name: {"required_by": "frozen_capture_path",
                         "materiality": materiality, "present": True,
                         "path": f"/usr/bin/{name}", "package": None,
                         "package_version": None, "missing_shared_libraries": []}
                  for name, materiality in CAPTURE_PATH_EXECUTABLES},
        "all_present": True, "all_linkable": True,
    }


def test_capture_toolchain_covers_exactly_the_capture_path():
    evidence = capture_toolchain_evidence()
    assert set(evidence["tools"]) == {"Xvfb", "openbox", "xdpyinfo", "xdotool"}
    # Provisioning-only tools must not be required before a capture authorization.
    assert "ffmpeg" not in evidence["tools"]
    assert "curl" not in evidence["tools"]


def test_a_complete_toolchain_is_accepted():
    require_capture_toolchain(_toolchain_evidence())


def test_missing_capture_executable_refuses_authorization():
    """8. The x11-utils/xdotool/openbox class of blocker, caught pre-authorization."""
    broken = _toolchain_evidence()
    broken["tools"]["xdotool"].update({"present": False, "path": None})
    with pytest.raises(EvidenceError, match="absent"):
        require_capture_toolchain(broken)


def test_unlinkable_capture_executable_refuses_authorization():
    """Present but unusable fails at launch exactly like absent."""
    broken = _toolchain_evidence()
    broken["tools"]["openbox"]["missing_shared_libraries"] = ["libfoo.so.1"]
    with pytest.raises(EvidenceError, match="resolve libraries"):
        require_capture_toolchain(broken)


def test_incomplete_toolchain_coverage_is_refused():
    broken = _toolchain_evidence()
    broken["tools"].pop("Xvfb")
    with pytest.raises(EvidenceError, match="does not cover"):
        require_capture_toolchain(broken)


# The server's real arming line, verbatim in shape: EpisodeManager logs
# "episode {} armed (layout={}, {} warmup + {} record ticks, v={}, q={}, seed={},
# rng={})". Both the seed and the rng source are read out of it by the verifier,
# so a fixture that paraphrased it would not exercise the parse.
_SMOKE_SEED = 1239302675008784277
_ARMED_LINE = (
    "[12:00:44] [Server thread/INFO]: [MineOcclude] episode 990001 armed "
    "(layout=layout_01, 1200 warmup + 180 record ticks, v=2.0, q=0.05, "
    f"seed={_SMOKE_SEED}, rng=immutable_numpy_schedule)"
)
_STARTSPEC_COMMAND = (
    f"mineocclude startspec layout_01 990001 {_SMOKE_SEED} 0.05 180 -7.8 "
    "smoke_a1q_ltr_wall_r01 " + "d" * 64
)


def _handshake(**overrides) -> dict:
    """A startspec handshake record of the shape ``arm_only`` returns."""
    record = {"schema": OPERATIONAL_SMOKE_HANDSHAKE_SCHEMA,
              "episode_id": 990001,
              "seed": _SMOKE_SEED,
              "noise_seed": _SMOKE_SEED,
              "schedule_seed_header": _SMOKE_SEED,
              "startspec_command": _STARTSPEC_COMMAND,
              "armed": True,
              "armed_log_line": _ARMED_LINE,
              "refusal": None,
              "rng_source": "immutable_numpy_schedule",
              "recording_started": False,
              "frames_written": 0}
    record.update(overrides)
    return record


def _stage_evidence() -> dict:
    """Stage records whose digests are genuinely computed over their excerpts."""
    excerpts = {
        "display_ready": "dimensions:    640x360 pixels\ndepth of root window: 24 planes\n",
        "server_ready": "[12:00:01] [Server thread/INFO]: Done (5.1s)! server ready\n",
        "client_joined": "[12:00:31] [Render thread/INFO]: smoke joined the game\n",
        "episode_armed": _ARMED_LINE + "\n",
        "teardown": "smoke: all launched pids exited; teardown_complete\n",
    }
    return {name: {"source_path": f"/runtime_logs/{name}.log",
                   "excerpt": text,
                   "excerpt_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                   "observed_monotonic": float(index)}
            for index, (name, text) in enumerate(excerpts.items())}


def _passing_smoke(namespace: str, commit: str = "abc123",
                   closure: str = "c" * 64, **overrides) -> dict:
    """A structurally complete v0.2 smoke document with a valid payload digest.

    Built the way the runner would build it, then sealed, so every negative case
    below is a single deliberate mutation of an otherwise-passing document.
    """
    smoke = {
        "schema": OPERATIONAL_SMOKE_SCHEMA,
        "artifact_id": OPERATIONAL_SMOKE_ARTIFACT_ID,
        "classification": OPERATIONAL_SMOKE_CLASSIFICATION,
        "run_namespace": operational_smoke_namespace(namespace),
        "scientific_evidence": False,
        "counts_toward_stage1_units": False,
        "status": "PASS",
        "source_commit": commit,
        "runtime_critical_source_closure_sha256": closure,
        "java_executable": {"path": "/usr/lib/jvm/java-17/bin/java",
                            "sha256": "a" * 64,
                            "version_line": 'openjdk version "17.0.19"'},
        "display": {"name": ":99", "geometry": "640x360x24",
                    "xdpyinfo_width": 640, "xdpyinfo_height": 360,
                    "xdpyinfo_depth": 24, "started_by_smoke": True},
        "openbox": {"started_by_smoke": True, "pid": 4102},
        "stage_evidence": _stage_evidence(),
        "startspec_handshake": _handshake(),
        "launched_processes": [{"pid": 4101, "role": "display", "exited": True},
                               {"pid": 4103, "role": "server", "exited": True},
                               {"pid": 4104, "role": "client", "exited": True}],
        "stranded_processes": [],
        "session_lock_present_after_teardown": False,
        "frames_captured": 0,
        "scientific_receipts_written": 0,
        "stage1_durable_objects_written": 0,
    }
    smoke.update(overrides)
    smoke["payload_sha256"] = canonical_payload_sha256(smoke, omit="payload_sha256")
    return smoke


def _reseal(smoke: dict) -> dict:
    smoke["payload_sha256"] = canonical_payload_sha256(smoke, omit="payload_sha256")
    return smoke


def test_a_genuine_smoke_document_is_accepted(stage1):
    namespace = str(stage1["run_namespace"])
    require_operational_smoke(_passing_smoke(namespace), run_namespace=namespace,
                              source_commit="abc123", closure_sha256="c" * 64)


def test_hand_written_pass_booleans_are_refused(stage1):
    """D3.4. The superseded v0.1 document -- the exploit this repair closes.

    This is exactly what used to authorize a campaign: a JSON file asserting
    that the server started, the client joined and teardown succeeded, with no
    evidence behind any of it.
    """
    namespace = str(stage1["run_namespace"])
    hand_written = {"artifact_id": OPERATIONAL_SMOKE_ARTIFACT_ID,
                    "classification": OPERATIONAL_SMOKE_CLASSIFICATION,
                    "run_namespace": operational_smoke_namespace(namespace),
                    "scientific_evidence": False, "counts_toward_stage1_units": False,
                    "server_started": True, "client_joined": True,
                    "capture_contract_crossed": True, "runtime_torn_down": True,
                    "stranded_processes": [], "status": "PASS",
                    "source_commit": "abc123"}
    with pytest.raises(EvidenceError, match="v0.2"):
        require_operational_smoke(hand_written, run_namespace=namespace,
                                  source_commit="abc123")


def test_mutated_payload_without_a_recomputed_digest_is_refused(stage1):
    """D3.5. Any edit anywhere invalidates the payload identity."""
    namespace = str(stage1["run_namespace"])
    tampered = _passing_smoke(namespace)
    tampered["frames_captured"] = 0  # unchanged value, but touch a neighbour:
    tampered["display"]["name"] = ":77"
    with pytest.raises(EvidenceError, match="payload_sha256 does not reproduce"):
        require_operational_smoke(tampered, run_namespace=namespace,
                                  source_commit="abc123")


@pytest.mark.parametrize("stage", ["server_ready", "client_joined"])
def test_forged_stage_digest_is_refused(stage1, stage):
    """D3.6/7. A digest that does not recompute from its own excerpt."""
    namespace = str(stage1["run_namespace"])
    forged = _passing_smoke(namespace)
    forged["stage_evidence"][stage]["excerpt_sha256"] = "b" * 64
    with pytest.raises(EvidenceError, match=f"{stage} does not match its digest"):
        require_operational_smoke(_reseal(forged), run_namespace=namespace,
                                  source_commit="abc123")


@pytest.mark.parametrize("stage,marker", [("server_ready", "server ready"),
                                          ("client_joined", "joined the game")])
def test_stage_evidence_without_its_marker_is_refused(stage1, stage, marker):
    """A correctly-digested excerpt that never showed the startup happened."""
    namespace = str(stage1["run_namespace"])
    forged = _passing_smoke(namespace)
    text = "nothing of interest occurred here\n"
    forged["stage_evidence"][stage].update(
        excerpt=text, excerpt_sha256=hashlib.sha256(text.encode()).hexdigest())
    with pytest.raises(EvidenceError, match="does not contain the marker"):
        require_operational_smoke(_reseal(forged), run_namespace=namespace,
                                  source_commit="abc123")


def test_out_of_order_stages_are_refused(stage1):
    """Evidence cannot be reassembled into an order startup cannot produce."""
    namespace = str(stage1["run_namespace"])
    forged = _passing_smoke(namespace)
    forged["stage_evidence"]["client_joined"]["observed_monotonic"] = -5.0
    with pytest.raises(EvidenceError, match="out of order"):
        require_operational_smoke(_reseal(forged), run_namespace=namespace,
                                  source_commit="abc123")


def test_missing_stage_evidence_is_refused(stage1):
    namespace = str(stage1["run_namespace"])
    forged = _passing_smoke(namespace)
    forged["stage_evidence"].pop("client_joined")
    with pytest.raises(EvidenceError, match="must cover exactly"):
        require_operational_smoke(_reseal(forged), run_namespace=namespace,
                                  source_commit="abc123")


@pytest.mark.parametrize("field", ["frames_captured", "scientific_receipts_written",
                                   "stage1_durable_objects_written"])
def test_a_smoke_that_collected_anything_is_refused(stage1, field):
    """D3.8/9/10. Non-collection is verified as a count, not asserted."""
    namespace = str(stage1["run_namespace"])
    collected = _passing_smoke(namespace, **{field: 1})
    with pytest.raises(EvidenceError, match="not non-scientific"):
        require_operational_smoke(collected, run_namespace=namespace,
                                  source_commit="abc123")


def test_operational_smoke_must_be_from_this_commit(stage1):
    namespace = str(stage1["run_namespace"])
    with pytest.raises(EvidenceError, match="not produced at this commit"):
        require_operational_smoke(_passing_smoke(namespace, commit="old"),
                                  run_namespace=namespace, source_commit="new")


def test_operational_smoke_must_bind_this_source_closure(stage1):
    """D2/D3. A smoke taken before an apparatus edit cannot authorize it."""
    namespace = str(stage1["run_namespace"])
    with pytest.raises(EvidenceError, match="not bound to this runtime-critical closure"):
        require_operational_smoke(_passing_smoke(namespace, closure="d" * 64),
                                  run_namespace=namespace, source_commit="abc123",
                                  closure_sha256="c" * 64)


def test_stranded_process_fails_the_smoke(stage1):
    namespace = str(stage1["run_namespace"])
    broken = _passing_smoke(namespace, stranded_processes=[4242])
    with pytest.raises(EvidenceError, match="stranded"):
        require_operational_smoke(broken, run_namespace=namespace, source_commit="abc123")


def test_a_surviving_launched_process_fails_the_smoke(stage1):
    """D4.15. Teardown must leave zero smoke-owned processes."""
    namespace = str(stage1["run_namespace"])
    broken = _passing_smoke(namespace)
    broken["launched_processes"][1]["exited"] = False
    with pytest.raises(EvidenceError, match="left pid 4103 running"):
        require_operational_smoke(_reseal(broken), run_namespace=namespace,
                                  source_commit="abc123")


def test_retained_session_lock_fails_the_smoke(stage1):
    """D5.20. session.lock must be released by the owned-server termination."""
    namespace = str(stage1["run_namespace"])
    broken = _passing_smoke(namespace, session_lock_present_after_teardown=True)
    with pytest.raises(EvidenceError, match="session.lock"):
        require_operational_smoke(broken, run_namespace=namespace, source_commit="abc123")


def test_operational_smoke_cannot_become_stage1_evidence(stage1):
    """9. Four independent markers each disqualify smoke output."""
    namespace = str(stage1["run_namespace"])
    smoke = _passing_smoke(namespace)
    with pytest.raises(EvidenceError, match="cannot be Stage-1 evidence"):
        refuse_operational_smoke_as_evidence(smoke, "smoke")

    for marker in ("classification", "artifact_id", "run_namespace", "scientific_evidence"):
        laundered = {"unit_id": "a1q_ltr_wall_r01", marker: smoke[marker]}
        with pytest.raises(EvidenceError, match="cannot be Stage-1 evidence"):
            refuse_operational_smoke_as_evidence(laundered, "laundered")


def test_a_real_stage1_unit_is_not_refused(stage1):
    """The barrier must not reject legitimate units."""
    for unit in stage1["units"]:
        refuse_operational_smoke_as_evidence(unit, unit["unit_id"])
    refuse_operational_smoke_as_evidence(stage1, "manifest")


def test_smoke_namespace_is_disjoint_from_the_scientific_namespace(stage1):
    namespace = str(stage1["run_namespace"])
    assert operational_smoke_namespace(namespace) != namespace
    assert operational_smoke_namespace(namespace).startswith(namespace)


def test_absent_smoke_evidence_is_refused(stage1):
    namespace = str(stage1["run_namespace"])
    with pytest.raises(EvidenceError, match="absent"):
        require_operational_smoke(None, run_namespace=namespace)
    # An empty document is refused too, just at the first binding it fails.
    with pytest.raises(EvidenceError):
        require_operational_smoke({}, run_namespace=namespace)


def _provenance_with(tmp_path, authority, stage1, monkeypatch, **extra):
    """A receipt correct for this tree, plus whatever capture-path fields are given.

    ``git`` is stubbed to report the clean tree a real freeze would have; the
    control under test is the capture-path gate, not the dirty-tree gate that
    fires earlier and would otherwise mask it in a working tree.
    """
    import json as _json

    from mineocclude.prospective import development_workflow as workflow
    from tests.prospective.test_provenance_authorization_and_stage_binding import (
        frozen_provenance,
    )

    path = frozen_provenance(tmp_path, authority, stage1, **extra)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
                          capture_output=True, check=True).stdout.strip()
    receipt = _json.loads(path.read_text())
    receipt["source_commit"] = head
    receipt["payload_sha256"] = None
    receipt.pop("payload_sha256")
    from mineocclude.prospective.development_workflow import canonical_payload_sha256

    receipt["payload_sha256"] = canonical_payload_sha256(receipt)

    real_run = subprocess.run

    def fake_run(command, *args, **kwargs):
        if command[:2] == ["git", "status"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:2] == ["git", "rev-parse"]:
            return subprocess.CompletedProcess(command, 0, head + "\n", "")
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(workflow.subprocess, "run", fake_run)
    return receipt


def test_old_provenance_without_smoke_cannot_authorize(
        tmp_path, stage1, authority, monkeypatch):
    """10. A receipt predating these controls cannot launch the successor campaign.

    This is the end-to-end gate, not its parts: the receipt is otherwise
    completely valid for this tree.
    """
    from mineocclude.prospective.development_workflow import require_preoutcome_provenance

    receipt = _provenance_with(tmp_path, authority, stage1, monkeypatch)
    assert "operational_startup_smoke" not in receipt
    with pytest.raises(PermissionError, match="capture-path preflight"):
        require_preoutcome_provenance(
            receipt, authority_path=AUTHORITY_PATH, manifest_path=STAGE1_PATH,
            required_source_paths=[ROOT / "src/mineocclude/prospective/development_workflow.py"])


def test_provenance_carrying_the_new_controls_clears_the_capture_gate(
        tmp_path, stage1, authority, monkeypatch):
    """The gate must accept a receipt that genuinely satisfies it.

    Asserted as "does not fail *here*": the later source-binding check compares
    working-tree bytes against HEAD, which cannot hold in an unfrozen tree, so a
    fully green ``require_preoutcome_provenance`` is only reachable post-freeze.
    What is provable now is that the capture-path control is not what refuses.
    """
    from mineocclude.prospective.development_workflow import require_preoutcome_provenance

    namespace = str(stage1["run_namespace"])
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
                          capture_output=True, check=True).stdout.strip()
    receipt = _provenance_with(
        tmp_path, authority, stage1, monkeypatch,
        capture_toolchain=capture_toolchain_evidence(),
        capture_contract_preflight=capture_contract_preflight(stage1, authority),
        operational_startup_smoke=_passing_smoke(
            namespace, commit=head,
            # Must be this tree's real closure: the gate binds the smoke to the
            # apparatus source it was produced from, so a placeholder would make
            # the capture-path control itself the refusal this test denies.
            closure=runtime_critical_source_closure_sha256(ROOT)))
    with pytest.raises(PermissionError) as caught:
        require_preoutcome_provenance(
            receipt, authority_path=AUTHORITY_PATH, manifest_path=STAGE1_PATH,
            required_source_paths=[ROOT / "src/mineocclude/prospective/development_workflow.py"])
    assert "capture-path preflight" not in str(caught.value)


def test_tampered_preflight_in_provenance_is_refused(
        tmp_path, stage1, authority, monkeypatch):
    """A preflight claiming identities the manifest does not produce is caught."""
    from mineocclude.prospective.development_workflow import require_preoutcome_provenance

    namespace = str(stage1["run_namespace"])
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
                          capture_output=True, check=True).stdout.strip()
    forged = capture_contract_preflight(stage1, authority)
    first = next(iter(forged["capture_spec_sha256_by_unit"]))
    forged["capture_spec_sha256_by_unit"][first] = "f" * 64
    receipt = _provenance_with(
        tmp_path, authority, stage1, monkeypatch,
        capture_toolchain=capture_toolchain_evidence(),
        capture_contract_preflight=forged,
        operational_startup_smoke=_passing_smoke(namespace, commit=head))
    with pytest.raises(PermissionError, match="does not reproduce"):
        require_preoutcome_provenance(
            receipt, authority_path=AUTHORITY_PATH, manifest_path=STAGE1_PATH,
            required_source_paths=[ROOT / "src/mineocclude/prospective/development_workflow.py"])


def test_preflight_reproduces_from_the_production_construction_path(stage1, authority):
    """The preflight and the run must not be able to disagree."""
    preflight = capture_contract_preflight(stage1, authority)
    for unit in stage1["units"]:
        produced = derive_effective_capture_spec(unit, authority)
        assert preflight["capture_spec_sha256_by_unit"][unit["unit_id"]] == produced["spec_hash"]


# ------------------------------------------------- D1/D2 apparatus source closure


CAMPAIGN_SOURCE = "scripts/run_large_scale_no_wall_campaign.py"
PROVISION_SOURCE = "scripts/provision_capture_runtime_sagemaker.sh"


@pytest.mark.parametrize("relative", [CAMPAIGN_SOURCE, PROVISION_SOURCE])
def test_capture_startup_source_is_in_the_runtime_critical_closure(relative):
    """D1.1/D2.1. Both control real apparatus behaviour, so both are enumerated.

    ``p2_common.load_live()`` imports the campaign module, which owns
    ``LiveRuntime.send``, the startspec FIFO command and ``launch_runtime``; and
    ``launch_runtime`` execs the provisioning script, which owns the Xvfb
    geometry, ``LIBGL_ALWAYS_SOFTWARE``, the JVM arguments and the natives path.
    Neither was enumerated, so their bytes could change what a capture did
    without changing the digest that authorizes it.
    """
    assert relative in RUNTIME_CRITICAL_SOURCE_PATHS
    assert (ROOT / relative).is_file()


def test_the_enumerated_campaign_path_is_the_one_actually_imported():
    """The closure must name the module p2_common really loads, not a lookalike.

    ``load_live`` does ``from scripts import run_large_scale_no_wall_campaign``,
    which resolves to ``scripts/run_large_scale_no_wall_campaign.py``. A closure
    entry under any other directory would pin a file the apparatus never reads.
    """
    live = _campaign()
    resolved = Path(live.__file__).resolve().relative_to(ROOT)
    assert str(resolved) == CAMPAIGN_SOURCE
    assert CAMPAIGN_SOURCE in RUNTIME_CRITICAL_SOURCE_PATHS


def test_the_enumerated_provision_path_is_the_one_launch_runtime_execs():
    """The provisioning script is reached by path, so pin that exact path."""
    text = (ROOT / CAMPAIGN_SOURCE).read_text()
    assert f'ROOT / "{PROVISION_SOURCE}"' in text
    assert PROVISION_SOURCE in RUNTIME_CRITICAL_SOURCE_PATHS


@pytest.mark.parametrize("relative", [CAMPAIGN_SOURCE, PROVISION_SOURCE])
def test_mutating_a_capture_startup_source_changes_the_closure_digest(relative, tmp_path):
    """D1.3/D2.3. A byte edit must move the runtime-critical closure SHA.

    Mutates a full copy of the repository tree rather than the working tree, so
    the check cannot damage the real sources it is verifying.
    """
    mirror = tmp_path / "mirror"
    mirror.mkdir()
    for path in RUNTIME_CRITICAL_SOURCE_PATHS:
        destination = mirror / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / path).read_bytes())

    before = runtime_critical_source_closure_sha256(mirror)
    assert before == runtime_critical_source_closure_sha256(ROOT)

    target = mirror / relative
    target.write_bytes(target.read_bytes() + b"\n# apparatus mutation\n")
    assert runtime_critical_source_closure_sha256(mirror) != before


@pytest.mark.parametrize("relative", [CAMPAIGN_SOURCE, PROVISION_SOURCE])
def test_mutated_capture_startup_source_is_refused_by_verification(relative, tmp_path):
    """D1.4/D2.4. The mutation must be refused, not merely observed.

    Pins each source to its current digest, mutates one, and requires
    ``verify_sources`` to name that path as a violation.
    """
    from mineocclude.prospective.source_provenance import CriticalSource, sha256_file

    mirror = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(mirror)], check=True)
    for path in (CAMPAIGN_SOURCE, PROVISION_SOURCE):
        destination = mirror / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / path).read_bytes())
    subprocess.run(["git", "-C", str(mirror), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(mirror), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "pin"], check=True)
    head = subprocess.run(["git", "-C", str(mirror), "rev-parse", "HEAD"],
                          text=True, capture_output=True, check=True).stdout.strip()

    pinned = [CriticalSource(path, sha256_file(mirror / path))
              for path in (CAMPAIGN_SOURCE, PROVISION_SOURCE)]
    assert verify_sources(mirror, pinned, expected_head=head).verified

    target = mirror / relative
    target.write_bytes(target.read_bytes() + b"\n# apparatus mutation\n")
    receipt = verify_sources(mirror, pinned, expected_head=head)
    assert not receipt.verified
    assert any(relative in violation for violation in receipt.violations)
    with pytest.raises(ProvenanceViolation):
        receipt.require_verified()


# ------------------------------------------------------ D5 teardown must not hang


def _capture_session(tmp_path, monkeypatch, *, server_alive: bool):
    """A ``CaptureSession`` bound to fake processes and an isolated FIFO.

    ``CaptureSession.__init__`` calls ``load_live()``, which requires the pinned
    JDK to be present, and ``__enter__`` launches a real runtime -- neither is
    available or wanted here. The unit under test is ``__exit__``, so the object
    is constructed directly and handed exactly the state a live session would
    hold. ``FIFO`` is redirected into ``tmp_path`` so no test can ever reach the
    real server's command pipe.
    """
    import importlib

    p2_common = importlib.import_module(
        "scripts.regime_a_prime_qualification_v0_1.p2_common")
    live = _campaign()
    monkeypatch.setattr(live, "FIFO", tmp_path / "cmd.fifo")

    # [display, server, client] -- the order launch_runtime builds and the order
    # request_graceful_stop reads the server from.
    processes = [FakeProcess(1), FakeProcess(2, already_exited=not server_alive),
                 FakeProcess(3)]
    session = object.__new__(p2_common.CaptureSession)
    session.live = live
    session.processes = list(processes)
    session.runtime = None
    session.scene_mode = "nowall"
    return session, processes


def test_graceful_stop_does_not_block_when_the_server_is_dead():
    """D5.16. The dead-server case that used to hang ``__exit__`` forever."""
    live = _campaign()
    processes = [FakeProcess(1), FakeProcess(2, already_exited=True), FakeProcess(3)]
    assert live.request_graceful_stop(processes) == "skipped_server_not_running"


def test_graceful_stop_does_not_block_on_a_fifo_with_no_reader(tmp_path, monkeypatch):
    """D5.17. The real primitive: a genuine FIFO that nobody is reading.

    ``open(fifo, "w")`` blocks until a reader attaches. This test would hang
    outright against the superseded implementation, so the timeout is the
    assertion -- pytest-timeout is not required because a live FIFO with no
    reader either returns immediately or never returns at all.
    """
    fifo = tmp_path / "cmd.fifo"
    os.mkfifo(fifo)
    live = _campaign()
    monkeypatch.setattr(live, "FIFO", fifo)
    # Server reported as running, so the liveness guard does not short-circuit;
    # only the non-blocking open can save this call.
    processes = [FakeProcess(1), FakeProcess(2), FakeProcess(3)]

    finished = threading.Event()
    outcome: list[str] = []

    def run():
        outcome.append(live.request_graceful_stop(processes))
        finished.set()

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    assert finished.wait(timeout=10), "request_graceful_stop blocked on a reader-less FIFO"
    assert outcome == ["skipped_ENXIO"]


def test_graceful_stop_writes_when_a_reader_is_attached(tmp_path, monkeypatch):
    """The polite path must still work when the server is alive and reading."""
    fifo = tmp_path / "cmd.fifo"
    os.mkfifo(fifo)
    live = _campaign()
    monkeypatch.setattr(live, "FIFO", fifo)
    processes = [FakeProcess(1), FakeProcess(2), FakeProcess(3)]

    received: list[bytes] = []

    def reader():
        with open(fifo, "rb") as stream:
            received.append(stream.read())

    consumer = threading.Thread(target=reader, daemon=True)
    consumer.start()
    time.sleep(0.2)  # let the reader attach so the write side finds it
    assert live.request_graceful_stop(processes) == "sent"
    consumer.join(timeout=10)
    assert received == [b"stop\n"]


def test_exit_runs_authoritative_cleanup_when_the_server_is_dead(tmp_path, monkeypatch):
    """D5.1/2/7. Teardown completes and strands nothing, dead server or not."""
    session, processes = _capture_session(tmp_path, monkeypatch, server_alive=False)
    session.__exit__(None, None, None)
    assert all(process.poll() is not None for process in processes)
    assert session.processes == []


def test_exit_preserves_the_original_exception(tmp_path, monkeypatch):
    """D5.4/6/18. A cleanup problem must not replace the real failure.

    Drives ``__exit__`` the way a ``with`` block does on the exception path --
    ``__enter__`` is not used, because it would launch a real runtime -- and
    requires the with-block's own exception to be the one that propagates.
    """
    import sys as _sys

    session, processes = _capture_session(tmp_path, monkeypatch, server_alive=False)

    class Boom(RuntimeError):
        pass

    with pytest.raises(Boom, match="the real failure"):
        try:
            raise Boom("the real failure")
        finally:
            session.__exit__(*_sys.exc_info())

    # Teardown still ran to completion; any complaint went to stderr, not upward.
    assert all(process.poll() is not None for process in processes)
    assert session.processes == []


def test_repeated_cleanup_is_safe(tmp_path, monkeypatch):
    """D5.5/19. Idempotent: a second teardown must not raise or re-signal."""
    session, processes = _capture_session(tmp_path, monkeypatch, server_alive=False)
    session.__exit__(None, None, None)
    session.__exit__(None, None, None)
    session.__exit__(None, None, None)
    assert session.processes == []


def test_exit_never_touches_processes_it_did_not_launch(tmp_path, monkeypatch):
    """D5. Someone else's runtime is not this session's to kill."""
    session, _ = _capture_session(tmp_path, monkeypatch, server_alive=False)
    stranger = FakeProcess(999)
    session.__exit__(None, None, None)
    assert not stranger.terminated and not stranger.killed


# ------------------------------------------- D4 the smoke must own a real display


def _receipts():
    import importlib

    return importlib.import_module(
        "scripts.regime_a_prime_qualification_v0_2.generate_receipts")


def test_a_pre_existing_display_cannot_satisfy_the_smoke(tmp_path, monkeypatch):
    """D4.14. The exploit: a generic 1280x720 display already serving on :99.

    ``ensure_display`` used to start exactly that -- the authority pins the
    renderer-probe display as "0 1280x720x24" -- and the production
    ``start_display`` then early-returns on its own ``xdpyinfo`` check, so the
    real 640x360x24 capture Xvfb and openbox never started. The smoke must refuse
    a display it did not start rather than silently reuse one.
    """
    receipts = _receipts()
    socket = tmp_path / "X99"
    socket.write_text("")
    monkeypatch.setattr(receipts, "display_socket", lambda display: socket)
    with pytest.raises(EvidenceError, match="already serving"):
        receipts.require_no_pre_existing_display(":99")


def test_an_unoccupied_display_is_allowed(tmp_path, monkeypatch):
    receipts = _receipts()
    monkeypatch.setattr(receipts, "display_socket", lambda display: tmp_path / "absent")
    receipts.require_no_pre_existing_display(":99")


def test_the_authority_generic_display_is_not_the_capture_geometry():
    """The two displays are genuinely different, which is why D4 mattered.

    If these ever coincided the defect would be invisible, so assert the gap the
    repair exists to close.
    """
    authority = load_json(AUTHORITY_PATH)
    generic = authority["runtime_identity_policy"]["runtime_reconstruction"]["xvfb_screen"]
    assert generic == "0 1280x720x24"
    assert OPERATIONAL_SMOKE_DISPLAY_GEOMETRY == "640x360x24"
    assert OPERATIONAL_SMOKE_DISPLAY_GEOMETRY not in generic


def test_production_start_display_uses_the_capture_geometry_and_openbox():
    """D4.11/12/13. The bytes the smoke must exercise really do start both."""
    text = (ROOT / PROVISION_SOURCE).read_text()
    assert f"-screen 0 {OPERATIONAL_SMOKE_DISPLAY_GEOMETRY}" in text
    assert 'openbox &' in text
    # And the early-return that a pre-created display would trigger.
    assert 'xdpyinfo >/dev/null 2>&1; then' in text


def test_smoke_geometry_evidence_is_rejected_at_the_generic_geometry(stage1):
    """A smoke reporting the renderer-probe geometry cannot authorize capture."""
    namespace = str(stage1["run_namespace"])
    generic = _passing_smoke(namespace)
    generic["display"].update(geometry="1280x720x24", xdpyinfo_width=1280,
                              xdpyinfo_height=720)
    with pytest.raises(EvidenceError, match="geometry is not 640x360x24"):
        require_operational_smoke(_reseal(generic), run_namespace=namespace,
                                  source_commit="abc123")


def test_smoke_that_did_not_start_its_own_display_is_refused(stage1):
    namespace = str(stage1["run_namespace"])
    borrowed = _passing_smoke(namespace)
    borrowed["display"]["started_by_smoke"] = False
    with pytest.raises(EvidenceError, match="did not start its own display"):
        require_operational_smoke(_reseal(borrowed), run_namespace=namespace,
                                  source_commit="abc123")


def test_smoke_without_openbox_is_refused(stage1):
    """D4.13. openbox is part of the production start_display path."""
    namespace = str(stage1["run_namespace"])
    no_openbox = _passing_smoke(namespace)
    no_openbox["openbox"]["started_by_smoke"] = False
    with pytest.raises(EvidenceError, match="did not start openbox"):
        require_operational_smoke(_reseal(no_openbox), run_namespace=namespace,
                                  source_commit="abc123")


def test_stage_evidence_digest_is_computed_over_the_excerpt():
    """The producer and the verifier must agree on how a stage is digested."""
    receipts = _receipts()
    record = receipts.stage_evidence("/some/log", "server ready\n", time.monotonic())
    assert record["excerpt_sha256"] == hashlib.sha256(b"server ready\n").hexdigest()
    assert record["source_path"] == "/some/log"


def test_log_stage_evidence_requires_the_marker(tmp_path):
    """A stage cannot be evidenced from a log that never reported it."""
    receipts = _receipts()
    log = tmp_path / "latest.log"
    log.write_text("[00:00:01] starting\n[00:00:02] still starting\n")
    with pytest.raises(EvidenceError, match="never reported"):
        receipts.log_stage_evidence(log, "server ready", time.monotonic())

    log.write_text("[00:00:01] starting\n[00:00:09] Done (5.1s)! server ready\n")
    record = receipts.log_stage_evidence(log, "server ready", time.monotonic())
    assert "server ready" in record["excerpt"]
    assert record["excerpt_sha256"] == hashlib.sha256(
        record["excerpt"].encode()).hexdigest()


def test_teardown_evidence_refuses_to_certify_a_stranded_process():
    receipts = _receipts()
    launched = [{"pid": 1, "role": "server", "exited": False}]
    with pytest.raises(EvidenceError, match="stranded"):
        receipts.teardown_stage_evidence(launched, [1], time.monotonic())


def test_the_smoke_producer_no_longer_pre_creates_the_display():
    """D4. Structural: the smoke path must not call ensure_display at all."""
    source = (ROOT / "scripts/regime_a_prime_qualification_v0_2/generate_receipts.py").read_text()
    smoke_body = source.split("def operational_startup_smoke(")[1]
    assert "ensure_display(" not in smoke_body
    assert "require_no_pre_existing_display(" in smoke_body
    # runtime-preflight may legitimately keep its generic renderer probe.
    assert "ensure_display(authority)" in source.split("def runtime_preflight(")[1]


# --------------------------------------------- D7 LiveRuntime.send must not hang
#
# Same defect class as D5, on the capture path instead of the teardown path.
# `LiveRuntime.send` opened the command FIFO with a blocking `open(..., "w")`,
# which waits for a reader; the reader is the server JVM. A server that died
# mid-episode therefore hung the capture forever instead of failing it.
#
# Authority decision: a dead server, an unavailable FIFO, or a bounded send
# failure is an OPERATIONAL apparatus failure -- never a scientific one. It must
# abort the attempt, run authoritative cleanup, and emit no unit receipt.


def _live_runtime(tmp_path, monkeypatch, *, server, make_fifo=True):
    """A ``LiveRuntime`` whose FIFO is isolated inside ``tmp_path``.

    Never allowed to reach the real server's command pipe: `FIFO` is redirected
    before the object is built, so a defect here cannot drive a live apparatus.
    """
    live = _campaign()
    fifo = tmp_path / "cmd.fifo"
    if make_fifo:
        os.mkfifo(fifo)
    monkeypatch.setattr(live, "FIFO", fifo)
    return live, live.LiveRuntime(server=server), fifo


def _send_within(runtime, commands, *, wait=10.0, **kwargs):
    """Run ``send`` on a worker and fail the test if it does not return.

    A blocking FIFO open never returns, so "did it finish" is the assertion; the
    superseded implementation hangs here rather than failing. ``wait`` bounds the
    test; any ``kwargs`` (such as ``timeout``) go to ``send`` itself.
    """
    outcome: list[BaseException | None] = []
    finished = threading.Event()

    def run():
        try:
            runtime.send(commands, **kwargs)
            outcome.append(None)
        except BaseException as exc:  # noqa: BLE001 - re-asserted by the caller
            outcome.append(exc)
        finally:
            finished.set()

    threading.Thread(target=run, daemon=True).start()
    assert finished.wait(timeout=wait), "LiveRuntime.send blocked instead of failing"
    return outcome[0]


def test_send_delivers_when_the_server_is_alive_and_reading(tmp_path, monkeypatch):
    """D7.1. The normal path: live server plus an attached reader still works."""
    live, runtime, fifo = _live_runtime(tmp_path, monkeypatch, server=FakeProcess(2))
    received: list[bytes] = []

    def reader():
        with open(fifo, "rb") as stream:
            received.append(stream.read())

    consumer = threading.Thread(target=reader, daemon=True)
    consumer.start()
    time.sleep(0.2)  # let the reader attach so the write side finds it
    assert _send_within(runtime, ["mineocclude mode nowall", "mineocclude reveal 0"]) is None
    consumer.join(timeout=10)
    assert received == [b"mineocclude mode nowall\nmineocclude reveal 0\n"]


def test_dead_server_fails_immediately_rather_than_writing(tmp_path, monkeypatch):
    """D7.2. A server known dead is not even attempted."""
    live, runtime, _ = _live_runtime(
        tmp_path, monkeypatch, server=FakeProcess(2, already_exited=True))
    failure = _send_within(runtime, ["mineocclude reveal 0"])
    assert isinstance(failure, live.OperationalCaptureError)
    assert "server exited" in str(failure)


def test_fifo_with_no_reader_does_not_hang(tmp_path, monkeypatch):
    """D7.3. The exact primitive that hung: a real FIFO nobody is reading.

    The server is reported alive, so the liveness guard cannot short-circuit --
    only the non-blocking open saves this call.
    """
    live, runtime, _ = _live_runtime(tmp_path, monkeypatch, server=FakeProcess(2))
    failure = _send_within(runtime, ["mineocclude reveal 0"])
    assert isinstance(failure, live.OperationalCaptureError)
    assert "no reader is attached" in str(failure)


def test_send_without_a_server_handle_still_refuses_to_block(tmp_path, monkeypatch):
    """D7.3b. The liveness guard is optional; the non-blocking open is not."""
    live, runtime, _ = _live_runtime(tmp_path, monkeypatch, server=None)
    assert isinstance(_send_within(runtime, ["stop"]), live.OperationalCaptureError)


def test_absent_fifo_is_an_operational_failure(tmp_path, monkeypatch):
    """D7.3c. No FIFO at all is the same class of apparatus failure."""
    live, runtime, _ = _live_runtime(
        tmp_path, monkeypatch, server=FakeProcess(2), make_fifo=False)
    failure = _send_within(runtime, ["stop"])
    assert isinstance(failure, live.OperationalCaptureError)
    assert "FIFO is absent" in str(failure)


def test_reader_that_stops_draining_fails_within_the_bound(tmp_path, monkeypatch):
    """D7.4. A reader attached but not consuming must time out, not hang.

    The reader attaches and then stops reading, so the pipe buffer fills and the
    write can never complete. The bound is what turns that into a failure.
    """
    live, runtime, fifo = _live_runtime(tmp_path, monkeypatch, server=FakeProcess(2))
    # Attach a reader so the open succeeds, then never drain it.
    holder = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
    try:
        # Far larger than the pipe buffer, so the write cannot complete.
        oversized = ["x" * 4096] * 512
        started = time.monotonic()
        failure = _send_within(runtime, oversized, wait=10.0, timeout=0.5)
        elapsed = time.monotonic() - started
    finally:
        os.close(holder)
    assert isinstance(failure, live.OperationalCaptureError)
    assert "did not accept" in str(failure)
    assert elapsed < 5.0, f"send exceeded its own bound: {elapsed:.1f}s"


def test_send_failure_is_operational_and_not_a_scientific_outcome(tmp_path, monkeypatch):
    """D7.5/7/8. Classification: apparatus failure, never scientific evidence."""
    live, runtime, _ = _live_runtime(
        tmp_path, monkeypatch, server=FakeProcess(2, already_exited=True))
    failure = _send_within(runtime, ["mineocclude reveal 0"])
    # Carried as a type, so the distinction survives being caught.
    assert isinstance(failure, live.CampaignError)
    assert failure.operational_apparatus_failure is True
    assert failure.reason_code == "OPERATIONAL_APPARATUS_FAILURE"
    # A genuine scientific failure is classified the other way.
    assert live.CampaignError("NO_WALL_MISMATCH", "x").operational_apparatus_failure is False


def test_send_does_not_retry_internally(tmp_path, monkeypatch):
    """D7. Controller retry policy stays authoritative: one attempt per send."""
    live, runtime, fifo = _live_runtime(tmp_path, monkeypatch, server=FakeProcess(2))
    opens: list[int] = []
    real_open = os.open

    def counting_open(path, flags, *args, **kwargs):
        if str(path) == str(fifo):
            opens.append(flags)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", counting_open)
    assert isinstance(_send_within(runtime, ["stop"]), live.OperationalCaptureError)
    assert len(opens) == 1, f"send retried internally: {len(opens)} opens"


def test_a_failed_send_aborts_the_attempt_and_runs_cleanup(tmp_path, monkeypatch):
    """D7.6/7/9/10. The whole contract, end to end through CaptureSession.

    The session holds a dead server, so `send` fails operationally. The failure
    must propagate out of the with-block, authoritative cleanup must still run,
    every launched process must be stopped, and nothing that looks like a
    scientific receipt may be produced.
    """
    session, processes = _capture_session(tmp_path, monkeypatch, server_alive=False)
    live = _campaign()
    os.mkfifo(live.FIFO)
    session.runtime = live.LiveRuntime(server=processes[1])
    unrelated = FakeProcess(99)

    with pytest.raises(live.OperationalCaptureError) as caught:
        try:
            session.runtime.send(["mineocclude reveal 0"])
        finally:
            session.__exit__(None, None, None)

    assert caught.value.operational_apparatus_failure is True
    # 6. Cleanup happened and stranded nothing.
    assert all(process.poll() is not None for process in processes)
    assert session.processes == []
    # 9. Repeated cleanup is safe.
    session.__exit__(None, None, None)
    # 10. Nothing this attempt did not launch was touched.
    assert unrelated.poll() is None
    assert not unrelated.terminated and not unrelated.killed
    # 7. No scientific unit receipt anywhere.
    assert not list(tmp_path.rglob("*receipt*.json"))


def test_the_capture_path_no_longer_opens_the_fifo_blocking():
    """D7. Structural: no blocking FIFO open survives on the runtime path.

    A behavioural test can only cover the paths it exercises; this asserts the
    superseded primitive is gone from the source outright.
    """
    import ast

    path = ROOT / "scripts/run_large_scale_no_wall_campaign.py"
    tree = ast.parse(path.read_text())
    # Parsed, not grepped: the prose explaining the superseded primitive names
    # it, and a text search cannot tell that apart from a live call.
    blocking = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "open" and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "FIFO"
        and any(isinstance(argument, ast.Constant) and argument.value == "w"
                for argument in node.args)
    ]
    assert not blocking, f"blocking FIFO open survives at line(s) {[n.lineno for n in blocking]}"
    assert "os.O_WRONLY | os.O_NONBLOCK" in path.read_text()


# ---------------------------------- D8 session.lock presence is not the lock
#
# `world_session_lock_present` reported the *file*, but Minecraft leaves
# session.lock on disk after a clean shutdown; the server JVM holds a POSIX
# record lock on it. So every world that had ever run reported a stranded
# server, and `require_operational_smoke` refuses any smoke that did -- making a
# passing real smoke impossible regardless of apparatus health.


def _session_lock_probe(tmp_path, monkeypatch):
    """Point the lock probe at an isolated world root and build the lock file."""
    import importlib

    receipts = importlib.import_module(
        "scripts.regime_a_prime_qualification_v0_2.generate_receipts")
    live = _campaign()
    world = tmp_path / "world-c1-v0_2"
    world.mkdir()
    lock = world / "session.lock"
    lock.write_bytes(b"\xe2\x98\x83")  # what Minecraft actually writes
    monkeypatch.setattr(live, "SERVER_ROOT", tmp_path)
    return receipts, lock


def test_a_shutdown_world_does_not_report_a_stranded_server(tmp_path, monkeypatch):
    """D8.1. The defect: a leftover lock file is not a running server."""
    receipts, _ = _session_lock_probe(tmp_path, monkeypatch)
    assert receipts.world_session_lock_present() is False


def test_a_held_session_lock_is_still_detected(tmp_path, monkeypatch):
    """D8.2. The repair must not blind the check it exists to perform.

    The holder must be a *separate* process, as the server JVM is: POSIX record
    locks are owned per-process, so a same-process re-acquire succeeds by
    converting the existing lock and would prove nothing.
    """
    receipts, lock = _session_lock_probe(tmp_path, monkeypatch)
    holder = subprocess.Popen(
        [sys.executable, "-c",
         "import fcntl,sys\n"
         "handle = open(sys.argv[1], 'r+b')\n"
         "fcntl.lockf(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
         "sys.stdout.write('locked\\n'); sys.stdout.flush()\n"
         "sys.stdin.readline()\n",
         str(lock)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "locked"
        assert receipts.world_session_lock_present() is True
    finally:
        holder.stdin.close()
        holder.wait(timeout=10)
    # Released with the holder: the world is free again.
    assert receipts.world_session_lock_present() is False


def test_no_world_at_all_reports_no_lock(tmp_path, monkeypatch):
    """D8.3. An absent world is not a stranded server either."""
    import importlib

    receipts = importlib.import_module(
        "scripts.regime_a_prime_qualification_v0_2.generate_receipts")
    monkeypatch.setattr(_campaign(), "SERVER_ROOT", tmp_path)
    assert receipts.world_session_lock_present() is False


def test_the_probe_leaves_the_lock_free(tmp_path, monkeypatch):
    """D8.4. Probing must not itself strand the world for the next attempt."""
    import fcntl

    receipts, lock = _session_lock_probe(tmp_path, monkeypatch)
    assert receipts.world_session_lock_present() is False
    with lock.open("r+b") as handle:  # must still be acquirable afterwards
        fcntl.lockf(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.lockf(handle, fcntl.LOCK_UN)


# --------------------------- D9 client-join evidence read from the wrong log
#
# The smoke sourced "joined the game" from the CLIENT log, but that is a
# server-side message the client never prints. A completely successful startup
# -- server up, client genuinely joined, recorded as such by the server -- still
# failed the smoke, so no provenance could ever be built on this machine.


def test_client_join_evidence_comes_from_the_log_that_records_the_join():
    """D9. The join marker must be read where it is actually written.

    ``launch_runtime`` blocks on "joined the game" in the *server* log; the
    smoke must conclude the same stage from the same place, or it certifies
    against a file the marker can never appear in.
    """
    source = (ROOT / "scripts/regime_a_prime_qualification_v0_2/generate_receipts.py").read_text()
    body = source.split("def operational_startup_smoke(")[1]
    joined = [line for line in body.splitlines() if '"joined the game"' in line]
    assert joined, "the smoke no longer evidences the client join at all"
    context = body.split('stages["client_joined"]')[1][:400]
    assert "SERVER_ROOT" in context and "CLIENT_ROOT" not in context.split("launched")[0]


def test_the_launch_gate_reads_the_join_from_the_server_log(tmp_path, monkeypatch):
    """D9. Behavioural: ``log_text`` -- what the launch gate tests -- is the server log.

    Pins the fact the repair depends on. If ``log_text`` ever became the client
    log, the smoke would be evidencing the join from the wrong file again.
    """
    live = _campaign()
    server, client = tmp_path / "server", tmp_path / "client"
    (server / "logs").mkdir(parents=True)
    (client / "logs").mkdir(parents=True)
    (server / "logs/latest.log").write_text("C1Observer joined the game\n")
    (client / "logs/latest.log").write_text("Connecting to 127.0.0.1, 25565\n")
    monkeypatch.setattr(live, "SERVER_ROOT", server)
    monkeypatch.setattr(live, "CLIENT_ROOT", client)
    runtime = live.LiveRuntime()
    assert "joined the game" in runtime.log_text()
    assert "joined the game" not in runtime.client_log_text()


# ------------------------ D10 teardown evidence zipped against a cleared list
#
# `CaptureSession.__exit__` hands its process list to the teardown and sets
# `self.processes = []`. The smoke then zipped its `launched` records against
# `session.processes`, which is empty by then, so the loop that marks each
# process exited never ran and a perfectly clean teardown reported all three
# processes stranded. `zip` truncates silently, so nothing raised.


def test_exit_clears_the_session_process_list(tmp_path, monkeypatch):
    """D10. The property the smoke's teardown evidence must not depend on."""
    session, processes = _capture_session(tmp_path, monkeypatch, server_alive=False)
    assert session.processes, "precondition: the session starts holding processes"
    session.__exit__(None, None, None)
    assert session.processes == []
    # The processes themselves really did stop; only the attribute was cleared.
    assert all(process.poll() is not None for process in processes)


def test_teardown_evidence_survives_the_cleared_process_list(tmp_path, monkeypatch):
    """D10. Held handles, not session.processes, must drive the exited flags."""
    session, processes = _capture_session(tmp_path, monkeypatch, server_alive=True)
    handles = list(session.processes)  # what the repaired smoke keeps
    launched = [{"pid": process.pid, "role": role, "exited": False}
                for role, process in zip(("display", "server", "client"), handles)]
    session.__exit__(None, None, None)

    # The superseded expression: silently empty, so nothing is marked exited.
    stale = list(zip(launched, session.processes))
    assert stale == []

    for record, process in zip(launched, handles):
        record["exited"] = process.poll() is not None
    assert [record["exited"] for record in launched] == [True, True, True]
    assert [record["pid"] for record in launched if not record["exited"]] == []


def test_the_smoke_does_not_read_session_processes_after_teardown():
    """D10. Structural: the post-teardown poll must not use the cleared list."""
    source = (ROOT / "scripts/regime_a_prime_qualification_v0_2/generate_receipts.py").read_text()
    body = source.split("def operational_startup_smoke(")[1]
    after = body.split("# After __exit__")[1][:300]
    assert "session.processes" not in after, "teardown evidence reads the cleared list"
    assert "handles" in after


# ------------------------------------------------------- server seed contract
#
# The defect that blocked Stage-1 attempt 02 on every unit:
#
#   REFUSED: noise schedule ... is invalid: schedule seed 1239302675008784277
#   does not match the episode seed 3901999841581120224
#
# The generator minted `seed` and `noise_seed` from two different labels, Python
# generated the schedule from `noise_seed`, and `startspec` carried `seed`. The
# server requires them to be one value, and so does every historical manifest.


def test_all_eight_stage1_units_satisfy_the_server_seed_contract(stage1):
    """The blocking condition, asserted directly on the frozen fixture."""
    assert len(stage1["units"]) == 8
    for unit in stage1["units"]:
        assert unit["seed"] == unit["noise_seed"], unit["unit_id"]


def test_stage1_units_still_carry_distinct_seeds(stage1):
    """Collapsing the two fields must not collapse units into each other."""
    seeds = [unit["seed"] for unit in stage1["units"]]
    assert len(set(seeds)) == len(seeds)


def test_every_stage2_identity_satisfies_the_server_seed_contract():
    """Stage-2 was minted by the same defective generator, so it is checked too."""
    stage2 = load_json(PACKAGE / "stage2_locked_manifest.json")
    identities = stage2["trajectory_identities"]
    assert len(identities) == 25
    for identity in identities:
        assert identity["seed"] == identity["noise_seed"], identity["trajectory_id"]
    for unit in stage2["capture_units"]:
        assert unit["seed"] == unit["noise_seed"], unit["unit_id"]


def test_historical_capturing_manifests_carry_one_seed_identity():
    """The authority for the contract: every spec that ever captured obeys it.

    This is what proves the repair restores predeclared semantics rather than
    inventing a convenient new rule -- all 25 Regime A v2.1 amendment-1 specs,
    which produced the real historical wall corpus, carry seed == noise_seed.
    """
    import json

    manifest = (ROOT / "docs/status/integration/regime_a_occlusion_extraction_v0_1"
                / "v2_amendment_1/trajectory_manifest_v2_1_amendment_1.jsonl")
    rows = [json.loads(line) for line in manifest.read_text().splitlines() if line.strip()]
    assert len(rows) == 25
    for row in rows:
        assert row["seed"] == row["noise_seed"], row["trajectory_spec_id"]


def test_effective_capture_spec_preserves_the_seed_identity(first_spec):
    require_server_seed_contract(first_spec)
    assert first_spec["seed"] == first_spec["noise_seed"]


def test_mismatched_seed_is_refused_before_authorization(first_spec):
    """The exact shape of the blocked attempt, refused statically."""
    broken = deepcopy(first_spec)
    broken["seed"] = broken["noise_seed"] + 1
    with pytest.raises(EvidenceError, match="server seed contract"):
        require_server_seed_contract(broken)
    with pytest.raises(EvidenceError, match="server seed contract"):
        require_capture_spec_contract(broken)


def test_preflight_refuses_a_manifest_with_a_seed_break(stage1, authority):
    """The gate that runs over all 8 units before a JVM starts."""
    broken = deepcopy(stage1)
    broken["units"][3]["noise_seed"] = broken["units"][3]["seed"] + 7
    with pytest.raises(EvidenceError, match="server seed contract"):
        capture_contract_preflight(broken, authority)


@pytest.mark.parametrize("value", ["12345", 12.5, -1, True, None])
def test_non_integer_seed_is_refused(first_spec, value):
    broken = deepcopy(first_spec)
    broken["seed"] = value
    with pytest.raises(EvidenceError, match="non-negative integer seed"):
        require_server_seed_contract(broken)


def test_the_generator_mints_one_seed_per_unit():
    """The repair lives in the generator, not only in the emitted bytes."""
    source = (ROOT / "scripts/regime_a_prime_qualification_v0_2/build_manifests.py").read_text()
    assert 'seed(unit_id + ":noise")' not in source
    assert 'seed(trajectory_id + ":noise")' not in source
    assert '"seed": identity_seed, "noise_seed": identity_seed' in source or (
        '"seed": identity_seed,' in source and '"noise_seed": identity_seed,' in source)


def test_regenerating_the_manifests_is_a_fixed_point(stage1):
    """The frozen bytes are what the repaired generator produces.

    Guards the case where the manifest was hand-corrected but the generator was
    not, which would silently reintroduce the break on the next rebuild.
    """
    import json

    result = subprocess.run(
        [sys.executable,
         str(ROOT / "scripts/regime_a_prime_qualification_v0_2/build_manifests.py")],
        capture_output=True, text=True, cwd=str(ROOT), check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(STAGE1_PATH.read_text()) == stage1


def test_the_startspec_line_is_built_once(first_spec):
    """Production capture and the preflight must send the same bytes.

    A preflight that assembled its own copy of the startspec line could pass
    while production sent a different one -- which is how a seed break survives
    a green prelaunch. Both call ``startspec_command``.
    """
    sys.path.insert(0, str(ROOT / "scripts/regime_a_prime_qualification_v0_1"))
    import p2_common

    line = p2_common.startspec_command(first_spec, 81001, 180)
    assert line.split()[3] == "81001"
    assert line.split()[4] == str(first_spec["seed"])
    assert line.split()[4] == str(first_spec["noise_seed"])

    source = (ROOT / "scripts/regime_a_prime_qualification_v0_1/p2_common.py").read_text()
    capture_body = source.split("def capture(")[1].split("def ")[0]
    assert "startspec_command(" in capture_body
    assert "mineocclude startspec layout_01" not in capture_body


def test_generated_schedule_header_seed_matches_the_startspec_seed(first_spec):
    """The two ends of the contract, on the real bytes the apparatus consumes."""
    import json

    sys.path.insert(0, str(ROOT / "scripts/regime_a_prime_qualification_v0_1"))
    sys.path.insert(0, str(ROOT / "src"))
    from mineocclude.data.noise_schedule import generate_noise_schedule, serialize_schedule

    schedule = generate_noise_schedule(int(first_spec["noise_seed"]),
                                       int(first_spec["expected_max_frames"]),
                                       float(first_spec["motion_noise_q"]))
    header = json.loads(serialize_schedule(schedule).decode().splitlines()[0])
    # This equality is precisely what NoiseSchedule.load(path, cfg.seed) checks.
    assert header["seed"] == int(first_spec["seed"])


# --------------------------------------------------- startspec handshake gate
#
# Part 5: the prelaunch control must issue a real startspec, so a seed mismatch
# cannot again survive until scientific collection.


def test_the_smoke_requires_an_arming_stage():
    stages = dict(OPERATIONAL_SMOKE_STAGES)
    assert stages["episode_armed"] == "rng=immutable_numpy_schedule"


def test_a_genuine_handshake_is_accepted(stage1):
    namespace = str(stage1["run_namespace"])
    require_operational_smoke(_passing_smoke(namespace), run_namespace=namespace,
                              source_commit="abc123", closure_sha256="c" * 64)


def test_a_smoke_without_a_handshake_is_refused(stage1):
    """The v0.2 smoke that let this defect through: it never issued a startspec."""
    namespace = str(stage1["run_namespace"])
    old = _passing_smoke(namespace)
    old.pop("startspec_handshake")
    with pytest.raises(EvidenceError, match="no startspec handshake"):
        require_operational_smoke(_reseal(old), run_namespace=namespace,
                                  source_commit="abc123")


def test_handshake_with_a_seed_mismatch_is_refused():
    """Attempt 02's exact condition must fail the preflight closed."""
    with pytest.raises(EvidenceError, match="seeds disagree"):
        require_startspec_handshake(
            {"startspec_handshake": _handshake(noise_seed=_SMOKE_SEED + 1)})
    with pytest.raises(EvidenceError, match="seeds disagree"):
        require_startspec_handshake(
            {"startspec_handshake": _handshake(schedule_seed_header=_SMOKE_SEED + 1)})


def test_handshake_that_never_armed_is_refused():
    refused = _handshake(
        armed=False, armed_log_line=None, rng_source=None,
        refusal=("REFUSED: noise schedule is invalid: schedule seed 123 "
                 "does not match the episode seed 456"))
    with pytest.raises(EvidenceError, match="did not arm"):
        require_startspec_handshake({"startspec_handshake": refused})


def test_handshake_on_the_nonscientific_fallback_is_refused():
    """Arming without a schedule at all is not a crossed contract."""
    fallback_line = _ARMED_LINE.replace("immutable_numpy_schedule",
                                        "java_util_random_nonscientific")
    fallback = _handshake(rng_source="java_util_random_nonscientific",
                          armed_log_line=fallback_line)
    with pytest.raises(EvidenceError, match="immutable schedule"):
        require_startspec_handshake({"startspec_handshake": fallback})


def test_handshake_naming_a_seed_the_apparatus_did_not_arm_is_refused():
    """The arming line is the server's word; the record must agree with it."""
    lying = _handshake(armed_log_line=_ARMED_LINE.replace(str(_SMOKE_SEED), "999"))
    with pytest.raises(EvidenceError, match="arming line does not carry the declared seed"):
        require_startspec_handshake({"startspec_handshake": lying})


def test_handshake_command_must_carry_the_declared_identity():
    borrowed = _handshake(
        startspec_command=_STARTSPEC_COMMAND.replace(str(_SMOKE_SEED), "424242"))
    with pytest.raises(EvidenceError, match="does not carry the declared episode and seed"):
        require_startspec_handshake({"startspec_handshake": borrowed})

    other_episode = _handshake(startspec_command=_STARTSPEC_COMMAND.replace("990001", "81001"))
    with pytest.raises(EvidenceError, match="does not carry the declared episode and seed"):
        require_startspec_handshake({"startspec_handshake": other_episode})


@pytest.mark.parametrize("field, value", [("recording_started", True),
                                          ("frames_written", 1)])
def test_a_handshake_that_captured_is_refused(field, value):
    """A preflight that ran on into recording is a capture, not a smoke."""
    captured = _handshake(**{field: value})
    with pytest.raises(EvidenceError):
        require_startspec_handshake({"startspec_handshake": captured})


def test_handshake_schema_is_pinned():
    with pytest.raises(EvidenceError, match="handshake is not"):
        require_startspec_handshake(
            {"startspec_handshake": _handshake(schema="mineocclude-handshake-v0.0")})


def test_the_smoke_runner_arms_and_never_captures():
    """The runner must reach the server, and must stop before the first frame."""
    source = (ROOT / "scripts/regime_a_prime_qualification_v0_2/generate_receipts.py").read_text()
    body = source.split("def operational_startup_smoke(")[1]
    assert "session.arm_only(" in body
    assert "startspec_handshake" in body
    assert 'stages["episode_armed"]' in body
    assert "session.capture(" not in body

    capture_source = (ROOT / "scripts/regime_a_prime_qualification_v0_1"
                      / "p2_common.py").read_text()
    arm_body = capture_source.split("def arm_only(")[1].split("\n    def ")[0]
    # Warmup, not a race, is what keeps the frame count at zero.
    assert "ARM_ONLY_WARMUP_TICKS" in arm_body
    assert "mineocclude stop" in arm_body
    # It must never reach the recording waits the scientific capture path uses.
    assert "recording started" not in arm_body.split("recording_started")[0]
    assert "capture_complete.json" not in arm_body
    assert "shutil.copytree" not in arm_body


def test_arm_only_is_classified_non_scientific():
    capture_source = (ROOT / "scripts/regime_a_prime_qualification_v0_1"
                      / "p2_common.py").read_text()
    arm_doc = capture_source.split("def arm_only(")[1].split('"""')[1]
    assert "NON-SCIENTIFIC" in arm_doc


# ------------------------------------------------------- adversarial handshake
#
# Part 6. Each case is built from the REAL frozen fixture and the REAL
# materialized schedule bytes, then put to the rule the apparatus applies, so a
# passing case here is the legitimate configuration and nothing else.

_MOD = ROOT / "fabric/mineocclude-mod/src/main/java/com/mineocclude/server"


def _materialize(spec):
    """The schedule bytes the capture path writes, and the header the server reads."""
    import json

    sys.path.insert(0, str(ROOT / "src"))
    from mineocclude.data.noise_schedule import generate_noise_schedule, serialize_schedule

    schedule = generate_noise_schedule(int(spec["noise_seed"]),
                                       int(spec["expected_max_frames"]),
                                       float(spec["motion_noise_q"]))
    payload = serialize_schedule(schedule)
    return payload, json.loads(payload.decode().splitlines()[0])


def _server_accepts(schedule_header, startspec_seed) -> bool:
    """The server's rule, verbatim: NoiseSchedule.java

        long seed = header.get("seed").getAsLong();
        if (seed != expectedSeed) { throw new IOException(...); }

    where expectedSeed is cfg.seed -- the seed the startspec line carried.
    """
    return int(schedule_header["seed"]) == int(startspec_seed)


def test_the_server_rule_this_suite_models_still_exists():
    """Drift guard: if the server rule changes, these cases stop meaning anything."""
    source = (_MOD / "NoiseSchedule.java").read_text()
    assert "if (seed != expectedSeed)" in source
    assert "does not match the episode seed" in source
    manager = (_MOD / "EpisodeManager.java").read_text()
    assert "NoiseSchedule.load(schedulePath, config.seed)" in manager


def test_the_legitimate_eight_unit_fixture_passes_the_handshake(stage1, authority):
    """The positive case: all 8 frozen units arm. No frames involved."""
    for unit in stage1["units"]:
        spec = derive_effective_capture_spec(unit, authority)
        require_capture_spec_contract(spec)
        _, header = _materialize(spec)
        assert _server_accepts(header, spec["seed"]), unit["unit_id"]


def test_schedule_generated_with_the_wrong_noise_seed_is_refused(first_spec):
    wrong = deepcopy(first_spec)
    wrong["noise_seed"] = int(wrong["noise_seed"]) ^ 0xDEAD
    _, header = _materialize(wrong)
    assert not _server_accepts(header, first_spec["seed"])
    with pytest.raises(EvidenceError, match="server seed contract"):
        require_capture_spec_contract(wrong)


def test_startspec_given_the_wrong_seed_identity_is_refused(first_spec):
    _, header = _materialize(first_spec)
    assert not _server_accepts(header, int(first_spec["seed"]) + 1)


def test_a_schedule_copied_from_another_unit_is_refused(stage1, authority):
    """Unit A armed with unit B's schedule: the header seed betrays it."""
    first = derive_effective_capture_spec(stage1["units"][0], authority)
    second = derive_effective_capture_spec(stage1["units"][1], authority)
    _, borrowed = _materialize(second)
    assert not _server_accepts(borrowed, first["seed"])


def test_a_stale_pre_repair_schedule_is_refused(first_spec):
    """The schedule the blocked attempt actually wrote.

    Attempt 02 generated from the old distinct noise_seed while startspec carried
    the old distinct seed. Reconstructed here from the blocked attempt's own
    numbers, it must still be refused.
    """
    blocked_noise_seed = 1239302675008784277
    blocked_episode_seed = 3901999841581120224
    assert blocked_noise_seed != blocked_episode_seed
    stale = deepcopy(first_spec)
    stale["noise_seed"] = blocked_noise_seed
    _, header = _materialize(stale)
    assert not _server_accepts(header, blocked_episode_seed)
    # And the repaired fixture no longer produces that pairing.
    assert int(first_spec["seed"]) == int(first_spec["noise_seed"])


def test_a_schedule_written_for_another_episode_is_not_found(stage1, authority):
    """Episode identity is carried by the schedule path, not only its bytes.

    EpisodeManager resolves mineocclude_schedules/episode_<id>.jsonl. A schedule
    filed under the wrong episode is simply absent for the armed one, and the
    server then arms on the NON-SCIENTIFIC java.util.Random fallback -- which the
    handshake gate refuses by rng source.
    """
    manager = (_MOD / "EpisodeManager.java").read_text()
    assert 'resolve("episode_" + config.episodeId + ".jsonl")' in manager
    assert "NON-SCIENTIFIC java.util.Random fallback" in manager

    first = derive_effective_capture_spec(stage1["units"][0], authority)
    second = derive_effective_capture_spec(stage1["units"][1], authority)
    assert int(first["episode_id"]) != int(second["episode_id"])

    fallback_line = _ARMED_LINE.replace("immutable_numpy_schedule",
                                        "java_util_random_nonscientific")
    with pytest.raises(EvidenceError, match="immutable schedule"):
        require_startspec_handshake({"startspec_handshake": _handshake(
            rng_source="java_util_random_nonscientific", armed_log_line=fallback_line)})


def test_a_wrong_episode_id_on_the_startspec_line_is_refused():
    mismatched = _handshake(episode_id=81001)
    with pytest.raises(EvidenceError, match="does not carry the declared episode and seed"):
        require_startspec_handshake({"startspec_handshake": mismatched})


def test_a_wrong_spec_hash_is_refused(first_spec):
    """Refused in Python before launch, and by MotionSchedule.load at the server."""
    forged = deepcopy(first_spec)
    forged["spec_hash"] = "f" * 64
    with pytest.raises(EvidenceError, match="spec_hash is not derived"):
        require_capture_spec_contract(forged)
    motion = (_MOD / "MotionSchedule.java").read_text()
    assert "motion schedule spec identity mismatch" in motion


def test_a_wrong_raw_capture_spec_hash_is_refused(first_spec):
    forged = deepcopy(first_spec)
    forged["raw_capture_spec_hash"] = "e" * 64
    with pytest.raises(EvidenceError, match="raw_capture_spec_hash"):
        require_capture_spec_contract(forged)


def test_no_adversarial_case_here_captures_a_frame():
    """This suite reasons over bytes and rules; it never starts the apparatus."""
    source = Path(__file__).read_text()
    section = source.split("# ------------------------------------------------------- adversarial")[1]
    for forbidden in ("CaptureSession(", "session.capture(", "arm_only(", "launch_runtime"):
        assert forbidden not in section, forbidden


def test_manifest_validation_refuses_a_seed_break(stage1, authority):
    """Third gate: a manifest the apparatus could never arm is structurally invalid.

    ``_validate_manifest_design`` runs before any Stage-1 evidence is scored, so
    a manifest carrying the break is refused at its structure rather than only
    when a capture spec is derived from it.
    """
    from mineocclude.prospective.development_workflow import Stage1Evaluator

    broken = deepcopy(stage1)
    broken["units"][0]["noise_seed"] = broken["units"][0]["seed"] + 1
    authority_sha = stage1["authority_binding"]["sha256"]
    evaluator = Stage1Evaluator(authority, broken,
                                authority_sha256=authority_sha, manifest_sha256="b" * 64)
    with pytest.raises(EvidenceError, match="server seed contract"):
        evaluator._validate_manifest_design()

    # The repaired manifest passes the same call.
    Stage1Evaluator(authority, stage1, authority_sha256=authority_sha,
                    manifest_sha256="b" * 64)._validate_manifest_design()

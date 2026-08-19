#!/usr/bin/env python3
"""Regression suite for the Stage-2 Part-2 execution repairs: C1 and C2.

Two defects, both of which would have stopped the real 50-unit scientific
extraction on its first unit, and neither of which any existing test could see:

**C1** -- the canonical scientific extraction path built ``Layer4Extractor()`` and
called ``extract()`` in one expression, never calling ``ensure_loaded()``.
``__init__`` binds bookkeeping only, so ``extract()`` died on
``AttributeError: 'Layer4Extractor' object has no attribute 'production'``. The
operational processability probe survived only because it uses a *different*
construction sequence that does call ``ensure_loaded()``.

**C2** -- the physical-gate PASS receipt was admitted by
``require_durable_unit_receipt``, whose contract is derived units and which
therefore requires ``source_commit_sha == the processing commit``. Repairing C1
creates a successor processing commit, so the 2h21m 50/50 durable PASS produced
under ``76098ae`` was refused. That is the source-homogeneity proxy that
``OPTION_3`` removed on the capture side, surviving on the derived side.

Each class opens with the original failure, proves the repair, and then proves
the repair did not weaken the control it replaced -- which matters most here,
because both sit on fail-closed paths where "make it stop raising" is the wrong
fix.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src"),
                str(ROOT / "scripts/regime_a_prime_qualification_v0_1"),
                str(ROOT / "scripts/regime_a_prime_qualification_v0_2")]

from mineocclude.prospective import capture_closure as cc  # noqa: E402
from mineocclude.prospective import physical_gate_admission as pga  # noqa: E402
from mineocclude.prospective.package_binding import package_directory  # noqa: E402
from p2d_extract import ExtractorNotLoadedError, Layer4Extractor  # noqa: E402

PACKAGE = package_directory("v0.4", ROOT)
MANIFEST_PATH = PACKAGE / "stage2_locked_manifest.json"
GATE_RECEIPT = Path("/mnt/sagemaker-nvme/regime_a_prime_a2y_v0_4/receipts/physical_gates.json")

#: The freeze that produced the canonical physical-gate PASS.
PHYSICAL_GATE_COMMIT = "76098ae8f4dcb9103ad8661cc0e0408de06d627a"
#: The frozen capture apparatus. Neither repair may move it.
CAPTURE_CRITICAL_CLOSURE = "b64bc70071d2efbbd90e04ca31f4fdaf508498eb51e36c69b584c3602284fa68"

requires_gate = pytest.mark.skipif(
    not GATE_RECEIPT.is_file(), reason="the campaign physical-gate receipt is not on this host")


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_bytes())


@pytest.fixture(scope="module")
def gate() -> dict:
    return json.loads(GATE_RECEIPT.read_bytes())


# ======================================================================
# C1 -- the extractor initialization contract
# ======================================================================

class TestExtractorInitializationContract:
    """The precondition C1 violated, stated as behaviour rather than as a comment."""

    def test_construction_binds_nothing_but_bookkeeping(self):
        """This is WHY the one-expression call site could never have worked."""
        extractor = Layer4Extractor()
        assert extractor.production is None
        assert extractor.adapter is None
        assert extractor.runtime is None
        assert extractor.load_count == 0

    def test_extract_on_an_unloaded_extractor_refuses_by_name(self):
        """The original failure was a bare AttributeError from mid-method."""
        with pytest.raises(ExtractorNotLoadedError) as raised:
            Layer4Extractor().extract(
                "a2y_t01_wall", Path("/nonexistent"), Path("/nonexistent"),
                expected_target_model_frame_indices=[1],
                scientific_trajectory_id="a2y_t01",
                expected_legacy_capture_trajectory_id="layout_01_ep86001")
        assert "ensure_loaded" in str(raised.value)

    def test_it_refuses_before_touching_the_filesystem(self):
        """Fail-closed placement: no capture byte is read and no activation path is
        opened, so a mis-sequenced caller cannot leave a partial artifact behind.
        The source path above does not exist -- a FileNotFoundError here would mean
        the guard sits after the first read."""
        with pytest.raises(ExtractorNotLoadedError):
            Layer4Extractor().extract(
                "a2y_t01_wall", Path("/nonexistent"), Path("/nonexistent"),
                expected_target_model_frame_indices=[1],
                scientific_trajectory_id="a2y_t01",
                expected_legacy_capture_trajectory_id="layout_01_ep86001")

    @pytest.mark.parametrize("bound", ["production", "adapter", "runtime"])
    def test_a_partially_bound_extractor_is_refused(self, bound):
        """Half-initialised is not initialised: binding one field does not open it."""
        extractor = Layer4Extractor()
        setattr(extractor, bound, object())
        with pytest.raises(ExtractorNotLoadedError):
            extractor.extract("u", Path("/nonexistent"), Path("/nonexistent"),
                              expected_target_model_frame_indices=[1],
                              scientific_trajectory_id="a",
                              expected_legacy_capture_trajectory_id="b")

    def test_extract_does_not_load_the_checkpoint_itself(self):
        """The guard must not be 'repaired' into a lazy load.

        A lazy ``ensure_loaded()`` inside ``extract()`` would make every caller
        work, including one that never established an authorized runtime, and the
        explicit load step is what makes checkpoint acquisition auditable.
        """
        source = (ROOT / "scripts/regime_a_prime_qualification_v0_1/p2d_extract.py").read_text()
        body = source.split("def extract(", 1)[1].split("\n    def ", 1)[0]
        assert "self.ensure_loaded()" not in body


# ======================================================================
# C1 -- the real production construction sequence
# ======================================================================

class TestScientificExtractionPathInitialisesTheExtractor:
    """Drives the REAL ``stage2_backend.extraction`` and inspects the extractor it
    hands to ``extract()``.

    Only governance and durability are stubbed; the construction sequence under
    test is the production one. A mock extractor_factory would have hidden C1
    exactly as the operational probe's factory did, so the factory here is the real
    ``Layer4Extractor`` class with only its model load replaced.
    """

    @pytest.fixture
    def harness(self, monkeypatch, manifest):
        import stage2_backend as backend

        observed: dict = {}
        loaded: list[str] = []

        class StubbedLoad(Layer4Extractor):
            """The real class, the real guard, a cheap ``ensure_loaded``."""

            def ensure_loaded(self) -> None:
                loaded.append("ensure_loaded")
                self.production = object()
                self.adapter = object()
                self.runtime = {"main_checkpoint_sha256": "0" * 64}
                self.load_count += 1

            def extract(self, run_id, source, destination, **kwargs):
                observed["bindings"] = {
                    "production": self.production is not None,
                    "adapter": self.adapter is not None,
                    "runtime": self.runtime is not None}
                observed["run_id"] = run_id
                observed["kwargs"] = kwargs
                raise _Reached

        unit = manifest["capture_units"][0]
        monkeypatch.setattr(backend, "Layer4Extractor", StubbedLoad)
        monkeypatch.setattr(backend, "campaign_commit", lambda: "a" * 40)
        monkeypatch.setattr(backend, "capture_receipt", lambda *_a, **_k: {})
        monkeypatch.setattr(backend, "backend_capture_admission", lambda *_a, **_k: object())
        monkeypatch.setattr(backend, "backend_physical_gate_admission",
                            lambda *_a, **_k: {"admission_regime": "HISTORICAL_ADMITTED"})
        monkeypatch.setattr(backend, "validate_physical_gate_receipts",
                            lambda *_a, **_k: {"status": "PASS"})
        monkeypatch.setattr(backend, "require_admitted_capture_receipt",
                            lambda *_a, **_k: {"capture_source_commit": "b" * 40})
        monkeypatch.setattr(backend, "verify_local_capture_inventory",
                            lambda *_a, **_k: Path("/nonexistent"))
        monkeypatch.setattr(backend, "load_json", _passthrough_load_json(backend, manifest))
        monkeypatch.setattr(backend, "receipt_path", lambda: Path("/tmp/a/b/c/receipt.json"))
        return backend, observed, loaded, unit

    def test_the_extractor_is_loaded_before_extract_is_reached(self, harness, manifest):
        """The C1 assertion. On the predecessor this records all three unbound."""
        backend, observed, loaded, _unit = harness
        extraction_unit = manifest["extraction_units"][0]
        with pytest.raises(_Reached):
            backend.extraction(manifest, MANIFEST_PATH, extraction_unit["unit_id"])
        assert loaded == ["ensure_loaded"], "ensure_loaded() was not called before extract()"
        assert observed["bindings"] == {"production": True, "adapter": True, "runtime": True}

    def test_the_authority_bound_rows_still_reach_the_extractor(self, harness, manifest):
        """The repair reordered construction; it must not have changed the call."""
        backend, observed, _loaded, _unit = harness
        extraction_unit = manifest["extraction_units"][0]
        with pytest.raises(_Reached):
            backend.extraction(manifest, MANIFEST_PATH, extraction_unit["unit_id"])
        kwargs = observed["kwargs"]
        assert set(kwargs) == {"expected_target_model_frame_indices",
                               "scientific_trajectory_id",
                               "expected_legacy_capture_trajectory_id"}
        assert len(kwargs["expected_target_model_frame_indices"]) == 19

    def test_a_failing_model_load_fails_the_unit_closed(self, monkeypatch, manifest):
        """Initialization that cannot succeed must stop the unit, not skip the load
        and proceed to produce an activation from an unbound runtime."""
        import stage2_backend as backend

        class Unloadable(Layer4Extractor):
            def ensure_loaded(self) -> None:
                raise RuntimeError("checkpoint unavailable")

        monkeypatch.setattr(backend, "Layer4Extractor", Unloadable)
        monkeypatch.setattr(backend, "campaign_commit", lambda: "a" * 40)
        monkeypatch.setattr(backend, "capture_receipt", lambda *_a, **_k: {})
        monkeypatch.setattr(backend, "backend_capture_admission", lambda *_a, **_k: object())
        monkeypatch.setattr(backend, "backend_physical_gate_admission", lambda *_a, **_k: {})
        monkeypatch.setattr(backend, "validate_physical_gate_receipts",
                            lambda *_a, **_k: {"status": "PASS"})
        monkeypatch.setattr(backend, "require_admitted_capture_receipt",
                            lambda *_a, **_k: {"capture_source_commit": "b" * 40})
        monkeypatch.setattr(backend, "verify_local_capture_inventory",
                            lambda *_a, **_k: Path("/nonexistent"))
        monkeypatch.setattr(backend, "load_json", _passthrough_load_json(backend, manifest))
        monkeypatch.setattr(backend, "receipt_path", lambda: Path("/tmp/a/b/c/receipt.json"))
        completed: list = []
        monkeypatch.setattr(backend, "complete", lambda *a, **k: completed.append(a))
        with pytest.raises(RuntimeError, match="checkpoint unavailable"):
            backend.extraction(manifest, MANIFEST_PATH, manifest["extraction_units"][0]["unit_id"])
        assert completed == [], "a unit whose model never loaded was recorded complete"

    def test_the_predecessor_construction_sequence_is_fatal(self):
        """What the predecessor call site literally did, run against the real class.

        This is the proof that the test above discriminates: the exact expression
        the superseded backend used raises, so a regression to it cannot pass.
        """
        with pytest.raises(ExtractorNotLoadedError):
            Layer4Extractor().extract(
                "a2y_t01_wall", Path("/nonexistent"), Path("/nonexistent"),
                expected_target_model_frame_indices=[1],
                scientific_trajectory_id="a2y_t01",
                expected_legacy_capture_trajectory_id="layout_01_ep86001")

    def test_every_extractor_construction_site_loads_before_extracting(self):
        """C1 was one call site; this refuses the next one.

        Any construction of ``Layer4Extractor`` in first-party source must have an
        ``ensure_loaded`` within its own function, so a new scientific entrypoint
        cannot reintroduce the defect somewhere this suite does not look.
        """
        import ast

        offenders = []
        for path in sorted(ROOT.glob("scripts/**/*.py")) + sorted(ROOT.glob("src/**/*.py")):
            try:
                tree = ast.parse(path.read_text())
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)):
                    continue
                text = ast.dump(node)
                if "'Layer4Extractor'" in text and "ensure_loaded" not in text:
                    offenders.append(f"{path.relative_to(ROOT)}::{getattr(node, 'name', '<module>')}")
        # Enclosing scopes legitimately contain a construction in a nested function.
        offenders = [o for o in offenders if not o.endswith("<module>")]
        assert offenders == [], f"Layer4Extractor built without ensure_loaded in: {offenders}"


class _Reached(Exception):
    """Sentinel: ``extract()`` was reached; stop before the model would run."""


def _passthrough_load_json(backend, manifest):
    real = backend.load_json

    def load_json(path):
        path = Path(path)
        if not path.is_file():
            return {"physical_gates": {"status": "PASS"}}
        return real(path)
    return load_json


# ======================================================================
# C2 -- historical physical-gate admission
# ======================================================================

class TestGateCriticalClosure:
    """What makes admitting the historical gate sound, rather than merely convenient."""

    def test_the_walk_reproduces_the_capture_critical_closure_exactly(self):
        """The reseeded walk is the capture_closure algorithm, seeded differently.

        Proving it reproduces ``b64bc700`` component-for-component when seeded at the
        capture entrypoints is what keeps the local copy honest: a divergence between
        the two implementations fails here rather than silently producing a gate
        closure that means something slightly different.
        """
        reseeded, components = pga.gate_critical_closure_at(
            cc.worktree_reader(ROOT), repository=ROOT, entrypoints=cc.CAPTURE_ENTRYPOINTS)
        native, native_components = cc.capture_critical_closure_at(
            cc.worktree_reader(ROOT), repository=ROOT)
        assert reseeded == native == CAPTURE_CRITICAL_CLOSURE
        assert components == native_components

    def test_the_gate_closure_is_equal_at_the_gate_commit_and_this_source(self):
        """The load-bearing admission condition, re-derived rather than asserted."""
        historical, historical_components = pga.gate_critical_closure_at(
            PHYSICAL_GATE_COMMIT, repository=ROOT)
        current, current_components = pga.gate_critical_closure_at(
            cc.worktree_reader(ROOT), repository=ROOT)
        differing = [key for key in set(historical_components) | set(current_components)
                     if historical_components.get(key) != current_components.get(key)]
        assert differing == [], f"gate-determining definitions moved: {differing}"
        assert historical == current

    def test_the_repaired_files_are_not_gate_determining(self):
        """Why the equality above holds: neither C1 file can change the verdict."""
        _digest, components = pga.gate_critical_closure_at(cc.worktree_reader(ROOT), repository=ROOT)
        assert [key for key in components if "p2d_extract" in key] == []
        assert "scripts/regime_a_prime_qualification_v0_2/stage2_backend.py::extraction" \
            not in components

    def test_the_capture_apparatus_did_not_move(self):
        """Neither repair may change what the camera recorded."""
        digest, _ = cc.capture_critical_closure_at(cc.worktree_reader(ROOT), repository=ROOT)
        assert digest == CAPTURE_CRITICAL_CLOSURE


@requires_gate
class TestHistoricalPhysicalGateAdmission:
    """The real, immutable receipt -- never mutated on disk, only in copies."""

    SUCCESSOR = "a" * 40

    @pytest.fixture
    def admit(self, manifest):
        import stage2_backend as backend

        context = backend.backend_capture_admission(
            manifest, MANIFEST_PATH, current_source_commit=self.SUCCESSOR)

        def run(receipt, *, commit=self.SUCCESSOR, durable=lambda *_: True):
            return backend.backend_physical_gate_admission(
                manifest, MANIFEST_PATH, receipt, capture_admission=context,
                current_source_commit=commit, durable_verifier=durable)
        return run

    def test_the_historical_pass_is_admitted_by_a_successor(self, admit, gate):
        """The C2 assertion: no replay of the 2h21m gate to repair an extractor."""
        record = admit(gate)
        assert record["admission_regime"] == "HISTORICAL_ADMITTED"
        assert record["gate_source_commit"] == PHYSICAL_GATE_COMMIT
        assert record["gate_result"] == "PASS"
        assert record["capture_units"] == 50
        assert record["paired_trajectories"] == 25

    def test_the_same_freeze_case_still_works(self, admit, gate):
        """The repair must not have turned the ordinary path into the exotic one."""
        assert admit(gate, commit=PHYSICAL_GATE_COMMIT)["admission_regime"] == "SAME_FREEZE"

    def test_the_receipt_on_disk_is_never_written(self, gate):
        """Admission is a read. The canonical receipt keeps its bytes."""
        import hashlib
        assert hashlib.sha256(GATE_RECEIPT.read_bytes()).hexdigest() == (
            "639f37d129f30e1dddc13e343052e0fbe7ddd4632a97787857ccde9b2603a8a2")
        assert json.loads(GATE_RECEIPT.read_bytes())["source_commit_sha"] == PHYSICAL_GATE_COMMIT

    # -- the refusals. Each is a way a bad gate could otherwise be laundered in --

    @pytest.mark.parametrize("label,mutate", [
        ("failed gate", lambda g: g["physical_gates"].__setitem__("status", "FAIL")),
        ("incomplete gate", lambda g: g.__setitem__("status", "PARTIAL")),
        ("wrong manifest", lambda g: g.__setitem__("manifest_sha256", "0" * 64)),
        ("wrong authority", lambda g: g.__setitem__("authority_sha256", "0" * 64)),
        ("wrong run namespace", lambda g: g.__setitem__("scientific_run_id", "other")),
        ("wrong durable uri", lambda g: g.__setitem__("durable_uri", "s3://elsewhere/x")),
        ("wrong unit identity", lambda g: g.__setitem__("unit_id", "not_the_gate")),
        ("wrong gate version", lambda g: g["physical_gates"].__setitem__(
            "required_checks", ["durability"])),
        ("wrong cohort size", lambda g: g["physical_gates"].__setitem__("capture_units", 49)),
        ("wrong pair count", lambda g: g["physical_gates"].__setitem__("paired_trajectories", 24)),
        ("wrong cohort identity", lambda g: g["physical_gates"]["capture_provenance_split"][
            "capture_source_commit_by_unit"].pop("a2y_t01_wall")),
        ("wrong apparatus", lambda g: g["physical_gates"]["capture_provenance_split"].__setitem__(
            "cohort_capture_critical_closure_sha256", "0" * 64)),
        ("mixed apparatus", lambda g: g["physical_gates"]["capture_provenance_split"].__setitem__(
            "all_admitted_capture_closures_equal", False)),
        ("forged source commit", lambda g: g.__setitem__("source_commit_sha", "a" * 40)),
        ("unnamed predecessor", lambda g: (
            g.__setitem__("source_commit_sha", "b" * 40),
            g["physical_gates"]["capture_provenance_split"].__setitem__(
                "processing_source_commit", "b" * 40))),
    ])
    def test_a_tampered_or_wrong_gate_is_refused(self, admit, gate, label, mutate):
        receipt = copy.deepcopy(gate)
        mutate(receipt)
        with pytest.raises(pga.PhysicalGateAdmissionError):
            admit(receipt)

    def test_a_gate_whose_source_changed_the_verdict_is_refused(self, admit, gate):
        """The condition that makes this rule a control and not a rubber stamp.

        If the successor genuinely changed how the gate decides, the historical
        verdict no longer represents what this source would compute, and admission
        must fail even though every other binding is perfect.
        """
        def moved(source, *, repository=None, entrypoints=None):
            return ("dead" * 16 if isinstance(source, str) else "beef" * 16), {}

        import stage2_backend as backend
        context = backend.backend_capture_admission(
            manifest=json.loads(MANIFEST_PATH.read_bytes()), manifest_path=MANIFEST_PATH,
            current_source_commit=self.SUCCESSOR)
        with pytest.raises(pga.PhysicalGateAdmissionError, match="gate-critical closure changed"):
            pga.admit_physical_gate_receipt(
                json.loads(MANIFEST_PATH.read_bytes()), gate,
                authority=json.loads((PACKAGE / "authority_parameters.json").read_bytes()),
                admission_authority=json.loads(
                    (PACKAGE / pga.AUTHORITY_FILENAME).read_bytes()),
                manifest_sha256=gate["manifest_sha256"],
                processing_source_commit=self.SUCCESSOR,
                expected_durable_uri=gate["durable_uri"],
                expected_required_checks=gate["physical_gates"]["required_checks"],
                authorized_capture_critical_closure=CAPTURE_CRITICAL_CLOSURE,
                repository=ROOT, durable_verifier=lambda *_: True, closure_at=moved)

    def test_durability_failure_blocks(self, admit, gate):
        with pytest.raises(pga.PhysicalGateAdmissionError, match="durability"):
            admit(gate, durable=lambda *_: False)

    def test_refusal_is_operational_not_a_scientific_verdict(self, gate):
        """BLOCKED, never FAIL: the error type carries that distinction."""
        assert issubclass(pga.PhysicalGateAdmissionError, RuntimeError)
        assert not issubclass(pga.PhysicalGateAdmissionError, AssertionError)

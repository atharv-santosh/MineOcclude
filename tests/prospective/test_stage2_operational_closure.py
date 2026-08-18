"""Operational closure: unit-1 checkpoint wiring, durable receipts, and CLI modes.

Three findings, all about what happens around an expensive scientific capture
rather than about any scientific value.

B002 -- the unit-1 checkpoint was unreachable
    ``unit1_checkpoint`` implemented a complete twelve-check gate and nothing in
    production ever constructed one: ``run-stage2`` built its ``DurableController``
    without a checkpoint and no production ``Prober`` existed, so a real campaign
    would have captured all fifty trajectories before anything tried to process
    one. These tests drive the REAL production wiring -- the controller, the real
    ``make_unit1_checkpoint``, the real ``capture_unit_structural_probe`` -- and
    assert reachability at the call site rather than accepting a test-local fake
    as evidence that production is wired.

B003 -- raw frames were durable, the capture receipt was not
    The receipt is written outside the synced capture directory and embeds
    capture-time runtime provenance that cannot honestly be recreated later, so
    losing local storage left recoverable frames that nothing could legitimately
    process. The destructive simulation below deletes the whole local unit tree
    and proves processing resumes from durable state with no recapture.

B006 -- ``evaluate-stage1`` presented source drift as a scientific FAIL
    Evaluating a COMPLETED campaign's frozen evidence in current-source mode at a
    later HEAD printed SCIENTIFIC FAIL for a legitimate PASS. The mode is now
    explicit, and neither branch can turn drift into a negative result.

Everything is fixture or rehearsal data. No scientific Stage-2 outcome exists,
no Stage-2 authorization is created, and no scientific unit is collected.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from mineocclude.prospective.capture_admission import (
    CaptureAdmissionError, resolve_typed_capture_identity,
)
from mineocclude.prospective.development_workflow import (
    CAPTURE_RECEIPT_OBJECT, UNIT_STATE_OBJECT, DurableController, DurableStateError,
    EvidenceError, atomic_write_json, build_unit_state, canonical_payload_sha256,
    durable_unit_state_uri, durable_unit_uri, evidence_source_drift, load_json,
    publish_durable_unit_state, restore_durable_capture_tree, restore_durable_unit_state,
    sha256_file,
)
from mineocclude.prospective.stage2_processability import (
    EXTRACTION_CHECKS, STRUCTURAL_CHECKS, StructuralProbeBlocked,
    capture_root_for, capture_unit_structural_probe, causal_fir_kernel,
    make_unit1_checkpoint,
)
from mineocclude.prospective.unit1_checkpoint import (
    FORBIDDEN_OUTCOME_FIELDS, OperationalCheckpointBlocked, PASS, REQUIRED_CHECKS,
    refuse_outcome_fields,
)

ROOT = Path(__file__).resolve().parents[2]
CONTROLLER = ROOT / "scripts/regime_a_prime_qualification_v0_2/development_controller.py"


def keys_at_any_depth(value, found=None):
    """Every mapping key in a document, at any nesting depth."""
    found = set() if found is None else found
    if isinstance(value, dict):
        for key, item in value.items():
            found.add(str(key).lower())
            keys_at_any_depth(item, found)
    elif isinstance(value, list):
        for item in value:
            keys_at_any_depth(item, found)
    return found

COMMIT = "d" * 40
AUTHORITY_SHA = "a" * 64
MANIFEST_SHA = "b" * 64
NAMESPACE = "rehearsal-operational-closure-not-a-scientific-namespace"
ROWS = 4
SHAPE = [ROWS, 4, 8]
DTYPE = "float16"

#: A genuine smoothing kernel: a bare integer-tick delay is refused by
#: ``causal_fir_targets``, so the fixture must use a real one.
KERNEL = [0.25, 0.5, 0.25]


# ======================================================================
# A synthetic campaign on disk
# ======================================================================


def stage1_decision_document():
    methods = [{"method_id": "causal_fir_group_delay", "kernel": list(KERNEL)}]
    return {"gates": {"render_server_temporal_alignment": {"detail": {
        "LEFT_TO_RIGHT": {"methods": methods}, "RIGHT_TO_LEFT": {"methods": methods}}}}}


def fir_labels(positions, ticks):
    return [sum(tap * positions[tick - lag] for lag, tap in enumerate(KERNEL))
            for tick in ticks]


class FakeTransport:
    """An in-memory object store with the two operations the code needs."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def upload(self, local: Path, uri: str) -> None:
        for path in sorted(local.rglob("*")):
            if path.is_file():
                key = f"{uri.rstrip('/')}/{path.relative_to(local).as_posix()}"
                self.objects[key] = path.read_bytes()

    def download(self, uri: str) -> bytes:
        if uri not in self.objects:
            raise DurableStateError(f"durable object could not be read back: {uri}")
        return self.objects[uri]


class Campaign:
    """A minimal Stage-2-shaped campaign the real production probes can run on."""

    def __init__(self, root: Path, unit_count: int = 3):
        self.root = root
        self.receipts = root / "receipts" / "capture"
        self.receipts.mkdir(parents=True, exist_ok=True)
        self.transport = FakeTransport()
        self.ticks = list(range(len(KERNEL) - 1, len(KERNEL) - 1 + ROWS))
        self.positions = [round(0.5 * index, 6) for index in range(64)]
        self.labels = fir_labels(self.positions, self.ticks)
        units = []
        for index in range(1, unit_count + 1):
            unit_id = f"reh_t{index:02d}_wall"
            units.append({
                "unit_id": unit_id, "trajectory_id": f"reh_t{index:02d}", "scene": "WALL",
                "direction": "LEFT_TO_RIGHT", "episode_id": 90000 + index,
                "scientific_run_id": NAMESPACE,
                "target_model_frame_indices": list(self.ticks),
                "expected_causal_fir_target_world_x_blocks": list(self.labels),
                "pipeline_stage": "capture_and_durability",
                "receipt_path": str(self.receipts / f"{unit_id}.json"),
                "command": [sys.executable, "-c", "pass", "--stage", "stage2-capture"]})
        self.manifest = {
            "artifact_id": "rehearsal-stage2-locked-manifest-v0.4",
            "run_namespace": NAMESPACE,
            "durable_prefix": "s3://rehearsal-bucket/operational-closure",
            "required_target_rows_per_capture": ROWS,
            "capture_units": units, "units": units}

    # -- capture ---------------------------------------------------------
    def capture(self, unit, *, publish=True, **overrides):
        """Write the bytes and the receipt a completed capture unit leaves behind."""
        root = capture_root_for(unit)
        (root / "raw").mkdir(parents=True, exist_ok=True)
        (root / "raw/server_state.jsonl").write_text(
            "".join(json.dumps({"sheep_x": value}) + "\n" for value in self.positions))
        # Two namespaces, written the way a real capture writes them: the Stage-2
        # visibility rows carry the SCIENTIFIC trajectory identity and the raw capture
        # package carries the LEGACY one. The superseded fixture put the scientific id
        # in the package, which no real capture does.
        identity = resolve_typed_capture_identity(REAL_AUTHORITY, unit)
        (root / "raw/visibility.jsonl").write_text(
            "".join(json.dumps({"model_frame_idx": tick, "tau": index + 1,
                                "trajectory_id": identity.scientific_trajectory_id}) + "\n"
                    for index, tick in enumerate(self.ticks)))
        (root / "capture_package_v0_1.json").write_text(
            json.dumps({"trajectory_id": identity.legacy_capture_trajectory_id,
                        "episode_id": identity.episode_id,
                        "layout_id": identity.layout_id}))
        objects = {path.relative_to(root).as_posix(): sha256_file(path)
                   for path in sorted(root.rglob("*")) if path.is_file()}
        for relative, digest in objects.items():
            self.transport.objects[
                f"{durable_unit_uri(self.manifest, unit['unit_id'])}/{relative}"] = (
                    (root / relative).read_bytes())
        receipt = {
            "schema_version": "1.1", "artifact_id": "rehearsal-unit-receipt-v0.4",
            "unit_id": unit["unit_id"], "status": DurableController.TERMINAL,
            "classification": "DEVELOPMENT_ONLY", "confirmatory_membership": False,
            "authority_sha256": AUTHORITY_SHA, "manifest_sha256": MANIFEST_SHA,
            "source_commit_sha": COMMIT, "scientific_run_id": NAMESPACE,
            "durable_uri": durable_unit_uri(self.manifest, unit["unit_id"]),
            "durable_objects": objects,
            "remote_checksum_manifest_sha256": hashlib.sha256(b"manifest").hexdigest(),
            "durable_unit_state_uri": durable_unit_state_uri(self.manifest, unit["unit_id"]),
            "server_state_sha256": sha256_file(root / "raw/server_state.jsonl"),
            "stage2_physical_evidence": {
                "target_model_frame_indices": list(self.ticks),
                "aligned_target_world_x_blocks": list(self.labels),
                "target_row_count": ROWS, "contamination_rows": []}}
        receipt.update(overrides)
        atomic_write_json(Path(unit["receipt_path"]), receipt)
        if publish:
            publish_durable_unit_state(
                self.manifest, unit, receipt_path=Path(unit["receipt_path"]),
                staging=self.receipts / ".unit_state_staging", transport=self.transport)
        return receipt

    def capture_all(self):
        for unit in self.manifest["units"]:
            self.capture(unit)

    # -- production probes, constructed exactly as the controller does ----
    def bindings(self):
        return {"manifest": self.manifest, "manifest_sha256": MANIFEST_SHA,
                "authority_sha256": AUTHORITY_SHA, "source_commit_sha": COMMIT,
                "scientific_run_id": NAMESPACE, "required_target_rows": ROWS,
                "stage1_decision": stage1_decision_document(),
                "capture_admission": StubCaptureAdmission(self.manifest)}

    def structural_probe(self):
        return capture_unit_structural_probe(
            **self.bindings(), durable_verifier=lambda unit, receipt: True)

    def checkpoint(self, extractor_factory):
        return make_unit1_checkpoint(
            **self.bindings(), expected_activation_shape=SHAPE,
            expected_activation_dtype=DTYPE,
            receipts_root=self.receipts.parent,
            durable_verifier=lambda unit, receipt: True,
            extractor_factory=extractor_factory)



#: The real frozen authority, used only for its ``apparatus.layout_id`` so the
#: fixture's legacy capture identities compose by the same frozen rule production
#: uses rather than by a second spelling invented here.
REAL_AUTHORITY = load_json(
    ROOT / "docs/status/integration/regime_a_prime_qualification_v0_1"
    / "prospective_development_authority_v0_4/authority_parameters.json")


class StubCaptureAdmission:
    """Admits captures on their scientific DESIGN bindings only.

    The real context additionally derives each capture's capture-critical closure
    from committed bytes and compares the physical apparatus to frozen authority;
    that has its own adversarial suite in
    ``test_stage2_capture_processing_provenance_split.py`` and needs a real commit,
    which this synthetic rehearsal campaign has none of. What is kept is the part
    these tests exercise -- the design bindings, including the mis-bound-receipt
    mutations below.

    ``source_commit_sha`` is deliberately still compared here. This fixture's
    captures are all taken by the commit under test, so for THIS cohort capture and
    processing provenance coincide, and the mis-bound-receipt case for that field is
    still a genuine refusal.
    """

    capture_provenance_authority_sha256 = "e" * 64
    authority = REAL_AUTHORITY

    def __init__(self, manifest, *, closure="a" * 64):
        self.manifest = manifest
        self.closure = closure

    def admit(self, unit, receipt):
        unit_id = str(unit.get("unit_id"))
        expected = {
            "unit_id": unit.get("unit_id"),
            "status": DurableController.TERMINAL,
            "classification": "DEVELOPMENT_ONLY",
            "confirmatory_membership": False,
            "manifest_sha256": MANIFEST_SHA,
            "authority_sha256": AUTHORITY_SHA,
            "source_commit_sha": COMMIT,
            "scientific_run_id": NAMESPACE,
            "durable_uri": durable_unit_uri(self.manifest, unit_id),
        }
        for key, value in expected.items():
            if receipt.get(key) != value:
                raise CaptureAdmissionError(
                    f"receipt binding mismatch on {key!r} "
                    f"({receipt.get(key)!r} != {value!r})")
        return {"unit_id": unit_id, "capture_compatibility": "PASS",
                "capture_source_commit": COMMIT,
                "capture_critical_closure_sha256": self.closure,
                "processing_source_commit": COMMIT,
                "capture_and_processing_commits_equal": True,
                "capture_taken_under_processing_commit": True,
                "durable_object_count": len(receipt.get("durable_objects") or {}),
                "durable_object_inventory_sha256": "c" * 64,
                "typed_capture_identity":
                    resolve_typed_capture_identity(REAL_AUTHORITY, unit).to_dict()}


class FakeExtractor:
    """Writes a real activation file with the shape and dtype under test."""

    def __init__(self, *, shape=None, dtype=DTYPE, finite=True, identity=True,
                 targets=None, layer=4):
        self.shape, self.dtype, self.finite = shape or SHAPE, dtype, finite
        self.identity, self.targets, self.layer = identity, targets, layer
        self.calls = 0

    def extract(self, run_id, source, destination, *, expected_target_model_frame_indices,
                scientific_trajectory_id, expected_legacy_capture_trajectory_id):
        self.calls += 1
        # Both typed identities must arrive, and must arrive in the right roles. The
        # defect under repair passed the raw capture package's legacy identity into
        # the Stage-2 slot, so a fake that accepted either interchangeably would let
        # that regress unnoticed.
        assert scientific_trajectory_id.startswith("reh_t"), scientific_trajectory_id
        assert expected_legacy_capture_trajectory_id.startswith("layout_"), (
            expected_legacy_capture_trajectory_id)
        assert "_ep" in expected_legacy_capture_trajectory_id
        self.identities = (scientific_trajectory_id,
                           expected_legacy_capture_trajectory_id)
        destination.mkdir(parents=True, exist_ok=True)
        path = destination / f"{run_id}.layer_04.npy"
        array = np.zeros(tuple(self.shape), dtype=np.dtype(self.dtype))
        if not self.finite:
            array.reshape(-1)[0] = np.inf
        np.save(path, array)
        record = {"layer": self.layer, "shape": list(self.shape), "dtype": self.dtype,
                  "activation_path": str(path), "activation_sha256": sha256_file(path),
                  "targets": list(self.targets if self.targets is not None
                                  else expected_target_model_frame_indices),
                  "target_rows_authority_bound": True}
        if self.identity:
            digests = {name: hashlib.sha256(name.encode()).hexdigest() for name in (
                "main_checkpoint_sha256", "vae_checkpoint_sha256", "model_config_sha256",
                "vae_config_sha256", "environment_report_sha256")}
            record["model_runtime_identity"] = {
                **digests, "runtime_id": "rehearsal-runtime",
                "preprocessing_identity": "preprocess-v1",
                "action_conversion_identity": "actions-v1",
                "model_class": "M", "transformer_class": "T", "vae_class": "V",
                "decoder_layer_path": "model.layers", "layer_count": 20,
                "hidden_size": 2048, "max_position_embeddings": 8192,
                "visual_tokens_per_frame": 336, "action_tokens_per_frame": 8,
                "tokens_per_pair": 344, "max_context_pairs": 16,
                "precision": "bfloat16", "device": "cuda",
                "adapter_api_version": "1.0", "schema_version": "1.0",
                "mineocclude_revision": hashlib.sha256(b"mo").hexdigest(),
                "mineworld_source_revision": hashlib.sha256(b"mw").hexdigest(),
                "modelscope_asset_revision": hashlib.sha256(b"ms").hexdigest()}
            record["main_checkpoint_sha256"] = digests["main_checkpoint_sha256"]
            record["vae_checkpoint_sha256"] = digests["vae_checkpoint_sha256"]
        return record

    def __call__(self):
        return self


@pytest.fixture
def campaign(tmp_path):
    return Campaign(tmp_path)


# ======================================================================
# B002 -- production reachability
# ======================================================================


class TestProductionReachability:
    """The finding was located by grep: nothing constructed the checkpoint.

    So reachability is asserted at the production call site, not by observing
    that a test can call the module.
    """

    @staticmethod
    def _run_stage2_controller_keywords() -> set[str]:
        tree = ast.parse(CONTROLLER.read_text())
        found: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id == "DurableController":
                found.update(keyword.arg for keyword in node.keywords if keyword.arg)
        return found

    def test_the_controller_constructs_the_checkpoint_and_the_per_unit_probe(self):
        keywords = self._run_stage2_controller_keywords()
        assert "unit1_checkpoint" in keywords
        assert "capture_unit_probe" in keywords

    def test_the_controller_imports_the_production_prober_module(self):
        source = CONTROLLER.read_text()
        assert "from mineocclude.prospective.stage2_processability import" in source
        assert "make_unit1_checkpoint" in source
        assert "capture_unit_structural_probe" in source

    def test_the_checkpoint_shape_comes_from_the_frozen_activation_contract(self):
        source = CONTROLLER.read_text()
        assert 'decision_authority["activation_contract"]' in source
        assert 'expected_activation_shape=list(activation_contract["expected_shape"])' in source

    def test_a_real_production_checkpoint_is_constructible(self, campaign):
        assert callable(campaign.checkpoint(FakeExtractor()))
        assert callable(campaign.structural_probe())


# ======================================================================
# B002 -- the checkpoint, driven through the real controller
# ======================================================================


def controller_for(campaign, tmp_path, *, checkpoint=None, probe=None):
    return DurableController(
        campaign.manifest, tmp_path / "state", tmp_path / "events.jsonl",
        manifest_sha256=MANIFEST_SHA, authority_sha256=AUTHORITY_SHA,
        source_commit_sha=COMMIT, run_namespace=NAMESPACE,
        stage_role="stage2-capture", durable_verifier=lambda unit, receipt: True,
        unit1_checkpoint=checkpoint, capture_unit_probe=probe)


class TestCheckpointThroughTheController:
    def test_the_checkpoint_runs_after_unit_one_and_permits_continuation(
            self, campaign, tmp_path):
        campaign.capture_all()
        extractor = FakeExtractor()
        controller = controller_for(campaign, tmp_path,
                                    checkpoint=campaign.checkpoint(extractor))
        controller.run(authorized=True, stop_after_stage1=False)
        events = [json.loads(line)
                  for line in (tmp_path / "events.jsonl").read_text().splitlines()]
        names = [event["event"] for event in events]
        assert names.count("unit1_checkpoint_started") == 1
        assert names.count("unit1_checkpoint_passed") == 1
        # after unit 1, and before unit 2 is reached
        first = names.index("unit1_checkpoint_started")
        assert events[first]["unit_id"] == "reh_t01_wall"
        reused = [index for index, event in enumerate(events)
                  if event.get("unit_id") == "reh_t02_wall"]
        assert all(index > first for index in reused)
        assert extractor.calls == 1

    def test_a_blocked_checkpoint_stops_the_remaining_collection(self, campaign, tmp_path):
        campaign.capture_all()
        controller = controller_for(
            campaign, tmp_path,
            checkpoint=campaign.checkpoint(FakeExtractor(shape=[ROWS, 4, 9])))
        with pytest.raises(OperationalCheckpointBlocked) as blocked:
            controller.run(authorized=True, stop_after_stage1=False)
        assert "ACTIVATION_SHAPE_VALID" in str(blocked.value)
        assert "OPERATIONAL block" in str(blocked.value)
        events = (tmp_path / "events.jsonl").read_text()
        assert "unit1_checkpoint_passed" not in events
        assert "reh_t03_wall" not in events

    @pytest.mark.parametrize("extractor,failing", [
        (FakeExtractor(dtype="float32"), "ACTIVATION_DTYPE_VALID"),
        (FakeExtractor(finite=False), "ACTIVATIONS_FINITE"),
        (FakeExtractor(identity=False), "ACTIVATION_IDENTITY_VALID"),
        (FakeExtractor(layer=7), "LAYER4_HOOK_RESOLVES"),
    ])
    def test_each_extraction_defect_blocks_with_its_own_check(
            self, campaign, tmp_path, extractor, failing):
        campaign.capture_all()
        controller = controller_for(campaign, tmp_path,
                                    checkpoint=campaign.checkpoint(extractor))
        with pytest.raises(OperationalCheckpointBlocked, match=failing):
            controller.run(authorized=True, stop_after_stage1=False)

    def test_a_capture_the_pipeline_cannot_read_blocks_before_the_model_loads(
            self, campaign, tmp_path):
        campaign.capture_all()
        unit = campaign.manifest["units"][0]
        (capture_root_for(unit) / "raw/server_state.jsonl").unlink()
        extractor = FakeExtractor()
        controller = controller_for(campaign, tmp_path,
                                    checkpoint=campaign.checkpoint(extractor))
        with pytest.raises((OperationalCheckpointBlocked, StructuralProbeBlocked)):
            controller.run(authorized=True, stop_after_stage1=False)
        assert extractor.calls == 0

    def test_the_checkpoint_receipt_carries_no_scientific_outcome(self, campaign, tmp_path):
        campaign.capture_all()
        controller = controller_for(campaign, tmp_path,
                                    checkpoint=campaign.checkpoint(FakeExtractor()))
        controller.run(authorized=True, stop_after_stage1=False)
        receipt = load_json(
            campaign.receipts.parent / "operational_processability"
            / "unit1_checkpoint_reh_t01_wall.json")
        assert receipt["status"] == PASS
        assert receipt["scientific_outcome_observed"] is False
        assert receipt["may_alter_scientific_design"] is False
        assert receipt["collection_remains_prospective"] is True
        assert set(receipt["checks"]) == set(REQUIRED_CHECKS)
        refuse_outcome_fields(receipt, "unit-1 checkpoint receipt")
        assert not (set(keys_at_any_depth(receipt)) & set(FORBIDDEN_OUTCOME_FIELDS))

    def test_the_operational_activation_is_not_in_the_scientific_tree(
            self, campaign, tmp_path):
        campaign.capture_all()
        controller = controller_for(campaign, tmp_path,
                                    checkpoint=campaign.checkpoint(FakeExtractor()))
        controller.run(authorized=True, stop_after_stage1=False)
        workspace = campaign.receipts.parent / "operational_processability"
        produced = list(workspace.rglob("*.npy"))
        assert produced and all("operational_processability" in str(path) for path in produced)
        assert not list((campaign.root / "activations").rglob("*.npy")) \
            if (campaign.root / "activations").exists() else True

    def test_a_restart_honours_a_proven_checkpoint_receipt(self, campaign, tmp_path):
        campaign.capture_all()
        extractor = FakeExtractor()
        controller_for(campaign, tmp_path, checkpoint=campaign.checkpoint(extractor)).run(
            authorized=True, stop_after_stage1=False)
        assert extractor.calls == 1
        second = FakeExtractor()
        controller_for(campaign, tmp_path, checkpoint=campaign.checkpoint(second)).run(
            authorized=True, stop_after_stage1=False)
        assert second.calls == 0, "a proven checkpoint must not re-probe on resume"

    def test_a_checkpoint_receipt_from_another_campaign_is_not_honoured(
            self, campaign, tmp_path):
        campaign.capture_all()
        extractor = FakeExtractor()
        controller_for(campaign, tmp_path, checkpoint=campaign.checkpoint(extractor)).run(
            authorized=True, stop_after_stage1=False)
        path = (campaign.receipts.parent / "operational_processability"
                / "unit1_checkpoint_reh_t01_wall.json")
        stale = load_json(path)
        stale["source_commit_sha"] = "e" * 40
        atomic_write_json(path, stale)
        again = FakeExtractor()
        controller_for(campaign, tmp_path, checkpoint=campaign.checkpoint(again)).run(
            authorized=True, stop_after_stage1=False)
        assert again.calls == 1, "a receipt from another source freeze must not be honoured"

    def test_a_checkpoint_receipt_for_another_unit_is_not_honoured(self, campaign, tmp_path):
        campaign.capture_all()
        extractor = FakeExtractor()
        controller_for(campaign, tmp_path, checkpoint=campaign.checkpoint(extractor)).run(
            authorized=True, stop_after_stage1=False)
        workspace = campaign.receipts.parent / "operational_processability"
        borrowed = load_json(workspace / "unit1_checkpoint_reh_t01_wall.json")
        borrowed["unit_id"] = "reh_t02_wall"
        borrowed["payload_sha256"] = canonical_payload_sha256(
            borrowed, omit="payload_sha256")
        atomic_write_json(workspace / "unit1_checkpoint_reh_t01_wall.json", borrowed)
        again = FakeExtractor()
        controller_for(campaign, tmp_path, checkpoint=campaign.checkpoint(again)).run(
            authorized=True, stop_after_stage1=False)
        assert again.calls == 1


# ======================================================================
# B002 -- the per-unit structural probe
# ======================================================================


class TestPerUnitStructuralProbe:
    def test_every_capture_unit_is_probed(self, campaign, tmp_path):
        campaign.capture_all()
        controller_for(campaign, tmp_path, probe=campaign.structural_probe()).run(
            authorized=True, stop_after_stage1=False)
        events = [json.loads(line)
                  for line in (tmp_path / "events.jsonl").read_text().splitlines()]
        probed = [event["unit_id"] for event in events
                  if event["event"] == "capture_unit_probe_passed"]
        assert probed == [unit["unit_id"] for unit in campaign.manifest["units"]]

    def test_a_defect_at_unit_two_stops_before_unit_three(self, campaign, tmp_path):
        campaign.capture_all()
        second = campaign.manifest["units"][1]
        (capture_root_for(second) / "raw/visibility.jsonl").unlink()
        with pytest.raises(StructuralProbeBlocked, match="EXPECTED_FILES_PRESENT"):
            controller_for(campaign, tmp_path, probe=campaign.structural_probe()).run(
                authorized=True, stop_after_stage1=False)
        events = (tmp_path / "events.jsonl").read_text()
        assert "reh_t03_wall" not in events

    def test_a_truncated_capture_file_blocks_through_the_controller(self, campaign, tmp_path):
        campaign.capture_all()
        (capture_root_for(campaign.manifest["units"][0]) / "raw/server_state.jsonl"
         ).write_text('{"sheep_x": 0.0}\n')
        with pytest.raises(StructuralProbeBlocked, match="EXPECTED_FILES_PRESENT"):
            controller_for(campaign, tmp_path, probe=campaign.structural_probe()).run(
                authorized=True, stop_after_stage1=False)

    @pytest.mark.parametrize("field,value", [
        ("source_commit_sha", "f" * 40), ("manifest_sha256", "0" * 64),
        ("scientific_run_id", "another-campaign"), ("status", "PARTIAL"),
        ("durable_uri", "s3://elsewhere/reh_t01_wall"),
    ])
    def test_a_mis_bound_receipt_blocks_at_the_probe(self, campaign, field, value):
        """Defence in depth: the controller refuses these first, the probe again.

        Driven directly because a receipt the controller rejects never reaches
        the probe through a run -- which is the correct ordering, and is why this
        check is exercised at the probe instead of through one.
        """
        campaign.capture_all()
        unit = campaign.manifest["units"][0]
        receipt = load_json(Path(unit["receipt_path"]))
        receipt[field] = value
        atomic_write_json(Path(unit["receipt_path"]), receipt)
        with pytest.raises(StructuralProbeBlocked, match="CAPTURE_RECEIPT_VALID"):
            campaign.structural_probe()(unit)

    def test_an_absent_receipt_blocks_at_the_probe(self, campaign):
        campaign.capture_all()
        unit = campaign.manifest["units"][0]
        Path(unit["receipt_path"]).unlink()
        with pytest.raises(StructuralProbeBlocked, match="CAPTURE_RECEIPT_VALID"):
            campaign.structural_probe()(unit)

    def test_a_broken_temporal_binding_blocks(self, campaign, tmp_path):
        campaign.capture_all()
        unit = campaign.manifest["units"][0]
        receipt = load_json(Path(unit["receipt_path"]))
        receipt["stage2_physical_evidence"]["aligned_target_world_x_blocks"] = [
            value + 1.0 for value in campaign.labels]
        atomic_write_json(Path(unit["receipt_path"]), receipt)
        with pytest.raises(StructuralProbeBlocked, match="TEMPORAL_BINDING_RESOLVES"):
            controller_for(campaign, tmp_path, probe=campaign.structural_probe()).run(
                authorized=True, stop_after_stage1=False)

    def test_a_wrong_target_row_count_blocks(self, campaign, tmp_path):
        campaign.capture_all()
        unit = campaign.manifest["units"][0]
        receipt = load_json(Path(unit["receipt_path"]))
        receipt["stage2_physical_evidence"]["target_model_frame_indices"] = campaign.ticks[:-1]
        atomic_write_json(Path(unit["receipt_path"]), receipt)
        with pytest.raises(StructuralProbeBlocked, match="EXPECTED_TARGET_COUNT"):
            controller_for(campaign, tmp_path, probe=campaign.structural_probe()).run(
                authorized=True, stop_after_stage1=False)

    def test_the_probe_reads_no_scientific_outcome(self, campaign):
        campaign.capture_all()
        record = campaign.structural_probe()(campaign.manifest["units"][0])
        assert set(record["checks"]) == set(STRUCTURAL_CHECKS)
        assert not set(STRUCTURAL_CHECKS) & set(EXTRACTION_CHECKS)
        refuse_outcome_fields(record, "structural probe record")
        assert not (set(keys_at_any_depth(record)) & set(FORBIDDEN_OUTCOME_FIELDS))

    def test_the_probe_also_runs_on_the_resume_path(self, campaign, tmp_path):
        campaign.capture_all()
        probe = campaign.structural_probe()
        controller_for(campaign, tmp_path, probe=probe).run(
            authorized=True, stop_after_stage1=False)
        (capture_root_for(campaign.manifest["units"][0]) / "raw/visibility.jsonl").unlink()
        with pytest.raises(StructuralProbeBlocked):
            controller_for(campaign, tmp_path, probe=campaign.structural_probe()).run(
                authorized=True, stop_after_stage1=False)

    def test_a_campaign_with_no_probe_still_runs(self, campaign, tmp_path):
        """The hooks are optional; the predecessor behaviour is unchanged."""
        campaign.capture_all()
        controller_for(campaign, tmp_path).run(authorized=True, stop_after_stage1=False)
        assert "capture_unit_probe_started" not in (tmp_path / "events.jsonl").read_text()


# ======================================================================
# B003 -- durable receipts and the destructive simulation
# ======================================================================


class TestDurableReceipt:
    def test_the_receipt_is_uploaded_and_reads_back_exactly(self, campaign):
        unit = campaign.manifest["units"][0]
        campaign.capture(unit)
        uri = durable_unit_state_uri(campaign.manifest, unit["unit_id"])
        assert campaign.transport.objects[f"{uri}/{CAPTURE_RECEIPT_OBJECT}"] == \
            Path(unit["receipt_path"]).read_bytes()
        state = json.loads(campaign.transport.objects[f"{uri}/{UNIT_STATE_OBJECT}"])
        assert state["capture_receipt_sha256"] == sha256_file(Path(unit["receipt_path"]))
        assert state["payload_sha256"] == canonical_payload_sha256(
            state, omit="payload_sha256")

    def test_the_state_namespace_is_outside_every_unit_prefix(self, campaign):
        """An extra object inside a unit prefix would break its own durability check."""
        for unit in campaign.manifest["units"]:
            assert not durable_unit_state_uri(campaign.manifest, unit["unit_id"]).startswith(
                durable_unit_uri(campaign.manifest, unit["unit_id"]) + "/")

    def test_a_receipt_missing_a_binding_cannot_be_made_durable(self, campaign):
        unit = campaign.manifest["units"][0]
        with pytest.raises(DurableStateError, match="missing"):
            build_unit_state({"unit_id": unit["unit_id"]}, receipt_sha256="0" * 64)

    def test_publishing_another_units_receipt_is_refused(self, campaign):
        first, second = campaign.manifest["units"][0], campaign.manifest["units"][1]
        campaign.capture(first)
        with pytest.raises(DurableStateError, match="is for"):
            publish_durable_unit_state(
                campaign.manifest, second, receipt_path=Path(first["receipt_path"]),
                staging=campaign.receipts / ".staging", transport=campaign.transport)


class TestNvmeLossRestore:
    """The critical acceptance test: total local loss, no recapture."""

    def restore(self, campaign, unit, **overrides):
        arguments = {"receipt_path": Path(unit["receipt_path"]),
                     "manifest_sha256": MANIFEST_SHA, "authority_sha256": AUTHORITY_SHA,
                     "source_commit_sha": COMMIT, "run_namespace": NAMESPACE,
                     "transport": campaign.transport}
        arguments.update(overrides)
        return restore_durable_unit_state(campaign.manifest, unit, **arguments)

    def test_a_completely_lost_unit_is_restored_and_reprocessed(self, campaign, tmp_path):
        import shutil

        unit = campaign.manifest["units"][0]
        original = campaign.capture(unit)
        original_sha = sha256_file(Path(unit["receipt_path"]))

        # total loss of the local unit tree: frames, receipt, everything
        shutil.rmtree(capture_root_for(unit))
        Path(unit["receipt_path"]).unlink()
        assert not Path(unit["receipt_path"]).exists()

        receipt = self.restore(campaign, unit)
        assert receipt == original
        assert sha256_file(Path(unit["receipt_path"])) == original_sha
        restored = restore_durable_capture_tree(
            campaign.manifest, unit, receipt=receipt,
            destination=capture_root_for(unit), transport=campaign.transport)
        assert set(restored) == set(receipt["durable_objects"])
        assert restored == receipt["durable_objects"]

        # and processing resumes: the real probe accepts the restored unit
        record = campaign.structural_probe()(unit)
        assert all(record["checks"].values())
        extractor = FakeExtractor()
        campaign.checkpoint(extractor)(unit)
        assert extractor.calls == 1

    def test_restoring_is_idempotent_when_the_local_receipt_survived(self, campaign):
        unit = campaign.manifest["units"][0]
        campaign.capture(unit)
        assert self.restore(campaign, unit) == load_json(Path(unit["receipt_path"]))

    def test_a_differing_local_receipt_is_not_silently_overwritten(self, campaign):
        unit = campaign.manifest["units"][0]
        campaign.capture(unit)
        edited = load_json(Path(unit["receipt_path"]))
        edited["episode_id"] = 1
        atomic_write_json(Path(unit["receipt_path"]), edited)
        with pytest.raises(DurableStateError, match="would discard it"):
            self.restore(campaign, unit)
        assert self.restore(campaign, unit, overwrite=True)["unit_id"] == unit["unit_id"]

    @pytest.mark.parametrize("field,value", [
        ("manifest_sha256", "0" * 64), ("authority_sha256", "1" * 64),
        ("source_commit_sha", "f" * 40), ("run_namespace", "another-campaign"),
    ])
    def test_wrong_provenance_is_refused(self, campaign, field, value):
        unit = campaign.manifest["units"][0]
        campaign.capture(unit)
        Path(unit["receipt_path"]).unlink()
        with pytest.raises(DurableStateError, match="binding mismatch"):
            self.restore(campaign, unit, **{field: value})

    def test_another_units_durable_state_is_refused(self, campaign):
        first, second = campaign.manifest["units"][0], campaign.manifest["units"][1]
        campaign.capture(first)
        campaign.capture(second)
        # serve the first unit's bundle from the second unit's location
        source = durable_unit_state_uri(campaign.manifest, first["unit_id"])
        target = durable_unit_state_uri(campaign.manifest, second["unit_id"])
        for name in (CAPTURE_RECEIPT_OBJECT, UNIT_STATE_OBJECT):
            campaign.transport.objects[f"{target}/{name}"] = \
                campaign.transport.objects[f"{source}/{name}"]
        Path(second["receipt_path"]).unlink()
        with pytest.raises(DurableStateError, match="binding mismatch"):
            self.restore(campaign, second)

    def test_a_receipt_from_another_attempt_is_refused(self, campaign):
        unit = campaign.manifest["units"][0]
        campaign.capture(unit)
        uri = durable_unit_state_uri(campaign.manifest, unit["unit_id"])
        other = json.loads(campaign.transport.objects[f"{uri}/{CAPTURE_RECEIPT_OBJECT}"])
        other["timestamp_utc"] = "2026-08-18T00:00:00Z"
        campaign.transport.objects[f"{uri}/{CAPTURE_RECEIPT_OBJECT}"] = json.dumps(
            other, sort_keys=True).encode()
        Path(unit["receipt_path"]).unlink()
        with pytest.raises(DurableStateError, match="different attempt"):
            self.restore(campaign, unit)

    def test_a_tampered_state_record_is_refused(self, campaign):
        unit = campaign.manifest["units"][0]
        campaign.capture(unit)
        uri = durable_unit_state_uri(campaign.manifest, unit["unit_id"])
        state = json.loads(campaign.transport.objects[f"{uri}/{UNIT_STATE_OBJECT}"])
        state["capture_receipt_sha256"] = "0" * 64
        campaign.transport.objects[f"{uri}/{UNIT_STATE_OBJECT}"] = json.dumps(state).encode()
        Path(unit["receipt_path"]).unlink()
        with pytest.raises(DurableStateError, match="digest does not reproduce"):
            self.restore(campaign, unit)

    def test_absent_durable_state_is_refused_rather_than_invented(self, campaign):
        unit = campaign.manifest["units"][0]
        campaign.capture(unit, publish=False)
        Path(unit["receipt_path"]).unlink()
        with pytest.raises(DurableStateError, match="could not be read back"):
            self.restore(campaign, unit)
        assert not Path(unit["receipt_path"]).exists()

    def test_a_substituted_capture_object_is_refused_during_tree_restore(self, campaign):
        unit = campaign.manifest["units"][0]
        receipt = campaign.capture(unit)
        uri = durable_unit_uri(campaign.manifest, unit["unit_id"])
        campaign.transport.objects[f"{uri}/raw/visibility.jsonl"] = b"substituted\n"
        with pytest.raises(DurableStateError, match="hashes to"):
            restore_durable_capture_tree(
                campaign.manifest, unit, receipt=receipt,
                destination=capture_root_for(unit), transport=campaign.transport)

    def test_the_driver_publishes_durable_state_at_the_end_of_capture(self):
        """The production call site, asserted at the source like B002's."""
        driver = (ROOT / "scripts/regime_a_prime_qualification_v0_2/stage_unit_driver.py"
                  ).read_text()
        assert "publish_durable_unit_state(manifest, unit, receipt_path=receipt_path" in driver
        assert 'receipt["durable_unit_state_uri"] = durable_unit_state_uri(' in driver

    def test_the_controller_exposes_a_restore_command(self):
        source = CONTROLLER.read_text()
        assert 'sub.add_parser("restore-unit")' in source
        assert "restore_durable_unit_state(" in source
        assert "restore_durable_capture_tree(" in source


# ======================================================================
# B006 -- historical vs current-source evaluation
# ======================================================================


STAGE1 = Path("/home/sagemaker-user/mineocclude-stage1-successor-046b34a")
HISTORICAL_EVIDENCE = STAGE1 / "collection_launch_01_20260817T225203Z/stage1_evidence.json"
HISTORICAL_PROVENANCE = STAGE1 / "preoutcome_provenance.json"
HISTORICAL_DECISION_SHA = (
    "d00d7730e44200c2406d32475843a69011f3fff5b4cdaaa67167321416b7f6e2")

historical = pytest.mark.skipif(
    not HISTORICAL_EVIDENCE.is_file() or not HISTORICAL_PROVENANCE.is_file(),
    reason="the completed v0.4 Stage-1 evidence tree is not on this host")


def run_cli(*arguments, repo=ROOT):
    return subprocess.run(
        [sys.executable, "scripts/regime_a_prime_qualification_v0_4/development_controller.py",
         *arguments], cwd=repo, text=True, capture_output=True)


class TestEvaluateStage1Modes:
    def test_a_mode_is_required(self, tmp_path):
        result = run_cli("evaluate-stage1", str(tmp_path / "e.json"), str(tmp_path / "d.json"))
        assert result.returncode != 0
        assert "--historical" in result.stderr and "--current-source" in result.stderr

    def test_the_two_modes_are_mutually_exclusive(self, tmp_path):
        result = run_cli("evaluate-stage1", str(tmp_path / "e.json"), str(tmp_path / "d.json"),
                         "--current-source", "--historical", str(tmp_path / "p.json"))
        assert result.returncode != 0

    @historical
    def test_historical_mode_reproduces_the_frozen_pass_exactly(self, tmp_path):
        output = tmp_path / "decision.json"
        result = run_cli("evaluate-stage1", str(HISTORICAL_EVIDENCE), str(output),
                         "--historical", str(HISTORICAL_PROVENANCE))
        assert result.returncode == 0, result.stderr
        assert "STAGE1_EVALUATION_STATUS=PASS" in result.stdout
        assert "STAGE1_EVALUATION_MODE=HISTORICAL" in result.stdout
        assert sha256_file(output) == HISTORICAL_DECISION_SHA
        decision = load_json(output)
        assert decision["status"] == "PASS"
        assert len(decision["gates"]) == 9
        assert all(gate["status"] == "PASS" for gate in decision["gates"].values())

    @historical
    def test_current_source_drift_is_blocked_and_never_a_scientific_fail(self, tmp_path):
        output = tmp_path / "decision.json"
        result = run_cli("evaluate-stage1", str(HISTORICAL_EVIDENCE), str(output),
                         "--current-source")
        assert result.returncode == 3, result.stdout + result.stderr
        assert "STAGE1_EVALUATION_STATUS=BLOCKED" in result.stderr
        assert "FAIL" not in result.stdout
        assert not output.exists(), "a blocked evaluation must write no decision artifact"

    @historical
    def test_a_wrong_historical_provenance_is_blocked_not_failed(self, tmp_path):
        forged = tmp_path / "provenance.json"
        document = load_json(HISTORICAL_PROVENANCE)
        document["source_commit"] = "0" * 40
        forged.write_text(json.dumps(document, sort_keys=True))
        output = tmp_path / "decision.json"
        result = run_cli("evaluate-stage1", str(HISTORICAL_EVIDENCE), str(output),
                         "--historical", str(forged))
        assert result.returncode == 3
        assert "STAGE1_EVALUATION_STATUS=BLOCKED" in result.stderr
        assert not output.exists()

    @historical
    def test_source_drift_detection_names_the_campaigns_own_commit(self):
        drift = evidence_source_drift(load_json(HISTORICAL_EVIDENCE), ROOT)
        assert drift["drifted"] is True
        assert drift["recorded_source_commits"] == [
            "046b34a3634f183b306fb48effaf62bf22d39d0a"]
        assert len(drift["units"]) == 8

    def test_evidence_matching_the_live_tree_does_not_drift(self):
        """The mode is not a blanket refusal: a matching tree evaluates normally."""
        from mineocclude.prospective.development_workflow import (
            RUNTIME_CRITICAL_SOURCE_PATHS,
        )
        pins = {relative: sha256_file(ROOT / relative)
                for relative in RUNTIME_CRITICAL_SOURCE_PATHS}
        evidence = {"runs": [{"unit_id": "u1", "runtime_provenance_receipt": {
            "head": COMMIT, "runtime_source_sha256": pins}}]}
        assert evidence_source_drift(evidence, ROOT)["drifted"] is False

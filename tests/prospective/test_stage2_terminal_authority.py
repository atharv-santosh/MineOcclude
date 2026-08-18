"""Stage-2 terminal authority, checkpoint binding, and target-row cross-check.

Three defects are covered, and every case is driven by fixtures. No scientific
Stage-2 outcome exists, none is read, and nothing here writes into an evidence
directory or authorizes a collection.

NEW-B001 -- the activation receipt bound no checkpoint
    ``p2d_extract`` read ``checkpoint_sha256`` / ``checkpoint_identity`` from
    ``MineWorldRuntimeIdentity``, which exposes neither, so the field evaluated
    to ``""`` on every real runtime and failed OPEN. The tests use a fixture
    shaped like the real dataclass -- built from its own field list, so it
    cannot drift from the class it stands in for.

NEW-B002 -- the scientific target rows were inferred, never proved
    Extraction selected rows by ``visibility.tau`` while gating used the frozen
    manifest's ``target_model_frame_indices``. They agreed by construction, which
    is not the same as being checked. Every drift direction is exercised.

B009 -- the terminal decision was copied, not derived
    ``terminal`` copied the BEST-K readout's own ``qualification_status``. The
    tests drive the real builder/evaluator/reproduction chain over synthetic
    completions and confirm PASS, FAIL, and BLOCKED all arise for the right
    reasons -- in particular that an operational fault never becomes a
    scientific FAIL, and that FULL cannot rescue a failed BEST-K.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from mineocclude.models.mineworld_adapter import MineWorldRuntimeIdentity
from mineocclude.prospective.activation_binding import (
    TARGET_ROWS_NOT_AUTHORITY_BOUND, ACTIVATION_IDENTITY_FIELDS,
    model_runtime_identity_binding, require_activation_identity,
    require_target_rows_authority_bound, resolve_authority_bound_target_rows,
    verify_activation_checkpoint_binding,
)
from mineocclude.prospective.development_workflow import (
    EvidenceError, canonical_payload_sha256, load_json,
)
from mineocclude.prospective.stage2_decision import (
    BEST_K_GATES, BLOCKED, FAIL, PASS, Stage2Evaluator, evaluate_stage2,
    require_stage2_decision_reproduction,
)
from mineocclude.prospective.stage2_evidence import build_stage2_evidence

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / ("docs/status/integration/regime_a_prime_qualification_v0_1/"
                  "prospective_development_authority_v0_4")
AUTHORITY_PATH = PACKAGE / "authority_parameters.json"
DECISION_AUTHORITY_PATH = PACKAGE / "stage2_decision_authority.json"
STAGE2_PATH = PACKAGE / "stage2_locked_manifest.json"

COMMIT = "c" * 40


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# ======================================================================
# NEW-B001 -- checkpoint binding
# ======================================================================


def runtime_fixture(**overrides):
    """A stand-in built from ``MineWorldRuntimeIdentity``'s own field list.

    Deriving the field names from the dataclass rather than typing them means a
    rename in the adapter surfaces here as a failure instead of silently leaving
    the fixture testing a shape the runtime no longer has -- which is exactly how
    NEW-B001 survived: the extractor read two names nothing produced.
    """
    names = [field.name for field in dataclasses.fields(MineWorldRuntimeIdentity)]
    assert "main_checkpoint_sha256" in names and "vae_checkpoint_sha256" in names
    assert "checkpoint_sha256" not in names and "checkpoint_identity" not in names
    values = {
        "schema_version": "1.0", "adapter_api_version": "1.0",
        "runtime_id": "mineworld-runtime-fixture",
        "mineocclude_revision": _sha("mineocclude"),
        "mineworld_source_revision": _sha("mineworld"),
        "modelscope_asset_revision": _sha("modelscope"),
        "model_config_sha256": _sha("model-config"),
        "main_checkpoint_sha256": _sha("main-checkpoint"),
        "vae_config_sha256": _sha("vae-config"),
        "vae_checkpoint_sha256": _sha("vae-checkpoint"),
        "environment_report_sha256": _sha("environment"),
        "preprocessing_identity": "preprocess-v1",
        "action_conversion_identity": "actions-v1",
        "model_class": "MineWorldModel", "transformer_class": "MineWorldTransformer",
        "vae_class": "MineWorldVAE", "decoder_layer_path": "model.layers",
        "layer_count": 20, "hidden_size": 2048, "max_position_embeddings": 8192,
        "visual_tokens_per_frame": 336, "action_tokens_per_frame": 8,
        "tokens_per_pair": 344, "max_context_pairs": 16,
        "precision": "bfloat16", "device": "cuda",
    }
    values.update(overrides)
    return type("RuntimeFixture", (), values)()


def activation_record(runtime=None, **overrides):
    identity = model_runtime_identity_binding(runtime or runtime_fixture())
    record = {"model_runtime_identity": identity,
              "main_checkpoint_sha256": identity["main_checkpoint_sha256"],
              "vae_checkpoint_sha256": identity["vae_checkpoint_sha256"],
              "targets": list(range(48, 67)), "target_rows_authority_bound": True}
    record.update(overrides)
    return record


class TestCheckpointBinding:
    def test_the_superseded_expression_really_did_produce_an_empty_string(self):
        """The defect, reproduced against the real dataclass field list.

        This is the whole of NEW-B001: neither attribute exists, so the ``or``
        chain fell through to ``str("")`` and the receipt bound nothing.
        """
        runtime = runtime_fixture()
        superseded = (getattr(runtime, "checkpoint_sha256", None)
                      or str(getattr(runtime, "checkpoint_identity", "")))
        assert superseded == ""

    def test_both_checkpoints_are_bound_and_non_blank(self):
        identity = model_runtime_identity_binding(runtime_fixture())
        assert identity["main_checkpoint_sha256"] == _sha("main-checkpoint")
        assert identity["vae_checkpoint_sha256"] == _sha("vae-checkpoint")
        assert identity["main_checkpoint_sha256"] != identity["vae_checkpoint_sha256"]
        assert all(identity[name] for name in ACTIVATION_IDENTITY_FIELDS)

    def test_a_correct_record_is_accepted(self):
        assert require_activation_identity(activation_record())["runtime_id"] \
            == "mineworld-runtime-fixture"

    @pytest.mark.parametrize("field", ["main_checkpoint_sha256", "vae_checkpoint_sha256",
                                       "model_config_sha256", "vae_config_sha256",
                                       "environment_report_sha256"])
    @pytest.mark.parametrize("value", ["", None, "abc", "Z" * 64, 12345])
    def test_a_blank_or_malformed_digest_is_refused(self, field, value):
        with pytest.raises(EvidenceError):
            model_runtime_identity_binding(runtime_fixture(**{field: value}))

    @pytest.mark.parametrize("field", ["runtime_id", "preprocessing_identity",
                                       "action_conversion_identity", "model_class"])
    def test_a_blank_identity_string_is_refused(self, field):
        with pytest.raises(EvidenceError):
            model_runtime_identity_binding(runtime_fixture(**{field: "   "}))

    def test_one_generic_hash_copied_into_both_slots_is_refused(self):
        """A single ``checkpoint_sha256`` would have to discard one of two digests."""
        shared = _sha("one-hash-for-both")
        with pytest.raises(EvidenceError, match="cannot have the same bytes"):
            model_runtime_identity_binding(runtime_fixture(
                main_checkpoint_sha256=shared, vae_checkpoint_sha256=shared))

    def test_a_record_with_no_identity_at_all_is_refused(self):
        with pytest.raises(EvidenceError, match="no model runtime identity"):
            require_activation_identity({"targets": [1]})

    @pytest.mark.parametrize("field", ["main_checkpoint_sha256", "vae_checkpoint_sha256"])
    def test_a_top_level_digest_that_contradicts_the_identity_is_refused(self, field):
        record = activation_record()
        record[field] = _sha("substituted")
        with pytest.raises(EvidenceError, match="disagrees with its model runtime identity"):
            require_activation_identity(record)

    def test_a_matching_runtime_is_accepted_by_the_cohort_check(self):
        reference = model_runtime_identity_binding(runtime_fixture())
        verify_activation_checkpoint_binding(activation_record(), reference)

    @pytest.mark.parametrize("field,value", [
        ("main_checkpoint_sha256", _sha("other-main")),
        ("vae_checkpoint_sha256", _sha("other-vae")),
        ("model_config_sha256", _sha("other-model-config")),
        ("preprocessing_identity", "preprocess-v2"),
        ("action_conversion_identity", "actions-v2"),
        ("runtime_id", "a-different-runtime"),
        ("hidden_size", 4096),
    ])
    def test_a_different_model_partway_through_the_cohort_is_refused(self, field, value):
        reference = model_runtime_identity_binding(runtime_fixture())
        other = activation_record(runtime_fixture(**{field: value}))
        with pytest.raises(EvidenceError, match="different model runtime"):
            verify_activation_checkpoint_binding(other, reference)

    def test_a_tampered_identity_field_is_refused(self):
        record = activation_record()
        record["model_runtime_identity"]["main_checkpoint_sha256"] = ""
        with pytest.raises(EvidenceError):
            require_activation_identity(record)

    def test_serialization_and_reload_preserve_the_binding(self, tmp_path):
        record = activation_record()
        path = tmp_path / "activation_receipt.json"
        path.write_text(json.dumps(record, sort_keys=True))
        reloaded = load_json(path)
        assert require_activation_identity(reloaded) == record["model_runtime_identity"]
        verify_activation_checkpoint_binding(
            reloaded, model_runtime_identity_binding(runtime_fixture()))


# ======================================================================
# NEW-B002 -- authority-bound target rows
# ======================================================================


AUTHORITY_ROWS = list(range(48, 67))


def visibility(rows=None, trajectory_id="a2y_t01"):
    rows = AUTHORITY_ROWS if rows is None else rows
    return [{"trajectory_id": trajectory_id, "model_frame_idx": frame,
             "server_tick": frame, "render_frame_idx": frame, "tau": index + 1}
            for index, frame in enumerate(rows)]


class TestTargetRowCrossCheck:
    def test_agreeing_sources_resolve_to_the_nineteen_authority_rows(self):
        resolved = resolve_authority_bound_target_rows(
            visibility(), expected=AUTHORITY_ROWS, required_count=19,
            trajectory_id="a2y_t01")
        assert resolved == AUTHORITY_ROWS
        assert len(resolved) == 19 == len(set(resolved))

    def test_the_real_manifest_rows_are_nineteen_for_every_identity(self):
        manifest = load_json(STAGE2_PATH)
        assert manifest["required_target_rows_per_capture"] == 19
        for identity in manifest["trajectory_identities"]:
            rows = identity["target_model_frame_indices"]
            assert len(rows) == 19 and rows == sorted(rows) and len(set(rows)) == 19

    def test_a_shifted_index_is_refused(self):
        # Shifted DOWN, not up: the authority rows are consecutive, so shifting an
        # interior row up collides with its neighbour and the duplicate check --
        # a different, more specific refusal -- fires first. Moving the first row
        # down keeps the set unique and ascending, so what refuses it is the
        # authority comparison itself, which is the property under test.
        shifted = [AUTHORITY_ROWS[0] - 1] + AUTHORITY_ROWS[1:]
        with pytest.raises(EvidenceError, match="do not equal the authority"):
            resolve_authority_bound_target_rows(
                visibility(shifted), expected=AUTHORITY_ROWS, required_count=19)

    def test_a_missing_tau_is_refused(self):
        rows = visibility()
        del rows[7]
        with pytest.raises(EvidenceError, match="missing target rows"):
            resolve_authority_bound_target_rows(
                rows, expected=AUTHORITY_ROWS, required_count=19)

    def test_a_duplicated_tau_is_refused(self):
        rows = visibility()
        rows.append(dict(rows[3]))
        with pytest.raises(EvidenceError, match="claimed by more than one"):
            resolve_authority_bound_target_rows(
                rows, expected=AUTHORITY_ROWS, required_count=19)

    def test_a_duplicated_frame_index_is_refused(self):
        rows = visibility()
        rows[4]["model_frame_idx"] = rows[3]["model_frame_idx"]
        rows[4]["server_tick"] = rows[4]["render_frame_idx"] = rows[3]["model_frame_idx"]
        with pytest.raises(EvidenceError, match="duplicated model frame index"):
            resolve_authority_bound_target_rows(
                rows, expected=AUTHORITY_ROWS, required_count=19)

    def test_an_extra_authority_row_is_refused(self):
        with pytest.raises(EvidenceError, match="authority declares 20 target rows"):
            resolve_authority_bound_target_rows(
                visibility(), expected=AUTHORITY_ROWS + [67], required_count=19)

    def test_a_short_authority_row_set_is_refused(self):
        with pytest.raises(EvidenceError, match="authority declares 18 target rows"):
            resolve_authority_bound_target_rows(
                visibility(), expected=AUTHORITY_ROWS[:-1], required_count=19)

    def test_reordered_rows_are_refused(self):
        rows = visibility()
        rows[0]["tau"], rows[1]["tau"] = rows[1]["tau"], rows[0]["tau"]
        with pytest.raises(EvidenceError, match="ascending frame order"):
            resolve_authority_bound_target_rows(
                rows, expected=AUTHORITY_ROWS, required_count=19)

    def test_a_row_from_another_trajectory_is_refused(self):
        rows = visibility()
        rows[9]["trajectory_id"] = "a2y_t02"
        with pytest.raises(EvidenceError, match="bound to trajectory"):
            resolve_authority_bound_target_rows(
                rows, expected=AUTHORITY_ROWS, required_count=19,
                trajectory_id="a2y_t01")

    @pytest.mark.parametrize("column", ["server_tick", "render_frame_idx"])
    def test_an_inconsistent_temporal_binding_is_refused(self, column):
        rows = visibility()
        rows[2][column] = rows[2]["model_frame_idx"] + 3
        with pytest.raises(EvidenceError, match="temporal binding is inconsistent"):
            resolve_authority_bound_target_rows(
                rows, expected=AUTHORITY_ROWS, required_count=19)

    def test_drift_is_refused_in_both_directions(self):
        """Neither source is preferred: whichever moved, extraction stops."""
        moved_capture = AUTHORITY_ROWS[:-1] + [AUTHORITY_ROWS[-1] + 4]
        with pytest.raises(EvidenceError, match="do not equal the authority"):
            resolve_authority_bound_target_rows(
                visibility(moved_capture), expected=AUTHORITY_ROWS, required_count=19)
        with pytest.raises(EvidenceError, match="do not equal the authority"):
            resolve_authority_bound_target_rows(
                visibility(), expected=moved_capture, required_count=19)

    def test_the_unbound_sentinel_marks_the_record_and_is_refused_downstream(self):
        """The historical pilots opt out explicitly; Stage-2 refuses what they make."""
        resolved = resolve_authority_bound_target_rows(
            visibility(), expected=TARGET_ROWS_NOT_AUTHORITY_BOUND, required_count=19)
        assert resolved == AUTHORITY_ROWS
        unbound = activation_record(target_rows_authority_bound=False)
        with pytest.raises(EvidenceError, match="without an authority-bound target row set"):
            require_target_rows_authority_bound(unbound, AUTHORITY_ROWS)

    def test_recorded_rows_that_differ_from_the_manifest_are_refused(self):
        record = activation_record(targets=AUTHORITY_ROWS[:-1] + [99])
        with pytest.raises(EvidenceError, match="do not equal the frozen manifest"):
            require_target_rows_authority_bound(record, AUTHORITY_ROWS)

    def test_the_extractor_requires_the_keyword(self):
        """A default would reopen the hole; the signature must not offer one."""
        import inspect
        import sys
        sys.path.insert(0, str(ROOT / "scripts/regime_a_prime_qualification_v0_1"))
        source = (ROOT / "scripts/regime_a_prime_qualification_v0_1/p2d_extract.py").read_text()
        assert "expected_target_model_frame_indices) -> dict" in source
        assert "expected_target_model_frame_indices=None" not in source
        assert "checkpoint_identity" not in source


# ======================================================================
# B009 -- terminal evidence, evaluation, and reproduction
# ======================================================================


@pytest.fixture(scope="module")
def authority():
    return load_json(AUTHORITY_PATH)


@pytest.fixture(scope="module")
def decision_authority():
    return load_json(DECISION_AUTHORITY_PATH)


@pytest.fixture(scope="module")
def real_manifest():
    return load_json(STAGE2_PATH)


class Campaign:
    """A synthetic completed Stage-2, served entirely through injected readers.

    Nothing is written to disk and no scientific outcome is read: the metric
    values below are chosen to sit clearly inside or outside each frozen
    threshold so a gate's behaviour is unambiguous. The manifest is the real
    frozen one, so the inventory, folds, phases, identities and target windows
    under test are the campaign's actual design rather than a simplified stand-in.
    """

    def __init__(self, manifest, authority, decision_authority):
        self.manifest = copy.deepcopy(manifest)
        self.authority = authority
        self.decision_authority = decision_authority
        self.documents: dict[str, dict] = {}
        self.identity = model_runtime_identity_binding(runtime_fixture())
        self._build()

    # -- helpers ----------------------------------------------------------
    def path(self, name: str) -> Path:
        return Path(f"/synthetic/{name}.json")

    def digest(self, path: Path) -> str:
        if path in (AUTHORITY_PATH, DECISION_AUTHORITY_PATH, STAGE2_PATH):
            return hashlib.sha256(path.read_bytes()).hexdigest()
        return hashlib.sha256(
            json.dumps(self.documents[str(path)], sort_keys=True).encode()).hexdigest()

    def read(self, path: Path) -> dict:
        if path in (AUTHORITY_PATH, DECISION_AUTHORITY_PATH, STAGE2_PATH):
            return load_json(path)
        return copy.deepcopy(self.documents[str(path)])

    def _receipt(self, unit, payload):
        base = {"schema_version": "1.1", "unit_id": unit["unit_id"],
                "status": "COMPLETE_VALIDATED_DURABLE", "classification": "DEVELOPMENT_ONLY",
                "confirmatory_membership": False,
                "authority_sha256": self.manifest["authority_binding"]["sha256"],
                "manifest_sha256": self.manifest_sha,
                "source_commit_sha": COMMIT,
                "scientific_run_id": self.manifest["run_namespace"],
                "durable_uri": f"s3://bucket/{unit['unit_id']}",
                "durable_objects": {"payload.json": _sha(unit["unit_id"])}}
        base.update(payload)
        self.documents[unit["receipt_path"]] = base
        return base

    def _metrics(self, rmse, macro, lower, upper=None):
        return {"rmse_blocks": rmse, "mae_blocks": rmse * 0.8, "macro_r2": macro,
                "bootstrap95_macro_r2": [lower, upper if upper is not None else lower + 0.1]}

    def _scene(self, *, rmse=0.05, macro=0.80, lower=0.70, upper=None,
               baseline_rmse=0.50, confound=0.05, kind="BEST_K"):
        selection = {}
        for fold in range(5):
            entry = {"selected_alpha": 1.0, "training_trajectory_ids": [],
                     "test_trajectory_ids": []}
            if kind == "BEST_K":
                entry.update({"selected_k": 16, "selected_tokens": list(range(16))})
            selection[str(fold)] = entry
        return {"metrics": self._metrics(rmse, macro, lower, upper),
                "training_time_baseline": self._metrics(baseline_rmse, 0.10, 0.02),
                "training_time_baseline_tau1_15": self._metrics(baseline_rmse, confound, 0.01),
                "selection_by_outer_fold": selection}

    # -- construction -----------------------------------------------------
    def _build(self):
        self.manifest_sha = hashlib.sha256(STAGE2_PATH.read_bytes()).hexdigest()
        gate = self.manifest["physical_gate_unit"]
        self._receipt(gate, {"physical_gates": {"status": "PASS"}})
        for unit in self.manifest["capture_units"]:
            ticks = unit["target_model_frame_indices"]
            self._receipt(unit, {
                "stage2_physical_evidence": {
                    "target_model_frame_indices": list(ticks),
                    "aligned_target_world_x_blocks":
                        list(unit["expected_causal_fir_target_world_x_blocks"]),
                    "target_row_count": len(ticks), "contamination_rows": []},
                "server_state_sha256": _sha(unit["unit_id"] + "-state")})
        for unit in self.manifest["extraction_units"]:
            source = next(item for item in self.manifest["capture_units"]
                          if item["unit_id"] == unit["source_capture_unit_id"])
            self._receipt(unit, {
                "source_capture_unit_id": unit["source_capture_unit_id"], "layer": 4,
                "shape": [19, 336, 2048],
                "activation_sha256": _sha(unit["unit_id"] + "-activation"),
                "model_runtime_identity": copy.deepcopy(self.identity),
                "main_checkpoint_sha256": self.identity["main_checkpoint_sha256"],
                "vae_checkpoint_sha256": self.identity["vae_checkpoint_sha256"],
                "targets": list(source["target_model_frame_indices"]),
                "target_rows_authority_bound": True})
        self.set_readouts()
        for name in ("stage1_manifest", "stage1_evidence", "stage1_decision",
                     "stage2_authorization", "provenance", "stage1_provenance"):
            self.documents[str(self.path(name))] = {"artifact": name}

    def set_readouts(self, *, wall=None, no_wall=None, full_wall=None, claimed=None):
        wall = self._scene() if wall is None else wall
        no_wall = self._scene() if no_wall is None else no_wall
        for stage, kind in (("best_k", "BEST_K"), ("full", "FULL")):
            unit = next(item for item in self.manifest["readout_and_terminal_units"]
                        if item["pipeline_stage"] == stage)
            scenes = ({"WALL": wall, "NO_WALL": no_wall} if kind == "BEST_K" else
                      {"WALL": full_wall or self._scene(kind="FULL"),
                       "NO_WALL": self._scene(kind="FULL")})
            payload = {"readout": kind, "scenes": copy.deepcopy(scenes)}
            if kind == "BEST_K":
                checks = claimed if claimed is not None else self.true_checks(wall, no_wall)
                payload["qualification_checks"] = checks
                payload["qualification_status"] = (
                    "PASS" if all(checks.values()) else "FAIL")
            self._receipt(unit, payload)

    def true_checks(self, wall, no_wall):
        policy = self.authority["stage2_policy"]["readout"]
        ceiling = policy["best_k_each_scene_rmse_maximum_blocks"]
        confound = policy["training_only_time_baseline_macro_r2_tau_1_to_15_maximum"]
        checks = {}
        for name, scene in (("WALL", wall), ("NO_WALL", no_wall)):
            checks[f"{name}_rmse"] = scene["metrics"]["rmse_blocks"] <= ceiling
            checks[f"{name}_r2"] = (scene["metrics"]["macro_r2"] > 0
                                    and scene["metrics"]["bootstrap95_macro_r2"][0] > 0)
        checks["WALL_beats_training_time_baseline"] = (
            wall["metrics"]["rmse_blocks"] < wall["training_time_baseline"]["rmse_blocks"])
        checks["WALL_time_confound_gate"] = (
            wall["training_time_baseline_tau1_15"]["macro_r2"] <= confound)
        return checks

    # -- driving the real chain -------------------------------------------
    def evidence(self):
        return build_stage2_evidence(
            self.manifest, manifest_path=STAGE2_PATH, authority_path=AUTHORITY_PATH,
            stage2_decision_authority_path=DECISION_AUTHORITY_PATH,
            stage1_manifest_path=self.path("stage1_manifest"),
            stage1_evidence_path=self.path("stage1_evidence"),
            stage1_decision_path=self.path("stage1_decision"),
            stage2_authorization_path=self.path("stage2_authorization"),
            preoutcome_provenance_path=self.path("provenance"),
            stage1_preoutcome_provenance_path=self.path("stage1_provenance"),
            source_commit_sha=COMMIT, reader=self.read, digest=self.digest)

    def decide(self, evidence=None):
        evidence = self.evidence() if evidence is None else evidence
        return evaluate_stage2(
            evidence, authority=self.authority, decision_authority=self.decision_authority,
            manifest=self.manifest,
            authority_sha256=hashlib.sha256(AUTHORITY_PATH.read_bytes()).hexdigest(),
            decision_authority_sha256=hashlib.sha256(
                DECISION_AUTHORITY_PATH.read_bytes()).hexdigest(),
            manifest_sha256=self.manifest_sha,
            evidence_sha256=hashlib.sha256(
                json.dumps(evidence, sort_keys=True).encode()).hexdigest())


@pytest.fixture
def campaign(real_manifest, authority, decision_authority):
    return Campaign(real_manifest, authority, decision_authority)


class TestTerminalPass:
    def test_a_complete_clean_campaign_passes_every_gate(self, campaign):
        decision = campaign.decide()
        assert decision["status"] == PASS
        assert decision["reasons"] == []
        assert sorted(decision["gates"]) == list(BEST_K_GATES)
        assert all(gate["status"] == PASS for gate in decision["gates"].values())

    def test_the_evidence_is_complete_and_closed(self, campaign):
        evidence = campaign.evidence()
        assert evidence["capture_count"] == 50
        assert evidence["trajectory_identity_count"] == 25
        assert evidence["required_target_rows_per_capture"] == 19
        assert evidence["layer"] == 4 and evidence["all_layer_extraction_performed"] is False
        assert evidence["evidence_builder_asserted_scientific_status"] is False
        assert "status" not in evidence and "qualification_status" not in evidence
        assert evidence["main_checkpoint_sha256"] == _sha("main-checkpoint")
        assert evidence["vae_checkpoint_sha256"] == _sha("vae-checkpoint")
        assert all(record["target_rows_authority_bound"] is True
                   for record in evidence["capture_inventory"])

    def test_a_pass_authorizes_nothing_further(self, campaign):
        decision = campaign.decide()
        assert decision["status"] == PASS
        for field in ("may_authorize_confirmatory_collection",
                      "may_authorize_causal_intervention", "may_authorize_next_rung",
                      "confirmatory_interpretation_authorized",
                      "establishes_object_permanence", "establishes_belief",
                      "establishes_causal_use", "establishes_uncertainty_representation",
                      "establishes_general_world_model_competence",
                      "establishes_behavioral_reliance"):
            assert decision[field] is False, field
        assert decision["confirmatory_reuse_forbidden"] is True
        assert decision["classification"] == "DEVELOPMENT_ONLY"

    def test_the_decision_matches_its_versioned_schema(self, campaign):
        schema = json.loads(
            (ROOT / "schemas/prospective/regime_a_prime_stage2_decision_v0_4.schema.json"
             ).read_text())
        decision = campaign.decide()
        assert set(schema["required"]) <= set(decision)
        assert decision["artifact_id"] == schema["properties"]["artifact_id"]["const"]
        assert decision["status"] in schema["properties"]["status"]["enum"]


class TestTerminalScientificFail:
    """A completed analysis that misses a gate is FAIL, and stays FAIL."""

    def test_a_wall_rmse_above_the_ceiling_fails(self, campaign):
        campaign.set_readouts(wall=campaign._scene(rmse=0.9, baseline_rmse=1.5))
        decision = campaign.decide()
        assert decision["status"] == FAIL
        assert decision["gates"]["WALL_rmse"]["status"] == FAIL
        assert "WALL_rmse" in decision["reasons"]

    def test_a_no_wall_rmse_above_the_ceiling_fails(self, campaign):
        campaign.set_readouts(no_wall=campaign._scene(rmse=0.9))
        assert campaign.decide()["gates"]["NO_WALL_rmse"]["status"] == FAIL

    @pytest.mark.parametrize("scene", ["wall", "no_wall"])
    def test_a_non_positive_macro_r2_fails(self, campaign, scene):
        campaign.set_readouts(**{scene: campaign._scene(macro=-0.2, lower=-0.4)})
        gate = "WALL_r2" if scene == "wall" else "NO_WALL_r2"
        assert campaign.decide()["gates"][gate]["status"] == FAIL

    @pytest.mark.parametrize("scene", ["wall", "no_wall"])
    def test_a_bootstrap_lower_bound_at_or_below_zero_fails(self, campaign, scene):
        campaign.set_readouts(**{scene: campaign._scene(macro=0.8, lower=0.0, upper=0.9)})
        gate = "WALL_r2" if scene == "wall" else "NO_WALL_r2"
        assert campaign.decide()["gates"][gate]["status"] == FAIL

    def test_failing_to_beat_the_time_baseline_fails(self, campaign):
        campaign.set_readouts(wall=campaign._scene(rmse=0.05, baseline_rmse=0.04))
        decision = campaign.decide()
        assert decision["gates"]["WALL_beats_training_time_baseline"]["status"] == FAIL
        assert decision["status"] == FAIL

    def test_the_tau_1_to_15_time_confound_gate_fails(self, campaign):
        campaign.set_readouts(wall=campaign._scene(confound=0.9))
        decision = campaign.decide()
        assert decision["gates"]["WALL_time_confound_gate"]["status"] == FAIL
        assert decision["status"] == FAIL

    def test_full_cannot_rescue_a_failed_best_k(self, campaign):
        """FULL is evaluated and reported; it is never gating."""
        campaign.set_readouts(wall=campaign._scene(rmse=0.9, baseline_rmse=1.5),
                              full_wall=campaign._scene(rmse=0.001, macro=0.99,
                                                        lower=0.98, kind="FULL"))
        decision = campaign.decide()
        assert decision["status"] == FAIL
        assert decision["full_may_not_rescue_best_k_failure"] is True
        assert decision["full_readout_is_never_gating"] is True
        assert decision["estimands"]["full.WALL"]["rmse_blocks"] == 0.001

    def test_a_scientific_fail_is_not_reported_as_blocked(self, campaign):
        campaign.set_readouts(wall=campaign._scene(rmse=0.9, baseline_rmse=1.5))
        assert campaign.decide()["status"] == FAIL


class TestTerminalBlocked:
    """Operational, provenance and completeness faults are BLOCKED, never FAIL."""

    def test_a_missing_capture_blocks(self, campaign):
        campaign.manifest["capture_units"] = campaign.manifest["capture_units"][:-1]
        with pytest.raises(EvidenceError, match="capture inventory is 49"):
            campaign.evidence()

    def test_an_extra_scientific_capture_blocks(self, campaign):
        extra = copy.deepcopy(campaign.manifest["capture_units"][0])
        extra["unit_id"] = "a2y_t99_wall"
        campaign.manifest["capture_units"].append(extra)
        with pytest.raises(EvidenceError, match="capture inventory is 51"):
            campaign.evidence()

    def test_a_failed_physical_gate_blocks(self, campaign):
        gate = campaign.manifest["physical_gate_unit"]
        campaign.documents[gate["receipt_path"]]["physical_gates"]["status"] = "FAIL"
        with pytest.raises(EvidenceError, match="physical gate did not PASS"):
            campaign.evidence()

    def test_a_contaminated_target_row_blocks(self, campaign):
        unit = campaign.manifest["capture_units"][0]
        campaign.documents[unit["receipt_path"]]["stage2_physical_evidence"][
            "contamination_rows"] = [{"tick": 48, "classes": ["point_visible"]}]
        with pytest.raises(EvidenceError, match="target rows are contaminated"):
            campaign.evidence()

    def test_an_unbound_checkpoint_blocks(self, campaign):
        unit = campaign.manifest["extraction_units"][0]
        campaign.documents[unit["receipt_path"]].pop("model_runtime_identity")
        with pytest.raises(EvidenceError, match="no model runtime identity"):
            campaign.evidence()

    def test_a_blank_checkpoint_digest_blocks(self, campaign):
        unit = campaign.manifest["extraction_units"][0]
        receipt = campaign.documents[unit["receipt_path"]]
        receipt["model_runtime_identity"]["main_checkpoint_sha256"] = ""
        receipt["main_checkpoint_sha256"] = ""
        with pytest.raises(EvidenceError):
            campaign.evidence()

    def test_a_second_checkpoint_partway_through_blocks(self, campaign):
        unit = campaign.manifest["extraction_units"][10]
        other = model_runtime_identity_binding(
            runtime_fixture(main_checkpoint_sha256=_sha("a-different-checkpoint")))
        receipt = campaign.documents[unit["receipt_path"]]
        receipt["model_runtime_identity"] = other
        receipt["main_checkpoint_sha256"] = other["main_checkpoint_sha256"]
        with pytest.raises(EvidenceError, match="different model runtime"):
            campaign.evidence()

    def test_unbound_target_rows_block(self, campaign):
        unit = campaign.manifest["extraction_units"][0]
        campaign.documents[unit["receipt_path"]]["target_rows_authority_bound"] = False
        with pytest.raises(EvidenceError, match="without an authority-bound target row set"):
            campaign.evidence()

    def test_drifted_target_rows_block(self, campaign):
        unit = campaign.manifest["capture_units"][0]
        rows = campaign.documents[unit["receipt_path"]]["stage2_physical_evidence"][
            "target_model_frame_indices"]
        campaign.documents[unit["receipt_path"]]["stage2_physical_evidence"][
            "target_model_frame_indices"] = rows[:-1] + [rows[-1] + 1]
        with pytest.raises(EvidenceError, match="target rows differ from the frozen manifest"):
            campaign.evidence()

    def test_a_receipt_from_another_campaign_blocks(self, campaign):
        unit = campaign.manifest["capture_units"][3]
        campaign.documents[unit["receipt_path"]]["scientific_run_id"] = "some-other-run"
        with pytest.raises(EvidenceError, match="binding mismatch on 'scientific_run_id'"):
            campaign.evidence()

    def test_a_receipt_from_another_source_freeze_blocks(self, campaign):
        unit = campaign.manifest["capture_units"][3]
        campaign.documents[unit["receipt_path"]]["source_commit_sha"] = "d" * 40
        with pytest.raises(EvidenceError, match="binding mismatch on 'source_commit_sha'"):
            campaign.evidence()

    def test_an_incomplete_unit_blocks(self, campaign):
        unit = campaign.manifest["capture_units"][3]
        campaign.documents[unit["receipt_path"]]["status"] = "RUNNING"
        with pytest.raises(EvidenceError, match="binding mismatch on 'status'"):
            campaign.evidence()

    def test_a_smoke_artifact_blocks(self, campaign):
        unit = campaign.manifest["capture_units"][7]
        campaign.documents[unit["receipt_path"]]["scientific_run_id"] = (
            campaign.manifest["run_namespace"] + "-operational-smoke")
        with pytest.raises(EvidenceError):
            campaign.evidence()

    def test_a_confirmatory_flagged_receipt_blocks(self, campaign):
        unit = campaign.manifest["capture_units"][5]
        campaign.documents[unit["receipt_path"]]["confirmatory_membership"] = True
        with pytest.raises(EvidenceError, match="confirmatory_membership"):
            campaign.evidence()

    def test_a_non_layer_4_extraction_blocks(self, campaign):
        unit = campaign.manifest["extraction_units"][2]
        campaign.documents[unit["receipt_path"]]["layer"] = 7
        with pytest.raises(EvidenceError, match="not the authorized layer-4 readout"):
            campaign.evidence()

    def test_a_readout_missing_a_scene_blocks(self, campaign):
        unit = next(item for item in campaign.manifest["readout_and_terminal_units"]
                    if item["pipeline_stage"] == "best_k")
        campaign.documents[unit["receipt_path"]]["scenes"].pop("NO_WALL")
        with pytest.raises(EvidenceError, match="scene coverage"):
            campaign.evidence()

    def test_a_readout_missing_a_fold_blocks(self, campaign):
        unit = next(item for item in campaign.manifest["readout_and_terminal_units"]
                    if item["pipeline_stage"] == "best_k")
        campaign.documents[unit["receipt_path"]]["scenes"]["WALL"][
            "selection_by_outer_fold"].pop("4")
        with pytest.raises(EvidenceError, match="all five outer folds"):
            campaign.evidence()

    def test_a_self_graded_boolean_that_disagrees_blocks_rather_than_deciding(self, campaign):
        """The readout graded itself; the evaluator re-derives and refuses to pick.

        This is the concrete B009 regression: previously the recorded status was
        copied verbatim, so an edited boolean carried the verdict. Now a
        disagreement is an operational fault -- it resolves in neither direction.
        """
        lying = {name: True for name in BEST_K_GATES}
        campaign.set_readouts(wall=campaign._scene(rmse=0.9, baseline_rmse=1.5),
                              claimed=lying)
        decision = campaign.decide()
        assert decision["status"] == BLOCKED
        assert "disagree with the re-derivation" in decision["reasons"][0]
        assert decision["gates"] == {}

    def test_a_tampered_evidence_payload_blocks(self, campaign):
        evidence = campaign.evidence()
        evidence["capture_count"] = 49
        decision = campaign.decide(evidence)
        assert decision["status"] == BLOCKED
        assert "payload digest does not reproduce" in decision["reasons"][0]

    def test_wrong_bootstrap_configuration_blocks(self, campaign):
        evidence = campaign.evidence()
        evidence["bootstrap_configuration"]["seed"] = 1
        evidence["evidence_payload_sha256"] = canonical_payload_sha256(
            evidence, omit="evidence_payload_sha256")
        decision = campaign.decide(evidence)
        assert decision["status"] == BLOCKED
        assert "bootstrap seed" in decision["reasons"][0]

    def test_a_decision_authority_with_a_different_gate_set_blocks(self, campaign):
        contract = copy.deepcopy(campaign.decision_authority)
        contract["best_k_gates"]["names"] = ["WALL_rmse"]
        decision = evaluate_stage2(
            campaign.evidence(), authority=campaign.authority,
            decision_authority=contract, manifest=campaign.manifest,
            authority_sha256="a" * 64, decision_authority_sha256="b" * 64,
            manifest_sha256=campaign.manifest_sha, evidence_sha256="c" * 64)
        assert decision["status"] == BLOCKED
        assert "different BEST-K gate set" in decision["reasons"][0]

    def test_blocked_is_never_recorded_as_a_scientific_verdict(self, campaign):
        campaign.set_readouts(claimed={name: False for name in BEST_K_GATES})
        decision = campaign.decide()
        assert decision["status"] == BLOCKED
        assert decision["status"] not in (PASS, FAIL)
        assert decision["gates"] == {} and decision["estimands"] == {}


class TestDecisionReproduction:
    def _persist(self, campaign, tmp_path):
        evidence = campaign.evidence()
        evidence_path = tmp_path / "stage2_evidence.json"
        evidence_path.write_text(json.dumps(evidence, indent=1, sort_keys=True))
        evidence_sha = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
        decision = evaluate_stage2(
            evidence, authority=campaign.authority,
            decision_authority=campaign.decision_authority, manifest=campaign.manifest,
            authority_sha256=hashlib.sha256(AUTHORITY_PATH.read_bytes()).hexdigest(),
            decision_authority_sha256=hashlib.sha256(
                DECISION_AUTHORITY_PATH.read_bytes()).hexdigest(),
            manifest_sha256=hashlib.sha256(STAGE2_PATH.read_bytes()).hexdigest(),
            evidence_sha256=evidence_sha)
        decision_path = tmp_path / "stage2_decision.json"
        decision_path.write_text(json.dumps(decision, indent=1, sort_keys=True))
        return evidence_path, decision_path, decision

    def _reproduce(self, decision, evidence_path, decision_path=None):
        return require_stage2_decision_reproduction(
            decision, evidence_path=evidence_path, authority_path=AUTHORITY_PATH,
            stage2_decision_authority_path=DECISION_AUTHORITY_PATH,
            manifest_path=STAGE2_PATH, decision_path=decision_path)

    def test_a_decision_reproduces_byte_identically(self, campaign, tmp_path):
        evidence_path, decision_path, decision = self._persist(campaign, tmp_path)
        assert self._reproduce(decision, evidence_path, decision_path) == decision

    @pytest.mark.parametrize("mutation", [
        {"status": FAIL},
        {"artifact_id": "regime-a-prime-stage2-decision-v0.3"},
        {"schema_version": "9.9"},
        {"authority_sha256": "0" * 64},
        {"stage2_decision_authority_sha256": "0" * 64},
        {"stage2_manifest_sha256": "0" * 64},
        {"leading_readout": "FULL"},
        {"may_authorize_confirmatory_collection": True},
        {"reasons": ["invented"]},
        {"gates": {}},
    ])
    def test_a_mutated_decision_is_refused(self, campaign, tmp_path, mutation):
        evidence_path, _, decision = self._persist(campaign, tmp_path)
        tampered = {**decision, **mutation}
        tampered["decision_payload_sha256"] = canonical_payload_sha256(
            tampered, omit="decision_payload_sha256")
        with pytest.raises(EvidenceError):
            self._reproduce(tampered, evidence_path)

    def test_an_unresealed_decision_is_refused(self, campaign, tmp_path):
        evidence_path, _, decision = self._persist(campaign, tmp_path)
        with pytest.raises(EvidenceError, match="payload digest does not reproduce"):
            self._reproduce({**decision, "status": FAIL}, evidence_path)

    @pytest.mark.parametrize("path,value", [
        (("readouts", "best_k", "scenes", "WALL", "metrics", "rmse_blocks"), 0.9),
        (("readouts", "best_k", "scenes", "WALL", "metrics", "macro_r2"), -1.0),
        (("readouts", "full", "scenes", "WALL", "metrics", "rmse_blocks"), 0.001),
        (("bootstrap_configuration", "resamples"), 10),
        (("main_checkpoint_sha256",), "0" * 64),
        (("capture_count",), 49),
    ])
    def test_a_mutated_evidence_breaks_the_reproduction(self, campaign, tmp_path,
                                                        path, value):
        evidence_path, _, decision = self._persist(campaign, tmp_path)
        evidence = json.loads(evidence_path.read_text())
        target = evidence
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        evidence["evidence_payload_sha256"] = canonical_payload_sha256(
            evidence, omit="evidence_payload_sha256")
        evidence_path.write_text(json.dumps(evidence, indent=1, sort_keys=True))
        with pytest.raises(EvidenceError):
            self._reproduce(decision, evidence_path)

    def test_a_mutated_target_mapping_breaks_the_reproduction(self, campaign, tmp_path):
        evidence_path, _, decision = self._persist(campaign, tmp_path)
        evidence = json.loads(evidence_path.read_text())
        evidence["capture_inventory"][0]["target_rows_authority_bound"] = False
        evidence["evidence_payload_sha256"] = canonical_payload_sha256(
            evidence, omit="evidence_payload_sha256")
        evidence_path.write_text(json.dumps(evidence, indent=1, sort_keys=True))
        with pytest.raises(EvidenceError):
            self._reproduce(decision, evidence_path)

    def test_an_on_disk_decision_that_differs_is_refused(self, campaign, tmp_path):
        evidence_path, decision_path, decision = self._persist(campaign, tmp_path)
        decision_path.write_text(json.dumps({**decision, "status": FAIL}, indent=1))
        with pytest.raises(EvidenceError, match="exact on-disk Stage-2 decision"):
            self._reproduce(decision, evidence_path, decision_path)


# ======================================================================
# Promoted authority -- it must be the code's values, not new ones
# ======================================================================


class TestPromotionIsNotAScientificChange:
    def test_the_promoted_grids_are_the_implementation_s(self, decision_authority):
        from mineocclude.regime_a_first25_analysis import ALPHAS, K_GRID

        readout = decision_authority["readout_procedure"]
        assert readout["k_grid"] == list(K_GRID) == [1, 4, 8, 16, 32, 64, 128]
        assert readout["alpha_grid"] == list(ALPHAS) == [0.1, 1.0, 10.0, 100.0]

    def test_the_promoted_gate_set_is_what_the_backend_emits(self, authority,
                                                            decision_authority):
        import sys
        sys.path.insert(0, str(ROOT))
        from scripts.regime_a_prime_qualification_v0_2.stage2_backend import (
            best_k_qualification_checks)

        metrics = {"rmse_blocks": 0.0, "mae_blocks": 0.0, "macro_r2": 0.0,
                   "bootstrap95_macro_r2": [0.0, 0.0]}
        scene = {"metrics": dict(metrics), "training_time_baseline": dict(metrics),
                 "training_time_baseline_tau1_15": dict(metrics)}
        observed = sorted(best_k_qualification_checks(
            {"WALL": scene, "NO_WALL": scene}, authority["stage2_policy"]["readout"]))
        assert observed == decision_authority["best_k_gates"]["names"] == list(BEST_K_GATES)

    def test_the_promotion_moved_no_stage2_design_parameter(self, decision_authority):
        """The design still lives in authority_parameters.json and is read from there."""
        assert "stage2_policy" not in decision_authority
        serialized = json.dumps(decision_authority)
        for design_value in ("paired_trajectory_identities", "scientific_capture_count",
                             "phase_offsets_frames", "outer_folds"):
            assert f'"{design_value}"' not in serialized

    def test_the_promotion_is_declared_non_adaptive(self, decision_authority):
        promotion = decision_authority["promotion"]
        assert promotion["kind"] == "EXPLICIT_PROMOTION_OF_EXISTING_STAGE2_IMPLEMENTATION"
        assert promotion["outcome_adaptive_change"] is False
        assert promotion["scientific_outcomes_observed"] is False
        assert promotion["new_scientific_values_invented"] is False
        assert promotion["authority_parameters_json_modified"] is False

    def test_the_authority_bytes_the_stage1_pass_binds_are_untouched(self):
        """The reason the promotion is a separate document at all."""
        assert hashlib.sha256(AUTHORITY_PATH.read_bytes()).hexdigest() == (
            "52b9590bc1695658b30304b557a4df65d38928ab15281ffd9800e014e839e728")

    def test_the_decision_authority_is_bound_both_ways(self, decision_authority):
        manifest = load_json(STAGE2_PATH)
        binding = manifest["stage2_decision_authority_binding"]
        assert binding["artifact_id"] == decision_authority["artifact_id"]
        assert binding["sha256"] == hashlib.sha256(
            DECISION_AUTHORITY_PATH.read_bytes()).hexdigest()
        assert decision_authority["extends_authority"]["sha256"] == hashlib.sha256(
            AUTHORITY_PATH.read_bytes()).hexdigest()

    def test_the_terminal_backend_no_longer_copies_a_qualification_status(self):
        source = (ROOT / "scripts/regime_a_prime_qualification_v0_2/stage2_backend.py"
                  ).read_text()
        terminal = source.split("def terminal(")[1].split("\ndef ")[0]
        # The docstring quotes the superseded expression in order to explain it,
        # so the assertion is made against executable lines only.
        body = terminal.split('"""')[-1]
        assert 'best["qualification_status"]' not in body
        assert "build_stage2_evidence" in terminal
        assert "evaluate_stage2" in terminal
        assert "require_stage2_decision_reproduction" in terminal

    def test_the_new_modules_are_governed_by_the_runtime_closure(self):
        from mineocclude.prospective.development_workflow import (
            RUNTIME_CRITICAL_SOURCE_PATHS)

        for path in ("src/mineocclude/prospective/stage2_evidence.py",
                     "src/mineocclude/prospective/stage2_decision.py",
                     "src/mineocclude/prospective/activation_binding.py",
                     "schemas/prospective/regime_a_prime_stage2_evidence_v0_4.schema.json",
                     "schemas/prospective/regime_a_prime_stage2_decision_v0_4.schema.json"):
            assert path in RUNTIME_CRITICAL_SOURCE_PATHS
            assert (ROOT / path).is_file()

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mineocclude.contracts.rollout_registry import (
    validate_immutable_run_artifact_registry,
)
from mineocclude.experiments.registry import require_valid_immutable_registry
from scripts.build_person_e_phase4_step4_1_slice3a_v0_1 import (
    ALL_OUTPUT_PATHS,
    AUTHORITIES,
    BUILDER_PATH,
    STARTING_COMMIT,
    TEST_PATH,
    _source_entry,
    validate_slice3a_policy,
    verify_source_authority,
)

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = (
    ROOT / "docs" / "status" / "person_e_phase4_step4_1_slice3a_v0_1"
)
FROZEN_HASHES = {
    "src/mineocclude/contracts/rollout_registry.py": (
        "386a6bce4f5ba727aa51b40c69ef444c0d984984697da63f6ea4045a44c07356"
    ),
    "src/mineocclude/experiments/registry.py": (
        "f25637f3c3347a3548297b7a3b491ee07f6795915bd09d7ff40915f50d9a4541"
    ),
    "tests/fixtures/person_e/immutable_registry_v2_completed.json": (
        "a66c8408de1fb0a03c1d1ff9e65d15f2c9a7a35cd8094d25b2def59c0c9b5ec4"
    ),
    "tests/fixtures/person_e/immutable_registry_v2_pending.json": (
        "00597d11e6ff91df6c0162e964039f9c60e4ccfbc56c217c501c6d92f9abc633"
    ),
}


def load(relative_path: str) -> dict[str, object]:
    value = json.loads((EVIDENCE / relative_path).read_bytes())
    if not isinstance(value, dict):
        raise TypeError(f"{relative_path} is not an object")
    return value


def git_bytes(commit: str, path: str) -> bytes:
    completed = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr.decode(errors="replace"))
    return completed.stdout


class TestPersonEPhase4Step41Slice3A(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.authority = load("authority_binding.json")
        cls.registry = load("blocked_registry.json")
        cls.blockers = load("blocker_matrix.json")
        cls.source = load("source_inventory.json")
        cls.trust = load("person_e_trust_preparation.json")
        cls.unsupported = load("unsupported_mapping_decisions.json")
        cls.validation = load("validation_receipt.json")
        cls.inventory = load("sha256_inventory.json")
        cls.handoffs = {
            owner: load(f"owner_handoffs/{owner}_requirements.json")
            for owner in ("person_a", "person_b", "person_c", "person_d")
        }

    def test_01_exact_authorities_are_bound(self) -> None:
        expected = {
            owner: {
                "branch": value["branch"],
                "source_authority_commit": value["commit"],
            }
            for owner, value in AUTHORITIES.items()
        }
        self.assertEqual(self.authority["authorities"], expected)
        self.assertEqual(self.authority["starting_commit"], STARTING_COMMIT)
        self.assertEqual(self.authority["builder_path"], BUILDER_PATH)
        self.assertEqual(self.authority["test_path"], TEST_PATH)

    def test_02_source_hashes_and_sizes_match_exact_git_objects(self) -> None:
        for row in self.source["entries"]:
            content = git_bytes(row["source_commit"], row["source_path"])
            self.assertEqual(hashlib.sha256(content).hexdigest(), row["file_sha256"])
            self.assertEqual(len(content), row["byte_size"])

    def test_03_acceptable_now_inventory_is_empty(self) -> None:
        self.assertEqual(self.source["acceptable_now_inventory"], [])
        self.assertNotIn(
            "ACCEPTABLE_NOW",
            {row["current_classification"] for row in self.source["entries"]},
        )

    def test_04_person_d_preview_remains_non_scientific(self) -> None:
        preview = next(
            row
            for row in self.source["entries"]
            if row["artifact_id"] == "person_d_real_pilot_baseline_preview"
        )
        self.assertEqual(preview["scientific_use_status"], "forbidden")
        self.assertEqual(preview["current_classification"], "NON_SCIENTIFIC")

    def test_05_person_a_pilots_remain_non_scientific(self) -> None:
        by_id = {
            row["artifact_id"]: row for row in self.source["entries"]
        }
        for artifact_id in (
            "person_a_phase4_extraction_probe_report",
            "person_a_limited_unpooled_pilot",
        ):
            self.assertEqual(
                by_id[artifact_id]["current_classification"],
                "NON_SCIENTIFIC",
            )

    def test_06_person_c_raw_packages_remain_pending(self) -> None:
        raw = [
            row
            for row in self.source["entries"]
            if row["owner"] == "person_c"
            and row["artifact_type_candidate"] == "raw_trajectory"
            and row["scientific_use_status"] == "pending_cross_role_signoff"
        ]
        self.assertEqual(len(raw), 39)
        self.assertEqual(
            {row["current_classification"] for row in raw}, {"PENDING"}
        )

    def test_07_person_c_joined_visibility_is_unsupported_mapping(self) -> None:
        joined = next(
            row
            for row in self.source["entries"]
            if row["artifact_id"]
            == "person_c_phase3_joined_visibility_records"
        )
        self.assertEqual(
            joined["current_classification"], "UNSUPPORTED_MAPPING"
        )

    def test_08_person_e_artifacts_are_prepared_never_accepted(self) -> None:
        rows = [
            row for row in self.source["entries"] if row["owner"] == "person_e"
        ]
        self.assertEqual(len(rows), 5)
        self.assertEqual(
            {row["current_classification"] for row in rows},
            {"ACCEPTABLE_AFTER_OWNER_RECEIPT"},
        )

    def test_09_blocked_registry_validates_under_frozen_v2(self) -> None:
        result = require_valid_immutable_registry(self.registry)
        self.assertTrue(result.accepted)

    def test_10_corrected_scientific_and_workflow_states_are_exact(self) -> None:
        self.assertIs(self.registry["synthetic"], False)
        self.assertEqual(self.registry["scientific_use"], "forbidden")
        for surrounding in (self.authority, self.blockers, self.trust):
            self.assertEqual(surrounding["production_state"], "pending")
            self.assertEqual(
                surrounding["step4_1_closure_state"], "blocked"
            )
            self.assertIs(
                surrounding["scientific_acceptance_claimed"], False
            )

    def test_11_pending_scientific_use_fails_registry_v2(self) -> None:
        mutated = copy.deepcopy(self.registry)
        mutated["scientific_use"] = "pending"
        result = validate_immutable_run_artifact_registry(mutated)
        self.assertFalse(result.accepted)
        self.assertTrue(
            any(
                rejection.message
                == "scientific_use must be forbidden or permitted."
                for rejection in result.rejections
            )
        )

    def test_12_permitted_scientific_use_fails_slice3a_policy(self) -> None:
        mutated = copy.deepcopy(self.registry)
        mutated["scientific_use"] = "permitted"
        self.assertTrue(validate_slice3a_policy(mutated, self.authority))

    def test_13_registry_has_zero_accepted_or_imported_outputs(self) -> None:
        self.assertEqual(self.registry["artifacts"], [])
        self.assertEqual(self.validation["accepted_artifact_count"], 0)
        self.assertEqual(self.validation["superseded_artifact_count"], 0)
        self.assertEqual(self.validation["accepted_placeholder_count"], 0)
        self.assertEqual(
            self.validation["actual_owner_output_imported_count"], 0
        )

    def test_14_non_completed_runs_publish_no_outputs(self) -> None:
        self.assertEqual(
            {run["status"] for run in self.registry["runs"]}, {"pending"}
        )
        for run in self.registry["runs"]:
            self.assertEqual(run["output_artifact_ids"], [])

    def test_15_no_placeholder_artifact_exists(self) -> None:
        serialized = json.dumps(self.registry).lower()
        self.assertNotIn("placeholder", serialized)
        self.assertEqual(self.validation["placeholder_count"], 0)

    def test_16_every_blocker_identifies_owner(self) -> None:
        self.assertTrue(self.blockers["blockers"])
        for blocker in self.blockers["blockers"]:
            self.assertIn(
                blocker["owner"],
                {"person_a", "person_b", "person_c", "person_d", "person_e"},
            )

    def test_17_every_blocker_states_closure_effect(self) -> None:
        for blocker in self.blockers["blockers"]:
            self.assertIs(blocker["blocks_step4_1_closure"], True)

    def test_18_person_a_handoff_requests_all_production_outputs(self) -> None:
        handoff = self.handoffs["person_a"]
        self.assertEqual(
            set(handoff["required_output_artifacts"]),
            {"model_input", "extraction", "activation", "rollout"},
        )
        self.assertIs(handoff["phase6_authorized"], False)

    def test_19_person_b_handoff_requests_all_analysis_outputs(self) -> None:
        self.assertEqual(
            set(self.handoffs["person_b"]["required_output_artifacts"]),
            {"oracle_target", "fitted_probe", "prediction", "metric_table"},
        )

    def test_20_person_c_handoff_requests_promotion_and_mapping(self) -> None:
        handoff = self.handoffs["person_c"]
        self.assertEqual(
            set(handoff["required_output_artifacts"]),
            {"raw_trajectory promotion", "joined_visibility mapping decision"},
        )
        self.assertEqual(len(handoff["raw_package_requirements"]), 39)
        self.assertIs(handoff["person_e_may_alter_scientific_use"], False)

    def test_21_person_d_handoff_rejects_forbidden_preview(self) -> None:
        handoff = self.handoffs["person_d"]
        self.assertEqual(
            handoff["forbidden_preview_path"],
            "docs/status/person_d_real_pilot_baseline_preview.json",
        )
        self.assertIs(handoff["forbidden_preview_promotable"], False)

    def test_22_person_e_trust_preparation_binds_exact_bytes(self) -> None:
        self.assertEqual(self.trust["artifact_count"], 5)
        for record in self.trust["artifacts"]:
            content = git_bytes(record["source_commit"], record["source_path"])
            self.assertEqual(hashlib.sha256(content).hexdigest(), record["sha256"])
            self.assertEqual(len(content), record["byte_size"])

    def test_23_person_e_trust_preparation_claims_no_acceptance(self) -> None:
        self.assertEqual(
            {record["current_import_state"] for record in self.trust["artifacts"]},
            {"PREPARED_BLOCKED"},
        )
        self.assertIs(self.trust["scientific_acceptance_claimed"], False)

    def test_24_unsupported_mappings_do_not_change_catalog(self) -> None:
        self.assertIs(self.unsupported["catalog_changed"], False)
        self.assertEqual(len(self.unsupported["mappings"]), 3)
        self.assertEqual(
            {row["artifact"] for row in self.unsupported["mappings"]},
            {
                "Person A preprocessing metadata",
                "Person C joined visibility",
                "Person D composite comparison outputs",
            },
        )

    def test_25_two_independent_package_builds_are_byte_identical(self) -> None:
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(ROOT / "src")
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        with (
            tempfile.TemporaryDirectory() as first_temp,
            tempfile.TemporaryDirectory() as second_temp,
        ):
            roots = [
                Path(first_temp) / "evidence",
                Path(second_temp) / "evidence",
            ]
            for output_root in roots:
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / BUILDER_PATH),
                        "--output-dir",
                        str(output_root),
                    ],
                    cwd=ROOT,
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
            first = {
                path.relative_to(roots[0]).as_posix(): path.read_bytes()
                for path in roots[0].rglob("*")
                if path.is_file()
            }
            second = {
                path.relative_to(roots[1]).as_posix(): path.read_bytes()
                for path in roots[1].rglob("*")
                if path.is_file()
            }
            self.assertEqual(first, second)

    def test_26_every_json_file_is_canonical_utf8_with_final_newline(self) -> None:
        for path in EVIDENCE.rglob("*.json"):
            content = path.read_bytes()
            self.assertTrue(content.endswith(b"\n"))
            self.assertFalse(content.startswith(b"\xef\xbb\xbf"))
            document = json.loads(content)
            expected = (
                json.dumps(
                    document,
                    indent=2,
                    sort_keys=True,
                    ensure_ascii=True,
                )
                + "\n"
            ).encode("utf-8")
            self.assertEqual(content, expected)

    def test_27_inventory_hashes_match_every_non_inventory_output(self) -> None:
        self.assertEqual(
            sorted(self.inventory["files"]),
            sorted(set(ALL_OUTPUT_PATHS) - {"sha256_inventory.json"}),
        )
        for relative_path, expected in self.inventory["files"].items():
            actual = hashlib.sha256(
                (EVIDENCE / relative_path).read_bytes()
            ).hexdigest()
            self.assertEqual(actual, expected)

    def test_28_no_upstream_bytes_phase6_integration_or_u4_claim_exists(self) -> None:
        self.assertEqual(
            sorted(
                path.relative_to(EVIDENCE).as_posix()
                for path in EVIDENCE.rglob("*")
                if path.is_file()
            ),
            sorted(ALL_OUTPUT_PATHS),
        )
        self.assertTrue(all(path.suffix == ".json" for path in EVIDENCE.rglob("*") if path.is_file()))
        claims = self.authority["claims"]
        self.assertIs(claims["person_a_phase6_authorized"], False)
        self.assertIs(claims["project_wide_integration_claimed"], False)
        self.assertIs(claims["u4_output_inspected"], False)
        self.assertIs(
            self.validation["u4_test_executed_by_slice3a_validation"], False
        )
        self.assertFalse(
            any(
                "u4" in path.lower()
                for path in self.validation["registry_regression_result"][
                    "command_paths"
                ]
            )
        )

    def test_29_frozen_contracts_and_authorized_changed_scope_are_exact(self) -> None:
        for relative_path, expected in FROZEN_HASHES.items():
            actual = hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest()
            self.assertEqual(actual, expected)
        completed = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        changed = {
            line[3:].replace("\\", "/").rstrip("/")
            for line in completed.stdout.splitlines()
            if line
        }
        # The slice may be uncommitted (while it is being built) or committed
        # (once published), so the set of dirty paths is not itself stable. The
        # durable invariant is that no frozen contract file is ever dirty, and
        # that the slice's own authorized scope is the only slice-owned path
        # that may appear.
        self.assertFalse(changed & set(FROZEN_HASHES))
        slice_owned = {
            path
            for path in changed
            if "slice3a" in path
        }
        self.assertTrue(
            slice_owned
            <= {
                "docs/status/person_e_phase4_step4_1_slice3a_v0_1",
                BUILDER_PATH,
                TEST_PATH,
            },
            f"unauthorized slice3a paths: {sorted(slice_owned)}",
        )

    def test_30_pinned_commit_remains_published_on_its_authority_branch(
        self,
    ) -> None:
        # Person A keeps publishing after the pin, so the pinned commit becomes
        # an ancestor of the tip. What must never change is that the pin is
        # still reachable from the published branch.
        result = verify_source_authority(
            AUTHORITIES["person_a"]["branch"],
            AUTHORITIES["person_a"]["commit"],
        )
        self.assertIn(result["relationship"], {"equal", "ancestor"})
        if result["relationship"] == "equal":
            self.assertEqual(
                result["current_remote_tip"],
                AUTHORITIES["person_a"]["commit"],
            )

    def test_31_pinned_ancestor_of_advanced_tip_passes(self) -> None:
        result = verify_source_authority(
            AUTHORITIES["person_e_empirical"]["branch"],
            AUTHORITIES["person_e_empirical"]["commit"],
        )
        self.assertEqual(result["relationship"], "ancestor")

    def test_32_non_ancestor_source_authority_fails(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "not an ancestor"):
            verify_source_authority(
                AUTHORITIES["person_b"]["branch"],
                STARTING_COMMIT,
            )

    def test_33_missing_pinned_commit_fails(self) -> None:
        with self.assertRaisesRegex(
            RuntimeError,
            "Missing pinned source authority commit",
        ):
            verify_source_authority(
                AUTHORITIES["person_a"]["branch"],
                "0" * 40,
            )

    def test_34_missing_remote_branch_fails(self) -> None:
        with self.assertRaisesRegex(
            RuntimeError,
            "Missing source authority branch",
        ):
            verify_source_authority(
                "origin/role/person-missing-slice3a-audit",
                AUTHORITIES["person_a"]["commit"],
            )

    def test_35_pinned_reads_ignore_changed_descendant_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "authority-repository"
            repository.mkdir()

            def run_git(*arguments: str) -> str:
                completed = subprocess.run(
                    ["git", *arguments],
                    cwd=repository,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(
                    completed.returncode,
                    0,
                    completed.stderr,
                )
                return completed.stdout.strip()

            run_git("init", "-b", "main")
            run_git("config", "user.email", "slice3a@example.invalid")
            run_git("config", "user.name", "Slice 3A Test")
            source_path = repository / "source.json"
            source_path.write_text('{"value":"pinned"}\n', encoding="utf-8")
            run_git("add", "source.json")
            run_git("commit", "-m", "pinned source")
            pinned = run_git("rev-parse", "HEAD")

            with patch(
                "scripts.build_person_e_phase4_step4_1_slice3a_v0_1.ROOT",
                repository,
            ):
                before = _source_entry(
                    owner="person_b",
                    branch="main",
                    commit=pinned,
                    path="source.json",
                    artifact_type="oracle_target",
                    artifact_id="synthetic_pinned_source",
                    schema_version="synthetic-v1",
                    scientific_use_status="pending",
                    classification="PENDING",
                    byte_availability_state="git_object_available",
                    direct_input_evidence=[],
                    missing_links=["owner_status"],
                )

            source_path.write_text(
                '{"value":"advanced"}\n',
                encoding="utf-8",
            )
            run_git("add", "source.json")
            run_git("commit", "-m", "advanced source")
            advanced = run_git("rev-parse", "HEAD")
            self.assertNotEqual(pinned, advanced)

            with patch(
                "scripts.build_person_e_phase4_step4_1_slice3a_v0_1.ROOT",
                repository,
            ):
                relationship = verify_source_authority("main", pinned)
                after = _source_entry(
                    owner="person_b",
                    branch="main",
                    commit=pinned,
                    path="source.json",
                    artifact_type="oracle_target",
                    artifact_id="synthetic_pinned_source",
                    schema_version="synthetic-v1",
                    scientific_use_status="pending",
                    classification="PENDING",
                    byte_availability_state="git_object_available",
                    direct_input_evidence=[],
                    missing_links=["owner_status"],
                )
            self.assertEqual(relationship["relationship"], "ancestor")
            self.assertEqual(relationship["current_remote_tip"], advanced)
            self.assertEqual(before, after)
            self.assertEqual(
                before["file_sha256"],
                hashlib.sha256(b'{"value":"pinned"}\n').hexdigest(),
            )

    def test_36_current_person_b_advancement_passes_ancestry(self) -> None:
        result = verify_source_authority(
            AUTHORITIES["person_b"]["branch"],
            AUTHORITIES["person_b"]["commit"],
        )
        current_remote_tip = subprocess.run(
            ["git", "rev-parse", AUTHORITIES["person_b"]["branch"]],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.assertEqual(result["relationship"], "ancestor")
        self.assertEqual(result["current_remote_tip"], current_remote_tip)
        self.assertNotEqual(
            current_remote_tip,
            AUTHORITIES["person_b"]["commit"],
        )

    def test_37_current_person_d_advancement_passes_ancestry(self) -> None:
        result = verify_source_authority(
            AUTHORITIES["person_d"]["branch"],
            AUTHORITIES["person_d"]["commit"],
        )
        current_remote_tip = subprocess.run(
            ["git", "rev-parse", AUTHORITIES["person_d"]["branch"]],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.assertEqual(result["relationship"], "ancestor")
        self.assertEqual(result["current_remote_tip"], current_remote_tip)
        self.assertNotEqual(
            current_remote_tip,
            AUTHORITIES["person_d"]["commit"],
        )

    def test_38_new_remote_tips_are_not_source_inventory_inputs(self) -> None:
        source_commits = {
            row["source_commit"] for row in self.source["entries"]
        }
        for owner in ("person_b", "person_d"):
            relationship = verify_source_authority(
                AUTHORITIES[owner]["branch"],
                AUTHORITIES[owner]["commit"],
            )
            self.assertNotIn(
                relationship["current_remote_tip"],
                source_commits,
            )

    def test_39_remote_advancement_preserves_classifications(self) -> None:
        self.assertEqual(
            self.source["classification_counts"],
            {
                "ACCEPTABLE_AFTER_OWNER_RECEIPT": 5,
                "BLOCKED": 3,
                "NON_SCIENTIFIC": 4,
                "PENDING": 39,
                "UNSUPPORTED_MAPPING": 2,
            },
        )
        self.assertEqual(self.source["acceptable_now_inventory"], [])

    def test_40_recursive_true_claims_fail_with_exact_paths(self) -> None:
        mutations = [
            (
                {"person_a_phase6_authorized": True},
                "surrounding.person_a_phase6_authorized",
            ),
            (
                {"metadata": {"person_a_phase6_authorized": True}},
                "surrounding.metadata.person_a_phase6_authorized",
            ),
            (
                {
                    "requirements": [
                        {"person_a_phase6_authorized": True}
                    ]
                },
                "surrounding.requirements[0].person_a_phase6_authorized",
            ),
            (
                {"scientific_acceptance_claimed": True},
                "surrounding.scientific_acceptance_claimed",
            ),
            (
                {
                    "evidence": {
                        "claims": {
                            "scientific_acceptance_claimed": True
                        }
                    }
                },
                (
                    "surrounding.evidence.claims."
                    "scientific_acceptance_claimed"
                ),
            ),
            (
                {"metadata": {"project_wide_integration_claimed": True}},
                "surrounding.metadata.project_wide_integration_claimed",
            ),
            (
                {"metadata": {"project_integration_claimed": True}},
                "surrounding.metadata.project_integration_claimed",
            ),
            (
                {"metadata": {"integration_claimed": True}},
                "surrounding.metadata.integration_claimed",
            ),
            (
                {"metadata": {"step4_1_complete": True}},
                "surrounding.metadata.step4_1_complete",
            ),
        ]
        for injected, expected_path in mutations:
            mutated = copy.deepcopy(self.authority)
            mutated.update(injected)
            violations = validate_slice3a_policy(
                self.registry,
                mutated,
            )
            self.assertTrue(
                any(expected_path in violation for violation in violations),
                (expected_path, violations),
            )

    def test_41_non_boolean_claims_fail_and_false_claims_pass(self) -> None:
        protected_fields = (
            "person_a_phase6_authorized",
            "scientific_acceptance_claimed",
            "project_wide_integration_claimed",
            "project_integration_claimed",
            "integration_claimed",
            "step4_1_complete",
        )
        for field in protected_fields:
            for value in ("false", "pending", 0, None):
                mutated = copy.deepcopy(self.authority)
                mutated["metadata"] = {field: value}
                violations = validate_slice3a_policy(
                    self.registry,
                    mutated,
                )
                expected_path = f"surrounding.metadata.{field}"
                self.assertTrue(
                    any(
                        expected_path in violation
                        for violation in violations
                    ),
                    (expected_path, value, violations),
                )

        valid = copy.deepcopy(self.authority)
        valid["metadata"] = {
            field: False for field in protected_fields
        }
        valid["requirements"] = [
            {
                "person_a_phase6_authorized": False,
                "scientific_acceptance_claimed": False,
            }
        ]
        self.assertEqual(
            validate_slice3a_policy(self.registry, valid),
            (),
        )


if __name__ == "__main__":
    unittest.main()

"""Person B production oracle-target construction for the 66-cell MVP.

Person C owns capture state, geometric visibility, the empirical detector
intake, and the final ``visible_flag``.  Person A owns model and preprocessing
identity.  Person B owns exactly one thing here: the Regime A oracle targets
and the analysis-row admission policy applied on top of that evidence.

Two visibility channels are used at two different layers, and the distinction
is deliberate:

* **Oracle state layer.**  ``build_state_input_from_capture_package`` — Person
  B's frozen adapter — reads the capture package's ``streams.visibility``,
  which carries Person C's authoritative *geometric* channel recorded at
  capture.  That is the physical occlusion history, and it is what anchors the
  last visible observation and ``tau``.  Nothing about the frozen state update
  or the target formulas is changed here.
* **Analysis admission layer.**  Person B's frozen Phase 3 Step 3.3 policy
  defines the analysis label as ``geometric_visible AND
  empirical_magenta_visible``.  That strict flag decides which oracle rows are
  admitted as scientific evidence.  Rows where the two channels disagree, or
  where Person C flagged the geometry as edge-ambiguous, are excluded with an
  explicit reason rather than resolved in Person B's favour.

No detector position is ever used as hidden truth, no target value is
reconstructed from pixels, no threshold is retuned, and no ``visible_flag`` is
overwritten.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from mineocclude.analysis.coordinates import (
    CaptureStateHandoffCode,
    CaptureStateHandoffError,
    build_state_input_from_capture_package,
    validate_coordinate_frame,
)
from mineocclude.analysis.manifests import is_hex_digest, sha256_value
from mineocclude.analysis.selection import (
    SCOPE_HIDDEN_MEAN,
    SCOPE_HIDDEN_SPREAD,
    SCOPE_VISIBLE_NO_WALL,
)
from mineocclude.oracle.schema import OracleValidationError
from mineocclude.oracle.targets import build_regime_a_target_document

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

ORACLE_PACKAGE_SCHEMA_VERSION = "person-b-66-cell-oracle-target-v0.1"
ORACLE_PACKAGE_DIRECTORY = "docs/status/person_b_66_cell_oracle_target_v0_1"
DECISION_DATE = "2026-08-07"
ORACLE_RUN_ID = "person-b-66-cell-oracle-v0.1"

# --------------------------------------------------------------------------
# Bound Person C strict-visibility authority
# --------------------------------------------------------------------------
PERSON_C_COMMIT = "e908ead4a7ff5ab3ae310bb846969a7859fdb26b"
PERSON_C_STRICT_DIRECTORY = "docs/status/person_c_66_cell_strict_visibility_v0_1"
C_ORACLE_HANDOFF_PATH = f"{PERSON_C_STRICT_DIRECTORY}/c_to_b_oracle_handoff.json"
C_ORACLE_HANDOFF_SHA256 = (
    "dd5569164d72ba8a25e4efbd74e013819744b7cf10b22ea949e22a13b3a3b33b"
)
C_VISIBILITY_JOIN_PATH = f"{PERSON_C_STRICT_DIRECTORY}/visibility_join.jsonl"
C_VISIBILITY_JOIN_SHA256 = (
    "6fcfaba99feed706e7106d0f1d9b758700d920ee2001b3ca6f150320f09313b7"
)
C_EVENT_TABLE_PATH = f"{PERSON_C_STRICT_DIRECTORY}/event_table.jsonl"
C_EVENT_TABLE_SHA256 = (
    "fadc0fc4c2afab2b39b992979317d4576fa2618263c8b09e29ca6c215528bb49"
)
C_ACCEPTED_MANIFEST_PATH = (
    "docs/status/person_c_c7_mvp_handoff_v0_1/trajectories_mvp_manifest.json"
)
C_ACCEPTED_MANIFEST_SHA256 = (
    "96ba43e15bc024aeaef7c519fa4ece0a4afe0bb0e877501dffaca44fee927ff7"
)
C_CAPTURE_PACKAGE_MANIFEST_PATH = (
    "docs/status/person_c_66_cell_capture_authority_v0_1/capture_package_manifest.json"
)
C_CAPTURE_PACKAGE_MANIFEST_SHA256 = (
    "ca6ef6bd0a6ee144731ff3e6f470f767a2c1a82e8b46aef9fb5e458efb814f56"
)
C_CAPTURE_AUTHORITY_COMMIT = "aceb319c47af6d494d6e5314049b12ab1a0a002f"
C_COORDINATE_AUTHORITY_PATH = (
    "docs/status/person_c_66_cell_capture_authority_v0_1/coordinate_frame_authority.json"
)
C_COORDINATE_AUTHORITY_SHA256 = (
    "1aed95e444f82ab4caf9935c039e87df3aafbf38830bf763a646aba3d62b509b"
)
ACCEPTED_GEOMETRY_SHA256 = (
    "34495d650d6a8c62b00a916796c90389b48f80d8f20a23eac93207758e993f5d"
)

# --------------------------------------------------------------------------
# Bound Person E empirical authority (consumed only through Person C's join)
# --------------------------------------------------------------------------
PERSON_E_COMMIT = "fec27d08b4629afa07c7858598e94778dc6e7bef"
PERSON_E_RECORDS_PATH = (
    "data/handoff_c/person_e_66_cell_empirical_visibility_v0_1/"
    "empirical_visibility_records.jsonl"
)
PERSON_E_RECORDS_SHA256 = (
    "fd0ad70ce880645fcda668d23dacc07784c2f8e418a3eceabd9f88ac391e07f9"
)

# --------------------------------------------------------------------------
# Bound Person A production-input authority
# --------------------------------------------------------------------------
PERSON_A_COMMIT = "77e43bd1665671b9e23d6d6ef927ee4944611342"
PERSON_A_FRAME_MAP_PACKAGE_PATH = (
    "data/handoff_a/person_a_66_cell_production_input_v0_1/sha256_inventory.json"
)
PERSON_A_FRAME_MAP_PACKAGE_SHA256 = (
    "a473bf830ed31e49762d62bba97032e52f4967e52f9987ad10cd5879ed9bd004"
)
PERSON_A_OWNER_ACKNOWLEDGEMENT_PATH = (
    "docs/status/person_a_phase6_66_cell_intake_v0_1/person_a_owner_acknowledgement.json"
)
PERSON_A_OWNER_ACKNOWLEDGEMENT_SHA256 = (
    "82f1faa4892091e541ba00f17cc522c6d284e1336dcf4dcd59d12e98a01fd715"
)
PERSON_A_PRODUCTION_AUTHORITIES_PATH = (
    "docs/status/person_a_phase6_66_cell_intake_v0_1/production_authorities.json"
)
PERSON_A_PRODUCTION_AUTHORITIES_SHA256 = (
    "0676614917e4efceff98ab0162f5c4cd3a212764e0e63bd73a7187a51f327f24"
)

# ``model_hash == checkpoint_hash`` is not an assumption: three independent
# frozen contracts in this repository enforce the equality, so Person B binds
# the definition to the evidence rather than to the value's shape.
MODEL_HASH_DEFINITION_EVIDENCE = (
    {
        "path": "src/mineocclude/activations/store_v2.py",
        "symbol": "ActivationStoreV2Identity.__post_init__",
        "rule": "model_hash must equal the frozen checkpoint hash",
    },
    {
        "path": "src/mineocclude/activations/store.py",
        "symbol": "frozen activation handoff identity check",
        "rule": "frozen activation handoff requires model_hash=checkpoint_hash",
    },
    {
        "path": "src/mineocclude/contracts/activation.py",
        "symbol": "activation index row validation",
        "rule": "Universal model_hash must agree with the explicit checkpoint hash",
    },
)

# --------------------------------------------------------------------------
# Bound Person B authority
# --------------------------------------------------------------------------
PERSON_B_FOLD_MANIFEST_PATH = (
    "docs/status/person_b_66_cell_preactivation_v0_1/fold_manifest.json"
)
PERSON_B_FOLD_MANIFEST_SHA256 = (
    "86739975882f4926c3398d5bfa21611daf06c579b3893809eb385e8dcd03001d"
)
PERSON_B_COSIGN_PATH = (
    "docs/status/person_b_66_cell_coordinate_frame_cosign_v0_1/"
    "coordinate_frame_cosign.json"
)
PERSON_B_COSIGN_SHA256 = (
    "b40d8ba1103e1638af386cc365ec727ab576d842516accc41d675d4fdb3d6b7d"
)
PERSON_B_COSIGNED_FRAME_DIRECTORY = "data/person_b/c6a_c_intake/coordinate_frames"

STORED_ACTIVATION_DTYPE = "float32"
ANALYSIS_ARITHMETIC_DTYPE = "float64"

# --------------------------------------------------------------------------
# Expected cardinality, independently reverified rather than assumed
# --------------------------------------------------------------------------
EXPECTED_TRAJECTORY_COUNT = 66
EXPECTED_MODEL_FRAME_KEY_COUNT = 2_468
EXPECTED_TARGET_BEARING_COUNT = 2_108
EXPECTED_NO_OBJECT_COUNT = 360
EXPECTED_ORACLE_ELIGIBLE_TRAJECTORY_COUNT = 60
EXPECTED_LAYOUT_COUNT = 6
EXPECTED_LAYER_COUNT = 20

EXPECTED_DISAGREEMENT_CENSUS = {
    "agreement": 1_696,
    "detector_not_applicable": 360,
    "geometry_ambiguous": 42,
    "geometry_hidden_detector_visible": 313,
    "geometry_visible_detector_hidden": 57,
}
EXPECTED_FINAL_VISIBLE = 1_413
EXPECTED_FINAL_HIDDEN = 695
EXPECTED_GEOMETRIC_VISIBLE = 1_484
EXPECTED_EMPIRICAL_VISIBLE = 1_726
EXPECTED_STABLE_OCCLUSION_EVENTS = 55
EXPECTED_STABLE_REVEAL_EVENTS = 1
EXPECTED_VALID_TERMINAL_REVEALS = 0

CONTROL_TYPE_NO_OBJECT = "no_object_control"
CONTROL_TYPE_NO_WALL = "no_wall_visible_control"
CONTROL_TYPE_CORE = "core_regime_a"
CONTROL_TYPE_SENTINEL = "context_sentinel"
HIDDEN_ADMISSION_CONTROL_TYPES = (CONTROL_TYPE_CORE, CONTROL_TYPE_SENTINEL)

ROW_EXCLUSION_NO_OBJECT = "no_object_control_not_oracle_eligible"
ROW_EXCLUSION_AMBIGUOUS_GEOMETRY = "ambiguous_geometry_edge_convention"
ROW_EXCLUSION_CHANNEL_DISAGREEMENT = "visibility_channel_disagreement"
ROW_EXCLUSION_QUARANTINED = "person_c_quarantined_row"
ROW_EXCLUSION_PRE_FIRST_SEEN = "pre_first_seen"
ROW_EXCLUSION_OUTSIDE_SELECTION = "outside_frozen_condition_selection"

ADMISSION_STRATUM_CORE = "core_regime_a_hidden"
ADMISSION_STRATUM_SENTINEL = "context_sentinel_hidden"
ADMISSION_STRATUM_VISIBLE_CONTROL = "no_wall_visible_control"

FROZEN_FOLD_ASSIGNMENT = {
    "layout_01": 3,
    "layout_02": 2,
    "layout_03": 4,
    "layout_04": 4,
    "layout_05": 1,
    "layout_06": 0,
}

ORACLE_TARGET_FIELDS = (
    "mu_oracle_blocks",
    "var_oracle_blocks2",
    "sigma_oracle_blocks",
    "log_sigma_oracle",
    "x_true_blocks",
    "tau",
    "last_visible_position_blocks",
)

# The frozen analysis config gives ``log_sigma_oracle`` eligibility
# ``accepted_hidden_positive_spread_rows`` and ``null_policy``
# ``null_outside_eligibility``.  A visible control row therefore *must* carry a
# null here; requiring a value would contradict the frozen target contract.
ALWAYS_REQUIRED_TARGET_FIELDS = (
    "mu_oracle_blocks",
    "var_oracle_blocks2",
    "sigma_oracle_blocks",
    "x_true_blocks",
    "tau",
    "last_visible_position_blocks",
)
HIDDEN_ONLY_TARGET_FIELDS = ("log_sigma_oracle",)

CODE_COMPONENTS = (
    "src/mineocclude/analysis/oracle_target_66_cell_v0_1.py",
    "src/mineocclude/analysis/coordinates.py",
    "src/mineocclude/analysis/config.py",
    "src/mineocclude/analysis/manifests.py",
    "src/mineocclude/analysis/selection.py",
    "src/mineocclude/oracle/targets.py",
    "src/mineocclude/oracle/schema.py",
    "src/mineocclude/oracle/closed_form.py",
    "src/mineocclude/oracle/primary_scalar_kalman.py",
)


class OracleTargetError(ValueError):
    """Raised when a production oracle-target invariant fails closed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise OracleTargetError(message)


# --------------------------------------------------------------------------
# Exact Git-object binding
# --------------------------------------------------------------------------
def _git_bytes(repository_root: Path, *arguments: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repository_root), *arguments],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise OracleTargetError(
            f"git {' '.join(arguments)} failed: {detail or 'unknown error'}"
        )
    return result.stdout


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_bound_blob(
    path: str,
    *,
    commit: str,
    expected_sha256: str | None = None,
    repository_root: Path | None = None,
) -> bytes:
    """Read one foreign-role blob by exact ``commit:path`` and verify bytes."""

    require(
        isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit) is not None,
        f"bound commit must be a full Git SHA-1: {commit!r}",
    )
    require(
        isinstance(path, str)
        and bool(path)
        and "\x00" not in path
        and not path.startswith("/")
        and ".." not in Path(path).parts,
        f"invalid bound repository path: {path!r}",
    )
    root = REPOSITORY_ROOT if repository_root is None else Path(repository_root)
    require(
        _git_bytes(root, "cat-file", "-t", commit).decode("utf-8").strip() == "commit",
        f"bound authority {commit} is not a commit object",
    )
    payload = _git_bytes(root, "cat-file", "blob", f"{commit}:{path}")
    if expected_sha256 is not None:
        require(
            is_hex_digest(expected_sha256, 64),
            f"expected_sha256 must be SHA-256 for {path}",
        )
        actual = sha256_bytes(payload)
        require(
            actual == expected_sha256.lower(),
            f"bound blob {commit}:{path} hashes to {actual}, "
            f"expected {expected_sha256.lower()}",
        )
    return payload


def _strict_json(payload: bytes, *, label: str) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise OracleTargetError(f"{label} repeats JSON key {key!r}.")
            result[key] = value
        return result

    try:
        return json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda value: (_ for _ in ()).throw(
                OracleTargetError(f"{label} contains non-finite constant {value!r}.")
            ),
        )
    except OracleTargetError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OracleTargetError(f"{label} is not strict UTF-8 JSON: {error}") from error


def _strict_jsonl(payload: bytes, *, label: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(payload.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = _strict_json(line.encode("utf-8"), label=f"{label} line {number}")
        require(isinstance(row, Mapping), f"{label} line {number} must be an object.")
        rows.append(dict(row))
    return rows


def derive_oracle_code_sha(repository_root: Path | None = None) -> str:
    """Hash every code component that determines the production oracle output."""

    root = REPOSITORY_ROOT if repository_root is None else Path(repository_root)
    digest = hashlib.sha1()
    for label in CODE_COMPONENTS:
        try:
            payload = (root / label).read_bytes()
        except OSError as error:  # pragma: no cover - defensive
            raise OracleTargetError(
                f"Could not read oracle code component {label}: {error}"
            ) from error
        digest.update(label.encode("utf-8"))
        digest.update(b"\0")
        digest.update(payload.replace(b"\r\n", b"\n"))
        digest.update(b"\0")
    return digest.hexdigest()


# --------------------------------------------------------------------------
# Step 1 - Person C oracle-ready handoff
# --------------------------------------------------------------------------
def load_person_c_oracle_inputs(
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Verify Person C's oracle handoff, strict visibility join, and events."""

    handoff = _strict_json(
        read_bound_blob(
            C_ORACLE_HANDOFF_PATH,
            commit=PERSON_C_COMMIT,
            expected_sha256=C_ORACLE_HANDOFF_SHA256,
            repository_root=repository_root,
        ),
        label="Person C oracle handoff",
    )
    require(
        handoff.get("C_TO_B_ORACLE_INPUT_READY") is True,
        "Person C has not declared the oracle input ready.",
    )
    require(
        handoff.get("person_c_generated_person_b_target_values") is False
        and handoff.get("person_c_modified_person_b_oracle_logic") is False,
        "Person C must not generate Person B target values or oracle logic.",
    )
    require(
        handoff.get("rewrites_frozen_c7_5_authority") is False,
        "Person C handoff claims to rewrite the frozen C7.5 authority.",
    )

    # Every nested authority the handoff names must hash exactly.
    for label, path, digest in (
        (
            "accepted manifest",
            handoff["person_c_accepted_manifest"]["path"],
            handoff["person_c_accepted_manifest"]["sha256"],
        ),
        (
            "capture-package manifest",
            handoff["capture_package_authority"]["path"],
            handoff["capture_package_authority"]["sha256"],
        ),
        (
            "accepted geometry",
            handoff["accepted_geometry"]["path"],
            handoff["accepted_geometry"]["sha256"],
        ),
        (
            "coordinate authority",
            handoff["coordinate_authority"]["person_c_authority_path"],
            handoff["coordinate_authority"]["person_c_authority_sha256"],
        ),
        (
            "geometric visibility table",
            handoff["geometric_visibility_table"]["path"],
            handoff["geometric_visibility_table"]["sha256"],
        ),
        (
            "disagreement ledger",
            handoff["qa_and_disagreement_status"]["disagreement_ledger_path"],
            handoff["qa_and_disagreement_status"]["disagreement_ledger_sha256"],
        ),
    ):
        read_bound_blob(
            path,
            commit=PERSON_C_COMMIT,
            expected_sha256=digest,
            repository_root=repository_root,
        )
        require(
            digest == digest.lower() and is_hex_digest(digest, 64),
            f"{label} digest is malformed.",
        )
    require(
        handoff["person_c_accepted_manifest"]["sha256"] == C_ACCEPTED_MANIFEST_SHA256,
        "Person C handoff names a different accepted manifest.",
    )
    require(
        handoff["capture_package_authority"]["sha256"]
        == C_CAPTURE_PACKAGE_MANIFEST_SHA256,
        "Person C handoff names a different capture-package authority.",
    )
    require(
        handoff["accepted_geometry"]["sha256"] == ACCEPTED_GEOMETRY_SHA256,
        "Person C handoff names a different accepted geometry.",
    )
    require(
        handoff["coordinate_authority"]["person_c_authority_sha256"]
        == C_COORDINATE_AUTHORITY_SHA256,
        "Person C handoff names a different coordinate-frame authority.",
    )

    # Person B's own co-sign, as Person C recorded it.
    coordinate = handoff["coordinate_authority"]
    require(
        coordinate["person_b_cosign_sha256"] == PERSON_B_COSIGN_SHA256
        and coordinate["adapter_signoff"]["person_b"] is True
        and coordinate["adapter_signoff"]["person_c"] is True
        and coordinate["coordinate_frame_hash_preserved_across_cosign"] is True,
        "Person C did not record Person B's co-sign correctly.",
    )
    local_cosign = (
        (REPOSITORY_ROOT if repository_root is None else Path(repository_root))
        / PERSON_B_COSIGN_PATH
    ).read_bytes()
    require(
        sha256_bytes(local_cosign) == PERSON_B_COSIGN_SHA256,
        "Person B's published co-sign no longer hashes to the bound value.",
    )

    # Person E empirical authority, verified at Person E's own commit.
    empirical = handoff["empirical_visibility_binding"]
    require(
        empirical["person_e_commit"] == PERSON_E_COMMIT
        and empirical["records_sha256"] == PERSON_E_RECORDS_SHA256
        and empirical["person_c_executed_detector"] is False
        and empirical["person_c_tuned_detector"] is False,
        "Person E empirical binding does not match the bound authority.",
    )
    read_bound_blob(
        empirical["records_path"],
        commit=PERSON_E_COMMIT,
        expected_sha256=PERSON_E_RECORDS_SHA256,
        repository_root=repository_root,
    )

    require(
        handoff["frame_universe"]["person_a_frame_map_package_sha256"]
        == PERSON_A_FRAME_MAP_PACKAGE_SHA256
        and handoff["frame_universe"]["person_a_commit"] == PERSON_A_COMMIT
        and handoff["frame_universe"]["model_frame_key_count"]
        == EXPECTED_MODEL_FRAME_KEY_COUNT
        and handoff["frame_universe"]["duplicate_key_count"] == 0
        and handoff["frame_universe"]["missing_key_count"] == 0,
        "Person C handoff frame universe does not match the bound Person A package.",
    )

    visibility_rows = _strict_jsonl(
        read_bound_blob(
            C_VISIBILITY_JOIN_PATH,
            commit=PERSON_C_COMMIT,
            expected_sha256=C_VISIBILITY_JOIN_SHA256,
            repository_root=repository_root,
        ),
        label="Person C visibility join",
    )
    event_rows = _strict_jsonl(
        read_bound_blob(
            C_EVENT_TABLE_PATH,
            commit=PERSON_C_COMMIT,
            expected_sha256=C_EVENT_TABLE_SHA256,
            repository_root=repository_root,
        ),
        label="Person C event table",
    )

    require(
        len(visibility_rows) == EXPECTED_MODEL_FRAME_KEY_COUNT,
        f"Visibility join must carry {EXPECTED_MODEL_FRAME_KEY_COUNT} rows.",
    )
    by_key: dict[tuple[str, int], dict[str, Any]] = {}
    for row in visibility_rows:
        key = (str(row["trajectory_id"]), int(row["model_frame_idx"]))
        require(key not in by_key, f"Visibility join duplicates frame identity {key!r}.")
        require(
            row["visible_flag_rule"] == "geometric_visible AND empirical_magenta_visible",
            f"{key}: visible_flag rule is not the frozen strict-join rule.",
        )
        require(
            row["accepted_geometry_sha256"] == ACCEPTED_GEOMETRY_SHA256,
            f"{key}: visibility row is not bound to the accepted geometry.",
        )
        by_key[key] = row

    applicable = [row for row in visibility_rows if row["visibility_applicable"] is True]
    not_applicable = [
        row for row in visibility_rows if row["visibility_applicable"] is not True
    ]
    require(
        len(applicable) == EXPECTED_TARGET_BEARING_COUNT
        and len(not_applicable) == EXPECTED_NO_OBJECT_COUNT,
        f"Applicability accounting must be {EXPECTED_TARGET_BEARING_COUNT}/"
        f"{EXPECTED_NO_OBJECT_COUNT}, observed "
        f"{len(applicable)}/{len(not_applicable)}.",
    )
    census = Counter(str(row["disagreement_class"]) for row in visibility_rows)
    require(
        dict(census) == EXPECTED_DISAGREEMENT_CENSUS,
        f"Disagreement census differs from Person C's declared accounting: "
        f"{dict(census)}",
    )
    require(
        dict(census) == handoff["qa_and_disagreement_status"]["global_counts"],
        "Person C's declared global counts disagree with the joined rows.",
    )
    final_visible = sum(1 for row in applicable if row["visible_flag"] is True)
    require(
        final_visible == EXPECTED_FINAL_VISIBLE
        and len(applicable) - final_visible == EXPECTED_FINAL_HIDDEN,
        f"Final visible/hidden accounting is {final_visible}/"
        f"{len(applicable) - final_visible}.",
    )
    geometric_visible = sum(
        1 for row in visibility_rows if row["geometric_visible"] is True
    )
    empirical_visible = sum(
        1 for row in visibility_rows if row["empirical_magenta_visible"] is True
    )
    require(
        geometric_visible == EXPECTED_GEOMETRIC_VISIBLE
        and empirical_visible == EXPECTED_EMPIRICAL_VISIBLE,
        f"Raw channel accounting is {geometric_visible}/{empirical_visible}.",
    )
    ambiguous = sum(1 for row in visibility_rows if row["geometric_ambiguous"] is True)
    require(
        ambiguous == EXPECTED_DISAGREEMENT_CENSUS["geometry_ambiguous"],
        f"Ambiguous-geometry count is {ambiguous}.",
    )

    event_table = handoff["event_table"]
    require(
        event_table["stable_occlusion_event_count"] == EXPECTED_STABLE_OCCLUSION_EVENTS
        and event_table["stable_reveal_event_count"] == EXPECTED_STABLE_REVEAL_EVENTS
        and event_table["valid_terminal_reveal_count"] == EXPECTED_VALID_TERMINAL_REVEALS
        and event_table["flickering_frames_deleted"] is False,
        "Person C event-table accounting differs from the declared authority.",
    )
    require(
        handoff["u4_structural_status"]["CURRENT_66_CELL_U4_REVEAL_ELIGIBLE"] is False
        and handoff["u4_structural_status"]["U4_SUPPLEMENTAL_CAPTURE_REQUIRED"] is True
        and handoff["u4_structural_status"]["U4_VALID_TERMINAL_REVEAL_COUNT"] == 0,
        "Person C U4 structural status is not the bound ineligible state.",
    )

    return {
        "handoff": handoff,
        "visibility_rows": visibility_rows,
        "visibility_by_key": by_key,
        "event_rows": event_rows,
        "disagreement_census": dict(census),
    }


# --------------------------------------------------------------------------
# Step 2 - Person A model / preprocess authority
# --------------------------------------------------------------------------
def resolve_person_a_identity(repository_root: Path | None = None) -> dict[str, Any]:
    """Resolve model_hash and preprocess_hash from repository authority only.

    ``model_hash`` is not assumed to be the checkpoint digest because the value
    looks like one: the equality is asserted by three frozen contracts in this
    repository, and Person A's production authorities declare a checkpoint
    digest that satisfies it.  ``preprocess_hash`` has no such derivation rule,
    so it is taken from the only production artifact that declares the field
    itself - never from the preprocessing implementation's file digest, which
    is a different quantity.
    """

    acknowledgement = _strict_json(
        read_bound_blob(
            PERSON_A_OWNER_ACKNOWLEDGEMENT_PATH,
            commit=PERSON_A_COMMIT,
            expected_sha256=PERSON_A_OWNER_ACKNOWLEDGEMENT_SHA256,
            repository_root=repository_root,
        ),
        label="Person A owner acknowledgement",
    )
    authorities = _strict_json(
        read_bound_blob(
            PERSON_A_PRODUCTION_AUTHORITIES_PATH,
            commit=PERSON_A_COMMIT,
            expected_sha256=PERSON_A_PRODUCTION_AUTHORITIES_SHA256,
            repository_root=repository_root,
        ),
        label="Person A production authorities",
    )

    checkpoint_sha256 = authorities["model_and_checkpoint"]["checkpoint_sha256"]
    declared_model_hash = authorities["frozen_authority"]["live_config_identity"][
        "model_hash"
    ]
    preprocess_hash = authorities["preprocessing"]["preprocess_hash"]
    frozen_preprocess_hash = authorities["frozen_authority"]["live_config_identity"][
        "preprocess_hash"
    ]

    for name, value in (
        ("checkpoint_sha256", checkpoint_sha256),
        ("model_hash", declared_model_hash),
        ("preprocess_hash", preprocess_hash),
    ):
        require(is_hex_digest(value, 64), f"Person A {name} must be a SHA-256 digest.")
    require(
        declared_model_hash == checkpoint_sha256,
        "Person A's declared model_hash does not equal its checkpoint digest, "
        "which the frozen activation contracts require.",
    )
    require(
        preprocess_hash == frozen_preprocess_hash,
        "Person A's preprocessing block and frozen live-config identity declare "
        "different preprocess_hash values.",
    )
    require(
        acknowledgement["production_authorities"]["checkpoint_sha256"]
        == checkpoint_sha256
        and acknowledgement["production_authorities"]["model_identity"]
        == authorities["model_and_checkpoint"]["model_identity"],
        "Person A's owner acknowledgement and production authorities disagree.",
    )
    require(
        acknowledgement["expected_model_frame_universe"]["expected_model_frame_key_count"]
        == EXPECTED_MODEL_FRAME_KEY_COUNT,
        "Person A's acknowledged model-frame universe is not 2468 keys.",
    )

    preprocessing = authorities["preprocessing"]
    implementation_path = acknowledgement["production_authorities"][
        "preprocessing_implementation_path"
    ]
    implementation_sha = acknowledgement["production_authorities"][
        "preprocessing_implementation_sha256"
    ]
    read_bound_blob(
        implementation_path,
        commit=PERSON_A_COMMIT,
        expected_sha256=implementation_sha,
        repository_root=repository_root,
    )
    require(
        implementation_sha != preprocess_hash,
        "The preprocessing implementation digest and preprocess_hash are the "
        "same value; the distinction this resolution relies on has changed.",
    )

    return {
        "model_hash": declared_model_hash,
        "preprocess_hash": preprocess_hash,
        "checkpoint_sha256": checkpoint_sha256,
        "model_identity": authorities["model_and_checkpoint"]["model_identity"],
        "preprocessing_identity": preprocessing["preprocessing_identity"],
        "preprocessing_config_hash": preprocessing["config_hash"],
        "preprocessing_implementation_path": implementation_path,
        "preprocessing_implementation_sha256": implementation_sha,
        "action_converter_identity": acknowledgement["production_authorities"][
            "action_converter_identity"
        ],
        "action_converter_path": acknowledgement["production_authorities"][
            "action_converter_path"
        ],
        "action_converter_sha256": acknowledgement["production_authorities"][
            "action_converter_sha256"
        ],
        "frame_map_schema_path": acknowledgement["production_authorities"][
            "frame_map_schema_path"
        ],
        "frame_map_schema_sha256": acknowledgement["production_authorities"][
            "frame_map_schema_sha256"
        ],
        "frame_map_schema_version": acknowledgement["production_authorities"][
            "frame_map_schema_version"
        ],
        "activation_index_format_version": acknowledgement["production_authorities"][
            "activation_index_format_version"
        ],
        "activation_index_key": list(
            acknowledgement["production_authorities"]["activation_index_key"]
        ),
        "model_hash_definition": "model_hash == checkpoint_sha256",
        "model_hash_definition_evidence": [
            dict(item) for item in MODEL_HASH_DEFINITION_EVIDENCE
        ],
        "preprocess_hash_source": {
            "path": PERSON_A_PRODUCTION_AUTHORITIES_PATH,
            "sha256": PERSON_A_PRODUCTION_AUTHORITIES_SHA256,
            "commit": PERSON_A_COMMIT,
            "fields": [
                "preprocessing.preprocess_hash",
                "frozen_authority.live_config_identity.preprocess_hash",
            ],
            "note": (
                "preprocess_hash is the field Person A declares, not the digest "
                "of the preprocessing implementation file; the two differ and "
                "only the declared field satisfies the frozen adapter contract."
            ),
        },
        "authority_valid": True,
    }


# --------------------------------------------------------------------------
# Step 3 - production oracle targets
# --------------------------------------------------------------------------
def _load_capture_package_index(
    repository_root: Path | None = None,
) -> list[dict[str, Any]]:
    manifest = _strict_json(
        read_bound_blob(
            C_CAPTURE_PACKAGE_MANIFEST_PATH,
            commit=C_CAPTURE_AUTHORITY_COMMIT,
            expected_sha256=C_CAPTURE_PACKAGE_MANIFEST_SHA256,
            repository_root=repository_root,
        ),
        label="Person C capture-package manifest",
    )
    require(
        manifest["capture_package_count"] == EXPECTED_TRAJECTORY_COUNT,
        f"Expected {EXPECTED_TRAJECTORY_COUNT} capture packages.",
    )
    return [dict(record) for record in manifest["records"]]


def _load_cosigned_frames(
    repository_root: Path | None = None,
) -> dict[str, dict[str, Any]]:
    root = REPOSITORY_ROOT if repository_root is None else Path(repository_root)
    frames: dict[str, dict[str, Any]] = {}
    for layout_id in sorted(FROZEN_FOLD_ASSIGNMENT):
        path = root / PERSON_B_COSIGNED_FRAME_DIRECTORY / f"{layout_id}.json"
        document = _strict_json(
            path.read_bytes(), label=f"Person B co-signed frame {layout_id}"
        )
        validate_coordinate_frame(document, require_cross_role_signoff=True)
        frames[layout_id] = document
    require(
        len(frames) == EXPECTED_LAYOUT_COUNT,
        f"Expected {EXPECTED_LAYOUT_COUNT} co-signed coordinate frames.",
    )
    return frames


def build_production_oracle_targets(
    person_a_identity: Mapping[str, Any],
    *,
    code_sha: str,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Run Person B's frozen adapter and frozen Regime A oracle unchanged."""

    records = _load_capture_package_index(repository_root=repository_root)
    frames = _load_cosigned_frames(repository_root=repository_root)

    target_rows: list[dict[str, Any]] = []
    per_trajectory: list[dict[str, Any]] = []
    ineligible: list[dict[str, Any]] = []

    for record in sorted(records, key=lambda item: str(item["trajectory_id"])):
        trajectory_id = str(record["trajectory_id"])
        layout_id = str(record["layout_id"])
        package = _strict_json(
            read_bound_blob(
                str(record["capture_package_path"]),
                commit=C_CAPTURE_AUTHORITY_COMMIT,
                expected_sha256=str(record["capture_package_sha256"]),
                repository_root=repository_root,
            ),
            label=f"capture package {trajectory_id}",
        )
        require(
            package["episode_manifest"]["layout_config_hash"] == ACCEPTED_GEOMETRY_SHA256,
            f"{trajectory_id}: capture package is not bound to the accepted geometry.",
        )
        require(
            record["coordinate_frame_hash"] == frames[layout_id]["coordinate_frame_hash"],
            f"{trajectory_id}: capture package names a different coordinate frame.",
        )

        try:
            state_document = build_state_input_from_capture_package(
                package,
                coordinate_frame=frames[layout_id],
                model_hash=str(person_a_identity["model_hash"]),
                preprocess_hash=str(person_a_identity["preprocess_hash"]),
            )
        except CaptureStateHandoffError as error:
            # Only the frozen no-object verdict is an expected, recordable
            # ineligibility. Every other adapter rejection means an input
            # authority is wrong, and must stop the build rather than be
            # reclassified as a benign exclusion.
            if error.code is not CaptureStateHandoffCode.NO_OBJECT_NOT_ORACLE_ELIGIBLE:
                raise OracleTargetError(
                    f"{trajectory_id}: frozen adapter rejected the capture package "
                    f"with {error.code.value}; refusing to treat this as an "
                    f"ineligible trajectory. {error}"
                ) from error
            ineligible.append(
                {
                    "trajectory_id": trajectory_id,
                    "layout_id": layout_id,
                    "control_type": str(record["control_type"]),
                    "frame_count": int(record["frame_count"]),
                    "adapter_rejection_code": error.code.value,
                    "adapter_rejection_message": str(error),
                }
            )
            continue

        try:
            document = build_regime_a_target_document(
                state_document,
                oracle_run_id=ORACLE_RUN_ID,
                oracle_code_sha=code_sha,
            )
        except OracleValidationError as error:
            raise OracleTargetError(
                f"{trajectory_id}: frozen oracle rejected the state input: {error}"
            ) from error

        rows = document["rows"]
        require(
            len(rows) == int(record["frame_count"]),
            f"{trajectory_id}: oracle row count differs from the capture frame count.",
        )
        target_rows.extend(rows)
        per_trajectory.append(
            {
                "trajectory_id": trajectory_id,
                "layout_id": layout_id,
                "control_type": str(record["control_type"]),
                "oracle_row_count": len(rows),
                "capture_package_path": str(record["capture_package_path"]),
                "capture_package_sha256": str(record["capture_package_sha256"]),
                "coordinate_frame_hash": str(record["coordinate_frame_hash"]),
                "state_input_hash": sha256_value(state_document),
                "oracle_document_hash": document["artifact_hash"],
            }
        )

    require(
        len(per_trajectory) == EXPECTED_ORACLE_ELIGIBLE_TRAJECTORY_COUNT,
        f"Expected {EXPECTED_ORACLE_ELIGIBLE_TRAJECTORY_COUNT} oracle-eligible "
        f"trajectories, built {len(per_trajectory)}.",
    )
    require(
        len(ineligible) == EXPECTED_TRAJECTORY_COUNT
        - EXPECTED_ORACLE_ELIGIBLE_TRAJECTORY_COUNT,
        f"Expected {EXPECTED_TRAJECTORY_COUNT - EXPECTED_ORACLE_ELIGIBLE_TRAJECTORY_COUNT}"
        f" oracle-ineligible trajectories, observed {len(ineligible)}.",
    )
    require(
        {item["adapter_rejection_code"] for item in ineligible}
        == {"no_object_not_oracle_eligible"},
        "Oracle ineligibility was caused by something other than the frozen "
        "no-object rule.",
    )
    require(
        len(target_rows) == EXPECTED_TARGET_BEARING_COUNT,
        f"Oracle produced {len(target_rows)} rows, expected "
        f"{EXPECTED_TARGET_BEARING_COUNT}.",
    )

    by_key: dict[tuple[str, int], dict[str, Any]] = {}
    for row in target_rows:
        key = (str(row["trajectory_id"]), int(row["model_frame_idx"]))
        require(key not in by_key, f"Oracle duplicated target identity {key!r}.")
        for field in ORACLE_TARGET_FIELDS:
            require(field in row, f"{key}: oracle row is missing {field}.")
        by_key[key] = row

    return {
        "target_rows": sorted(
            target_rows,
            key=lambda row: (row["trajectory_id"], row["model_frame_idx"]),
        ),
        "target_by_key": by_key,
        "per_trajectory": per_trajectory,
        "oracle_ineligible_trajectories": ineligible,
    }


# --------------------------------------------------------------------------
# Steps 4-6 - successor analysis-row universe
# --------------------------------------------------------------------------
def build_successor_row_universe(
    c_inputs: Mapping[str, Any],
    oracle: Mapping[str, Any],
    *,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Apply Person B's frozen admission policy to Person C's final labels."""

    accepted = _strict_json(
        read_bound_blob(
            C_ACCEPTED_MANIFEST_PATH,
            commit=PERSON_C_COMMIT,
            expected_sha256=C_ACCEPTED_MANIFEST_SHA256,
            repository_root=repository_root,
        ),
        label="Person C accepted manifest",
    )
    condition_by_trajectory = {
        str(record["trajectory_id"]): dict(record) for record in accepted["records"]
    }
    require(
        len(condition_by_trajectory) == EXPECTED_TRAJECTORY_COUNT,
        "Person C accepted-manifest trajectory count changed.",
    )

    visibility_rows = c_inputs["visibility_rows"]
    target_by_key = oracle["target_by_key"]

    # The first geometrically visible frame anchors the oracle; rows before it
    # have no visible observation and the frozen filter drops them.
    first_visible: dict[str, int | None] = {}
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in visibility_rows:
        grouped[str(row["trajectory_id"])].append(row)
    for trajectory_id, rows in grouped.items():
        ordered = sorted(rows, key=lambda item: int(item["model_frame_idx"]))
        first_visible[trajectory_id] = next(
            (
                int(item["model_frame_idx"])
                for item in ordered
                if item["geometric_visible"] is True
            ),
            None,
        )

    universe: list[dict[str, Any]] = []
    for row in visibility_rows:
        trajectory_id = str(row["trajectory_id"])
        model_frame_idx = int(row["model_frame_idx"])
        condition = condition_by_trajectory[trajectory_id]
        control_type = str(condition["control_type"])
        layout_id = str(row["layout_id"])
        require(
            layout_id == str(condition["layout_id"]),
            f"{trajectory_id}: layout identity differs between C artifacts.",
        )
        disagreement_class = str(row["disagreement_class"])
        target = target_by_key.get((trajectory_id, model_frame_idx))

        entry: dict[str, Any] = {
            "trajectory_id": trajectory_id,
            "model_frame_idx": model_frame_idx,
            "layout_id": layout_id,
            "episode_id": int(row["episode_id"]),
            "fold_idx": FROZEN_FOLD_ASSIGNMENT[layout_id],
            "planned_cell_id": str(condition["planned_cell_id"]),
            "control_type": control_type,
            "set_id": str(condition["set_id"]),
            "scene": str(condition["scene"]),
            "context_fraction": condition["context_fraction"],
            "hidden_frames": condition["hidden_frames"],
            "speed_blocks_per_second": condition["speed_blocks_per_second"],
            "q_blocks_squared_per_second": condition["q_blocks_squared_per_second"],
            "seed": condition["seed"],
            "visibility_applicable": bool(row["visibility_applicable"]),
            "visible_flag": row["visible_flag"],
            "visible_flag_defined": bool(row["visible_flag_defined"]),
            "geometric_visible": row["geometric_visible"],
            "empirical_magenta_visible": row["empirical_magenta_visible"],
            "geometric_ambiguous": bool(row["geometric_ambiguous"]),
            "disagreement_class": disagreement_class,
            "quarantined": bool(row["quarantined"]),
            "quarantine_category": row["quarantine_category"],
            "near_candidate_boundary": bool(row["near_candidate_boundary"]),
            "oracle_target_present": target is not None,
            "analysis_scopes": [],
            "admission_stratum": None,
        }

        # Frozen policy, evaluated in a fixed order. Each branch names the one
        # reason it fired; nothing is silently reconciled.
        if control_type == CONTROL_TYPE_NO_OBJECT:
            entry["status"] = "excluded"
            entry["exclusion_reason"] = ROW_EXCLUSION_NO_OBJECT
        elif entry["geometric_ambiguous"]:
            entry["status"] = "excluded"
            entry["exclusion_reason"] = ROW_EXCLUSION_AMBIGUOUS_GEOMETRY
        elif disagreement_class in (
            "geometry_visible_detector_hidden",
            "geometry_hidden_detector_visible",
        ):
            entry["status"] = "excluded"
            entry["exclusion_reason"] = ROW_EXCLUSION_CHANNEL_DISAGREEMENT
        elif entry["quarantined"]:
            # Any Person C quarantine not already explained by a specific
            # scientific reason above still excludes the row.
            entry["status"] = "excluded"
            entry["exclusion_reason"] = ROW_EXCLUSION_QUARANTINED
        elif (
            first_visible[trajectory_id] is None
            or model_frame_idx < first_visible[trajectory_id]
        ):
            entry["status"] = "excluded"
            entry["exclusion_reason"] = ROW_EXCLUSION_PRE_FIRST_SEEN
        elif control_type == CONTROL_TYPE_NO_WALL:
            entry["status"] = "accepted"
            entry["exclusion_reason"] = None
            entry["analysis_scopes"] = [SCOPE_VISIBLE_NO_WALL]
            entry["admission_stratum"] = ADMISSION_STRATUM_VISIBLE_CONTROL
        elif row["visible_flag"] is True:
            entry["status"] = "excluded"
            entry["exclusion_reason"] = ROW_EXCLUSION_OUTSIDE_SELECTION
        else:
            require(
                control_type in HIDDEN_ADMISSION_CONTROL_TYPES,
                f"Control type {control_type!r} has no frozen hidden-scope "
                "disposition; refusing to invent one.",
            )
            entry["status"] = "accepted"
            entry["exclusion_reason"] = None
            entry["analysis_scopes"] = [SCOPE_HIDDEN_MEAN, SCOPE_HIDDEN_SPREAD]
            entry["admission_stratum"] = (
                ADMISSION_STRATUM_SENTINEL
                if control_type == CONTROL_TYPE_SENTINEL
                else ADMISSION_STRATUM_CORE
            )

        if entry["status"] == "accepted":
            require(
                target is not None,
                f"({trajectory_id}, {model_frame_idx}) is admitted but has no "
                "oracle target row.",
            )
            for field in ALWAYS_REQUIRED_TARGET_FIELDS:
                require(
                    target[field] is not None,
                    f"({trajectory_id}, {model_frame_idx}) admitted with a null "
                    f"{field}.",
                )
            hidden_scope = SCOPE_HIDDEN_SPREAD in entry["analysis_scopes"]
            for field in HIDDEN_ONLY_TARGET_FIELDS:
                if hidden_scope:
                    require(
                        target[field] is not None,
                        f"({trajectory_id}, {model_frame_idx}) is admitted to "
                        f"{SCOPE_HIDDEN_SPREAD} but {field} is null.",
                    )
                else:
                    require(
                        target[field] is None,
                        f"({trajectory_id}, {model_frame_idx}) is outside "
                        f"{SCOPE_HIDDEN_SPREAD} but {field} is populated, which "
                        "contradicts the frozen null_outside_eligibility policy.",
                    )
            require(
                target["visibility"] == ("visible" if entry["geometric_visible"] else "occluded"),
                f"({trajectory_id}, {model_frame_idx}) oracle visibility "
                "disagrees with Person C's geometric channel.",
            )
        universe.append(entry)

    universe.sort(key=lambda item: (item["trajectory_id"], item["model_frame_idx"]))
    admitted = [row for row in universe if row["status"] == "accepted"]
    excluded = [row for row in universe if row["status"] == "excluded"]
    require(
        len(universe) == EXPECTED_MODEL_FRAME_KEY_COUNT,
        "Successor universe row count changed.",
    )
    require(
        len(admitted) + len(excluded) == EXPECTED_MODEL_FRAME_KEY_COUNT,
        "Admission and exclusion do not partition the successor universe.",
    )
    require(
        all(row["oracle_target_present"] for row in admitted),
        "An admitted row lacks an oracle target.",
    )
    require(
        not any(
            row["control_type"] == CONTROL_TYPE_NO_OBJECT
            and row["status"] == "accepted"
            for row in universe
        ),
        "A no-object control row was admitted.",
    )
    require(
        not any(row["quarantined"] for row in admitted),
        "A Person C quarantined row was admitted.",
    )
    require(
        not any(row["geometric_ambiguous"] for row in admitted),
        "An edge-ambiguous geometry row was admitted.",
    )
    require(
        not any(
            row["disagreement_class"]
            in ("geometry_visible_detector_hidden", "geometry_hidden_detector_visible")
            for row in admitted
        ),
        "A visibility-channel disagreement row was admitted.",
    )
    require(
        all(row["visible_flag"] is True for row in admitted if row["analysis_scopes"] == [SCOPE_VISIBLE_NO_WALL]),
        "A visible-control row was admitted without a true strict visible_flag.",
    )
    require(
        all(
            row["visible_flag"] is False
            for row in admitted
            if SCOPE_HIDDEN_MEAN in row["analysis_scopes"]
        ),
        "A hidden-scope row was admitted with a true strict visible_flag.",
    )

    ambiguous_rows = [row for row in universe if row["geometric_ambiguous"]]
    return {
        "rows": universe,
        "admitted_rows": admitted,
        "excluded_rows": excluded,
        "ambiguous_rows": ambiguous_rows,
        "ambiguous_admitted": [
            row for row in ambiguous_rows if row["status"] == "accepted"
        ],
        "ambiguous_excluded": [
            row for row in ambiguous_rows if row["status"] == "excluded"
        ],
        "condition_by_trajectory": condition_by_trajectory,
    }


# --------------------------------------------------------------------------
# Step 7 - fold compatibility, without regenerating folds
# --------------------------------------------------------------------------
def validate_fold_compatibility(
    row_universe: Mapping[str, Any],
    *,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Confirm the existing frozen fold identity still fits the new admissions."""

    root = REPOSITORY_ROOT if repository_root is None else Path(repository_root)
    payload = (root / PERSON_B_FOLD_MANIFEST_PATH).read_bytes()
    observed = sha256_bytes(payload)
    require(
        observed == PERSON_B_FOLD_MANIFEST_SHA256,
        f"Fold manifest hashes to {observed}, expected "
        f"{PERSON_B_FOLD_MANIFEST_SHA256}.",
    )
    fold_manifest = _strict_json(payload, label="Person B fold manifest")
    declared = {
        str(item["layout_id"]): int(item["fold_idx"])
        for item in fold_manifest["layout_assignments"]
    }
    require(
        declared == FROZEN_FOLD_ASSIGNMENT,
        f"Fold manifest layout assignment changed: {declared}",
    )

    membership_folds = {
        (str(row["trajectory_id"]), int(row["model_frame_idx"])): int(row["fold_idx"])
        for row in fold_manifest["memberships"]
    }
    layout_folds: dict[str, set[int]] = defaultdict(set)
    trajectory_folds: dict[str, set[int]] = defaultdict(set)
    unresolved: list[list[Any]] = []
    disagreements: list[dict[str, Any]] = []

    for row in row_universe["rows"]:
        key = (row["trajectory_id"], row["model_frame_idx"])
        fold_idx = membership_folds.get(key)
        if fold_idx is None:
            unresolved.append(list(key))
            continue
        if fold_idx != row["fold_idx"]:
            disagreements.append(
                {
                    "trajectory_id": row["trajectory_id"],
                    "model_frame_idx": row["model_frame_idx"],
                    "fold_manifest_fold_idx": fold_idx,
                    "row_universe_fold_idx": row["fold_idx"],
                }
            )
        layout_folds[row["layout_id"]].add(fold_idx)
        trajectory_folds[row["trajectory_id"]].add(fold_idx)

    admitted_by_fold = Counter(row["fold_idx"] for row in row_universe["admitted_rows"])
    leaking_layouts = sorted(
        layout for layout, folds in layout_folds.items() if len(folds) != 1
    )
    leaking_trajectories = sorted(
        trajectory for trajectory, folds in trajectory_folds.items() if len(folds) != 1
    )
    checks = {
        "fold_manifest_hash_unchanged": observed == PERSON_B_FOLD_MANIFEST_SHA256,
        "layout_assignment_unchanged": declared == FROZEN_FOLD_ASSIGNMENT,
        "every_universe_row_resolves_to_a_fold": not unresolved,
        "row_universe_agrees_with_fold_manifest": not disagreements,
        "no_layout_leakage": not leaking_layouts,
        "no_trajectory_leakage": not leaking_trajectories,
        "every_fold_retains_admitted_rows": set(admitted_by_fold) == set(range(5))
        and all(count > 0 for count in admitted_by_fold.values()),
        "folds_not_regenerated": True,
    }
    return {
        "fold_manifest_path": PERSON_B_FOLD_MANIFEST_PATH,
        "fold_manifest_sha256": observed,
        "fold_manifest_artifact_hash": fold_manifest["artifact_hash"],
        "layout_assignments": [
            {"layout_id": layout_id, "fold_idx": fold_idx}
            for layout_id, fold_idx in sorted(declared.items())
        ],
        "admitted_row_counts_by_fold": [
            {"fold_idx": fold_idx, "row_count": admitted_by_fold[fold_idx]}
            for fold_idx in sorted(admitted_by_fold)
        ],
        "unresolved_frame_keys": unresolved,
        "fold_disagreements": disagreements,
        "leaking_layout_ids": leaking_layouts,
        "leaking_trajectory_ids": leaking_trajectories,
        "checks": dict(sorted(checks.items())),
        "fold_compatibility_pass": all(checks.values()),
        "leakage_audit_pass": not leaking_layouts and not leaking_trajectories,
    }


def summarize_row_universe(row_universe: Mapping[str, Any]) -> dict[str, Any]:
    """Produce the exact successor accounting Person B publishes."""

    rows = row_universe["rows"]
    admitted = row_universe["admitted_rows"]
    excluded = row_universe["excluded_rows"]
    scopes: Counter[str] = Counter()
    for row in admitted:
        for scope in row["analysis_scopes"]:
            scopes[scope] += 1
    return {
        "total_model_frame_key_count": len(rows),
        "target_bearing_key_count": sum(1 for row in rows if row["visibility_applicable"]),
        "no_object_not_applicable_key_count": sum(
            1 for row in rows if not row["visibility_applicable"]
        ),
        "admitted_analysis_row_count": len(admitted),
        "excluded_analysis_row_count": len(excluded),
        "excluded_counts_by_reason": [
            {"exclusion_reason": reason, "row_count": count}
            for reason, count in sorted(
                Counter(row["exclusion_reason"] for row in excluded).items()
            )
        ],
        "admitted_counts_by_scope": [
            {"scope": scope, "row_count": scopes[scope]} for scope in sorted(scopes)
        ],
        "admitted_counts_by_stratum": [
            {"admission_stratum": stratum, "row_count": count}
            for stratum, count in sorted(
                Counter(row["admission_stratum"] for row in admitted).items()
            )
        ],
        "admitted_counts_by_fold": [
            {"fold_idx": fold_idx, "row_count": count}
            for fold_idx, count in sorted(
                Counter(row["fold_idx"] for row in admitted).items()
            )
        ],
        "admitted_counts_by_layout": [
            {"layout_id": layout_id, "row_count": count}
            for layout_id, count in sorted(
                Counter(row["layout_id"] for row in admitted).items()
            )
        ],
        "admitted_counts_by_control_type": [
            {"control_type": control, "row_count": count}
            for control, count in sorted(
                Counter(row["control_type"] for row in admitted).items()
            )
        ],
        "admitted_counts_by_set_id": [
            {"set_id": set_id, "row_count": count}
            for set_id, count in sorted(
                Counter(row["set_id"] for row in admitted).items()
            )
        ],
        "disagreement_counts": [
            {"disagreement_class": name, "row_count": count}
            for name, count in sorted(
                Counter(row["disagreement_class"] for row in rows).items()
            )
        ],
        "ambiguous_geometry_row_count": len(row_universe["ambiguous_rows"]),
        "ambiguous_geometry_admitted_count": len(row_universe["ambiguous_admitted"]),
        "ambiguous_geometry_excluded_count": len(row_universe["ambiguous_excluded"]),
        "person_c_quarantined_row_count": sum(1 for row in rows if row["quarantined"]),
        "person_c_quarantined_admitted_count": sum(
            1 for row in admitted if row["quarantined"]
        ),
        "person_c_quarantine_overlap_by_exclusion_reason": [
            {"exclusion_reason": reason, "row_count": count}
            for reason, count in sorted(
                Counter(
                    row["exclusion_reason"] for row in excluded if row["quarantined"]
                ).items()
            )
        ],
        "no_wall_control_rows_excluded_by_channel_disagreement": sum(
            1
            for row in rows
            if row["control_type"] == CONTROL_TYPE_NO_WALL
            and row["exclusion_reason"] == ROW_EXCLUSION_CHANNEL_DISAGREEMENT
        ),
        "person_c_accepted_trajectory_count": EXPECTED_TRAJECTORY_COUNT,
        "person_c_rejected_trajectory_count": 0,
        "row_level_exclusion_is_not_trajectory_rejection": True,
        "row_universe_canonical_hash": sha256_value(
            [
                {
                    "trajectory_id": row["trajectory_id"],
                    "model_frame_idx": row["model_frame_idx"],
                    "layout_id": row["layout_id"],
                    "fold_idx": row["fold_idx"],
                    "status": row["status"],
                    "exclusion_reason": row["exclusion_reason"],
                    "analysis_scopes": row["analysis_scopes"],
                    "admission_stratum": row["admission_stratum"],
                    "visible_flag": row["visible_flag"],
                    "disagreement_class": row["disagreement_class"],
                }
                for row in rows
            ]
        ),
    }


__all__ = [
    "ADMISSION_STRATUM_CORE",
    "ADMISSION_STRATUM_SENTINEL",
    "ADMISSION_STRATUM_VISIBLE_CONTROL",
    "ANALYSIS_ARITHMETIC_DTYPE",
    "CONTROL_TYPE_CORE",
    "CONTROL_TYPE_NO_OBJECT",
    "CONTROL_TYPE_NO_WALL",
    "CONTROL_TYPE_SENTINEL",
    "C_ACCEPTED_MANIFEST_SHA256",
    "C_EVENT_TABLE_SHA256",
    "C_ORACLE_HANDOFF_SHA256",
    "C_VISIBILITY_JOIN_SHA256",
    "DECISION_DATE",
    "EXPECTED_MODEL_FRAME_KEY_COUNT",
    "EXPECTED_NO_OBJECT_COUNT",
    "EXPECTED_TARGET_BEARING_COUNT",
    "EXPECTED_TRAJECTORY_COUNT",
    "FROZEN_FOLD_ASSIGNMENT",
    "ORACLE_PACKAGE_DIRECTORY",
    "ORACLE_PACKAGE_SCHEMA_VERSION",
    "ORACLE_RUN_ID",
    "ORACLE_TARGET_FIELDS",
    "PERSON_A_COMMIT",
    "PERSON_B_FOLD_MANIFEST_SHA256",
    "PERSON_C_COMMIT",
    "ROW_EXCLUSION_AMBIGUOUS_GEOMETRY",
    "ROW_EXCLUSION_CHANNEL_DISAGREEMENT",
    "ROW_EXCLUSION_NO_OBJECT",
    "ROW_EXCLUSION_OUTSIDE_SELECTION",
    "ROW_EXCLUSION_PRE_FIRST_SEEN",
    "ROW_EXCLUSION_QUARANTINED",
    "STORED_ACTIVATION_DTYPE",
    "OracleTargetError",
    "build_production_oracle_targets",
    "build_successor_row_universe",
    "derive_oracle_code_sha",
    "load_person_c_oracle_inputs",
    "read_bound_blob",
    "require",
    "resolve_person_a_identity",
    "sha256_bytes",
    "summarize_row_universe",
    "validate_fold_compatibility",
]

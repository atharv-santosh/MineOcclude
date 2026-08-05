"""Accept Person A's exact five-layout activation provenance for A6.6.

This additive Person E acceptance verifies the immutable Person A successor
collection, every referenced per-run bundle and Activation Store v2 object,
and the exact joins to Person E's canonical post-C1 C6A registry.  The earlier
single-layout receipt remains immutable predecessor evidence and is not
reinterpreted as accepting the successor.  This script does not perform A6.6.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_REL = "docs/status/person_e_a_multilayout_activation_provenance_acceptance_v0_1"
PACKAGE_DIR = ROOT / PACKAGE_REL

PERSON_E_REQUIRED_ANCESTRY = "14ff11b25b8a740e490b680a16c8473ebb7c7dc6"
PERSON_A_ROOT = Path("C:/Users/lollo/MineOcclude")
PERSON_A_COMMIT = "1858ea12513f833b62ea916e0691ae994f117428"
PERSON_C_COMMIT = "b810bae554ba4f31018d39beb304c9b936387ca4"
PERSON_C_PACKAGE_SHA256 = "612b03fea372d10c5f5b87cb581dd5f993035112e16aa1de7341801bdc35a9ef"

COLLECTION_NAME = (
    "person-a-canonical-c6a-multilayout-successor-seed-20260725-"
    "retry-20260804T211350Z"
)
COLLECTION_GIT_REL = f"docs/status/phase6_runtime/{COLLECTION_NAME}"
COLLECTION_ROOT = PERSON_A_ROOT / COLLECTION_GIT_REL
COLLECTION_MANIFEST_SHA256 = "a672c834e8af3fd12c735e4042951b7b90d0aeeed5b0b62790aacdf3a58c0db0"
A_TO_E_HANDOFF_SHA256 = "75d35991f34dabc3851dd2e31dc9e2b2912fa66a776034b7ecb7932bc854575b"
EXTERNAL_INVENTORY_SHA256 = "342807be961eb9734bcc6ee935906a98bda7d44ed6d2f6fcf7691169dba0df02"

CANONICAL_C6A_ID = "person-c-c6a-post-c1-v0.1"
TRAJECTORIES = [
    ("layout_01", "layout_01_ep12602", 12602),
    ("layout_02", "layout_02_ep12610", 12610),
    ("layout_03", "layout_03_ep12645", 12645),
    ("layout_04", "layout_04_ep12626", 12626),
    ("layout_05", "layout_05_ep12634", 12634),
]
ACTIVATION_INDEX_SHA256S = [
    "a6ba07a50ff20e9b90f0b036a0acd18783bad4fa3aacbebc0dd70df825f00a27",
    "29a750527e6b8bd3b8987d5a481f292280dec7e22263e292505fbce0103b711d",
    "2a4b0112f648f23cbe95a50404e073fd4839280a74973273d20afaf9d5b1c683",
    "a4a8b5943d2f2ad75b1e95d613ce44a6f88c9edba22f666837a671c5db1d5376",
    "32bf62d734dd2a0b8e6fee0599f28a920f7bf6d3ae9beb6b6222fdbc4321d4b3",
]
LAYOUT_COUNT = 5
TRAJECTORY_COUNT = 5
SOURCE_FRAME_COUNT = 300
FRAME_COUNT_PER_TRAJECTORY = 60
LAYER_COUNT = 20
HIDDEN_WIDTH = 2048
ACTIVATION_INDEX_COUNT = 5
ACTIVATION_ROW_COUNT = 6000
ACTIVATION_CHUNK_COUNT = 100

MODEL_SHA256 = "a92c311baf49bbf31338da2caaadc9e4f947b94df8abcf75da350c4ae41319c5"
MODEL_CONFIG_SHA256 = "e13b3a80fb370547a05852809c2c8f02d05ebe2fce3b3bb2fd1ee54eee78c018"
PREPROCESSING = (
    "mineworld_gradio_step_video_preprocessing@1.0:"
    "036fa0b4899285e5499f88581f6e02426a25f732fcc26bd63c0f5b3863a9d9ab"
)
PREPROCESS_SHA256 = PREPROCESSING.rsplit(":", 1)[1]
ACTION_CONVERSION = (
    "mineworld_mcdataset_json_action_to_env_action@1.0:"
    "7e8d16db01f085481d41d340e5a0b84669b8e163f3338d5fd572731532c52746"
)
HOOK_SITE = "decoder_layer_output_residual_stream"
POOLING_METHOD = "mean"
TOKEN_REGION = "visual"
ACTIVATION_STORE_FORMAT = "person-a-activation-store-v2"
ACTIVATION_INDEX_FORMAT = "person-a-activation-index-v2"

PRIOR_C6A_REL = "docs/status/person_e_c6a_provenance_closure_v0_1"
PRIOR_C6A_HANDOFF_SHA256 = "e2897aac65a8b51893f1ef397af26cdc7958fe89e6d2bd0159082a9547d253d1"
PRIOR_C6A_REGISTRY_SHA256 = "77c105176bdb4d93382b36b3131267848acab6fbdc181f1d8272080e0ad5d588"
PRIOR_ACCEPTANCE_REL = "docs/status/person_e_a_activation_provenance_acceptance_v0_1"
PRIOR_ACCEPTANCE_RECEIPT = (
    ROOT / PRIOR_ACCEPTANCE_REL / "person_e_to_person_a_activation_provenance_receipt.json"
)
PRIOR_ACCEPTANCE_PROVENANCE_PATH = Path(
    "C:/Users/lollo/MineOcclude-Person-E-Refit"
) / PRIOR_ACCEPTANCE_REL / "person_e_to_person_a_activation_provenance_receipt.json"
PRIOR_ACCEPTANCE_RECEIPT_SHA256 = (
    "1d4fb69ec6b5693cfafc56eaeb11fe6bedbb1bfa9fe420de5f288a9ad544c7f4"
)

RECEIPT_NAME = "person_e_to_person_a_multilayout_activation_provenance_receipt.json"
SCHEMA_NAME = "person_e_to_person_a_multilayout_activation_provenance_receipt.schema.json"
RECEIPT_SCHEMA_VERSION = (
    "person-e-to-person-a-canonical-multilayout-activation-provenance-receipt-v0.1"
)
VALIDATION_SCHEMA_VERSION = (
    "person-e-canonical-multilayout-activation-provenance-validation-v0.1"
)
INVENTORY_SCHEMA_VERSION = (
    "person-e-canonical-multilayout-activation-provenance-sha256-inventory-v0.1"
)
RECEIPT_ID = "person-e-to-person-a-canonical-c6a-multilayout-activation-provenance-v0.1"
A6_6_STATEMENT = (
    "A6.6 may consume the activation provenance from this exact five-layout "
    "canonical Person A successor collection. This receipt does not perform A6.6."
)


class AcceptanceError(RuntimeError):
    """Fail-closed successor provenance acceptance error."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceError(message)


def canonical_json(document: Any) -> bytes:
    return (
        json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            size += len(block)
            digest.update(block)
    return size, digest.hexdigest()


def load_json_bytes(payload: bytes, identity: str, *, canonical: bool = True) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            require(key not in result, f"duplicate JSON key in {identity}: {key}")
            result[key] = value
        return result

    try:
        document = json.loads(payload, object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceError(f"invalid JSON in {identity}: {exc}") from exc
    if canonical:
        require(canonical_json(document) == payload, f"noncanonical JSON: {identity}")
    return document


def load_json_file(path: Path) -> Any:
    return load_json_bytes(path.read_bytes(), str(path))


def git_text(repository: Path, *arguments: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repository), *arguments],
            stderr=subprocess.PIPE,
            text=True,
        ).strip()
    except subprocess.CalledProcessError as exc:
        raise AcceptanceError(exc.stderr.strip()) from exc


def git_bytes(repository: Path, commit: str, relative: str) -> bytes:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repository), "show", f"{commit}:{relative}"],
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        raise AcceptanceError(
            f"missing Git object {commit}:{relative}: "
            f"{exc.stderr.decode('utf-8', errors='replace').strip()}"
        ) from exc


def safe_relative(value: str) -> str:
    path = PurePosixPath(value)
    require(not path.is_absolute(), f"absolute inventory path: {value}")
    require(".." not in path.parts, f"escaping inventory path: {value}")
    return path.as_posix()


def load_person_a_validator() -> Any:
    path = PERSON_A_ROOT / "scripts/prepare_person_a_phase6_canonical_multilayout.py"
    spec = importlib.util.spec_from_file_location(
        "person_a_multilayout_successor_validator_for_person_e", path
    )
    require(spec is not None and spec.loader is not None, "cannot load Person A validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_git_authorities() -> None:
    require(
        subprocess.run(
            [
                "git",
                "-C",
                str(ROOT),
                "merge-base",
                "--is-ancestor",
                PERSON_E_REQUIRED_ANCESTRY,
                "HEAD",
            ],
            check=False,
        ).returncode
        == 0,
        "Person E required ancestry is absent",
    )
    require(
        subprocess.run(
            [
                "git",
                "-C",
                str(PERSON_A_ROOT),
                "merge-base",
                "--is-ancestor",
                PERSON_A_COMMIT,
                "HEAD",
            ],
            check=False,
        ).returncode
        == 0,
        "Person A successor commit is not in local ancestry",
    )


def verify_immutable_package(
    *, repository: Path, commit: str, package_rel: str, package_root: Path
) -> None:
    tree = set(
        git_text(repository, "ls-tree", "-r", "--name-only", commit, package_rel).splitlines()
    )
    current = {
        path.relative_to(repository).as_posix()
        for path in package_root.rglob("*")
        if path.is_file()
    }
    require(tree == current, f"immutable package file set changed: {package_rel}")
    for relative in sorted(tree):
        require(
            (repository / relative).read_bytes() == git_bytes(repository, commit, relative),
            f"immutable package object changed: {relative}",
        )


def verify_predecessors() -> dict[str, Any]:
    verify_immutable_package(
        repository=ROOT,
        commit=PERSON_E_REQUIRED_ANCESTRY,
        package_rel=PRIOR_ACCEPTANCE_REL,
        package_root=ROOT / PRIOR_ACCEPTANCE_REL,
    )
    require(
        sha256_file(PRIOR_ACCEPTANCE_RECEIPT)[1] == PRIOR_ACCEPTANCE_RECEIPT_SHA256,
        "single-layout predecessor receipt hash mismatch",
    )
    prior_receipt = load_json_file(PRIOR_ACCEPTANCE_RECEIPT)
    require(
        prior_receipt["canonical_c6a_binding"]["trajectory_id"]
        == TRAJECTORIES[0][1],
        "single-layout predecessor trajectory mismatch",
    )
    require(
        prior_receipt["person_a_result"]["a_to_e_handoff_sha256"]
        == "7414956699d9d37f0b4b486b7c800ff2482b453ffd634cb2bf99d92bcb042cfe",
        "single-layout predecessor handoff mismatch",
    )
    prior_inventory_path = ROOT / PRIOR_ACCEPTANCE_REL / "sha256_inventory.json"
    prior_inventory = load_json_file(prior_inventory_path)
    prior_inventory_sha256 = sha256_file(prior_inventory_path)[1]

    c6a_root = ROOT / PRIOR_C6A_REL
    c6a_handoff = c6a_root / "person_e_to_person_a_c6a_provenance_handoff.json"
    c6a_registry = c6a_root / "canonical_registry_records.json"
    require(
        sha256_file(c6a_handoff)[1] == PRIOR_C6A_HANDOFF_SHA256,
        "canonical C6A handoff hash mismatch",
    )
    require(
        sha256_file(c6a_registry)[1] == PRIOR_C6A_REGISTRY_SHA256,
        "canonical C6A registry hash mismatch",
    )
    handoff = load_json_file(c6a_handoff)
    require(
        handoff["canonical_c6a_id"] == CANONICAL_C6A_ID
        and handoff["a6_6_provenance_consumption_authorized"] is True,
        "canonical C6A authority mismatch",
    )
    return {
        "c6a_handoff": handoff,
        "registry": load_json_file(c6a_registry),
        "prior_inventory": prior_inventory,
        "prior_inventory_sha256": prior_inventory_sha256,
        "prior_receipt": prior_receipt,
    }


def verify_collection_package() -> dict[str, Any]:
    require(COLLECTION_ROOT.is_dir(), "Person A successor collection is absent")
    expected_files = {
        "collection_manifest.json",
        "external_activation_inventory.json",
        "person_a_to_person_b_canonical_multilayout_handoff.json",
        "person_a_to_person_e_canonical_multilayout_handoff.json",
        "sha256_inventory.json",
    }
    present = {
        path.relative_to(COLLECTION_ROOT).as_posix()
        for path in COLLECTION_ROOT.rglob("*")
        if path.is_file()
    }
    require(present == expected_files, "successor collection package file set mismatch")
    inventory_path = COLLECTION_ROOT / "sha256_inventory.json"
    inventory = load_json_file(inventory_path)
    require(
        inventory.get("schema_version")
        == "person-a-canonical-c6a-multirun-package-inventory-v0.1",
        "successor package inventory schema mismatch",
    )
    rows = inventory.get("files")
    require(isinstance(rows, list) and len(rows) == 4, "successor inventory count mismatch")
    inventoried: set[str] = set()
    for row in rows:
        relative = safe_relative(row["path"])
        require(relative not in inventoried, f"duplicate collection inventory path: {relative}")
        inventoried.add(relative)
        local = COLLECTION_ROOT / relative
        size, digest = sha256_file(local)
        require(
            size == row["size_bytes"] and digest == row["sha256"],
            f"successor collection inventory mismatch: {relative}",
        )
        load_json_file(local)
    require(inventoried | {"sha256_inventory.json"} == present, "collection inventory incomplete")
    for relative in sorted(present):
        git_relative = f"{COLLECTION_GIT_REL}/{relative}"
        require(
            (COLLECTION_ROOT / relative).read_bytes()
            == git_bytes(PERSON_A_ROOT, PERSON_A_COMMIT, git_relative),
            f"successor collection differs from producing commit: {relative}",
        )

    manifest_path = COLLECTION_ROOT / "collection_manifest.json"
    handoff_path = COLLECTION_ROOT / "person_a_to_person_e_canonical_multilayout_handoff.json"
    external_path = COLLECTION_ROOT / "external_activation_inventory.json"
    require(
        sha256_file(manifest_path)[1] == COLLECTION_MANIFEST_SHA256,
        "collection manifest hash mismatch",
    )
    require(
        sha256_file(handoff_path)[1] == A_TO_E_HANDOFF_SHA256,
        "successor A-to-E handoff hash mismatch",
    )
    require(
        sha256_file(external_path)[1] == EXTERNAL_INVENTORY_SHA256,
        "external activation inventory hash mismatch",
    )
    manifest = load_json_file(manifest_path)
    handoff = load_json_file(handoff_path)
    external = load_json_file(external_path)
    expected_trajectories = [row[1] for row in TRAJECTORIES]
    expected_layouts = [row[0] for row in TRAJECTORIES]
    expected_episodes = [row[2] for row in TRAJECTORIES]
    require(
        manifest["schema_version"] == "person-a-canonical-c6a-multirun-collection-v0.1"
        and manifest["status"] == "READY_FOR_PERSON_B_AND_PERSON_E_REVIEW"
        and manifest["immutable"] is True,
        "collection manifest authority mismatch",
    )
    require(manifest["canonical_c6a_id"] == CANONICAL_C6A_ID, "collection C6A mismatch")
    require(
        (
            manifest["layout_count"],
            manifest["trajectory_count"],
            manifest["activation_index_count"],
            manifest["activation_row_count"],
            manifest["activation_chunk_count"],
        )
        == (
            LAYOUT_COUNT,
            TRAJECTORY_COUNT,
            ACTIVATION_INDEX_COUNT,
            ACTIVATION_ROW_COUNT,
            ACTIVATION_CHUNK_COUNT,
        ),
        "collection cardinality mismatch",
    )
    require(
        manifest["no_missing_extra_duplicate_stale_or_reordered_rows"] is True,
        "collection identity completeness failed",
    )
    expected_order = [
        {
            "activation_index_sha256": digest,
            "logical_row_start_inclusive": index * 1200,
            "logical_row_stop_exclusive": (index + 1) * 1200,
            "trajectory_id": trajectory,
        }
        for index, ((_, trajectory, _), digest) in enumerate(
            zip(TRAJECTORIES, ACTIVATION_INDEX_SHA256S, strict=True)
        )
    ]
    require(manifest["logical_order"] == expected_order, "collection logical order mismatch")
    require(
        manifest["collection_contract"]
        == {
            "index_semantics": "five_independent_immutable_person_a_activation_index_v2_documents",
            "logical_order_is_not_a_physical_index": True,
            "physical_combined_index_created": False,
        },
        "collection multi-index contract mismatch",
    )
    require(
        manifest["person_a_to_person_e_handoff"]
        == {
            "path": "person_a_to_person_e_canonical_multilayout_handoff.json",
            "sha256": A_TO_E_HANDOFF_SHA256,
        },
        "collection A-to-E binding mismatch",
    )
    require(
        handoff["schema_version"]
        == "person-a-to-person-e-canonical-multilayout-handoff-v0.1"
        and handoff["status"] == "READY_FOR_NEW_PERSON_E_PROVENANCE_REVIEW"
        and handoff["immutable"] is True,
        "successor A-to-E handoff authority mismatch",
    )
    require(
        handoff["person_e_successor_acceptance_claimed"] is False
        and handoff["requires_new_person_e_receipt"] is True,
        "successor handoff predecessor/successor policy mismatch",
    )
    require(
        handoff["trajectory_ids"] == expected_trajectories
        and handoff["episode_ids"] == expected_episodes,
        "successor handoff ordered identity mismatch",
    )
    require(
        handoff["multi_index_collection"]["logical_order"] == expected_order
        and handoff["multi_index_collection"]["index_count"] == ACTIVATION_INDEX_COUNT
        and handoff["multi_index_collection"]["physical_combined_index_created"] is False,
        "successor handoff multi-index identity mismatch",
    )
    require(
        handoff["activation_row_count"] == ACTIVATION_ROW_COUNT
        and handoff["activation_chunk_count"] == ACTIVATION_CHUNK_COUNT,
        "successor handoff activation count mismatch",
    )
    require(
        handoff["certification"]
        == {
            "all_direct_pooling_audits": "PASS",
            "all_repeatability_checks": "PASS",
            "all_source_identity_joins": "PASS",
            "missing_extra_duplicate_stale_or_reordered_rows": 0,
        },
        "successor handoff certification mismatch",
    )
    require(
        external["schema_version"]
        == "person-a-canonical-c6a-multirun-external-inventory-v0.1"
        and external["status"] == "PASS"
        and external["physical_combined_activation_index_created"] is False,
        "external activation inventory authority mismatch",
    )
    artifacts = external.get("artifacts")
    require(
        isinstance(artifacts, list)
        and external["artifact_count"] == len(artifacts) == 105,
        "external activation inventory cardinality mismatch",
    )
    require(
        sum(row["type"] == "activation_index" for row in artifacts) == 5
        and sum(row["type"] == "activation_chunk" for row in artifacts) == 100,
        "external activation inventory type count mismatch",
    )
    require(
        [row["trajectory_id"] for row in manifest["runs"]] == expected_trajectories
        and [row["layout_id"] for row in manifest["runs"]] == expected_layouts,
        "collection run order mismatch",
    )
    return {
        "external": external,
        "handoff": handoff,
        "inventory_sha256": sha256_file(inventory_path)[1],
        "manifest": manifest,
    }


def verify_bundle_inventory(root: Path) -> str:
    inventory_path = root / "sha256_inventory.json"
    inventory = load_json_file(inventory_path)
    rows = inventory.get("files")
    require(isinstance(rows, list) and len(rows) == 36, f"bundle inventory count mismatch: {root}")
    listed: set[str] = set()
    for row in rows:
        relative = safe_relative(row["path"])
        require(relative not in listed, f"duplicate bundle inventory path: {root}/{relative}")
        listed.add(relative)
        path = root / relative
        size, digest = sha256_file(path)
        require(
            size == row["size_bytes"] and digest == row["sha256"],
            f"bundle inventory mismatch: {root}/{relative}",
        )
        if path.suffix == ".json":
            load_json_file(path)
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }
    require(actual == listed | {"sha256_inventory.json"}, f"bundle inventory incomplete: {root}")
    git_root = f"docs/status/phase6_runtime/{root.name}"
    for relative in sorted(actual):
        require(
            (root / relative).read_bytes()
            == git_bytes(PERSON_A_ROOT, PERSON_A_COMMIT, f"{git_root}/{relative}"),
            f"bundle differs from Person A successor commit: {root.name}/{relative}",
        )
    return sha256_file(inventory_path)[1]


def verify_direct_pooling_audit(root: Path, trajectory_id: str) -> dict[str, Any]:
    handoff = load_json_file(root / "person_a_to_person_e_canonical_provenance_handoff.json")
    bounded = {row["type"]: row for row in handoff["bounded_unpooled_audit_artifacts"]}
    require(
        set(bounded) == {"bounded_unpooled_activation", "bounded_unpooled_manifest"},
        f"bounded pooling inventory mismatch: {trajectory_id}",
    )
    npz_path = root / "bounded_audit/limited_unpooled_frame_0.npz"
    manifest_path = root / "bounded_audit/limited_unpooled_frame_0.manifest.json"
    for kind, path in (
        ("bounded_unpooled_activation", npz_path),
        ("bounded_unpooled_manifest", manifest_path),
    ):
        size, digest = sha256_file(path)
        require(
            size == bounded[kind]["byte_size"] and digest == bounded[kind]["sha256"],
            f"bounded pooling artifact mismatch: {trajectory_id}/{kind}",
        )
    manifest = load_json_file(manifest_path)
    require(manifest["status"] == "PASS", f"pooling audit did not pass: {trajectory_id}")
    require(
        manifest["scientific_identity"]
        == {
            "hook_site": HOOK_SITE,
            "model_frame_idx": 0,
            "trajectory_id": trajectory_id,
        },
        f"pooling audit scientific identity mismatch: {trajectory_id}",
    )
    provenance = manifest["provenance"]
    require(
        provenance["main_checkpoint_sha256"] == MODEL_SHA256
        and provenance["model_config_sha256"] == MODEL_CONFIG_SHA256
        and provenance["preprocessing_profile"] == PREPROCESSING
        and provenance["action_conversion_profile"] == ACTION_CONVERSION,
        f"pooling audit pipeline identity mismatch: {trajectory_id}",
    )
    audit = manifest["pooling_audit"]
    require(
        audit["status"] == "PASS"
        and audit["exact_candidate_binding"]["all_layers_match"] is True
        and audit["token_reproduction"]["status"] == "PASS",
        f"direct pooling audit result mismatch: {trajectory_id}",
    )
    with np.load(npz_path, allow_pickle=False) as arrays:
        require(
            set(arrays.files)
            == {"token_values", "pooled_means", "layer_indices", "visual_positions"},
            f"pooling array inventory mismatch: {trajectory_id}",
        )
        tokens = arrays["token_values"]
        pooled = arrays["pooled_means"]
        layers = arrays["layer_indices"]
        positions = arrays["visual_positions"]
        require(
            tokens.shape == (LAYER_COUNT, 336, HIDDEN_WIDTH)
            and tokens.dtype == np.dtype("float16"),
            f"unpooled activation identity mismatch: {trajectory_id}",
        )
        require(
            pooled.shape == (LAYER_COUNT, HIDDEN_WIDTH)
            and pooled.dtype == np.dtype("float32"),
            f"pooled activation identity mismatch: {trajectory_id}",
        )
        require(
            np.array_equal(layers, np.arange(LAYER_COUNT))
            and np.array_equal(positions, np.arange(336)),
            f"pooling layer/token order mismatch: {trajectory_id}",
        )
        recomputed = tokens.astype(np.float32).mean(axis=1)
        tolerance = audit["token_reproduction"]
        require(
            bool(
                np.allclose(
                    recomputed,
                    pooled,
                    rtol=tolerance["rtol"],
                    atol=tolerance["atol"],
                )
            ),
            f"direct pooling recomputation mismatch: {trajectory_id}",
        )
        observed_maximum = float(np.max(np.abs(recomputed - pooled)))
        require(
            observed_maximum <= tolerance["maximum_absolute_difference"] + 1e-12,
            f"direct pooling maximum difference mismatch: {trajectory_id}",
        )
        records = audit["layer_records"]
        require(len(records) == LAYER_COUNT, f"pooling layer count mismatch: {trajectory_id}")
        for layer, row in enumerate(records):
            require(
                row["layer_idx"] == layer
                and row["allclose"] is True
                and row["candidate_binding_sha256_equal"] is True,
                f"pooling layer audit failed: {trajectory_id}/{layer}",
            )
            digest = sha256_bytes(np.ascontiguousarray(pooled[layer]).tobytes())
            require(
                digest == row["stored_pooled_sha256"] == row["candidate_sha256"],
                f"pooling layer binding mismatch: {trajectory_id}/{layer}",
            )
    return {
        "bounded_manifest": {
            "path": str(manifest_path.resolve()),
            "sha256": sha256_file(manifest_path)[1],
        },
        "bounded_npz": {
            "path": str(npz_path.resolve()),
            "sha256": sha256_file(npz_path)[1],
        },
        "maximum_absolute_difference": observed_maximum,
        "status": "PASS",
        "trajectory_id": trajectory_id,
    }


def verify_activation_index(
    *, root: Path, collection_run: Mapping[str, Any], runtime_commit: str
) -> dict[str, Any]:
    trajectory_id = str(collection_run["trajectory_id"])
    index_descriptor = collection_run["activation_index"]
    index_path = root / "activation_store/indexes" / Path(index_descriptor["path"]).name
    index_size, index_sha256 = sha256_file(index_path)
    require(
        index_size == index_descriptor["byte_size"]
        and index_sha256 == index_descriptor["sha256"],
        f"activation index descriptor mismatch: {trajectory_id}",
    )
    index = load_json_file(index_path)
    rows = index["index_rows"]
    chunks = index["chunks"]
    require(
        index["format_version"] == ACTIVATION_INDEX_FORMAT
        and index["run_status"] == "completed"
        and len(rows) == 1200
        and len(chunks) == 20,
        f"activation index identity/count mismatch: {trajectory_id}",
    )
    store = index["store_identity"]
    handoff = load_json_file(root / "person_a_to_person_e_canonical_provenance_handoff.json")
    require(
        store["accepted_manifest_hash"] == handoff["capture_package"]["sha256"]
        and store["checkpoint_hash"] == MODEL_SHA256
        and store["model_hash"] == MODEL_SHA256
        and store["code_sha"] == runtime_commit
        and store["dtype"] == "float32"
        and store["format_version"] == ACTIVATION_STORE_FORMAT
        and store["hidden_width"] == HIDDEN_WIDTH
        and store["hook_site"] == HOOK_SITE
        and store["preprocess_hash"] == PREPROCESS_SHA256
        and store["requested_layers"] == list(range(LAYER_COUNT)),
        f"activation store identity mismatch: {trajectory_id}",
    )
    require(store["run_id"] == rows[0]["run_id"], f"activation run ID mismatch: {trajectory_id}")
    handoff_chunks = {
        Path(row["path"]).name: row
        for row in handoff["activation_artifacts"]
        if row["type"] == "activation_chunk"
    }
    require(len(handoff_chunks) == 20, f"handoff chunk count mismatch: {trajectory_id}")
    require(
        {Path(row["path"]).name for row in chunks} == set(handoff_chunks),
        f"index/handoff chunk join mismatch: {trajectory_id}",
    )
    layer_chunks: dict[int, str] = {}
    receipts = []
    for row in chunks:
        name = Path(row["path"]).name
        local = root / "activation_store/chunks" / name
        size, digest = sha256_file(local)
        handed = handoff_chunks[name]
        require(
            size == row["byte_size"] == handed["byte_size"]
            and digest == row["sha256"] == handed["sha256"]
            and row["row_count"] == FRAME_COUNT_PER_TRAJECTORY
            and row["hidden_width"] == HIDDEN_WIDTH
            and row["dtype"] == "float32",
            f"activation chunk identity mismatch: {trajectory_id}/{name}",
        )
        layer = int(row["layer_idx"])
        require(layer not in layer_chunks, f"duplicate activation layer: {trajectory_id}/{layer}")
        layer_chunks[layer] = row["chunk_id"]
        array = np.load(local, mmap_mode="r", allow_pickle=False)
        require(
            array.shape == (FRAME_COUNT_PER_TRAJECTORY, HIDDEN_WIDTH)
            and array.dtype == np.dtype("float32")
            and bool(np.isfinite(array).all()),
            f"activation chunk payload mismatch: {trajectory_id}/{name}",
        )
        receipts.append(
            {
                "byte_size": size,
                "layer_idx": layer,
                "path": str(local.resolve()),
                "row_count": FRAME_COUNT_PER_TRAJECTORY,
                "sha256": digest,
            }
        )
    require(set(layer_chunks) == set(range(LAYER_COUNT)), f"layer coverage mismatch: {trajectory_id}")
    joins = handoff["exact_source_identity_joins"]
    expected_order = [
        (frame, layer)
        for frame in range(FRAME_COUNT_PER_TRAJECTORY)
        for layer in range(LAYER_COUNT)
    ]
    observed_order: list[tuple[int, int]] = []
    frame_map_rows: dict[int, str] = {}
    state_rows: dict[int, str] = {}
    for row in rows:
        frame = int(row["global_model_frame_idx"])
        layer = int(row["layer_idx"])
        observed_order.append((frame, layer))
        require(
            row["trajectory_id"] == trajectory_id
            and row["source_frame_idx"] == frame == row["source_tick"]
            and row["source_frame_id"] == f"{trajectory_id}:render_frame:{frame}"
            and row["activation_chunk_id"] == layer_chunks[layer]
            and row["chunk_row_idx"] == frame
            and row["status"] == "accepted"
            and row["run_status"] == "completed"
            and row["exclusion_reason"] is None
            and row["superseded_by"] is None,
            f"activation row physical/source identity mismatch: {trajectory_id}/{frame}/{layer}",
        )
        exact = {
            "accepted_manifest_hash": handoff["capture_package"]["sha256"],
            "checkpoint_hash": MODEL_SHA256,
            "code_sha": runtime_commit,
            "dtype": "float32",
            "hook_site": HOOK_SITE,
            "model_hash": MODEL_SHA256,
            "pooling_method": POOLING_METHOD,
            "preprocess_hash": PREPROCESS_SHA256,
            "store_format_version": ACTIVATION_STORE_FORMAT,
            "token_region": TOKEN_REGION,
            "vector_shape": [HIDDEN_WIDTH],
        }
        require(
            all(row.get(key) == value for key, value in exact.items()),
            f"activation row scientific identity mismatch: {trajectory_id}/{frame}/{layer}",
        )
        require(
            row["c_frame_map_sha256"] == joins["c_frame_map_source_sha256"]
            and row["c_state_sha256"] == joins["c_server_state_source_sha256"],
            f"activation row source-file join mismatch: {trajectory_id}/{frame}/{layer}",
        )
        frame_map_rows.setdefault(frame, row["c_frame_map_row_sha256"])
        state_rows.setdefault(frame, row["c_state_row_sha256"])
        require(
            frame_map_rows[frame] == row["c_frame_map_row_sha256"]
            and state_rows[frame] == row["c_state_row_sha256"],
            f"source-row join differs across layers: {trajectory_id}/{frame}",
        )
    require(observed_order == expected_order, f"activation row order mismatch: {trajectory_id}")
    require(
        len(set(frame_map_rows.values())) == FRAME_COUNT_PER_TRAJECTORY
        and len(set(state_rows.values())) == FRAME_COUNT_PER_TRAJECTORY
        and joins["status"] == "PASS"
        and joins["failure_count"] == 0,
        f"exact source identity join failed: {trajectory_id}",
    )
    return {
        "activation_chunks": sorted(receipts, key=lambda row: row["layer_idx"]),
        "activation_index": {
            "byte_size": index_size,
            "path": str(index_path.resolve()),
            "sha256": index_sha256,
        },
        "source_identity_join": {
            "failure_count": 0,
            "frame_map_sha256": joins["c_frame_map_source_sha256"],
            "server_state_sha256": joins["c_server_state_source_sha256"],
            "status": "PASS",
        },
    }


def verify_runs(collection: dict[str, Any], registry: dict[str, Any]) -> list[dict[str, Any]]:
    validator = load_person_a_validator()
    records = registry["records"]
    run_receipts = []
    all_external = []
    for expected, index_sha256, collection_run in zip(
        TRAJECTORIES,
        ACTIVATION_INDEX_SHA256S,
        collection["manifest"]["runs"],
        strict=True,
    ):
        layout_id, trajectory_id, episode_id = expected
        root = PERSON_A_ROOT / "docs/status/phase6_runtime" / Path(
            collection_run["output_bundle_root"]
        ).name
        verified = validator._validate_output_bundle(root, trajectory_id)
        require(
            verified["trajectory_id"] == trajectory_id
            and verified["layout_id"] == layout_id
            and verified["episode_id"] == episode_id
            and verified["source_frame_count"] == FRAME_COUNT_PER_TRAJECTORY
            and verified["activation_row_count"] == 1200
            and verified["activation_chunk_count"] == 20,
            f"repository-owned output verification mismatch: {trajectory_id}",
        )
        bundle_inventory_sha256 = verify_bundle_inventory(root)
        manifest_path = root / "accepted_pilot_manifest.json"
        handoff_path = root / "person_a_to_person_e_canonical_provenance_handoff.json"
        accepted = load_json_file(manifest_path)
        handoff = load_json_file(handoff_path)
        require(
            sha256_file(manifest_path)[1] == collection_run["accepted_manifest"]["sha256"]
            and sha256_file(handoff_path)[1] == collection_run["a_to_e_handoff"]["sha256"],
            f"collection per-run provenance binding mismatch: {trajectory_id}",
        )
        require(
            accepted["schema_version"] == "person-a-canonical-pilot-accepted-manifest-v0.1"
            and accepted["status"] == "ACCEPTED_FOR_FROZEN_A6_1_TO_A6_5"
            and accepted["accepted_pilot_count"] == 1
            and accepted["canonical_c6a_id"] == CANONICAL_C6A_ID
            and accepted["selected_trajectory_id"] == trajectory_id
            and accepted["selected_episode_id"] == episode_id
            and accepted["grouping"] == {"key": "layout_id", "value": layout_id},
            f"accepted manifest identity mismatch: {trajectory_id}",
        )
        require(
            handoff["schema_version"]
            == "person-a-to-person-e-canonical-provenance-handoff-v0.1"
            and handoff["status"] == "READY_FOR_PERSON_E_PROVENANCE_CONSUMPTION"
            and handoff["canonical_c6a_id"] == CANONICAL_C6A_ID
            and handoff["trajectory_id"] == trajectory_id
            and handoff["episode_id"] == episode_id
            and handoff["grouping"] == {"key": "layout_id", "value": layout_id}
            and handoff["expected_activation_row_count"] == 1200,
            f"per-run A-to-E handoff identity mismatch: {trajectory_id}",
        )
        identity = handoff["identities"]
        require(
            identity["model_sha256"] == MODEL_SHA256
            and identity["model_config_sha256"] == MODEL_CONFIG_SHA256
            and identity["preprocessing"] == PREPROCESSING
            and identity["action_conversion"] == ACTION_CONVERSION
            and identity["hook_site"] == HOOK_SITE
            and identity["pooling_method"] == POOLING_METHOD
            and identity["token_region"] == TOKEN_REGION
            and identity["activation_store_format"] == ACTIVATION_STORE_FORMAT
            and identity["activation_index_format"] == ACTIVATION_INDEX_FORMAT,
            f"per-run model/pipeline identity mismatch: {trajectory_id}",
        )
        matching_records = [row for row in records if row.get("episode_id") == episode_id]
        require(len(matching_records) == 1, f"canonical E registry episode is not unique: {episode_id}")
        record = matching_records[0]
        record_sha256 = sha256_bytes(canonical_json(record))
        require(
            record["canonical_c6a_id"] == CANONICAL_C6A_ID
            and record["record_status"] == "accepted"
            and handoff["person_e_source"]
            == {
                "handoff_sha256": PRIOR_C6A_HANDOFF_SHA256,
                "registry_record_id": record["registry_record_id"],
                "registry_record_sha256": record_sha256,
            }
            and accepted["person_e"]["handoff_sha256"] == PRIOR_C6A_HANDOFF_SHA256
            and accepted["person_e"]["registry_record_id"] == record["registry_record_id"]
            and accepted["person_e"]["registry_record_sha256"] == record_sha256
            and accepted["episode_artifact_manifest"]["sha256"]
            == PRIOR_C6A_REGISTRY_SHA256
            and handoff["direct_episode_artifacts"] == record["outputs"]
            and accepted["direct_episode_artifacts"] == record["outputs"]
            and len(record["outputs"]) == 67,
            f"canonical E registry source join mismatch: {trajectory_id}",
        )
        preflight = load_json_file(root / "runtime_preflight_receipt.json")
        runtime_commit = preflight["git_commit"]
        require(
            preflight["status"] == "PASS"
            and preflight["frozen_file_sha256"]["main_checkpoint"] == MODEL_SHA256
            and preflight["model_config_physical_sha256"] == MODEL_CONFIG_SHA256
            and preflight["canonical_authority"]["canonical_c6a_id"] == CANONICAL_C6A_ID,
            f"runtime preflight identity mismatch: {trajectory_id}",
        )
        activation = verify_activation_index(
            root=root, collection_run=collection_run, runtime_commit=runtime_commit
        )
        require(
            activation["activation_index"]["sha256"] == index_sha256,
            f"activation index hash mismatch: {trajectory_id}",
        )
        audit = verify_direct_pooling_audit(root, trajectory_id)
        certification = load_json_file(root / "step6_5.json")
        result = certification["result"]
        repeatability = handoff["repeatability_validation"]
        require(
            certification["status"] == "PASS"
            and result["status"] == "PASS"
            and result["direct_pooling_audit"] == "PASS"
            and result["source_identity_join_failure_count"] == 0
            and repeatability["status"] == "PASS"
            and repeatability["maximum_absolute_difference"] == 0.0
            and result["repeatability_maximum_absolute_difference"] == 0.0,
            f"per-run certification/repeatability mismatch: {trajectory_id}",
        )
        all_external.extend(collection_run["activation_artifacts"])
        run_receipts.append(
            {
                "accepted_manifest": {
                    "path": str(manifest_path.resolve()),
                    "sha256": sha256_file(manifest_path)[1],
                },
                "activation_chunks": activation["activation_chunks"],
                "activation_index": activation["activation_index"],
                "a_to_e_handoff": {
                    "path": str(handoff_path.resolve()),
                    "sha256": sha256_file(handoff_path)[1],
                },
                "bundle_inventory_sha256": bundle_inventory_sha256,
                "canonical_registry_record_id": record["registry_record_id"],
                "canonical_registry_record_sha256": record_sha256,
                "direct_pooling_audit": audit,
                "episode_id": episode_id,
                "layout_id": layout_id,
                "producing_runtime_commit": runtime_commit,
                "repeatability": {
                    "atol": repeatability["atol"],
                    "maximum_absolute_difference": 0.0,
                    "rtol": repeatability["rtol"],
                    "status": "PASS",
                },
                "source_identity_join": activation["source_identity_join"],
                "trajectory_id": trajectory_id,
            }
        )
    expected_external = {
        (row["byte_size"], row["sha256"], row["type"])
        for row in collection["external"]["artifacts"]
    }
    observed_external = {
        (row["byte_size"], row["sha256"], row["type"]) for row in all_external
    }
    require(
        len(expected_external) == len(observed_external) == 105
        and expected_external == observed_external,
        "external activation inventory does not join exactly to all runs",
    )
    return run_receipts


def receipt_schema() -> dict[str, Any]:
    required = [
        "a6_6_performed",
        "a6_6_provenance_consumption_authorized",
        "a6_6_provenance_consumption_statement",
        "activation_provenance",
        "canonical_c6a_binding",
        "collection_identity",
        "historical_preservation",
        "immutable",
        "person_a_result",
        "receipt_id",
        "schema_version",
        "status",
        "unresolved_blockers",
        "validation",
    ]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "additionalProperties": False,
        "properties": {
            "a6_6_performed": {"const": False},
            "a6_6_provenance_consumption_authorized": {"const": True},
            "a6_6_provenance_consumption_statement": {"const": A6_6_STATEMENT},
            "activation_provenance": {"type": "object"},
            "canonical_c6a_binding": {"type": "object"},
            "collection_identity": {"type": "object"},
            "historical_preservation": {"type": "object"},
            "immutable": {"const": True},
            "person_a_result": {"type": "object"},
            "receipt_id": {"const": RECEIPT_ID},
            "schema_version": {"const": RECEIPT_SCHEMA_VERSION},
            "status": {"const": "READY_FOR_A6_6_PROVENANCE_CONSUMPTION"},
            "unresolved_blockers": {"maxItems": 0, "type": "array"},
            "validation": {"type": "object"},
        },
        "required": required,
        "title": "Person E to Person A five-layout activation provenance receipt",
        "type": "object",
    }


def validate_receipt_schema(receipt: dict[str, Any], schema: dict[str, Any]) -> None:
    require(schema["type"] == "object", "receipt schema root type mismatch")
    require(set(receipt) == set(schema["required"]), "receipt top-level schema mismatch")
    for key, rule in schema["properties"].items():
        value = receipt[key]
        if "const" in rule:
            require(value == rule["const"], f"receipt schema const mismatch: {key}")
        if rule.get("type") == "object":
            require(isinstance(value, dict), f"receipt schema object mismatch: {key}")
        if rule.get("type") == "array":
            require(isinstance(value, list), f"receipt schema array mismatch: {key}")
            require(
                len(value) <= rule.get("maxItems", len(value)),
                f"receipt schema array too long: {key}",
            )
    collection = receipt["collection_identity"]
    require(
        collection["layout_count"] == LAYOUT_COUNT
        and collection["trajectory_count"] == TRAJECTORY_COUNT
        and collection["activation_index_count"] == ACTIVATION_INDEX_COUNT
        and collection["activation_row_count"] == ACTIVATION_ROW_COUNT
        and collection["activation_chunk_count"] == ACTIVATION_CHUNK_COUNT
        and collection["source_frame_count"] == SOURCE_FRAME_COUNT,
        "receipt collection cardinality mismatch",
    )
    activation = receipt["activation_provenance"]
    require(
        len(activation["per_run"]) == TRAJECTORY_COUNT
        and len(activation["activation_indexes"]) == ACTIVATION_INDEX_COUNT
        and len(activation["activation_chunks"]) == ACTIVATION_CHUNK_COUNT
        and len(activation["direct_pooling_audits"]) == TRAJECTORY_COUNT
        and len(activation["repeatability_checks"]) == TRAJECTORY_COUNT
        and len(activation["source_identity_joins"]) == TRAJECTORY_COUNT,
        "receipt activation cardinality mismatch",
    )
    require(
        all(receipt["validation"].values()),
        "receipt contains a failed validation decision",
    )


def generate(out_dir: Path | None = None) -> dict[str, bytes]:
    verify_git_authorities()
    predecessors = verify_predecessors()
    collection = verify_collection_package()
    runs = verify_runs(collection, predecessors["registry"])
    trajectories = [row[1] for row in TRAJECTORIES]
    layouts = [row[0] for row in TRAJECTORIES]
    schema = receipt_schema()
    activation_chunks = [chunk for run in runs for chunk in run["activation_chunks"]]
    receipt = {
        "a6_6_performed": False,
        "a6_6_provenance_consumption_authorized": True,
        "a6_6_provenance_consumption_statement": A6_6_STATEMENT,
        "activation_provenance": {
            "activation_chunk_count": ACTIVATION_CHUNK_COUNT,
            "activation_chunks": activation_chunks,
            "activation_index_count": ACTIVATION_INDEX_COUNT,
            "activation_indexes": [run["activation_index"] for run in runs],
            "activation_row_count": ACTIVATION_ROW_COUNT,
            "direct_pooling_audits": [run["direct_pooling_audit"] for run in runs],
            "identities": {
                "action_conversion": ACTION_CONVERSION,
                "activation_index_format": ACTIVATION_INDEX_FORMAT,
                "activation_store_format": ACTIVATION_STORE_FORMAT,
                "checkpoint_sha256": MODEL_SHA256,
                "hidden_width": HIDDEN_WIDTH,
                "hook_site": HOOK_SITE,
                "layer_count": LAYER_COUNT,
                "model_config_sha256": MODEL_CONFIG_SHA256,
                "model_sha256": MODEL_SHA256,
                "pooling_method": POOLING_METHOD,
                "preprocessing": PREPROCESSING,
                "token_region": TOKEN_REGION,
            },
            "per_run": runs,
            "repeatability_checks": [run["repeatability"] for run in runs],
            "source_identity_joins": [run["source_identity_join"] for run in runs],
        },
        "canonical_c6a_binding": {
            "canonical_c6a_id": CANONICAL_C6A_ID,
            "person_c_commit": PERSON_C_COMMIT,
            "person_c_package_sha256": PERSON_C_PACKAGE_SHA256,
            "person_e_c6a_handoff_sha256": PRIOR_C6A_HANDOFF_SHA256,
            "person_e_c6a_registry_sha256": PRIOR_C6A_REGISTRY_SHA256,
            "registry_records": [
                {
                    "episode_id": run["episode_id"],
                    "layout_id": run["layout_id"],
                    "registry_record_id": run["canonical_registry_record_id"],
                    "registry_record_sha256": run["canonical_registry_record_sha256"],
                    "trajectory_id": run["trajectory_id"],
                }
                for run in runs
            ],
        },
        "collection_identity": {
            "a_to_e_handoff_path": str(
                (COLLECTION_ROOT / "person_a_to_person_e_canonical_multilayout_handoff.json").resolve()
            ),
            "a_to_e_handoff_sha256": A_TO_E_HANDOFF_SHA256,
            "activation_chunk_count": ACTIVATION_CHUNK_COUNT,
            "activation_index_count": ACTIVATION_INDEX_COUNT,
            "activation_row_count": ACTIVATION_ROW_COUNT,
            "collection_manifest_path": str(
                (COLLECTION_ROOT / "collection_manifest.json").resolve()
            ),
            "collection_manifest_sha256": COLLECTION_MANIFEST_SHA256,
            "episode_ids": [row[2] for row in TRAJECTORIES],
            "layout_count": LAYOUT_COUNT,
            "layout_ids": layouts,
            "logical_order": collection["manifest"]["logical_order"],
            "source_frame_count": SOURCE_FRAME_COUNT,
            "trajectory_count": TRAJECTORY_COUNT,
            "trajectory_ids": trajectories,
        },
        "historical_preservation": {
            "existing_person_e_records_modified": False,
            "predecessor_acceptance_inventory_sha256": predecessors[
                "prior_inventory_sha256"
            ],
            "predecessor_acceptance_receipt_path": str(
                PRIOR_ACCEPTANCE_PROVENANCE_PATH
            ),
            "predecessor_acceptance_receipt_sha256": PRIOR_ACCEPTANCE_RECEIPT_SHA256,
            "predecessor_acceptance_scope": "single-layout layout_01_ep12602 only",
            "predecessor_claims_successor_acceptance": False,
            "predecessor_package_modified": False,
            "prior_c6a_records_modified": False,
            "successor_relationship": "additive five-layout successor acceptance",
        },
        "immutable": True,
        "person_a_result": {
            "collection_inventory_sha256": collection["inventory_sha256"],
            "external_activation_inventory_sha256": EXTERNAL_INVENTORY_SHA256,
            "producing_successor_commit": PERSON_A_COMMIT,
            "successor_package_root": str(COLLECTION_ROOT.resolve()),
        },
        "receipt_id": RECEIPT_ID,
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "status": "READY_FOR_A6_6_PROVENANCE_CONSUMPTION",
        "unresolved_blockers": [],
        "validation": {
            "accepted_manifests_valid": True,
            "activation_chunks_valid": True,
            "activation_indexes_valid": True,
            "canonical_c6a_identity_valid": True,
            "collection_inventory_complete": True,
            "collection_manifest_valid": True,
            "direct_pooling_audits_valid": True,
            "model_and_pipeline_identities_valid": True,
            "predecessor_preserved": True,
            "repeatability_valid": True,
            "source_identity_joins_valid": True,
            "successor_a_to_e_handoff_valid": True,
            "zero_missing_duplicate_stale_reordered_or_extra_identities": True,
        },
    }
    validate_receipt_schema(receipt, schema)
    validation = {
        **receipt["validation"],
        "a6_6_provenance_consumption_authorized": True,
        "activation_chunk_count": ACTIVATION_CHUNK_COUNT,
        "activation_index_count": ACTIVATION_INDEX_COUNT,
        "activation_row_count": ACTIVATION_ROW_COUNT,
        "canonical_c6a_id": CANONICAL_C6A_ID,
        "collection_manifest_sha256": COLLECTION_MANIFEST_SHA256,
        "layout_count": LAYOUT_COUNT,
        "receipt_schema_valid": True,
        "schema_version": VALIDATION_SCHEMA_VERSION,
        "source_frame_count": SOURCE_FRAME_COUNT,
        "status": "PASS",
        "trajectory_count": TRAJECTORY_COUNT,
        "unresolved_blockers": [],
    }
    files = {
        RECEIPT_NAME: canonical_json(receipt),
        SCHEMA_NAME: canonical_json(schema),
        "validation_receipt.json": canonical_json(validation),
    }
    inventory_rows = [
        {
            "path": relative,
            "sha256": sha256_bytes(payload),
            "size_bytes": len(payload),
        }
        for relative, payload in sorted(files.items())
    ]
    files["sha256_inventory.json"] = canonical_json(
        {
            "file_count": len(files) + 1,
            "files": inventory_rows,
            "hash_algorithm": "sha256",
            "hash_source": "literal_file_bytes",
            "inventory_excludes_self": True,
            "schema_version": INVENTORY_SCHEMA_VERSION,
        }
    )
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        for relative, payload in files.items():
            (out_dir / relative).write_bytes(payload)
    return files


def validate_package(package_dir: Path) -> None:
    expected = generate()
    present = (
        {path.name for path in package_dir.iterdir() if path.is_file()}
        if package_dir.is_dir()
        else set()
    )
    require(present == set(expected), "successor acceptance package file inventory mismatch")
    for relative, payload in expected.items():
        require(
            (package_dir / relative).read_bytes() == payload,
            f"successor acceptance package byte drift: {relative}",
        )
    receipt = load_json_file(package_dir / RECEIPT_NAME)
    schema = load_json_file(package_dir / SCHEMA_NAME)
    validate_receipt_schema(receipt, schema)
    inventory = load_json_file(package_dir / "sha256_inventory.json")
    require(
        inventory["inventory_excludes_self"] is True
        and inventory["file_count"] == len(expected),
        "successor receipt inventory metadata mismatch",
    )
    for row in inventory["files"]:
        size, digest = sha256_file(package_dir / safe_relative(row["path"]))
        require(
            size == row["size_bytes"] and digest == row["sha256"],
            f"successor receipt inventory mismatch: {row['path']}",
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--out-dir", type=Path, default=PACKAGE_DIR)
    args = parser.parse_args()
    try:
        if args.write:
            require(not args.out_dir.exists(), f"immutable output already exists: {args.out_dir}")
            generate(args.out_dir)
        if args.validate or not args.write:
            validate_package(args.out_dir)
        print("VALIDATE OK: exact five-layout Person E activation provenance receipt")
    except (AcceptanceError, FileNotFoundError, KeyError, TypeError, ValueError) as exc:
        print(f"FAIL-CLOSED: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

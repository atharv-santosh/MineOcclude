"""Verify Person A's 66-cell preprocessed-frame handoff (v0.3, additive).

Additive successor to :mod:`mineocclude.baselines.frame_handoff_v0_2`.
That module stays exactly as it is: it is the frozen, reproducible
authority for the historical ten-pilot / 1,695-record production run and
for the tests that reproduce it. Nothing here rewrites it, and nothing
here reuses its ``FROZEN_PILOT_IDS`` pinning -- the ten-pilot identity
set is historical/test authority only and has no place in the 66-cell
production execution path.

What changed, and why a successor rather than an edit:

* Scope: 10 pilots / 1,695 frames -> **66 trajectories / 2,468 frames**.
* Manifest: Person A commit ``380b9a3`` -> ``3384cbf``, a different
  file at a different path with a different schema id
  (``person-a-preprocessed-frame-manifest-v0.2``).
* Record shape: ``output_relative_path`` -> ``output_path``; the 66-cell
  record additionally carries the full Person C canonical-source hash
  chain (``source_canonical_png_sha256``,
  ``source_canonical_pixel_sha256``, ``source_raw_sha256``) that the
  ten-pilot record never had.
* Admission: the ten-pilot manifest declared its own
  ``fold_manifest_sha256``/``target_manifest_sha256`` summary fields.
  The 66-cell manifest does not, and its per-record ``fold_binding``
  carries Person A's *copy* of an admission status that has since been
  superseded by Person B. This module therefore verifies media identity
  only and deliberately does **not** read admission from Person A --
  see :mod:`mineocclude.baselines.production_universe_66_cell_v0_1`,
  where admission comes from Person B's row universe alone.

Pixel-input contract resolved from Person D's own frozen algorithm
(``baselines/raw_pixel.py``: "Exact current preprocessed occluded
frame", and ``REQUIRED_PAYLOAD_SHAPE`` in v0.2), not from what happens
to be available: ``raw_pixel`` consumes Person **A's** model-facing
384x224 CHW float32 payloads. Person C's canonical 640x360 RGB PNG set
is the *source* of those payloads and is bound here as the head of the
hash chain, but it is not itself the raw-pixel feature representation.
No new image transform is introduced anywhere in this module; it never
decodes, resizes, or renormalizes a frame.

This module never writes to Person A's output root and never touches a
U4 path.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------
# Person A 66-cell authority (commit-pinned, independently hash-verified)
# --------------------------------------------------------------------------

PERSON_A_66_CELL_COMMIT = "3384cbfed92f069236d68746f2308ec76f1a4124"

PERSON_A_FRAME_MANIFEST_PATH = (
    "docs/status/person_a_66_cell_preprocessed_media_v0_2/"
    "preprocessed_frame_manifest.json"
)
PERSON_A_FRAME_MANIFEST_SHA256 = (
    "dda2220d1e388253c671f7a7d879987e53d4c0a1a1e815fbc8da6a19356de5a1"
)
PERSON_A_FRAME_MANIFEST_SCHEMA_ID = "person-a-preprocessed-frame-manifest-v0.2"

PERSON_A_TO_D_HANDOFF_PATH = (
    "docs/status/person_a_66_cell_preprocessed_media_v0_2/a_to_d_frame_handoff.json"
)
PERSON_A_TO_D_HANDOFF_SHA256 = (
    "a0575a63755b865ae6e59ce0de2385bd4f8a37558eafd0dfff3c2a1504a07868"
)

#: Person A's declared external payload root. Payload bytes are not
#: committed to Git (2.5 GB); Person A publishes the manifest plus the
#: per-payload SHA-256 and Person D verifies the bytes against them.
PERSON_A_EXTERNAL_FRAME_ROOT = (
    r"C:\Users\lollo\MineOcclude-Person-A-Outputs"
    r"\person-a-66-cell-preprocessed-frames-v0-2"
)
PERSON_A_FILENAME_RULE = "frames/{trajectory_id}/{model_frame_idx:06d}.f32le"

REQUIRED_FRAME_ARTIFACT_COUNT = 2468
REQUIRED_TRAJECTORY_COUNT = 66
REQUIRED_PAYLOAD_BYTE_TOTAL = 2547449856

#: Person A's frozen preprocessing authority. Person D records these and
#: verifies every record declares them; it never reimplements any step.
PERSON_A_PREPROCESS_HASH = (
    "8b585e1ffe7d9b7c7bf549f8b5695825bbd2a5b2579e4adf607ca5fa5786635c"
)
PERSON_A_PREPROCESSING_IDENTITY = "person-a-bgr2rgb-inter-linear-224x384-v1.0"
PERSON_A_PREPROCESSING_IMPLEMENTATION_PATH = (
    "src/mineocclude/models/_mineworld_adapter_wave2.py"
)
PERSON_A_PREPROCESSING_IMPLEMENTATION_SHA256 = (
    "02fd79fe5cd8463dc0117c3207f8d37c6c4f69b9f7017a9aaa4e8ef5e77609f8"
)
PERSON_A_COLOUR_CONVERSION = "cv2.COLOR_BGR2RGB"
PERSON_A_INTERPOLATION = "cv2.INTER_LINEAR"
PERSON_A_NORMALIZATION = "(x - 0.5) / 0.5 per channel"
PERSON_A_SCALING = "uint8 / float32(255.0)"

#: Model-facing payload contract. Identical in shape/dtype/layout to the
#: ten-pilot v0.2 contract -- restated here so the successor is
#: self-contained and does not import a ten-pilot-scoped constant.
REQUIRED_PAYLOAD_DTYPE = "float32"
REQUIRED_PAYLOAD_LAYOUT = "CHW"
REQUIRED_PAYLOAD_COLOR_ORDER = "RGB"
REQUIRED_PAYLOAD_FORMAT = "raw-little-endian-float32-c-order"
REQUIRED_PAYLOAD_SHAPE = (3, 224, 384)
REQUIRED_PAYLOAD_BYTE_SIZE = 1032192
REQUIRED_PAYLOAD_VALUE_RANGE = (-1.0, 1.0)

# --------------------------------------------------------------------------
# Person C 66-cell canonical-media authority (head of the hash chain)
# --------------------------------------------------------------------------

PERSON_C_66_CELL_COMMIT = "3846230a4f141a8a55084eeaaa040f9a10cfc408"
PERSON_C_CANONICAL_MEDIA_MANIFEST_PATH = (
    "docs/status/person_c_66_cell_canonical_media_v0_1/canonical_media_manifest.json"
)
PERSON_C_CANONICAL_MEDIA_MANIFEST_SHA256 = (
    "a11762bd9292404b58ddccc062ebcf5115d935d61426fff4cd4474c8def257c9"
)
PERSON_C_TO_D_MEDIA_HANDOFF_PATH = (
    "docs/status/person_c_66_cell_canonical_media_v0_1/c_to_d_media_handoff.json"
)
PERSON_C_TO_D_MEDIA_HANDOFF_SHA256 = (
    "84b5b927ab41d34d51ebf30f1af9d48cf1b5af9d057518a6ca6338cef7f38a56"
)
PERSON_C_CANONICALIZER_PATH = "src/mineocclude/data/preprocess.py"
PERSON_C_CANONICALIZER_SHA256 = (
    "cc80f6eb889ee7794786b26a81dea3647439a2cbc3e7f85235e0215bbd2c319a"
)
PERSON_C_CANONICAL_WIDTH = 640
PERSON_C_CANONICAL_HEIGHT = 360
PERSON_C_CANONICAL_CHANNEL_ORDER = "RGB"

#: Person C ships both a lossless canonical PNG set and an H.264
#: convenience MP4. Only the PNG set is a pixel-identical scientific
#: source; the MP4 is lossy and must never be used as one.
PERSON_C_SCIENTIFIC_PIXEL_SOURCE = "lossless_canonical_png_640x360_rgb"
MP4_PERMITTED_AS_PIXEL_SOURCE = False


class FrameHandoffV03Error(ValueError):
    """Raised when the 66-cell frame handoff cannot be honestly verified."""


def _valid_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def sha256_of_file(path: Path) -> str:
    """SHA-256 of a file's exact bytes."""

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_artifact_raw_bytes(path: Path, expected_sha256: str) -> tuple[str, ...]:
    """Verify a foreign artifact's raw bytes before its parsed content is trusted.

    Byte identity is the only basis for claiming a file is genuinely the
    committed upstream artifact, independent of what its parsed JSON
    says about itself.
    """

    file_path = Path(path)
    if not file_path.exists():
        return ("artifact_file_not_found",)
    actual = sha256_of_file(file_path)
    if actual != expected_sha256:
        return (f"raw_sha256_mismatch:expected={expected_sha256}:actual={actual}",)
    return ()


def verify_frame_manifest_summary_counts(
    manifest: Mapping[str, Any],
) -> tuple[str, ...]:
    """Check the 66-cell manifest's declared summary fields.

    Every value required here is one Person A's own manifest and
    ``a_to_d_frame_handoff.json`` both declare; none is a threshold
    Person D invented.
    """

    if not isinstance(manifest, Mapping):
        return ("manifest_not_mapping",)

    errors: list[str] = []
    if manifest.get("schema_id") != PERSON_A_FRAME_MANIFEST_SCHEMA_ID:
        errors.append("schema_id_mismatch")
    if manifest.get("artifact_count") != REQUIRED_FRAME_ARTIFACT_COUNT:
        errors.append("artifact_count_mismatch")
    if manifest.get("unique_frame_count") != REQUIRED_FRAME_ARTIFACT_COUNT:
        errors.append("unique_frame_count_mismatch")
    if manifest.get("trajectory_count") != REQUIRED_TRAJECTORY_COUNT:
        errors.append("trajectory_count_mismatch")
    if manifest.get("duplicate_frame_count") != 0:
        errors.append("duplicate_frame_count_nonzero")
    if manifest.get("missing_frame_count") != 0:
        errors.append("missing_frame_count_nonzero")
    if manifest.get("failure_count") != 0:
        errors.append("failure_count_nonzero")
    if manifest.get("payload_byte_total") != REQUIRED_PAYLOAD_BYTE_TOTAL:
        errors.append("payload_byte_total_mismatch")
    if manifest.get("mp4_used_as_pixel_source") is not False:
        errors.append("mp4_used_as_pixel_source")
    if list(manifest.get("join_key") or ()) != ["trajectory_id", "model_frame_idx"]:
        errors.append("join_key_mismatch")

    contract = manifest.get("output_contract")
    if not isinstance(contract, Mapping):
        errors.append("output_contract_missing")
    else:
        if contract.get("dtype") != REQUIRED_PAYLOAD_DTYPE:
            errors.append("output_contract_dtype_mismatch")
        if contract.get("layout") != REQUIRED_PAYLOAD_LAYOUT:
            errors.append("output_contract_layout_mismatch")
        if contract.get("color_order") != REQUIRED_PAYLOAD_COLOR_ORDER:
            errors.append("output_contract_color_order_mismatch")
        if contract.get("payload_format") != REQUIRED_PAYLOAD_FORMAT:
            errors.append("output_contract_payload_format_mismatch")
        if tuple(contract.get("shape") or ()) != REQUIRED_PAYLOAD_SHAPE:
            errors.append("output_contract_shape_mismatch")
        if contract.get("payload_byte_size") != REQUIRED_PAYLOAD_BYTE_SIZE:
            errors.append("output_contract_payload_byte_size_mismatch")
        if tuple(contract.get("value_range_inclusive") or ()) != REQUIRED_PAYLOAD_VALUE_RANGE:
            errors.append("output_contract_value_range_mismatch")

    preprocessing = manifest.get("person_a_preprocessing")
    if not isinstance(preprocessing, Mapping):
        errors.append("person_a_preprocessing_missing")
    else:
        if preprocessing.get("preprocess_hash") != PERSON_A_PREPROCESS_HASH:
            errors.append("preprocess_hash_mismatch")
        if (
            preprocessing.get("implementation_sha256")
            != PERSON_A_PREPROCESSING_IMPLEMENTATION_SHA256
        ):
            errors.append("preprocessing_implementation_sha256_mismatch")
        if preprocessing.get("interpolation") != PERSON_A_INTERPOLATION:
            errors.append("interpolation_mismatch")
        if preprocessing.get("normalization") != PERSON_A_NORMALIZATION:
            errors.append("normalization_mismatch")
        if preprocessing.get("colour_conversion") != PERSON_A_COLOUR_CONVERSION:
            errors.append("colour_conversion_mismatch")
        if preprocessing.get("scaling") != PERSON_A_SCALING:
            errors.append("scaling_mismatch")

    canonical = manifest.get("person_c_canonical_media")
    if not isinstance(canonical, Mapping):
        errors.append("person_c_canonical_media_missing")
    else:
        if canonical.get("commit") != PERSON_C_66_CELL_COMMIT:
            errors.append("person_c_commit_mismatch")
        if canonical.get("canonicalizer_sha256") != PERSON_C_CANONICALIZER_SHA256:
            errors.append("person_c_canonicalizer_sha256_mismatch")
        if canonical.get("canonical_dimensions") != (
            f"{PERSON_C_CANONICAL_WIDTH}x{PERSON_C_CANONICAL_HEIGHT}"
        ):
            errors.append("person_c_canonical_dimensions_mismatch")

    records = manifest.get("records")
    if not isinstance(records, list) or len(records) != REQUIRED_FRAME_ARTIFACT_COUNT:
        errors.append("records_count_mismatch")
    return tuple(errors)


def verify_frame_manifest_records(
    manifest: Mapping[str, Any],
    *,
    expected_frame_keys: Sequence[tuple[str, int]] | None = None,
) -> tuple[str, ...]:
    """Check every 66-cell frame record's identity and preprocessing declaration.

    Unlike the ten-pilot verifier this does **not** consult a frozen
    pilot-id allowlist. The 66-cell trajectory set is not a Person D
    constant: it is whatever Person B's row universe admits, so callers
    pass ``expected_frame_keys`` (Person B's authoritative
    ``(trajectory_id, model_frame_idx)`` set) and this function requires
    exact agreement in both directions.
    """

    records = manifest.get("records") if isinstance(manifest, Mapping) else None
    if not isinstance(records, list):
        return ("records_not_a_list",)

    errors: list[str] = []
    seen_artifact_ids: set[str] = set()
    seen_frame_keys: set[tuple[str, int]] = set()

    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            errors.append(f"record[{index}]:not_a_mapping")
            continue

        artifact_id = record.get("artifact_id")
        if not isinstance(artifact_id, str) or not artifact_id:
            errors.append(f"record[{index}]:invalid_artifact_id")
        elif artifact_id in seen_artifact_ids:
            errors.append(f"record[{index}]:duplicate_artifact_id")
        else:
            seen_artifact_ids.add(artifact_id)

        if not _valid_sha256(record.get("payload_sha256")):
            errors.append(f"record[{index}]:invalid_payload_sha256")
        if record.get("payload_byte_size") != REQUIRED_PAYLOAD_BYTE_SIZE:
            errors.append(f"record[{index}]:invalid_payload_byte_size")

        trajectory_id = record.get("trajectory_id")
        model_frame_idx = record.get("model_frame_idx")
        if not isinstance(trajectory_id, str) or not trajectory_id:
            errors.append(f"record[{index}]:invalid_trajectory_id")
        if not isinstance(model_frame_idx, int) or isinstance(model_frame_idx, bool):
            errors.append(f"record[{index}]:invalid_model_frame_idx")
        else:
            key = (trajectory_id, model_frame_idx)
            if key in seen_frame_keys:
                errors.append(f"record[{index}]:duplicate_frame_identity")
            seen_frame_keys.add(key)

        expected_global_identity = f"{trajectory_id}:{model_frame_idx}"
        if record.get("global_frame_identity") != expected_global_identity:
            errors.append(f"record[{index}]:global_frame_identity_mismatch")

        if record.get("dtype") != REQUIRED_PAYLOAD_DTYPE:
            errors.append(f"record[{index}]:dtype_mismatch")
        if record.get("payload_format") != REQUIRED_PAYLOAD_FORMAT:
            errors.append(f"record[{index}]:payload_format_mismatch")
        shape = record.get("shape")
        if not isinstance(shape, list) or tuple(shape) != REQUIRED_PAYLOAD_SHAPE:
            errors.append(f"record[{index}]:shape_mismatch")
        if record.get("preprocess_hash") != PERSON_A_PREPROCESS_HASH:
            errors.append(f"record[{index}]:preprocess_hash_mismatch")
        if record.get("preprocessing_identity") != PERSON_A_PREPROCESSING_IDENTITY:
            errors.append(f"record[{index}]:preprocessing_identity_mismatch")
        if (
            record.get("canonicalization_implementation_sha256")
            != PERSON_C_CANONICALIZER_SHA256
        ):
            errors.append(f"record[{index}]:canonicalizer_sha256_mismatch")
        if record.get("source_canonical_width") != PERSON_C_CANONICAL_WIDTH:
            errors.append(f"record[{index}]:source_canonical_width_mismatch")
        if record.get("source_canonical_height") != PERSON_C_CANONICAL_HEIGHT:
            errors.append(f"record[{index}]:source_canonical_height_mismatch")
        if record.get("source_channel_order") != PERSON_C_CANONICAL_CHANNEL_ORDER:
            errors.append(f"record[{index}]:source_channel_order_mismatch")
        for chain_field in (
            "source_canonical_png_sha256",
            "source_canonical_pixel_sha256",
            "source_raw_sha256",
        ):
            if not _valid_sha256(record.get(chain_field)):
                errors.append(f"record[{index}]:invalid_{chain_field}")

        output_path = record.get("output_path")
        if not isinstance(output_path, str) or not output_path:
            errors.append(f"record[{index}]:invalid_output_path")
        elif isinstance(model_frame_idx, int) and not isinstance(model_frame_idx, bool):
            expected_path = PERSON_A_FILENAME_RULE.format(
                trajectory_id=trajectory_id, model_frame_idx=model_frame_idx
            )
            if output_path != expected_path:
                errors.append(f"record[{index}]:output_path_rule_mismatch")

    if expected_frame_keys is not None:
        expected = set(expected_frame_keys)
        missing = sorted(expected - seen_frame_keys)
        extra = sorted(seen_frame_keys - expected)
        if missing:
            errors.append(f"frame_keys_missing_from_manifest:{len(missing)}:{missing[:3]}")
        if extra:
            errors.append(f"frame_keys_not_in_row_universe:{len(extra)}:{extra[:3]}")

    return tuple(errors)


@dataclass(frozen=True)
class FramePayloadVerificationResult:
    expected_frame_count: int
    actual_frame_count: int
    verified_frame_count: int
    missing_frame_count: int
    duplicate_frame_count: int
    size_mismatch_count: int
    hash_mismatch_count: int
    errors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def all_clear(self) -> bool:
        return (
            self.actual_frame_count == self.expected_frame_count
            and self.missing_frame_count == 0
            and self.duplicate_frame_count == 0
            and self.size_mismatch_count == 0
            and self.hash_mismatch_count == 0
        )


def verify_frame_payloads_on_disk(
    manifest: Mapping[str, Any],
    *,
    frame_root: Path,
    only_frame_keys: Sequence[tuple[str, int]] | None = None,
) -> FramePayloadVerificationResult:
    """Verify external payload bytes against the manifest's declared hashes.

    Never trusts the manifest's own claim about a file this function can
    read directly. ``only_frame_keys`` restricts hashing to a subset --
    the production run needs pixel bytes only for the rows Person B
    admits, and rehashing all 2.5 GB to score 662 rows would be pure
    cost. The count fields always report against the full manifest so a
    restricted verification can never masquerade as a complete one.
    """

    records = manifest.get("records") if isinstance(manifest, Mapping) else None
    if not isinstance(records, list):
        return FramePayloadVerificationResult(
            expected_frame_count=REQUIRED_FRAME_ARTIFACT_COUNT,
            actual_frame_count=0,
            verified_frame_count=0,
            missing_frame_count=REQUIRED_FRAME_ARTIFACT_COUNT,
            duplicate_frame_count=0,
            size_mismatch_count=0,
            hash_mismatch_count=0,
            errors=("records_not_a_list",),
        )

    wanted = set(only_frame_keys) if only_frame_keys is not None else None
    root = Path(frame_root)
    errors: list[str] = []
    seen_keys: set[tuple[str, int]] = set()
    verified = missing = duplicate = size_mismatch = hash_mismatch = 0

    for record in records:
        if not isinstance(record, Mapping):
            errors.append("record_not_a_mapping")
            continue
        key = (record.get("trajectory_id"), record.get("model_frame_idx"))
        if key in seen_keys:
            duplicate += 1
            errors.append(f"{key}:duplicate_payload_identity")
            continue
        seen_keys.add(key)
        if wanted is not None and key not in wanted:
            continue

        relative_path = record.get("output_path")
        if not isinstance(relative_path, str) or not relative_path:
            missing += 1
            errors.append(f"{key}:missing_output_path")
            continue
        full_path = root / relative_path
        if not full_path.exists():
            missing += 1
            errors.append(f"{key}:file_missing:{full_path}")
            continue

        payload = full_path.read_bytes()
        if len(payload) != record.get("payload_byte_size"):
            size_mismatch += 1
            errors.append(
                f"{key}:size_mismatch:expected={record.get('payload_byte_size')}:"
                f"actual={len(payload)}"
            )
        if hashlib.sha256(payload).hexdigest() != record.get("payload_sha256"):
            hash_mismatch += 1
            errors.append(f"{key}:hash_mismatch")
        verified += 1

    return FramePayloadVerificationResult(
        expected_frame_count=REQUIRED_FRAME_ARTIFACT_COUNT,
        actual_frame_count=len(seen_keys),
        verified_frame_count=verified,
        missing_frame_count=missing,
        duplicate_frame_count=duplicate,
        size_mismatch_count=size_mismatch,
        hash_mismatch_count=hash_mismatch,
        errors=tuple(errors),
    )


def build_pixel_input_contract() -> dict[str, Any]:
    """The exact, explicit pixel-input binding for every Person D family.

    Seven of the eight frozen families read no pixels at all -- they
    consume only the legally observable scalars on
    :class:`~mineocclude.baselines.interface.TrajectoryContext`. Only
    ``raw_pixel`` consumes an image, and its frozen contract names the
    *preprocessed* frame, which is Person A's model-facing payload.
    """

    return {
        "schema_id": "person-d-66-cell-pixel-input-contract-v0-1",
        "schema_version": "1.0",
        "resolution_basis": (
            "Person D's own frozen implementations, read directly: "
            "baselines/raw_pixel.py binds 'exact current preprocessed "
            "frame'; the other seven families take no pixel argument at all."
        ),
        "families_consuming_no_pixels": [
            "last_seen",
            "constant_velocity",
            "grouped_shuffled",
            "time_only",
            "explicit_feature",
            "visible_history_q",
            "known_q_analytic",
        ],
        "families_consuming_pixels": ["raw_pixel"],
        "raw_pixel_input_authority": {
            "producer_role": "person_a",
            "artifact": "person_a_66_cell_preprocessed_frame_payload",
            "commit": PERSON_A_66_CELL_COMMIT,
            "manifest_path": PERSON_A_FRAME_MANIFEST_PATH,
            "manifest_sha256": PERSON_A_FRAME_MANIFEST_SHA256,
            "external_payload_root": PERSON_A_EXTERNAL_FRAME_ROOT,
            "filename_rule": PERSON_A_FILENAME_RULE,
            "shape_chw": list(REQUIRED_PAYLOAD_SHAPE),
            "width": REQUIRED_PAYLOAD_SHAPE[2],
            "height": REQUIRED_PAYLOAD_SHAPE[1],
            "dtype": REQUIRED_PAYLOAD_DTYPE,
            "layout": REQUIRED_PAYLOAD_LAYOUT,
            "channel_order": REQUIRED_PAYLOAD_COLOR_ORDER,
            "byte_order": "little",
            "payload_format": REQUIRED_PAYLOAD_FORMAT,
            "payload_byte_size": REQUIRED_PAYLOAD_BYTE_SIZE,
            "value_range_inclusive": list(REQUIRED_PAYLOAD_VALUE_RANGE),
            "normalization": PERSON_A_NORMALIZATION,
            "scaling": PERSON_A_SCALING,
            "interpolation": PERSON_A_INTERPOLATION,
            "colour_conversion": PERSON_A_COLOUR_CONVERSION,
            "preprocess_hash": PERSON_A_PREPROCESS_HASH,
            "preprocessing_identity": PERSON_A_PREPROCESSING_IDENTITY,
            "preprocessing_implementation_path": (
                PERSON_A_PREPROCESSING_IMPLEMENTATION_PATH
            ),
            "preprocessing_implementation_sha256": (
                PERSON_A_PREPROCESSING_IMPLEMENTATION_SHA256
            ),
            "person_d_introduces_no_further_transform": True,
        },
        "source_hash_chain": [
            {
                "stage": "person_c_raw_capture",
                "per_record_field": "source_raw_sha256",
                "owner": "person_c",
            },
            {
                "stage": "person_c_canonical_png_640x360_rgb",
                "per_record_field": "source_canonical_png_sha256",
                "pixel_digest_field": "source_canonical_pixel_sha256",
                "owner": "person_c",
                "commit": PERSON_C_66_CELL_COMMIT,
                "canonicalizer_path": PERSON_C_CANONICALIZER_PATH,
                "canonicalizer_sha256": PERSON_C_CANONICALIZER_SHA256,
                "manifest_sha256": PERSON_C_CANONICAL_MEDIA_MANIFEST_SHA256,
                "handoff_sha256": PERSON_C_TO_D_MEDIA_HANDOFF_SHA256,
                "is_scientific_pixel_authority": True,
                "mp4_permitted_as_pixel_source": MP4_PERMITTED_AS_PIXEL_SOURCE,
            },
            {
                "stage": "person_a_model_facing_384x224_chw_float32",
                "per_record_field": "payload_sha256",
                "owner": "person_a",
                "commit": PERSON_A_66_CELL_COMMIT,
                "is_raw_pixel_feature_representation": True,
            },
        ],
        "not_used_as_raw_pixel_features": {
            "person_c_canonical_png_640x360": (
                "Head of the hash chain and the scientific pixel authority, "
                "but Person D's frozen raw_pixel contract names the "
                "preprocessed frame, so the canonical PNG is bound for "
                "provenance, not consumed as the feature vector."
            ),
            "person_a_hidden_activations": (
                "Person B's b_to_d_successor_handoff declares "
                "person_d_baselines_consume_activations = false; no Person D "
                "family reads an activation."
            ),
            "h264_convenience_mp4": "Lossy; never a pixel-identical source.",
        },
    }


__all__ = [
    "MP4_PERMITTED_AS_PIXEL_SOURCE",
    "PERSON_A_66_CELL_COMMIT",
    "PERSON_A_COLOUR_CONVERSION",
    "PERSON_A_EXTERNAL_FRAME_ROOT",
    "PERSON_A_FILENAME_RULE",
    "PERSON_A_FRAME_MANIFEST_PATH",
    "PERSON_A_FRAME_MANIFEST_SCHEMA_ID",
    "PERSON_A_FRAME_MANIFEST_SHA256",
    "PERSON_A_INTERPOLATION",
    "PERSON_A_NORMALIZATION",
    "PERSON_A_PREPROCESSING_IDENTITY",
    "PERSON_A_PREPROCESSING_IMPLEMENTATION_PATH",
    "PERSON_A_PREPROCESSING_IMPLEMENTATION_SHA256",
    "PERSON_A_PREPROCESS_HASH",
    "PERSON_A_SCALING",
    "PERSON_A_TO_D_HANDOFF_PATH",
    "PERSON_A_TO_D_HANDOFF_SHA256",
    "PERSON_C_66_CELL_COMMIT",
    "PERSON_C_CANONICALIZER_PATH",
    "PERSON_C_CANONICALIZER_SHA256",
    "PERSON_C_CANONICAL_MEDIA_MANIFEST_PATH",
    "PERSON_C_CANONICAL_MEDIA_MANIFEST_SHA256",
    "PERSON_C_SCIENTIFIC_PIXEL_SOURCE",
    "PERSON_C_TO_D_MEDIA_HANDOFF_PATH",
    "PERSON_C_TO_D_MEDIA_HANDOFF_SHA256",
    "REQUIRED_FRAME_ARTIFACT_COUNT",
    "REQUIRED_PAYLOAD_BYTE_SIZE",
    "REQUIRED_PAYLOAD_BYTE_TOTAL",
    "REQUIRED_PAYLOAD_COLOR_ORDER",
    "REQUIRED_PAYLOAD_DTYPE",
    "REQUIRED_PAYLOAD_FORMAT",
    "REQUIRED_PAYLOAD_LAYOUT",
    "REQUIRED_PAYLOAD_SHAPE",
    "REQUIRED_TRAJECTORY_COUNT",
    "FrameHandoffV03Error",
    "FramePayloadVerificationResult",
    "build_pixel_input_contract",
    "sha256_of_file",
    "verify_artifact_raw_bytes",
    "verify_frame_manifest_records",
    "verify_frame_manifest_summary_counts",
    "verify_frame_payloads_on_disk",
]

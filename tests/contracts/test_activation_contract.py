"""Tests for the MineOcclude A→B activation contract."""

from __future__ import annotations

import hashlib
import json
import unittest
from collections import Counter
from copy import deepcopy
from pathlib import Path

from mineocclude.contracts.activation import (
    ActivationRejectionCode,
    validate_activation_handoff,
)


FIXTURE_DIR = (
    Path(__file__).parent.parent
    / "fixtures"
    / "activation"
)

OLD_HANDOFF_ID = "synthetic_activation_handoff_001"
OLD_RUN_ID = "synthetic_activation_run_001"
OLD_MANIFEST_HASH = "5" * 64

CORRECTED_HANDOFF_ID = "synthetic_activation_handoff_002"
CORRECTED_RUN_ID = "synthetic_activation_run_002"
CORRECTED_MANIFEST_HASH = "6" * 64


def load_fixture(filename: str):
    """Load one Step 1.4 JSON fixture."""

    path = (
        FIXTURE_DIR
        / filename
    )

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def rejection_codes(
    result,
) -> set[ActivationRejectionCode]:
    """Return all rejection codes from one validation result."""

    return {
        rejection.code
        for rejection in result.rejections
    }


class TestActivationContract(
    unittest.TestCase
):
    """Verify the Step 1.4 A→B activation contract."""

    def test_accepted_activation_handoff_passes(
        self,
    ):
        package = load_fixture(
            "accepted_activation_handoff.json"
        )

        result = (
            validate_activation_handoff(
                package
            )
        )

        self.assertTrue(
            result.accepted
        )

        self.assertEqual(
            result.rejections,
            (),
        )

    def test_accepted_fixture_has_coherent_20hz_timebase(
        self,
    ):
        package = load_fixture(
            "accepted_activation_handoff.json"
        )

        rows_by_frame = {}

        for row in package["index_rows"]:
            key = row["model_frame_idx"]
            identity = (
                row["server_tick"],
                row["tau"],
            )

            if key in rows_by_frame:
                self.assertEqual(
                    rows_by_frame[key],
                    identity,
                )
            else:
                rows_by_frame[key] = identity

        first_frame = min(rows_by_frame)
        first_tick, first_tau = rows_by_frame[first_frame]

        for model_frame_idx, (server_tick, tau) in rows_by_frame.items():
            frame_delta = model_frame_idx - first_frame

            self.assertEqual(
                server_tick - first_tick,
                frame_delta,
            )
            self.assertAlmostEqual(
                tau - first_tau,
                frame_delta * 0.05,
            )

    def test_timebase_correction_has_new_identity_and_lineage(
        self,
    ):
        package = load_fixture(
            "accepted_activation_handoff.json"
        )
        lineage = load_fixture(
            "timebase_correction_lineage.json"
        )

        self.assertEqual(package["schema_version"], "1.0")
        self.assertEqual(package["handoff_id"], CORRECTED_HANDOFF_ID)
        self.assertEqual(package["run_id"], CORRECTED_RUN_ID)
        self.assertEqual(
            package["accepted_manifest_hash"],
            CORRECTED_MANIFEST_HASH,
        )

        self.assertEqual(
            lineage["superseded_evidence"],
            {
                "handoff_id": OLD_HANDOFF_ID,
                "run_id": OLD_RUN_ID,
                "accepted_manifest_hash": OLD_MANIFEST_HASH,
                "tau_seconds_by_model_frame_idx": {
                    "0": 0.0,
                    "1": 1.0,
                    "2": 2.0,
                },
            },
        )
        self.assertEqual(
            lineage["replacement_evidence"]["handoff_id"],
            CORRECTED_HANDOFF_ID,
        )
        self.assertEqual(
            lineage["replacement_evidence"]["run_id"],
            CORRECTED_RUN_ID,
        )
        self.assertEqual(
            lineage["replacement_evidence"]["accepted_manifest_hash"],
            CORRECTED_MANIFEST_HASH,
        )
        self.assertFalse(lineage["schema_migration"])
        self.assertEqual(lineage["schema_version"], "1.0")

        serialized_package = json.dumps(package, sort_keys=True)
        self.assertNotIn(OLD_HANDOFF_ID, serialized_package)
        self.assertNotIn(OLD_RUN_ID, serialized_package)
        self.assertNotIn(OLD_MANIFEST_HASH, serialized_package)

        for row in package["index_rows"]:
            self.assertEqual(row["schema_version"], "1.0")
            self.assertEqual(row["run_id"], CORRECTED_RUN_ID)
            self.assertEqual(
                row["accepted_manifest_hash"],
                CORRECTED_MANIFEST_HASH,
            )

    def test_stale_manifest_identity_is_rejected_not_repaired(
        self,
    ):
        package = load_fixture(
            "accepted_activation_handoff.json"
        )
        package["accepted_manifest_hash"] = OLD_MANIFEST_HASH
        original = deepcopy(package)

        result = validate_activation_handoff(package)

        self.assertFalse(result.accepted)
        self.assertIn(
            ActivationRejectionCode.METADATA_MISMATCH,
            rejection_codes(result),
        )
        self.assertEqual(package, original)

    def test_corrected_handoff_validation_is_row_order_independent(
        self,
    ):
        package = load_fixture(
            "accepted_activation_handoff.json"
        )
        package["index_rows"] = list(reversed(package["index_rows"]))
        original = deepcopy(package)

        result = validate_activation_handoff(package)

        self.assertTrue(result.accepted)
        self.assertEqual(result.rejections, ())
        self.assertEqual(package, original)

    def test_target_label_selection_is_forbidden(
        self,
    ):
        package = load_fixture(
            "rejected_label_leakage.json"
        )

        result = (
            validate_activation_handoff(
                package
            )
        )

        self.assertFalse(
            result.accepted
        )

        self.assertIn(
            ActivationRejectionCode.LEAKAGE_SELECTION_FORBIDDEN,
            rejection_codes(
                result
            ),
        )

    def test_cardinality_mismatch_is_rejected(
        self,
    ):
        package = load_fixture(
            "rejected_cardinality.json"
        )

        result = (
            validate_activation_handoff(
                package
            )
        )

        self.assertFalse(
            result.accepted
        )

        self.assertIn(
            ActivationRejectionCode.CARDINALITY_MISMATCH,
            rejection_codes(
                result
            ),
        )

    def test_invalid_token_positions_are_rejected(
        self,
    ):
        package = load_fixture(
            "rejected_token_positions.json"
        )

        result = (
            validate_activation_handoff(
                package
            )
        )

        self.assertFalse(
            result.accepted
        )

        self.assertIn(
            ActivationRejectionCode.INVALID_TOKEN_POSITIONS,
            rejection_codes(
                result
            ),
        )

    def test_duplicate_activation_identity_is_rejected(
        self,
    ):
        package = load_fixture(
            "rejected_duplicate_activation_identity.json"
        )

        result = (
            validate_activation_handoff(
                package
            )
        )

        self.assertFalse(
            result.accepted
        )

        self.assertIn(
            ActivationRejectionCode.DUPLICATE_ACTIVATION_IDENTITY,
            rejection_codes(
                result
            ),
        )

    def test_metadata_mismatch_is_rejected(
        self,
    ):
        package = load_fixture(
            "rejected_metadata_mismatch.json"
        )

        result = (
            validate_activation_handoff(
                package
            )
        )

        self.assertFalse(
            result.accepted
        )

        self.assertIn(
            ActivationRejectionCode.METADATA_MISMATCH,
            rejection_codes(
                result
            ),
        )

    def test_locked_vector_shape_is_enforced(
        self,
    ):
        package = load_fixture(
            "accepted_activation_handoff.json"
        )

        package[
            "chunks"
        ][0][
            "vector_shape"
        ] = [1]

        for row in package[
            "index_rows"
        ]:
            row[
                "vector_shape"
            ] = [1]

        result = validate_activation_handoff(
            package
        )

        self.assertFalse(
            result.accepted
        )

        self.assertIn(
            ActivationRejectionCode.INVALID_CHUNK_DESCRIPTOR,
            rejection_codes(
                result
            ),
        )

    def test_malformed_status_and_dtypes_return_rejections(
        self,
    ):
        accepted = load_fixture(
            "accepted_activation_handoff.json"
        )

        cases = (
            (
                "run_status",
                lambda package: package.__setitem__(
                    "run_status",
                    [],
                ),
                ActivationRejectionCode.INVALID_RUN_STATUS,
            ),
            (
                "chunk_dtype",
                lambda package: package[
                    "chunks"
                ][0].__setitem__(
                    "dtype",
                    [],
                ),
                ActivationRejectionCode.INVALID_CHUNK_DESCRIPTOR,
            ),
            (
                "row_dtype",
                lambda package: package[
                    "index_rows"
                ][0].__setitem__(
                    "dtype",
                    [],
                ),
                ActivationRejectionCode.INVALID_INDEX_ROW,
            ),
        )

        for (
            name,
            mutate,
            expected_code,
        ) in cases:
            with self.subTest(
                name=name
            ):
                package = deepcopy(
                    accepted
                )

                mutate(
                    package
                )

                result = validate_activation_handoff(
                    package
                )

                self.assertFalse(
                    result.accepted
                )

                self.assertIn(
                    expected_code,
                    rejection_codes(
                        result
                    ),
                )

    def test_accepted_manifest_row_count_is_reproducible(
        self,
    ):
        package = load_fixture(
            "accepted_activation_handoff.json"
        )

        package[
            "cardinality_report"
        ][
            "accepted_manifest_rows"
        ] = 4

        result = validate_activation_handoff(
            package
        )

        self.assertFalse(
            result.accepted
        )

        self.assertIn(
            ActivationRejectionCode.CARDINALITY_MISMATCH,
            rejection_codes(
                result
            ),
        )

    def test_validator_does_not_mutate_handoff(
        self,
    ):
        package = load_fixture(
            "rejected_cardinality.json"
        )

        original = deepcopy(
            package
        )

        validate_activation_handoff(
            package
        )

        self.assertEqual(
            package,
            original,
        )

    def test_activation_chunk_has_expected_vectors(
        self,
    ):
        chunk = load_fixture(
            "synthetic_activation_chunk.json"
        )

        rows = chunk[
            "rows"
        ]

        self.assertEqual(
            len(rows),
            6,
        )

        for expected_index, row in enumerate(
            rows
        ):
            self.assertEqual(
                row[
                    "chunk_row_idx"
                ],
                expected_index,
            )

            self.assertEqual(
                len(
                    row[
                        "vector"
                    ]
                ),
                2048,
            )

    def test_chunk_row_indices_match_activation_index(
        self,
    ):
        package = load_fixture(
            "accepted_activation_handoff.json"
        )

        chunk = load_fixture(
            "synthetic_activation_chunk.json"
        )

        index_rows = package[
            "index_rows"
        ]

        chunk_rows = chunk[
            "rows"
        ]

        indexed_chunk_rows = {
            row[
                "chunk_row_idx"
            ]
            for row in index_rows
        }

        stored_chunk_rows = {
            row[
                "chunk_row_idx"
            ]
            for row in chunk_rows
        }

        self.assertEqual(
            indexed_chunk_rows,
            stored_chunk_rows,
        )

    def test_chunk_descriptor_resolves_and_hashes_companion(
        self,
    ):
        package = load_fixture(
            "accepted_activation_handoff.json"
        )

        descriptor = package[
            "chunks"
        ][0]

        chunk_path = (
            FIXTURE_DIR
            / descriptor[
                "path"
            ]
        )

        self.assertTrue(
            chunk_path.is_file()
        )

        actual_hash = hashlib.sha256(
            chunk_path.read_bytes()
        ).hexdigest()

        self.assertEqual(
            actual_hash,
            descriptor[
                "sha256"
            ],
        )

    def test_person_b_can_join_targets_without_row_order(
        self,
    ):
        """Prove B can join targets using explicit identity keys."""

        package = load_fixture(
            "accepted_activation_handoff.json"
        )

        targets = load_fixture(
            "synthetic_targets.json"
        )

        index_rows = package[
            "index_rows"
        ]

        # Person B builds this lookup only from documented identity fields.
        target_by_key = {
            (
                target[
                    "trajectory_id"
                ],
                target[
                    "model_frame_idx"
                ],
            ): target
            for target in targets
        }

        self.assertEqual(
            len(target_by_key),
            len(targets),
            msg="Synthetic target identities must be unique.",
        )

        activation_frame_keys = {
            (
                row[
                    "trajectory_id"
                ],
                row[
                    "model_frame_idx"
                ],
            )
            for row in index_rows
        }

        self.assertEqual(
            activation_frame_keys,
            set(
                target_by_key
            ),
        )

        activation_sites = {
            (
                row[
                    "layer_idx"
                ],
                row[
                    "hook_site"
                ],
            )
            for row in index_rows
        }

        joined_rows = []

        for activation_row in index_rows:
            key = (
                activation_row[
                    "trajectory_id"
                ],
                activation_row[
                    "model_frame_idx"
                ],
            )

            self.assertIn(
                key,
                target_by_key,
            )

            joined_rows.append(
                {
                    **activation_row,
                    **target_by_key[
                        key
                    ],
                }
            )

        # Three frames × two layers = six joined activation rows.
        self.assertEqual(
            len(joined_rows),
            6,
        )

        # Every activation row must join exactly one target row.
        self.assertEqual(
            len(joined_rows),
            len(index_rows),
        )

        self.assertEqual(
            len(index_rows),
            len(target_by_key)
            * len(activation_sites),
        )

        for frame_key in target_by_key:
            sites_for_frame = {
                (
                    row[
                        "layer_idx"
                    ],
                    row[
                        "hook_site"
                    ],
                )
                for row in index_rows
                if (
                    row[
                        "trajectory_id"
                    ],
                    row[
                        "model_frame_idx"
                    ],
                ) == frame_key
            }

            self.assertEqual(
                sites_for_frame,
                activation_sites,
            )

    def test_person_b_can_reproduce_total_row_count(
        self,
    ):
        package = load_fixture(
            "accepted_activation_handoff.json"
        )

        report = package[
            "cardinality_report"
        ]

        actual_count = len(
            package[
                "index_rows"
            ]
        )

        self.assertEqual(
            actual_count,
            report[
                "actual_activation_rows"
            ],
        )

        self.assertEqual(
            actual_count,
            report[
                "expected_activation_rows"
            ],
        )

        self.assertEqual(
            actual_count,
            6,
        )

    def test_person_b_can_reproduce_per_layer_counts(
        self,
    ):
        package = load_fixture(
            "accepted_activation_handoff.json"
        )

        index_rows = package[
            "index_rows"
        ]

        report = package[
            "cardinality_report"
        ]

        computed_counts = Counter(
            row[
                "layer_idx"
            ]
            for row in index_rows
        )

        computed_counts = {
            str(layer): count
            for (
                layer,
                count,
            ) in computed_counts.items()
        }

        self.assertEqual(
            computed_counts,
            report[
                "actual_rows_by_layer"
            ],
        )

        self.assertEqual(
            computed_counts,
            report[
                "expected_rows_by_layer"
            ],
        )

        self.assertEqual(
            computed_counts,
            {
                "5": 3,
                "12": 3,
            },
        )

    def test_accepted_manifest_hash_is_present_on_every_row(
        self,
    ):
        package = load_fixture(
            "accepted_activation_handoff.json"
        )

        manifest_hash = package[
            "accepted_manifest_hash"
        ]

        for row in package[
            "index_rows"
        ]:
            self.assertEqual(
                row[
                    "accepted_manifest_hash"
                ],
                manifest_hash,
            )

    def test_checkpoint_and_preprocess_hashes_match_every_row(
        self,
    ):
        package = load_fixture(
            "accepted_activation_handoff.json"
        )

        checkpoint_hash = package[
            "checkpoint_hash"
        ]

        preprocess_hash = package[
            "preprocess_hash"
        ]

        for row in package[
            "index_rows"
        ]:
            self.assertEqual(
                row[
                    "checkpoint_hash"
                ],
                checkpoint_hash,
            )

            self.assertEqual(
                row[
                    "model_hash"
                ],
                checkpoint_hash,
            )

            self.assertEqual(
                row[
                    "preprocess_hash"
                ],
                preprocess_hash,
            )


if __name__ == "__main__":
    unittest.main()

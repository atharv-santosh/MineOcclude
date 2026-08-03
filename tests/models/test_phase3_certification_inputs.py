"""CPU-only tests for bounded Phase 3 certification-input preparation."""

from __future__ import annotations

import copy
import hashlib
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mineocclude.contracts.trajectory import ROW_STREAMS, validate_trajectory_package
from mineocclude.models import phase3_certification_inputs as inputs
from mineocclude.models.phase2_evidence import canonical_json_bytes, sha256_file


REPO_ROOT = Path(__file__).resolve().parents[2]
TRAJECTORY_FIXTURE = (
    REPO_ROOT / "tests" / "fixtures" / "trajectory" / "accepted_package.json"
)
MINEWORLD_SOURCE = Path(r"C:\Users\lollo\MineWorld-Upstream")


def _temporary_directory():
    return tempfile.TemporaryDirectory(ignore_cleanup_errors=True)


def _expanded_package(count: int = 10) -> dict:
    package = json.loads(TRAJECTORY_FIXTURE.read_text(encoding="utf-8"))
    for stream_name in ROW_STREAMS:
        template = copy.deepcopy(package["streams"][stream_name][0])
        rows = []
        for index in range(count):
            row = copy.deepcopy(template)
            row.update(
                {
                    "server_tick": 100 + index,
                    "render_frame_idx": index,
                    "action_idx": 200 + index,
                    "model_frame_idx": 300 + index,
                }
            )
            if stream_name == "client_tick_log":
                row["client_tick"] = 400 + index
            if stream_name == "seed_noise":
                row["noise_draw"] = index / 10
            if stream_name == "raw_actions":
                row["raw_action"] = {
                    "keyboard": {"keys": []},
                    "mouse": {"buttons": [], "dx": 0.0, "dy": 0.0},
                }
            rows.append(row)
        package["streams"][stream_name] = rows
    package["media"]["frame_count"] = count
    package["exclusion_ledger"] = []
    package["scientific_use"] = "pending_cross_role_signoff"
    return package


class _FakeConverter:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def convert(self, raw_action):
        self.calls += 1
        if self.fail:
            raise ValueError("controlled converter mismatch")
        normalized = {
            "camera": [0.0, 0.0],
            "attack": 0,
        }
        return normalized, tuple(range(8192, 8203)), True


def _frame_files(root: Path, count: int = 10):
    paths = {}
    hashes = {}
    for index in range(count):
        path = root / f"{index:06d}.png"
        path.write_bytes(f"controlled-frame-{index}".encode("ascii"))
        paths[path.name] = path
        hashes[path.name] = sha256_file(path)
    return paths, hashes


def _write_frame_inventory(path: Path, frames: dict[str, bytes]) -> None:
    lines = [
        f"{hashlib.sha256(payload).hexdigest()}  {name}"
        for name, payload in sorted(frames.items())
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_tar(
    path: Path,
    frames: dict[str, bytes],
    *,
    extras: tuple[tuple[str, bytes, bytes], ...] = (),
) -> None:
    with tarfile.open(path, "w:gz") as archive:
        directory = tarfile.TarInfo("frames_640x360")
        directory.type = tarfile.DIRTYPE
        archive.addfile(directory)
        for name, payload in sorted(frames.items()):
            member = tarfile.TarInfo(f"frames_640x360/{name}")
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))
        for name, member_type, payload in extras:
            member = tarfile.TarInfo(name)
            member.type = member_type
            member.size = len(payload) if member_type == tarfile.REGTYPE else 0
            archive.addfile(
                member,
                io.BytesIO(payload) if member_type == tarfile.REGTYPE else None,
            )


class ChecksumAndArchiveTests(unittest.TestCase):
    def test_malformed_and_duplicate_checksum_inventory_reject(self):
        with _temporary_directory() as root:
            root_path = Path(root)
            malformed = root_path / "malformed.txt"
            malformed.write_text("not a checksum\n", encoding="utf-8")
            with self.assertRaises(inputs.PreparationError) as caught:
                inputs.parse_checksum_inventory(malformed)
            self.assertEqual(caught.exception.code, "malformed_checksum_inventory")

            duplicate = root_path / "duplicate.txt"
            duplicate.write_text(
                f"{'a' * 64}  000000.png\n{'b' * 64}  000000.png\n",
                encoding="utf-8",
            )
            with self.assertRaises(inputs.PreparationError) as caught:
                inputs.parse_checksum_inventory(duplicate)
            self.assertEqual(caught.exception.code, "duplicate_checksum_filename")

    def test_valid_archive_allows_only_exact_appledouble_metadata(self):
        with _temporary_directory() as root:
            root_path = Path(root)
            frames = {"000000.png": b"zero", "000001.png": b"one"}
            inventory = root_path / "frames.sha256"
            archive = root_path / "frames.tar.gz"
            _write_frame_inventory(inventory, frames)
            _write_tar(
                archive,
                frames,
                extras=(
                    ("._frames_640x360", tarfile.REGTYPE, b"metadata"),
                    (
                        "frames_640x360/._000000.png",
                        tarfile.REGTYPE,
                        b"metadata",
                    ),
                ),
            )
            result = inputs.verify_and_extract_frame_archive(
                archive,
                inventory,
                root_path / "extracted",
                expected_archive_sha256=sha256_file(archive),
                expected_count=2,
            )
            self.assertEqual(set(result.frame_paths), set(frames))
            self.assertEqual(len(result.ignored_appledouble_members), 2)
            self.assertEqual(
                result.frame_hashes["000001.png"],
                hashlib.sha256(b"one").hexdigest(),
            )

    def test_archive_hash_and_altered_png_reject(self):
        with _temporary_directory() as root:
            root_path = Path(root)
            frames = {"000000.png": b"zero"}
            inventory = root_path / "frames.sha256"
            archive = root_path / "frames.tar.gz"
            _write_frame_inventory(inventory, {"000000.png": b"different"})
            _write_tar(archive, frames)
            with self.assertRaises(inputs.PreparationError) as caught:
                inputs.verify_and_extract_frame_archive(
                    archive,
                    inventory,
                    root_path / "hash-fail",
                    expected_archive_sha256="0" * 64,
                    expected_count=1,
                )
            self.assertEqual(caught.exception.code, "archive_hash_mismatch")
            with self.assertRaises(inputs.PreparationError) as caught:
                inputs.verify_and_extract_frame_archive(
                    archive,
                    inventory,
                    root_path / "frame-fail",
                    expected_archive_sha256=sha256_file(archive),
                    expected_count=1,
                )
            self.assertEqual(caught.exception.code, "extracted_frame_hash_mismatch")

    def test_archive_safety_matrix(self):
        cases = (
            ("traversal", "../000000.png", tarfile.REGTYPE, "unsafe_archive_path"),
            (
                "absolute",
                "/frames_640x360/000000.png",
                tarfile.REGTYPE,
                "unsafe_archive_path",
            ),
            (
                "unsupported",
                "frames_640x360/link",
                tarfile.SYMTYPE,
                "unsupported_archive_member",
            ),
            (
                "unexpected-frame",
                "frames_640x360/000001.png",
                tarfile.REGTYPE,
                "unexpected_frame",
            ),
        )
        for name, member, member_type, expected_code in cases:
            with self.subTest(name=name), _temporary_directory() as root:
                root_path = Path(root)
                frames = {"000000.png": b"zero"}
                inventory = root_path / "frames.sha256"
                archive = root_path / "frames.tar.gz"
                _write_frame_inventory(inventory, frames)
                _write_tar(
                    archive,
                    frames,
                    extras=((member, member_type, b"extra"),),
                )
                with self.assertRaises(inputs.PreparationError) as caught:
                    inputs.verify_and_extract_frame_archive(
                        archive,
                        inventory,
                        root_path / "extracted",
                        expected_archive_sha256=sha256_file(archive),
                        expected_count=1,
                    )
                self.assertEqual(caught.exception.code, expected_code)

    def test_duplicate_archive_member_rejects(self):
        with _temporary_directory() as root:
            root_path = Path(root)
            inventory = root_path / "frames.sha256"
            archive = root_path / "frames.tar.gz"
            _write_frame_inventory(inventory, {"000000.png": b"zero"})
            _write_tar(
                archive,
                {"000000.png": b"zero"},
                extras=(
                    ("frames_640x360/000000.png", tarfile.REGTYPE, b"zero"),
                ),
            )
            with self.assertRaises(inputs.PreparationError) as caught:
                inputs.verify_and_extract_frame_archive(
                    archive,
                    inventory,
                    root_path / "extracted",
                    expected_archive_sha256=sha256_file(archive),
                    expected_count=1,
                )
            self.assertEqual(caught.exception.code, "duplicate_archive_member")

    def test_missing_frame_rejects(self):
        with _temporary_directory() as root:
            root_path = Path(root)
            inventory = root_path / "frames.sha256"
            archive = root_path / "frames.tar.gz"
            expected = {"000000.png": b"zero", "000001.png": b"one"}
            _write_frame_inventory(inventory, expected)
            _write_tar(archive, {"000000.png": b"zero"})
            with self.assertRaises(inputs.PreparationError) as caught:
                inputs.verify_and_extract_frame_archive(
                    archive,
                    inventory,
                    root_path / "extracted",
                    expected_archive_sha256=sha256_file(archive),
                    expected_count=2,
                )
            self.assertEqual(caught.exception.code, "missing_frame")


class WindowAndDerivativeTests(unittest.TestCase):
    def test_earliest_window_is_deterministic_and_preserves_identities(self):
        with _temporary_directory() as root:
            paths, hashes = _frame_files(Path(root), 10)
            package = _expanded_package(10)
            converter = _FakeConverter()
            first = inputs.select_earliest_window(
                package,
                paths,
                hashes,
                pair_count=8,
                converter=converter,
            )
            second = inputs.select_earliest_window(
                package,
                paths,
                hashes,
                pair_count=8,
                converter=_FakeConverter(),
            )
            self.assertEqual(first.package_row_indices, tuple(range(8)))
            self.assertEqual(first.package_row_indices, second.package_row_indices)
            self.assertEqual(
                [row["model_frame_idx"] for row in first.frame_rows],
                list(range(300, 308)),
            )
            self.assertEqual(len(first.action_records), 8)

    def test_quarantined_earliest_window_is_recorded_and_skipped(self):
        with _temporary_directory() as root:
            paths, hashes = _frame_files(Path(root), 10)
            package = _expanded_package(10)
            package["exclusion_ledger"] = [
                copy.deepcopy(package["streams"]["frame_map"][0])
            ]
            selected = inputs.select_earliest_window(
                package,
                paths,
                hashes,
                pair_count=8,
                converter=_FakeConverter(),
            )
            self.assertEqual(selected.package_row_indices, tuple(range(1, 9)))
            self.assertEqual(
                selected.rejected_candidates[0]["package_row_indices"],
                [0, 7],
            )
            self.assertTrue(
                any(
                    reason.startswith("quarantined_identity")
                    for reason in selected.rejected_candidates[0]["reasons"]
                )
            )

    def test_missing_action_and_converter_mismatch_reject(self):
        for name, mutator, converter in (
            (
                "missing-final",
                lambda package: package["streams"]["raw_actions"].pop(),
                _FakeConverter(),
            ),
            ("converter", lambda package: None, _FakeConverter(fail=True)),
        ):
            with self.subTest(name=name), _temporary_directory() as root:
                paths, hashes = _frame_files(Path(root), 8)
                package = _expanded_package(8)
                mutator(package)
                with self.assertRaises(inputs.PreparationError) as caught:
                    inputs.select_earliest_window(
                        package,
                        paths,
                        hashes,
                        pair_count=8,
                        converter=converter,
                    )
                self.assertEqual(caught.exception.code, "no_valid_window")

    def test_context_limit_rejects(self):
        with _temporary_directory() as root:
            paths, hashes = _frame_files(Path(root), 16)
            with self.assertRaises(inputs.PreparationError) as caught:
                inputs.select_earliest_window(
                    _expanded_package(16),
                    paths,
                    hashes,
                    pair_count=16,
                    converter=_FakeConverter(),
                )
            self.assertEqual(caught.exception.code, "invalid_pair_count")

    def test_derivative_is_deterministic_and_contract_accepted(self):
        with _temporary_directory() as root:
            paths, hashes = _frame_files(Path(root), 8)
            source = _expanded_package(8)
            selected = inputs.select_earliest_window(
                source,
                paths,
                hashes,
                pair_count=8,
                converter=_FakeConverter(),
            )
            media = {"size_bytes": 10, "sha256": "a" * 64}
            impulse = {
                "trajectory_id": "layout_00_ep9440",
                "qa_report": {"sha256": "b" * 64},
                "evidence_file": {"sha256": "c" * 64},
                "causal_offset": 0,
                "causal_semantics": "action_i affects visual_i -> visual_(i+1)",
            }
            first = inputs._build_derivative_package(
                source,
                selected,
                media,
                impulse,
                person_a_revision="1" * 40,
                person_c_revision="2" * 40,
            )
            second = inputs._build_derivative_package(
                source,
                selected,
                media,
                impulse,
                person_a_revision="1" * 40,
                person_c_revision="2" * 40,
            )
            self.assertEqual(canonical_json_bytes(first), canonical_json_bytes(second))
            self.assertTrue(validate_trajectory_package(first).accepted)
            self.assertEqual(first["scientific_use"], "forbidden_engineering_certification_only")
            self.assertEqual(
                [row["model_frame_idx"] for row in first["streams"]["frame_map"]],
                list(range(300, 308)),
            )
            self.assertEqual(
                [row["render_frame_idx"] for row in first["streams"]["frame_map"]],
                list(range(8)),
            )
            self.assertEqual(len(first["streams"]["raw_actions"]), 8)

    def test_invalid_full_package_rejects_before_selection(self):
        package = _expanded_package(8)
        package["schema_version"] = "2.0"
        self.assertFalse(validate_trajectory_package(package).accepted)

    def test_action_provenance_detects_raw_mutation_without_torch(self):
        with _temporary_directory() as root:
            paths, hashes = _frame_files(Path(root), 8)
            source = _expanded_package(8)
            selected = inputs.select_earliest_window(
                source,
                paths,
                hashes,
                pair_count=8,
                converter=_FakeConverter(),
            )
            derivative = inputs._build_derivative_package(
                source,
                selected,
                {"size_bytes": 10, "sha256": "a" * 64},
                {
                    "trajectory_id": "layout_00_ep9440",
                    "qa_report": {"sha256": "b" * 64},
                    "evidence_file": {"sha256": "c" * 64},
                    "causal_offset": 0,
                    "causal_semantics": "action_i affects visual_i -> visual_(i+1)",
                },
                person_a_revision="1" * 40,
                person_c_revision="2" * 40,
            )
            derivative["streams"]["raw_actions"][0]["raw_action"]["mouse"]["dx"] = 1.0
            with self.assertRaises(inputs.PreparationError) as caught:
                inputs._validate_action_provenance(
                    derivative,
                    source_root=MINEWORLD_SOURCE,
                )
            self.assertEqual(caught.exception.code, "action_conversion_record_mismatch")

    def test_output_inside_either_git_repository_rejects(self):
        with self.assertRaises(inputs.PreparationError) as caught:
            inputs._assert_external_output(
                REPO_ROOT / "not-allowed",
                person_c_root=Path(r"C:\Users\lollo\MineOcclude-Person-C"),
            )
        self.assertEqual(caught.exception.code, "output_inside_git_repository")


class ImpulseAndCliTests(unittest.TestCase):
    def test_invalid_impulse_evidence_rejects(self):
        with _temporary_directory() as root:
            fixture = Path(root) / "impulse"
            fixture.mkdir()
            with self.assertRaises(inputs.PreparationError) as caught:
                inputs._validate_impulse_fixture(
                    fixture,
                    mock.Mock(),
                    ffprobe_executable="ffprobe",
                )
            self.assertEqual(caught.exception.code, "impulse_evidence_incomplete")

    def test_cli_exposes_prepare_and_validation_only_operations(self):
        parser = inputs.build_parser()
        help_text = parser.format_help()
        self.assertIn("prepare", help_text)
        self.assertIn("validate", help_text)
        self.assertNotIn("CUDA", help_text)

    def test_validator_module_does_not_import_torch(self):
        source = Path(inputs.__file__).read_text(encoding="utf-8")
        self.assertNotIn("import torch", source)
        self.assertNotIn("torch.cuda", source)

    def test_c6a_and_impulse_archive_hashes_are_separate_pins(self):
        self.assertEqual(
            inputs.EXPECTED_C6A_ARCHIVE_SHA256,
            "aaa38084e59cd20e70433c9ab169ecb140edde7a0f75e8bf86363bf95ebfbc2b",
        )
        self.assertEqual(
            inputs.EXPECTED_IMPULSE_ARCHIVE_SHA256,
            "823825b80d570d2f6df1bca40d765df62a2e3b47ffd82fda70d0bb18564c01d9",
        )
        self.assertNotEqual(
            inputs.EXPECTED_C6A_ARCHIVE_SHA256,
            inputs.EXPECTED_IMPULSE_ARCHIVE_SHA256,
        )

    def test_mp4_metadata_mismatch_fails_closed(self):
        valid = {
            "width": 640,
            "height": 360,
            "r_frame_rate": "20/1",
            "avg_frame_rate": "20/1",
            "declared_frames": 8,
            "decoded_frames": 8,
            "duration_seconds": 0.4,
        }
        inputs._require_exact_media_probe(
            valid,
            frame_count=8,
            role="controlled MP4",
            expected_duration=0.4,
        )
        for field, value in (
            ("width", 320),
            ("avg_frame_rate", "10/1"),
            ("decoded_frames", 7),
            ("duration_seconds", 0.35),
        ):
            with self.subTest(field=field):
                invalid = dict(valid)
                invalid[field] = value
                with self.assertRaises(inputs.PreparationError) as caught:
                    inputs._require_exact_media_probe(
                        invalid,
                        frame_count=8,
                        role="controlled MP4",
                        expected_duration=0.4,
                    )
                self.assertEqual(caught.exception.code, "mp4_metadata_mismatch")

    def test_derivative_media_hash_and_size_mismatch_fail(self):
        with _temporary_directory() as root:
            path = Path(root) / "bounded.mp4"
            path.write_bytes(b"bounded")
            identity = {
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            inputs._require_declared_media_identity(
                identity,
                path,
                role="controlled bounded MP4",
            )
            for field, value in (
                ("size_bytes", path.stat().st_size + 1),
                ("sha256", "f" * 64),
            ):
                with self.subTest(field=field):
                    invalid = dict(identity)
                    invalid[field] = value
                    with self.assertRaises(inputs.PreparationError) as caught:
                        inputs._require_declared_media_identity(
                            invalid,
                            path,
                            role="controlled bounded MP4",
                        )
                    self.assertEqual(
                        caught.exception.code,
                        "bounded_media_hash_mismatch",
                    )


if __name__ == "__main__":
    unittest.main()

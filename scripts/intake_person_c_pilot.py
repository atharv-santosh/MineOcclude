"""Validate and freeze Person C's real Week 1 capture handoff."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mineocclude.analysis.capture_intake import (  # noqa: E402
    CAPTURE_SOURCE_LIST_SCHEMA_VERSION,
    CaptureIntakeError,
    CaptureSource,
    build_capture_intake_bundle,
    derive_capture_intake_code_sha,
)
from mineocclude.experiments.registry import (  # noqa: E402
    load_json_with_sha256,
    write_json_exclusive,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Authenticate C capture bytes, co-sign verified coordinate frames, "
            "and freeze condition rows without inventing missing A provenance."
        )
    )
    parser.add_argument("source_manifest", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument(
        "--artifact-id",
        default="person_b_phase6_c_capture_intake_2026_07_24",
    )
    return parser.parse_args()


def _load_source_manifest(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CaptureIntakeError(
            f"Could not load capture source manifest {path}: {error}"
        ) from error
    if not isinstance(document, dict):
        raise CaptureIntakeError("Capture source manifest must be a mapping.")
    if (
        document.get("capture_source_list_schema_version")
        != CAPTURE_SOURCE_LIST_SCHEMA_VERSION
    ):
        raise CaptureIntakeError("Capture source-list schema version mismatch.")
    packages = document.get("capture_packages")
    if (
        not isinstance(packages, list)
        or not packages
        or any(not isinstance(item, dict) for item in packages)
    ):
        raise CaptureIntakeError(
            "capture_packages must be a non-empty list of mappings."
        )
    return document


def _run_git(*arguments: str) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["git", *arguments],
            cwd=ROOT,
            check=False,
            capture_output=True,
        )
    except OSError as error:
        raise CaptureIntakeError(f"Could not execute Git: {error}") from error


def _verify_source_revision(document: dict[str, Any]) -> str:
    source_branch = document.get("source_branch")
    source_commit = document.get("source_commit")
    if not isinstance(source_branch, str) or not source_branch.strip():
        raise CaptureIntakeError("source_branch must be a non-empty string.")
    if (
        not isinstance(source_commit, str)
        or len(source_commit) != 40
        or any(character not in "0123456789abcdefABCDEF" for character in source_commit)
    ):
        raise CaptureIntakeError("source_commit must be a 40-character Git SHA.")

    remote_ref = f"refs/remotes/origin/{source_branch}"
    resolved = _run_git("rev-parse", "--verify", f"{remote_ref}^{{commit}}")
    if resolved.returncode != 0:
        raise CaptureIntakeError(
            f"Could not resolve Person C source branch {remote_ref!r}."
        )
    remote_commit = resolved.stdout.decode("ascii").strip()
    ancestry = _run_git(
        "merge-base",
        "--is-ancestor",
        source_commit,
        remote_commit,
    )
    if ancestry.returncode != 0:
        raise CaptureIntakeError(
            f"Source commit {source_commit} is not reachable from {remote_ref}."
        )
    return source_commit.lower()


def _verify_git_blob(
    *,
    source_commit: str,
    relative_path: str,
    local_path: Path,
) -> None:
    result = _run_git("show", f"{source_commit}:{relative_path}")
    if result.returncode != 0:
        raise CaptureIntakeError(
            f"{relative_path}: file is absent from source commit {source_commit}."
        )
    try:
        local_bytes = local_path.read_bytes()
    except OSError as error:
        raise CaptureIntakeError(
            f"Could not read local source file {local_path}: {error}"
        ) from error
    if local_bytes != result.stdout:
        raise CaptureIntakeError(
            f"{relative_path}: local bytes differ from source commit "
            f"{source_commit}."
        )


def _load_sources(document: dict[str, Any]) -> list[CaptureSource]:
    source_commit = _verify_source_revision(document)
    sources: list[CaptureSource] = []
    for entry in document["capture_packages"]:
        relative = entry.get("path")
        if not isinstance(relative, str) or not relative:
            raise CaptureIntakeError("Every capture package requires a path.")
        capture_path = (ROOT / relative).resolve()
        if ROOT not in capture_path.parents:
            raise CaptureIntakeError(
                f"Capture path escapes the repository: {relative!r}."
            )
        normalized_relative = relative.replace("\\", "/")
        sidecar_path = Path(str(capture_path) + ".sha256")
        _verify_git_blob(
            source_commit=source_commit,
            relative_path=normalized_relative,
            local_path=capture_path,
        )
        _verify_git_blob(
            source_commit=source_commit,
            relative_path=f"{normalized_relative}.sha256",
            local_path=sidecar_path,
        )
        package, literal_sha256 = load_json_with_sha256(capture_path)
        try:
            sidecar_sha256 = sidecar_path.read_text(encoding="ascii").strip()
        except (OSError, UnicodeDecodeError) as error:
            raise CaptureIntakeError(
                f"Could not read checksum sidecar {sidecar_path}: {error}"
            ) from error
        sources.append(
            CaptureSource(
                path=normalized_relative,
                package=package,
                literal_sha256=literal_sha256,
                sidecar_sha256=sidecar_sha256,
            )
        )
    return sources


def _trajectory_id_from_frame(frame: dict[str, Any]) -> str:
    frame_id = frame.get("coordinate_frame_id")
    prefix = "person_b_c_live_"
    suffix = "_v1"
    if (
        not isinstance(frame_id, str)
        or not frame_id.startswith(prefix)
        or not frame_id.endswith(suffix)
    ):
        raise CaptureIntakeError(
            "Generated coordinate frame ID does not follow the frozen format."
        )
    trajectory_id = frame_id[len(prefix) : -len(suffix)]
    if not trajectory_id:
        raise CaptureIntakeError(
            "Generated coordinate frame ID is missing its trajectory."
        )
    return trajectory_id


def execute(args: argparse.Namespace) -> None:
    source_manifest = _load_source_manifest(args.source_manifest)
    bundle = build_capture_intake_bundle(
        _load_sources(source_manifest),
        source_branch=source_manifest["source_branch"],
        source_commit=source_manifest["source_commit"],
        artifact_id=args.artifact_id,
        code_sha=derive_capture_intake_code_sha(),
    )
    write_json_exclusive(
        args.output_directory / "capture_intake_report.json",
        bundle.report,
    )
    write_json_exclusive(
        args.output_directory / "condition_selection_source.json",
        bundle.condition_selection_source,
    )
    for frame in bundle.coordinate_frames:
        trajectory_id = _trajectory_id_from_frame(frame)
        write_json_exclusive(
            args.output_directory
            / "coordinate_frames"
            / f"{trajectory_id}.json",
            frame,
        )


def main() -> None:
    execute(parse_args())


if __name__ == "__main__":
    main()

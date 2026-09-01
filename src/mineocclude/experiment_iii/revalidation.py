"""Authority revalidation for evidence bound to a predecessor authority (A0).

A0's invalidation scope is exact, and it is deliberately not "regenerate":

    If the authority changes after A1 has begun, every downstream artifact bound
    to the old ``AUTHORITY_SHA256`` is invalidated and **must be revalidated**.

So an amendment does not retract a measurement. It makes every artifact bound to
the superseded hash *unusable until revalidated*, and revalidation is the
prescribed remedy. Without this module the only available remedies would be to
re-run P0 -- discarding a valid 252-unit campaign because a bootstrap seed was
named -- or to weaken the drift check, which would let genuinely stale evidence
through. Both are wrong.

**What revalidation proves.** Not "the operator says it is fine". For each
artifact:

1. its bytes are unchanged, and it is hashed as it lies on disk;
2. the authority it was produced under is a **recognised predecessor** in the
   frozen lineage, not an arbitrary foreign hash;
3. every machine-authority key path that changed between that predecessor and
   the current authority is **disjoint from the authority roots the artifact
   depends on**.

(3) is the load-bearing claim and it is computed, never asserted: the predecessor
machine authority is read back out of the git object database at its immutable
freeze commit and diffed against the live one. An artifact is revalidated only
if the amendment provably could not have changed it. An amendment that touched
``p0_rve`` could not revalidate a P0 ladder this way, and would have to say so.

Revalidation is recorded in one index receipt, and the loaders consult it. Drift
with no revalidation record still fails closed exactly as before.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Iterable, Mapping

from mineocclude.experiment_iii.authority import (
    AUTHORITY_FREEZE_COMMIT,
    AUTHORITY_VERSION,
    FROZEN_AUTHORITY_SHA256,
    AUTHORITY_JSON_PATH,
    PREDECESSOR_2_AUTHORITY_FREEZE_COMMIT,
    PREDECESSOR_2_AUTHORITY_SHA256,
    PREDECESSOR_AUTHORITY_FREEZE_COMMIT,
    PREDECESSOR_AUTHORITY_SHA256,
    REPOSITORY_ROOT,
    canonical_sha256,
    machine_authority,
    sha256_file,
    verify_authority_binding,
)
from mineocclude.experiment_iii.errors import ExperimentIIIError

__all__ = [
    "AUTHORITY_LINEAGE",
    "REVALIDATION_INDEX_PATH",
    "REVALIDATION_SCHEMA_VERSION",
    "authority_delta",
    "build_revalidation_receipt",
    "load_revalidation_index",
    "resolve_authority_binding",
]

REVALIDATION_SCHEMA_VERSION = "mineocclude-experiment-iii-authority-revalidation-v1"

#: The recognised predecessor lineage, newest first. A binding to anything
#: outside this tuple is foreign provenance and is never revalidatable.
AUTHORITY_LINEAGE: tuple[tuple[str, str], ...] = (
    (PREDECESSOR_AUTHORITY_SHA256, PREDECESSOR_AUTHORITY_FREEZE_COMMIT),
    (PREDECESSOR_2_AUTHORITY_SHA256, PREDECESSOR_2_AUTHORITY_FREEZE_COMMIT),
)

REVALIDATION_INDEX_PATH = (
    REPOSITORY_ROOT
    / "docs"
    / "experiment_iii"
    / "receipts"
    / "authority_revalidation_receipt.json"
)

#: Machine-authority roots that carry no scientific decision: an edit confined to
#: these is amendment bookkeeping. Everything else is scientific and blocks
#: revalidation of any artifact that depends on it.
_BOOKKEEPING_ROOTS = frozenset(
    {
        "amended_by",
        "authority_version",
        "authority_markdown_sha256",
        "authority_markdown_bytes",
        "authority_markdown_hash_recomputed_by",
        "authority_status",
        "authority_repair_date",
        "authority_repair_pass",
        "authority_repair_pass_2",
        "authority_closure_pass",
    }
)


def _is_bookkeeping(root: str) -> bool:
    return (
        root in _BOOKKEEPING_ROOTS
        or root.startswith("authority_amendment_")
        or root.startswith("authority_markdown_sha256_superseded_")
    )


def _flatten(node: Any, trail: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    if isinstance(node, Mapping):
        for key, value in node.items():
            flat.update(_flatten(value, f"{trail}.{key}" if trail else str(key)))
    elif isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            flat.update(_flatten(value, f"{trail}[{index}]"))
    else:
        flat[trail] = node
    return flat


def _machine_authority_at(commit: str) -> dict[str, Any]:
    """The machine authority as it was at ``commit``, from the object database.

    Read from git rather than from any working-tree copy: the whole point is to
    compare against bytes that cannot have been edited to make the comparison
    succeed.
    """
    relative = AUTHORITY_JSON_PATH.relative_to(REPOSITORY_ROOT).as_posix()
    result = subprocess.run(
        ["git", "show", f"{commit}:{relative}"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ExperimentIIIError(
            "PROVENANCE_BINDING_MISSING",
            f"the machine authority at {commit} is not reachable in this "
            f"repository: {result.stderr.strip()}",
        )
    return json.loads(result.stdout)


def authority_delta(predecessor_commit: str) -> dict[str, Any]:
    """Every machine-authority key path that moved since ``predecessor_commit``."""
    previous = _flatten(_machine_authority_at(predecessor_commit))
    current = _flatten(machine_authority())
    changed = sorted(
        key
        for key in set(previous) | set(current)
        if previous.get(key) != current.get(key)
    )
    roots = sorted({key.split(".")[0].split("[")[0] for key in changed})
    scientific = sorted(root for root in roots if not _is_bookkeeping(root))
    return {
        "predecessor_commit": predecessor_commit,
        "changed_key_paths": changed,
        "changed_key_path_count": len(changed),
        "changed_roots": roots,
        "changed_scientific_roots": scientific,
        "bookkeeping_only": not scientific,
    }


def build_revalidation_receipt(
    artifacts: Mapping[str, Iterable[str]],
    *,
    out: Path | None = None,
) -> dict[str, Any]:
    """Revalidate historical artifacts against the current authority.

    ``artifacts`` maps a repository-relative path to the machine-authority roots
    that artifact's content depends on. The dependency declaration is the honest
    part of the contract: naming too few roots would revalidate an artifact the
    amendment really did move, so it is recorded in the receipt and can be
    audited against the artifact.
    """
    binding = verify_authority_binding()
    deltas: dict[str, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []

    for relative, roots in artifacts.items():
        path = REPOSITORY_ROOT / relative
        if not path.is_file():
            raise ExperimentIIIError(
                "PROVENANCE_BINDING_MISSING",
                f"cannot revalidate {relative}: it does not exist",
            )
        body = json.loads(path.read_text(encoding="utf-8"))
        provenance = body.get("provenance") or {}
        observed = (
            (provenance.get("authority_binding") or {}).get("AUTHORITY_SHA256")
            or (body.get("authority_binding") or {}).get("AUTHORITY_SHA256")
            or body.get("authority_sha256")
        )
        if observed is None:
            raise ExperimentIIIError(
                "PROVENANCE_BINDING_MISSING",
                f"{relative} declares no authority binding to revalidate",
            )
        if observed == FROZEN_AUTHORITY_SHA256:
            raise ExperimentIIIError(
                "PROVENANCE_BINDING_MISSING",
                f"{relative} is already bound to the current authority; it needs "
                f"no revalidation and must not be given a record implying it did",
            )
        lineage = {sha: commit for sha, commit in AUTHORITY_LINEAGE}
        if observed not in lineage:
            raise ExperimentIIIError(
                "PROVENANCE_AUTHORITY_DRIFT",
                f"{relative} is bound to {observed}, which is not a recognised "
                f"predecessor of {FROZEN_AUTHORITY_SHA256}; foreign provenance "
                f"is never revalidatable",
            )
        commit = lineage[observed]
        if commit not in deltas:
            deltas[commit] = authority_delta(commit)
        delta = deltas[commit]
        declared = sorted(set(roots))
        collisions = sorted(set(delta["changed_scientific_roots"]) & set(declared))
        if collisions:
            raise ExperimentIIIError(
                "PROVENANCE_AUTHORITY_DRIFT",
                f"{relative} depends on {collisions}, which the amendment "
                f"changed; this artifact is genuinely invalidated and must be "
                f"regenerated, not revalidated",
            )
        records.append(
            {
                "artifact": relative,
                # Keyed on CANONICAL CONTENT, not file bytes. Re-serialising the
                # same JSON is not a change to the artifact, and a receipt that
                # only recognised one formatting of it would refuse a faithful
                # copy while still admitting nothing that was actually edited:
                # any change to a value moves the canonical digest.
                "artifact_canonical_sha256": canonical_sha256(body),
                "artifact_file_sha256": sha256_file(path),
                "artifact_bytes": path.stat().st_size,
                "historical_authority_sha256": observed,
                "historical_authority_freeze_commit": commit,
                "revalidated_against_authority_sha256": FROZEN_AUTHORITY_SHA256,
                "depends_on_authority_roots": declared,
                "changed_scientific_roots_since_historical": delta[
                    "changed_scientific_roots"
                ],
                "dependency_intersection_empty": True,
                "bytes_modified_by_revalidation": False,
                "scientific_content_unchanged": True,
                "status": "REVALIDATED",
            }
        )

    receipt = {
        "schema_version": REVALIDATION_SCHEMA_VERSION,
        "authority_section": "A0_INVALIDATION_SCOPE",
        "rule": (
            "every downstream artifact bound to the old AUTHORITY_SHA256 is "
            "invalidated and must be revalidated"
        ),
        "authority_version": AUTHORITY_VERSION,
        "authority_binding": binding,
        "authority_freeze_commit": AUTHORITY_FREEZE_COMMIT,
        "authority_deltas": deltas,
        "revalidated": records,
        "revalidated_count": len(records),
        "regenerated_instead": [],
        "scientific_evidence_invalidated": False,
        "passed": True,
    }
    if out is not None:
        from mineocclude.experiment_iii.schema import write_json_atomic

        write_json_atomic(out, receipt)
    return receipt


def load_revalidation_index(
    path: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Revalidation records for the CURRENT authority, keyed by artifact digest.

    A record written against a different successor authority is ignored rather
    than trusted: a second amendment must be revalidated again.
    """
    target = path or REVALIDATION_INDEX_PATH
    if not target.is_file():
        return {}
    body = json.loads(target.read_text(encoding="utf-8"))
    if body.get("schema_version") != REVALIDATION_SCHEMA_VERSION:
        return {}
    bound = (body.get("authority_binding") or {}).get("AUTHORITY_SHA256")
    if bound != FROZEN_AUTHORITY_SHA256:
        return {}
    return {
        record["artifact_canonical_sha256"]: record
        for record in body.get("revalidated") or ()
        if record.get("status") == "REVALIDATED"
    }


def resolve_authority_binding(
    path: Path,
    observed: str | None,
    *,
    index: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Admit an artifact's authority binding, or raise ``PROVENANCE_AUTHORITY_DRIFT``.

    Current binding passes. A predecessor binding passes **only** with a
    revalidation record for this exact file digest under this exact authority.
    Anything else fails closed, unchanged.
    """
    current = verify_authority_binding()["AUTHORITY_SHA256"]
    if observed == current:
        return {"binding": "CURRENT", "authority_sha256": current, "revalidated": False}
    records = load_revalidation_index() if index is None else dict(index)
    digest = canonical_sha256(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )
    record = records.get(digest)
    if (
        record is not None
        and record.get("historical_authority_sha256") == observed
        and record.get("revalidated_against_authority_sha256") == current
    ):
        return {
            "binding": "REVALIDATED_PREDECESSOR",
            "authority_sha256": current,
            "historical_authority_sha256": observed,
            "revalidated": True,
            "artifact_canonical_sha256": digest,
        }
    raise ExperimentIIIError(
        "PROVENANCE_AUTHORITY_DRIFT",
        f"{path} was produced under authority {observed} and this run is bound "
        f"to {current}, with no revalidation record for digest {digest}",
    )

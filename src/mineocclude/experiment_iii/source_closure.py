"""The Experiment III source closure (authority 0.3).

```
sha256( "<mode> <blob-sha1> <stage>\\t<path>" records from
        `git ls-files -s src fabric scripts`,
        sorted ascending by the PATH FIELD ONLY as raw UTF-8 bytes,
        joined with a single LF and terminated by one trailing LF )
```

**A generic whole-line sort is forbidden.** It would order on ``<mode>`` and then
``<blob-sha1>`` before ever reaching the path, producing a different byte stream
and a different digest for the same tree. That is the single defect this module
exists to make impossible, so the sort key here is the path substring and never
the record.

The A1 implementation was deliberately left uncommitted, so the closure of the
*working tree* is computed against a **temporary index** built from ``HEAD`` plus
the working-tree contents of the three gated roots. The repository's own index is
never touched, and the resulting records are exactly what a commit of that tree
would produce.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from mineocclude.experiment_iii.authority import REPOSITORY_ROOT
from mineocclude.experiment_iii.errors import ExperimentIIIError

__all__ = [
    "CLOSURE_ROOTS",
    "closure_digest",
    "closure_records",
    "closure_stream",
    "source_closure",
]

#: The three gated roots, in the authority's order.
CLOSURE_ROOTS = ("src", "fabric", "scripts")


def _git(*arguments: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise ExperimentIIIError(
            "SOURCE_CLOSURE_DRIFT",
            f"git {' '.join(arguments)} failed: {result.stderr.strip()}",
        )
    return result.stdout


def closure_records(*, include_working_tree: bool = True) -> list[str]:
    """The ``git ls-files -s`` records for the three gated roots, unsorted."""
    if include_working_tree:
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ)
            env["GIT_INDEX_FILE"] = str(Path(directory) / "closure.index")
            _git("read-tree", "HEAD", env=env)
            _git("add", "-A", "--", *CLOSURE_ROOTS, env=env)
            output = _git("ls-files", "-s", "--", *CLOSURE_ROOTS, env=env)
    else:
        output = _git("ls-files", "-s", "--", *CLOSURE_ROOTS)
    return [line for line in output.split("\n") if line]


def closure_stream(records: list[str]) -> bytes:
    """Sort by the PATH FIELD ONLY, join with LF, terminate with one LF."""
    def path_of(record: str) -> bytes:
        if "\t" not in record:
            raise ExperimentIIIError(
                "SOURCE_CLOSURE_DRIFT",
                f"malformed ls-files record without a tab separator: {record!r}",
            )
        return record.split("\t", 1)[1].encode("utf-8")

    ordered = sorted(records, key=path_of)
    return ("\n".join(ordered) + "\n").encode("utf-8")


def closure_digest(*, include_working_tree: bool = True) -> str:
    return hashlib.sha256(
        closure_stream(closure_records(include_working_tree=include_working_tree))
    ).hexdigest()


def source_closure(*, include_working_tree: bool = True) -> dict[str, Any]:
    """The closure digest with the provenance a stage receipt must record."""
    records = closure_records(include_working_tree=include_working_tree)
    stream = closure_stream(records)
    return {
        "source_closure_sha256": hashlib.sha256(stream).hexdigest(),
        "roots": list(CLOSURE_ROOTS),
        "record_count": len(records),
        "stream_bytes": len(stream),
        "record_format": "<mode> <blob-sha1> <stage>\\t<path>",
        "sort": "ASCENDING_BY_PATH_FIELD_ONLY_AS_RAW_UTF8_BYTES",
        "whole_line_sort": False,
        "line_ending": "LF",
        "trailing_newline": True,
        "includes_uncommitted_working_tree": include_working_tree,
        "head_commit": _git("rev-parse", "HEAD").strip(),
    }

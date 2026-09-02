"""A18 must not package a result set that does not exist.

`build_scientific_package.py --stage package` globbed the results root, recorded
`artifact_count`, wrote the manifest and returned 0. Over an empty root that is
a PASS on a package tracing nothing: only A19's condition 7 caught it, a stage
later, which is the wrong place to learn that A12-A17 produced nothing.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "_a18_driver",
    REPOSITORY_ROOT / "scripts/experiment_iii/build_scientific_package.py",
)
a18 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(a18)

REQUIRED = (
    "PREDICTION_LOCK.json", "baselines_receipt.json", "primary_results.json",
    "temporal_results.json", "context_age_results.json",
    "adjudication_receipt.json",
)


def test_an_empty_results_root_is_refused(tmp_path: Path, capsys) -> None:
    results = tmp_path / "results"
    results.mkdir()
    assert a18.main(["--stage", "package", "--analysis", str(results)]) == 1
    assert "PACKAGE_ARTIFACT_MISSING" in capsys.readouterr().err
    assert not (results / "scientific_package_manifest.json").is_file()


@pytest.mark.parametrize("dropped", REQUIRED)
def test_a_missing_result_family_is_refused(
    tmp_path: Path, dropped: str, capsys
) -> None:
    """Every A12-A17 family A19 later requires must be present at A18."""
    results = tmp_path / "results"
    results.mkdir()
    for name in REQUIRED:
        if name != dropped:
            (results / name).write_text(json.dumps({"stage": "X"}), encoding="utf-8")
    assert a18.main(["--stage", "package", "--analysis", str(results)]) == 1
    err = capsys.readouterr().err
    assert "PACKAGE_ARTIFACT_MISSING" in err
    assert dropped in err


# --------------------------------------------------------------------------
# --plan-only must never resolve towards spending production
# --------------------------------------------------------------------------


def _driver(name: str):
    spec = importlib.util.spec_from_file_location(
        f"_drv_{name}", REPOSITORY_ROOT / "scripts/experiment_iii" / name
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "script,what",
    [("run_production_capture.py", "captures"),
     ("run_extraction.py", "forwards")],
)
def test_plan_only_with_execute_is_refused(script: str, what: str, capsys) -> None:
    """`--plan-only --execute` used to resolve silently towards execution.

    ``--plan-only`` defaults True and execution is chosen by ``--execute``, so
    the flag was inert: an operator who passed both got a production run of 125
    captures or 2,375 forwards.
    """
    assert _driver(script).main(["--plan-only", "--execute"]) == 1
    assert "contradictory" in capsys.readouterr().err


def test_plan_only_alone_still_plans() -> None:
    """A9 plan mode is unaffected: the guard fires only on the contradiction."""
    assert _driver("run_extraction.py").main(["--plan-only"]) == 0


@pytest.mark.parametrize(
    "script", ["run_production_capture.py", "run_extraction.py"]
)
def test_plan_only_alone_is_never_the_contradiction(script: str, capsys) -> None:
    """A7 plan mode needs --ladder, so it may refuse -- but never as the
    contradiction, which would mean the guard had swallowed a valid request."""
    _driver(script).main(["--plan-only"])
    assert "contradictory" not in capsys.readouterr().err

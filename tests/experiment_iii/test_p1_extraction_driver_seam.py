"""The A5 pilot driver's own construction of ``RuntimeLoadRequest``.

The 786-test suite of record covered both sides of this seam and still shipped
``EXTRACTION_DRIVER_PROVENANCE_TRUNCATION`` to a GPU host:

* ``tests/models/test_mineworld_adapter*`` exercised ``RuntimeLoadRequest``
  directly, always handing it a well-formed 40-character revision;
* ``tests/experiment_iii/test_p1_extraction.py`` exercised the campaign against
  a stub adapter it constructed itself.

Neither ever ran ``scripts/experiment_iii/run_p1_extraction.py``'s ``_execute``,
which is the only place the pilot's provenance is actually assembled. It passed
``_head_commit()[:12]``, the frozen contract requires ``CODE_SHA_LENGTH == 40``,
and the real A5 executor failed on the GPU host before the model loaded.

So these tests drive the *driver*: they run ``_execute`` far enough to capture
the request it hands to ``load_runtime`` and then stop. No CUDA, no weights, no
forward -- the recording adapter raises the moment it has the request.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from mineocclude.experiment_iii.authority import machine_authority
from mineocclude.experiment_iii.host_preflight import EXTRACTION_HOST_STAGES
from mineocclude.experiment_iii.p1_extraction import PILOT_CAPTURES
from mineocclude.models import mineworld_adapter as adapter_module

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DRIVER_PATH = REPOSITORY_ROOT / "scripts" / "experiment_iii" / "run_p1_extraction.py"

HEX = re.compile(r"\A[0-9a-f]+\Z")

# A HEAD that is unmistakably not the real one, so an assertion can prove the
# driver forwarded *this* identity rather than happening to agree with git.
MOCK_HEAD = "abcdef0123456789abcdef0123456789abcdef01"


def _driver() -> Any:
    """The real pilot driver module, loaded from the script path it ships at."""
    spec = importlib.util.spec_from_file_location(
        "experiment_iii_run_p1_extraction", DRIVER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _RequestRecorded(Exception):
    """Raised by the recording adapter once it holds the request under test."""


class _RecordingAdapter:
    """Stops the driver at ``load_runtime`` with the request it constructed.

    Raising rather than returning is deliberate: nothing past this point in
    ``_execute`` may run in a test, because everything past it is the pilot's
    190 real forwards.
    """

    def __init__(self, sink: list[adapter_module.RuntimeLoadRequest]) -> None:
        self._sink = sink

    def load_runtime(self, request: adapter_module.RuntimeLoadRequest) -> None:
        self._sink.append(request)
        raise _RequestRecorded


def _a3_receipt() -> dict[str, Any]:
    """An extraction-host A3 receipt that authorizes A5 with verified weights."""
    extraction = machine_authority()["extraction"]
    return {
        "passed": True,
        "authorized_stages": list(EXTRACTION_HOST_STAGES),
        "model_identity_checks": {
            "verified": True,
            "main_checkpoint": {
                "observed_sha256": extraction["main_checkpoint_sha256"],
                "path": "/weights/model.pt",
            },
            "vae_checkpoint": {
                "observed_sha256": extraction["vae_sha256"],
                "path": "/weights/vae.pt",
            },
        },
    }


def _handoff_manifest() -> dict[str, Any]:
    """The ten pilot capture units, in the shape the real handoff manifest uses."""
    units = []
    for identity in ("e3_p90", "e3_p91"):
        for level in range(5):
            index = len(units)
            units.append(
                {
                    "capture_unit_id": f"{identity}__L{level}",
                    "identity": identity,
                    "condition_id": f"L{level}",
                    "seed": 5276912483436174581 + index,
                    "spec_sha256": f"{index:064x}",
                    "target_model_frame_indices": list(range(39, 58)),
                }
            )
    assert len(units) == PILOT_CAPTURES
    return {"captures": {"units": units}}


def _args(tmp_path: Path) -> argparse.Namespace:
    """Every argument ``_execute`` reads on the way to ``load_runtime``.

    The digests and paths are structurally valid but arbitrary; the only field
    under test is the one the driver derives for itself.
    """
    for name in ("source_root", "model.yaml", "model.pt", "vae.yaml", "vae.pt"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    return argparse.Namespace(
        a3_receipt=tmp_path / "a3.json",
        handoff_manifest=tmp_path / "manifest.json",
        captures=tmp_path / "captures",
        activations=tmp_path / "activations",
        runtime_id="experiment-iii-a5-pilot",
        mineworld_source_revision="b" * 40,
        modelscope_asset_revision="c" * 40,
        mineworld_source_root=tmp_path / "source_root",
        model_config=tmp_path / "model.yaml",
        main_checkpoint=tmp_path / "model.pt",
        vae_config=tmp_path / "vae.yaml",
        vae_checkpoint=tmp_path / "vae.pt",
        model_config_sha256="3" * 64,
        vae_config_sha256="4" * 64,
        environment_report_sha256="5" * 64,
        precision="float16",
        device="cuda",
    )


def _captured_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    head: str | None = MOCK_HEAD,
) -> adapter_module.RuntimeLoadRequest:
    """Run the real ``_execute`` up to ``load_runtime`` and return its request."""
    driver = _driver()
    args = _args(tmp_path)
    args.a3_receipt.write_text(json.dumps(_a3_receipt()), encoding="utf-8")
    args.handoff_manifest.write_text(json.dumps(_handoff_manifest()), encoding="utf-8")

    if head is not None:
        monkeypatch.setattr(driver, "_head_commit", lambda: head)

    recorded: list[adapter_module.RuntimeLoadRequest] = []
    monkeypatch.setattr(
        adapter_module,
        "create_mineworld_adapter",
        lambda *a, **k: _RecordingAdapter(recorded),
    )

    with pytest.raises(_RequestRecorded):
        driver._execute(args, driver.extraction_plan())

    assert len(recorded) == 1, "the driver must load exactly one runtime"
    return recorded[0]


# --------------------------------------------------------------------------
# The driver -> adapter seam
# --------------------------------------------------------------------------


def test_the_driver_passes_a_complete_forty_character_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exact failure the GPU host hit: a short SHA never reaches the model."""
    request = _captured_request(tmp_path, monkeypatch)
    revision = request.mineocclude_revision
    assert adapter_module.CODE_SHA_LENGTH == 40
    assert len(revision) == adapter_module.CODE_SHA_LENGTH
    assert HEX.fullmatch(revision) is not None
    assert revision == MOCK_HEAD


def test_the_driver_does_not_abbreviate_the_head_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pins the defect itself: the 12-character short form must not appear."""
    request = _captured_request(tmp_path, monkeypatch)
    assert request.mineocclude_revision != MOCK_HEAD[:12]
    assert len(request.mineocclude_revision) != 12


def test_the_driver_revision_is_the_working_trees_real_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unmocked: the recorded provenance must name the implementation that ran."""
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if len(head) != 40:
        pytest.skip("no git HEAD is resolvable from this working tree")
    request = _captured_request(tmp_path, monkeypatch, head=None)
    assert request.mineocclude_revision == head
    assert len(request.mineocclude_revision) == 40


def test_the_recorded_request_is_the_frozen_adapter_dataclass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The seam under test is the real one, not a paraphrase of it.

    ``RuntimeLoadRequest.__post_init__`` ran on this instance, so reaching the
    recorder at all proves the driver satisfied the whole provenance contract --
    not merely the one field these tests name.
    """
    request = _captured_request(tmp_path, monkeypatch)
    assert isinstance(request, adapter_module.RuntimeLoadRequest)
    assert request.runtime_id == "experiment-iii-a5-pilot"
    assert request.main_checkpoint_sha256 == str(
        machine_authority()["extraction"]["main_checkpoint_sha256"]
    )


# --------------------------------------------------------------------------
# The contract stays fail-closed
# --------------------------------------------------------------------------


def test_a_truncated_revision_is_still_refused_before_the_model_loads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The repair is the driver's, not the contract's.

    Reconstructing the old expression must still fail exactly as it did on the
    GPU host. If this ever passes, the fix was applied to the wrong side.
    """
    request = _captured_request(tmp_path, monkeypatch)
    fields = {
        name: getattr(request, name) for name in request.__dataclass_fields__
    }
    for label, bad in (
        ("short", MOCK_HEAD[:12]),
        ("empty", ""),
        ("non-hexadecimal", "z" * 40),
        ("branch name", "experiment/exp3-graded-partial-observability"),
        ("short with padding", MOCK_HEAD[:12] + " " * 28),
        ("forty-one characters", MOCK_HEAD + "a"),
    ):
        with pytest.raises(adapter_module.MineWorldAdapterError) as error:
            adapter_module.RuntimeLoadRequest(
                **{**fields, "mineocclude_revision": bad}
            )
        assert (
            error.value.code is adapter_module.AdapterFailureCode.INVALID_PROVENANCE
        ), label

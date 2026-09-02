"""The A9 -> A10 -> A11 array-path contract, asserted in one place.

A11 formatted its own ``layer19_current.npy``. A9 has never written that name
and A10 has never read it, so the feature build could only fail -- and only
after A9 had spent all 2,375 production forwards. The three stages must resolve
the same bytes from the same function, not from three spellings that happen to
agree until one of them is edited.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from mineocclude.experiment_iii.activation_store import (
    UNITS_PER_CAPTURE,
    array_relative_path,
)
from mineocclude.experiment_iii.extraction import SELECTED_LAYERS
from mineocclude.experiment_iii.feature_store import _activation_path
from mineocclude.experiment_iii.schema import TemporalSlice


@pytest.mark.parametrize("layer", SELECTED_LAYERS)
@pytest.mark.parametrize("slice_name", [s.value for s in TemporalSlice])
def test_a11_reads_exactly_where_a9_writes(layer: int, slice_name: str) -> None:
    root, unit = Path("ACT"), "e3_t01__L0"
    assert _activation_path(root, unit, layer, slice_name) == (
        root / unit / array_relative_path(layer, slice_name)
    )


def test_a11_does_not_respell_the_path_itself() -> None:
    """The contract is shared code, not a coincidence between two literals."""
    import ast

    tree = ast.parse(inspect.getsource(_activation_path).lstrip())
    func = tree.body[0]
    func.body = [n for n in func.body if not (isinstance(n, ast.Expr)
                 and isinstance(n.value, ast.Constant)
                 and isinstance(n.value.value, str))]      # drop the docstring
    code = ast.unparse(func)
    assert "array_relative_path" in code
    assert ".npy" not in code and "layer{" not in code


def test_the_frozen_array_set_is_three_layers_by_two_slices() -> None:
    paths = {
        array_relative_path(layer, name)
        for layer in SELECTED_LAYERS
        for name in TemporalSlice
    }
    assert len(paths) == UNITS_PER_CAPTURE == 6
    assert paths == {
        "activations/layer_04/PREVIOUS.npy", "activations/layer_04/CURRENT.npy",
        "activations/layer_10/PREVIOUS.npy", "activations/layer_10/CURRENT.npy",
        "activations/layer_19/PREVIOUS.npy", "activations/layer_19/CURRENT.npy",
    }

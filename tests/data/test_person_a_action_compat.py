"""Cross-role compatibility: C's raw actions must be drop-in for A's converter.

Verifies C's ``flat_to_official_raw_action`` reproduces Person A's expected
raw-action shape for EVERY case in A's frozen golden matrix
(``tests/fixtures/person_a_compat/phase3_wave2_action_matrix.json``, vendored
read-only from ``origin/role/person-a-model``). If this passes, A's
``convert_action`` consumes C's mapped raw actions without reinterpretation.
"""

import json
from pathlib import Path

import mineocclude.contracts  # noqa: F401  (import-order cycle guard)
from mineocclude.data.convert_mineworld import (
    OFFICIAL_KEY_BINDINGS,
    OFFICIAL_MOUSE_BUTTONS,
    flat_to_official_raw_action,
)

MATRIX = (Path(__file__).resolve().parents[1] / "fixtures" / "person_a_compat"
          / "phase3_wave2_action_matrix.json")

# Reverse of A's raw format -> the flat capture row C would have logged.
KEY_TO_FLAT = {v: k for k, v in OFFICIAL_KEY_BINDINGS.items()}
BUTTON_TO_FLAT = {v: k for k, v in OFFICIAL_MOUSE_BUTTONS.items()}


def _flat_from_official(raw, prev_hotbar):
    """Build the flat C row equivalent to one of A's raw_action cases."""
    flat = {f: False for f in list(OFFICIAL_KEY_BINDINGS) + list(OFFICIAL_MOUSE_BUTTONS)}
    hotbar = prev_hotbar
    for key in raw["keyboard"]["keys"]:
        if key in KEY_TO_FLAT:
            flat[KEY_TO_FLAT[key]] = True
        elif key.startswith("key.keyboard.") and key.split(".")[-1].isdigit():
            hotbar = int(key.split(".")[-1]) - 1  # slot key N -> index N-1
    for btn in raw["mouse"]["buttons"]:
        if btn in BUTTON_TO_FLAT:
            flat[BUTTON_TO_FLAT[btn]] = True
    flat["hotbar"] = hotbar
    flat["camera_dx"] = raw["mouse"]["dx"]
    flat["camera_dy"] = raw["mouse"]["dy"]
    return flat, hotbar


def test_c_raw_actions_match_person_a_golden_matrix():
    matrix = json.loads(MATRIX.read_text())
    assert matrix["vocabulary_offset"] == 8192
    for case in matrix["cases"]:
        expected = case["raw_action"]
        # prev_hotbar differs from the target only for the hotbar case, so a
        # switch is emitted; every other case has no number key.
        keys = expected["keyboard"]["keys"]
        digit_keys = [k for k in keys if k.split(".")[-1].isdigit()]
        prev_hotbar = 0 if not digit_keys else 8  # force a change for the switch
        flat, _ = _flat_from_official(expected, prev_hotbar)
        got = flat_to_official_raw_action(flat, prev_hotbar=prev_hotbar)
        assert sorted(got["keyboard"]["keys"]) == sorted(keys), case["case_id"]
        assert got["mouse"]["buttons"] == sorted(expected["mouse"]["buttons"]), case["case_id"]
        assert got["mouse"]["dx"] == expected["mouse"]["dx"], case["case_id"]
        assert got["mouse"]["dy"] == expected["mouse"]["dy"], case["case_id"]


def test_unchanged_hotbar_emits_no_number_key():
    flat = {f: False for f in OFFICIAL_KEY_BINDINGS}
    flat.update({f: False for f in OFFICIAL_MOUSE_BUTTONS})
    flat.update({"hotbar": 3, "camera_dx": 0.0, "camera_dy": 0.0})
    # same slot as prev -> no switch -> no number key
    out = flat_to_official_raw_action(flat, prev_hotbar=3)
    assert out["keyboard"]["keys"] == []
    # a real switch -> the slot key appears
    out2 = flat_to_official_raw_action(flat, prev_hotbar=0)
    assert out2["keyboard"]["keys"] == ["key.keyboard.4"]


def test_noop_is_fully_empty():
    flat = {f: False for f in OFFICIAL_KEY_BINDINGS}
    flat.update({f: False for f in OFFICIAL_MOUSE_BUTTONS})
    flat.update({"hotbar": 0, "camera_dx": 0.0, "camera_dy": 0.0})
    out = flat_to_official_raw_action(flat, prev_hotbar=0)
    assert out == {"keyboard": {"keys": []},
                   "mouse": {"buttons": [], "dx": 0.0, "dy": 0.0}}

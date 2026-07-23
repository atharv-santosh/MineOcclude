"""Raw action -> MineWorld env-action / 11-token conversion (Person C, C4.4).

Person C converts the recorded raw keyboard/mouse state into the unambiguous
env-action dict that Person A feeds to the pinned MineWorld tokenizer. The
EXACT token ids and camera bin boundaries are owned by MineWorld's pinned
``MCDataset.json_action_to_env_action`` / ``get_action_index_from_actiondict``
(``action_vocab_offset=8192``) and must be reconciled by Person A against the
checkpoint. Per the frozen interface packet, Person C does not invent them.

This module therefore:

  * always emits the raw-preserving env-action dict, and
  * emits 11 tokens through a *pluggable converter*. The default is a
    self-consistent REFERENCE layout (``REFERENCE_CONVERTER_ID``) so token
    count/order can be unit-tested now; a scientific run must inject A's
    pinned converter and record its identity. Rows written with the reference
    converter carry that converter id so no one can mistake them for the
    pinned vocabulary.

Every raw row is converted, including no-op (C4.4: omitting no-op rows shifts
later actions).
"""
from __future__ import annotations

import json
from collections.abc import Callable

import numpy as np

ACTION_VOCAB_OFFSET = 8192   # action tokens live above the visual vocab
N_ACTION_TOKENS = 11
CAMERA_BINS = 11             # VPT-style; A reconciles the exact scheme
CAMERA_MAX_DEG = 10.0        # |dx|,|dy| beyond this saturate to the edge bin

REFERENCE_CONVERTER_ID = "person_c_reference_tokenizer_v0"
PINNED_CONVERTER_REQUIRED = "PINNED_MINEWORLD_CONVERTER_REQUIRED"

# Reference token slot layout: (name, number_of_values). BOS/EOS are singletons.
SLOTS = [
    ("act_bos", 1),
    ("camera_dy", CAMERA_BINS),
    ("camera_dx", CAMERA_BINS),
    ("hotbar", 9),
    ("forward_back", 3),   # 0 none, 1 forward, 2 back
    ("left_right", 3),     # 0 none, 1 left, 2 right
    ("sprint_sneak", 3),   # 0 none, 1 sprint, 2 sneak
    ("use_attack", 3),     # 0 none, 1 use, 2 attack
    ("jump", 2),           # 0 none, 1 jump
    ("drop_pick", 3),      # 0 none, 1 drop, 2 pickItem
    ("act_eos", 1),
]
assert len(SLOTS) == N_ACTION_TOKENS


def bin_camera(deg: float, bins: int = CAMERA_BINS,
               max_deg: float = CAMERA_MAX_DEG) -> int:
    """Map a camera delta (degrees) to a symmetric bin index in [0, bins-1].

    Linear symmetric binning with the centre bin = no motion. The pinned
    mcdataset.py boundaries (possibly mu-law) replace this in the A path.
    """
    if not np.isfinite(deg):
        deg = 0.0
    deg = float(np.clip(deg, -max_deg, max_deg))
    half = bins // 2
    frac = deg / max_deg               # [-1, 1]
    return int(round(frac * half)) + half


def raw_to_env_action(row) -> dict:
    """Convert one raw action record (dict-like) to a MineWorld env-action dict."""
    def flag(key):
        return bool(row.get(key, False)) if hasattr(row, "get") else bool(row[key])
    return {
        "camera": [float(row["camera_dy"]), float(row["camera_dx"])],  # [pitch, yaw]
        "hotbar": int(row["hotbar"]),
        "forward": flag("forward"), "back": flag("back"),
        "left": flag("left"), "right": flag("right"),
        "sprint": flag("sprint"), "sneak": flag("sneak"),
        "use": flag("use"), "attack": flag("attack"),
        "jump": flag("jump"),
        "drop": flag("drop"), "pick_item": flag("pick_item"),
    }


def _tri(pos: bool, neg: bool) -> int:
    """3-state encode: 0 none, 1 first, 2 second (first wins if both)."""
    if pos:
        return 1
    if neg:
        return 2
    return 0


def env_action_to_tokens(env: dict, offset: int = ACTION_VOCAB_OFFSET) -> list[int]:
    """Reference 11-token encoding. Each slot value is offset into its own block.

    NOTE: this is a self-consistent reference layout for validation, not the
    authoritative MineWorld vocab — Person A substitutes the pinned tokenizer.
    """
    values = {
        "act_bos": 0,
        "camera_dy": bin_camera(env["camera"][0]),
        "camera_dx": bin_camera(env["camera"][1]),
        "hotbar": int(np.clip(env["hotbar"], 0, 8)),
        "forward_back": _tri(env["forward"], env["back"]),
        "left_right": _tri(env["left"], env["right"]),
        "sprint_sneak": _tri(env["sprint"], env["sneak"]),
        "use_attack": _tri(env["use"], env["attack"]),
        "jump": 1 if env["jump"] else 0,
        "drop_pick": _tri(env["drop"], env["pick_item"]),
        "act_eos": 0,
    }
    tokens, base = [], offset
    for name, size in SLOTS:
        value = int(values[name])
        if not 0 <= value < size:
            raise ValueError(f"slot {name} value {value} out of range [0,{size})")
        tokens.append(base + value)
        base += size
    assert len(tokens) == N_ACTION_TOKENS
    return tokens


def write_mineworld_actions(
    frame_map,
    path: str,
    tokenizer: Callable[[dict], list[int]] | None = None,
    converter_id: str = REFERENCE_CONVERTER_ID,
) -> int:
    """Write mineworld_actions.jsonl: env-action + tokens per accepted frame.

    ``tokenizer`` defaults to the reference encoding; a scientific run injects
    A's pinned converter and passes its recorded ``converter_id``. Every row
    asserts exactly ``N_ACTION_TOKENS`` tokens (C4.4) and records the
    converter identity so provenance is explicit.
    """
    encode = tokenizer if tokenizer is not None else env_action_to_tokens
    count = 0
    with open(path, "w", encoding="utf-8") as handle:
        for _, row in frame_map.iterrows():
            env = raw_to_env_action(row)
            tokens = encode(env)
            if len(tokens) != N_ACTION_TOKENS:
                raise ValueError(
                    f"converter {converter_id} produced {len(tokens)} tokens; "
                    f"exactly {N_ACTION_TOKENS} are required"
                )
            record = {
                "episode_id": str(row["episode_id"]),
                "trajectory_id": str(row["trajectory_id"]),
                "server_tick": int(row["server_tick"]),
                "model_frame_idx": int(row["model_frame_idx"]),
                "action_idx": int(row["action_idx"]),
                "env_action": env,
                "tokens": tokens,
                "converter_id": converter_id,
                "action_vocab_offset": ACTION_VOCAB_OFFSET,
            }
            handle.write(json.dumps(record) + "\n")
            count += 1
    return count

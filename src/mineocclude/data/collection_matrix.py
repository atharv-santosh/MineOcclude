"""The locked 66-trajectory MVP collection matrix (Person C, C7.1 preparation).

Encodes the frozen MVP matrix and emits (a) a machine-readable plan and (b)
the exact ordered server-console command blocks the operator runs:

  Core Regime A (48) : 6 layouts x v{1,2} x q{0.02,0.2} x hidden{4,16}
  No-wall visible (6): 1 per layout (positive control; sheep always visible)
  Occluder only  (6) : 1 per layout (negative control; wall, no sheep)
  Context sentinel(6): 1 per layout, hidden=24 (1.5x the 16-pair context), q=0.05

Durations are HIDDEN-FRAME counts at 20 Hz: 4 = 0.25x context, 16 = 1.0x,
24 = 1.5x. These mappings are global and must not be rounded differently by
episode. Collection order is balanced-interleaved with a fixed shuffle seed
so order cannot align with q, duration, layout, or control type. Per-episode
seeds are deterministic and recorded; the immutable NumPy noise schedule for
each episode is generated from its seed by
``mineocclude.data.noise_schedule`` before capture.

Layout identities are the six frozen C1 layout IDs (``layout_01`` ..
``layout_06`` from ``configs/scenes/layouts.yaml``).

C7 STATUS: layouts v0.3 (``configs/scenes/layouts.yaml``) now exports the
mod's real, geometrically-valid geometry, and the mod registers the matching
``layout_01``–``layout_06`` IDs — so the command blocks emitted here are
accepted by the runtime. Duration is controlled: this module emits no
``reveal`` command, so the mod stops at the hidden-frame target (reveal
defaults to 0), giving exactly ``hidden`` occluded frames per core cell.

Usage:
  python -m mineocclude.data.collection_matrix --out configs/collection
"""
from __future__ import annotations

import argparse
import os
import random

import pandas as pd

LAYOUTS = [f"layout_0{i}" for i in range(1, 7)]
CORE_V = [1.0, 2.0]
CORE_Q = [0.02, 0.20]
CORE_HIDDEN = [4, 16]           # 0.25x and 1.0x context
SENTINEL_HIDDEN = 24            # 1.5x context
SENTINEL_Q = 0.05

WARMUP_TICKS = 60               # 3 s pre-record delay
CORE_MAX_TICKS = 300            # safety cap; hidden-frame auto-stop governs
CONTROL_TICKS = 60              # no-wall / no-sheep: fixed 3 s (no hidden phase)
SEED_BASE = 20260726
SHUFFLE_SEED = 42


def build_matrix() -> pd.DataFrame:
    rows = []
    episode = 1

    # Core (48): episode_id 1..48
    for layout in LAYOUTS:
        for v in CORE_V:
            for q in CORE_Q:
                for hidden in CORE_HIDDEN:
                    rows.append(dict(set="core", scene="normal",
                                     layout_id=layout, v=v, q=q,
                                     hidden_frames=hidden,
                                     max_ticks=CORE_MAX_TICKS,
                                     warmup=WARMUP_TICKS,
                                     episode_id=episode))
                    episode += 1
    # No-wall positive control (6): 49..54
    for layout in LAYOUTS:
        rows.append(dict(set="nowall", scene="nowall", layout_id=layout,
                         v=1.0, q=0.05, hidden_frames=0,
                         max_ticks=CONTROL_TICKS, warmup=WARMUP_TICKS,
                         episode_id=episode))
        episode += 1
    # Occluder-only negative control (6): 55..60
    for layout in LAYOUTS:
        rows.append(dict(set="nosheep", scene="nosheep", layout_id=layout,
                         v=1.0, q=0.05, hidden_frames=0,
                         max_ticks=CONTROL_TICKS, warmup=WARMUP_TICKS,
                         episode_id=episode))
        episode += 1
    # Context sentinel (6): 61..66
    for layout in LAYOUTS:
        rows.append(dict(set="sentinel", scene="normal", layout_id=layout,
                         v=1.0, q=SENTINEL_Q, hidden_frames=SENTINEL_HIDDEN,
                         max_ticks=CORE_MAX_TICKS, warmup=WARMUP_TICKS,
                         episode_id=episode))
        episode += 1

    matrix = pd.DataFrame(rows)
    # Deterministic per-trajectory seed.
    matrix["seed"] = SEED_BASE + matrix["episode_id"] * 7919
    # Balanced-interleaved collection order (fixed seed) so order != condition.
    order = list(range(len(matrix)))
    random.Random(SHUFFLE_SEED).shuffle(order)
    matrix = matrix.iloc[order].reset_index(drop=True)
    matrix["collection_order"] = range(len(matrix))
    return matrix


def command_blocks(matrix: pd.DataFrame) -> str:
    """Ordered server-console command blocks, one per trajectory."""
    lines = [
        "# MineOcclude MVP collection — run each block in the SERVER console.",
        "# After each 'start', wait for '... recording started' then let it",
        "# auto-stop, then validate + build_dataset for that episode before",
        "# the next block.",
        f"# {len(matrix)} trajectories, balanced order "
        f"(shuffle seed {SHUFFLE_SEED}).",
        "",
    ]
    for _, row in matrix.iterrows():
        lines.append(
            f"# [{int(row.collection_order) + 1}/{len(matrix)}] set={row.set} "
            f"layout={row.layout_id} v={row.v} q={row.q} "
            f"hidden={int(row.hidden_frames)} ep={int(row.episode_id)}"
        )
        lines.append(f"mineocclude mode {row.scene}")
        lines.append(f"mineocclude duration {int(row.hidden_frames)}")
        lines.append(f"mineocclude warmup {int(row.warmup)}")
        lines.append(
            f"mineocclude start {row.layout_id} {int(row.episode_id)} "
            f"{int(row.seed)} {row.v} {row.q} {int(row.max_ticks)}"
        )
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="configs/collection")
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)

    matrix = build_matrix()
    matrix.to_csv(os.path.join(args.out, "mvp_matrix.csv"), index=False)
    matrix.to_parquet(os.path.join(args.out, "mvp_matrix.parquet"), index=False)
    with open(os.path.join(args.out, "mvp_collection_commands.txt"), "w") as f:
        f.write(command_blocks(matrix))

    print(f"wrote {len(matrix)} trajectories to "
          f"{args.out}/mvp_matrix.{{csv,parquet}}")
    print("by set:", matrix.set.value_counts().to_dict())
    print("core cells:", int((matrix.set == "core").sum()),
          "| unique seeds:", matrix.seed.nunique(),
          "| unique episode_ids:", matrix.episode_id.nunique())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Matrix-aware collection driver + progress report (Person C, C7.2 support).

Cross-references the locked MVP matrix against what has actually been
captured, runs each collected episode through the strict-join pipeline, and
reports accepted / excluded / remaining by set — the bounded-window daily
count/QA report.

Usage:
  python -m mineocclude.data.collect \
      --matrix configs/collection/mvp_matrix.csv \
      --server-root <server_run_dir>/mineocclude_out \
      --client-root <client_run_dir>/mineocclude_client_out \
      --out data/mvp
"""
from __future__ import annotations

import argparse
import json
import os

import pandas as pd

from mineocclude.data.build_dataset import process_episode


def _episode_dirs(server_root: str, client_root: str,
                  episode: int) -> tuple[str, str, bool]:
    server = os.path.join(os.path.expanduser(server_root), f"episode_{episode}")
    client = os.path.join(os.path.expanduser(client_root), f"episode_{episode}")
    return server, client, (os.path.isdir(server) and os.path.isdir(client))


def run(matrix_csv: str, server_root: str, client_root: str, out_root: str,
        run_empirical: bool = True) -> dict:
    matrix = pd.read_csv(matrix_csv)
    os.makedirs(out_root, exist_ok=True)

    results = []
    for _, row in matrix.iterrows():
        episode = int(row.episode_id)
        server_dir, client_dir, present = _episode_dirs(
            server_root, client_root, episode
        )
        record = {"episode_id": episode, "set": row.set,
                  "layout_id": row.layout_id, "v": row.v, "q": row.q,
                  "hidden_frames": int(row.hidden_frames),
                  "collected": present, "accepted": False, "n_frames": 0,
                  "n_hidden": None, "reasons": []}
        if present:
            summary = process_episode(server_dir, client_dir, out_root,
                                      run_empirical)
            record["accepted"] = summary["accepted"]
            record["n_frames"] = summary.get("n_frames", 0)
            record["n_hidden"] = summary.get("n_hidden")
            record["reasons"] = summary.get("problems", [])
        results.append(record)

    report = pd.DataFrame(results)
    report.to_csv(os.path.join(out_root, "collection_status.csv"), index=False)

    summary = {
        "total": len(report),
        "collected": int(report.collected.sum()),
        "accepted": int(report.accepted.sum()),
        "remaining": int((~report.collected).sum()),
        "collected_not_accepted": int(
            (report.collected & ~report.accepted).sum()
        ),
        "by_set": {
            name: {
                "total": int((report.set == name).sum()),
                "accepted": int(((report.set == name) & report.accepted).sum()),
            }
            for name in sorted(report.set.unique())
        },
    }
    with open(os.path.join(out_root, "collection_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", default="configs/collection/mvp_matrix.csv")
    parser.add_argument("--server-root", required=True)
    parser.add_argument("--client-root", required=True)
    parser.add_argument("--out", default="data/mvp")
    parser.add_argument("--no-empirical", action="store_true")
    args = parser.parse_args()

    summary = run(args.matrix, args.server_root, args.client_root, args.out,
                  run_empirical=not args.no_empirical)
    print(f"MVP collection: {summary['accepted']}/{summary['total']} accepted "
          f"({summary['collected']} collected, {summary['remaining']} "
          f"remaining, {summary['collected_not_accepted']} "
          "collected-but-rejected)")
    for name, value in summary["by_set"].items():
        print(f"  {name:9s}: {value['accepted']}/{value['total']} accepted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

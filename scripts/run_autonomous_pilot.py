#!/usr/bin/env python3
"""Autonomous episode collection driver (Person C).

Removes the human from the collection loop: for each planned episode it

  1. generates the immutable NumPy noise schedule (seed derived from the
     episode id by the locked convention),
  2. brings the Minecraft client window frontmost (macOS) so the renderer is
     never throttled,
  3. drives the dedicated server through its console FIFO,
  4. waits for the episode to finish and verifies the client stayed
     connected and capturing,
  5. runs the strict Python pipeline (align -> visibility -> conversion ->
     frame_map.parquet -> QA) immediately, and
  6. on failure retries the same planned cell under a NEW episode id
     (attempts are linked, never overwritten).

The camera is server-locked during recording, so operator input cannot
change the framing; the only human prerequisite is a running, connected
client.

Usage:
  python3 scripts/run_autonomous_pilot.py --plan smoke      # 2 reveal episodes + impulse
  python3 scripts/run_autonomous_pilot.py --plan pilots10   # C6B ten varied pilots
  python3 scripts/run_autonomous_pilot.py --plan controls   # no-wall + no-sheep controls
  python3 scripts/run_autonomous_pilot.py --plan impulse3   # 3 impulse fixtures

Every plan begins with scripted-impulse pairing calibration for the current
client connection.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO, "src"))

import mineocclude.contracts  # noqa: E402,F401  (import-order cycle guard)
from mineocclude.data.build_dataset import process_episode  # noqa: E402
from mineocclude.data.noise_schedule import (  # noqa: E402
    generate_noise_schedule,
    write_schedule,
)

SRV = os.path.expanduser("~/mineocclude-server")
CLIENT = os.path.expanduser("~/mineocclude-client")
FIFO = os.path.join(SRV, "cmd.fifo")
SEED_BASE = 20260726  # locked convention: seed = SEED_BASE + episode_id * 7919


def server_log_path() -> str:
    return os.path.join(SRV, "logs", "latest.log")


def log_text() -> str:
    try:
        with open(server_log_path(), errors="ignore") as handle:
            return handle.read()
    except FileNotFoundError:
        return ""


def wait_for(pattern: str, timeout: float, start_offset: int = 0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if re.search(pattern, log_text()[start_offset:]):
            return True
        time.sleep(1.0)
    return False


def send(commands: list[str]) -> None:
    with open(FIFO, "w") as fifo:
        fifo.write("\n".join(commands) + "\n")


def _utc_now() -> str:
    # Second-precision Z form: the rollout-registry validator parses strictly
    # with "%Y-%m-%dT%H:%M:%SZ" (offset/fractional forms fail closed).
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git(args: list[str]) -> str:
    try:
        return subprocess.run(["git", "-C", REPO, *args], capture_output=True,
                              text=True, timeout=15).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return ""


def _sha256(path: str) -> str:
    import hashlib
    try:
        with open(path, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()
    except OSError:
        return ""


def _capturing_jar_path() -> str:
    """Return the installed capture mod, preferring the accepted 0.1.1 build."""
    override = os.environ.get("MINEOCCLUDE_MOD_JAR")
    if override:
        return os.path.expanduser(override)
    mods = os.path.join(SRV, "mods")
    for name in ("mineocclude-0.1.1.jar", "mineocclude-0.1.0.jar"):
        candidate = os.path.join(mods, name)
        if os.path.isfile(candidate):
            return candidate
    return os.path.join(mods, "mineocclude-0.1.1.jar")


def _write_provenance(episode_id, command, seed, start_utc, end_utc, out_root,
                      layout, accepted, trajectory_id=None) -> str:
    """Record run-level provenance AT capture: exact command, UTC start/end,
    seed, git dirty/sha, capturing-jar hash. This is the field set E's
    registry needs and that captures before this change lack."""
    prov = {
        "episode_id": episode_id,
        "trajectory_id": trajectory_id,
        "layout": layout,
        "seed": int(seed),
        "capture_command": command,
        "start_utc": start_utc,
        "end_utc": end_utc,
        "git_sha": _git(["rev-parse", "HEAD"]),
        # git_dirty is CODE-scoped: was the code/config that produced this
        # capture uncommitted? Output data written into the tracked data/ dir
        # during collection does not count (it always exists mid-run). This is
        # the provenance E asks about. working_tree_dirty is the raw all-paths
        # flag, kept for full transparency.
        "git_dirty": bool(_git(["status", "--porcelain", "--",
                                "src", "fabric/mineocclude-mod/src", "scripts",
                                "configs", "schemas"])),
        "working_tree_dirty": bool(_git(["status", "--porcelain"])),
        "capturing_jar_sha256": _sha256(_capturing_jar_path()),
        "accepted": accepted,
        "provenance_schema": "person-c-capture-provenance-v0.1",
    }
    dest_dir = (os.path.join(out_root, trajectory_id) if trajectory_id
                else os.path.join(out_root, f"episode_{episode_id}_failed"))
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, "capture_provenance.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(prov, handle, indent=1)
    return path


def focus_client() -> bool:
    """Bring the sole visible Minecraft client frontmost.

    Captures historically used macOS ``osascript``.  On Linux/X11, target the
    Minecraft window itself (rather than an arbitrary Java process), activate
    it through the window manager, and assert that it owns X input focus.
    """
    if sys.platform == "darwin":
        command = [
            "osascript", "-e",
            'tell application "System Events" to set frontmost of '
            '(first process whose name is "java") to true',
        ]
    elif sys.platform.startswith("linux"):
        if not os.environ.get("DISPLAY"):
            return False
        try:
            found = subprocess.run(
                ["xdotool", "search", "--onlyvisible", "--name",
                 r"^Minecraft"],
                check=True, capture_output=True, text=True, timeout=10,
            )
            window_ids = [line.strip() for line in found.stdout.splitlines()
                          if line.strip()]
            # Multiple visible clients make OS-level input targeting ambiguous.
            if len(window_ids) != 1:
                return False
            window_id = window_ids[0]
            subprocess.run(
                ["xdotool", "windowactivate", "--sync", window_id],
                check=True, capture_output=True, text=True, timeout=10,
            )
            focused = subprocess.run(
                ["xdotool", "getwindowfocus"],
                check=True, capture_output=True, text=True, timeout=10,
            )
            return focused.stdout.strip() == window_id
        except (subprocess.SubprocessError, OSError):
            return False
    else:
        return False
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=10)
        return True
    except (subprocess.SubprocessError, OSError):
        return False


def client_connected() -> bool:
    return "joined the game" in log_text() and not re.search(
        r"left the game(?!.*joined the game)", log_text(), re.S
    )


def run_episode(episode_id: int, *, scene: str, hidden: int, reveal: int,
                impulse_tick: int, impulse_deg: float, v: float, q: float,
                max_ticks: int, warmup: int, out_root: str,
                layout: str = "layout_01") -> dict:
    seed = SEED_BASE + episode_id * 7919
    schedule = generate_noise_schedule(seed=seed, n_draws=max_ticks, q=q)
    write_schedule(schedule, os.path.join(
        SRV, "mineocclude_schedules", f"episode_{episode_id}.jsonl"))

    if not focus_client():
        print("  [warn] could not focus the client window automatically")
    time.sleep(1.0)

    command = [
        f"mineocclude mode {scene}",
        f"mineocclude duration {hidden}",
        f"mineocclude reveal {reveal}",
        f"mineocclude warmup {warmup}",
        f"mineocclude impulse {impulse_tick} {impulse_deg}",
        "mineocclude lockcam on",
        f"mineocclude start {layout} {episode_id} {seed} {v} {q} {max_ticks}",
    ]
    # Run-level provenance recorded AT capture (the fields E's registry needs):
    # exact command, UTC start/end, seed, git dirty/sha, and the capturing jar
    # hash. Written even on failure so every attempt is auditable.
    start_utc = _utc_now()
    offset = len(log_text())
    send(command)
    started = wait_for(rf"episode {episode_id} recording started", 30, offset)
    if not started:
        refused = re.search(rf"REFUSED.*{episode_id}", log_text()[offset:])
        _write_provenance(episode_id, command, seed, start_utc, _utc_now(),
                          out_root, layout, accepted=False)
        return {"accepted": False, "episode_id": episode_id,
                "problems": ["episode never started"
                             + (" (start REFUSED)" if refused else "")]}
    duration_cap = (warmup + max_ticks) / 20.0 + 30
    ended = wait_for(rf"episode {episode_id} ended", duration_cap, offset)
    end_utc = _utc_now()
    if not ended:
        _write_provenance(episode_id, command, seed, start_utc, end_utc,
                          out_root, layout, accepted=False)
        return {"accepted": False, "episode_id": episode_id,
                "problems": ["episode did not end within the safety window"]}
    time.sleep(2.0)  # let async PNG writes settle

    summary = process_episode(
        os.path.join(SRV, "mineocclude_out", f"episode_{episode_id}"),
        os.path.join(CLIENT, "mineocclude_client_out", f"episode_{episode_id}"),
        out_root,
    )
    summary["episode_id"] = episode_id
    prov = _write_provenance(episode_id, command, seed, start_utc, end_utc,
                             out_root, layout, accepted=summary.get("accepted"),
                             trajectory_id=summary.get("trajectory_id"))
    summary["provenance"] = prov
    return summary


PLANS = {
    # name -> list of cells (scene, hidden, reveal, impulse_tick, impulse_deg,
    #                        v, q, max_ticks)
    "smoke": [
        dict(scene="normal", hidden=16, reveal=20, impulse_tick=-1,
             impulse_deg=0.0, v=1.0, q=0.05, max_ticks=400),
        dict(scene="normal", hidden=4, reveal=20, impulse_tick=-1,
             impulse_deg=0.0, v=1.0, q=0.02, max_ticks=400),
        dict(scene="normal", hidden=0, reveal=0, impulse_tick=30,
             impulse_deg=20.0, v=1.0, q=0.05, max_ticks=60),
    ],
    # C6B shape: ten varied pilots spanning all six layouts, both speeds,
    # both q levels, and short/long hidden durations, each with a reveal
    # window. Order interleaves conditions so collection order does not
    # align with any factor.
    "pilots10": [
        dict(layout="layout_06", scene="normal", hidden=4, reveal=20,
             impulse_tick=-1, impulse_deg=0.0, v=1.0, q=0.02, max_ticks=500),
        dict(layout="layout_03", scene="normal", hidden=16, reveal=20,
             impulse_tick=-1, impulse_deg=0.0, v=2.0, q=0.20, max_ticks=500),
        dict(layout="layout_01", scene="normal", hidden=16, reveal=20,
             impulse_tick=-1, impulse_deg=0.0, v=1.0, q=0.20, max_ticks=500),
        dict(layout="layout_04", scene="normal", hidden=4, reveal=20,
             impulse_tick=-1, impulse_deg=0.0, v=2.0, q=0.02, max_ticks=500),
        dict(layout="layout_02", scene="normal", hidden=16, reveal=20,
             impulse_tick=-1, impulse_deg=0.0, v=2.0, q=0.02, max_ticks=500),
        dict(layout="layout_05", scene="normal", hidden=4, reveal=20,
             impulse_tick=-1, impulse_deg=0.0, v=1.0, q=0.20, max_ticks=500),
        dict(layout="layout_03", scene="normal", hidden=4, reveal=20,
             impulse_tick=-1, impulse_deg=0.0, v=1.0, q=0.02, max_ticks=500),
        dict(layout="layout_06", scene="normal", hidden=16, reveal=20,
             impulse_tick=-1, impulse_deg=0.0, v=2.0, q=0.20, max_ticks=500),
        dict(layout="layout_04", scene="normal", hidden=16, reveal=20,
             impulse_tick=-1, impulse_deg=0.0, v=1.0, q=0.02, max_ticks=500),
        dict(layout="layout_01", scene="normal", hidden=4, reveal=20,
             impulse_tick=-1, impulse_deg=0.0, v=2.0, q=0.20, max_ticks=500),
    ],
    # C1.4 runtime evidence: the same layouts support both controls with
    # only the intended difference (wall removed / sheep absent).
    "controls": [
        dict(layout="layout_02", scene="nowall", hidden=0, reveal=0,
             impulse_tick=-1, impulse_deg=0.0, v=1.0, q=0.05, max_ticks=200),
        dict(layout="layout_05", scene="nosheep", hidden=0, reveal=0,
             impulse_tick=-1, impulse_deg=0.0, v=1.0, q=0.05, max_ticks=200),
    ],
    "impulse3": [
        dict(scene="normal", hidden=0, reveal=0, impulse_tick=t,
             impulse_deg=20.0, v=1.0, q=0.05, max_ticks=60)
        for t in (20, 30, 40)
    ],
}


def load_production_plan() -> list:
    """Build the driver plan from the frozen 66-cell MVP matrix
    (configs/collection/mvp_matrix.csv). Controlled duration: reveal=0 so the
    mod stops at the hidden-frame target (core hidden={4,16}, sentinel=24;
    controls have no hidden phase). Scenes: core/sentinel=normal,
    nowall/nosheep as named."""
    import csv
    cells = []
    matrix = os.path.join(REPO, "configs", "collection", "mvp_matrix.csv")
    with open(matrix, newline="") as handle:
        for row in sorted(csv.DictReader(handle),
                          key=lambda r: int(r["collection_order"])):
            scene = {"core": "normal", "sentinel": "normal",
                     "nowall": "nowall", "nosheep": "nosheep"}[row["set"]]
            cells.append(dict(
                layout=row["layout_id"], scene=scene,
                hidden=int(float(row["hidden_frames"])), reveal=0,
                impulse_tick=-1, impulse_deg=0.0,
                v=float(row["v"]), q=float(row["q"]),
                max_ticks=int(float(row["max_ticks"]))))
    return cells


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", default="smoke")  # named PLANS or "production"
    parser.add_argument("--base-id", type=int, default=9300,
                        help="first episode id; attempts count upward")
    parser.add_argument("--out", default=os.path.join(REPO, "data", "autonomous"))
    parser.add_argument("--retries", type=int, default=2)
    args = parser.parse_args()

    if args.plan == "production":
        PLANS["production"] = load_production_plan()
    if not client_connected():
        print("ABORT: no client is connected to the server. "
              "Launch the MineOcclude installation and join localhost first.")
        return 2

    os.makedirs(args.out, exist_ok=True)
    next_id = args.base_id

    # ---- Session calibration (C3.6/C4.7): measure the client/server tick
    # phase with a scripted impulse and zero the action-pairing shift. The
    # phase is fixed per connection, so one calibration covers the session.
    calibration_cell = dict(scene="normal", hidden=0, reveal=0,
                            impulse_tick=30, impulse_deg=20.0,
                            v=1.0, q=0.05, max_ticks=60)
    shift = 0
    calibrated = False
    for round_index in range(4):
        send([f"mineocclude pairshift {shift}"])
        episode_id = next_id
        next_id += 1
        print(f"[calibration] round {round_index + 1}: shift={shift} "
              f"episode {episode_id}")
        summary = run_episode(episode_id, warmup=60, out_root=args.out,
                              **calibration_cell)
        offset = summary.get("impulse_offset")
        print(f"  -> accepted={summary.get('accepted')} offset={offset}")
        if summary.get("accepted") and offset == 0:
            calibrated = True
            break
        if offset is None:
            print("  calibration episode failed structurally: "
                  f"{summary.get('problems')}")
            continue
        if abs(int(offset)) > 2:
            print(f"  implausible measured offset {offset}; treating as a "
                  "measurement failure, not calibration signal")
            continue
        shift += int(offset)
        if abs(shift) > 2:
            print(f"  shift {shift} outside the sane range; resetting to 0")
            shift = 0
    if not calibrated:
        print("ABORT: pairing calibration did not converge; see the ledger.")
        return 3
    print(f"[calibration] converged: pairing shift = {shift}\n")
    ledger = []
    for index, cell in enumerate(PLANS[args.plan]):
        accepted = None
        attempts = []
        for attempt in range(1 + args.retries):
            episode_id = next_id
            next_id += 1
            print(f"[cell {index}] attempt {attempt + 1}: episode {episode_id} "
                  f"{ {k: v for k, v in cell.items()} }")
            summary = run_episode(episode_id, warmup=60, out_root=args.out,
                                  **cell)
            attempts.append(summary)
            status = "ACCEPTED" if summary.get("accepted") else "excluded"
            print(f"  -> {status}"
                  + ("" if summary.get("accepted")
                     else f": {summary.get('problems')}"))
            if summary.get("accepted"):
                accepted = summary
                break
            time.sleep(2.0)
        ledger.append({"cell": cell, "attempts": attempts,
                       "accepted_episode": (accepted or {}).get("episode_id")})

    report_path = os.path.join(args.out, f"pilot_{args.plan}_ledger.json")
    with open(report_path, "w") as handle:
        json.dump(ledger, handle, indent=2, default=str)
    n_ok = sum(1 for entry in ledger if entry["accepted_episode"] is not None)
    print(f"\n{n_ok}/{len(ledger)} cells accepted -> {report_path}")
    return 0 if n_ok == len(ledger) else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Strict tick/frame/action equality join -> frame_map (Person C, C4.1-C4.3).

Fuses the capture channels of one real episode into a single per-frame table,
enforcing the frozen model-input contract with NO repair:

  server_state.jsonl   (authoritative, server)   one row per accepted tick
  raw_actions.jsonl    (client)                  one full action per frame
  client_tick.jsonl    (client)                  capture diagnostics + join key
  frames/*.png         (client)                  one rendered frame per tick

Guarantees enforced (any failure -> the episode is REJECTED, not fixed):

  * N_state == N_raw_action == N_client_tick == N_frames  (C4.3 cardinality)
  * server_tick consecutive from 0 in server_state and client_tick
  * render_frame_idx / action_idx consecutive from 0
  * no duplicate identity in any channel
  * a single episode_id across every channel (no mixed episodes)
  * exact one-to-one equality join on the identity fields (C4.2); no
    nearest-time matching anywhere
  * every client_tick.frame_path exists on disk

``model_frame_idx`` is assigned only after the exact source identity is proven
(C4.2). The join is order-independent: channels are sorted by their explicit
identity fields before comparison, never trusted in file order.

Identity note: the capture mod records ``episode_id`` as an integer. The
canonical downstream string identity is ``str(episode_id)`` and the derived
``trajectory_id`` is ``"<layout_id>_ep<episode_id>"``. This deterministic
mapping is declared here once; nothing downstream re-derives identity from
paths or filenames.
"""
from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class AlignReport:
    """Machine-readable outcome of one strict alignment attempt."""

    accepted: bool = False
    n_state: int = 0
    n_action: int = 0
    n_tick: int = 0
    n_frame: int = 0
    problems: list[str] = field(default_factory=list)

    def fail(self, msg: str) -> None:
        self.problems.append(msg)
        self.accepted = False


def _read_jsonl(path: str) -> pd.DataFrame:
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    return pd.read_json(path, lines=True)


def _consecutive_from_zero(series: pd.Series) -> bool:
    return list(series) == list(range(len(series)))


def _first_mismatch(series: pd.Series) -> str:
    """Locate the first identity gap for a concrete C4.3 diagnostic."""
    values = list(series)
    for index, value in enumerate(values):
        if value != index:
            lo = max(0, index - 2)
            hi = min(len(values), index + 3)
            return (
                f"first mismatch at position {index}: expected {index}, "
                f"found {value}; neighborhood {values[lo:hi]}"
            )
    return "no mismatch"


def align_episode(
    server_dir: str, client_dir: str
) -> tuple[pd.DataFrame | None, AlignReport]:
    """Join one episode. Returns ``(frame_map, report)``; frame_map is ``None``
    when the episode is rejected."""
    report = AlignReport()

    try:
        state = _read_jsonl(os.path.join(server_dir, "server_state.jsonl"))
        actions = _read_jsonl(os.path.join(client_dir, "raw_actions.jsonl"))
        ticks = _read_jsonl(os.path.join(client_dir, "client_tick.jsonl"))
    except (FileNotFoundError, ValueError) as error:
        report.fail(f"unreadable source: {error}")
        return None, report
    frames = sorted(glob.glob(os.path.join(client_dir, "frames", "*.png")))

    report.n_state, report.n_action = len(state), len(actions)
    report.n_tick, report.n_frame = len(ticks), len(frames)
    report.accepted = True

    # 0. Required identity fields per channel (C4.1: validate before joining).
    for name, frame_df, required in (
        ("server_state", state, ("episode_id", "server_tick")),
        ("raw_actions", actions, ("episode_id", "server_tick",
                                  "render_frame_idx", "action_idx")),
        ("client_tick", ticks, ("episode_id", "server_tick",
                                "render_frame_idx", "frame_path")),
    ):
        missing = [column for column in required if column not in frame_df.columns]
        if missing:
            report.fail(f"{name} is missing identity columns: {missing}")
    if not report.accepted:
        return None, report

    # 1. Single episode identity across every channel (mixed_episode_id).
    episode_values = (
        set(state["episode_id"].unique())
        | set(actions["episode_id"].unique())
        | set(ticks["episode_id"].unique())
    )
    if len(episode_values) != 1:
        report.fail(f"mixed episode ids across channels: {sorted(episode_values)}")
        return None, report

    # 2. Cardinality (C4.3).
    if not (report.n_state == report.n_action == report.n_tick == report.n_frame):
        report.fail(
            f"cardinality mismatch: state={report.n_state} "
            f"action={report.n_action} tick={report.n_tick} "
            f"frame={report.n_frame}"
        )

    # 3. Duplicate identities (duplicate_state / duplicate_frame).
    if state["server_tick"].duplicated().any():
        report.fail("server_state contains a duplicate server_tick")
    if ticks["render_frame_idx"].duplicated().any():
        report.fail("client_tick contains a duplicate render_frame_idx")
    if actions["action_idx"].duplicated().any():
        report.fail("raw_actions contains a duplicate action_idx")

    # 4. Consecutive ticks / indices, sorted by explicit identity (never file
    #    order).
    state = state.sort_values("server_tick").reset_index(drop=True)
    ticks = ticks.sort_values("render_frame_idx").reset_index(drop=True)
    actions = actions.sort_values("render_frame_idx").reset_index(drop=True)
    if not _consecutive_from_zero(state["server_tick"]):
        report.fail(
            "server_state.server_tick is not consecutive from 0; "
            + _first_mismatch(state["server_tick"])
        )
    if not _consecutive_from_zero(ticks["server_tick"]):
        report.fail(
            "client_tick.server_tick is not consecutive from 0; "
            + _first_mismatch(ticks["server_tick"])
        )
    if not _consecutive_from_zero(actions["render_frame_idx"]):
        report.fail(
            "raw_actions.render_frame_idx is not consecutive from 0; "
            + _first_mismatch(actions["render_frame_idx"])
        )
    if not _consecutive_from_zero(actions["action_idx"]):
        report.fail(
            "raw_actions.action_idx is not consecutive from 0; "
            + _first_mismatch(actions["action_idx"])
        )

    # 5. Frame files referenced by client_tick must exist.
    for _, row in ticks.iterrows():
        frame_path = os.path.join(client_dir, str(row["frame_path"]))
        if not os.path.isfile(frame_path):
            report.fail(
                f"client_tick references missing frame: {row['frame_path']}"
            )
            break

    if not report.accepted:
        return None, report

    # 6. Exact one-to-one equality join (C4.2). client_tick + raw_actions on
    #    (episode_id, server_tick, render_frame_idx); then to server_state on
    #    (episode_id, server_tick). validate= makes a multiple match an error.
    try:
        joined = ticks.merge(
            actions,
            on=["episode_id", "server_tick", "render_frame_idx"],
            how="inner",
            validate="one_to_one",
            suffixes=("_tick", "_act"),
        )
    except pd.errors.MergeError as error:
        report.fail(f"client_tick<->raw_actions join is not one-to-one: {error}")
        return None, report
    if len(joined) != report.n_frame:
        report.fail(
            f"client_tick<->raw_actions join dropped rows: "
            f"{len(joined)} of {report.n_frame}"
        )
        return None, report

    try:
        frame_map = joined.merge(
            state,
            on=["episode_id", "server_tick"],
            how="inner",
            validate="one_to_one",
        )
    except pd.errors.MergeError as error:
        report.fail(f"frame<->state join is not one-to-one: {error}")
        return None, report
    if len(frame_map) != report.n_frame:
        report.fail(
            f"frame<->state join dropped rows: {len(frame_map)} of {report.n_frame}"
        )
        return None, report

    # 7. Identity projections: model_frame_idx is assigned only now, after the
    #    exact join has proven source identity (C4.2).
    frame_map = frame_map.sort_values("render_frame_idx").reset_index(drop=True)
    frame_map["model_frame_idx"] = frame_map["render_frame_idx"]
    frame_map["trajectory_id"] = (
        frame_map["layout_id"].astype(str)
        + "_ep"
        + frame_map["episode_id"].astype(str)
    )
    # Absolute frame path for downstream loaders; the path is provenance, not
    # identity.
    frame_map["frame_abspath"] = frame_map["frame_path"].apply(
        lambda p: os.path.abspath(os.path.join(client_dir, str(p)))
    )

    report.accepted = True
    return frame_map, report

"""Tests for the immutable Regime A noise schedule (C2.4 support)."""

import json
import math

import pytest

from mineocclude.data.noise_schedule import (
    CONSUMPTION_ABS_TOL,
    generate_noise_schedule,
    load_schedule,
    schedule_hash,
    serialize_schedule,
    validate_schedule_invariants,
    verify_consumption,
    write_schedule,
)


def test_generation_is_deterministic_and_scaled():
    a = generate_noise_schedule(seed=1234, n_draws=16, q=0.2)
    b = generate_noise_schedule(seed=1234, n_draws=16, q=0.2)
    assert [r.noise_draw for r in a.rows] == [r.noise_draw for r in b.rows]
    assert a.n_draws == 16
    std = math.sqrt(0.2 * 0.05)
    for row in a.rows:
        assert row.noise_std_blocks == pytest.approx(std, abs=0)
        assert row.noise_draw == pytest.approx(
            row.standard_normal_draw * std, abs=1e-15
        )
    assert validate_schedule_invariants(a) == []


def test_different_seeds_differ():
    a = generate_noise_schedule(seed=1, n_draws=8, q=0.02)
    b = generate_noise_schedule(seed=2, n_draws=8, q=0.02)
    assert [r.noise_draw for r in a.rows] != [r.noise_draw for r in b.rows]


def test_serialize_hash_roundtrip(tmp_path):
    schedule = generate_noise_schedule(seed=99, n_draws=4, q=0.05)
    digest = schedule_hash(schedule)
    path = tmp_path / "schedule.jsonl"
    written = write_schedule(schedule, str(path))
    assert written == digest
    loaded = load_schedule(str(path))
    assert loaded.seed == schedule.seed
    assert [r.noise_draw for r in loaded.rows] == [
        r.noise_draw for r in schedule.rows
    ]
    assert schedule_hash(loaded) == digest


def test_load_rejects_tampered_draw(tmp_path):
    schedule = generate_noise_schedule(seed=7, n_draws=3, q=0.05)
    lines = serialize_schedule(schedule).decode().splitlines()
    record = json.loads(lines[2])
    record["noise_draw"] = record["noise_draw"] + 1.0
    lines[2] = json.dumps(record, sort_keys=True)
    path = tmp_path / "bad.jsonl"
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError, match="noise_draw"):
        load_schedule(str(path))


def test_load_rejects_skipped_draw(tmp_path):
    schedule = generate_noise_schedule(seed=7, n_draws=3, q=0.05)
    lines = serialize_schedule(schedule).decode().splitlines()
    del lines[2]  # drop draw_idx 1
    path = tmp_path / "bad.jsonl"
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError):
        load_schedule(str(path))


def test_invalid_parameters_rejected():
    with pytest.raises(ValueError):
        generate_noise_schedule(seed=1, n_draws=0, q=0.1)
    with pytest.raises(ValueError):
        generate_noise_schedule(seed=1, n_draws=4, q=-0.1)


def test_verify_consumption_accepts_exact_replay():
    schedule = generate_noise_schedule(seed=5, n_draws=5, q=0.2)
    consumed = [
        {"draw_idx": r.draw_idx, "noise_draw": r.noise_draw}
        for r in schedule.rows
    ]
    assert verify_consumption(schedule, consumed) == []


def test_verify_consumption_rejects_reorder_and_mismatch():
    schedule = generate_noise_schedule(seed=5, n_draws=5, q=0.2)
    consumed = [
        {"draw_idx": r.draw_idx, "noise_draw": r.noise_draw}
        for r in schedule.rows
    ]
    swapped = [consumed[1], consumed[0]] + consumed[2:]
    assert any("order violation" in p for p in verify_consumption(schedule, swapped))

    tampered = [dict(row) for row in consumed]
    tampered[3]["noise_draw"] += 10 * CONSUMPTION_ABS_TOL
    assert any("does not" in p for p in verify_consumption(schedule, tampered))

    assert any(
        "consumed 4 draws" in p
        for p in verify_consumption(schedule, consumed[:-1])
    )

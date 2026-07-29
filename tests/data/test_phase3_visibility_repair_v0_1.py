"""Focused tests for the Person C Phase 3 Step 3.3 generation-input package.

Builds the package once into a temp dir (happy path) and asserts determinism,
structure, context values/types, key-set equality, forbidden-field absence, and
existing-authority immutability. Fail-closed branches are exercised by injecting
bad inputs into the generator's frame-map / provenance / context sources.
"""
import io
import json
import os
import subprocess
import sys
import tarfile

import pandas as pd
import pytest
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import build_phase3_visibility_repair_v0_1 as mod

SOURCE_ROOT = os.path.expanduser("~/mineocclude-client/mineocclude_client_out")
GVR = os.path.join(ROOT, mod.GVR_REL)


def _loadj(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _readb(path):
    with open(path, "rb") as f:
        return f.read()


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("pkg")
    files = mod.generate(SOURCE_ROOT, out_dir=str(out))
    return str(out), files


def _rows(pkg, name):
    with open(os.path.join(pkg, name), encoding="utf-8") as f:
        return [json.loads(l) for l in f]


# ---- determinism ----------------------------------------------------------
def test_deterministic_regeneration_byte_identical():
    a = mod.generate(SOURCE_ROOT, out_dir=None)
    b = mod.generate(SOURCE_ROOT, out_dir=None)
    assert a.keys() == b.keys()
    for k in a:
        assert a[k] == b[k], k


def test_deterministic_archive_helper_and_fixed_metadata():
    members = [("frames_640x360/000000.png", b"\x89PNG_a"),
               ("frames_640x360/000001.png", b"\x89PNG_b")]
    a1 = mod.build_deterministic_archive(members)
    a2 = mod.build_deterministic_archive(members)
    assert a1 == a2
    # gzip: no embedded filename (FNAME bit clear), mtime zero
    assert not (a1[3] & 0x08)
    assert a1[4:8] == b"\x00\x00\x00\x00"
    with tarfile.open(fileobj=io.BytesIO(a1), mode="r:gz") as t:
        for ti in t.getmembers():
            assert ti.mtime == 0 and ti.uid == 0 and ti.gid == 0
            assert ti.uname == "" and ti.gname == ""


# ---- structure ------------------------------------------------------------
def test_exactly_56_archives_and_1850_members(built):
    pkg, _ = built
    ai = _loadj(os.path.join(pkg, "archive_inventory.json"))
    assert ai["archive_count"] == 56
    assert ai["member_count"] == 1850
    assert ai["total_unique_primary_keys"] == 1850
    assert ai["missing_members"] == 0 and ai["extra_members"] == 0
    assert ai["duplicate_identity_members"] == 0 and ai["member_hash_mismatches"] == 0
    archives = [f for f in os.listdir(os.path.join(pkg, "canonical_frames"))
                if f.endswith(".tar.gz")]
    assert len(archives) == 56


def test_generation_and_identity_row_counts(built):
    pkg, _ = built
    assert len(_rows(pkg, "generation_input_manifest.jsonl")) == 1850
    assert len(_rows(pkg, "derived_identity_manifest.jsonl")) == 1850


def test_member_bytes_reproduce_declared_hashes_and_dims(built):
    pkg, _ = built
    gen = _rows(pkg, "generation_input_manifest.jsonl")
    by_arch = {}
    for r in gen:
        by_arch.setdefault(r["archive_path"], []).append(r)
    checked = 0
    for arch, grp in by_arch.items():
        with tarfile.open(os.path.join(pkg, arch), "r:gz") as t:
            got = {ti.name: t.extractfile(ti).read() for ti in t.getmembers()}
        for r in grp:
            b = got[r["archive_member_path"]]
            assert mod.sha256_bytes(b) == r["frame_640_sha256"]
            with Image.open(io.BytesIO(b)) as im:
                assert im.size == (640, 360)
            checked += 1
    assert checked == 1850


def test_archive_member_paths_relative_sorted_unique(built):
    pkg, _ = built
    gen = _rows(pkg, "generation_input_manifest.jsonl")
    by_arch = {}
    for r in gen:
        by_arch.setdefault(r["archive_path"], []).append(r)
    seen = set()
    for arch in by_arch:
        with tarfile.open(os.path.join(pkg, arch), "r:gz") as t:
            names = [ti.name for ti in t.getmembers()]
        assert all(not n.startswith("/") and n.startswith("frames_640x360/") for n in names)
        assert names == sorted(names)
        assert len(names) == len(set(names))
        for n in names:
            key = (arch, n)
            assert key not in seen
            seen.add(key)


# ---- key-set equality -----------------------------------------------------
def test_exact_key_set_equality_all_sources(built):
    pkg, _ = built
    recs = [json.loads(l) for l in mod.read_lines(GVR)]
    rk = {(r["trajectory_id"], r["model_frame_idx"]) for r in recs}
    gk = {(r["trajectory_id"], r["model_frame_idx"]) for r in _rows(pkg, "generation_input_manifest.jsonl")}
    ik = {(r["trajectory_id"], r["model_frame_idx"]) for r in _rows(pkg, "derived_identity_manifest.jsonl")}
    prov = _loadj(os.path.join(ROOT, mod.PROV_REL))["source_frame_maps"]
    mk = set()
    for m in prov:
        df = pd.read_parquet(os.path.join(ROOT, m), columns=["trajectory_id", "model_frame_idx"])
        mk |= {(t, int(i)) for t, i in zip(df["trajectory_id"], df["model_frame_idx"])}
    assert rk == gk == ik == mk
    assert len(rk) == 1850


# ---- context --------------------------------------------------------------
def test_required_context_values_and_string_types(built):
    pkg, _ = built
    for r in _rows(pkg, "generation_input_manifest.jsonl"):
        assert r["resolution"] == "640x360" and isinstance(r["resolution"], str)
        assert r["coordinate_convention"] == "pixel_center_xy_zero_based"
        assert isinstance(r["coordinate_convention"], str)


def test_context_derivation_authority(built):
    pkg, _ = built
    c = _loadj(os.path.join(pkg, "context_field_derivation_authority.json"))
    assert c["resolution"]["source"] == "source_frame_map.detector_frame_space"
    assert c["resolution"]["emitted_value"] == "640x360"
    assert c["resolution"]["emitted_json_type"] == "string"
    assert c["coordinate_convention"]["source"].endswith("::image_coordinate_convention")
    assert c["coordinate_convention"]["emitted_value"] == "pixel_center_xy_zero_based"
    assert c["no_competing_source_value_found"] is True
    assert c["person_e_may_copy_emitted_values_but_may_not_translate_or_substitute"] is True


# ---- forbidden data -------------------------------------------------------
def test_forbidden_fields_absent_from_generation_rows(built):
    pkg, _ = built
    forbidden = {"empirical_magenta_visible", "visible_flag", "geometric_visible",
                 "empirical_visible", "blob_area", "blob_cx", "blob_cy",
                 "visibility_quarantine", "quarantine_category", "detector_id"}
    for r in _rows(pkg, "generation_input_manifest.jsonl"):
        assert not (set(r) & forbidden)
    for r in _rows(pkg, "derived_identity_manifest.jsonl"):
        assert not (set(r) & forbidden)


# ---- deterministic formatting + schema ids --------------------------------
def test_json_formatting_and_schema_version(built):
    pkg, files = built
    for rel in files:
        if not rel.endswith((".json", ".jsonl")):
            continue  # binary archives are not text-formatted
        p = os.path.join(pkg, rel)
        raw = _readb(p)
        assert raw[:3] != b"\xef\xbb\xbf"  # no BOM
        assert raw.endswith(b"\n")  # final newline
        if rel.endswith(".json"):
            obj = json.loads(raw)
            assert raw == (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
            assert obj.get("schema_version") == "1.0"
            assert mod.SCHEMA_ID in json.dumps(obj)
        elif rel.endswith(".jsonl"):
            for line in raw.decode().splitlines():
                o = json.loads(line)
                assert line == json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def test_all_required_schema_files_present(built):
    pkg, _ = built
    need = {"generation_input_manifest", "derived_identity_manifest",
            "context_field_derivation_authority", "identity_authority",
            "archive_inventory", "provenance_index", "validation_receipt", "phase3_status"}
    have = {f.replace(".schema.json", "") for f in os.listdir(os.path.join(pkg, "schemas"))}
    assert need <= have


# ---- existing authority immutability --------------------------------------
def test_existing_authority_files_byte_identical_to_head():
    for rel in (mod.GVR_REL, mod.PROV_REL, mod.HOMOG_REL,
                mod.IMPORT_CONTRACT_REL, mod.FINAL_INTERFACE_REL,
                "data/autonomous/layout_01_ep10000/frame_map.parquet"):
        committed = subprocess.check_output(["git", "-C", ROOT, "show", f"HEAD:{rel}"])
        with open(os.path.join(ROOT, rel), "rb") as f:
            assert f.read() == committed, rel


# ---- validate-only mode ---------------------------------------------------
def test_validate_only_passes(built):
    pkg, _ = built
    mod.validate(SOURCE_ROOT, pkg)  # raises on failure


def test_validate_detects_tampered_archive(built, tmp_path):
    pkg, _ = built
    import shutil
    clone = tmp_path / "clone"
    shutil.copytree(pkg, clone)
    victim = next(clone.glob("canonical_frames/*.tar.gz"))
    data = bytearray(victim.read_bytes())
    data[-1] ^= 0xFF
    victim.write_bytes(bytes(data))
    with pytest.raises(mod.FailClosed):
        mod.validate(SOURCE_ROOT, str(clone))


def test_validate_detects_missing_and_extra_file(built, tmp_path):
    import shutil
    pkg, _ = built
    clone = tmp_path / "c2"
    shutil.copytree(pkg, clone)
    (clone / "phase3_status.json").unlink()
    with pytest.raises(mod.FailClosed):
        mod.validate(SOURCE_ROOT, str(clone))
    shutil.copytree(pkg, tmp_path / "c3")
    (tmp_path / "c3" / "UNEXPECTED.json").write_text("{}\n")
    with pytest.raises(mod.FailClosed):
        mod.validate(SOURCE_ROOT, str(tmp_path / "c3"))


# ---- fail-closed source guards (inject bad frame-map / provenance / context)
def _patch_first_map(monkeypatch, mutate):
    real = mod.pd.read_parquet
    state = {"done": False}

    def fake(path, columns=None):
        df = real(path, columns=columns)
        if not state["done"]:
            state["done"] = True
            df = mutate(df.copy())
        return df
    monkeypatch.setattr(mod.pd, "read_parquet", fake)


def test_wrong_source_resolution_fails_closed(monkeypatch):
    def mut(df):
        df.loc[df.index[0], "detector_frame_space"] = "1280x720"
        return df
    _patch_first_map(monkeypatch, mut)
    with pytest.raises(mod.FailClosed):
        mod.gather(SOURCE_ROOT)


def test_wrong_coordinate_convention_fails_closed(monkeypatch, tmp_path):
    bad = tmp_path / "homog.json"
    h = _loadj(os.path.join(ROOT, mod.HOMOG_REL))
    h["image_coordinate_convention"] = "top_left_origin"
    bad.write_text(json.dumps(h))
    monkeypatch.setattr(mod, "HOMOG_REL", os.path.relpath(str(bad), ROOT))
    with pytest.raises(mod.FailClosed):
        mod.gather(SOURCE_ROOT)


def test_wrong_source_png_hash_fails_closed(monkeypatch):
    def mut(df):
        df.loc[df.index[0], "frame_640_sha256"] = "0" * 64
        return df
    _patch_first_map(monkeypatch, mut)
    with pytest.raises(mod.FailClosed):
        mod.gather(SOURCE_ROOT)


def test_missing_source_png_fails_closed(monkeypatch):
    def mut(df):
        df.loc[df.index[0], "frame_640_path"] = "/nonexistent/does_not_exist.png"
        return df
    _patch_first_map(monkeypatch, mut)
    # empty source root forces the fallback to the (missing) declared path
    with pytest.raises(mod.FailClosed):
        mod.gather("/tmp/definitely_no_such_capture_root_xyz")


def test_duplicate_identity_fails_closed(monkeypatch):
    def mut(df):
        return pd.concat([df, df.iloc[[0]]], ignore_index=True)
    _patch_first_map(monkeypatch, mut)
    with pytest.raises(mod.FailClosed):
        mod.gather(SOURCE_ROOT)


def test_extra_identity_key_fails_closed(monkeypatch):
    def mut(df):
        row = df.iloc[[0]].copy()
        row.loc[row.index[0], "model_frame_idx"] = 999999
        return pd.concat([df, row], ignore_index=True)
    _patch_first_map(monkeypatch, mut)
    with pytest.raises(mod.FailClosed):
        mod.gather(SOURCE_ROOT)


def test_missing_identity_key_fails_closed(monkeypatch):
    def mut(df):
        return df.iloc[1:].reset_index(drop=True)
    _patch_first_map(monkeypatch, mut)
    with pytest.raises(mod.FailClosed):
        mod.gather(SOURCE_ROOT)


def test_wrong_frame_map_hash_fails_closed(monkeypatch):
    real = mod.load_provenance

    def fake():
        p = dict(real())
        first = min(p)
        p[first] = "f" * 64
        return p
    monkeypatch.setattr(mod, "load_provenance", fake)
    with pytest.raises(mod.FailClosed):
        mod.gather(SOURCE_ROOT)


def test_geometric_record_sha_change_fails_closed(monkeypatch):
    monkeypatch.setattr(mod, "GEOMETRIC_RECORDS_SHA", "a" * 64)
    with pytest.raises(mod.FailClosed):
        mod.gather(SOURCE_ROOT)


def test_png_decode_failure_and_wrong_dims_fail_closed(monkeypatch, tmp_path):
    # decode failure: point first frame at a non-PNG file
    notpng = tmp_path / "x.png"
    notpng.write_bytes(b"not a png at all")

    def mut(df):
        df.loc[df.index[0], "frame_640_path"] = str(notpng)
        # keep its declared hash consistent so decode (not hash) is the trigger
        df.loc[df.index[0], "frame_640_sha256"] = mod.sha256_file(str(notpng))
        return df
    _patch_first_map(monkeypatch, mut)
    with pytest.raises(mod.FailClosed):
        mod.gather("/tmp/definitely_no_such_capture_root_xyz")


def test_wrong_dimensions_fail_closed(monkeypatch, tmp_path):
    small = tmp_path / "small.png"
    Image.new("RGB", (100, 100)).save(small)

    def mut(df):
        df.loc[df.index[0], "frame_640_path"] = str(small)
        df.loc[df.index[0], "frame_640_sha256"] = mod.sha256_file(str(small))
        return df
    _patch_first_map(monkeypatch, mut)
    with pytest.raises(mod.FailClosed):
        mod.gather("/tmp/definitely_no_such_capture_root_xyz")


def test_u4_source_root_rejected(monkeypatch):
    monkeypatch.setattr(sys, "argv",
                        ["x", "build", "--source-root", "/data/mineocclude_u4/out"])
    assert mod.main() == 2


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

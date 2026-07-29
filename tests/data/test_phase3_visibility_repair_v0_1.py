"""Focused tests for the Person C Phase 3 Step 3.3 generation-input package.

Portable by construction: the generator's expected source-root layout is
reconstructed entirely from the committed canonical archives under
data/handoff_e/phase3_visibility_repair_v0_1/. No external capture directory,
user home, or machine-specific path is referenced. Every generate()/validate()
/gather() call consumes the reconstructed temporary source root; fail-closed
mutations happen only inside pytest temp dirs and never touch the committed
package.
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

PKG = os.path.join(ROOT, mod.PKG_REL)
GVR = os.path.join(ROOT, mod.GVR_REL)


def _loadj(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _readb(path):
    with open(path, "rb") as f:
        return f.read()


def _is_safe_relpath(name: str) -> bool:
    n = name.replace("\\", "/")
    return (bool(n) and not os.path.isabs(name) and not n.startswith("/")
            and ".." not in n.split("/"))


# --------------------------------------------------------------------------- #
# Portable source root: reconstruct <tmp>/episode_<id>/frames_640x360/<idx>.png
# from the committed archives, matching the layout the generator resolves.
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def source_root(tmp_path_factory):
    root = tmp_path_factory.mktemp("canonical_src")
    gen = [json.loads(l) for l in mod.read_lines(os.path.join(PKG, "generation_input_manifest.jsonl"))]
    assert len(gen) == 1850
    by_arch = {}
    for r in gen:
        by_arch.setdefault(r["archive_path"], []).append(r)

    written: set[str] = set()
    identities: set[tuple] = set()
    count = 0
    for arch_rel, rows in by_arch.items():
        assert _is_safe_relpath(arch_rel), arch_rel
        with tarfile.open(os.path.join(PKG, arch_rel), "r:gz") as tar:
            infos = tar.getmembers()
            names = [ti.name for ti in infos]
            assert len(names) == len(set(names))  # each member exactly once
            by_name = {ti.name: ti for ti in infos}
            for r in rows:
                mp = r["archive_member_path"]
                assert _is_safe_relpath(mp), mp
                ti = by_name.get(mp)
                assert ti is not None, mp
                extracted = tar.extractfile(ti)
                assert extracted is not None
                data = extracted.read()  # explicit per-member read, no extractall
                assert mod.sha256_bytes(data) == r["frame_640_sha256"]
                assert len(data) == r["frame_size_bytes"]
                episode = mod._episode_of(r["trajectory_id"])
                base = os.path.basename(mp)
                assert base == f"{r['render_frame_idx']:06d}.png"
                out = root / f"episode_{episode}" / "frames_640x360" / base
                assert str(out) not in written  # no duplicate output paths
                written.add(str(out))
                identities.add((r["trajectory_id"], r["model_frame_idx"]))
                out.parent.mkdir(parents=True, exist_ok=True)
                with open(out, "wb") as f:
                    f.write(data)
                count += 1

    all_pngs = list(root.rglob("*.png"))
    assert count == 1850
    assert len(all_pngs) == 1850  # exactly 1,850 files, no extras
    assert len(written) == 1850   # zero duplicate output paths
    assert len(identities) == 1850  # exactly 1,850 manifest identities
    return str(root)


@pytest.fixture(scope="module")
def built(source_root, tmp_path_factory):
    out = tmp_path_factory.mktemp("pkg")
    files = mod.generate(source_root, out_dir=str(out))
    return str(out), files


def _rows(pkg, name):
    with open(os.path.join(pkg, name), encoding="utf-8") as f:
        return [json.loads(l) for l in f]


# ---- determinism ----------------------------------------------------------
def test_deterministic_regeneration_byte_identical(source_root):
    a = mod.generate(source_root, out_dir=None)
    b = mod.generate(source_root, out_dir=None)
    assert a.keys() == b.keys()
    for k in a:
        assert a[k] == b[k], k


def test_deterministic_archive_helper_and_fixed_metadata():
    members = [("frames_640x360/000000.png", b"\x89PNG_a"),
               ("frames_640x360/000001.png", b"\x89PNG_b")]
    a1 = mod.build_deterministic_archive(members)
    a2 = mod.build_deterministic_archive(members)
    assert a1 == a2
    assert not (a1[3] & 0x08)  # gzip FNAME bit clear
    assert a1[4:8] == b"\x00\x00\x00\x00"  # gzip mtime zero
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
def test_validate_only_passes(built, source_root):
    pkg, _ = built
    mod.validate(source_root, pkg)  # raises on failure


def test_validate_detects_tampered_archive(built, source_root, tmp_path):
    import shutil
    pkg, _ = built
    clone = tmp_path / "clone"
    shutil.copytree(pkg, clone)
    victim = next(clone.glob("canonical_frames/*.tar.gz"))
    data = bytearray(victim.read_bytes())
    data[-1] ^= 0xFF
    victim.write_bytes(bytes(data))
    with pytest.raises(mod.FailClosed):
        mod.validate(source_root, str(clone))


def test_validate_detects_missing_and_extra_file(built, source_root, tmp_path):
    import shutil
    pkg, _ = built
    clone = tmp_path / "c2"
    shutil.copytree(pkg, clone)
    (clone / "phase3_status.json").unlink()
    with pytest.raises(mod.FailClosed):
        mod.validate(source_root, str(clone))
    shutil.copytree(pkg, tmp_path / "c3")
    (tmp_path / "c3" / "UNEXPECTED.json").write_text("{}\n")
    with pytest.raises(mod.FailClosed):
        mod.validate(source_root, str(tmp_path / "c3"))


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


def test_wrong_source_resolution_fails_closed(monkeypatch, source_root):
    def mut(df):
        df.loc[df.index[0], "detector_frame_space"] = "1280x720"
        return df
    _patch_first_map(monkeypatch, mut)
    with pytest.raises(mod.FailClosed):
        mod.gather(source_root)


def test_wrong_coordinate_convention_fails_closed(monkeypatch, source_root, tmp_path):
    bad = tmp_path / "homog.json"
    h = _loadj(os.path.join(ROOT, mod.HOMOG_REL))
    h["image_coordinate_convention"] = "top_left_origin"
    bad.write_text(json.dumps(h))
    monkeypatch.setattr(mod, "HOMOG_REL", os.path.relpath(str(bad), ROOT))
    with pytest.raises(mod.FailClosed):
        mod.gather(source_root)


def test_wrong_source_png_hash_fails_closed(monkeypatch, source_root):
    def mut(df):
        df.loc[df.index[0], "frame_640_sha256"] = "0" * 64
        return df
    _patch_first_map(monkeypatch, mut)
    with pytest.raises(mod.FailClosed):
        mod.gather(source_root)


def test_missing_source_png_fails_closed(monkeypatch, source_root):
    def mut(df):
        df.loc[df.index[0], "frame_640_path"] = "no_such_frame_deadbeef.png"
        return df
    _patch_first_map(monkeypatch, mut)
    with pytest.raises(mod.FailClosed):
        mod.gather(source_root)


def test_duplicate_identity_fails_closed(monkeypatch, source_root):
    def mut(df):
        return pd.concat([df, df.iloc[[0]]], ignore_index=True)
    _patch_first_map(monkeypatch, mut)
    with pytest.raises(mod.FailClosed):
        mod.gather(source_root)


def test_extra_identity_key_fails_closed(monkeypatch, source_root):
    def mut(df):
        row = df.iloc[[0]].copy()
        row.loc[row.index[0], "model_frame_idx"] = 999999
        return pd.concat([df, row], ignore_index=True)
    _patch_first_map(monkeypatch, mut)
    with pytest.raises(mod.FailClosed):
        mod.gather(source_root)


def test_missing_identity_key_fails_closed(monkeypatch, source_root):
    def mut(df):
        return df.iloc[1:].reset_index(drop=True)
    _patch_first_map(monkeypatch, mut)
    with pytest.raises(mod.FailClosed):
        mod.gather(source_root)


def test_wrong_frame_map_hash_fails_closed(monkeypatch, source_root):
    real = mod.load_provenance

    def fake():
        p = dict(real())
        p[min(p)] = "f" * 64
        return p
    monkeypatch.setattr(mod, "load_provenance", fake)
    with pytest.raises(mod.FailClosed):
        mod.gather(source_root)


def test_geometric_record_sha_change_fails_closed(monkeypatch, source_root):
    monkeypatch.setattr(mod, "GEOMETRIC_RECORDS_SHA", "a" * 64)
    with pytest.raises(mod.FailClosed):
        mod.gather(source_root)


def test_png_decode_failure_fails_closed(monkeypatch, source_root, tmp_path):
    notpng = tmp_path / "x.png"
    notpng.write_bytes(b"not a png at all")

    def mut(df):
        df.loc[df.index[0], "frame_640_path"] = str(notpng)
        df.loc[df.index[0], "frame_640_sha256"] = mod.sha256_file(str(notpng))
        return df
    _patch_first_map(monkeypatch, mut)
    with pytest.raises(mod.FailClosed):
        mod.gather(source_root)


def test_wrong_dimensions_fail_closed(monkeypatch, source_root, tmp_path):
    small = tmp_path / "small.png"
    Image.new("RGB", (100, 100)).save(small)

    def mut(df):
        df.loc[df.index[0], "frame_640_path"] = str(small)
        df.loc[df.index[0], "frame_640_sha256"] = mod.sha256_file(str(small))
        return df
    _patch_first_map(monkeypatch, mut)
    with pytest.raises(mod.FailClosed):
        mod.gather(source_root)


def test_u4_source_root_rejected(monkeypatch):
    monkeypatch.setattr(sys, "argv",
                        ["x", "build", "--source-root", "/data/mineocclude_u4/out"])
    assert mod.main() == 2


# ---- portability guard ----------------------------------------------------
def test_module_has_no_machine_specific_source_root():
    """This test module must not reference any machine-specific source root.

    Forbidden substrings are assembled from fragments so this assertion does not
    match itself.
    """
    with open(os.path.abspath(__file__), encoding="utf-8") as f:
        src = f.read()
    forbidden = [
        "C:" + "\\Users" + "\\",          # windows user home
        "/" + "Users" + "/",              # posix user home
        "expand" + "user",                # home-directory expansion helper
        "Path." + "home",                 # pathlib home locator
        "mineocclude_" + "client_out",    # fixed external capture dir
    ]
    for frag in forbidden:
        assert frag not in src, frag


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

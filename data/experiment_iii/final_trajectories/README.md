# MineOcclude — Experiment III-A final trajectory / capture corpus

**These are the ORIGINAL A7 production capture bytes.** Nothing in this dataset was
regenerated, re-rendered, re-encoded, or reconstructed. Every file is byte-identical to what
the A7 production driver wrote during the final Experiment III-A run, and every byte is
verified against the per-capture `durable_receipt.json` files that A7 itself emitted
(authority §8.2). Zero mismatches over 24,500 files.

---

## 1. What this is

The graded-partial-observability production cohort for **Experiment III-A**: 25 trajectory
identities, each captured five times under five frozen occlusion conditions, in a balanced
5×5 Latin-square design.

| Quantity | Value |
|---|---|
| Capture units | **125** (25 identities × 5 conditions) |
| Identities | **25** (`e3_t01` … `e3_t25`) |
| Conditions | **5** (`L0` … `L4`) |
| Frames per capture | **180** |
| Total PNG frames | **22,500** |
| Scored target rows per capture | **19** (context ages 1…19) |
| Total target rows | **2,375** |
| Files | **24,500** (22,500 PNG + 1,250 JSON + 750 JSONL) |
| Bytes | **1,746,151,209** (≈1.63 GiB) |

Capture unit ids are `<identity>__<condition>`, e.g. `e3_t01__L0` … `e3_t25__L4`.

## 2. The five frozen conditions

From the frozen Experiment III authority v1.8, §4.1, confirmed against the per-capture
`condition_receipt.json` of all 125 units:

| ID | Physical condition | Runtime scene | `wall_block_id` | Scientific role |
|---|---|---|---|---|
| `L0` | no blocks in the wall cells | `NO_WALL` | `minecraft:air` | fully visible anchor |
| `L1` | one full-cube stained-glass layer | `NORMAL` | `minecraft:white_stained_glass` | high partial evidence |
| `L2` | one full-cube stained-glass layer | `NORMAL` | `minecraft:light_blue_stained_glass` | medium partial evidence |
| `L3` | one full-cube stained-glass layer | `NORMAL` | `minecraft:brown_stained_glass` | low but measurable partial evidence |
| `L4` | one full-cube stone layer | `NORMAL` | `minecraft:stone` | opaque anchor |

`L1`–`L3` materials were selected by stage P0 from the frozen 12-candidate stained-glass
roster (authority §4.2).

## 3. Provenance — and how "final" was proven

| Identity | Value |
|---|---|
| Authority version | **v1.8** |
| `AUTHORITY_SHA256` | `472eae5eac83a2709808e64aa449a2ffba24a5a12715b4f1645ce88a3094a9f4` |
| `MACHINE_AUTHORITY_SHA256` | `22f236786013b6bf3d0b702523a2990d145d6b4e0bfb0140ddbefc4e5526613b` |
| `PHASE0_DESIGN_SHA256` | `be3ccd97525434659dc39b3be36e6046ceebaeab2a33db81ce18c139e19c8e4c` |
| Final implementation commit | `a91502ce2cd421721f8c638eaeea013a1fcddaf1` |
| Final implementation tree | `3846709e257377bbd8a26aefa10621b77a23ae87` |
| **Final source closure** | `cdee2a8ba0f6093fc6d9c961718adbee5315e71f1c640bbb1570f0e5b3b10dd0` |
| **Final P2 package** | `f0e9d954d187acdf2a479683cde40bd89d4cae5a8fabc6b3cefb010f0f99f7a8` |
| P2 freeze commit | `96a045b` (parent of this branch) |
| Runtime capture root | `data/experiment_iii/production/captures/` |

Run status: **A7 COMPLETE 125/125** (0 errors, 0 retries) · **A8 PASS**, attrition branch
`NORMAL`, `N_complete = 25`, 2,375 analysable target rows, 0 imputed cells, 0 dropped
conditions · **A9–A19 PASS** · **A19 closure `EXPERIMENT_III_COMPLETE = true`**, all 8
closure conditions met, 0 unmet, 0 disclosed limitations.

The receipts that establish all of the above are committed in [`provenance/`](provenance/).

## 4. This is NOT the superseded cohort

An earlier 125-capture cohort exists and is **excluded from this dataset**. It is a different
run under a different implementation, and it must never be substituted for this one:

| | **This dataset (FINAL)** | Superseded predecessor |
|---|---|---|
| P2 package | `f0e9d954…` | `7d94a1c7…` |
| Source closure | `cdee2a8b…` | `f9fba4b5…` |
| Head commit | `a91502c` / `96a045b` | `03a1174f` |
| A9 | PASS | `FAILED_BEFORE_FIRST_FORWARD` (`P1_INCOMPLETE`) |
| Eligibility | final confirmatory analysis | `NOT_ELIGIBLE_FOR_FINAL_CONFIRMATORY_ANALYSIS_AFTER_REFREEZE` |

The predecessor's own supersession record is committed here as
[`provenance/PREDECESSOR_SUPERSESSION_RECORD.json`](provenance/PREDECESSOR_SUPERSESSION_RECORD.json)
for reference; **its capture bytes are not published in this branch or its release.** Under
the frozen reuse policy, `OLD_CAPTURE_REUSE_COUNT` must remain 0 and predecessor captures may
never be grandfathered into the successor P2 cohort.

The discriminator is mechanical, not editorial: every record of
[`provenance/production_capture_ledger.jsonl`](provenance/production_capture_ledger.jsonl)
carries `source_closure = cdee2a8b…`, and
[`provenance/capture_matrix.json`](provenance/capture_matrix.json) binds
`p2_package_sha256 = f0e9d954…` together with that closure at `stage = A7`.

## 5. Layout

```
data/experiment_iii/final_trajectories/
    README.md                  this file
    MANIFEST.json              per-capture dataset manifest (125 entries)
    SHA256SUMS.txt             sha256 of all 24,500 corpus files
    ARCHIVES.json              release-asset index (names, sizes, sha256, URLs)
    verify_corpus.sh           verification helper
    provenance/                A7/A8/A19 receipts, capture matrix, ledger, P2 hash
    captures/
        e3_t01__L0/
            capture_completion.json    frames, target rows, FIR labels, spec hash
            condition_receipt.json     wall block id, observed scene
            camera_receipt.json        camera pose
            target_receipt.json        target placement
            wall_receipt.json          wall geometry
            path_receipt.json          trajectory path
            timing_receipt.json        tick/frame timing
            framebuffer_receipt.json   framebuffer identity
            physical_receipt.json      per-frame physical state
            coordinates.jsonl          per-frame coordinates
            durable_receipt.json       sha256 + size of every file in this unit
            raw/
                frames/000000.png … 000179.png   180 captured frames
                server_state.jsonl     per-tick server state
                client_tick.jsonl      per-tick client state
                actions.jsonl          per-tick actions
                frame_map.jsonl        model-frame ↔ tick mapping
                visibility.jsonl       per-frame visibility record
        e3_t01__L1/ …  e3_t25__L4/     (125 units, identical internal layout)
```

`captures/` here is exactly the runtime `data/experiment_iii/production/captures/` tree.

### Where the bytes live

The 2,000 JSON/JSONL files (≈51 MB) are **committed directly in this branch** — browsable and
diffable on GitHub. The 22,500 PNG frames (≈1.62 GiB) are published as **GitHub release
assets** rather than in Git history, to avoid permanently inflating the repository and to
avoid Git LFS storage/bandwidth quotas on an account this branch's author does not
administer. `SHA256SUMS.txt` covers all 24,500 files either way.

## 6. Getting the full corpus

```bash
git clone --branch data/experiment-iii-final-trajectories \
    https://github.com/atharv-santosh/MineOcclude.git
cd MineOcclude/data/experiment_iii/final_trajectories

# 5 archives, ~319 MiB each, ~1.56 GiB total
gh release download exp3a-final-trajectories-v1 -p '*.tar.gz' -D .
# ...or without gh, for each asset name in ARCHIVES.json:
#   curl -L -H "Authorization: token $GITHUB_TOKEN" \
#        -H "Accept: application/octet-stream" -o "$NAME" \
#        "https://api.github.com/repos/atharv-santosh/MineOcclude/releases/assets/$ASSET_ID"

for f in mineocclude_exp3a_final_trajectories_part*.tar.gz; do tar -xzf "$f"; done
./verify_corpus.sh          # expects: FULL_CORPUS_VERIFY=OK (24500 files)
```

The repository is **private**, so both the clone and the release download need a GitHub token
with `repo` scope (or a browser session with access).

Without the archives you can still verify what the branch carries:

```bash
./verify_corpus.sh --metadata-only   # METADATA_VERIFY=OK (2000 files)
```

Each archive is rooted at `captures/`, so extracting it inside this directory lands the units
in place. The JSON/JSONL inside the archives are byte-identical to the committed copies, so
extracting over a clean checkout is a no-op for those files — `git status` stays clean apart
from the untracked PNGs.

## 7. Independent verification

Three independent checks, in increasing strength:

1. `sha256sum -c SHA256SUMS.txt` — the corpus matches this manifest.
2. Per unit, recompute each file's sha256 and compare against that unit's own
   `durable_receipt.json`. Those receipts were written by A7 at capture time, not by this
   publication, so this checks the bytes against the run itself.
3. Confirm `provenance/capture_matrix.json` reports `p2_package_sha256 = f0e9d954…`,
   `source_closure_sha256 = cdee2a8b…`, and expected counts 125 / 22,500 / 2,375 — and that
   `provenance/A7_status.json` reports `COMPLETED_UNITS = 125`, `ERRORS_SEEN = 0`,
   `SOURCE_CLOSURE = cdee2a8b…`.

Check 2 is the one that matters: it is what proves the published bytes are the run's bytes.
It was run in full before publication, over all 24,500 files, with 0 mismatches.

## 8. Scope and status

- These are **capture artifacts only**. Model activations from A9 (≈19 GiB of `.npy`) are
  **not** included — they are derived data, not trajectories.
- The P1 pilot corpus is **not** included.
- Publishing this dataset changed nothing about Experiment III-A's closed scientific result.
  No receipt, ledger, or analysis artifact was modified, moved, or regenerated.
- Experiment III emits no overall pass/fail verdict and no success gate (authority §8.10.6);
  closure is `COMPLETE`, which is a statement about completeness, not about outcome.

## 9. License

The MineOcclude repository declares no license file. Treat this dataset as internal research
data under the repository's existing (private, all-rights-reserved) status.

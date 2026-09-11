# Experiment III-A — trajectory / capture recovery report

**Result: `FINAL_ORIGINAL_CORPUS_RECOVERED`.** The final Experiment III-A production capture
corpus was found intact on local disk, verified byte-for-byte against the receipts A7 wrote
at capture time, and published. **No regeneration was required and none was performed.**

---

## 1. What was recovered

125 capture units — 25 identities `e3_t01`…`e3_t25` × 5 conditions `L0`…`L4` — at

```
/home/sagemaker-user/MineOcclude-Exp3/data/experiment_iii/production/captures/
```

24,500 files · 1,746,151,209 bytes · 22,500 PNG frames (180/capture) · 2,375 target rows
(19/capture). This is untracked working-tree content of the `MineOcclude-Exp3` worktree
(branch `exp3-sagemaker-gpu`, HEAD `96a045b`), which is why it was not visible from any
committed tree and had to be found on the filesystem.

## 2. How the search was conducted

Repositories and worktrees: 18 `.git` directories under `/home/sagemaker-user`, including all
9 worktrees of the shared `MineOcclude` object store, plus `exp3-shadow-pipeline`,
`MineWorld-Upstream`, the P11 operational clones and the v3.x/v4.x rehearsal repos. Branch
listing covered all local and remote refs, including
`origin/experiment/exp3-graded-partial-observability` and `origin/exp3-sagemaker-gpu`.
Untracked and ignored content was included throughout.

Filesystem: a depth-12 sweep for capture-unit directories matching `e3_t*__L*` across
`/home/sagemaker-user`, `/opt/ml`, `/tmp` and `/mnt/sagemaker-nvme`. This is the decisive
search — it returns every capture corpus on the machine regardless of what any receipt claims,
and it returned exactly four (§3). All auxiliary `exp3-*` roots named in the task, including
`exp3-incoming`, were inspected individually.

S3: the account has exactly one bucket, `sagemaker-us-east-1-323206973672`. Its
`mineocclude/experiment_iii/` prefix was inventoried in full — 48 objects, 2,249,414,717
bytes. It holds the A19 final scientific package (under a key that names the final P2,
`final_scientific_package_a19_p2_f0e9d954_lock_2a25bcb0/`), six P2 freeze packages including
`p2_freeze_final_v1_8_cdee2a8b`, and the P0/P1 transfer bundles. **It contains no A7
production capture corpus** — not loose, not archived. Nothing was uploaded to, overwritten
in, or deleted from S3.

## 3. Candidates found, and how the final one was identified

| Candidate | Units | Files | Bytes | Source closure | Verdict |
|---|---|---|---|---|---|
| `data/experiment_iii/production/captures` | 125 | 24,500 | 1,746,151,209 | `cdee2a8b…` | **FINAL — published** |
| `superseded_production/a7_p2_7d94a1c7_…` | 125 | 24,500 | 1,746,160,774 | `f9fba4b5…` | superseded — excluded |
| `superseded_production/a7_p2_0d286dde_…` | 56 | 10,976 | 783,787,954 | `a559c7fc…` | partial predecessor — excluded |
| `exp3-shadow-pipeline/…/production/captures` | 125 | 3,500 | 1,685,419,997 | `shadow` | synthetic fixture — excluded |

The second row is the hazard the task warned about, and it is a real one: it has the **same**
unit count, the same 22,500 frames and the same 2,375 target rows as the final cohort. Counting
cannot separate them. Three things do:

1. **The ledger.** Every `source_closure`-bearing record of the final corpus's
   `production_capture_ledger.jsonl` carries `cdee2a8ba0f6093fc6d9c961718adbee5315e71f1c640bbb1570f0e5b3b10dd0`.
   The superseded corpus's ledger carries `f9fba4b5…` in the same field. 125 units × 6
   lifecycle states = 750 records on each side, all terminal state `COMPLETE`.
2. **The capture matrix.** `docs/experiment_iii/capture/capture_matrix.json` binds
   `p2_package_sha256 = f0e9d954…` and `source_closure_sha256 = cdee2a8b…` at `stage = A7`,
   with `expected_counts` of 125 captures / 22,500 frames / 2,375 target rows, and reports
   `inventory.complete = true`. Those are the two identities the task named as final, in one
   artifact, bound together.
3. **The predecessor's own confession.** The superseded root carries a
   `SUPERSESSION_RECORD.json` naming itself: P2 `7d94a1c7…`, closure `f9fba4b5…`, head
   `03a1174f`, `classification: SUPERSEDED_BY_POST_PRODUCTION_A9_IMPLEMENTATION_REPAIR`, and
   `predecessor_a9.status: FAILED_BEFORE_FIRST_FORWARD` with blocker `P1_INCOMPLETE`. Its
   reuse policy states that `OLD_CAPTURE_REUSE_COUNT` must remain 0 and that predecessor
   captures may never be grandfathered into the successor P2 cohort.

Corroborating the same conclusion from the committed source side: commit `a91502c` has tree
`3846709e257377bbd8a26aefa10621b77a23ae87` — exactly the final implementation tree named in
the task — and its `static_validation_receipt.json` reports
`source_closure.source_closure_sha256 = cdee2a8b…` over 586 records at authority v1.8. Its
child `96a045b` is the commit that freezes `P2_FREEZE_PACKAGE.sha256` to `f0e9d954…`. The
publication branch is based on `96a045b` for that reason.

## 4. Verification performed

Every one of the 125 capture units carries a `durable_receipt.json` written by A7 at capture
time (authority §8.2), listing the sha256 and byte length of every file in that unit. Each
file on disk was re-hashed and compared against it:

```
units                     125 / 125
identities                 25  (e3_t01 … e3_t25), no gaps, no duplicates
conditions                  5  (L0 … L4), all 125 cells present
files checked          24,500
sha256 mismatches           0
size mismatches             0
files listed but missing    0
files on disk but unlisted  0
frames                 22,500  (180 per capture, uniform)
target rows             2,375  (19 per capture, uniform)
bytes           1,746,151,209
```

This is the check that matters. The receipts predate this recovery by nine days and were
written by the production driver, not by the publication, so matching them proves the
published bytes are the run's bytes rather than merely self-consistent.

The five release archives were then extracted into a scratch directory and re-verified against
`SHA256SUMS.txt` in full: 24,500 files, all matching. The archives reconstitute the corpus
exactly.

Run-level status, read from the receipts rather than assumed: A7 `STAGE_STATUS: COMPLETE`,
`COMPLETED_UNITS: 125`, `ERRORS_SEEN: 0`, `RETRY_COUNT: 0`, `POST_STAGE_VALIDATOR_STATUS: PASS`;
A8 attrition branch `NORMAL`, `N_complete: 25`, 2,375 analysable rows, 0 imputed cells, 0
dropped conditions, 0 absent identities; A19 `EXPERIMENT_III_COMPLETE: true` with all 8 closure
conditions met and no disclosed limitations.

## 5. How it was published

Git LFS was not used. It is installable here (conda-forge 3.8.0 / apt 3.4.1) and the
repository's LFS batch endpoint does accept uploads, so the mechanism was available — but the
corpus is 1.63 GiB against a 1 GiB free LFS storage allowance, and LFS downloads are metered
against a separate 1 GiB/month bandwidth allowance. The credential available here has `push`
but not `admin` on `atharv-santosh/MineOcclude`, so a quota exhaustion could not be remedied
from this session, and the failure mode is the dataset becoming undownloadable. Release assets
have a 2 GiB per-asset limit and are not metered, so they were used instead.

- Branch `data/experiment-iii-final-trajectories`, based on `96a045b`, carries the README,
  `MANIFEST.json`, `SHA256SUMS.txt` (all 24,500 files), `ARCHIVES.json`, `verify_corpus.sh`,
  the provenance receipts, and all 2,000 JSON/JSONL capture files byte-exact. A
  `.gitattributes` in the dataset directory disables text/eol normalisation so the committed
  bytes hash identically to the originals.
- Release `exp3a-final-trajectories-v1` carries five `tar.gz` archives, each rooted at
  `captures/`, together holding all 24,500 files including the 22,500 PNG frames.

Excluded by intent: the A9 model activations (~19 GiB of `.npy` — derived data, not
trajectories), the P1 pilot corpus, both superseded cohorts, and the shadow-pipeline fixture.

## 6. What was not touched

No existing scientific evidence was deleted, moved, mutated or invalidated. No S3 key was
written or overwritten. No existing branch was rewritten. The superseded cohorts remain in
place, unmodified, still marked superseded. Experiment III-A's closed result is unchanged —
this work read the corpus and copied it outward, and did nothing else to it.

## 7. Blockers

None.

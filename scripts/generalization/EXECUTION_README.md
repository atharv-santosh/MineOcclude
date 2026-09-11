# Fresh MineOcclude generalization run

This is the execution source for the user-authorized 2026-09-11 extension. The
original repository data, 25-identity graded-evidence study, and previous paper
outputs are preserved. No cloud instance, publication, push, or Overleaf edit is
performed by these scripts.

## Frozen design

See PROTOCOL.md, TRANSFER_PROTOCOL.md, and the timestamped ANALYSIS_FREEZE.json
in the capture root / compact package. There are 75 fresh identities, split
equally between original-setting replication, altered geometry, and 50% higher
speed. Each has paired air and stone recordings. Engineering pilots are excluded.

The primary estimator is the fixed layer-19 coarse 2x6 RGB representation with
16 reset input pairs and five-by-four grouped nested ridge evaluation. Seven
predictors produce 19,950 primary cells. Secondary unchanged-probe transfer uses
the 25 fresh original-setting identities as its only training source and produces
5,700 destination prediction cells. Its source-constant-column safeguard is
explicitly documented; it does not modify primary within-setting fits.

## Executed environment

The development machine is Windows with Ubuntu-24.04 WSL, RTX 5090, Ryzen 9
9950X3D, and 64 GB installed RAM. The isolated data/runtime root is
`/home/bpcfno/mineocclude-generalization-20260911`; the managed Python executable
is `/home/bpcfno/mineocclude-rgb-env/bin/python`. These are machine-specific
execution paths, not required public installation locations.

The scripts reference the project checkout through their own location. The
capture-root constants and runtime.json need explicit configuration on another
machine. GPU extraction additionally requires the upstream MineWorld source at
the recorded revision and the hash-verified checkpoint/VAE, as used by the
preserved scripts/rgb_replication/extract_features.py. The upstream model source,
checkpoint paths, and all numerical dependencies are recorded in runtime receipts.
Full recapture is distinct from CPU statistical reconstruction.

## Stage order

1. Provision Java 17, Xvfb, Mesa, the official Minecraft/Fabric runtime, and an
   unmodified build of fabric/mineocclude-mod. `provision.py` is isolated and
   hash-checks downloaded core binaries. `audit_mod.py` checks original sources
   and all 43 Java tests.
2. Run disjoint pilots with `pilot.py`; inspect `audit_pilots.py` output and actual
   images. `plan_cohort.py` writes the prospective roster. `admit.py` binds the
   pilot checks, roster, runtime, mod, and protocol. Do not overwrite a roster or
   rerun admission over an active display. Use a new pilot attempt ID for recovery.
3. `audit_roster.py` checks historical/pilot seed separation. `capture.py` saves
   150 recordings with immutable BANKED durability receipts. BANKED is not the
   scientific qualification state. `prepare.py` independently verifies all units,
   exact pairing, targets, and grouped folds before writing manifest.json.
4. `features.py --mode pixels` and `features.py --mode mineworld` extract the fixed
   inputs. `fit.py` performs primary evaluation. `transfer.py` performs the
   separately specified source-only transfer analysis. Neither tunes on held-out
   destination data.
5. `rebuild_statistics.py`, `summarize_transfer.py`, and `validate_results.py`
   reconstruct and independently check numerical summaries. `scene_assets.py`
   supplies actual paired example images and nonblank-image checks.
6. `package_results.py` stages CPU reproduction. Its `--raw` mode archives every
   original fresh frame/log with verified hashes, without game binaries or weights.
   `build_paper.py` prepares a new manuscript directory; compile and visually
   inspect it before delivery. None of this overwrites the prior manuscript.

The asynchronous `run_analysis.py` waits for full capture completion and runs the
analysis stages fail-closed. It does not declare final scientific or visual QA.

## Validation caveats retained

The old Python test suite needs explicit GIT_DIR/GIT_WORK_TREE when invoked from
WSL because this checkout's .git indirection uses a Windows path. Once resolved,
154 selected tests pass; one strict historical label-equality assertion differs
by floating-point summation order. `arithmetic_audit.py` independently bounds the
new-target fsum difference below 2e-15 blocks and reproduces historical raw-state
oracle predictions to floating-point precision. No old test or numerical record
is rewritten to conceal this.

The unchanged FIR definition is checked against visible silhouette motion on
disjoint pilots. This is not exact rendered-entity-origin calibration. Fresh
capture uses software rendering, so comparisons with the recovered hardware-
rendered cohort are not attributable solely to independent trajectory sampling.
The three fresh settings share one software renderer for their own comparisons.

The companion CPU-only reproduction snapshot is portable and needs only Python
3.10--3.12 and NumPy 1.26.4. Its `python reproduce.py` command does not depend on
the execution-machine paths above. Public anonymous access is a separate release
step and is not established by creating a local archive.

The final edited manuscript is the delivered Overleaf ZIP. `build_paper.py`
creates the initial data-filled draft, not the final editorial revision; do not
rerun it over the delivered paper directory if retaining those edits.

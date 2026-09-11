# legacy_bgr — the channel order Experiment III-A actually executed under

**Every model-side artifact in this package is legacy-BGR-conditioned, and that was the
authorized design — not a defect discovered after the fact.**

## What executed

The A9 driver loaded each captured PNG with PIL as **true scene RGB**:

```python
# scripts/experiment_iii/run_extraction.py:233-238
def _load_frame(path: Path):
    with Image.open(path) as handle:
        return _np.asarray(handle.convert("RGB"))
```

and handed it to the frozen adapter preprocessing, whose first operation assumes a
`cv2.imread`-style BGR array:

```python
# src/mineocclude/models/_mineworld_adapter_wave2.py:432
rgb = cv2.cvtColor(source, cv2.COLOR_BGR2RGB)
```

Given true-RGB input, that call **reverses** the channels instead of restoring them. The
tensor MineWorld consumed therefore carried the scene's blue channel in slot 0 and its red
channel in slot 2.

This was verified empirically on 2026-09-11, not merely read off the source: replaying
`_preprocess_bgr_frame` on a real A7 frame (`e3_t01__L2/raw/frames/000040.png`) and
comparing bit-for-bit against references built with the remaining steps only —

| reference | matches executed tensor |
|---|---|
| true-RGB array → resize → normalize | **no** |
| channel-reversed array → resize → normalize | **yes** |

Per-channel means: executed `[0.2195, 0.1521, -0.0932]` versus true-RGB `[-0.0932, 0.1521, 0.2195]` — exactly transposed.

## Why this is not a bug report

Authority v1.8 **knew about this before production and froze it deliberately**:

- `p0_rve.measurement_scope_disclosure.mineworld_historical_preprocessing_channel_order = "BGR"`
- `extraction.rgb_bgr_historical_behavior_change_allowed = false`
- `EXPERIMENT_III_LIFECYCLE.json` → `states[9].forbidden_repairs[5] = "FIX_THE_HISTORICAL_RGB_BGR_PREPROCESSING_BEHAVIOR"`
- Authority §2253: *"Experiment III does not 'fix' or reinterpret the historical RGB/BGR channel-order behavior."*
- The frozen authority audit carries a passing check named *"RVE disclosure names the BGR history."*

The reasoning recorded in the authority: every condition passes through **identical** code, so
the ladder remains internally valid; the RVE statistic is channel-permutation invariant so the
number is unchanged; what the ordering costs is that the RVE ladder orders conditions by
**source-rendered** visual evidence rather than by model-perceived evidence. That is a declared
scope limitation of the experiment, disclosed in §7.4, not an error in it.

## The asymmetry that matters when reading results

| path | channel order |
|---|---|
| captured PNGs on disk | **true RGB** (nothing was ever serialized swapped) |
| MineWorld model input, VAE input | **BGR** |
| activations at layers 4 / 10 / 19, both slices | **BGR**-conditioned |
| feature blocks `CURRENT`, `CURRENT_L04`, `CURRENT_L10`, `CURRENT_MINUS_PREVIOUS`, `TWO_FRAME_CONCAT` | **BGR**-conditioned |
| feature block `PIXEL_BASELINE` → model `LINEAR_CURRENT_PIXEL` | **true RGB** |
| P0 / RVE condition ladder | **true RGB** (authority §7.4 forbids coupling to the model path) |
| FIR targets | not pixel-derived at all — server-side world coordinates |

So the headline comparison, MineWorld versus the linear current-frame pixel baseline, is a
comparison between a BGR-conditioned readout and a true-RGB baseline. That is what ran, and it
is preserved here exactly.

## Corrected RGB

```
CORRECTED_RGB_OUTPUTS=NONE_FOUND
```

No corrected-RGB extraction, prediction lock, feature block or result exists anywhere on this
machine or in S3. Searched: the whole filesystem under `/home/sagemaker-user`, `/opt/ml`,
`/tmp` and `/mnt/sagemaker-nvme` for `*corrected*`, `*rgb_fix*`, `*bgr_fix*`, `*channel_fix*`,
`*color_fix*`, `*rerun*`, `*reextract*`, `*reprocess*`; `git log --all` across every local and
remote ref for RGB / BGR / channel; and the full `mineocclude/experiment_iii/` S3 prefix. Every
git hit belongs to the Experiment-I / Regime-A 66-cell lineage (`person-a-bgr2rgb-inter-linear-224x384-v1.0`),
not to Experiment III.

**None was created by this recovery.** There is therefore no `corrected_rgb/` directory in this
package — an empty one was deliberately not invented. `CHANNEL_ORDER_MANIFEST.json` in this
directory classifies every artifact by its channel condition, which is what keeps the two
regimes separable if a corrected-RGB run is ever produced.

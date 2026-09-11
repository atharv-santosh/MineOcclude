# MineOcclude history-dependent diagnostic, prospective protocol

User authorized five hours on 2026-09-11 at 14:44 UTC; deadline 19:44 UTC.
This is a new experiment. Preserve every prior capture, prediction and paper.

## Question and cohorts

Does a fixed visual representation distinguish hidden positions when scene,
direction and occlusion age are matched but observed pre-occlusion speeds differ?
Use layout_01 and layout_04, the same locked camera and sheep as the previous
extension. Each layout has 24 training identities and 24 untouched test identities.
Each partition has 12 LTR and 12 RTL identities. Within each direction, six speeds
are sampled uniformly from [0.8,1.6] and six from [2.4,3.2] blocks/s. All random
seeds are fresh. Reciprocal slow/fast donor pairs are fixed by roster position,
not by decoding outcomes. The stochastic drift model retains q=0.05, dt=0.05,
180 frames and exact paired air/stone captures. No invisible unpredictable event
is introduced. Starts have magnitude U(7.3,7.9). No probe receives commanded speed.

Sixteen engineering captures (both speed endpoints, both directions, both
layouts, air/stone) are excluded from all scientific fitting and estimates.
Production requires the inherited physical/frame/path/pair checks plus visible
pilot motion agreement. No failed decoding result can be replaced.

Target selection is the first 19 consecutive geometry-defined fully occluded
rows, with >=16 frames available and no target clamp. These rows are identical
between air and stone. Primary estimates use ages 1--10; ages 11--15 are secondary
and 16--19 are a no-pre-occlusion-evidence control for the reset window.

## Inputs and readouts

Primary: verified RGB MineWorld 700M_16f, final layer 19, coarse 2x6 pooling,
16 teacher-forced reset pairs. Secondary checkpoint: MineWorld 300M_16f, same
final-layer pooling and input window, pinned asset hash and official config.
This second checkpoint extends model size within one family, not architectures.

Stone-history interventions keep the recipient current frame and action tokens:
- correct: recipient's recorded 16-image history;
- swapped: paired donor's 15 preceding stone frames at the same occlusion age,
  followed by the recipient current frame;
- removed: recipient current stone image repeated 16 times.
Original-only training is used for every intervention evaluation. Reciprocal
donor histories come from the same partition, layout and direction. Report
current-frame pixel mismatch and visible-frame counts; do not silently discard
bad pairs. Swapping at a hidden-to-hidden boundary preserves the observed object's
motion continuity; background mismatch and removal distribution shift remain
explicit caveats. Ages >=16 must contain no counterfactual visible rows.

Compare ridge probes with a small nonlinear MLP (training-only 64-D PCA,
32 hidden units, tanh; weight-decay {0.001,0.1}; 3 fixed random seeds). Ridge uses
alpha {0.1,1,10,100,1000}. Four grouped training folds select hyperparameters;
test labels are scoring-only. Standardization/PCA/constant-column removal are
training-only. Save all fitted selections before reporting any test metric.

Comparators: current pixels and identical 16-frame history pixels (48x28 RGB),
training mean, direction+age OLS, privileged last-seen/CV, and an image-only
magenta-object tracker with train-only pixel-to-position calibration and
constant-velocity extrapolation from reliable visible detections inside the
same 16-frame window. The tracker never receives test server positions or
geometry-derived visibility. Report detection coverage and a train-mean fallback
when no reliable observation remains. A nonlearned detector is appropriate to
this known sheep; it is not a general-purpose tracking result.

## Transfer and confirmation

Fit original-layout probes using only its 24 training identities. Evaluate the
24 untouched other-layout test identities with (1) unchanged probes, (2) a shared
affine output calibration fitted using six predesignated other-layout TRAINING
identities in AIR only, and (3) native within-layout fitting. No hidden destination
labels enter the visible-calibration fit. Explain that this is output calibration,
not proof of a mechanism. All other-layout native training remains disjoint from
its test set. Old 75-identity observations are development evidence only.

Report mean identity RMSE/MAE, signed paired differences, and 10,000 paired
bootstrap intervals. Resample reciprocal donor pairs for intervention comparisons
because both recipients share donor data. Test prediction response against donor
and recipient targets, including signed response agreement; input sensitivity is
not an identified internal causal circuit. Preserve all conditions and checkpoints.
No significance-driven stopping, model reselection, or invented outcomes.

## Delivery

New paper/source/PDF, compact CPU-rebuildable results and full capture archive.
Prepare a privacy-reviewed anonymous release and verify access if existing
credentials permit it. Never publish credentials, private paths or identity-bearing
logs. Do not overwrite the existing Overleaf project or previous release artifacts.
Record any access or technical blocker. Do not bypass checkpoint safety or runtime
validation to meet the deadline. Full architecture-level mechanistic claims are
out of scope unless directly supported; input-history interventions alone do not
establish them.

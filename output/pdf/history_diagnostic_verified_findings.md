# MineOcclude prospective diagnostic: verified findings

New captures and analyses, not a relabeling of the previous experiments. Primary interval: occlusion ages 1–10. 48 training and 48 held-out identities, two layouts, 192 paired recordings. The earlier central and 75-identity extension studies are preserved separately.

## Correct-history hidden-position decoding

| Predictor | Mean identity RMSE [95% bootstrap interval], blocks |
|---|---|
| MW_700M | 1.603 [1.314, 1.908] |
| MW_300M | 1.588 [1.291, 1.900] |
| MW_700M_MLP | 1.199 [0.908, 1.523] |
| MW_300M_MLP | 1.315 [1.032, 1.627] |
| PIXEL_CURRENT | 3.911 [3.870, 3.951] |
| PIXEL_HISTORY16 | 1.915 [1.470, 2.449] |
| IMAGE_TRACKER_CV | 2.918 [2.631, 3.208] |
| DIRECTION_AGE | 0.154 [0.136, 0.172] |
| ORACLE_LAST_SEEN | 0.411 [0.362, 0.459] |
| ORACLE_CONSTANT_VELOCITY | 0.252 [0.219, 0.286] |
| TRAINING_MEAN | 3.917 [3.877, 3.955] |

A separate training-diagnostic-triggered check extends only the final MLP optimization budget, without reopening hyperparameter selection. All 24 seed-level fits converge; the original capped fits remain above.

- MW_700M_MLP_OPT10K: 1.240 [0.944, 1.565].
- MW_300M_MLP_OPT10K: 1.341 [1.063, 1.645].

The paired 700M ridge minus history-pixel difference is -0.312 [-0.784, 0.013]. Its interval includes zero; this new pooled comparison does not establish a reliable advantage. Direction-and-age remains much more accurate despite variable commanded speeds.


## History interventions

Current image and actions are fixed; only the earlier images change. Differences below are intervened minus correct-history RMSE, using reciprocal-donor-pair bootstrap intervals. Positive means worse after intervention.

| Predictor | Swapped history | Repeated-current history |
|---|---|---|
| MW_700M | -0.094 [-0.144, -0.047] | 2.314 [2.068, 2.560] |
| MW_300M | -0.074 [-0.121, -0.031] | 2.329 [2.075, 2.574] |
| MW_700M_MLP | -0.066 [-0.096, -0.038] | 2.714 [2.471, 2.941] |
| MW_300M_MLP | -0.060 [-0.094, -0.024] | 2.596 [2.350, 2.828] |
| PIXEL_CURRENT | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] |
| PIXEL_HISTORY16 | -0.093 [-0.125, -0.062] | 2.002 [1.416, 2.437] |
| IMAGE_TRACKER_CV | -0.042 [-0.082, -0.008] | 0.998 [0.924, 1.076] |

## Geometry transfer

Source training uses only the original layout. Visible calibration fits one affine output correction on six predesignated destination-training air identities. Destination hidden test labels never fit the calibration.

| Predictor | Frozen air / stone | Visible-calibrated air / stone | Native air / stone |
|---|---|---|---|
| MW_700M | 1.934 / 2.675 | 0.271 / 3.177 | 0.111 / 1.653 |
| MW_300M | 1.852 / 2.824 | 0.342 / 4.087 | 0.104 / 1.589 |
| PIXEL_CURRENT | 1.495 / 4.023 | 0.119 / 4.023 | 0.094 / 4.011 |
| PIXEL_HISTORY16 | 7.000 / 49.139 | 0.165 / 75.218 | 0.086 / 1.897 |

## Validation and remaining limits

- Saved-fit replay, split/target joins, source-provenance checks, independent arithmetic, and intervention resampling checks passed for all 40,128 original prediction cells. The separate converged-MLP check adds 7,296 replayed cells and a CPU statistics rebuild.
- One validation assertion incorrectly assumed every prior frame preceding the selected consecutive occlusion segment was visible. A recorded transient occlusion violated that shortcut. Validation now uses exact recorded visibility; the failed check and repair are preserved, and no identity, prediction, target, or original statistic changed.
- Swapping history changes predictions but does not reliably make them follow donor position: 700M donor-direction agreement is 32.1%. Removing history worsens decoding. These are distinct findings.
- The image tracker falls back to the training mean on 59.4% of primary stone rows. Its weak score must be interpreted alongside this limited observation coverage.
- Statistics condition on fitted models; intervals do not include retraining uncertainty or multiple-comparison adjustment.
- Two sizes of one pretrained family are not two independent architectures. One entity and one stochastic motion family remain.
- History swaps are input-distribution interventions, not proof of a neural memory circuit. Image-history matching does not match resolution or pretraining.
- Full tracker coverage, later-age bins, nonlinear optimizer diagnostics, and all unfavorable results remain in the snapshot.
- Anonymous release and access are separate from local verification. Check the delivery receipt for their actual status.

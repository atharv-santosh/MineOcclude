# Analysis implementation specification

Written before production capture and before any test prediction is scored.
The roster and primary protocol remain unchanged.

Hyperparameter selection minimizes mean identity RMSE over all 19 training
targets in four identity folds (rank modulo four). Primary reporting uses ages
1--10. Nonlinear probes use standardized features, randomized PCA with at most
64 components (seed 93011), and a 32-unit tanh MLP with L-BFGS, max_iter=500,
max_fun=25000, tolerance 1e-5. Targets are standardized using training statistics.
Three seeds 1301, 1302, 1303 are averaged. Select L2 penalty 0.001 or 0.1 using
the same training folds. Nonconvergence is reported, not silently discarded.

Image tracking uses the largest connected component of pixels satisfying
R>45, B>30, R>1.4G and B>1.25G. Pixel coordinates are calibrated to the existing
FIR target by ordinary least squares on training AIR frames with abs(raw x)<6
and index>=15. Typical component width, height and area use medians of those
training detections. A reliable detection has width>=0.85, height>=0.85 and
area>=0.65 of these medians. Fit time-versus-calibrated-position OLS to the last
at most ten reliable observations within the supplied 16-frame image window.
One observation uses last position; none uses the training target mean. This
same detector and threshold recipe is used for every layout and intervention.
No test server label or visibility class enters the tracker.

Visible-only transfer calibration uses the six layout_04 TRAIN identities with
rank in {0,4,8}, three in each direction. Fit one intercept and slope from the
source AIR probe's predictions to their AIR targets. Apply this same mapping to
both source AIR and STONE probes on layout_04 test identities. Report the frozen,
calibrated, and native fits; never select among them using test performance.

In addition to mean identity RMSE/MAE, report trajectory-macro R2, with each
trajectory's own mean denominator. Paired differences always mean first minus
second, so negative RMSE differences favor the first predictor. All intervals
use 10,000 identity bootstrap draws (seed 930119), except intervention contrasts,
which resample reciprocal donor pairs. Intervals condition on the fitted models.
The primary swapped-history response measures whether prediction changes have
the same sign as donor-minus-recipient targets, excluding exactly zero target
differences. Report response magnitude as well, without asserting a circuit.

Fresh target truth is used for supervised probe fitting and scoring only. It
does not enter MineWorld, pixel features, or test image tracking. Metadata and
oracle baselines are separately labeled privileged inputs.

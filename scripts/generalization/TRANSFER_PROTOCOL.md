# Secondary fixed-probe transfer

Specified during production capture, before any new neural or pixel readout
outcomes were computed or inspected. This instantiates the optional secondary
transfer analysis in PROTOCOL.md; the primary within-cohort analysis is unchanged.

Train on the 25 fresh replication identities, separately for AIR and STONE.
Select ridge alpha from the same five-value grid using the five frozen identity
folds of this source cohort, minimizing mean held-out identity RMSE. Refit scaler
and ridge on all 25 source identities. Evaluate the unchanged probe on all 25
geometry and all 25 speed identities, without using their labels in any fitting,
scaling, or selection. Run this for MineWorld L19 coarse RGB, current pixels,
and 16-frame history pixels. Retain all three predictors and both destinations.

This is transfer from the fresh source cohort, not from the historical cohort.
All three fresh cohorts share the rendering runtime. Geometry changes several
spatial factors together; speed changes by 50%. Report RMSE/MAE/trajectory R2
and descriptive paired identity-bootstrap intervals conditional on source fit.
Do not pool transfer and within-condition refitting into one score.

Numerical safeguard specified before readout outcomes: remove exactly constant
source-training columns (peak-to-peak range zero) before standardization, inside
each source-validation fold and again for the final source fit. This prevents
round-off in the standard deviation of repeated pixel values from producing
spurious large transfer weights. The mask is learned on source training data
only and then fixed for destination prediction. It applies to all three transfer
predictors. The primary historical-compatible within-cohort implementation is
unchanged; transfer explicitly reports this constant-column safeguard.

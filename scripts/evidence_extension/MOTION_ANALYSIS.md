# Prospective motion analysis

The production sample is 128 independent trajectory families, split 64 training
and 64 test, with 32 families per partition/layout. Four motion types each supply
eight families per layout/partition. Each family has two variants, both directions
are balanced, and air/stone are paired: 512 captures and 9,728 scored rows.
Engineering pilots do not enter training, selection, or scientific intervals.
Geometry-only candidate rejection is recorded before capture. Starts are adjusted
to match the world position at first full occlusion within each direction/layout.
Within-trajectory changes are deterministic and visible-history-informative, with
no added process noise. They must not be described as unpredictable hidden events.

Primary readout: frozen RGB MineWorld 700M, layer 19, coarse 2x6, 16 reset pairs.
Comparators: current pixels, 16-frame pixels, ordered current-plus-frame-differences,
current pixels plus 15 Farneback fields, and frozen pretrained VideoMAE-S.
Ridge alpha {0.1,1,10,100,1000}; four training-only family folds (rank modulo four)
select mean family RMSE over the 19 aligned target rows. Source-condition scaling
and alpha stay frozen for cross-condition testing. No destination recalibration.
Train separately in each layout and report both and an equally weighted pooled
summary. Store fitted weights, masks, scales, alpha choices and row predictions.

Metadata OLS [1,d,a,d*a] is supplemented by cubic age interactions with direction
and an explicitly privileged motion-family indicator. Oracle last-position and
constant-velocity forecasts use only pre-occlusion state logs, not future states;
they are not image-history-matched comparators. Report their information access.

Primary scoring is occlusion ages 1-10; secondary 11-15 and 16-19 separately.
Average errors within variants, then within family. Bootstrap 10,000 independent
families, stratified by layout and motion type, seed 94113. Report RMSE/MAE and
paired differences against equal-history pixels, VideoMAE, and metadata. Test
whether paired prediction differences track paired target differences, reporting
signed agreement and contrast error rather than using a positive score as a gate.
No candidate selection or stopping uses these test results.

The identical-input negative control is separately labeled as a constructed
information-boundary test. Duplicate the exact full observed input and associate
two prespecified alternative hidden futures. Deterministic predictions must remain
identical. This is a leakage/information-limit control, not new empirical evidence
for object memory and not a test on which exact branch identification is possible.

Admission requires exact commanded-path replay, zero queued ticks, complete frame
joins, paired state/action agreement, visible sheep in air, no visible sheep in
scored stone rows, and pilot verification of rendered alignment and history
observability. Invalid capture attempts are retained and may be recaptured under
new episode IDs; scientific outcomes are never used as recapture criteria.

# Person E homography refit: Attempt 02 annotation preparation

The immutable Person C handoff and all six screenshot and geometry-receipt
identities verify, but the existing deterministic marker detector fails closed
on two comparable lime blobs in `layout_06`. No diagnostic pixel coordinate is
accepted or stored.

Run this one command from any directory:

```powershell
python C:\Users\lollo\MineOcclude-Person-E-Refit\scripts\annotate_person_e_homography_refit_attempt_02.py
```

The window prompts for four fit-marker centres and four independent validation
points on each of the six original-resolution screenshots. The result is
written once to:

`C:\Users\lollo\MineOcclude-Person-E-Refit\data\handoff_e\person_e_v0_4_homography_refit_v0_1\person_e_attempt_02_image_points_v0_1.json`

Existing output is never overwritten. The homography fit remains blocked until
this complete, operator-confirmed annotation exists.

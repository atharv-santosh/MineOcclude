"""Record the concrete analysis code before any fresh feature extraction/fitting."""
from datetime import datetime,timezone
from prepare import ROOT,SOURCE,read,save,sha


if __name__=='__main__':
    destination=ROOT/'ANALYSIS_FREEZE.json'
    assert not destination.exists()
    assert not (ROOT/'analysis/features').exists()
    files=['PROTOCOL.md','TRANSFER_PROTOCOL.md','features.py','fit.py','transfer.py',
           'rebuild_statistics.py','summarize_transfer.py']
    save(destination,dict(frozen_at_utc=datetime.now(timezone.utc).isoformat(),
        stage='Production capture active; no fresh features or readout outcomes yet',
        capture_status=read(ROOT/'capture_status.json'),
        files={name:sha(SOURCE/'scripts/generalization'/name) for name in files},
        cohort_sha256=sha(ROOT/'cohort_geometry_draft.json'),
        capture_admission_sha256=sha(ROOT/'capture_admission.json')))
    print('ANALYSIS_FROZEN',sha(destination))

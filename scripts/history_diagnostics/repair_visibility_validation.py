"""Record an audit correction without changing predictions or statistics."""
from diag_common import *
from datetime import datetime,timezone
import subprocess
import time

OUT=ROOT/'analysis'


def main():
    path=ROOT/'validation_count_repair.json'; assert not path.exists()
    manifest=read(ROOT/'manifest.json')['units']
    exceptions=[]
    for name,r in manifest.items():
        if '_test_' not in name or not name.endswith('__L4'): continue
        t=r['target_model_frame_indices'][0]
        transient=[j for j in range(t-15,t) if r['fully_occluded'][j]]
        if transient: exceptions.append(dict(unit=name,first_target=t,earlier_fully_occluded_frames=transient,prior_visibility=[not r['fully_occluded'][j] for j in range(t-15,t)]))
    assert len(exceptions)==1 and exceptions[0]['unit']=='h26_layout_04_test_1_03__L4'
    assert exceptions[0]['earlier_fully_occluded_frames']==[39] and exceptions[0]['first_target']==42
    failure=OUT/'job_logs/validate_diag.log'
    assert "donor_nonfull_frames" in failure.read_text() and 'AssertionError' in failure.read_text()
    previous=read(ROOT/'statistical_source_amendment.json')
    save(path,dict(status='POST_PREDICTION_VALIDATION_CORRECTION_NO_RESULT_CHANGE',utc=datetime.now(timezone.utc).isoformat(),previous_amendment_sha256=sha(ROOT/'statistical_source_amendment.json'),original_validator_sha256=previous['current_files']['validate_diag.py'],repaired_validator_sha256=sha(Path(__file__).parent/'validate_diag.py'),failed_validation_log_sha256=sha(failure),reason='The first 19-frame consecutive occlusion segment need not be the first isolated fully occluded frame. One recorded trajectory is hidden at frame 39, visible at 40-41, and continuously hidden from 42. Replace an assumed visibility-count formula with exact recorded-visibility checks, retaining the zero-prior-visibility condition at ages 16-19.',exceptions=exceptions,unchanged_statistics_sha256=sha(OUT/'statistics.json'),unchanged_predictions={p.name:sha(p) for p in sorted((OUT/'predictions').glob('*.json'))},scope='No captures, labels, features, estimators, selection decisions, predictions, statistics, or inclusion rules change. No identity is excluded.'))
    started=time.monotonic()
    log=OUT/'job_logs/validate_diag_repaired.log'; assert not log.exists()
    with log.open('w') as stream:
        subprocess.run([sys.executable,str(Path(__file__).parent/'validate_diag.py')],stdout=stream,stderr=subprocess.STDOUT,check=True)
    save(OUT/'job_logs/validate_diag_repaired.json',dict(status='PASS',elapsed_seconds=time.monotonic()-started,finished_utc=datetime.now(timezone.utc).isoformat(),log_sha256=sha(log)))
    save(OUT/'analysis_complete.json',dict(status='PASS',finished_utc=datetime.now(timezone.utc).isoformat(),statistics_sha256=sha(OUT/'statistics.json'),validation_sha256=sha(OUT/'independent_validation.json'),validation_repair_sha256=sha(path),original_failed_validation_log_sha256=sha(failure)))
    print('EXACT_VISIBILITY_VALIDATION_PASS',flush=True)


if __name__=='__main__': main()

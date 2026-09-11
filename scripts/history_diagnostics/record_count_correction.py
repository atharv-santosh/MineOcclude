from diag_common import *
from datetime import datetime,timezone


def main():
    assert not list((ROOT/'analysis/predictions').glob('*.json'))
    destination=ROOT/'statistical_source_amendment.json'
    assert not destination.exists()
    original=read(ROOT/'statistical_source_freeze.json')
    save(destination,dict(utc=datetime.now(timezone.utc).isoformat(),status='CORRECTED_BEFORE_ANY_TEST_PREDICTION_FILE',original_freeze_sha256=sha(ROOT/'statistical_source_freeze.json'),original_files=original['files'],current_files={name:sha(Path(__file__).parent/name) for name in original['files']},correction='Expected prediction cardinality corrected from 62016 to 40128. The earlier arithmetic double-counted native-model layout totals. Added a count unit test and validation of this amendment. No estimator, split, outcome, prediction, or statistical formula changed.',cardinality=dict(native_6_models=21888,tracker_and_motion=10944,transfer_4_models=7296,total=40128)))
    print('PREOUTCOME_CARDINALITY_CORRECTION_RECORDED',sha(destination))


if __name__=='__main__':
    main()

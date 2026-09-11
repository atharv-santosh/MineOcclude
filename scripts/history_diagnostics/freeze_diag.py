from diag_common import *
import datetime
import shutil
import subprocess


def main():
    destination=ROOT/'analysis_freeze.json'
    assert not destination.exists()
    rows=read(ROOT/'roster.json')['identities']
    seeds={r['seed'] for r in rows}
    expression='(^|[^0-9])('+'|'.join(map(str,sorted(seeds)))+')([^0-9]|$)'
    command=(['rg','-l','-g','*.json','-g','*.jsonl',expression,'docs','data'] if shutil.which('rg') else ['grep','-rEl','--include=*.json','--include=*.jsonl',expression,'docs','data'])
    result=subprocess.run(command,cwd=SOURCE,text=True,capture_output=True)
    assert result.returncode==1,(result.returncode,result.stdout,result.stderr)
    previous_seeds={r['seed'] for r in read(PREVIOUS/'cohort_geometry_draft.json')['identities']}
    for path in (PREVIOUS/'pilots').glob('*/spec.json'):
        previous_seeds.add(read(path)['seed'])
    assert not seeds&previous_seeds
    assert not list((ROOT/'analysis/predictions').glob('*.json'))
    files={p.name:sha(p) for p in Path(__file__).parent.iterdir() if p.suffix in ('.py','.md')}
    save(destination,dict(status='FROZEN_BEFORE_TEST_PREDICTIONS',utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),files=files,roster_sha256=sha(ROOT/'roster.json'),seed_independence='96 new seeds absent from historical docs/data JSON records and prior fresh/pilot captures',prior_fresh_seeds_checked=len(previous_seeds),solver_validation=read(ROOT/'analysis/tests/solver_validation.json'),capture_admission_sha256=sha(ROOT/'capture_admission.json')))
    print('ANALYSIS_FROZEN',sha(destination),flush=True)


if __name__=='__main__':
    main()

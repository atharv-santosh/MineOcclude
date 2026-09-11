"""Check new seeds against historical repository records and engineering pilots."""
import json
import subprocess
import shutil
from prepare import ROOT,SOURCE,read,save,sha


def main():
    draft=read(ROOT/'cohort_geometry_draft.json')
    seeds={r['seed'] for r in draft['identities']}
    assert len(seeds)==75
    expression='(^|[^0-9])('+'|'.join(map(str,sorted(seeds)))+')([^0-9]|$)'
    # Read-only search of historical tracked-data areas, not the new work output.
    command=(['rg','-l','-g','*.json','-g','*.jsonl',expression,'docs','data'] if shutil.which('rg')
             else ['grep','-rEl','--include=*.json','--include=*.jsonl',expression,'docs','data'])
    result=subprocess.run(command,cwd=SOURCE,text=True,capture_output=True)
    assert result.returncode==1,(result.returncode,result.stdout,result.stderr)
    pilot_seeds=set()
    for path in (ROOT/'pilots').glob('*/spec.json'):
        spec=read(path)
        pilot_seeds.add(spec['seed'])
    assert not seeds&pilot_seeds
    save(ROOT/'seed_independence.json',dict(status='PASS',new_seeds=75,engineering_pilot_seeds=len(pilot_seeds),historical_search='No new numerical seed occurs in JSON/JSONL records under repository docs/ or data/.',draft_sha256=sha(ROOT/'cohort_geometry_draft.json')))
    print('SEED_INDEPENDENCE_PASS',len(seeds),len(pilot_seeds))


if __name__=='__main__':
    main()

from diag_common import *
import argparse
import numpy as np
import prepare as inherited
from audit_pilots import audit


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--pilot',action='store_true')
    a=p.parse_args()
    inherited.ROOT=ROOT
    roster=read(ROOT/'roster.json')
    rows=roster['pilots' if a.pilot else 'identities']
    units={}
    audits=[]
    for row in rows:
        for c in ['L0','L4']:
            unit=f"{row['identity']}__{c}"
            directory=ROOT/('pilots' if a.pilot else 'captures')/unit
            info=inherited.verify(directory,row)
            units[unit]=info
            if a.pilot:
                check=audit(directory)
                if c=='L0':
                    assert check['historical_FIR_pixel_centered_rmse']<.15,check
                    assert abs(check['historical_FIR_pixel_offset_median'])<.30,check
                audits.append({k:v for k,v in check.items() if k!='measurements'})
            print('VERIFIED',unit,flush=True)
        x,y=(units[f"{row['identity']}__{c}"] for c in ['L0','L4'])
        for k in ['targets','state_positions','target_model_frame_indices','action_payload']:
            assert x[k]==y[k],(row['identity'],k)
    if a.pilot:
        save(ROOT/'capture_admission.json',dict(status='PASS',roster_sha256=sha(ROOT/'roster.json'),protocol_sha256=roster['protocol_sha256'],pilot_units=len(units),audits=audits,alignment='Inherited FIR; visible silhouette check, not exact rendered-origin recalibration'))
    else:
        assert len(units)==192
        save(ROOT/'manifest.json',dict(status='ALL_192_VERIFIED',units=units,roster_sha256=sha(ROOT/'roster.json')))
    print('VERIFICATION_PASS',len(units),flush=True)

if __name__=='__main__':
    main()

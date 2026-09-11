from common import *
import numpy as np
from fit_diag import predict_frozen
from motion_baselines import design,oracle

def main():
    roster=read(MOTION_ROSTER)['rows'];byid={r['identity']:r for r in roster}
    test={r['identity'] for r in roster if r['partition']=='test'}
    maxerr=0.;count=0
    for p in sorted((ROOT/'motion/predictions').glob('*.json')):
        data=read(p);cells=data['cells'];model=cells[0]['model'];layout=cells[0]['layout'];source=cells[0]['source']
        assert not set(data['training_ids'])&test
        assert not {byid[i]['family_id'] for i in data['training_ids']}&{byid[i]['family_id'] for i in test}
        assert data['roster_sha256']==sha(MOTION_ROSTER)
        if source!='METADATA':
            fit=ROOT/'motion/fits'/f'{model}__{layout}__{source}.npz'
            assert sha(fit)==data['fit_sha256']
        for i in sorted({r['identity'] for r in cells}):
            spec=byid[i];assert i in test
            for c in ['L0','L4']:
                selected=sorted([r for r in cells if r['identity']==i and r['condition']==c],key=lambda r:r['age'])
                assert len(selected)==19
                assert [r['target'] for r in selected]==spec['historical_FIR_reference_labels']
                if model.startswith('META'):pred=design(spec,model)@np.array(data['coefficients'])
                elif model.startswith('ORACLE'):pred=oracle(spec,model)
                else:pred=predict_frozen(fit,np.load(ROOT/'motion/features'/model/f'{i}__{c}.npy',allow_pickle=False))
                maxerr=max(maxerr,float(np.max(abs(pred-[r['prediction'] for r in selected]))));count+=19
    assert maxerr<1e-7,maxerr
    banks=list((ROOT/'captures').glob('*/BANKED.json'))
    assert len(banks)==512
    feature_receipts=list((ROOT/'motion/receipts').glob('*.json'))
    for p in feature_receipts:
        r=read(p)
        assert sha(ROOT/'captures'/r['unit']/'BANKED.json')==r['bank_sha256']
        assert all(sha(ROOT/'motion/features'/m/f'{r["unit"]}.npy')==h for m,h in r['features'].items())
    save(ROOT/'motion/validation.json',dict(status='PASS',prediction_rows=count,saved_fit_replay_max_error=maxerr,capture_units=len(banks),feature_receipts=len(feature_receipts),train_test_family_disjoint=True))
    print('MOTION_VALIDATION_PASS',count,maxerr,flush=True)

if __name__=='__main__':main()

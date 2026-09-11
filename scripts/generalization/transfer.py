"""Secondary fixed-source probe transfer, with no destination-label fitting."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','4')
os.environ.setdefault('OMP_NUM_THREADS','4')
import time
import numpy as np
from fit import OUT, ROOT, SOURCE, read, save, sha, ALPHAS, predict_alphas
from mineocclude.probes.ridge import fit_ridge


def main():
    manifest=read(ROOT/'manifest.json')
    assert manifest['status']=='ALL_150_VERIFIED'
    source_folds=manifest['folds']['replication']
    for model in ['MW_RGB_L19','PIXEL_CURRENT','PIXEL_HISTORY16']:
        for condition in ['L0','L4']:
            path=OUT/'transfer'/f'{model}__{condition}.json'
            assert not path.exists(),path
            started=time.monotonic()
            records={r['identity']:r for r in manifest['units'].values() if r['condition_id']==condition}
            source=sorted(i for i,r in records.items() if r['cohort']=='replication')
            destination=sorted(i for i,r in records.items() if r['cohort']!='replication')
            assert len(source)==25 and len(destination)==50 and not set(source)&set(destination)
            x={i:np.load(OUT/'features'/model/f'{i}__{condition}.npy',allow_pickle=False) for i in records}
            y={i:np.array(records[i]['targets']) for i in source}
            scores=[]
            for fold in source_folds:
                train,held=fold['training_identities'],fold['held_out_identities']
                train_matrix=np.concatenate([x[i] for i in train])
                keep=np.ptp(train_matrix,axis=0)>0
                if not keep.any():
                    predictions=np.full((len(held)*19,5),np.concatenate([y[i] for i in train]).mean())
                else:
                    predictions=predict_alphas(train_matrix[:,keep],np.concatenate([y[i] for i in train]),np.concatenate([x[i] for i in held])[:,keep])
                error=predictions-np.concatenate([y[i] for i in held])[:,None]
                scores.append(np.sqrt((error**2).reshape(5,19,5).mean(axis=1)).mean(axis=0))
            scores=np.mean(scores,axis=0)
            alpha=float(ALPHAS[np.argmin(scores)])
            train_x=np.concatenate([x[i] for i in source])
            train_y=np.concatenate([y[i] for i in source])
            keep=np.ptp(train_x,axis=0)>0
            if not keep.any():
                predictions=np.full(len(destination)*19,train_y.mean())
                maximum=0.
            else:
                predictions=predict_alphas(train_x[:,keep],train_y,np.concatenate([x[i] for i in destination])[:,keep],[alpha])[:,0]
                reference=fit_ridge(train_x[:,keep],train_y,alpha=alpha)
                maximum=max(float(np.max(abs(reference.predict(x[i][:,keep])-predictions[j*19:(j+1)*19]))) for j,i in enumerate(destination))
            assert maximum<1e-8,maximum
            # Destination targets are accessed only now, after predictions.
            cells=[]
            for j,i in enumerate(destination):
                for k,value in enumerate(predictions[j*19:(j+1)*19]):
                    r=records[i]
                    cells.append(dict(identity=i,cohort=r['cohort'],condition_id=condition,model=model,row_index=k,model_frame_idx=r['target_model_frame_indices'][k],context_age=r['context_ages'][k],target=r['targets'][k],prediction=float(value)))
            save(path,dict(cells=cells,source_identities=source,destination_identities=destination,selected_alpha=alpha,source_cv_scores=scores.tolist(),retained_source_column_indices=np.flatnonzero(keep).tolist(),constant_column_rule='Training-only exact ptp==0 removal, including within source CV.',reference_maximum_error=maximum,elapsed_seconds=time.monotonic()-started,protocol_sha256=sha(SOURCE/'scripts/generalization/TRANSFER_PROTOCOL.md'),manifest_sha256=sha(ROOT/'manifest.json')))
            print('TRANSFER',model,condition,alpha,round(time.monotonic()-started,1),flush=True)


if __name__=='__main__':
    main()

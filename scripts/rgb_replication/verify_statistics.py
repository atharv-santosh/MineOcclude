"""Reconstruct original primary/age results and check baseline replay."""
import json
import numpy as np
from audit_recovery import PKG, OUT, read, save
from mineocclude.experiment_iii.prediction_lock import PredictionLock, PredictionCell
from mineocclude.experiment_iii.statistics import primary_estimands, primary_analysis, identity_bootstrap_interval


def main():
    raw=read(PKG/'prediction_lock/PREDICTION_LOCK.json')
    lock=PredictionLock(feature_block_hashes=raw['feature_block_hashes'])
    lock.extend(PredictionCell(**x) for x in raw['cells'])
    assert lock.seal()==raw['prediction_lock_sha256']
    metrics=read(OUT/'legacy_reconstructed_metrics.json')['per_identity']
    original=read(PKG/'results/primary_results.json')
    names=sorted(metrics['MW_CURRENT/L0'])
    estimates={i:primary_estimands({f'L{c}':metrics[f'MW_CURRENT/L{c}'][i]['rmse'] for c in range(5)},original['O_c']) for i in names}
    derived=primary_analysis(estimates,lock=lock,bootstrap_seed=original['bootstrap_seed'])
    differences=[]
    for key,value in derived['estimands'].items():
        for field in ('mean','standard_error','raw_p_value','holm_adjusted_p_value'):
            differences.append(abs(value[field]-original['estimands'][key][field]))
        for field in ('point_estimate','ci_low','ci_high'):
            differences.append(abs(value['interval'][field]-original['estimands'][key]['interval'][field]))
    assert max(differences)<1e-12,max(differences)
    age_original=read(PKG/'results/context_age_results.json')
    cells={(r['identity'],r['condition_id'],r['row_index']):r for r in raw['cells'] if r['model']=='MW_CURRENT'}
    def age_rmse(identity,condition,low,high):
        return float(np.sqrt(np.mean([(cells[identity,condition,j]['prediction']-cells[identity,condition,j]['target'])**2 for j in range(low-1,high)])))
    for label,entry in age_original['bins'].items():
        for condition,value in entry['identity_macro_rmse_by_condition'].items():
            observed=np.mean([age_rmse(i,condition,entry['low'],entry['high']) for i in names])
            assert abs(observed-value)<1e-12,(label,condition,observed,value)
    interactions={i:age_rmse(i,'L4',16,19)-age_rmse(i,'L4',12,15)-np.mean([age_rmse(i,f'L{c}',16,19)-age_rmse(i,f'L{c}',12,15) for c in (1,2,3)]) for i in names}
    interval=identity_bootstrap_interval(interactions,seed=original['bootstrap_seed'])
    for field in ('point_estimate','ci_low','ci_high'):
        assert abs(interval[field]-age_original['boundary_interaction_interval'][field])<1e-12
    old={(r['identity'],r['condition_id'],r['row_index']):r for r in raw['cells'] if r['model']=='LINEAR_CURRENT_PIXEL'}
    replay=[]
    for c in range(5):
        path=OUT/'predictions'/f'PIXEL_CURRENT__L{c}.json'
        if path.exists():
            replay.extend(read(path)['cells'])
    error=max([abs(r['prediction']-old[r['identity'],r['condition_id'],r['row_index']]['prediction']) for r in replay],default=0)
    assert len(replay)==2375,len(replay)
    solver_check=read(OUT/'reference_solver_check.json')
    assert solver_check['status']=='PASS'
    report={'status':'ORIGINAL_STATISTICS_RECONSTRUCTED','original_primary_max_abs_error':max(differences),'original_primary_intervals_and_pvalues_verified':True,'original_age_bins_verified':True,'original_boundary_interaction_verified':interval,'current_pixel_replay_cells':len(replay),'current_pixel_prediction_max_abs_error':error,'cross_host_pixel_refit_identical':error<1e-5,'current_host_optimized_matches_unmodified_reference':True,'refit_note':'All 125 current-pixel feature block hashes match original inputs. The unmodified reference solver on this host reproduces the optimized implementation exactly, but some selected alphas differ from the old host. Original sealed predictions remain the source for historical tables; new-host predictions are labeled separately.'}
    save(OUT/'statistics_reconstruction_audit.json',report)
    save(OUT/'legacy_primary_reconstructed.json',derived)
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':
    main()

"""Gate fresh capture on observed disjoint pilot evidence, preserving old authority."""
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np
from audit_pilots import audit,lines,ROOT,SOURCE
from pilot import CaptureRuntime,RuntimeConfig,save


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    reports=[]
    pairs=[]
    for idx in range(6):
        rows=[]
        for cond in ['L0','L4']:
            d=ROOT/'pilots'/f'g26_p{idx:02d}_{cond}_a2'
            r=audit(d)
            reports.append(r)
            positions=np.array([s['sheep_x'] for s in lines(d/'server/server_state.jsonl')])
            rows.append(positions)
            if cond=='L0':
                assert min(r['target_magenta_areas'])>20
                assert r['historical_FIR_pixel_centered_rmse']<.15
                assert abs(r['historical_FIR_pixel_offset_median'])<.30
            else:
                assert max(r['target_magenta_areas'])==0
        assert np.array_equal(*rows)
        pairs.append(dict(pilot=idx,path_exactly_paired=True))
    config=RuntimeConfig.from_json(ROOT/'runtime.json')
    with CaptureRuntime(config) as runtime:
        runtime.start_display()
        gl=subprocess.check_output(['glxinfo','-B'],env=config.environment(),text=True)
        assert 'llvmpipe' in gl.lower(),gl
    receipt=dict(admitted=True,authority='Fresh generalization protocol, user authorized 2026-09-11. Not historical A7/P2 authorization.',cohort_sha256=sha(ROOT/'cohort_geometry_draft.json'),protocol_sha256=sha(Path(__file__).parent/'PROTOCOL.md'),pilot_count=12,pilot_pair_checks=pairs,renderer=gl,mod_sha256=sha(ROOT/'mod/build/libs/mineocclude-0.1.1.jar'),runtime_config_sha256=sha(ROOT/'runtime.json'),alignment='Retain fixed historical FIR target definition. Visible silhouette motion is an engineering diagnostic, not an exact rendered-origin measurement. Its offset is not used to alter labels.',alignment_diagnostic_limits=dict(centered_rmse_blocks=.15,absolute_median_offset_blocks=.30),reports=[{k:v for k,v in r.items() if k!='measurements'} for r in reports],no_neural_results_inspected=True)
    save(ROOT/'capture_admission.json',receipt)
    print('FRESH_CAPTURE_ADMITTED',receipt['cohort_sha256'],flush=True)


if __name__=='__main__':
    main()

from common import *
import numpy as np
from PIL import Image
from audit_pilots import measure
import argparse

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',type=int,default=3);args=parser.parse_args()
    attempt=args.attempt
    config=read(ROOT/f'motion_pilots_v{attempt}.json');roster=config['rows']
    audit_path=ROOT/f'pilot_audit_a{attempt}_{len(roster)*2}.json'
    audit=read(audit_path)
    def frames(r):
        unit=r['identity']+'__L4'
        return ROOT/f'pilots_a{config["sources"][unit]}'/unit/'client/frames'
    assert audit['complete']
    reports=audit['reports']
    assert all(r['exact_path_error']<1e-9 for r in reports)
    assert all(r['opaque_window_no_magenta'] for r in reports if r['condition']=='L4')
    aligned=[r for r in reports if r['condition']=='L0']
    assert max(r['fir_pixel_centered_rmse'] for r in aligned)<.15, 'New motion exceeds pilot alignment tolerance'
    assert max(abs(r['fir_pixel_median_offset']) for r in aligned)<.30, 'Large systematic rendered/target displacement'
    histories=[]
    for row in roster:
        base=frames(row)
        areas={t:measure(base/f'{t:06d}.png')['area'] for t in range(180)}
        counts=[sum(areas[k]>20 for k in range(t-15,t)) for t in row['target_model_frame_indices']]
        histories.append(dict(identity=row['identity'],family=row['family'],visible_prior_counts=counts))
    history_path=ROOT/f'PILOT_HISTORY_AUDIT_V{attempt}.json'
    if not history_path.exists():save(history_path,dict(histories=histories))
    assert all(h['visible_prior_counts'][0]>=3 for h in histories),'Entry window lacks sufficient image evidence'
    pairs=[]
    for family in sorted({r['family_id'] for r in roster}):
        a,b=sorted([r for r in roster if r['family_id']==family],key=lambda r:r['variant'])
        distance=[]
        for j in range(10):
            ta=a['target_model_frame_indices'][j];tb=b['target_model_frame_indices'][j]
            delta=[]
            for k in range(1,16):
                pa=frames(a)/f'{ta-k:06d}.png'
                pb=frames(b)/f'{tb-k:06d}.png'
                delta.append(float(np.mean(abs(np.asarray(Image.open(pa),dtype=float)-np.asarray(Image.open(pb),dtype=float)))))
            distance.append(float(np.mean(delta)))
        contrast=np.array(b['historical_FIR_reference_labels'])-a['historical_FIR_reference_labels']
        pairs.append(dict(family_id=family,history_pixel_mae_by_age=distance,target_contrast_by_age=contrast.tolist()))
    assert all(p['history_pixel_mae_by_age'][0]>.01 for p in pairs),'Matched histories not distinguishable at entry'
    admission=dict(status='PASS',pilot_capture_count=len(roster)*2,pilot_audit_sha256=sha(audit_path),production_roster_sha256=sha(MOTION_ROSTER),analysis_sha256=sha(Path(__file__).with_name('MOTION_ANALYSIS.md')),sample_size_reason='Retain 64 training and 64 held-out families; no fitted production outcomes inspected. Any capture-engineering amendments are separately recorded.',alignment_max_centered_rmse=max(r['fir_pixel_centered_rmse'] for r in aligned),alignment_max_offset=max(abs(r['fir_pixel_median_offset']) for r in aligned),histories=histories,pairs=pairs,claim_boundary='Distinct informative images at entry are necessary, not proof of exact parameter identification or model memory. Report decreasing observed-history support by age.')
    save(ROOT/('MOTION_ADMISSION.json' if attempt==3 else f'MOTION_ADMISSION_V{attempt}.json'),admission)
    print('MOTION_ADMISSION_PASS',admission['alignment_max_centered_rmse'],flush=True)

if __name__=='__main__':main()

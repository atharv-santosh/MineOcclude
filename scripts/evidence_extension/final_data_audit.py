from common import *
import numpy as np

def lines(path):
    return [json.loads(s) for s in path.read_text().splitlines()]

def main():
    assert read(ROOT/'PRODUCTION_COMPLETE.json')['status']=='PASS'
    roster=read(MOTION_ROSTER)['rows']
    assert len(roster)==256 and len({r['family_id'] for r in roster})==128
    assert read(MOTION_ADMISSION)['production_roster_sha256']==sha(MOTION_ROSTER)
    freeze=read(MOTION_FREEZE)
    assert freeze['roster_sha256']==sha(MOTION_ROSTER)
    assert freeze['analysis_sha256']==sha(Path(__file__).with_name('MOTION_ANALYSIS.md'))
    units={r['identity']+'__'+c for r in roster for c in ['L0','L4']}
    assert {p.parent.name for p in (ROOT/'captures').glob('*/BANKED.json')}==units
    expected_receipts={mode+'__'+u+'.json' for u in units for mode in ['pixels','700M','video']}
    assert {p.name for p in (ROOT/'motion/receipts').glob('*.json')}==expected_receipts
    action_keys=['forward','back','left','right','jump','sneak','sprint','use','attack','drop','pick_item','hotbar','camera_dx','camera_dy']
    histories=[];input_hashes={};state_error=0.
    for row in roster:
        paired=[]
        for c in ['L0','L4']:
            unit=row['identity']+'__'+c;base=ROOT/'captures'/unit
            bank=read(base/'BANKED.json');assert bank['spec_hash']==row['spec_hash']
            assert all(sha(base/k)==v for k,v in bank['files'].items())
            input_hashes[unit]=sha(base/'BANKED.json')
            state=lines(base/'server/server_state.jsonl');actions=lines(base/'client/raw_actions.jsonl')
            assert len(state)==len(actions)==180
            state_error=max(state_error,float(np.max(abs(np.array([r['sheep_x'] for r in state])-row['state_positions']))))
            paired.append([[r[k] for k in action_keys] for r in actions])
            physical=read(base/'server/physical_receipt.json')
            observed=physical['camera']['observed']
            assert physical['camera']['lock_camera']
            assert np.max(abs(np.array([observed['feet_x'],observed['eye_y'],observed['feet_z']])-row['camera']))<1e-7
            assert observed['yaw_degrees']==observed['pitch_degrees']==0
            authority=read(base/'client/client_authority.json')
            assert authority['fov_degrees']==70 and authority['fov_effect_scale']==0
            assert (authority['framebuffer_width'],authority['framebuffer_height'])==(640,360)
            assert authority['hud_hidden']
            a=read(ROOT/'motion/receipts'/('pixels__'+unit+'.json'))
            for mode in ['700M','video']:
                b=read(ROOT/'motion/receipts'/(mode+'__'+unit+'.json'))
                assert a['indices']==b['indices']==row['target_model_frame_indices']
                assert a['visible_prior_counts']==b['visible_prior_counts']
                assert a['bank_sha256']==b['bank_sha256']==input_hashes[unit]
                assert a['channel_order']==b['channel_order']=='RGB'
            if c=='L4':
                assert a['visible_prior_counts'][0]>=3
                histories.append(dict(identity=row['identity'],family_id=row['family_id'],partition=row['partition'],layout=row['layout_id'],motion_type=row['family'],visible_prior_counts=a['visible_prior_counts']))
        assert paired[0]==paired[1],row['identity']
    assert state_error<1e-9
    predictions=[r for p in (ROOT/'motion/predictions').glob('*.json') for r in read(p)['cells']]
    assert len(predictions)==82688
    stats=read(ROOT/'motion/statistics.json')
    assert len(stats['summaries'])==408 and len(stats['paired_differences'])==216
    save(ROOT/'motion/final_data_audit.json',dict(status='PASS',captures=512,independent_families=128,feature_receipts=1536,prediction_rows=len(predictions),exact_state_max_error=state_error,paired_actions_equal=True,all_camera_and_framebuffer_checks_pass=True,all_feature_modes_use_same_rgb_histories=True,bank_sha256=input_hashes,visible_history_by_identity=histories))
    print('FINAL_DATA_AUDIT_PASS',len(predictions),flush=True)

if __name__=='__main__':main()

import unittest
import tempfile
from pathlib import Path
import numpy as np
from statistics_core import bootstrap,family_scores,summarize_motion
from motion_baselines import oracle,design
from fit_diag import Ridge,predict_frozen
from motion import make
from amend_reversal_floor import revise

class Tests(unittest.TestCase):
    def test_reversal_amendment_preserves_entry_and_other_arms(self):
        old=make('reversal','layout_04','unit',1,0,True,True,True,True)
        new=revise(old)
        self.assertTrue(1.6<=new['speed_blocks_per_second']<=1.9)
        self.assertEqual(new['target_model_frame_indices'],list(range(48,67)))
        self.assertAlmostEqual(old['state_positions'][36],new['state_positions'][48],places=10)
        self.assertTrue(min(new['signed_velocities'])<0<max(new['signed_velocities']))
        other=make('velocity','layout_01','unit',0,0,True,True,True,True)
        self.assertEqual(revise(other),other)

    def test_boundary_check_uses_exact_speed_floor(self):
        old=make('reversal','layout_04','pilot_matched',1,0,True,True,True,True)
        new=revise(old,True)
        self.assertEqual(new['speed_blocks_per_second'],1.6)
        self.assertTrue(new['engineering_boundary_speed'])
        self.assertIn('pilot_boundary',new['identity'])

    def test_prepared_weights_match_live_predictions(self):
        rng=np.random.default_rng(73)
        x=rng.normal(size=(57,12));y=rng.normal(size=57);q=rng.normal(size=(38,12))
        model=Ridge(x,y)
        with tempfile.TemporaryDirectory() as directory:
            for alpha in [.1,1.,10.,100.,1000.]:
                path=Path(directory)/f'fit-{alpha}.npz'
                model.freeze(path,alpha)
                np.testing.assert_array_equal(model.predict(q,[alpha])[:,0],predict_frozen(path,q))

    def test_bootstrap_constant(self):
        self.assertEqual(bootstrap([2.,2.,2.],['a','a','b']),dict(mean=2.,ci=[2.,2.]))

    def test_family_aggregation(self):
        cells=[]
        for v in [0,1]:
            for a in range(1,20):
                cells.append(dict(family_id='f',variant=v,age=a,prediction=float(a+v+v*2),target=float(a+v),layout='layout_01',family='velocity'))
        s=family_scores(cells,1,10)['f']
        self.assertEqual(s['rmse'],1.)
        self.assertEqual(s['mae'],1.)
        self.assertEqual(s['contrast_rmse'],2.)
        self.assertEqual(s['sign_agreement'],1.)

    def test_oracle_future_independence(self):
        r=dict(target_model_frame_indices=list(range(30,49)),state_positions=list(np.arange(180)*.05),direction='LEFT_TO_RIGHT',family='velocity')
        for kind in ['ORACLE_LAST','ORACLE_CV']:
            a=oracle(r,kind)
            b=oracle({**r,'state_positions':r['state_positions'][:30]+[999.]*150},kind)
            np.testing.assert_array_equal(a,b)

    def test_metadata_target_independence(self):
        r=dict(direction='RIGHT_TO_LEFT',family='reversal')
        for kind in ['META_LINEAR','META_CUBIC','META_FAMILY']:
            np.testing.assert_array_equal(design(r,kind),design({**r,'historical_FIR_reference_labels':[999.]*19},kind))

    def test_duplicate_age_rejected(self):
        r=dict(family_id='f',variant=0,age=1,prediction=1.,target=1.,layout='layout_01',family='velocity')
        with self.assertRaises(AssertionError):family_scores([r,r,{**r,'variant':1}],1,1)

if __name__=='__main__':unittest.main()

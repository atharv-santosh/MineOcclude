import unittest
import numpy as np
from statistics_core import bootstrap,family_scores,summarize_motion
from motion_baselines import oracle,design

class Tests(unittest.TestCase):
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

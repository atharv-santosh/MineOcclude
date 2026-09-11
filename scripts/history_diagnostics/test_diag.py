import unittest
import numpy as np
from statistics_diag import interval,scores
from baselines_diag import detect,track


class DiagnosticTests(unittest.TestCase):
    def test_prediction_cardinality(self):
        per_condition=24*19
        native_six_models=6*2*(per_condition+3*per_condition)
        baselines=2*(4*per_condition+4*2*per_condition)
        transfer=4*2*2*per_condition
        self.assertEqual(native_six_models+baselines+transfer,40128)

    def test_constant_interval(self):
        self.assertEqual(interval([2.]*24),dict(mean=2.,ci95=[2.,2.]))

    def test_pair_bootstrap(self):
        x=[1.,3.,4.,8.]
        pair=interval(x,['a','a','b','b'])
        equivalent=interval([2.,6.])
        self.assertEqual(pair,equivalent)

    def test_signed_difference(self):
        self.assertEqual(interval([-2.]*24)['mean'],-2.)

    def test_identity_not_frame_weighting(self):
        rows=[dict(identity='a',age=j,target=float(j),prediction=float(j+1),donor='b') for j in range(1,20)]
        r=scores(rows,(1,10))['a']
        self.assertEqual(r['rmse'],1.)
        self.assertEqual(r['mae'],1.)

    def test_magenta_component(self):
        rgb=np.zeros((30,40,3),np.uint8)
        rgb[5:15,10:30]=[200,20,180]
        rgb[1:3,1:3]=[200,20,180]
        d=detect(rgb)
        self.assertEqual(d['area'],200)
        self.assertEqual(d['width'],20)
        self.assertEqual(d['u'],19.5)

    def test_tracker_zero_detections(self):
        c=dict(target_mean=2.,width=10.,height=10.,area=100.,beta=[0.,1.])
        self.assertEqual(track([None]*16,c),(2.,0))

    def test_tracker_linear_motion(self):
        c=dict(target_mean=2.,width=10.,height=10.,area=100.,beta=[0.,1.])
        window=[dict(width=10.,height=10.,area=100.,u=1.+.5*j) if j<8 else None for j in range(16)]
        p,n=track(window,c)
        self.assertAlmostEqual(p,8.5,places=10)
        self.assertEqual(n,8)

    def test_tracker_partial_rejection(self):
        c=dict(target_mean=2.,width=10.,height=10.,area=100.,beta=[0.,1.])
        window=[dict(width=2.,height=10.,area=20.,u=100.)]*16
        self.assertEqual(track(window,c),(2.,0))


if __name__=='__main__':
    unittest.main(verbosity=2)

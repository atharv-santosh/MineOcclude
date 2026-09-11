"""Independent small checks for the compact statistics implementation."""
import unittest
import json
import tempfile
from pathlib import Path
import numpy as np
from rebuild_statistics import identity_metrics, interval, rebuild, COHORTS, MODELS


class StatisticsTests(unittest.TestCase):
    def test_exact(self):
        self.assertEqual(identity_metrics([1, 2, 3], [1, 2, 3]), dict(rmse=0., mae=0., r2=1.))

    def test_constant(self):
        m = identity_metrics([-1, 0, 1], [0, 0, 0])
        self.assertAlmostEqual(m['rmse'], np.sqrt(2/3))
        self.assertAlmostEqual(m['mae'], 2/3)
        self.assertEqual(m['r2'], 0.)

    def test_not_pooled(self):
        a = identity_metrics([0, 1], [0, 1])['rmse']
        b = identity_metrics([0, 1], [2, 3])['rmse']
        self.assertEqual((a+b)/2, 1.)
        self.assertNotEqual((a+b)/2, np.sqrt(2))

    def test_pair_cancellation(self):
        index = np.random.default_rng(0).integers(0, 25, (10000, 25))
        baseline = np.linspace(0, 3, 25)
        out = interval((baseline + .5) - baseline, index)
        self.assertEqual(out['mean'], .5)
        np.testing.assert_allclose(out['ci95'], [.5, .5], atol=1e-14)

    def test_r2_negative(self):
        self.assertLess(identity_metrics([0, 1, 2], [5, 5, 5])['r2'], 0.)

    def test_complete_synthetic_snapshot_and_duplicate_rejection(self):
        # This fixture never enters a scientific output or manuscript.
        cells=[]
        for cohort in COHORTS:
            for i in range(25):
                for condition in ['L0','L4']:
                    for m,model in enumerate(MODELS):
                        for j in range(19):
                            cells.append(dict(identity=f'test_{cohort}_{i}',cohort=cohort,condition_id=condition,
                                model=model,outer_fold=i%5,row_index=j,model_frame_idx=30+j,context_age=j+1,
                                target=float(j),prediction=float(j+m)))
        with tempfile.TemporaryDirectory(prefix='mineocclude-statistics-test-') as directory:
            path=Path(directory)/'synthetic.json'
            path.write_text(json.dumps(dict(cells=cells)))
            result=rebuild(directory)
            self.assertEqual(result['cells'],19950)
            self.assertEqual(len(result['summaries']),42)
            for row in result['summaries']:
                self.assertEqual(row['rmse']['mean'],MODELS.index(row['model']))
            for row in result['paired_contrasts']:
                if row['contrast']=='MW_RGB_L19-minus-PIXEL_HISTORY16':
                    self.assertEqual(row['mean'],-2.)
                    self.assertEqual(row['ci95'],[-2.,-2.])
            cells[-1]=dict(cells[-2])
            path.write_text(json.dumps(dict(cells=cells)))
            with self.assertRaises(AssertionError):
                rebuild(directory)


if __name__ == '__main__':
    unittest.main()

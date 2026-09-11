import tempfile
import unittest
from pathlib import Path
from finalize_delivery import dependencies


class DependencyTests(unittest.TestCase):
    def test_nested_input_rows_figures_and_style(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'paper.tex').write_text(r'\usepackage{graphicx,local}\input{appendix}\includegraphics[width=1cm]{graph}\bibliography{refs}')
            (root / 'appendix.tex').write_text(r'\tablerows{rows.tex}')
            for name in ['local.sty', 'graph.pdf', 'refs.bib', 'rows.tex']:
                (root / name).write_text('')
            self.assertEqual(dependencies(root), ['appendix.tex', 'graph.pdf', 'local.sty', 'paper.tex', 'refs.bib', 'rows.tex'])

    def test_reject_missing_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'paper.tex').write_text(r'\input{missing}')
            with self.assertRaises(AssertionError):
                dependencies(root)


if __name__ == '__main__':
    unittest.main()

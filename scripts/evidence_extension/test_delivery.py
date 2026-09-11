import tempfile
import unittest
from pathlib import Path
from finalize_delivery import dependencies
from stage_overleaf import rewrite


class DependencyTests(unittest.TestCase):
    def test_nested_input_rows_figures_and_style(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'paper.tex').write_text(r'\usepackage{graphicx,local}\input{appendix}\includegraphics[width=1cm]{graph}\bibliography{refs}')
            (root / 'appendix.tex').write_text(r'\tablerows{rows.tex} \tablerows unbraced.tex')
            for name in ['local.sty', 'graph.pdf', 'refs.bib', 'rows.tex', 'unbraced.tex']:
                (root / name).write_text('')
            self.assertEqual(dependencies(root), ['appendix.tex', 'graph.pdf', 'local.sty', 'paper.tex', 'refs.bib', 'rows.tex', 'unbraced.tex'])

    def test_reject_missing_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'paper.tex').write_text(r'\input{missing}')
            with self.assertRaises(AssertionError):
                dependencies(root)

    def test_overleaf_paths_isolate_dependencies_only(self):
        original = r'\usepackage[review]{neurips_2026}\usepackage{graphicx}\input{appendix}\tablerows rows.tex \includegraphics{graph.pdf}\bibliography{refs}'
        names = {'neurips_2026.sty', 'appendix.tex', 'rows.tex', 'graph.pdf', 'refs.bib'}
        transformed = rewrite(original, names)
        self.assertIn(r'\usepackage[review]{evidence-extension/neurips_2026}', transformed)
        self.assertIn(r'\usepackage{graphicx}', transformed)
        self.assertIn(r'\input{evidence-extension/appendix}', transformed)
        self.assertIn(r'\tablerows evidence-extension/rows.tex', transformed)
        self.assertIn(r'\includegraphics{evidence-extension/graph.pdf}', transformed)
        self.assertIn(r'\bibliography{evidence-extension/refs}', transformed)


if __name__ == '__main__':
    unittest.main()

import ast
import re
import unittest
from pathlib import Path
from build_paper import PREVIOUS,update_checklist

class PresentationTests(unittest.TestCase):
    def test_checklist_retains_all_questions_and_answers(self):
        tree=ast.parse(Path(__file__).with_name('build_paper.py').read_text())
        value=next(n.value for n in ast.walk(tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='justifications' for t in n.targets))
        changes=ast.literal_eval(value)
        original=(PREVIOUS/'checklist.tex').read_text()
        changed=update_checklist(original,changes)
        for field in ['Question','Answer']:
            pattern=rf'(?m)^.*{field}:.*$'
            self.assertEqual(re.findall(pattern,original),re.findall(pattern,changed))
        self.assertEqual(len(re.findall(r'Question:',changed)),16)
        for text in changes.values():self.assertIn(text,changed)

    def test_existing_section_boundaries(self):
        text=(PREVIOUS/'paper.tex').read_text()
        for name in ['Metrics and inference','Prospective history and transfer tests','From readout development to a new cohort','Position decoding across visual evidence','Context age and decoder depth','Fresh identities and history dependence','Interpretation and limitations']:
            self.assertEqual(text.count(r'\subsection{'+name+'}'),1,name)
        self.assertIn('\\clearpage\n\\bibliographystyle',text)
        self.assertIn('\\clearpage\n\\input{checklist}',text)

if __name__=='__main__':unittest.main()

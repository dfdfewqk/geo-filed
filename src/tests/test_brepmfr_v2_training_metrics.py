"""Check model's real held-out confusion aggregation when Torch is available.

Optional native dependencies skip in the lean backend CI, but never invent
successful learning. Source-only assertions still check guarded reporting.
"""
from __future__ import annotations
import ast
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
RESEARCH=ROOT/"research"/"brepmfr_v2"
sys.path.insert(0,str(RESEARCH))
import train_research as training

try:
    import torch
    import numpy as np
except ImportError:
    torch=None;np=None


class ResearchEvaluationSource(unittest.TestCase):
    def test_hole_only_and_family_metrics_derived_inside_one_evaluation_pass(self):
        tree=ast.parse((RESEARCH/"train_research.py").read_text(encoding="utf8"))
        funcs={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
        evaluation=ast.unparse(funcs["evaluate"])
        training_source=ast.unparse(funcs["train"])
        self.assertIn("hole_macro_f1",evaluation)
        self.assertIn("per_family",evaluation)
        self.assertIn("family[actual, predicted] += 1",evaluation)
        self.assertEqual(training_source.count("evaluate(net, splits['test'], device)"),1)
        self.assertIn("eligible_for_production",training_source)
        self.assertIn("False",training_source)


@unittest.skipUnless(torch is not None and np is not None,
                    "Requires explicit Torch+NumPy research runtime")
class ActualResearchEvaluation(unittest.TestCase):
    def test_family_confusion_and_hole_macro_computed_from_same_forward(self):
        class ToyModel:
            def eval(self):return self
            def __call__(self,fa,fg,neigh,edges):
                # deterministic predictions encoded in a synthetic feature
                predicted=fa[:,0].long().tolist()
                score=torch.full((len(predicted),3),-5.,dtype=torch.float32)
                for i,k in enumerate(predicted):
                    score[i,k]=5.
                return score

        with tempfile.TemporaryDirectory(prefix="geofield-v2-research-eval-") as temp:
            entries=[]
            for family,target,pred in (
                ("family_through",1,1),
                ("family_through",1,0),
                ("family_blind",2,2),
                ("family_blind",2,1),
                ("family_other",0,0)):
                idx=len(entries);path=Path(temp)/f"{idx}.npz"
                fa=np.zeros((1,14),dtype=np.float32);fa[0,0]=pred
                np.savez_compressed(path,
                    face_attr=fa,face_grid=np.zeros((1,7,10,10),dtype=np.float32),
                    edge_attr=np.zeros((1,15),dtype=np.float32),
                    edge_grid=np.zeros((1,12,10),dtype=np.float32),
                    edge_index=np.array([[0],[0]],dtype=np.int64),
                    target=np.array([target],dtype=np.int64))
                entries.append(({"family":family,"id":f"test_{idx}"},path))
            report=training.evaluate(ToyModel(),entries,torch.device("cpu"))
            self.assertEqual(report["confusion_matrix"],[[1,0,0],[1,1,0],[0,1,1]])
            self.assertEqual(report["per_family"]["family_through"]["hole_recall"]["through_hole"],.5)
            self.assertEqual(report["per_family"]["family_blind"]["hole_recall"]["blind_hole"],.5)
            self.assertEqual(report["per_family"]["family_other"]["hole_recall"]["blind_hole"],None)
            self.assertAlmostEqual(report["hole_macro_f1"],(2/3+2/3)/2)
            self.assertEqual(sum(x["supervised_faces"] for x in report["per_family"].values()),5)
            self.assertTrue(report["other_face_support_is_no_hole_designs_only"])


if __name__=="__main__":
    unittest.main()

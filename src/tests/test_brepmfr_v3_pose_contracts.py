"""B07 v3 regression: true geometric feature transforms and held-out guards.

Optional numerical tests run when NumPy is installed. Lean generic CI does
not install private converter, Torch, CadQuery, sklearn or old checkpoints.
"""
import ast
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
RESEARCH=ROOT/"research"/"brepmfr_v2"
sys.path.insert(0,str(RESEARCH))
import train_pose_invariant as stage
import invariant_features as features

try:
    import numpy as np
except ImportError:
    np=None


class ResearchV3Source(unittest.TestCase):
    def test_never_production_and_new_test_after_validation(self):
        source=(RESEARCH/"train_pose_invariant.py").read_text(encoding="utf8")
        tree=ast.parse(source)
        funcs={x.name:ast.unparse(x) for x in tree.body
               if isinstance(x,ast.FunctionDef)}
        training=funcs["train"]
        self.assertIn("eligible_for_production",training)
        self.assertIn("replace_epoch43",training)
        self.assertIn("held_out_test_used_for_tuning",training)
        self.assertIn("False",training)
        self.assertLess(training.index('val = evaluate(model, grouped[\'val\'])'),
                        training.index('test = evaluate(best, grouped[\'test\'])'))
        self.assertEqual(training.count("evaluate(best, grouped['test'])"),1)

    def test_new_geometry_splits_and_previous_families_cannot_leak(self):
        old={"schema":"geofield-v2-2-generalization-v1",
             "converter_sha256":stage.CONVERTER_SHA256,
             "rows":[{"id":"a","family":"previous","label":"no_hole",
                      "graph_path":"/tmp/a.npz"}]}
        new={"schema":"gf-v3-pose-invariant-v1",
             "model_production_eligible":False,
             "old_14_evaluated_families_as_train_only":True,
             "split":{"train":["fresh_train"],"val":["fresh_val"],
                      "test":["fresh_test"]},
             "rows":[]}
        with self.assertRaises(ValueError):
            stage.validate_manifests(old,new)
        new["split"]["test"]=["previous"]
        with self.assertRaises(ValueError):
            stage.validate_manifests(old,new)
        new["split"]["test"]=["fresh_val"]
        with self.assertRaises(ValueError):
            stage.validate_manifests(old,new)

    def test_unknown_or_unsafe_manifest_is_rejected(self):
        with self.assertRaises(ValueError):
            stage.validate_manifests(
                {"schema":"unknown"},{"schema":"unknown"})


@unittest.skipUnless(np is not None,"Native NumPy geometric invariance in dedicated ML runner")
class NumericalPoseInvariantRegression(unittest.TestCase):
    @staticmethod
    def graph():
        n=2
        fa=np.zeros((n,14),dtype=np.float32)
        fa[:,0]=[1,0];fa[:,1]=[.35,.9]
        fa[:,2:5]=[[0.1,0.2,0.3],[.5,.6,.7]]
        grid=np.zeros((n,7,10,10),dtype=np.float32)
        u=np.linspace(-1,1,10);v=np.linspace(-.7,.7,10)
        for i in range(n):
            for j,a in enumerate(u):
                for k,b in enumerate(v):
                    grid[i,0:3,j,k]=[np.cos(a)*.15+i*.25,
                                    np.sin(a)*.15,b*.25+i*.1]
                    grid[i,3:6,j,k]=[np.cos(a),np.sin(a),0]
                    grid[i,6,j,k]=1.
        return {"face_attr":fa,"face_grid":grid,
                "edge_index":np.array([[0,1],[1,0]],dtype=np.int64),
                "edge_attr":np.zeros((2,15),dtype=np.float32)}

    def test_global_rotation_and_translation_do_not_change_local_features(self):
        base=self.graph();x=features.face_features(base)
        a=np.deg2rad(37)
        b=np.deg2rad(79)
        rz=np.array([[np.cos(a),-np.sin(a),0],
                     [np.sin(a),np.cos(a),0],[0,0,1]])
        rx=np.array([[1,0,0],[0,np.cos(b),-np.sin(b)],
                     [0,np.sin(b),np.cos(b)]])
        r=rz@rx
        g={k:v.copy() for k,v in base.items()}
        g["face_attr"][:,2:5]=base["face_attr"][:,2:5]@r.T+np.array([35,-27,15])
        for i in range(2):
            raw=base["face_grid"][i,0:3].reshape(3,-1).T
            norm=base["face_grid"][i,3:6].reshape(3,-1).T
            g["face_grid"][i,0:3]=(raw@r.T+[35,-27,15]).T.reshape(3,10,10)
            g["face_grid"][i,3:6]=(norm@r.T).T.reshape(3,10,10)
        y=features.face_features(g)
        self.assertEqual(x.shape,(2,39))
        np.testing.assert_allclose(x,y,rtol=2e-5,atol=2e-5)

    def test_nonfinite_and_out_of_bounds_graphs_rejected(self):
        g=self.graph();g["face_attr"][0,1]=np.nan
        with self.assertRaises(ValueError):features.face_features(g)
        g=self.graph();g["edge_index"][1,0]=9
        with self.assertRaises(ValueError):features.face_features(g)


if __name__=="__main__":
    unittest.main()

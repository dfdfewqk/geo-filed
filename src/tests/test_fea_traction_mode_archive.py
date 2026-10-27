"""Regression: two differently loaded C3D10 runs are NOT same physics.

Uses a small temporary SQLite record only; never opens user data or calls
the solver. An actual, source-reverified case would pass restore_payload.
"""
from __future__ import annotations
import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
import types

# The actual FEA comparison imports the installed, private fea_restore at
# module-load time. For this pure SQLite identity regression only, isolate that
# import; all verification behavior remains inside the production _side.
with patch.dict(sys.modules, {"fea_restore": types.ModuleType("fea_restore")}):
    sys.modules["fea_restore"].restore_payload = lambda *_a, **_kw: (_ for _ in ()).throw(
        AssertionError("restore_payload must be patched in this test"))
    from fea_compare import _side
    from fea_convergence import _physics, assess

SHA="a"*64
RUN="b"*32
RECORD="c"*32
CASE="d"*64


class ArchiveTractionIdentity(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir=Path(self.tmp.name)
        self.db=self.dir/"history.sqlite3"
        summary={"fea":{"state":"complete","result_run_id":RUN,
                         "maximum_von_mises_mpa":21.0,"maximum_displacement_mm":.09},
                 "cad":{"sha256":SHA}}
        with sqlite3.connect(self.db) as cx:
            cx.execute("CREATE TABLE snapshots(id TEXT, stage TEXT, job_id TEXT, cad_sha256 TEXT, cad_name TEXT, created_at TEXT, summary_json TEXT)")
            cx.execute("INSERT INTO snapshots VALUES(?,?,?,?,?,?,?)",
                       (RECORD,"fea_result",RUN,SHA,"test","2026-10-27",json.dumps(summary)))
        self.case={"cad_sha256":SHA,"case_sha256":CASE,
            "mesh_request":{"target_element_size_mm":3.,"element_type":"C3D10",
                            "traction_model":"straight_tri6_full_consistent"},
            "material":{"name":"metal","young_modulus_mpa":200000.,"poisson_ratio":.3},
            "boundary_conditions":{"total_force_n":29.41995,"force_direction_unit":[0,0,-1],
                                  "fixed_face_ids":[1],"load_face_ids":[2]}}
        self.result={"cad_sha256":SHA,"case_sha256":CASE,
            "mesh":{"element_type":"C3D10","traction_model":"straight_tri6_full_consistent",
                    "node_count":20,"tetrahedron_count":5},
            "solver":"CalculiX ccx","mesher":"Gmsh",
            "results":{"maximum_nodal_von_mises_mpa":21.0,"maximum_displacement_mm":.09}}
        self.payload={"sha":SHA,"case":self.case}

    def read(self):
        with patch("fea_compare.restore_payload",
                   return_value=(self.payload,RUN,self.result,None)):
            return _side(self.db,self.dir,RECORD)

    def test_read_reverified_full_tri6_preserves_physics(self):
        data=self.read()
        self.assertEqual(data["traction_model"],"straight_tri6_full_consistent")
        self.assertEqual(_physics(data)["traction_model"],"straight_tri6_full_consistent")

    def test_old_default_is_backward_compatible(self):
        self.case["mesh_request"].pop("traction_model")
        self.result["mesh"].pop("traction_model")
        data=self.read()
        self.assertEqual(data["traction_model"],"free_node_moment_equivalent")

    def test_saved_vs_solved_traction_conflict_is_refused(self):
        self.result["mesh"]["traction_model"]="free_node_moment_equivalent"
        with self.assertRaisesRegex(ValueError,"표면 하중 방식"):
            self.read()

    def test_illegal_full_tri6_with_c3d4_is_refused(self):
        self.case["mesh_request"]["element_type"]="C3D4"
        self.result["mesh"]["element_type"]="C3D4"
        with self.assertRaisesRegex(ValueError,"표면 하중 방식"):
            self.read()

    def test_mesh_comparison_must_not_combine_different_traction(self):
        a={"traction_model":"straight_tri6_full_consistent","element_type":"C3D10"}
        b={"traction_model":"free_node_moment_equivalent","element_type":"C3D10"}
        self.assertNotEqual(_physics(a),_physics(b))
        self.assertEqual(_physics({"element_type":"C3D4"})["traction_model"],
                         "free_node_moment_equivalent")
        # No real files in this unit test. assess() must reject the unequal
        # physics before doing any mesh-size/load/INP numerical comparisons.
        base=dict(cad_sha256=SHA,material="metal",young_modulus_mpa=200000.,
                  poisson_ratio=.3,fixed_faces=[1],load_faces=[2],
                  force_n=29.41995,direction=[0.,0.,-1.],
                  external_mass_kg=None,analysis_type=None,load_interpretation=None,
                  self_weight_applied=False,gravity_density_kg_m3=None,
                  gravity_direction=None,gravity_mm_s2=None,
                  solver="ccx",mesher="gmsh",element_type="C3D10",
                  mesh_target_mm=3.,mesh_node_count=20,mesh_tetrahedron_count=5,
                  max_stress_mpa=21.,max_displacement_mm=.09,
                  evidence="real_solver_files_revalidated")
        rows={}
        for i,traction in enumerate((a["traction_model"],b["traction_model"],
                                    a["traction_model"])):
            ident=str(i+1)*32
            rows[ident]=dict(base,snapshot_id=ident,run_id=str(i+4)*32,
                             traction_model=traction,mesh_target_mm=3.-i*.5)
        with patch("fea_convergence._side",side_effect=lambda _db,_jobs,record:rows[record]):
            with self.assertRaisesRegex(ValueError,"조건"):
                assess("unused",self.dir,list(rows))


if __name__=="__main__":
    unittest.main()

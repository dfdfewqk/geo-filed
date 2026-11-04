"""Verify cross-geometry FEA comparator: synthetic reverified solver rows only.

This isolates the real production function and never opens STEP/solver/SQLite.
"""
import ast
import math
import re
import unittest
from pathlib import Path

SRC=(Path(__file__).resolve().parents[1]/"fea_compare.py").read_text(encoding="utf8")
NODE=next(n for n in ast.parse(SRC).body if isinstance(n,ast.FunctionDef)
          and n.name=="compare_d6_geometry_variant")
SCOPE={"math":math,"re":re}
exec(compile(ast.fix_missing_locations(ast.Module(body=[NODE],type_ignores=[])),
             "fea_compare.py","exec"),SCOPE)
RUN_A="1"*32
RUN_B="2"*32
SNAP_A="3"*32
SNAP_B="4"*32
SHA_A="a"*64
SHA_B="b"*64
CASE_A="c"*64
CASE_B="d"*64
LINEAGE={
 "source":"server_OCP_postexport_reverified",
 "operation":"lbracket_d55_to_d60_4_through_copy_v1",
 "source_sha256":SHA_A,
 "variant_sha256":SHA_B,
 "geometry_only_verified":True,
 "structural_improvement_verified":False,
 "needs_new_face_selection":True}
def original():
    return {
      "snapshot_id":SNAP_A,"run_id":RUN_A,"cad_sha256":SHA_A,"case_sha256":CASE_A,
      "cad_name":"L_bracket.step",
      "evidence":"real_solver_files_revalidated",
      "max_stress_mpa":20.,"max_displacement_mm":0.03,
      "mesh_target_mm":1.8,"mesh_node_count":1000,"mesh_tetrahedron_count":3500,
      "material":"Steel","young_modulus_mpa":200000.,"poisson_ratio":0.3,
      "fixed_faces":[1,2],"load_faces":[3],
      "force_n":49.05,"direction":[0.,0.,-1.],
      "external_mass_kg":5.,
      "gravity_density_kg_m3":None,"gravity_mm_s2":None,
      "gravity_direction":None,"self_weight_applied":False,
      "load_interpretation":"force", "element_type":"C3D4",
      "traction_model":"free_node_moment_equivalent",
      "solver":"CalculiX","mesher":"Gmsh","analysis_type":"linear_static"}
def variant():
    row=original()
    row.update(snapshot_id=SNAP_B,run_id=RUN_B,cad_sha256=SHA_B,
               case_sha256=CASE_B,cad_name="L_bracket_D6_separate.step",
               max_stress_mpa=18.,max_displacement_mm=.027,
               mesh_node_count=1250,mesh_tetrahedron_count=4400,
               fixed_faces=[22,28],load_faces=[33])
    return row
def cmp(left=None,right=None,link=None):
    rows={SNAP_A:original() if left is None else left,
          SNAP_B:variant() if right is None else right}
    seen=[]
    def loader(_db,_root,sid):
        seen.append(sid)
        return rows[sid]
    data=SCOPE["compare_d6_geometry_variant"](
        "RO-FAKE","NOT-A-PATH",SNAP_A,SNAP_B,
        LINEAGE if link is None else link,load_side=loader,
        load_physics=lambda root,a,b:{
          "status":"real_two_inp_load_support_screen_passed",
          "source":"two_real_reverified_inp_decks_node_boundary_cload",
          "read_only":True,"gravity_body_loads_included":False,
          "support_bounding_screen_passed":True,
          "applied_load_and_moment_screen_passed":True,
          "physical_cad_surface_correspondence_verified":False,
          "reaction_equilibrium_correspondence_verified":False,
          "geometry_improvement_verified":False,
          "structural_safety_certified":False,
          "support_bbox_max_drift_mm":0.,
          "load_bbox_max_drift_mm":0.,
          "load_center_distance_mm":0.,
          "resultant_drift_n":0.,
          "load_moment_change_n_mm":0.,
          "load_moment_equivalent_lever_arm_change_mm":0.})
    return data,seen

class OriginalD6Comparison(unittest.TestCase):
    def test_independent_runs_are_observations_not_improvement(self):
        data,calls=cmp()
        self.assertEqual(calls,[SNAP_A,SNAP_B])
        self.assertEqual(data["status"],"two_different_cad_real_solver_runs_descriptive_only")
        self.assertEqual(data["original"]["cad_sha256"],SHA_A)
        self.assertEqual(data["variant"]["cad_sha256"],SHA_B)
        self.assertEqual(data["stress_change"]["absolute_difference"],-2.)
        self.assertAlmostEqual(data["stress_change"]["percent_vs_original"],-10.)
        self.assertAlmostEqual(data["displacement_change"]["percent_vs_original"],-10.)
        for flag in ("fixed_and_loaded_surface_equivalence_verified",
                     "reaction_and_applied_moment_equivalence_verified",
                     "design_improvement_verified","structural_safety_certified"):
            self.assertFalse(data[flag])
        self.assertTrue(data["read_only"])
        self.assertTrue(data["support_location_screen_passed"])
        self.assertTrue(data["applied_load_moment_screen_passed"])
        self.assertEqual(data["physical_load_screen"]["load_center_distance_mm"],0.)

    def test_untrusted_lineage_rejected_before_record_access(self):
        for link in ({},None,{**LINEAGE,"source":"user_claim"},
                     {**LINEAGE,"structural_improvement_verified":True}):
            with self.subTest(link=link):
                calls=[]
                def loader(*args):
                    calls.append(args)
                    raise AssertionError("unexpected IO")
                with self.assertRaises(ValueError):
                    SCOPE["compare_d6_geometry_variant"](
                       "db","root",SNAP_A,SNAP_B,link,load_side=loader)
                self.assertEqual(calls,[])

    def test_valid_looking_but_wrong_sha_link_rejected_against_actual_runs(self):
        # A syntactically valid SHA cannot be judged before reading and
        # independently verifying the actual saved candidate run.
        with self.assertRaises(ValueError):
            cmp(link={**LINEAGE,"variant_sha256":"f"*64})

    def test_identity_and_independent_real_fea_required(self):
        for bad in ({**variant(),"cad_sha256":SHA_A},
                    {**variant(),"cad_sha256":"f"*64},
                    {**variant(),"case_sha256":CASE_A},
                    {**variant(),"run_id":RUN_A},
                    {**variant(),"evidence":"saved_numbers_only"},
                    {**variant(),"max_stress_mpa":float("nan")}):
            with self.subTest(value=bad):
                with self.assertRaises(ValueError):
                    cmp(right=bad)

    def test_material_force_mesh_gravity_and_faces_fail_closed(self):
        edits=(
            {"material":"Aluminum"},
            {"young_modulus_mpa":70000.},
            {"force_n":50.},
            {"direction":[0.,1.,0.]},
            {"mesh_target_mm":1.2},
            {"self_weight_applied":True},
            {"gravity_density_kg_m3":7850.},
            {"element_type":"C3D10"},
            {"fixed_faces":[]},
            {"load_faces":None}
        )
        for update in edits:
            with self.subTest(change=update):
                with self.assertRaises(ValueError):
                    cmp(right={**variant(),**update})

    def test_same_step_comparator_is_not_relaxed(self):
        self.assertIn("if left_sha != right_sha:",SRC)
        self.assertIn("서로 다른 STEP 원본의 FEA 기록은 비교할 수 없습니다.",SRC)
        self.assertNotIn("gf_agent_llm_optional(",SRC)
        self.assertNotIn("run_real_fea(",ast.get_source_segment(SRC,NODE))
        self.assertNotIn("sqlite3.connect(",ast.get_source_segment(SRC,NODE))

if __name__=="__main__":
    unittest.main()

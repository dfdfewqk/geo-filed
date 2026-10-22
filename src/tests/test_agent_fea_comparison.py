"""Stage 5: actual production agent commentary on reverified FEA comparisons.

Inputs are synthetic representations of the existing fea_compare.compare output.
No real Windows solver, result files, user database, or archive is touched.
"""
from __future__ import annotations
import ast
import copy
from pathlib import Path
import unittest

SOURCE=Path(__file__).resolve().parents[1]/"payload"/"GeoField_CAD_Analysis.py"
src=SOURCE.read_text(encoding="utf-8")
tree=ast.parse(src)
parts=[n for n in tree.body if isinstance(n,ast.FunctionDef) and
       n.name=="gf_agent_compare_verified_runs"]
assert len(parts)==1, "Production FEA agent comparison missing"
env={}
exec(compile(ast.Module(body=parts,type_ignores=[]),str(SOURCE),"exec"),env)
review=env["gf_agent_compare_verified_runs"]
CAD="a"*64
CASE1="b"*64
CASE2="c"*64
RUN1="1"*32
RUN2="2"*32
S1="3"*32
S2="4"*32

def pair():
    base={
        "snapshot_id":S1,"run_id":RUN1,"cad_sha256":CAD,"case_sha256":CASE1,
        "evidence":"real_solver_files_revalidated",
        "max_stress_mpa":12.0,"max_displacement_mm":0.04,
        "material":"steel","young_modulus_mpa":210000,"poisson_ratio":0.3,
        "fixed_faces":[1],"load_faces":[3],"force_n":49.05,
        "direction":[0,0,-1],"external_mass_kg":5,
        "self_weight_applied":False,"gravity_density_kg_m3":None,
        "gravity_direction":None,"gravity_mm_s2":None,
        "mesh_target_mm":2.0,"mesh_node_count":1200,
        "mesh_tetrahedron_count":2000,
        "solver":"calculix","mesher":"gmsh",
        "analysis_type":"linear_static","load_interpretation":"distributed"
    }
    second=copy.deepcopy(base)
    second.update(snapshot_id=S2,run_id=RUN2,case_sha256=CASE2,
                  force_n=58.86,external_mass_kg=6,
                  max_stress_mpa=15.0,max_displacement_mm=0.05)
    return base,second

def comparison(left=None,right=None):
    if left is None or right is None:left,right=pair()
    delta=lambda k:{
        "absolute_difference":right[k]-left[k],
        "percent_vs_left":((right[k]-left[k])/left[k]*100 if left[k] else None)}
    return {
        "status":"verified_read_only_comparison",
        "left":left,"right":right,
        "same_cad":left["cad_sha256"]==right["cad_sha256"],
        "same_material":left["material"]==right["material"],
        "same_boundary_conditions":left["force_n"]==right["force_n"],
        "same_mesh_target":left["mesh_target_mm"]==right["mesh_target_mm"],
        "stress_change":delta("max_stress_mpa"),
        "displacement_change":delta("max_displacement_mm")}

class AgentFeaComparison(unittest.TestCase):
    def test_verified_same_cad_explicit_condition_differences_without_causal_claim(self):
        data=comparison()
        saved=copy.deepcopy(data)
        result=review(data)
        self.assertEqual(data,saved)
        self.assertEqual(result["status"],"same_cad_verified_runs_descriptive_comparison")
        self.assertEqual(result["changes"],["force","external_mass"])
        self.assertIn("self_weight",result["unverified_condition_groups"])
        self.assertEqual(result["stress_change"],data["stress_change"])
        self.assertEqual(result["displacement_change"],data["displacement_change"])
        self.assertEqual(result["left_run_id"],RUN1)
        self.assertEqual(result["right_run_id"],RUN2)
        self.assertFalse(result["causal_effect_verified"])
        self.assertFalse(result["structural_safety_verified"])
        self.assertFalse(result["element_type_comparable"])
    def test_no_change_is_not_proof_of_safety_or_mesh_convergence(self):
        a,b=pair()
        b["force_n"]=a["force_n"];b["external_mass_kg"]=a["external_mass_kg"]
        result=review(comparison(a,b))
        self.assertEqual(result["changes"],[])
        self.assertFalse(result["mesh_convergence_verified"])
        self.assertFalse(result["causal_effect_verified"])
    def test_different_cad_blocks_numerical_agent_attribution(self):
        a,b=pair();b["cad_sha256"]="f"*64
        result=review(comparison(a,b))
        self.assertEqual(result["status"],"different_cad_not_comparable")
        self.assertIsNone(result["stress_change"])
        self.assertIsNone(result["displacement_change"])
    def test_wrong_same_cad_claim_is_rejected(self):
        data=comparison();data["same_cad"]=False
        self.assertEqual(review(data)["status"],"not_verified")
    def test_missing_source_provenance_rejected(self):
        data=comparison();data["right"]["evidence"]="cached_unverified_json"
        self.assertIsNone(review(data)["stress_change"])
    def test_reused_run_id_rejected(self):
        data=comparison();data["right"]["run_id"]=RUN1
        self.assertEqual(review(data)["status"],"not_verified")
    def test_reused_snapshot_id_rejected(self):
        data=comparison();data["right"]["snapshot_id"]=S1
        self.assertEqual(review(data)["status"],"not_verified")
    def test_wrong_run_identifier_rejected(self):
        data=comparison();data["left"]["run_id"]="not-id"
        self.assertEqual(review(data)["status"],"not_verified")
    def test_wrong_case_hash_rejected(self):
        data=comparison();data["right"]["case_sha256"]="missing"
        self.assertEqual(review(data)["status"],"not_verified")
    def test_non_verified_comparator_status_rejected(self):
        data=comparison();data["status"]="archive_cache_only"
        self.assertEqual(review(data)["status"],"not_verified")
    def test_wrong_original_delta_rejected(self):
        data=comparison();data["stress_change"]["absolute_difference"]=999
        self.assertIsNone(review(data)["stress_change"])
    def test_wrong_percent_rejected(self):
        data=comparison();data["displacement_change"]["percent_vs_left"]=999
        self.assertEqual(review(data)["status"],"not_verified")
    def test_nonfinite_measured_value_rejected(self):
        data=comparison();data["left"]["max_stress_mpa"]=float("nan")
        self.assertEqual(review(data)["status"],"not_verified")
    def test_zero_baseline_does_not_invent_a_percent(self):
        a,b=pair()
        a["max_stress_mpa"]=0
        result=review(comparison(a,b))
        self.assertEqual(result["status"],"same_cad_verified_runs_descriptive_comparison")
        self.assertIsNone(result["stress_change"]["percent_vs_left"])
    def test_missing_condition_is_uncertain_not_equal(self):
        data=comparison();data["left"].pop("mesh_node_count")
        result=review(data)
        self.assertIn("mesh",result["unverified_condition_groups"])
        self.assertNotIn("mesh",result["changes"])
    def test_existing_api_uses_real_comparator_before_agent(self):
        self.assertIn("data=compare_verified_fea(HISTORY_DB,JOBS_DIR",src)
        self.assertIn("data['agent_review']=gf_agent_compare_verified_runs(data)",src)

if __name__=="__main__":
    unittest.main()

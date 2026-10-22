"""FEA spatial evidence regression: actual production pure function, synthetic mesh.

The field fixture is not a real CalculiX run. These tests verify that the
agent maps only provenance-bound FRD-shaped SURFACE-node maxima to non-authoritative
CAD triangle proximity (never a proven FEA-to-CAD face or hotspot cause).
"""
import copy
import math
import unittest
from test_agent_evidence import env, CAD, CASE, RUN, JOB

spatial=env["gf_agent_fea_spatial"]

def cad():
    return {"sha256":CAD,"mesh":{
        "positions":[[0,0,0],[10,0,0],[10,10,0],[0,10,0]],
        "triangles":[[0,1,2],[0,2,3]],
        "face_ids":[6,6]}}

def fea():
    return {"status":"INP_STA_FRD_reverified",
            "run_id":RUN,"case_sha256":CASE,"cad_sha256":CAD,
            "maximum_von_mises_mpa":16.0,"maximum_displacement_mm":0.3}

def field():
    return {"schema":"geofield-fea-surface-field-v1",
            "source":"actual_calculix_ascii_frd",
            "cad_sha256":CAD,"case_sha256":CASE,
            "run_id":RUN,"cad_job_id":JOB,
            "positions_mm":[[2,3,0],[7,6,0],[4,2,0]],
            "triangles":[[0,1,2]],
            "von_mises_mpa":[2.0,14.5,4.0],
            "displacements_mm":[[0,0,0],[0,.1,0],[0,0,.2]]}

def features():
    return {"schema":"geofield-agent-cad-features-v1",
            "cad_sha256":CAD,"cad_job_id":JOB,
            "face_ids":[6],"fea_hotspots_verified":False}

class AgentFeaSpatialTests(unittest.TestCase):
    def run_spatial(self):
        inputs=(fea(),cad(),field(),features())
        old=copy.deepcopy(inputs)
        res=spatial(*inputs)
        self.assertEqual(inputs,old)
        return res

    def test_actual_surface_peak_coords_but_not_safety_or_face_certification(self):
        r=self.run_spatial()
        self.assertEqual(r["schema"],"geofield-agent-fea-spatial-v1")
        self.assertEqual(r["status"],"verified_frd_surface_peak_positions")
        self.assertEqual(r["run_id"],RUN)
        self.assertEqual(r["stress_peak"]["value"],14.5)
        self.assertEqual(r["stress_peak"]["position_mm"],[7,6,0])
        self.assertEqual(r["stress_peak"]["unit"],"MPa")
        self.assertEqual(r["displacement_peak"]["value"],.2)
        self.assertEqual(r["displacement_peak"]["position_mm"],[4,2,0])
        self.assertEqual(r["displacement_peak"]["unit"],"mm")
        self.assertEqual(r["stress_peak"]["cad_face_proximity"]["cad_face_id_candidate"],6)
        self.assertEqual(r["stress_peak"]["cad_face_proximity"]["status"],
                         "geometric_proximity_candidate_only")
        self.assertFalse(r["cad_face_attribution_verified"])
        self.assertIn("체적 전체 최대치",r["note"])

    def test_without_reverified_fea_show_no_coordinates(self):
        info=fea();info["status"]="not_verified"
        r=spatial(info,cad(),field(),features())
        self.assertIsNone(r["stress_peak"])
        self.assertEqual(r["status"],"not_verified")

    def test_other_run_id_denied(self):
        x=field();x["run_id"]="f"*32
        self.assertEqual(spatial(fea(),cad(),x,features())["status"],"not_verified")

    def test_other_case_hash_denied(self):
        x=field();x["case_sha256"]="f"*64
        self.assertIsNone(spatial(fea(),cad(),x,features())["stress_peak"])

    def test_other_step_sha_denied(self):
        x=cad();x["sha256"]="f"*64
        self.assertEqual(spatial(fea(),x,field(),features())["status"],"not_verified")

    def test_other_cad_job_denied(self):
        x=field();x["cad_job_id"]="f"*32
        self.assertIsNone(spatial(fea(),cad(),x,features())["stress_peak"])

    def test_fake_source_denied(self):
        x=field();x["source"]="cached_unverified_json"
        self.assertEqual(spatial(fea(),cad(),x,features())["status"],"not_verified")

    def test_incomplete_nodal_result_denied(self):
        x=field();x["von_mises_mpa"]=x["von_mises_mpa"][:2]
        self.assertEqual(spatial(fea(),cad(),x,features())["status"],"not_verified")

    def test_fea_surface_cannot_exceed_verified_global_stress(self):
        x=field();x["von_mises_mpa"][1]=19.
        self.assertEqual(spatial(fea(),cad(),x,features())["status"],"not_verified")

    def test_fea_surface_cannot_exceed_verified_global_displacement(self):
        x=field();x["displacements_mm"][2]=[0,0,.7]
        self.assertEqual(spatial(fea(),cad(),x,features())["status"],"not_verified")

    def test_nan_or_negative_fea_fields_blocked(self):
        for val in (float('nan'),float('inf'),-4,True):
            with self.subTest(value=val):
                x=field();x["von_mises_mpa"][0]=val
                self.assertIsNone(spatial(fea(),cad(),x,features())["stress_peak"])

    def test_malformed_verified_global_maxima_fail_closed(self):
        for bad in (None,"16.0",True,float("nan"),float("inf"),-1,{}):
            for field_name in ("maximum_von_mises_mpa","maximum_displacement_mm"):
                with self.subTest(bad=bad,field=field_name):
                    x=fea();x[field_name]=bad
                    result=spatial(x,cad(),field(),features())
                    self.assertEqual(result["status"],"not_verified")
                    self.assertIsNone(result["stress_peak"])

    def test_wrong_feature_schema_rejected_even_with_matching_sha(self):
        x=features();x["schema"]="unchecked"
        self.assertEqual(spatial(fea(),cad(),field(),x)["status"],"not_verified")

    def test_triangle_mismatch_cannot_establish_location(self):
        x=cad();x["mesh"]["face_ids"]=[6]
        self.assertEqual(spatial(fea(),x,field(),features())["status"],"not_verified")

    def test_invalid_fea_surface_triangles_blocked(self):
        x=field();x["triangles"]=[[0,1,99]]
        self.assertEqual(spatial(fea(),cad(),x,features())["status"],"not_verified")

    def test_ambiguous_overlapping_faces_have_no_attribution(self):
        x=cad();x["mesh"]["triangles"].append([0,1,2])
        x["mesh"]["face_ids"].append(7)
        r=spatial(fea(),x,field(),features())
        self.assertEqual(r["status"],"verified_frd_surface_peak_positions")
        relation=r["stress_peak"]["cad_face_proximity"]
        self.assertEqual(relation["status"],"ambiguous_faces")
        self.assertIsNone(relation["cad_face_id_candidate"])
        self.assertFalse(r["cad_face_attribution_verified"])

    def test_offset_fea_geometry_no_cad_proximity_claim(self):
        x=field();x["positions_mm"]=[[2,3,3],[7,6,3],[4,2,3]]
        r=spatial(fea(),cad(),x,features())
        self.assertEqual(r["status"],"verified_frd_surface_peak_positions")
        self.assertEqual(r["stress_peak"]["cad_face_proximity"]["status"],"no_close_cad_triangle")
        self.assertIsNone(r["stress_peak"]["cad_face_proximity"]["cad_face_id_candidate"])

    def test_coordinate_proximity_is_not_risk_or_mapped_stress_proof(self):
        r=self.run_spatial()
        self.assertFalse(r["cad_face_attribution_verified"])
        self.assertNotIn("safety_certified",r)
        self.assertNotIn("stress_hotspot_at_face_verified",r)

if __name__=="__main__":
    unittest.main()

"""Read-only CAD face evidence test against the real agent function.

All CAD inputs are synthetic; no actual FreeCAD or physical risk is claimed.
Only an existing active CAD mesh can authorize 3D face highlighting. ML face
ordinal numbers are intentionally never used to obtain a CAD face ID.
"""
import copy
import unittest
from test_agent_evidence import env, record, CAD, JOB

cad_features=env["gf_agent_cad_features"]
evaluate=env["gf_agent_evaluate"]

def model():
    # face_ids are PER-TRIANGLE IDs, not a sequential face count.
    return {"sha256":CAD, "mesh":{"face_ids":[6,6,7,11,12,12],
            "triangles":[[0,1,2],[0,2,3],[0,1,3],[1,2,3],[0,2,4],[1,2,4]]}}

class AgentCadFeatureTests(unittest.TestCase):
    def test_verified_current_mesh_face_produces_linked_candidate(self):
        data=record(); d=data[1]; old=copy.deepcopy(d)
        result=cad_features(d,model())
        self.assertEqual(d,old)
        self.assertEqual(result["schema"],"geofield-agent-cad-features-v1")
        self.assertEqual(result["cad_sha256"],CAD)
        self.assertEqual(result["cad_job_id"],JOB)
        self.assertEqual(result["candidate_count"],1)
        candidate=result["candidates"][0]
        self.assertEqual(candidate["face_mapping_status"],"verified_in_current_cad_mesh")
        self.assertEqual(candidate["face_ids"],[6])
        self.assertFalse(candidate["mechanical_risk_confirmed"])
        self.assertFalse(candidate["hole_through_confirmed"])
        self.assertFalse(candidate["thin_wall_confirmed"])
        self.assertFalse(candidate["fea_hotspot_correlated"])
        self.assertFalse(result["ml_face_ordinals_are_cad_face_ids"])
        self.assertFalse(result["fea_hotspots_verified"])
        summary=evaluate(*data,cad_features=result)
        self.assertEqual(summary["cad_features"],result)
        self.assertEqual(summary["fea"]["maximum_von_mises_mpa"],14.512)

    def test_other_cad_hash_refused_even_if_face_numbers_same(self):
        data=record(); m=model();m["sha256"]="f"*64
        with self.assertRaisesRegex(ValueError,"SHA"):
            cad_features(data[1],m)

    def test_invalid_mesh_face_id_map_is_denied(self):
        d=record()[1]
        for bad in (None,[],["6"],[True],[6,-1],[6,3.0]):
            with self.subTest(face_ids=bad):
                m=model();m["mesh"]["face_ids"]=bad
                with self.assertRaises(ValueError):
                    cad_features(d,m)

    def test_missing_or_misaligned_triangles_refuse_face_mapping(self):
        d=record()[1]
        for bad in (None, [], [[0,1,2]], [[0,1,2]]*7,
                    [[0,1,2]]*5+[[0,1,"2"]],
                    [[0,1,2]]*5+[[0,1,-1]]):
            with self.subTest(triangles=bad):
                m=model();m["mesh"]["triangles"]=bad
                with self.assertRaisesRegex(ValueError,"삼각형"):
                    cad_features(d,m)

    def test_face_id_list_per_triangle_matches_verification_count(self):
        d=record()[1]
        m=model()
        self.assertEqual(len(m["mesh"]["face_ids"]),len(m["mesh"]["triangles"]))
        c=cad_features(d,m)["candidates"][0]
        self.assertEqual(c["face_ids"],[6])

    def test_mixed_valid_and_unknown_candidate_faces_are_not_partially_highlighted(self):
        d=record()[1];d["items"][0]["face_ids"]=[6,999]
        result=cad_features(d,model())
        self.assertEqual(result["candidate_count"],1)
        self.assertEqual(result["candidates"][0]["face_mapping_status"],"not_verified")
        self.assertEqual(result["candidates"][0]["face_ids"],[])
        self.assertIn("5.5 mm",result["candidates"][0]["measured_evidence"])

    def test_no_mapping_alone_cannot_create_assumed_hole_thickness_or_stress(self):
        d=record()[1]
        d["items"]=[{"where":"얇은 구간 가능성","measured_evidence":"비율이 높을 수 있음",
                    "face_ids":[],"next_check":"두께 실측 필요"}]
        result=cad_features(d,model())
        item=result["candidates"][0]
        self.assertFalse(item["thin_wall_confirmed"])
        self.assertFalse(item["mechanical_risk_confirmed"])
        self.assertFalse(item["fea_hotspot_correlated"])
        self.assertEqual(item["face_mapping_status"],"not_verified")

    def test_duplicate_triangle_faces_are_deduplicated_and_order_is_preserved(self):
        d=record()[1];d["items"][0]["face_ids"]=[12,6,12,7,6]
        result=cad_features(d,model())
        self.assertEqual(result["candidates"][0]["face_ids"],[12,6,7])

    def test_boolean_float_and_string_candidate_face_ids_do_not_map(self):
        d=record()[1]
        for value in ([True],[6.0],["6"],[None],{"id":6},None):
            with self.subTest(value=value):
                d["items"][0]["face_ids"]=value
                result=cad_features(d,model())
                self.assertEqual(result["candidates"][0]["face_ids"],[])
                self.assertEqual(result["candidates"][0]["face_mapping_status"],"not_verified")

    def test_ml_internal_face_ordinal_never_maps_to_cad_face(self):
        s,d,ml,r,fea=record()
        d["items"][0]["face_ids"]=[999]
        ml["result"]["variants"]["topology_trimmed"]["faces"][0]["face_ordinal"]=6
        res=cad_features(d,model())
        self.assertEqual(res["candidates"][0]["face_ids"],[])
        self.assertFalse(res["ml_face_ordinals_are_cad_face_ids"])
        answer=evaluate(s,d,ml,r,fea,cad_features=res)
        self.assertEqual(answer["ml"]["status"],"research_unverified")
        self.assertEqual(answer["cad_features"]["candidates"][0]["face_ids"],[])

    def test_decision_without_explicit_cad_job_id_rejected_by_agent(self):
        data=record();data[1].pop("cad_job_id")
        with self.assertRaises(ValueError):
            evaluate(*data,cad_features=cad_features(data[1],model()))

    def test_candidates_are_limited_and_missing_measurement_is_ignored(self):
        d=record()[1]
        d["items"]=[{"where":f"feature #{i}","measured_evidence":"B-Rep observed",
                     "face_ids":[6]} for i in range(18)]
        d["items"][2]["measured_evidence"]=""
        result=cad_features(d,model())
        self.assertEqual(result["candidate_count"],11)
        self.assertEqual(result["candidates"][-1]["candidate_index"],11)

    def test_forged_feature_hash_and_job_refused_by_agent(self):
        data=record()
        features=cad_features(data[1],model())
        for key,changed in (("cad_sha256","c"*64),("cad_job_id","f"*32),
                            ("schema","not-the-expected-schema")):
            with self.subTest(key=key):
                bad=copy.deepcopy(features);bad[key]=changed
                with self.assertRaisesRegex(ValueError,"CAD 특징 면"):
                    evaluate(*data,cad_features=bad)

    def test_cad_feature_evidence_cannot_change_original_fea_numbers(self):
        data=record();before=copy.deepcopy(data)
        features=cad_features(data[1],model())
        response=evaluate(*data,cad_features=features)
        self.assertEqual(data,before)
        self.assertEqual(response["fea"]["run_id"],data[4]["id"])
        self.assertEqual(response["fea"]["maximum_displacement_mm"],0.05698)
        self.assertFalse(response["cad_features"]["fea_hotspots_verified"])

if __name__=="__main__":
    unittest.main()

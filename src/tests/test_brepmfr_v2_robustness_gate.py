"""B07 v2 model fail-closed research readiness, no private model/STEP needed."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

SCRIPT=(Path(__file__).resolve().parents[1]/"research"/"brepmfr_v2"/"readiness_gate.py")
SPEC=importlib.util.spec_from_file_location("v2_readiness_gate",SCRIPT)
gate=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)
SHA="a"*64


def fixtures():
    train={
      "schema":gate.TRAIN_SCHEMA,
      "research_only":True,"eligible_for_production":False,
      "new_model_checkpoint_sha256":SHA,
      "train_families":["plate","l_support"],
      "validation_families":["double_fin"],
      "frozen_holdout_families":["u_channel","web_bridge"],
      "test_evaluated_once_after_epoch_selected":True,
      "prior_test_reused_as_train":True,
      "test":{"confusion_matrix":[[234,0,0],[0,12,0],[0,0,12]]}}
    stress={
      "schema":gate.STRESS_SCHEMA,
      "production_eligible":False,
      "checkpoint_sha256":SHA,
      "source_exact_archived_converter_sha256":gate.CONVERTER_SHA256,
      "transformed_fixed_holdout_cad":[
         {"expected":label,"cylinders":[{"prediction":prediction}],
          "correct_cylinders":int(label==prediction)}
         for label in ("through_hole","blind_hole")
         for prediction in ([label]*6 if label=="through_hole" else ["other"]*6)]}
    return train,stress


class RealisticResearchGate(unittest.TestCase):
    def test_perfect_fresh_synthetic_is_rejected_after_rotation_failure(self):
        t,s=fixtures();r=gate.review(t,s,SHA)
        self.assertEqual(r["synthetic_holdout_recall"],
                         {"through_hole":1.0,"blind_hole":1.0})
        self.assertEqual(r["postfit_rigid_transform_recall"],
                         {"through_hole":1.0,"blind_hole":0.0})
        self.assertIn("rotation_stress_fail_blind_hole",r["failed_gates"])
        self.assertFalse(r["synthetic_robustness_gate_passed"])
        self.assertFalse(r["production_eligible"])
        self.assertFalse(r["eligible_to_replace_epoch43"])
        self.assertFalse(r["can_drive_fea_or_engineering_safety"])

    def test_even_perfect_synthetic_and_rotation_requires_real_cad(self):
        t,s=fixtures()
        for row in s["transformed_fixed_holdout_cad"]:
            row["cylinders"][0]["prediction"]=row["expected"]
            row["correct_cylinders"]=1
        r=gate.review(t,s,SHA)
        self.assertTrue(r["synthetic_robustness_gate_passed"])
        self.assertEqual(r["failed_gates"],[
            "independently_labeled_real_industrial_cad_missing"])
        self.assertFalse(r["production_eligible"])

    def test_reject_stale_checkpoint_or_converter_digest(self):
        t,s=fixtures()
        s["checkpoint_sha256"]="b"*64
        with self.assertRaises(ValueError):gate.review(t,s,SHA)
        s["checkpoint_sha256"]=SHA
        s["source_exact_archived_converter_sha256"]="b"*64
        with self.assertRaises(ValueError):gate.review(t,s,SHA)

    def test_reject_cross_split_leakage(self):
        t,s=fixtures()
        t["frozen_holdout_families"].append("plate")
        with self.assertRaises(ValueError):gate.review(t,s,SHA)

    def test_reject_ambiguous_stress_and_false_correct_counter(self):
        t,s=fixtures()
        s["transformed_fixed_holdout_cad"][0]["cylinders"].append(
            {"prediction":"other"})
        with self.assertRaises(ValueError):gate.review(t,s,SHA)
        t,s=fixtures()
        s["transformed_fixed_holdout_cad"][0]["correct_cylinders"]=0
        with self.assertRaises(ValueError):gate.review(t,s,SHA)

    def test_reject_incomplete_test_or_invalid_raw_confusion(self):
        t,s=fixtures()
        t["test"]["confusion_matrix"][1][1]=-1
        with self.assertRaises(ValueError):gate.review(t,s,SHA)
        t,s=fixtures()
        t["test"]["confusion_matrix"][2][2]=0
        with self.assertRaises(ValueError):gate.review(t,s,SHA)

    def test_no_test_epoch_selection(self):
        t,s=fixtures()
        t["test_evaluated_once_after_epoch_selected"]=False
        with self.assertRaises(ValueError):gate.review(t,s,SHA)

    def test_input_files_dont_exist_no_creation(self):
        with self.assertRaises(ValueError):
            gate._read_json(SCRIPT.with_suffix(".unknown"))
        with self.assertRaises(ValueError):
            gate._digest(SCRIPT.with_suffix(".pt"))


if __name__=="__main__":
    unittest.main()

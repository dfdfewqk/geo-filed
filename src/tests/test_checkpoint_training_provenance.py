"""No-private-weight CI tests for structural checkpoint provenance gate."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

SOURCE = Path(__file__).resolve().parents[1]/"checkpoint_training_provenance.py"
spec = importlib.util.spec_from_file_location("checkpoint_training_provenance", SOURCE)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class FakeTensor:
    def __init__(self, *shape):
        self.shape = shape


def expected_five_stream():
    result = {
        "encoder.node_feature.fusion.fc1.weight": FakeTensor(256, 1408),
        "face_classifier.fc3.weight": FakeTensor(27, 512),
    }
    for name in ("surface_encoder", "face_type_encoder", "face_area_encoder",
                 "face_centroid_encoder", "face_rationality_encoder",
                 "face_loop_encoder"):
        result[f"encoder.node_feature.{name}.weight"] = FakeTensor(256, 1)
    return result


class Epoch43ProvenanceContract(unittest.TestCase):
    def test_historical_five_stream_fusion_shape_detected(self):
        params = SimpleNamespace(hidden_dim=256, num_layers=8,
                                 face_segmentation=True, learning_rate=.0016,
                                 private_data_path="never include")
        proof = audit.structural_evidence(expected_five_stream(), params)
        self.assertEqual(proof["node_fusion_weight_shape"], [256, 1408])
        self.assertEqual(proof["face_segmentation_head_weight_shape"], [27, 512])
        self.assertEqual(len(proof["present_node_feature_streams"]), 6)
        self.assertEqual(len(proof["absent_optional_node_feature_streams"]), 3)
        self.assertTrue(proof["five_stream_checkpoint_structure_verified"])
        self.assertFalse(proof["current_public_eight_stream_model_compatible"])
        self.assertFalse(proof["original_training_forward_verified"])
        self.assertFalse(proof["original_training_commit_verified"])
        self.assertFalse(proof["can_automatically_promote_as_production_model"])
        self.assertNotIn("private_data_path", proof["recorded_training_config"])

    def test_current_public_eight_stream_network_is_not_mislabeled_as_legacy(self):
        state=expected_five_stream()
        state["encoder.node_feature.fusion.fc1.weight"]=FakeTensor(256, 2176)
        for name in ("face_normal_encoder","face_bbox_encoder","face_reversed_encoder"):
            state[f"encoder.node_feature.{name}.weight"]=FakeTensor(256,3)
        proof=audit.structural_evidence(state)
        self.assertFalse(proof["five_stream_checkpoint_structure_verified"])
        self.assertIsNone(proof["current_public_eight_stream_model_compatible"])
        self.assertFalse(proof["original_training_forward_verified"])

    def test_wrong_face_head_or_missing_feature_never_passes(self):
        state=expected_five_stream()
        state["face_classifier.fc3.weight"]=FakeTensor(25,512)
        self.assertFalse(audit.structural_evidence(state)["five_stream_checkpoint_structure_verified"])
        state=expected_five_stream()
        state.pop("encoder.node_feature.face_loop_encoder.weight")
        self.assertFalse(audit.structural_evidence(state)["five_stream_checkpoint_structure_verified"])

    def test_invalid_state_rejected(self):
        for state in (None, [], "bad", dict.fromkeys(str(i) for i in range(10001))):
            with self.subTest(kind=type(state).__name__):
                with self.assertRaises(ValueError):
                    audit.structural_evidence(state)

    def test_missing_checkpoint_fails_closed_without_importing_torch(self):
        with self.assertRaises(ValueError):
            audit.inspect(Path(__file__).resolve().parent/"absent_epoch43.ckpt")


if __name__ == "__main__":
    unittest.main(verbosity=2)

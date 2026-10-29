# -*- coding: utf-8 -*-
"""Private local-only epoch43 CHECKPOINT STRUCTURE review (never infer ML).

Usage:
    python checkpoint_training_provenance.py --checkpoint path/to/epoch43.ckpt

Prints a bounded, path-free JSON summary. Checkpoint bytes are NOT copied,
uploaded, trained, converted or modified. Requires installed PyTorch. The
checkpoint's SHA-256 is verified before and after restricted deserialization.
This does NOT prove the original training-time forward implementation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

PINNED_SHA256 = "50bc40c647d55aab599b907c1587f37ff66f666a99aaae3f2561a3df984f42d1"
MAX_CKPT_BYTES = 2_000_000_000
# Two concrete globals recorded in the historical Lightning checkpoint;
# only metadata placeholders, never the installed private source modules.
APPROVED_GLOBALS = frozenset({
    "pathlib.PosixPath",
    "brepformer.configs.config.BrepClassifierConfig",
})


class _PathRecord:
    def __init__(self, *parts):
        pass


class _ConfigRecord:
    pass


def _shape(state, name):
    obj = state.get(name)
    if obj is None or not hasattr(obj, "shape"):
        return None
    dims = tuple(obj.shape)
    return list(dims) if all(type(v) is int and 0 <= v <= 1_000_000 for v in dims) else None


def structural_evidence(state, config=None):
    """Derive ONLY shape/key evidence from a state dict. No torch dependency."""
    if not isinstance(state, dict) or len(state) > 10000:
        raise ValueError("Invalid checkpoint state dictionary")
    fusion = _shape(state, "encoder.node_feature.fusion.fc1.weight")
    face_head = _shape(state, "face_classifier.fc3.weight")
    keys = tuple(state)
    absent = [
        name for name in ("face_normal_encoder", "face_bbox_encoder", "face_reversed_encoder")
        if not any(k.startswith("encoder.node_feature." + name + ".") for k in keys)
    ]
    streams = [
        name for name in ("surface_encoder", "face_type_encoder",
                          "face_area_encoder", "face_centroid_encoder",
                          "face_rationality_encoder", "face_loop_encoder")
        if any(k.startswith("encoder.node_feature." + name + ".") for k in keys)
    ]
    # 128-dimensional sampled surface embedding plus five attribute embeddings
    # of 256 dimensions each; public current 8-stream network is 128+8*256.
    five_stream = (
        fusion == [256, 1408] and face_head == [27, 512] and
        len(streams) == 6 and len(absent) == 3
    )
    params = {}
    if config is not None:
        for name in ("hidden_dim", "ffn_dim", "num_heads", "num_kv_heads",
                     "num_layers", "face_attr_dim", "edge_attr_dim",
                     "num_face_classes", "face_segmentation", "face_seg_weight",
                     "model_cls_weight", "learning_rate"):
            value = getattr(config, name, None)
            if type(value) in (str, int, float, bool) and len(str(value)) < 80:
                params[name] = value
    return {
        "node_fusion_weight_shape": fusion,
        "face_segmentation_head_weight_shape": face_head,
        "present_node_feature_streams": streams,
        "absent_optional_node_feature_streams": absent,
        "five_stream_checkpoint_structure_verified": five_stream,
        "current_public_eight_stream_model_compatible": False if five_stream else None,
        "recorded_training_config": params,
        "original_training_forward_verified": False,
        "original_training_commit_verified": False,
        "checkpoint_predictions_validated_on_held_out_step": False,
        "can_automatically_promote_as_production_model": False,
    }


def _digest(p):
    h = hashlib.sha256()
    with p.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def inspect(checkpoint):
    """Safely examine only a known-hash historical checkpoint, without executing ML."""
    source = Path(checkpoint).absolute()
    if source.is_symlink() or not source.is_file():
        raise ValueError("Missing or linked checkpoint")
    before = source.stat()
    if not 0 < before.st_size <= MAX_CKPT_BYTES:
        raise ValueError("Checkpoint size out of bounds")
    if _digest(source) != PINNED_SHA256:
        raise ValueError("Unknown checkpoint digest; refusing serialization")
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError("PyTorch is required for local checkpoint review") from exc
    unsafe = set(torch.serialization.get_unsafe_globals_in_checkpoint(str(source)))
    if unsafe != APPROVED_GLOBALS:
        raise ValueError("Checkpoint pickle globals do not match known epoch43 metadata")
    with torch.serialization.safe_globals([
        (_PathRecord, "pathlib.PosixPath"),
        (_ConfigRecord, "brepformer.configs.config.BrepClassifierConfig"),
    ]):
        loaded = torch.load(str(source), map_location="cpu", weights_only=True)
    after = source.stat()
    if ((before.st_size, before.st_mtime_ns) !=
            (after.st_size, after.st_mtime_ns) or _digest(source) != PINNED_SHA256):
        raise ValueError("Checkpoint changed during read-only analysis")
    if not isinstance(loaded, dict):
        raise ValueError("Malformed checkpoint")
    cfg = loaded.get("hyper_parameters", {}).get("config")
    result = structural_evidence(loaded.get("state_dict"), cfg)
    result.update({
        "schema": "geofield-epoch43-training-provenance-v1",
        "checkpoint_digest": PINNED_SHA256,
        "checkpoint_bytes": before.st_size,
        "recorded_epoch": loaded.get("epoch"),
        "recorded_global_step": loaded.get("global_step"),
        "recorded_lightning_version": loaded.get("pytorch-lightning_version"),
        "state_dict_tensor_count": len(loaded["state_dict"]),
        "status": "STRUCTURE_RECORDED_TRAINING_FORWARD_UNPROVEN",
        "safe_review_only": True,
        "no_private_checkpoint_or_paths_exported": True,
    })
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(inspect(args.checkpoint), ensure_ascii=False, indent=2,
                         sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        # Do not print private paths, checkpoint contents or traceback.
        print("[BLOCKED] Epoch43 source provenance review: " + type(exc).__name__)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

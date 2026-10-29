# GeoField B07 — epoch43 original-training provenance and model structure review (2026-10-29)

## Actual checkpoint, read-only
Verified private archived historical `best-epoch43-f1_0.8626.ckpt` SHA-256:
`50bc40c647d55aab599b907c1587f37ff66f666a99aaae3f2561a3df984f42d1`.

Loaded with **PyTorch weights_only=True** and ONLY the two historical harmless metadata-class placeholders (`pathlib.PosixPath` and `brepformer.configs.config.BrepClassifierConfig`). This is **not** the unsafe default pickle loader; no private source module was imported. The historical model weights stayed in the private sandbox; only aggregate numeric/structural facts are committed.

**Metadata directly recorded inside the checkpoint:**
- `epoch=43`; `global_step=31372`; PyTorch Lightning `1.7.1`
- `state_dict` contains **242 tensor entries**
- `hyper_parameters.config`: `hidden_dim=256`, `ffn_dim=512`, `num_heads=32`, `num_kv_heads=8`, `num_layers=8`, `num_face_types=6`, `num_edge_types=6`, `face_attr_dim=14`, `edge_attr_dim=15`, `face_grid_channels=7`, `edge_grid_channels=12`, `num_face_classes=27`, `face_segmentation=True`, `face_seg_weight=2.0`, `model_cls_weight=0.5`, `learning_rate=0.0016`, `adam_beta1=0.99`.
- Checkpoint callback best validation `val/f1=0.8626` recorded in the historical source checkpoint. This is **not** a fresh GeoField inference score and does not validate arbitrary STEP files.

## Definitive state_dict structural difference
| Feature | Actual epoch43 checkpoint | Current public BrepFormer main source |
|---|---|---|
| Face fusion `encoder.node_feature.fusion.fc1.weight` | **[256, 1408]** | **[256, 2176]** |
| Feature fusion | UV-surface embedding 128 + five face attribute streams × 256 | UV-surface embedding 128 + eight face attribute streams × 256 |
| Face normal encoder | **absent** from saved weights | present |
| Face bbox encoder | **absent** from saved weights | present |
| Face reversed encoder | **absent** from saved weights | present |
| Face segmentation head | `face_classifier.fc3.weight = [27, 512]` | current code defines 27-class face head |

Exact current public source reviewed: `cad-results/BrepMFR` `brepformer/models/layers/embedding.py` at `main` and initial published commit `c16cc666f4d1`; **both public revisions show eight streams**, not the five-stream checkpoint. Only one public branch (`main`) was listed at review time. It follows that these two inspected published source revisions cannot be treated as the exact training-architecture revision for epoch43. The original source commit itself is **NOT established**.

**Important:** the Oct-15 owner archive does contain `ml/brepmfr_core/legacy_architecture.py` (a reconstructed five-stream network) that loads all checkpoint keys strictly, but identical weight names/shapes **do not prove identical forward tensor operations** or training/preprocessing semantics. This program's `OldGraphNodeFeature.forward` consumes scalar face attr fields, whereas the archive converter's `normalize_geometry` emits onehot training-style fields. The apparent conflict and the missing signed training forward remain unresolved.

## Permanent safety guard / reproducible local proof
`src/checkpoint_training_provenance.py` allows optional local read-only verification of the **same SHA-pinned** checkpoint. It checks:
1. file exists, is not a symlink, bounded size and expected SHA-256;
2. pickle global names are **exactly** the two pre-reviewed metadata classes;
3. deserialization uses `weights_only=True` and only two no-op metadata record aliases;
4. the input file hash and stat metadata did not change;
5. expected 242-key architecture shape and feature-stream presence are summarized **without printing private paths or any weight values**;
6. the result explicitly sets `original_training_forward_verified=false`, `original_training_commit_verified=false`, `can_automatically_promote_as_production_model=false`.

Example for an already owned/private research copy, not a new download:
```shell
python src/checkpoint_training_provenance.py --checkpoint "<PRIVATE_LOCAL_EPOCH43_PATH>"
```
This tool **does not install Python dependencies**, alter the user Windows installation, download or upload a checkpoint, generate predictions or rewrite the model. Unit tests do not include private weights and run without Torch.

## Decision
**Do not replace the existing epoch43 inference's layer connections, swap to the current eight-stream public code, or claim the original training forward is proven.** The static shape evidence establishes only a historical five-stream network; it cannot identify the exact old forward implementation or genuine training dataset preprocessing. The prior full 864-pass input ablation did not identify a robust preprocessor rewrite across CAD families.

**Next milestone:** decide whether an authentic original training source revision plus matching preprocessing/face labels can be recovered. If not, proceed to a **new versioned model** trained/evaluated using a single deployed STEP→graph converter (including actual UV trim masks and graph descriptors), held-out CAD-family splits, and separate through/blind class precision/recall/F1. Keep the independent B-Rep occupancy diagnostic and CAD/FEA/3D safe until acceptance criteria pass. No paid/cloud training is assumed.

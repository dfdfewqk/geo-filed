# BrepMFR epoch43 input-schema & quality gate (2026-10-29)
## Grounded experiment
Owner's private 2026-10-15 research ZIP contained an actual 76,179,155-byte epoch43 checkpoint; SHA-256 `50bc40c647d55aab599b907c1587f37ff66f666a99aaae3f2561a3df984f42d1` verified. It was run in an isolated local research container; **not** shipped to GitHub, not confirmed equal to current Windows installation.
12 synthetic STEP CAD research runs reproduced classification problems: the cylinder of 4 through-hole cases was `through_hole` 0/4 with either baseline or fixed typed-edge preprocessing; 4 blind-hole cases produced 4/4 `blind_hole`. Four no-hole cases had no cylindrical hole surface. This is **not** an independently labeled industrial or MFTRCAD face-level accuracy evaluation.
## New controlled eight-case schema ablation (actual checkpoint, no retraining)
| Face attribute input interpretation | Through-hole cylinder matches | Blind-hole cylinder matches |
| --- | ---: | ---: |
| Typed index + area + centroid (archived fixed preprocessor) | 0/4 | 4/4 |
| Replace only first index with one-hot first bit | 0/4 | 4/4 |
| Full training-sample-like 14-element one-hot face attribute | 2/4 | 0/4 |
Training-like representation caused both L-support *blind holes* to be predicted as `through_hole`; through-hole chamfer plates still failed. Thus **no layout substitution is safe as a model accuracy fix**. Research face architecture was reverse-engineered to load the checkpoint; strict state_dict loading does not prove it is operationally equivalent to the original training network.
Archived official MFTRCAD training graph JSON `graph_face_attr` uses first six one-hot type channels, whereas the reconstructed worker reads surface type as scalar index 0. Source provenance does not show which representation the particular epoch43 checkpoint learned; do **not** guess a new mapping or relabel classes. Archived 27-class definitions map 1=`through_hole`, 12=`blind_hole`, 11=`Oring`.
## Safe product changes
The **GitHub-tracked** validator and frontend reject worker payloads whose score is outside [0,1], whose `viewer_face_mapping_verified` asserts unsupported verification, or whose optional `trained_architecture_equivalence` claims anything other than `not_proven`. The existing optional fields may be absent in older private workers; absence never implies verification. UI explicitly states that BrepMFR cannot establish through/blind hole type. The raw experimental face labels are still viewable only as diagnostic predictions and cannot change B-Rep geometry, FEA, stress, or AI evidence.
New deterministic Python/Node tests use synthetic JSON only and do not bundle private training files.
## Remaining
Original training dataset preprocessing and exact checkpoint training network must be independently verified before any true classification fix or retraining plan can be approved; version/hash of Windows private source, same-CAD real ML and AI GUI integration remain unverified. Do not mark GeoField B07 finished or the model production-ready.

## Additional real checkpoint probe on archived *labeled* original MFTRCAD graph samples
The private epoch43 checkpoint was run on **12 supplied public sample graphs (363 faces)** carrying 10 `through_hole` face labels and 22 `blind_hole` face labels. The model and graph inputs were held constant; only the 14-element face attribute input layout was changed. **These are examples distributed with the upstream repository, not an independent validation split.** The original 27-class label schema was used without relabeling.
| Layout | Exact face label matches | Through-hole face matches | Blind-hole face matches |
| --- | ---: | ---: | ---: |
| Original upstream sample `graph_face_attr` one-hot | **209 / 363** | **10 / 10** | 17 / 22 |
| Archived inference-style type/area/centroid remap | 46 / 363 | 3 / 10 | **21 / 22** |
The substantially poorer overall performance of the remapped layout is direct evidence of **an input schema compatibility defect**, not proof that blindly using original raw graph layout fixes user STEP files. Prior STEP synthetic tests under the one-hot style still misclassified some holes. Dataset `brepformer/data/dataset.py` passes original `graph_face_attr` to the collator; archived converter reassigns `face_attr_array[:,0]` / `[:,1]` / `[:,2:5]`. Model architecture equivalence, training checkpoint provenance, synthetic-to-MFTRCAD domain shift and real installed Windows source are still unverified. The source reviewer now reports the archived remap signature without touching source or weights.

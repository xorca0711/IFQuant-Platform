# Whole-slide nuclei stitching and live registration

Updated 2026-10-11; implementation and public execution evidence for jobs 3.5,
5.1 and 5.2. These tools target future obtainable high-resolution images.
The public examples establish engineering behavior within the scopes below.

## Results

| Run | Observed result | Interpretation |
| --- | --- | --- |
| InstanSeg complete public H&E field, 1,380 × 1,484 pixels at 0.50008 µm/pixel | Nine tiles; 5,726 objects; 488,916 foreground pixels; 2,389 overlap unions; 44 unresolved seam flags; reconstructed package passed | Native-resolution field, not a billion-pixel slide throughput benchmark. Objects remain nuclei candidates. |
| Same-image tiling comparison, 512 × 512 shared pixels | Single-window prediction: 1,152 objects; stitched: 1,170; 1,150 matches; F1 0.99053; mean matched IoU 0.99186 | Tiling sensitivity, not independent segmentation accuracy. Seam flags are review cues, not an exhaustive error detector. |
| Controlled public-image transform, VALIS rigid registration | 16 evaluation points; RMSE 5.949 µm; maximum 6.389 µm; zero sampled folds | Known resampling transform, never supplied to fitting. About 0.75 source pixels; not a biological landmark benchmark. |
| Actual public IHC pair, VALIS similarity plus optical flow | Completed; zero folds on a 4 × 4 interior probe grid; triangle area ratios 0.95335–1.04321 | No independent landmarks: accuracy is undefined and local error support is unavailable. Finite sampling cannot establish global invertibility. |

The [portable evidence](../validation/evidence/stitching-valis-20261011.json)
records input, runtime and output hashes. Earlier ROI/BANKSY/NGFF/throughput
results remain in [public development](PUBLIC_DEVELOPMENT.md). Raw images,
weights, registrar files and full generated outputs stay outside Git.

## InstanSeg execution

Install the main optional environment and run the pinned example from the repo root:

```powershell
uv sync --locked --extra dev --extra inference --extra wsi-codecs
uv run --no-sync python scripts/replay_tiled_instanseg.py --download --output validation/output/tiled-instanseg
```

For your registered calibrated image, use this closed plan. Paths resolve from
the plan directory. There is no implicit weight download in the executor.

```json
{"schema_version":"ifquant.instanseg-slide/1","source":"source.json",
 "weights":"instanseg.pt","tile_size":512,"halo":64,"threads":4,
 "overlap_iou":0.5,"minimum_overlap_pixels":16,"maximum_objects":100000}
```

```powershell
uv run --no-sync python -m ifquant_platform segment-instanseg-slide plan.json --output validation/output/nuclei --max-tiles 2
uv run --no-sync python -m ifquant_platform segment-instanseg-slide plan.json --output validation/output/nuclei --resume
uv run --no-sync python -m ifquant_platform validate-instanseg-slide validation/output/nuclei
```

Omit `--max-tiles` to run continuously. An interrupt preserves completed tiles;
resume verifies image/model/configuration/code/runtime bindings and tile hashes.
An OS-owned lock prevents competing writers and releases on process exit.
Uncommitted interrupted arrays are retained as orphans and recomputed. Completed
packages cannot resume or be overwritten; finalization attempts remain separate.

Each half-open core owns its pixels once. Halo predictions establish identity
through mutual-best overlap IoU, including diagonal neighbors. A union cannot
collapse distinct labels from the same tile. Ambiguous matches remain separate;
core tiles, image-edge contact and seam flags accompany each object. Centroids
use pixel centers at index +0.5 in the selected source grid. Areas use its physical
calibration. This does not guarantee count or boundary invariance on real tissue.

Outputs include compressed tiled uint32 BigTIFF labels, calibrated objects,
overlap decisions, tile predictions and a byte-bound package. Validation rebuilds
labels/tables from committed tiles and compares their hashes, without inference.
Synthetic tests cover exact seams, corners, partial edges, narrow images,
collision rejection, pause/resume, corruption and interrupted writes.

The profile accepts isotropic uint8 RGB H&E and the pinned brightfield nuclei
model only. Cores are 64–512 pixels in multiples of 16; halo is 16 through half
the core size. Guards limit model-scale tile pixels to four million, tile count
to 100,000, raster area to ten billion pixels and cumulative tile instances
(including halo duplicates) to two million. Arrays remain tile-bounded; object
bookkeeping is bounded by the instance cap. These are capacity guards, not
demonstrated throughput limits. Labels have no display pyramid yet. This result
does not unlock the fluorescence-v1 InstanSeg backend or infer cells/severity.

## Isolated VALIS execution

VALIS 1.2.0 requires a NumPy 1.x stack; the main optional environment uses NumPy
2.x. Its own locked environment uses Python 3.11, CPU torch 2.8.0 and binary
libvips. Run from the repository root (PowerShell shown):

```powershell
uv sync --directory environments/valis --locked --python 3.11
$env:PYTHONPATH = "$PWD/src"
$env:MPLBACKEND = "Agg"
uv run --project environments/valis --no-sync python scripts/replay_valis.py --download --output validation/output/valis
```

On Windows ARM64, use an x64 Python 3.11 executable with
`--python-platform x86_64-pc-windows-msvc --python <x64-python.exe>` on sync.
The local tested environment is `.venv-valis311`; no global Python was changed.
Linux execution is included in CI. Omit `--download` when public TIFFs are cached.
VALIS import may fetch its default DISK/LightGlue weights even though this plan
uses VGG/OpenCV descriptors; the explicit model cache and result inventory retain
their hashes. Initial setup therefore needs network access and can take minutes.

The example manifest pins two official IHC OME-TIFF files (about 32 MB). libvips
decodes their pixels to lossless PNG; OME calibration and TIFF hashes are retained.
`brightfield` is an additive image modality so IHC is not mislabeled H&E.
Patient identity and physical section relationship are not established by these
example names: their grouping is a source-series proxy and relation is `unknown`.

`register-valis-pair plan.json --output fresh-directory` accepts an
`ifquant.valis-pair/1` plan with `moving_source`, `fixed_source`, `points_csv`,
`section_relation`, `heldout_reference`, `non_rigid`, `processed_size`, `seed`,
`model_cache`, `probe_grid_xy` and `max_local_distance_um`. See the replay's
generated plans for complete examples. Current inputs are distinct level-zero
RGB PNG sources of at most 16 million pixels each; processed size is 256–2048.
This deliberate reader profile avoids JVM/Bio-Formats discovery. Native whole-slide
VALIS warping/export is a remaining extension, not demonstrated by this adapter.

The runner fits image features, then uses the live `warp_xy_from_to` API at
source/point/destination level zero. It never loads a registrar pickle. Target
landmarks are used only after fitting. Separate fitted-feature summaries,
evaluation residuals, sampled folds and local support prevent treating a fit
score as held-out accuracy. See [point schema and QC](ANALYSIS_WORKFLOW.md).

VALIS 1.2.0's rigid-only cleanup accesses an uninitialized nonrigid settings
container. The adapter initializes that empty container only when missing, and
still requires successful registrar outputs. The runtime is always shut down.
CI requires 16 controlled evaluation points, RMSE below 20 µm (approximately 2.5
pixels here) and zero sampled folds. This is an engineering regression tolerance,
not a pathology acceptance threshold; the unannotated real pair has no accuracy
pass threshold.

References: [VALIS installation](https://valis.readthedocs.io/en/latest/installation.html),
[reader and registration API](https://valis.readthedocs.io/en/latest/registration.html),
[public source manifest](../datasets/examples/valis-ihc-pair.json),
[runtime lock](../environments/valis/uv.lock).

## Remaining development order

1. Review seam disagreements against independent nuclei annotations; audit
   pretrained-data overlap and compare native/StarDist/InstanSeg on one protocol.
2. Benchmark native-resolution, complete slides across scanners; qualify memory,
   disk and interruption costs, label-pyramid visualization and package adapters.
3. Extend VALIS to calibrated native slide readers/export and independent public
   paired-slide landmarks, including tissue edges and representative deformations.
4. Follow the [register](DEVELOPMENT_PLAN.md) for compatible scRNA references,
   supported Slide-GoTags source access and optional multimodal branches.
5. Establish disease-specific severity and intended-use accuracy using suitable
   independent experts/references. The user's own dataset is not a prerequisite
   for software work, but representative evidence is required for these claims.

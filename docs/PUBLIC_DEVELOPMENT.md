# Development without private validation data

Updated 2026-10-11. This extends the original priority 1–5 pass. Public resources
exercise software intended for future obtainable high-resolution images; they do
not define or limit the product's eventual inputs.

The subsequent [stitching and registration increment](STITCHING_REGISTRATION.md)
implements whole-grid InstanSeg stitching/resume and live VALIS execution. Its
[separate evidence](../validation/evidence/stitching-valis-20261011.json) preserves
this earlier run record and supersedes the former unimplemented-software gaps.

## Delivered in the first public development increment

| Register jobs | Deliverable | Evidence and boundary |
| --- | --- | --- |
| 1.6 | NGFF 0.4/0.5 bounded image-plane intake with explicit T/Z and channel selection | Exact-pixel and physical-coordinate tests; no arbitrary axis discovery, 3D segmentation or intensity rescaling. |
| 3.1 | Complete selected-pyramid-level H&E execution on public CMU-1 | Frozen same-image appearance fit, tiled analysis and package revalidation; throughput evidence, not held-out pathology accuracy. |
| 3.5 | Pinned InstanSeg CPU H&E nuclei executor, calibrated object measurements and IoU matching | Official model fixture plus calibrated public H&E ROI; separate tissue result, not fluorescence-v1 canonical export or backend equivalence. |
| 4.1–4.2 | Five source-cited mouse lung marker panels and shared full-library normalization | Exact deposited Ensembl IDs; explicit incomplete-coverage abstention and no automatic cell-state assignment. |
| 4.5 | Real 308-feature lung replay and BANKSY feature comparison | 2,486 measured spots; expression baseline, simple smoothing, BANKSY λ=0 and λ=0.8; fixed k-means, no ground-truth domains. |

Portable run summaries are in
[`public-development-20261011.json`](../validation/evidence/public-development-20261011.json).
Fresh output directories preserve earlier attempts and provenance. Source images,
RNA matrices, model weights and generated runs remain outside Git.

## Reproduce

Use Python 3.11–3.13 **x64** for the optional engines on Windows. The repository's
core CLI still has no mandatory analysis dependencies. CPU PyTorch is selected
by the uv index configuration; install optional engines only when needed.

```powershell
uv sync --locked --extra dev --extra spatialdata --extra morphology --extra performance --extra wsi-codecs --extra inference --extra domains
uv run --no-sync python scripts/replay_lung_rna.py --download --output validation/output/lung-rna
uv run --no-sync python scripts/replay_instanseg.py --download --output validation/output/instanseg
uv run --no-sync python scripts/replay_histology_throughput.py --download --output validation/output/histology-throughput
```

Downloads are opt-in. Omit `--download` when the pinned cache is already present.
The lung files total about 15 MB, the InstanSeg archive/example about 16 MB, and
CMU-1 about 178 MB. Every replay refuses an existing output directory.
The optional Linux CI job installs the pinned engines, executes a small BANKSY
fixture, and requires InstanSeg model-conformance F1 and mean matched IoU ≥0.99.
This threshold concerns reproduction of the released model output only.

### InstanSeg

`segment-instanseg plan.json --output fresh-directory` accepts this closed plan:

```json
{"schema_version":"ifquant.instanseg/1","source":"source.json",
 "weights":"instanseg.pt","window_xywh":[256,256,512,512],"threads":4}
```

The source uses the existing calibrated image contract. Only the SHA-bound
official `brightfield_nuclei` 0.1.1 TorchScript model is accepted; code is
`instanseg-torch` 0.1.2 with CPU torch 2.8.0. There is no implicit model download.
The current profile accepts isotropic uint8 RGB H&E windows up to one million
pixels and four million pixels at the model's 0.5 µm scale. It exports instance
labels and centroids/areas in the selected source grid, with boundary objects
flagged. Pixel centers are at index +0.5. This ROI command does not stitch tiles;
the separate `segment-instanseg-slide` command now does. Neither infers whole
cells, assigns phenotype or produces injury severity.

The upstream fixture's 336 objects matched with F1 and mean IoU of 1.0. The
public 512 ×512 ROI produced 1,026 nuclei. Its OME metadata supplies
0.5000799214 µm/pixel; the model fixture's 0.5 µm scale comes from its RDF metadata.
Neither is an independent expert annotation set. `match_instances` provides
maximum-cardinality, one-to-one IoU matching on exhaustive common ROIs, invariant
to label numbers. Empty denominators remain undefined.

Sources: [official inference documentation](https://instanseg.github.io/instanseg/inference.html),
[versioned model release](https://github.com/instanseg/instanseg/releases/tag/instanseg_models_v0.1.1).

### Lung RNA and BANKSY

The frozen plan selects 300 genes by population variance of log1p(CP10k) using
full raw-library totals, after declared detection and mitochondrial/ribosomal
prefix filters. It then includes every registry gene, giving 308 total features
and 613,472 nonzero counts. All selected gene totals independently reconcile to
the deposited HDF5: 8,378,972 selected counts out of 26,079,373 total counts.
All 4,992 positions remain represented; 2,506 unreported RNA positions are
excluded from scoring/clustering rather than treated as biological zeros.

The [marker registry](../protocols/niethamer-lung-markers-v1.json) cites
[Niethamer et al.](https://doi.org/10.1016/j.stem.2024.12.002): CAP1
Gpihbp1/Kit, CAP2 Ednrb/Car4, iCAP-associated Sparcl1/Ntrk2, glycolysis context
Pfkl/Tpi1/Ldha/Pkm, and MHC-II context Ciita/Cd74. These are positive marker
summaries, not author-trained signatures. The Day 3 replay precedes the reported
approximately 11-day iCAP onset. Mixed spots and nonspecific expression cannot
establish those cell identities, metabolic flux, lineage or regeneration.

Domain plan v2 adds `library_totals_csv` and `banksy` (null to disable) to v1.
`banksy` contains `neighbors`, `lambda`, `max_m`; the frozen replay uses 15, 0.8, 1.
The optional wrapper executes [pybanksy 1.3.5](https://github.com/prabhakarlab/Banksy_py)
feature augmentation, then the same 20-component SVD and seeded five-cluster
k-means comparison. It does not claim to reproduce the upstream Leiden workflow.
BANKSY λ=0 provides its own feature-scaling control. Partition agreement and
spatial smoothness are descriptive; greater smoothness is not domain accuracy.

### NGFF planes and throughput

`import-ngff-window` v1 remains compatible with calibrated 0.4 YX/CYX inputs.
Plan v2 also accepts 0.5 and ordered TCZYX subsets ending YX. It adds
`axis_indices` (every present T/Z index) and `channel_indices` (one grayscale or
three explicitly ordered RGB channels; null without a channel axis). Crop origin,
selected T/Z physical coordinates and source inventory are retained. NGFF 0.5
requires Zarr v3 and matching array dimension names. Other data types, automatic
RGB inference and whole-volume processing remain unsupported. See the
[OME-NGFF 0.5 specification](https://ngff.openmicroscopy.org/0.5/).

The throughput script fits an appearance model on CMU-1 pyramid level 2 and
processes the complete level 1 grid with 512-pixel tiles. Image bounds are an
unreviewed footprint, never an anatomical reference. The fitted appearance model
is reused only as an engineering workload. Timings are local observations and
include source verification/output publication; concurrent workloads affect them.

## Pipeline revisions and rationale

1. Private validation data are not required for engine execution, source-program
   curation, broader public replay or explicit format support. These items were
   moved out of the earlier conditional queue and implemented.
2. The proposed 500-gene replay exceeded the existing million-row interchange
   guard. The plan was reduced to 300 variable genes plus markers before the
   successful run. No capacity guard was weakened or biological result optimized.
3. Panel selection must not redefine the library denominator. Programs and domains
   now share the complete full-library validator; all observations must be covered.
4. A brightfield nuclei result has a different scope from the fluorescence-v1
   cell package. The new executor publishes its own explicit tissue contract;
   it does not bypass the older governed backend gate.

## Remaining work, in development order

| Order | Specific jobs | What permits completion |
| --- | --- | --- |
| 1 — Expand software qualification | Tiled stitching, resume and package validation are implemented. Next: label pyramids, deliberate fluorescence export adapter and larger-scale recovery/capacity tests. Extend NGFF only with explicit semantics. | Public images and engineering fixtures suffice; the current full-field replay is not a native whole-slide throughput benchmark. |
| 2 — Public comparative benchmarks | Select an independently annotated, license-compatible nuclei set; audit model/train overlap; compare native, StarDist and InstanSeg with one sampling/evaluation contract. Test complete native-resolution slide throughput across scanners. | Public reference data can start this work; generalization to the user's future acquisition remains unestablished. CMU-1 is not asserted to be lung. |
| 3 — Registration qualification | Live isolated VALIS execution, public IHC pair and controlled-transform QC are completed. Next: native slide readers/export, independent real landmarks and representative deformation coverage. | Current bounded public planes establish execution; the real pair has no independent accuracy reference. See [scope and results](STITCHING_REGISTRATION.md). |
| 4 — Broader molecular comparisons | Select a compatible independently annotated scRNA reference; justify raw-count panel/capacity and reference transfer; compare simple mapping before cell2location/Tangram. Add verified animal/timepoint replication for biological analyses. | Appropriate public references can support development; 308 selected genes and one accession proxy do not establish deconvolution or replicate-level effects. |
| 5 — Authenticated TME reproduction | Obtain processed Slide-GoTags cells through the supported portal, bind author-column/coverage provenance and predeclare one cell-level spatial reproduction target. | Authorized source access; current 240-row workbook consistency is not cell-level reproduction. The supplied paper remains the optional TME reference, not a lung-severity model. |
| 6 — Intended-use acceptance | Independent anatomy/lesion/cell masks, blinded disease-specific ordinal ratings, native/StarDist boundary review, supervised QuPath comparison, representative acquisition-domain robustness. | Independent experts and representative future images, or a genuinely matching public benchmark. The user's own dataset is not mandatory, but suitable evidence is. |

LIANA+, SpatialGlue, CODEX, UNI/HEST and histology-to-omics prediction remain
question/input-dependent branches. No release, clinical accuracy, universal
severity score, human acceptance or backend equivalence is asserted here.

# Development result through priority 5

2026-10-09. All **31 numbered jobs** have an explicit outcome in the
[roadmap/register](DEVELOPMENT_PLAN.md) and its
[JSON counterpart](DEVELOPMENT_REGISTER.json). This completes the current
development pass, with conditional engines and scientific acceptance left visible.
The product remains a tool for future high-resolution tissue images, lung
injury/regeneration first, with optional omics/TME.

| Development order | Delivered | Remaining boundary |
| --- | --- | --- |
| **1 — Interchange and integrity** | Sparse AnnData, classic Visium and SpatialData; completed-product validation; bounded NGFF and MCMICRO-compatible cell features; optional CI/capacity guards. | General multidimensional NGFF discovery and Visium HD are outside the supported profiles. |
| **2 — Real lung replay** | Pinned Kasmani source acquisition, H&E/spot overlay, raw-count reconciliation and both native round trips. | Derivative image, no independent landmarks/calibration/animal IDs, no biological-domain claims. |
| **3 — Imaging and lesion qualification** | Real WSI window benchmark, fixed pyramid reader, QuPath discrete-label export, mask metrics, sampling protocol, calibrated 2D profiles and ordinal agreement. | Independent pathology/cell references, warning review, trained-model accuracy and canonical InstanSeg executor. |
| **4 — Lung molecular context** | Versioned program interface, explicit filtering/normalization, graph baselines, conditioned spatial tests and biological-unit associations. | Real program curation, adequate features and independent specimens; reference mapping/cell2location/Tangram and BANKSY remain conditional. |
| **5 — Registration and optional TME** | Live VALIS point interface/QC, processed GoTags source profile, frozen pairs/radii, nulls/BH/jitter and published-table reconciliation. | Real paired-slide execution, authenticated processed-cell reproduction, and question-driven interaction/fusion comparisons. |

Register counts: **9 demonstrated**, **6 implemented**, **4 revised and
implemented**, **9 implemented with explicit gates**, **3 conditional branches**.
These are development statuses, not counts of validated scientific methods.

## Observed results

| Run | Result | Interpretation |
| --- | --- | --- |
| Integrated optional-stack suite | **202 tests, 144 subtests passed**; 41 upstream dependency warnings. | Contract, numerical, integrity and regression checks. |
| Build / import / lint | Source distribution and wheel built; wheel core imports with site packages disabled; scoped Ruff passed. | Optional dependencies remain optional. Existing unrelated broad-lint debt was not silently relabeled as passing. |
| Kasmani GSM6108348 | 4,992 positions: 2,486 measured, 2,506 not reported; all five raw totals and AnnData/SpatialData round trips passed. | Measured source-data interchange, not paper biology reproduction. |
| Kasmani selected totals | Sftpb 84,600; Car4 6,111; Cd8a 75; Cd4 64; Itgam 185. | Independently reconciled to deposited raw HDF5. |
| Kasmani resource use | 188.654 s; 389,857,280 bytes sampled peak RSS (~372 MiB). | One real example on this machine, not a universal performance claim. |
| Aperio CMU-1 | 46,000 × 32,914 RGB; three levels; 64 × 512-pixel windows; 15.2 ms median read and ~90.2 MiB sampled peak RSS. | First successful real-source reader qualification. Combined replay later observed 12.1 ms and ~90.5 MiB; timings vary with cache/runtime. |
| QuPath 0.7 classifier bridge | Numeric labels and grid preserved; synthetic threshold reference Dice/IoU = 1 for both classes (768 pixels each). | Runtime/export smoke evidence; no trained lesion accuracy claim. |
| Optional analysis demo | Ten independently runnable synthetic plans executed. | Demonstrates interfaces and output semantics, not biological reference data. |
| Slide-GoTags published source | All **240 RCC_1_A rows / six pairs** matched between Supplementary Table 13 and Figure 3c. | Reported-statistic consistency only; no recomputed cell-level NMS/permutation test. |

Portable records and local log/output hashes:
[priorities 1–5 evidence](../validation/evidence/priorities-1-5-20261009.json),
[completed lung evidence](../validation/evidence/priorities-1-2-20261009.json).
Commands are in [analysis workflows](ANALYSIS_WORKFLOW.md),
[interchange](SPATIAL_INTERCHANGE.md) and [imaging qualification](IMAGING_QUALIFICATION.md).
Data, downloaded workbooks, classifier fixtures and generated stores are excluded
from Git; source manifests, tests, scripts and evidence summaries are included.

## Pipeline corrections and rationale

1. **Real pyramid read failure:** TIFF level zero exposed a Zarr multiscale group.
   Explicit selected-array opening fixes both native and reduced levels; exact
   pixel regression checks cover the distinction.
2. **Incomplete large download:** a truncated Aperio file had TIFF offsets beyond
   its end. Pinned ranged acquisition now verifies response range, complete bytes,
   total size and digest before publication. Failed local evidence is preserved.
3. **Ambiguous interchange semantics:** use explicit axes, channels, units, crop
   origin and named frames. The NGFF deliverable is a bounded calibrated 0.4
   bridge, rather than silently accepting arbitrary multi-axis stores. Cell
   intensity features remain separate from integer RNA-count contracts.
4. **Unsupported morphology claims:** cuff area divided by perimeter is a 2D
   burden measure, not radial thickness. Reviewed septal transects are lengths,
   not unbiased 3D thickness. Severity remains a model-specific rubric with
   independent reviewer agreement and unresolved fields.
5. **Insufficient RNA/replication:** the five-gene real panel checks interchange.
   It cannot justify tissue domains or reference deconvolution. Program scoring
   records the denominator; association aggregates regions by verified biological
   unit within stratum and rejects repeated-group designs needing another model.
6. **Nonrigid registration and uncertain calls:** consume forward level-zero
   points from VALIS rather than fabricating an affine approximation. Separate
   held-out residuals and sampled folds from fit error. Author expression labels
   and coverage-free nanopore status are not promoted to measured genotype calls.
7. **Spatial nulls:** preserve region/coverage strata, apply a finite-permutation
   correction and BH, and abstain when scores/nulls are undefined or degenerate.
   These are explicit revisions to author analysis choices. Jitter ranges are
   sensitivity scenarios, not confidence bounds.
8. **Source reproduction scope:** public GoTags tables lack coordinates and edge
   counts; the processed-data portal requires sign-in. Reconcile the obtainable
   reported values now and retain a concrete processed-cell reproduction gate.

## Next work that can change scientific status

First obtain representative future high-resolution images and independent
pathology/cell references under the frozen sampling protocol. Then review
native/StarDist warning boundaries, score the supervised QuPath comparison and
decide whether InstanSeg adds value. For RNA, curate source-bound lung programs,
adequate measured features and independent biological units before deconvolution,
biological domains or morphology–RNA inference. For TME, run actual paired-slide
registration with independent landmarks and obtain processed source cells through
the supported access route. LIANA+, SpatialGlue, CODEX, UNI and HEST remain
conditional comparisons with declared input/question/reference requirements.

The research bibliography and method-to-job mapping remain in the
[updated methodology roadmap](../notes/2026-10-09-development-roadmap.md).
No human scientific approval or backend equivalence is inferred from this pass.

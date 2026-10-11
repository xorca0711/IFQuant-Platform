# Current project state

Update this before stopping work, every session.

Updated 2026-10-11. Branch `codex/public-data-development` starts from merged
PR #3 / main `e54192d`. The user authorized remaining feasible development,
roadmap updates, commit, push and updates to PR #4. No merge or scientific
acceptance is authorized.

## Latest: tiled nuclei and live VALIS

- Resumable whole-grid InstanSeg with core pixel ownership, conservative overlap
  identity, lock/recovery behavior, calibrated object tables and tiled BigTIFF.
  Public full-field replay: nine tiles, 5,726 candidates, 44 seam flags; package
  reconstruction passed. This is not a native whole-slide throughput benchmark.
- Single-window comparison: F1 0.99053 / matched IoU 0.99186 on shared pixels.
  This measures tiling sensitivity; independent segmentation accuracy is open.
- Isolated VALIS 1.2.0 execution: controlled public-image transform RMSE 5.949 µm
  across 16 points; real IHC pair completed nonrigid registration with no sampled
  folds. Real pair accuracy is undefined without independent landmarks; physical
  section relation remains unknown.
- Full suite: 217 tests / 144 subtests passed. After the final pre-allocation
  capacity guard, nine focused tests passed (including one new regression), and
  the public package reconstructed unchanged. Scoped lint and core wheel passed.
- Runtime and source constraints, failed-attempt rationale and artifact hashes
  are in [new evidence](validation/evidence/stitching-valis-20261011.json) and
  [execution guide](docs/STITCHING_REGISTRATION.md). Publication targets existing
  [PR #4](https://github.com/xorca0711/IFQuant-Platform/pull/4); GitHub is authoritative
  for current remote checks.

## Earlier public development increment

- Pinned CPU InstanSeg H&E ROI nuclei inference and calibrated object exports.
  All 336 objects in the upstream model fixture matched (F1/IoU 1); a calibrated
  public ROI produced 1,026 nuclei. Conformance is not independent accuracy.
- Five source-cited Niethamer mouse lung marker panels; exact Ensembl IDs and
  injury/timepoint interpretation limits. Shared complete full-library totals
  protect normalization from feature-panel selection.
- Broader real lung replay: 308 features, 613,472 nonzero counts, 2,486 measured
  spots and 2,506 not-reported positions. All selected gene totals reconcile.
  Expression/graph baselines and optional BANKSY λ=0/0.8 execute on the same data.
- NGFF 0.4/0.5 bounded uint8 planes with explicit T/Z/channel selection, preserved
  physical coordinates and storage/dimension-name checks.
- Complete H&E pipeline at CMU-1 pyramid level 1: 94,622,000 pixels, 391 tiles,
  281.3 s local analysis and approximately 161 MiB sampled peak RSS; package
  revalidation passed. Same-image appearance fit is a workload, not pathology truth.
- Regression suite: **209 tests and 144 subtests passed**; 41 upstream warnings.
  Optional CPU-engine CI now checks a BANKSY fixture and pinned model conformance.

[Portable evidence](validation/evidence/public-development-20261011.json),
[workflow/results/gaps](docs/PUBLIC_DEVELOPMENT.md) and the updated
[31-job register](docs/DEVELOPMENT_PLAN.md) are the current records.
The [original execution report](docs/EXECUTION_REPORT.md) preserves prior evidence.
GitHub is authoritative for the follow-up PR and remote checks.

## Remaining gaps, in order

1. Independent annotated nuclei comparisons and seam review; native-resolution
   multi-scanner throughput, label pyramids and deliberate fluorescence adapters.
   These remain software/public-data work, not private-data gates.
2. Native VALIS slide readers/warped-image export, independent real paired-slide
   landmarks and representative local deformation coverage. Bounded-plane live
   execution is complete; real-pair accuracy is still unmeasured.
3. Compatible scRNA reference selection, count-capacity qualification and verified
   specimen identities before cell2location/Tangram or biological associations.
4. Supported authenticated Slide-GoTags cell access before cell-level reproduction.
   Existing workbook agreement covers 240 reported rows / six pairs only.
5. Expert anatomy/lesion/cell references, native/StarDist warning decisions,
   supervised QuPath comparison, disease-specific ordinal rubric and representative
   acquisition validation. No universal injury score or scientific acceptance.

Optional LIANA+/SpatialGlue/CODEX/UNI/HEST remain question/input dependent.
The tool still targets future high-resolution images; public resources do not
constrain its product identity. Lung injury/regeneration remains first.

## Runtime and publication

`.venv-spatial` uses isolated x64 CPython on this ARM64 Windows host. New optional
extras are `inference` and `domains`; model weights, source data and generated runs
stay ignored. Zarr local sockets need normal runtime access on this host. See
[agent context](AI_CONTEXT.md) for operational details and [third-party notices](THIRD_PARTY_NOTICES.md)
for optional engine terms. Preserve historical records and failed attempts.

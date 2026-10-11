# Current project state

Update this before stopping work, every session.

Updated 2026-10-11. Branch `codex/public-data-development` starts from merged
PR #3 / main `e54192d`. The user authorized remaining feasible development,
roadmap updates, commit, push and a follow-up PR. No merge or scientific
acceptance is authorized.

## Delivered in this increment

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

1. Whole-slide InstanSeg stitching, resume and deliberate package adapters;
   independent annotated public comparisons and native-resolution multi-scanner
   throughput. These remain software/public-data work, not private-data gates.
2. Actual VALIS public paired-slide runtime execution and held-out landmark QC.
   The existing point adapter is implemented; a live registration replay is not.
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

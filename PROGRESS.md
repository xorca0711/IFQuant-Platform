# Current project state

Updated 2026-10-09. Branch `codex/development-priorities-1-5`. Follow-up publication is tracked on this branch. Earlier
[PR #2](https://github.com/xorca0711/IFQuant-Platform/pull/2) was already merged;
this increment is a separate PR.
Commit/push/PR updates are authorized. No merge or deployment is authorized.

The user expanded scope from priorities 1–2 to all jobs through **priority 5**,
including pipeline corrections, rationale, current documentation and an overall
report. That development pass is implemented for review; independent scientific
acceptance and conditional engines remain explicit in the
[31-job register](docs/DEVELOPMENT_PLAN.md) and
[execution report](docs/EXECUTION_REPORT.md).

## Current deliverables and observed evidence

- Native AnnData/classic Visium/SpatialData interchange, completed links/context
  validation, bounded calibrated NGFF intake and numeric MCMICRO-compatible tables.
- Real Kasmani Day 3 young-lung replay: 4,992 positions, 2,486 measured RNA,
  2,506 not reported; five raw-count totals reconciled; both native round trips
  pass. Image is a deposited 2000 × 1834 derivative with no invented physical
  calibration or independent animal identity.
- Real 46,000 × 32,914 RGB Aperio image benchmark: 64 reproducible 512-pixel
  windows, 15.2 ms median read, about 90.2 MiB sampled peak RSS on this host.
  A real pyramid-level reader bug was corrected. This is not full-slide analysis
  throughput or lung pathology validation.
- QuPath 0.7 discrete classifier bridge executed; a synthetic threshold reference
  matched exactly. Independent supervised lesion-model scoring remains gated.
- Calibrated 2D cuff/septal measurements, mask metrics, ordinal reviewer agreement,
  explicit RNA programs/normalization, domain baselines, biological-unit
  associations, live VALIS point export/QC, processed GoTags profile and frozen
  spatial hypotheses/nulls. Ten runnable synthetic workflow examples.
- Published Slide-GoTags source reconciliation: 240 RCC_1_A rows / six pairs match
  between supplement and figure data. Processed-cell portal sign-in is required;
  cell-level spatial reproduction has not run.

Verification and hashes are recorded in
[`validation/evidence/priorities-1-5-20261009.json`](validation/evidence/priorities-1-5-20261009.json).
The completed lung record is
[`validation/evidence/priorities-1-2-20261009.json`](validation/evidence/priorities-1-2-20261009.json).
GitHub is authoritative for the latest remote checks.

## Remaining gates, in order

1. Representative intended-use images, acquisition metadata, independent expert
   anatomy/artifact/lesion/cell references and a frozen disease-specific rubric.
2. Human review of native/StarDist boundaries and topology warnings; scored
   baseline/supervised classifier comparisons. Canonical InstanSeg execution is
   conditional and unimplemented.
3. Curated lung gene programs, sufficiently broad measured features and verified
   independent specimens; compatible references before cell2location/Tangram or
   BANKSY comparisons. The five-gene replay cannot establish biological domains.
4. Actual paired-slide VALIS execution with independent landmarks; supported
   access to processed Slide-GoTags cells before a cell-level reproduction.
5. Question-driven activation of LIANA+, SpatialGlue, CODEX, UNI/HEST; future
   intended-use and acquisition-domain evaluation (roadmap WP6).

## Reproducibility / historical records

Use the [workflow commands](docs/ANALYSIS_WORKFLOW.md). On this Windows ARM64 host,
the complete optional stack is `.venv-spatial` using isolated x64 CPython.
Zarr local async socket pairs and QuPath Java preferences require unsandboxed
execution in this environment. Core imports remain lazy. Raw data, model weights,
environments and generated runs stay in ignored caches/output, never Git.

The earlier saved checkpoint `2566fc1` and
[checkpoint note](notes/2026-10-09-priorities-1-2-checkpoint.md) remain historical.
Their in-progress statements are superseded by this state. Prior 156/144 and
181/144 test totals belong to earlier code checkpoints. Fluorescence Phase 1–9
records remain scoped evidence; current priorities 1–5 are a different numbering
system. Preserve failed-run evidence and human-review boundaries.

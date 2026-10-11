# Agent handoff

Read [PROGRESS](PROGRESS.md), [the numbered register](docs/DEVELOPMENT_PLAN.md),
[execution report](docs/EXECUTION_REPORT.md) and [analysis guide](docs/ANALYSIS_WORKFLOW.md).
They supersede the saved priorities 1–2 checkpoint. The current user authorized
all work through priority 5, fixes with rationale, current docs and commit/push/PR.
Do not infer permission to merge or any human scientific acceptance.

- Workspace `X:/GitHub/IFQuant-Platform`; branch `codex/public-data-development`,
  based on merged PR #3 / main `e54192d`; publish a new follow-up PR. Legacy `X:/GitHub/IFQuant-Lung` is read-only. MIT original source;
  third-party code/model/data terms remain separate. No subagents were used.
- Product: future high-resolution tissue imaging and spatial phenotyping;
  lung injury/regeneration first, optional TME/omics. Public data are development
  resources, not a product restriction. User cannot provide own validation data.
- Current priority numbering 1–5 differs from product stages/WP0–WP6 and historical
  fluorescence governance Phases 1–9. All 31 register entries have a status,
  evidence and remaining gate. Conditional engines must not be called implemented.
- Existing fluorescence v1, tissue and spatial schema families remain distinct.
  New analysis plans use closed versioned runtime validation. Optional imports
  must stay lazy. Never label intensity tables RNA counts or author annotations
  coverage-supported genotype calls without the required data.
- Main full-stack runtime is `.venv-spatial/Scripts/python.exe` (x64) because the
  ARM64 SpatialData/GDAL stack did not install. `.venv` remains the lightweight
  ARM environment. Lock extras: dev, imaging, morphology, performance, spatial,
  spatialdata, wsi-codecs, inference, domains. Optional torch is CPU 2.8.0,
  instanseg-torch 0.1.2 and pybanksy 1.3.5; Python 3.11–3.13 x64. No global changes.
- Set TEMP/TMP to ignored `validation/output` as needed. Zarr's asyncio socket
  pair cannot run under this host's sandbox; use approved local escalation for
  tests/replays. QuPath is `X:/QuPath/QuPath-0.7.0 (console).exe`; Java preferences
  also need normal runtime access. Never pass `--save` for export-only scripts.
- Fresh destinations are mandatory. Recompute after code/input changes; do not
  mutate completed run packages. Existing failed run outputs remain evidence.
- Raw/cache files and generated outputs are ignored. Commit portable evidence,
  manifests and scripts only. Source papers/workbooks, images, weights and runtime
  binaries are not part of Git. Input download is explicit and pinned.
- New evidence: `validation/evidence/public-development-20261011.json`; 209 tests
  plus 144 subtests passed. `docs/PUBLIC_DEVELOPMENT.md` gives commands/results/gaps.
  Pinned model conformance and public ROI inference, 308-feature lung/BANKSY replay,
  five marker panels, NGFF multi-axis planes, 391-tile reduced-level H&E execution.
- Earlier real checks: Kasmani interchange/count replay; Aperio read benchmark; QuPath
  synthetic label bridge; source-workbook consistency. None establishes clinical,
  injury, registration, lineage, cognate TCR or biological domain validity.
- All future claims requiring humans/data remain open: independent pathology
  labels, severity rubric, native/StarDist warning acceptance, supervised model
  comparisons, broad-feature biological analyses and representative paired-slide
  registration. InstanSeg now executes a bounded H&E ROI through a separate tissue contract;
  it does not unlock the fluorescence-v1 canonical backend. Whole-slide stitching
  and independent accuracy remain open. BANKSY feature comparison executes;
  cell2location/Tangram/LIANA+/SpatialGlue/CODEX remain conditional.
- Tests, example outputs and provenance summaries are linked from the current
  evidence JSON. Reuse valid checks; repeat only after relevant changes. Remote
  CI status must be read from GitHub, not inferred from local success.

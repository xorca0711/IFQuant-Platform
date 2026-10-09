# Agent handoff

Read [PROGRESS](PROGRESS.md), [the numbered register](docs/DEVELOPMENT_PLAN.md),
[execution report](docs/EXECUTION_REPORT.md) and [analysis guide](docs/ANALYSIS_WORKFLOW.md).
They supersede the saved priorities 1–2 checkpoint. The current user authorized
all work through priority 5, fixes with rationale, current docs and commit/push/PR.
Do not infer permission to merge or any human scientific acceptance.

- Workspace `X:/GitHub/IFQuant-Platform`; branch `codex/development-priorities-1-5`,
  with a new follow-up PR; earlier PR #2 is merged. Legacy `X:/GitHub/IFQuant-Lung` is read-only. MIT original source;
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
  spatialdata, wsi-codecs. No global environment changes required.
- Set TEMP/TMP to ignored `validation/output` as needed. Zarr's asyncio socket
  pair cannot run under this host's sandbox; use approved local escalation for
  tests/replays. QuPath is `X:/QuPath/QuPath-0.7.0 (console).exe`; Java preferences
  also need normal runtime access. Never pass `--save` for export-only scripts.
- Fresh destinations are mandatory. Recompute after code/input changes; do not
  mutate completed run packages. Existing failed run outputs remain evidence.
- Raw/cache files and generated outputs are ignored. Commit portable evidence,
  manifests and scripts only. Source papers/workbooks, images, weights and runtime
  binaries are not part of Git. Input download is explicit and pinned.
- Real checks: Kasmani interchange/count replay; Aperio read benchmark; QuPath
  synthetic label bridge; source-workbook consistency. None establishes clinical,
  injury, registration, lineage, cognate TCR or biological domain validity.
- All future claims requiring humans/data remain open: independent pathology
  labels, severity rubric, native/StarDist warning acceptance, supervised model
  comparisons, broad-feature biological analyses and representative paired-slide
  registration. See the register for conditional InstanSeg/cell2location/BANKSY/
  Tangram/LIANA+/SpatialGlue/CODEX activation criteria.
- Tests, example outputs and provenance summaries are linked from the current
  evidence JSON. Reuse valid checks; repeat only after relevant changes. Remote
  CI status must be read from GitHub, not inferred from local success.

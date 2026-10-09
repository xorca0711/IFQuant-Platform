# Phase 5 replaceable-backend status

## Current checkpoint — 2026-10-09

Fresh StarDist run `pilot-20261009-engineering-11-stardist` completed export,
independent structural validation and deterministic QC rendering. It produced
2,380 candidates: 2,308 accepted and 72 boundary exclusions. Of the accepted
objects, 1,322 retain topology warnings; all remain engineering candidates.
The QC-only 0.001-pixel repair has now been exercised at runtime. No biological
approval or backend comparison follows from this success.

Evidence: `validation/evidence/stages-1-4-20261009.json`; ignored detailed output
is in `validation/output/pilot-20261009-engineering-11-stardist`. Run 10 retains
its sandbox/Java preferences failure. Human H1/H2 review remains pending, and
InstanSeg still fails explicitly as unimplemented. Stage 1–4 tissue/reporting
work is described separately in `docs/STAGES_1_4_STATUS.md`.

## Historical checkpoint — before the fresh run

Phase 5 has started with the recommended StarDist-first sequence. The adapter
engineering boundary is implemented; InstanSeg has not started and no backend
comparison or selection has been made.

Work is intentionally paused before the next QuPath execution. StarDist
inference and object creation have run successfully on the preserved full-image
engineering project. Two fail-closed integration findings were recorded:

- StarDist intensity keys are exactly `Cell: DAPI: Mean`,
  `Cytoplasm: DAPI: Mean`, and `Nucleus: DAPI: Mean`; these observed names are
  bound in the next run configuration rather than inferred by the exporter.
- Some valid StarDist polygon inputs trigger a JTS `free hole` topology error
  while calculating the QC-only nucleus-outside-cell area. The current local
  checkpoint preserves canonical WKT at 10^-6 pixel precision and adds a
  deterministic 0.001-pixel precision repair only for that QC overlay metric.
  This change has static tests but has not yet been exercised by another
  QuPath run.

Preserved ignored run evidence is under
`validation/output/pilot-20260830-engineering-06-stardist` through
`pilot-20260830-engineering-09-stardist`. Runs 06-09 are diagnostic or failed
engineering attempts and are not validated packages. Resume by creating a new
run identity; do not overwrite them.

The saved source checkpoint is commit `0cad6b0` on branch
`codex/phase5-stardist`. A clean x64 environment passes all 112 tests and 130
schema/contract subtests. The checkpoint has not yet demonstrated that the
staged QC overlay repair succeeds at runtime; that is the first resume action.

Implemented StarDist controls:

- QuPath `StarDist2D` is loaded only for a `stardist` run, so the native
  watershed executor does not acquire an extension dependency.
- QuPath version, extension JAR, model descriptor, `.pb` model weights, and
  preprocessing profile are distinct, required, SHA-256-bound artifacts.
- The loaded class code source and implementation version must equal the
  configured extension artifact and version.
- DAPI channel, local percentile normalization, inference resolution,
  threshold, tile size, cell expansion/constraint, threads, simplification,
  measurements, probability retention, and parent constraint are explicit.
- Existing-detection refusal, complete candidate accounting, boundary policy,
  canonical export, QC, and non-claims remain shared with native QuPath.
- InstanSeg still fails with `CANDIDATE_BACKEND_NOT_IMPLEMENTED`; there is no
  silent fallback.

## Runtime assets

Official assets staged in the Git-ignored local runtime cache:

| Artifact | SHA-256 |
| --- | --- |
| `qupath-extension-stardist-0.6.0.jar` | `8c8be80fc9169802a5ef58f7d73f8c0474f7dbbfd13709d24e18d3cc445ff73b` |
| `dsb2018_heavy_augment.pb` | `fc1f1148f22180bf2874346d14926e7baf8486088cb66277e13cb22ddccfe01b` |

The candidate follows the official QuPath 0.7 StarDist scripting API and uses
OpenCV inference. DJL/TensorFlow and GPU execution are deliberately outside
this first adapter scope.

## Gates

| Gate | State | Advancement condition |
| --- | --- | --- |
| P5-E1 identity-bearing adapter | Engineering pass, including run 11 runtime preflight | Recheck after adapter/runtime changes. |
| P5-E2 StarDist smoke execution | Passed engineering export, validation and QC in run 11 | Preserve the fresh run and all earlier failed evidence; biological review remains separate. |
| P5-H1 visual review | Pending after smoke run | Inspect DAPI overlay and failure populations; record reviewer/date/rationale. |
| P5-S1 comparative scoring | Blocked by real Phase 3/4 gates | Score native and StarDist separately on the same frozen reviewed real references with prospective criteria. |
| P5-E3 InstanSeg adapter | Not started | Begin only after StarDist export/preflight boundary is stable. |

No Phase 5 artifact establishes scientific validation, backend equivalence,
model universality, or authorization.

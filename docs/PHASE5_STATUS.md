# Phase 5 replaceable-backend status

## Current checkpoint

Phase 5 has started with the recommended StarDist-first sequence. The adapter
engineering boundary is implemented; InstanSeg has not started and no backend
comparison or selection has been made.

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
| P5-E1 identity-bearing adapter | Static engineering pass: focused tests and full regression suite pass | Complete runtime preflight and preserve distinct extension/model/preprocessing identities. |
| P5-E2 StarDist smoke execution | Pending | Run a fresh full-image engineering package and deterministic QC without overwriting native evidence. |
| P5-H1 visual review | Pending after smoke run | Inspect DAPI overlay and failure populations; record reviewer/date/rationale. |
| P5-S1 comparative scoring | Blocked by real Phase 3/4 gates | Score native and StarDist separately on the same frozen reviewed real references with prospective criteria. |
| P5-E3 InstanSeg adapter | Not started | Begin only after StarDist export/preflight boundary is stable. |

No Phase 5 artifact establishes scientific validation, backend equivalence,
model universality, or authorization.

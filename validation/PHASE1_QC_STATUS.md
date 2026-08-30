# Phase 1 DAPI QC status

Status: **engineering evidence complete; human review and geometry-policy
confirmation open**.

This record describes the fresh `pilot-20260830-engineering-03` run. Its full
package, source derivative, per-candidate ledger, and rendered images are under
the Git-ignored local `validation/output/` tree. They are not published by this
document.

Nothing here establishes segmentation accuracy, biological validity, backend
equivalence, endpoint fitness, model universality, or authorization for a
biological dataset.

## Bound run

- QuPath: 0.7.0, native `WatershedCellDetection`.
- Exporter source revision:
  `926d1768d91c294b3cd44e6ec05c1fa45ea5e15a`.
- Exporter SHA-256:
  `00b8650a9c1c6d9ea6ebb13db569f013e8a8f719340fa422720fb510e6fd11fd`.
- Renderer source revision:
  `8910706ff9fa5a660bbf3f693e54c9e2bf5fff6a`.
- Renderer-module SHA-256:
  `a42347f28c7e595f78a733931ae2ce157ec9f1b9abdf1e33cd554515d711147b`.
- Source OME-TIFF SHA-256:
  `28e4c767036b0dca540a820096a0f76baa0277c33ed60bbb2cc0099539592eb8`.
- Canonical package SHA-256:
  `5baa7e4c02eeac0166b0428f581cbaa7f213d082d5d24b9aaeabc4765d7eefa7`.
- Candidate-manifest canonical SHA-256:
  `963753d68d128452ddf6e90f38b5b83ac24317e172c928a477d47b1919c2733a`.

The canonical package validator reports `valid` for structural, referential,
and byte integrity. The complete candidate-ledger validator also reports
`valid`. Fifty Python tests pass with the imaging extras; the core-only run
passes with the one imaging test skipped. The finalized exporter compiles under
QuPath 0.7.0. These are engineering checks only.

## Candidate reconciliation

| Outcome | Count |
| --- | ---: |
| Detected candidates | 1,551 |
| Accepted canonical objects | 1,453 |
| Excluded: cell not covered by annotation | 45 |
| Excluded: cell touches annotation boundary | 53 |
| Geometry warnings across all candidates | 207 |
| Geometry warnings among accepted objects | 182 |
| Geometry warnings among excluded candidates | 25 |

For the 182 accepted warnings, the nucleus area outside the cell has a median
fraction of 0.0377%, a 95th-percentile fraction of 0.4593%, and a maximum of
1.2676%. The maximum outside area is 2.4441 px². Of those warnings, 127 are at
or below 0.1%, 46 are above 0.1% and at or below 0.5%, seven are above 0.5% and
at or below 1%, and two exceed 1%.

These values quantify the topology warning; they do not determine whether an
object is biologically acceptable or whether its measurements are unbiased.

## Local review outputs

The primary local directory is:

```text
validation/output/pilot-20260830-engineering-03/qc-rendered/
```

| File | Purpose | SHA-256 |
| --- | --- | --- |
| `dapi-overview.png` | DAPI display, supplied ROI, 100 µm scale bar | `671d86c67892fc7442f75d85c38687736dc52daba86bd458542dfb44e6f7347a` |
| `dapi-candidate-disposition.png` | Complete cell/nucleus candidate overlay and dispositions | `405e25a94a75b456d008cc54b4f1f968369343dd7deb5b8eb645aa588e6e2244` |
| `dapi-review-montage.png` | Eight highest-severity accepted warnings and eight deterministic controls | `4a6b711ac838e717d6f6eff9d9387cca0cc2f719d91e52bbf25215c3c5470d36` |
| `qc-manifest.json` | Input, display, selection, implementation, output, and non-claim bindings | `4c3beaa31616f1801a0e03efe1e9901ad5aa5f97ce5f885768e6d6188c8615be` |

A second fresh render is byte-identical for all four files. Display windowing is
the deterministic 1st to 99.8th percentile range, corresponding to native DAPI
sample values 15 to 3,027 for this derivative.

Overlay colors are green for accepted cell contours, orange for other excluded
cells, magenta for boundary-excluded cells, yellow for warning nucleus
contours, and cyan for the supplied ROI.

Because this is DAPI-only review evidence, it can support inspection of nuclear
detection and nucleus contour placement. The expanded cell contours are
algorithmic constructions, not membrane ground truth, and cannot be declared
biologically accurate from this image alone.

## Required human gates

Before Phase 2, a reviewer should check the overview, complete overlay, and
warning/control montage for obvious missed nuclei, fragments, merges, implausible
cell expansion, boundary behavior, and systematic dense/sparse-region effects.
The reviewer and method owner must then record one geometry-policy outcome:

1. **Exclude conservatively** — retain all warnings in immutable evidence but
   make the 182 accepted flagged objects ineligible downstream. This remains
   the default until another outcome is confirmed.
2. **Accept under a precise rule** — state a machine-testable topology/severity
   rule and its scope, then evaluate potential morphology/intensity bias.
3. **Revise and rerun** — change detector parameters, cell construction, or
   geometry handling under a new method and run identity.

Confirmation should include reviewer identity, review date, selected outcome,
rationale, and any declared rule. Until then, Phase 2 remains blocked and all
objects retain QC `not_evaluated` and review `unreviewed`.

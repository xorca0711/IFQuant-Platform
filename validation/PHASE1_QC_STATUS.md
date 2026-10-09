# Phase 1 DAPI QC status

> **Scope:** fluorescence governance/backend evidence. Its phase numbers are
> distinct from the current tissue/spatial development priorities. See the
> [active plan](../docs/DEVELOPMENT_PLAN.md) and [current progress](../PROGRESS.md).


Status: **full-frame engineering policy verified; formal H1 review and H2
geometry-warning disposition remain open for biological eligibility**.

The current evidence is the fresh
`pilot-20260830-engineering-05-full-crop-guard` run. It uses the complete
2048 × 2048 image, not an inset ROI. The user described the DAPI overlay as
seemingly acceptable and requested full-image detection. The symmetric
full-frame guard is independently verified engineering behavior; it is not
recorded as a formal human policy approval. Run 04 is retained as a superseded
engineering audit because it exposed QuPath's positive-edge detector-grid
rounding; it was not overwritten.

The package, source derivative, per-candidate ledger, and rendered images remain
under the Git-ignored local `validation/output/` tree. Nothing here establishes
segmentation accuracy, biological validity, backend equivalence, endpoint
fitness, model universality, or authorization for biological analysis.

## Bound run

- QuPath: 0.7.0, native `WatershedCellDetection`.
- Exporter source revision:
  `f8fe27053700f012e91959c5b4aa1f83a0da8224`.
- Exporter SHA-256:
  `7e28147d359efe7a1400c21ef883eec67e016a5dba79f325bde8f31f942950c2`.
- Renderer-module SHA-256:
  `4eb80e09cb897817c1d2aa22ad0605f564fb5ea6c50d5e5ad1cbd9238786523d`.
- Source OME-TIFF SHA-256:
  `28e4c767036b0dca540a820096a0f76baa0277c33ed60bbb2cc0099539592eb8`.
- Canonical package SHA-256:
  `e086130f68823ef30dd30e4b0f596dcf3842cff215b7b2638e02ecccc5e5125f`.
- Candidate-manifest canonical SHA-256:
  `e4a38bceaf10a6d72dfbbffbcd8e889d32ba26a61b5f5e79ca7a92bef6a59a67`.

The canonical package and complete candidate-ledger validators report `valid`
for structural, referential, geometric-policy, and byte integrity. The run05
boundary implementation passed 58 tests when committed; the current branch,
including the initial Phase 2 contract, passes the full repository test suite.
These are engineering checks only.

## Candidate reconciliation and boundary decision

| Outcome | Count |
| --- | ---: |
| Detected candidates | 1,803 |
| Accepted canonical objects | 1,700 |
| Excluded: within full-image boundary guard | 103 |
| Guard members: top | 33 |
| Guard members: left | 23 |
| Guard members: right | 27 |
| Guard members: bottom | 21 |
| Geometry warnings across all candidates | 204 |
| Geometry warnings among accepted objects | 194 |
| Geometry warnings among guard exclusions | 10 |

The guard is one effective detector-processing pixel: 0.5 µm, or
1.4492842522051745 native pixels for this image. Top/left coordinates at or
below the guard and right/bottom coordinates at or above
`image dimension - guard` are classified symmetrically. Side counts need not be
equal and can overlap at a corner; the acceptance invariant is **zero accepted
guard members**, which the independent Python validator confirms.

The earlier right/bottom asymmetry was representational: the 0.5 µm detector
grid mapped its terminal coordinate to about 2047.84 rather than 2048, while
the origin remained exactly zero. Exact `>= 2048` comparisons therefore missed
positive-edge objects. The declared guard corrects this without clipping or
modifying governed geometry.

## Geometry-warning evidence

For the 194 accepted warnings, nucleus area outside the cell has a median
fraction of 0.0410%, a 95th-percentile fraction of 0.6187%, and a maximum of
1.6491%. The maximum outside area is 1.9137 px². Of those warnings, 125 are at
or below 0.1%, 56 are above 0.1% and at or below 0.5%, 12 are above 0.5% and at
or below 1%, and one exceeds 1%.

These values quantify a normalized topology warning. They do not decide whether
an object is biologically acceptable or whether morphology/intensity estimates
are unbiased.

## Local review outputs

The primary local directory is:

```text
X:\GitHub\IFQuant-Platform\validation\output\pilot-20260830-engineering-05-full-crop-guard\qc-rendered\
```

| File | Purpose | SHA-256 |
| --- | --- | --- |
| `dapi-overview.png` | Full-image DAPI, full-frame cyan ROI, 100 µm scale bar | `c65ad8e726c8d119da812e8bbcaf15e3a0adaea2f514e6dd1487f22939594a23` |
| `dapi-candidate-disposition.png` | Complete cell/nucleus overlay; four-sided edge exclusions | `e565dbb116a0a6874b5b867e94b989ee6ea9de39c80fcf2ee81fd8a4847318e7` |
| `dapi-review-montage.png` | Eight highest-fraction accepted warnings and eight deterministic controls | `109200fde452a01b7af9e8ce44921b206059023b1783104dc3dfbd3601883325` |
| `qc-manifest.json` | Inputs, guard, counts, display, renderer, outputs, and non-claims | `a065d7e014e5f546a8642a44360d2c55dcf529c5aa2c5d2eec5b0610a6a73bdc` |

A second fresh render under `qc-rendered-repeat-verification/` is byte-identical
for all four files. Local machine-readable validation evidence is under the
same run's `attestations/` directory.

Overlay colors are green for accepted cell contours, magenta for boundary-guard
exclusions, yellow for warning nucleus contours, and cyan for the full-frame
ROI. Because this is DAPI-only evidence, it supports inspection of nuclear
detection and contour placement. Expanded cell contours remain algorithmic
constructions, not membrane ground truth.

## Remaining H2 gate and Phase 2 boundary

The DAPI appearance assessment is provisional; H1 still needs reviewer
identity, date, and rationale. The full-frame edge guard is independently
verified engineering behavior. H2 requires one recorded outcome for the 194
accepted topology warnings:

1. **Exclude conservatively** — keep the objects in immutable evidence but make
   them ineligible downstream. This is the active default.
2. **Accept under a precise rule** — declare a machine-testable rule and evaluate
   morphology/intensity bias under its intended scope.
3. **Revise and rerun** — change cell construction or geometry handling under a
   new method/run identity.

Phase 2 observation-contract and validator infrastructure may proceed without
resolving H1/H2. The source observation itself still requires biological
identities and reviewed-annotation evidence. No run05 detected object may enter
reference labels, training inputs, biological object datasets, or endpoint
aggregation until H1/H2 are resolved.

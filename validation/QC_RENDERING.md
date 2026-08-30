# Deterministic DAPI engineering QC rendering

`ifquant-platform render-qc` turns a structurally valid canonical cell-object
package and its complete candidate-disposition sidecar into review aids. It does
not change the package, make a QC decision, or constitute scientific validation.

## Inputs and fail-closed checks

The command first runs the canonical package validator. It then requires:

- `qc/candidate-dispositions-manifest.json`;
- the manifest-bound `qc/candidate-dispositions.jsonl`;
- exact package, image, annotation-set, segmentation-run, and coordinate-space
  identity agreement;
- exact JSONL SHA-256, byte size, count, canonical rows, and ascending indices;
- recomputed candidate identities from image/run/coordinate identities and
  normalized cell/nucleus WKT;
- a one-to-one link from every accepted candidate to every package object;
- exact geometry, centroid, annotation, source-detection, and warning agreement
  for accepted objects;
- reconciled disposition, reason, and geometry-warning counts;
- independently recomputed top/right/bottom/left physical-edge contact from
  candidate WKT and manifest-bound image dimensions;
- for the symmetric image-boundary policy, exactly one included annotation whose
  rectangle equals the complete image extent;
- exact script, run-configuration, source-image, and annotation-content hashes;
- explicit `false` scientific-validation, backend-equivalence, and
  model-universality claims with authorization `none`.

Pillow and NumPy are optional and imported only after those checks pass. Install
them with `pip install -e ".[qc]"`. Core contract imports and validation remain
usable without the imaging extras.

## Usage

From the repository root:

```powershell
ifquant-platform render-qc `
  "X:\path\to\qupath-output" `
  --output "X:\path\to\qupath-output\qc\rendered"
```

The output directory must not already exist. Candidate paths default to the
two `qc/` sidecars under the package. They can be supplied explicitly with
`--candidate-manifest` and `--candidate-dispositions`, but the JSONL path must
still equal the manifest-bound package-relative path.

Optional display controls are `--lower-percentile`, `--upper-percentile`,
`--montage-per-group`, and `--montage-crop-size`. Defaults are 1%, 99.8%, eight
warning/control crops per group, and 192 pixels.

## Outputs

- `dapi-overview.png`: recorded DAPI display window, included ROI, and calibrated
  scale bar. A full-frame ROI ending at the continuous coordinate equal to image
  width/height is clamped to the final visible pixel only for display, so all
  four cyan sides remain visible; governed geometry is unchanged.
- `dapi-candidate-disposition.png`: all candidate cell/nucleus contours, ROI,
  scale bar, and legend. Cell contours encode disposition: green is accepted,
  orange is another exclusion, and magenta is a boundary exclusion. A yellow
  nucleus contour independently marks a nucleus-outside-cell warning, including
  when its candidate cell was excluded. Cyan is the ROI.
- `dapi-review-montage.png`: deterministic warning and control crops with full
  accepted object IDs. Warning crops prioritize the largest recorded
  nucleus-outside-cell fraction, then area, then a package-seeded SHA-256 tie
  break. Controls use package-seeded SHA-256 ranking.
- `qc-manifest.json`: canonical input bindings, nearest-rank display percentiles
  and resulting native-sample bounds, dependency versions, scale bar, selection
  rule and selected IDs, disposition/reason/physical-edge-side counts, output
  dimensions/hashes, exact renderer-module SHA-256 and Python version, and
  non-claims.

For unsigned 8/16-bit data, percentile bounds use an exact integer histogram and
nearest-rank selection. The same inputs, options, and Pillow/NumPy versions yield
the same PNG and manifest bytes. The dependency versions are recorded because
PNG encoding and text rasterization are implementation inputs.

## Review boundary

These images provide evidence for a human geometry review gate. A reviewer must
still decide whether warnings are benign raster/vector precision effects,
correctable cell-construction defects, or detector failures. The renderer does
not turn `not_evaluated` objects into passes, does not persist review decisions,
and does not authorize dataset or model use.

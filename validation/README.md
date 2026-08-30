# Validation

The initial execution record is in `PILOT_STATUS.md`. The current deterministic
DAPI evidence, geometry-warning statistics, and open human gate are in
`PHASE1_QC_STATUS.md`. Both records preserve explicit non-validation boundaries.

Validation separates structural conformance from scientific claims. The initial
CLI checks contracts and canonical cell-object packages; passing it means that
the artifact is internally consistent for the identities and local artifacts
it declares, not that every upstream artifact was independently retrieved or
that a backend or endpoint is biologically valid.

## Validation layers

### Contract and integrity

- reject missing or unknown fields, duplicate identities, invalid units, and
  ambiguous missingness;
- verify bytes for local source/artifact paths, canonical hashes for bound
  manifests and method contracts, geometry-derived object IDs, and exact
  cross-document echoes for detector/model/preprocessing identities;
- validate channel mapping, dimensions, calibration, coordinate frames, and
  object/compartment relationships;
- reconcile object counts, object/package QC, review counts/reviewer evidence,
  corrections, and any declared abstained predictions; and
- reject stale, partial, mixed-method, or silently repaired packages.

### Deterministic and numerical fixtures

Use synthetic fixtures for geometry encoding, object ordering, calibrated
morphology, compartment ownership, intensity statistics, threshold boundaries,
empty observations, anisotropic pixels, and annotation-edge behavior. Repeated
runs with identical inputs must serialize the same canonical evidence, excluding
explicitly non-semantic runtime metadata.

### Segmentation evaluation

Evaluate detection matches, misses, false positives, split/merge errors,
boundary and overlap measures, count bias, and geometry error. Preserve
per-object match data and signed differences. Compare candidate backends on the
same immutable observations without pooling them as one method.

### Downstream effect and model evaluation

- quantify bias propagated into morphology, compartment intensity, and declared
  endpoints;
- evaluate probability calibration and reliability by relevant groups;
- report abstention coverage, retained-set error, and failure reasons;
- test domain shift across scanner, batch, staining, and specimen conditions;
- keep mouse, slide, batch, and scanner groups disjoint as required by the split
  design; and
- report uncertainty and subgroup sample counts, not correlation alone.

## CLI contract

The validation CLI should accept explicit input paths and an optional expected
contract or method-instance identity, produce a machine-readable report, and
return a nonzero status on failure. Reports distinguish errors, warnings,
not-evaluable conditions, and observed zeros. Validation must never modify the
input package.

## Evidence status

Acceptance criteria are defined before confirmatory evaluation and are tied to a
declared acquisition and biological scope. Structural checks, software
conformance, or agreement between two implementations do not establish
scientific validation, backend equivalence, ground truth, or model universality.

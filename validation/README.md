# Validation

Current tissue/spatial execution evidence is in [PROGRESS](../PROGRESS.md), [the execution report](../docs/EXECUTION_REPORT.md), and `evidence/priorities-1-5-20261009.json`. The fluorescence records below remain scoped subsystem evidence. Scientific acceptance remains separate from engineering success.

The initial execution record is in `PILOT_STATUS.md`. The current full-frame,
deterministic DAPI evidence, geometry-warning statistics, verified engineering
boundary policy, local paths, and remaining human gates are in
`PHASE1_QC_STATUS.md`. Both
records preserve explicit non-validation boundaries.

The passing synthetic Phase 3 reference/split checkpoint, exact image
assignments, validator outputs, and remaining real-data gates are recorded in
[`docs/PHASE3_WIP_STATUS.md`](../docs/PHASE3_WIP_STATUS.md). That checkpoint is
engineering contract evidence only.

The Phase 4 engineering evaluator, algorithms, connected-folder audit, decision
gates, and exact remaining path to a scored native baseline are recorded in
[`docs/PHASE4_STATUS.md`](../docs/PHASE4_STATUS.md). No real reviewed reference
artifact was found in the connected microscopy folder, so Phase 4 scientific
performance remains not evaluated.

The Phase 5 StarDist adapter checkpoint, hash-bound runtime/model inputs,
preserved failed run identities, QC geometry integration finding, and exact
resume sequence are recorded in
[`docs/PHASE5_STATUS.md`](../docs/PHASE5_STATUS.md). StarDist run 11 exported a structurally valid canonical package and deterministic QC. Its 1,322 accepted topology warnings, independent review, scored backend comparison and scientific validation remain open.

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

Phase 2 adds a read-only governed-observation validator. It verifies supplied
biological/acquisition identity, artifact bytes, cross-manifest linkage, and
annotation lineage with a reviewed selected revision. It never creates IDs
from filenames and does not assign Phase 3 splits.

Phase 3 adds two read-only validators:

- `validate-reference-set` (alias `validate-nuclear-reference-set`) recursively
  validates the governed observation revision, DAPI target and evaluation
  policy, selection-protocol bytes, source-family coverage, declared region
  scope/count reconciliation, canonical nuclear-object and ignore-region
  NDJSON, deterministic IDs, prediction exposure, review/adjudication,
  canonical geometry/topology, image/ROI containment, edge-reason consistency,
  duplicate geometry, readiness, chronology, frozen state, provenance, and
  non-claims.

- `validate-split` (alias `validate-split-manifest`) recursively revalidates the
  reference set, requires exact image-level assignment coverage, checks every
  biological/acquisition/source-family identity echo, rejects a declared
  mouse/slide/source-family connected component spanning partitions, applies
  declared batch/scanner controls, and verifies the exact held-out ID and
  reference-content locks, parent/successor policy, chronology, provenance, and
  non-claims.

Phase 4 adds `evaluate-segmentation`. It recursively validates the frozen
Phase 3 split/reference boundary, verifies reference-raster pixels against the
canonical WKT objects, and reports deterministic matching, split/merge,
boundary, size/crowding, count, and signed measurement-bias evidence.

```powershell
ifquant-platform evaluate-segmentation `
  validation/fixtures/minimal-phase4-evaluation/evaluation-plan.json `
  --predictions validation/fixtures/minimal-phase4-evaluation/prediction-instances.jsonl
```

That fixture is synthetic software evidence and cannot close the real-data
Phase 4 gate.

The geometry implementation is deliberately limited to a fail-closed 2D
polygon subset. It canonicalizes ring orientation/start and member ordering;
rejects self-intersection, zero area/length, repeated or redundant collinear
vertices, invalid hole/member topology, noncanonical one-member
`MULTIPOLYGON`, and duplicate geometry; and requires coverage by the closed
image domain `[0, width] x [0, height]` and the governed inclusion ROI. A
`physical_image_edge` ignore must meet the image boundary. In the absence of a
separate specimen-boundary artifact, `physical_specimen_edge` is tested against
the governed ROI boundary. Exact nuclear duplicates and exact ignore duplicates
are rejected image-wide, regardless of annotation. A nuclear reference may not
overlap or even touch any same-image ignore geometry, keeping held-out positives
inside the scoreable domain.

The validator can reconcile a declared complete region ledger, but it cannot
decide whether a reviewer omitted an in-scope region. Hard mouse/slide/
source-family components are formed across every governed image; excluded or
otherwise unassigned images can therefore bridge two assigned partitions.
Connected-group checking exposes overlap in declared identities but cannot
discover an unrecorded biological or acquisition relationship.

## Phase 3 synthetic verification

After installing the package in editable mode, run:

```powershell
ifquant-platform validate-reference-set `
  validation/fixtures/minimal-phase3-reference-split `
  --expect-reference-set-sha256 `
  f0137f493ef2cecede86f933729d12ac169a528608bfc69b96d82e457f0fb935
ifquant-platform validate-split `
  validation/fixtures/minimal-phase3-reference-split `
  --expect-split-manifest-sha256 `
  43c32b9c947257b79bd00ae59b09adf64883e0b7554606aaa700b2e6a0d3b47d `
  --expect-reference-set-sha256 `
  f0137f493ef2cecede86f933729d12ac169a528608bfc69b96d82e457f0fb935 `
  --expect-held-out-test-image-ids-sha256 `
  44f3c019439012f5f0136129747a02e98a83354a84e42120f565cd9cdaa70f67 `
  --expect-held-out-test-reference-content-sha256 `
  a16120a41f7bf114a4c1608cca05757c09a119f50d290abd5e09861645a25900
```

The fixture has four governed synthetic images, four canonical nuclear
reference objects, one explicit ignore region, and three source families. Its
exact image assignments are:

- `train`: `phase3-image-001`, `phase3-image-002`;
- `tuning`: `phase3-image-003`;
- `held_out_test`: locked `phase3-image-004`.

The one model-assisted, single-review object is deliberately confined to
`train` in this fixture. The validator prohibits such an image from
`held_out_test` but does not impose a universal train-only rule; study policy
must decide whether it is eligible for tuning. The reference report therefore
reports `model_assisted_nonconfirmatory_review_count: 1` and remains
`confirmatory_reference_ready: false` even though both reports return
`status: valid`. An adjudicator decision is confirmatory only when its
adjudicator is distinct from all reviewers. A reference set must contain at
least one nuclear object, and every held-out image must have a positive nuclear
reference and confirmatory readiness.

The current expected reference-set SHA-256 is
`f0137f493ef2cecede86f933729d12ac169a528608bfc69b96d82e457f0fb935`;
the split-manifest SHA-256 is
`43c32b9c947257b79bd00ae59b09adf64883e0b7554606aaa700b2e6a0d3b47d`;
the canonical locked held-out image-list SHA-256 is
`44f3c019439012f5f0136129747a02e98a83354a84e42120f565cd9cdaa70f67`;
and the `ifquant_held_out_reference_content_v1` SHA-256 is
`a16120a41f7bf114a4c1608cca05757c09a119f50d290abd5e09861645a25900`.

The content descriptor binds the task, evaluation policy, selection protocol,
and, for the held-out image, its complete governed observation record
(including biological identity and source/channel/annotation hashes), source
family, all region-ledger entries, nuclear-reference objects, and ignore
regions. Successor validation rejects held-out truth, policy, source,
annotation, biological-identity, or source-family drift while allowing valid
train/tuning-only evolution under the declared policy.

Chronology traverses every governed-observation-set revision in its validated
parent chain. A direct parent observation set's `provenance.created_at` must be
no later than its child's. For the current revision and every ancestor, the
observation-set, image, channel-map, and annotation-lineage provenance;
acquisition time when present; and every annotation and identity review must be
no later than the reference freeze. Reference provenance and every
region/object/ignore review are bound to that freeze as well. Parent
reference/split freezes must precede successor creation, and the current
reference freeze must precede split creation. Only the initial split requires
its reference freeze to precede the original held-out commitment. A later
reference successor may freeze after that preserved commitment when held-out
content is unchanged, enabling honest train/tuning-only evolution. The
commitment and split creation remain no later than the split freeze.

Every governed-observation revision's provenance code artifact, the Phase 3
evaluation-policy and selection-protocol artifacts, and the reference/split
provenance code artifacts must be nonempty and byte-attested by exact size and
SHA-256; each provenance code identity must match its verified code artifact.

The current repository run discovers 108 tests: 107 pass, and one optional
JSON-Schema instance test is explicitly skipped because `jsonschema` is not
installed. The focused Phase 3 run discovers 37 tests: 36 pass with the same
one optional skip. The standard-library validation path is exercised and
passes in both runs.

This fixture is not real reference data or a real held-out cohort. It does not
prove label correctness, hidden-leakage absence, statistical adequacy, split
optimality, population representativeness, domain generalizability, scientific
validation, backend equivalence, model universality, H1/H2 closure, or
authorization.

Schema conformance alone does not enforce every cross-record runtime invariant.
Prediction-exposure hashes are asserted identities rather than locally
byte-attested artifacts in v1, and approval of real source-family membership is
a human study gate. The synthetic fixture is not scientific validation,
backend equivalence, model-universality evidence, or proof that hidden leakage
is absent.

## Evidence status

Acceptance criteria are defined before confirmatory evaluation and are tied to a
declared acquisition and biological scope. Structural checks, software
conformance, or agreement between two implementations do not establish
scientific validation, backend equivalence, ground truth, or model universality.

Before Phase 4 evaluation, real governed observations and exhaustive reviewed
reference scope must be frozen, real source-family/domain controls approved,
exact held-out IDs committed, and metrics/acceptance thresholds predeclared.
The accepted run05 full-image symmetric boundary result remains an engineering
pilot decision; the 194 `nucleus_not_covered_by_cell_geometry` warnings remain
conservatively ineligible until H2 is resolved.

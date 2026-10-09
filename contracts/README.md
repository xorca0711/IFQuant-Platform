# IFQuant Platform contracts

These Draft 2020-12 JSON Schemas define the first canonical interchange
boundary for image metadata, semantic channels, supplied annotations,
segmentation runs, cell objects, cell-object packages, governed observations,
DAPI nuclear references, and image-level split manifests.

They are clean-slate engineering contracts. Schema validity does not establish
scientific validation, biological validity, backend equivalence, historical
reproducibility, model universality, or authority to use an endpoint.

## Contract family

| Schema | Role |
| --- | --- |
| `schemas/measurement-definition.schema.json` | Defines backend-neutral cell morphology and compartment-intensity meaning. |
| `schemas/parameter-set.schema.json` | Binds every declared parameter slot to one explicit applicability scope. |
| `image-manifest.schema.json` | Identifies source image bytes, biological unit, dimensions, calibration, coordinate space, acquisition grouping, and ingest provenance. |
| `channel-map.schema.json` | Maps image-local channel indices to stable semantic channel and marker identities. |
| `annotation-set.schema.json` | Carries the supplied annotation regions used to constrain cell detection. |
| `segmentation-run.schema.json` | Records one configured segmentation execution and the exact backend, model descriptor, optional weights, configuration, preprocessing, and versioned boundary semantics. Contract 1.1 adds an explicit detector-resolution image-boundary guard while 1.0 remains readable for legacy exact-envelope audits. |
| `governed-observation-set.schema.json` | Phase 2 aggregate for explicit biological/acquisition identity, immutable image and channel references, annotation lineage with a reviewed selected revision, identity review, byte-bound producer code, and non-claims. It deliberately contains no Phase 3 partition assignment. |
| `nuclear-reference-object.schema.json` | One canonical reviewed DAPI nuclear-instance geometry with governed image/ROI identity, creation mode, prediction exposure when model-assisted, and explicit review/adjudication evidence. |
| `reference-ignore-region.schema.json` | One canonical reviewed region excluded from reference scoring for a controlled truncation, ambiguity, artifact, or unscorable reason; it does not inherit a detector edge rule. |
| `nuclear-reference-set.schema.json` | Phase 3 aggregate binding a governed observation revision, DAPI task/evaluation policy, selection protocol, source-family coverage, declared exhaustive region ledger, canonical nuclear/ignore artifacts, frozen state, provenance, and non-claims. |
| `split-manifest.schema.json` | Frozen image-level train/tuning/held-out assignments with hard mouse/slide/source-family separation, declared batch/scanner controls, exact held-out image-ID and reference-content commitments, lineage, and non-claims. |
| `cell-object.schema.json` | Defines one deterministic cell-object record for JSON Lines export. |
| `cell-object-package.schema.json` | Binds all manifests and exactly one deterministic JSON Lines cell-object artifact. |
| `canonicalization-vectors.json` | Cross-runtime golden bytes and hashes for Unicode, control escaping, and binary64 number formatting. |

Every schema uses `additionalProperties: false`. Contract revisions add fields
through a new schema and contract version rather than silently accepting
unknown data.

The separate `tissue/v1/` and `spatial/v1/` families extend these boundaries without
changing fluorescence v1. Tissue schemas cover calibrated intake, regions, H&E
models, review and packages. Spatial schemas cover processed RNA, provided affine
transforms, region links and processed molecular context. Their Python validators
enforce semantic checks beyond JSON shape. See
[`docs/STAGES_5_6_PIPELINE.md`](../docs/STAGES_5_6_PIPELINE.md) for the current limited
adapter scope and planned native AnnData/SpatialData interoperability.

## Identity and canonical bytes

All SHA-256 values are lowercase hexadecimal over the exact bytes named by the
field. Manifest hashes used by package references are computed over canonical
JSON: UTF-8 without a BOM; object keys sorted lexicographically; no
insignificant whitespace; arrays retained in declared order; non-ASCII Unicode
written directly; and JSON control characters escaped. Binary64 numbers use
their shortest round-trippable value in exponent-free plain-decimal form, with
trailing fractional zeroes removed and integral values written as integers.
Thus `1e-5`, `0.000010`, and an in-memory binary64 `1e-5` canonicalize as
`0.00001`.

Parsing must reject duplicate object keys, non-JSON constants, non-finite
numbers, negative zero, and integers outside the interoperable range
`[-9007199254740991, 9007199254740991]`. Timestamps are RFC 3339 UTC values
ending in `Z`. Strings containing unpaired Unicode surrogates are rejected.

`cell-object.object_id` is deterministic. It is the lowercase SHA-256 of the
canonical JSON bytes for this exact descriptor:

```json
{
  "annotation_id": "<annotation_id>",
  "cell_wkt": "<normalized cell WKT>",
  "image_id": "<image_id>",
  "nucleus_wkt": "<normalized nucleus WKT>",
  "segmentation_run_id": "<segmentation_run_id>"
}
```

The exporter sorts detections by `annotation_id`, cell-centroid y,
cell-centroid x, then the UTF-8 cell WKT. It assigns zero-based contiguous
`object_index` values only after that sort. A validator must recompute every
object identity; a schema pattern alone is insufficient.

## Cross-document invariants

- Every referenced ID has exactly one matching document or record. The image,
  biological-unit, channel-map, annotation-set, coordinate-space, and
  segmentation-run IDs agree across all bound contracts.
- Governed-observation biological identifiers are study-scoped. A specimen ID
  cannot move between mice, a section ID cannot change its mouse/specimen/slide
  parents, and a slide ID cannot span mice within one observation set.
- Package reference hashes equal recomputed canonical manifest hashes.
- Package measurement-definition, parameter-set, and method-instance hashes
  equal independently recomputed identities; contract validity carries no
  scientific authorization.
- Pixel width and height are finite and positive. Geometry uses the declared
  coordinate space, `x y` axis order, and pixel units; morphology uses physical
  units derived from the bound calibration.
- Package segmentation bindings exactly repeat the referenced run values:
  `backend_sha256` is `backend.artifact_sha256`, `model_sha256` is
  `model.descriptor_sha256`, `weights_sha256` is `model.weights_sha256`,
  `detector_config_sha256` is `detector.config_sha256`, and
  `preprocessing_sha256` is `preprocessing.profile_sha256`.
- `source_channel_index` values and semantic `channel_id` values are each
  unique within a channel map. The mappings are sorted by source index.
- An intensity transform of `none` has scale `1`, offset `0`, and unit
  `native_sample_value`. A `linear` transform applies `output = input * scale +
  offset`; scale must be nonzero.
- Annotation IDs are unique within a set. Cell-object `annotation_id` values
  resolve to an `include` annotation in that set, and exported cells originate
  within the supplied region under the segmentation run's declared boundary
  policy. Annotation geometry type agrees with its WKT prefix.
- Morphology and intensity `measurement_id` values are unique per object.
  Compartments and units must match the feature/statistic semantics. Numeric
  values are finite. Canonical v1 rejects a package with an unavailable
  required feature rather than emitting a partial object or encoding NaN,
  Infinity, or a magic sentinel.
- Morphology area uses `um2`; perimeter and axis lengths use `um`; circularity,
  solidity, eccentricity, and area ratios use `ratio`. Intensity `sum` uses
  `integrated_native_sample_value`; other statistics use the unit declared by
  their channel mapping.
- If a prediction has `abstained: true`, `abstention_reason` is non-empty and
  `label` and `score` are null. Otherwise, `label` and `score` are present and
  `abstention_reason` is null. Probabilities lie in `[0, 1]`.
- Object review state `unreviewed` has null reviewer and review time. Other
  review states identify a reviewer and time. Corrections increment `revision`
  and point to the superseded object; source detections are never overwritten.
- Annotation review uses the same reviewer/time nullability rule.
- Package artifact `record_count` equals the number of non-empty JSONL lines;
  each line validates independently against `cell-object.schema.json`.
  `object_index` is contiguous and records are ordered by ascending index.
  `size_bytes` and SHA-256 are verified against the exact JSONL bytes.
- Package QC counts sum to `object_count`; both equal artifact `record_count`.
  Reviewed-object count cannot exceed the artifact record count.
- Package, run, and object QC are evidence fields, not scientific authorization.
  Review state is independent of QC and prediction state.
- `mouse_id`, `slide_id`, `batch_id`, and `scanner_id` remain available for
  grouped dataset splitting. Tile-random validation is outside this contract
  and must not be inferred from package validity.
- Every nuclear-reference object resolves to one governed image, biological
  unit, coordinate space, and include annotation, and its target is exactly a
  DAPI nuclear instance. Its ID is the canonical SHA-256 of the reference set,
  image, annotation, target, and canonical geometry descriptor.
- A `human_corrected_prediction` reference binds the prediction package,
  package hash, segmentation run, predicted object, and predicted geometry.
  Human-drawn records carry no prediction exposure. Review and adjudication
  evidence is explicit rather than inferred from creation mode.
- Every reference-ignore ID binds the reference set, image, annotation,
  canonical geometry, and controlled reason. Reference evaluation declares
  explicit ignore handling and must not silently inherit a candidate detector's
  edge guard.
- Nuclear and ignore geometry is accepted only in the narrow canonical 2D
  polygon subset described below. Each geometry must lie within both its image
  and its governed inclusion ROI. Exact duplicate nuclear geometry and exact
  duplicate ignore geometry are rejected image-wide rather than only within an
  annotation scope, even if an alternative WKT representation would otherwise
  encode the same canonical shape.
- A nuclear-reference geometry may neither overlap nor touch any same-image
  ignore geometry. This inclusive separation keeps every positive nucleus
  scoreable after ignore regions are removed, including in held-out evaluation.
- An ignore reason of `physical_image_edge` requires the geometry to intersect
  the physical image boundary. `physical_specimen_edge` requires intersection
  with the governed inclusion-ROI boundary; v1 uses that boundary because it
  has no separate specimen-boundary artifact.
- Source-family coverage assigns every governed image exactly once. The
  reference region ledger declares exhaustive scope for the governed
  observation set and reconciles per-region and aggregate
  nuclear-object/ignore counts against the bound canonical NDJSON artifacts.
  Validator reconciliation makes the declared scope inspectable; human review
  must still establish that the declaration is complete and scientifically
  appropriate.
- A reference revision must contain at least one nuclear-reference object.
  Every image assigned to `held_out_test` must itself have at least one positive
  nuclear reference and confirmatory review readiness.
- An `adjudicator_decision` must identify an adjudicator distinct from every
  listed reviewer. Model-assisted records without independent second review,
  consensus, or a distinct-adjudicator decision are counted in
  `model_assisted_nonconfirmatory_review_count` and are not held-out ready.
- Split assignments cover every included reference image exactly once at image
  level. Any images connected by a shared `mouse_id`, `slide_id`, or
  `source_family_id` remain in one partition. Connected components are built
  across every governed image, including excluded or otherwise unassigned
  images that can transitively bridge assigned partitions. This
  declared-component check does not discover missing or incorrect relatedness
  metadata.
- Batch and scanner controls are declared separately as either
  `partition_disjoint` or `leave_values_out`; they are not universally treated
  as interchangeable hard-group rules.
- The held-out image commitment lists the exact ascending held-out image IDs
  and binds their canonical SHA-256. A second commitment using
  `ifquant_held_out_reference_content_v1` binds the full task, evaluation
  policy, selection protocol, and, for every held-out image, its governed
  observation record (including biological identities and source/channel/
  annotation hashes), source family, all region-ledger entries, nuclear
  records, and ignore records.
- Successors preserve all earlier assignments and both held-out commitments.
  Validation therefore rejects held-out truth, source, annotation, biological
  identity, source-family, or policy drift. Valid train/tuning-only evolution
  is permitted when it complies with the declared successor and split policy;
  newly admitted images may enter only `train` or `tuning`.
- A model-assisted single-review image is not eligible for
  `held_out_test`. Its presence also causes the reference validator to report
  that the reference set is not confirmatory-ready, even when structural
  validation otherwise passes.
- Chronology is fail-closed and traverses every governed-observation-set
  revision in the validated parent chain. Each direct parent observation set's
  `provenance.created_at` must not follow its child's. For the current revision
  and every ancestor, observation-set, image, channel-map, and annotation-lineage
  provenance; image acquisition time when present; and every annotation and
  identity review must not follow the reference freeze. Reference provenance
  and every region/object/ignore review are bound to that freeze as well. A
  parent reference or split freeze must not follow its successor's creation,
  and the current reference freeze must not follow split creation.
- For an initial split only, the reference must also be frozen before the
  original held-out commitment. A later reference successor may legitimately
  freeze after that preserved original commitment when its held-out content is
  unchanged; this exception enables honest train/tuning-only evolution without
  weakening the held-out content lock. The commitment and split creation still
  cannot follow the split freeze.
- Every governed-observation revision's provenance code artifact, the Phase 3
  evaluation-policy and selection-protocol artifacts, and the reference/split
  provenance code artifacts must be nonempty local artifacts whose exact byte
  size and SHA-256 are verified. Each provenance `code_sha256` must equal its
  verified code-artifact identity.

### Canonical Phase 3 geometry subset

Phase 3 v1 deliberately implements a narrow, fail-closed 2D `POLYGON`/
`MULTIPOLYGON` subset rather than a general computational-geometry engine.
Rings are closed, simple, nonzero-area, and canonicalized to a fixed
orientation and start vertex; holes and true multipolygon members use stable
ordering. Repeated non-closing vertices, zero-length segments, self
intersections, redundant collinear vertices, invalid hole/member topology, and
a one-member `MULTIPOLYGON` are rejected. This canonical form is what identity
hashes bind.

The image domain is the closed rectangle `[0, width] x [0, height]` in the
declared pixel coordinate space. Reference and ignore geometry must be covered
by both that domain and the resolved governed inclusion ROI. These algorithms
make the supported cases deterministic; they do not assert biological label
correctness or numerical equivalence among segmentation backends.

Relative artifact paths use `/`, never an absolute path or a `..` segment.
Every referenced manifest and method contract is named by such a relative path,
so a package can be validated without guessing filenames or consulting a
workstation path.
WKT is OGC polygon or multipolygon text in the bound image coordinate space;
the canonical WKT bytes are provenance-bearing. Exporters must use the accepted
stable decimal formatting and ring ordering. These schemas do not claim that
geometries from different segmentation backends are numerically equivalent.

Canonical v1 is deliberately 2D and accepts only singleton Z/T source images.
The validator re-hashes the local source named by `source_uri` (a
package-relative path, an absolute local path, or a local `file:` URI) and
checks its declared byte size. Measurement semantic inputs must match channel
marker identity, intensity coordinate, representation, transform, and feature
unit before a package is accepted.

## Segmentation boundary

The candidate `backend.kind` values are `native_qupath`, `stardist`, and
`instanseg`. They share a cell-object output interface only. A shared schema,
matching configuration names, or successful validation does not imply equal
objects, measurements, performance, or fitness for a biological endpoint.
Training, calibration, statistical validation, and aggregation stay outside
Groovy execution.

Native QuPath runs still carry a content-addressed model descriptor; their
`weights_sha256` is null when no external learned weights are used. StarDist
and InstanSeg runs must bind their exact weight bytes.

## Standard-library validation

A Python standard-library validator can load JSON with `object_pairs_hook` to
reject duplicate keys, check the exact key sets and scalar types expressed in
these schemas, recompute hashes with `hashlib`, and enforce the cross-document
rules above. JSON Schema validation may be added as a convenience, but package
acceptance must also perform those referential and byte-level checks.

JSON Schema alone does not provide all Phase 3 cross-record, topology,
containment, chronology, canonical-byte, review-readiness, or successor
invariants; the read-only runtime validator is authoritative for those checks.
Conversely, a valid runtime report does not turn declared metadata into an
independent scientific attestation. In v1, prediction package/run/object/
geometry hashes in prediction-exposure records are asserted identities, not
local byte-attestation. Approval that real `source_family_id` assignments are
complete and scientifically appropriate remains a human study gate.

Phase 3 exposes the same read-only principle through
`ifquant-platform validate-reference-set` and
`ifquant-platform validate-split`. The reference command recursively validates
the governed observation set, canonical nuclear/ignore artifacts, region and
source-family completeness, review lineage, provenance, and non-claims. The
split command recursively revalidates the reference set, exact assignments,
declared grouping/domain rules, frozen state, parent/successor invariants, and
the held-out lock. A `valid` report describes engineering integrity only; it is
not scientific validation, biological ground truth, split optimality,
population representativeness, leakage proof, backend equivalence, model
universality, or authorization.

Phase 4 adds `segmentation-evaluation-plan.schema.json` and
`segmentation-evaluation-instance.schema.json`. A frozen plan binds one exact
native-QuPath method scope to the Phase 3 split/reference hashes, selected
partitions, reference-raster bytes, matching/boundary/split-merge/size
thresholds, and prospectively supplied acceptance criteria. The runtime does
not trust the raster ledger alone: it independently rasterizes each selected
canonical Phase 3 WKT object by pixel-center inclusion and requires exact
identity and pixel equality. Prediction ledgers use the same ordered pixel-set
shape. A valid evaluation report is a reproducible calculation, not scientific
approval.

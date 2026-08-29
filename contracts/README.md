# IFQuant Platform contracts

These Draft 2020-12 JSON Schemas define the first canonical interchange
boundary for image metadata, semantic channels, supplied annotations,
segmentation runs, cell objects, and cell-object packages.

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
| `segmentation-run.schema.json` | Records one configured segmentation execution and the exact backend, model descriptor, optional weights, configuration, and preprocessing identities. |
| `cell-object.schema.json` | Defines one deterministic cell-object record for JSON Lines export. |
| `cell-object-package.schema.json` | Binds all manifests and exactly one deterministic JSON Lines cell-object artifact. |
| `canonicalization-vectors.json` | Cross-runtime golden bytes and hashes for Unicode, control escaping, and binary64 number formatting. |

Every schema uses `additionalProperties: false`. Contract revisions add fields
through a new schema and contract version rather than silently accepting
unknown data.

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

Relative artifact paths use `/`, never an absolute path or a `..` segment.
Every referenced manifest and method contract is named by such a relative path,
so a package can be validated without guessing filenames or consulting a
workstation path.
WKT is OGC polygon or multipolygon text in the bound image coordinate space;
the exact WKT bytes are provenance-bearing. Exporters should use stable decimal
formatting and ring ordering, but these schemas do not claim that geometries
from different segmentation backends are numerically equivalent.

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

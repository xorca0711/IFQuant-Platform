# QuPath canonical cell-package pilot

Status: **unvalidated engineering pilot**.

This proof of concept is the narrow QuPath execution boundary for IFQuant
Platform. It opens one saved project image, selects an exact set of existing
persisted annotations, runs native QuPath Watershed Cell Detection, derives
calibrated 2D morphology, maps exact QuPath compartment-intensity measurements,
and emits the canonical v1 cell-object package. Python owns contract governance,
package validation, datasets, training, statistics, aggregation, and scientific
assessment. Groovy contains no model-training path.

Nothing here establishes scientific validity, biological accuracy, backend
equivalence, endpoint validity, or a universal model.

## Supported execution boundary

- QuPath >= 0.6.0 and < 0.8.0; the examples target the documented 0.7 CLI.
- Exactly one script argument: the configuration path in `args[0]`.
- Project-only execution using `--project` plus `--image`. The project image
  must already contain saved `FLUORESCENCE` image data and the persisted
  annotations selected by this run. Standalone `--image` execution is rejected.
- QuPath image type `FLUORESCENCE`; brightfield, unset, and other image types
  are rejected before plugin execution.
- A singleton 2D source only: `nZSlices() == 1` and
  `nTimepoints() == 1`.
- One local source file URI. The exporter verifies its normalized URI, exact
  byte size, and SHA-256 against the current QuPath image server.
- Native sample values only. Configured bit depth and unsigned/floating-point
  representation must equal QuPath's image-wide pixel type. Linear or
  normalized intensity export is rejected because QuPath's aggregated
  measurement values are not silently transformed.
- `native_qupath` only, using
  `QP.runPlugin(String, ImageData, Map)` with the configured
  `WatershedCellDetection` parameters.
- `exclude_touching_annotation_boundary` only. Cells wholly covered by one
  selected annotation and not touching its boundary are exported. Cells that
  cross or touch the boundary are counted and excluded. New cells with no
  selected-annotation intersection or an ambiguous multi-annotation
  intersection are also excluded with distinct QC ledger codes; no annotation
  identity is fabricated.
- Existing detections that intersect, or are children of, a selected
  annotation cause a fail-closed stop before the plugin runs.
- `stardist` and `instanseg` are interface candidates only and terminate
  with `CANDIDATE_BACKEND_NOT_IMPLEMENTED`.
- `clip_to_annotation` and `include_touching_annotation_boundary` are
  schema-level candidates only and terminate with
  `CANDIDATE_BOUNDARY_POLICY_NOT_IMPLEMENTED`. The pilot does not fabricate
  clipped geometry or morphology.

Official QuPath references:

- https://qupath.github.io/javadoc/docs/qupath/lib/scripting/QP.html
- https://qupath.github.io/javadoc/docs/qupath/lib/scripting/ScriptAttributes.html
- https://qupath.readthedocs.io/en/stable/docs/advanced/command_line.html

## Prepare a run-specific configuration

Copy `qupath/config/pilot.example.json` and replace every angle-bracket
placeholder. The example is deliberately non-runnable until all required
identities, hashes, and exact QuPath measurement names are known.
Also replace the example source size and calibration values.

Important bindings:

1. `image.source_artifact.source_uri` must be an absolute `file:` URI for
   exactly the file returned by the image server. Record its byte size and
   SHA-256. Compound or multi-URI sources are rejected by this pilot.
2. `image.expected_server_name`, configured channel indices/names, bit depth,
   intensity representation, and pixel calibration must match QuPath metadata.
   This pilot assumes a fluorescence image with the DAPI source channel and
   positive cell expansion required by the bound cell/cytoplasm/nucleus method.
3. Every selected annotation must have exactly
   `annotation_set.classification`. The exporter normalizes and sorts those
   ROIs before detection.
4. `annotation_set.expected_content_sha256` binds the exact selected ROI set.
   The checked-in all-`1` value is a deliberate preflight mismatch. After all
   other placeholders are resolved, run once; the fail-closed mismatch reports
   the observed hash. Independently verify the descriptor below, record that
   hash, and rerun.
5. `execution.script_path` must resolve to the script actually reported by
   QuPath through `ScriptAttributes.FILE_PATH`. Normalized paths must be
   equal, the filename and embedded contract/version sentinel must match, and
   the bytes must match `execution.expected_script_sha256`.
6. `segmentation.backend.version` must equal the running QuPath version. The
   backend artifact, algorithm descriptor, preprocessing profile, runtime
   environment, code revision, and run/package identities must all be real,
   immutable values for the run.
   Plugin start/completion timestamps are captured around `QP.runPlugin` by
   the exporter; they are not accepted as predeclared config assertions.
7. The three intensity `source_measurement` values are exact, case-sensitive
   QuPath measurement-list keys. There is no guessing or fuzzy matching.
8. `output_directory` may be absent or empty. Any existing entry is refused;
   files are never overwritten.

The annotation-content hash is canonical SHA-256 over this object, with
`annotations` sorted by `annotation_id`:

```json
{
  "contract": "ifquant-platform-annotation-content/v1",
  "annotation_set_id": "...",
  "image_id": "...",
  "coordinate_space_id": "...",
  "revision": 0,
  "annotations": [
    {
      "annotation_id": "...",
      "label": "...",
      "inclusion_policy": "include",
      "geometry": {
        "encoding": "WKT1",
        "geometry_type": "POLYGON",
        "wkt": "..."
      }
    }
  ]
}
```

Each annotation ID is `ann_` plus canonical SHA-256 of:

```json
{
  "annotation_set_id": "...",
  "image_id": "...",
  "label": "...",
  "wkt": "..."
}
```

The configured measurement method is copied into the output package and pinned
to:

- definition:
  `b4699d43736ad279718126bdb0b87733c1c370d903a28d01335515af852c99e6`
- parameter set:
  `0ab144834e8e57b3ce21787bcfc99f2fe6bf661d695184814a07375876c83027`
- method instance:
  `6c47eda4968b78ec47df0253205dfb9bae40ad5677964def25a0ed1ac0938d3d`

This POC requires method missingness `unavailable = reject_package` and
`nonfinite = reject`. It supports definitions with no parameter slots; the
Python contract layer governs constrained parameter slots.

The current script-byte binding is:

```text
4ba40609b938fd4425acef2ec18ab96328725521c4dd6b5ee13ab081bc73f246
```

## Reproducible QuPath 0.7 CLI

Project image (required), Windows PowerShell:

```powershell
& "C:\Program Files\QuPath-0.7.0\QuPath-0.7.0 (console).exe" script --project "C:\absolute\pilot.qpproj" --image "Exact project image name" --args "C:\absolute\pilot.run.json" "C:\absolute\DetectCellsAndExport.groovy"
```

Pass `--args` exactly once and invoke the same script path recorded in config.
The selected project entry must have its `FLUORESCENCE` image type and source
annotations saved before this headless run. A standalone image does not carry
that persisted project state and is intentionally unsupported.
`--save` is intentionally omitted: this pilot does not persist detections or
selection changes to the QuPath image data.

## Canonical v1 output

A successful run publishes this exact package shape:

```text
output_directory/
  package.json
  cell_objects.jsonl
  manifests/
    image-manifest.json
    channel-map.json
    annotation-set.json
    segmentation-run.json
  contracts/
    cell-morphology-intensity-v1.json
    cell-morphology-intensity-engineering-v1.json
```

`package.json` contains package-relative paths and canonical manifest/method
hashes. `cell_objects.jsonl` is UTF-8 canonical JSON Lines; its exact bytes,
size, record count, and SHA-256 are bound in the package. Publication uses
same-directory temporary files and atomic moves, with rollback of published
files if a later publication step fails.

Cell-object IDs use the documented geometry descriptor exactly:

```json
{
  "annotation_id": "...",
  "cell_wkt": "...",
  "image_id": "...",
  "nucleus_wkt": "...",
  "segmentation_run_id": "..."
}
```

Cell and nucleus geometries are reduced to six decimal places, normalized with
JTS, and represented in image-pixel coordinates. Morphology is derived from
that normalized geometry after anisotropic scaling by the verified x/y pixel
calibration. Records sort by `annotation_id`, cell centroid y, cell centroid
x, and cell WKT; the exporter then assigns contiguous `object_index` values
and writes in ascending index order.

`provenance.source_detection_id` records QuPath's actual detection UUID,
separate from the deterministic geometry-derived `object_id`. Because this
pilot omits `--save`, that UUID traces only the in-memory execution; it is not
a durable project-object reference until a future persisted correction
workflow establishes one.

Zero cells is a valid engineering result. The exporter writes an empty
`cell_objects.jsonl`, `record_count: 0`, and explicit
`zero_cells_exported` warning flags while QC remains `not_evaluated`.
Every exclusion category is also recorded as a separate count-bearing warning
in both the segmentation and package QC flags.

Validate a completed output from the repository environment:

```powershell
python -m ifquant_platform.cli validate-package "C:\absolute\output_directory"
```

Structural validation is necessary but is not scientific validation.

## Deliberate limitations

- QuPath is not installed on the scaffold host, so this Groovy file has not
  been compiled or executed against a microscopy image here.
- Canonical serialization, geometry-derived object identity, and row ordering
  are deterministic. Actual plugin timestamps and QuPath detection UUIDs are
  deliberately run-specific, so complete package bytes are not claimed to be
  identical across reruns.
- `ScriptAttributes.FILE_PATH` binds the CLI-reported file path and bytes.
  Interactive unsaved editor text is outside this pilot; use the documented
  file-based CLI invocation.
- Only a one-file, singleton-z, singleton-time 2D image is accepted. Olympus
  VSI and other compound/multi-file images require a future artifact manifest.
- Boundary clipping is not implemented. Expanded cells that touch or cross an
  annotation boundary are excluded, not modified.
- Annotation review, cell review, and QC remain unreviewed/not evaluated.
  Engineering warning flags are not biological QC.
- Exact QuPath measurement names and Watershed behavior can change with image
  type, channel metadata, plugin parameters, and QuPath version; all are pinned
  inputs, not equivalence claims.
- Atomicity is per file, not a transactional directory commit. Empty
  directories may remain after rollback.
- Detection may exist in memory if a later export check fails, but the CLI
  command omits `--save`.
- StarDist and InstanSeg adapters, model training, object-classifier training,
  group-aware splitting, endpoint-bias analysis, calibration, abstention, and
  domain-shift evaluation remain Python-governed future work.

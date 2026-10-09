# Native spatial interchange and the lung example

The optional adapters add real file interchange to the existing CSV assay and
affine-link foundation. They do not run deconvolution, normalize expression,
assign cell types, estimate injury or establish biological validity.

## Environment and commands

```powershell
uv sync --locked --extra dev --extra imaging --extra spatialdata
uv run --no-sync python -m ifquant_platform import-spatial-native native-import.json --output validation/output/native
uv run --no-sync python -m ifquant_platform export-anndata validation/output/native/assay.json --output validation/output/rna.h5ad
uv run --no-sync python -m ifquant_platform export-spatialdata validation/output/native/assay.json --output validation/output/scene.zarr
uv run --no-sync python -m ifquant_platform import-spatialdata validation/output/scene.zarr --output validation/output/restored
```

Use `[spatial]` when only AnnData/Visium is needed. `[spatialdata]` adds the larger
geospatial stack. Core commands retain lazy optional imports. CI exercises
Windows/Linux x64. On Windows ARM64, SpatialData's pyogrio/pyarrow binary stack
may require an isolated x64 Python environment; this session used that route.
No global Python or user environment is replaced.

## Native import configuration

All IDs and frames are explicit. Paths resolve relative to the configuration.
The common fields are:

```json
{
  "schema_version": "ifquant.native-spatial-import/1",
  "format": "anndata",
  "assay_id": "sample-rna",
  "subject": {"subject_id": "subject-1", "species": "Mus musculus", "specimen_id": "lung-1", "section_id": "section-1"},
  "entity_type": "spot",
  "coordinate_frame": {"frame_id": "sample-image-pixels", "unit": "pixel", "axes": ["x", "y"], "origin": "top_left", "y_direction": "down"},
  "inputs": {"h5ad": "sample.h5ad"},
  "options": {"counts_layer": "counts", "coordinates_key": "spatial", "feature_name_column": "feature_name", "status_column": null, "default_status": "measured", "feature_ids": null}
}
```

AnnData count selection is explicit: `X`, `raw.X`, or an exact `layers` key.
Only sparse CSR/CSC raw nonnegative integer counts are accepted; a dense or
normalized layer is rejected. `feature_ids` is either null (all features) or an
explicit ordered subset of exact feature IDs. Duplicate display symbols remain
distinct. Selected coordinates must be finite N × 2 XY in the declared frame.
obs and selected var metadata are retained in `annotations.h5ad`; unrelated
uns/obsm layers are outside this profile. The adapter reads sparse counts from
the HDF5 backing store without materializing the full expression matrix.

An export uses sparse raw `X`, `obsm['spatial']`, `obs['ifquant_assay_status']`
and `uns['ifquant_metadata_json']`. For reimport select these exact names; the
embedded subject/frame must agree with the configuration. Empty matrix rows
for unresolved observations are storage placeholders, not measured zeros.

For `visium_h5`, replace inputs/options with:

```json
{
  "inputs": {"matrix_h5": "filtered_feature_bc_matrix.h5", "positions": "tissue_positions_list.csv.gz", "scalefactors": "scalefactors_json.json"},
  "options": {"positions_profile": "legacy_headerless", "matrix_scope": "filtered", "target_image": "hires", "feature_ids": null}
}
```

Use `positions_profile: headered` for the six-column `tissue_positions.csv`.
Use `format: visium_mtx` with `matrix_mtx`, `barcodes`, `features`, `positions`
and `scalefactors` input paths for integer general Matrix Market and three-column
feature TSVs. Gzip text inputs are supported. Only Gene Expression features are
admitted; multimodal feature matrices need an explicit RNA subset.

`pxl_col_in_fullres` becomes X; `pxl_row_in_fullres` becomes Y. `fullres` applies
no scaling; `hires`/`lowres` apply the declared scale exactly once. No physical
pixel calibration is inferred. Matrix barcode order is retained, followed by
positions absent from that matrix. Those positions receive `not_reported` with
null library totals and an `absent_from_supplied_matrix` reason in obs metadata.
They are not reclassified as zero expression, unassayed tissue or failed biology.
`in_tissue`, array coordinates and matrix availability are preserved separately.

## SpatialData profile

An optional `--scene scene.json` adds an image and regions:

```json
{"frame_id": "image-pixels", "image": "image.png", "assay_to_image": [[1,0,0],[0,1,0],[0,0,1]], "regions_geojson": "regions.geojson", "scale_factors": [2,2]}
```

The affine maps native assay coordinates to the scene image pixels. Distinct,
named systems prevent ambiguous rescaling. Scene inputs currently require an
RGB image of at most 16 million pixels. Valid Polygon/MultiPolygon GeoJSON
regions retain exact IDs and supplied review properties. The image can be
stored as a chunked pyramid; this is not a general OME-NGFF source reader or a
scanner-scale benchmark. Large TIFF intake remains in the imaging workflow.

The RNA table annotates point instances with exact observation IDs. A sibling
`STORE.ifquant.json` hashes every store file, binds metadata and preserves scene
provenance. Reimport verifies store completeness, table/point identity, XY and
named transforms. Both the store and sibling manifest must travel together.
External source paths are provenance; the store can be reopened after relocation.
The profile deliberately rejects unknown layouts rather than guessing which
arbitrary SpatialData table or coordinate system to use.

## Completed-product verification

```powershell
uv run --no-sync python -m ifquant_platform validate-spatial-links linked --assay assay.json --source source.json --regions regions.json
uv run --no-sync python -m ifquant_platform validate-molecular-context context.json --assay assay.json
```

Validation recomputes outputs from bound inputs without rewriting them. It checks
links, raw-count reconciliation, reports/CSV, processed calls and missingness.
Historical producer hashes are retained; a software update does not make an old
producer hash pretend to describe current code. Changed inputs require a new run.

## Reproduce the real lung intake example

```powershell
uv run --no-sync python scripts/replay_lung_example.py --download --output validation/output/kasmani-day3
```

Open `validation/output/kasmani-day3/report.html`. Repeat with a fresh output
directory; the verified cache can be reused without `--download`. The tracked
[acquisition manifest](../datasets/examples/kasmani-day3-young.json) pins four
public files (about 15 MB compressed), gene IDs, attribution and limitations.
Raw images/counts and generated stores remain Git-ignored.

The example uses GSE202322/GSM6108348, young lung at day 3 after influenza, and a
five-gene panel named in the authors' visualization script. It checks selected
raw counts independently against the original HDF5, AnnData/SpatialData round
trips and deposited coordinate scaling. Source `in_tissue` flags and an explicitly
unreviewed image footprint provide context; there is no fabricated anatomical
ROI, micrometer calibration or registration landmark. This is a source-data
replay, not a reproduction of Seurat integration, SPOTlight deconvolution or the
paper's biological comparisons. Sample identity is a library proxy because
independent animal/section identifiers were not available in the inspected record.

## Capacity and evidence

Limits: 200,000 observations, 100,000 features, 1 million selected sparse count
rows, 100 million input sparse entries, 1 million entries per HDF5 slice, 5 million
metadata cells and 8 GiB per input file. These are guards, not performance promises.
Raw inputs are streamed and feature selection is explicit. Visium HD parquet,
general dense AnnData conversion, automatic registration, spatial inference and
paper-level biological validation remain future work.

See [current evidence](../validation/evidence/priorities-1-2-20261009.json) and
[the execution plan](DEVELOPMENT_PLAN.md). API/format references:
[AnnData I/O](https://anndata.readthedocs.io/en/stable/generated/anndata.io.read_h5ad.html),
[SpatialData models](https://spatialdata.scverse.org/en/stable/api/models.html),
[10x spatial outputs](https://www.10xgenomics.com/support/software/space-ranger/latest/analysis/outputs/spatial-outputs),
[source study](https://www.nature.com/articles/s41467-023-42021-y).

# QuPath pilot status

Status: **completed, structurally valid unvalidated engineering pilot**.

The final evidence run completed on 2026-08-29 with QuPath 0.7.0 and is stored
under the Git-ignored local directory
`validation/output/pilot-20260829-engineering-02/`. The earlier `-01` run was a
pre-commit smoke run and is superseded because its recorded Git revision did
not contain the exact exporter bytes used at execution.

## Input and project boundary

- `D:\Microscopy_Images` was used read-only. The selected VSI and its
  pixel-bearing ETS companions were not renamed, copied in place, or modified.
- The historical `IFQuant-Lung` repository and its QuPath projects were not
  modified. The unrelated pre-existing
  `scripts/export_vsi_overviews.groovy` working-tree edit was not copied.
- QuPath `convert-ome` produced a 2048 by 2048, four-channel, singleton-Z/T
  OME-TIFF engineering derivative. It is 24,697,529 bytes with SHA-256
  `28e4c767036b0dca540a820096a0f76baa0277c33ed60bbb2cc0099539592eb8`.
- The original VSI is compound and has pixel-bearing ETS companions. Those
  companion bytes are not fully attested, so this run does not claim complete
  original-VSI byte traceability.
- A fresh disposable project was saved as `FLUORESCENCE` with one explicitly
  synthetic `Pilot ROI`. It is an execution fixture, not a biological
  annotation or ground truth. Acquisition-group identities are null and the
  biological-unit identifier is explicitly an engineering value.
- The derivative retains four channels, but this pilot maps and measures DAPI
  only.

## Reproducibility bindings

- Git code revision:
  `1014a2172f7eca1bd82bdb7f4da7d3db2d24abde`
- executed exporter source SHA-256:
  `ed690a9fb7273d16118b956744d003286e18d696c89866e9798bd5643a56d3ee`
- native detector implementation JAR SHA-256
  (`qupath-core-processing-0.7.0.jar`):
  `d6c73a8c25069fbd22048242d10176ace70b97936ee4e8d91e2981699d8cf8ef`
- runtime attestation SHA-256:
  `f161986e2a22ad4113b52515ed43481769c58b85923eabb3fa7bb280550ab062`

The exact executed exporter source and a selected-runtime-artifact manifest are
archived in the run attestations. The runtime manifest is not represented as a
complete Java classpath or operating-system attestation.

## Execution result

The annotation-content hash was independently reproduced by the Python
canonical-contract implementation before detection. Native QuPath Watershed
Cell Detection reported 1,551 nuclei. The boundary policy exported 1,453 cell
objects and excluded:

- 45 cells not fully covered by the annotation; and
- 53 cells touching the annotation boundary.

Of the 1,453 exported objects, 182 carry the warning
`nucleus_not_covered_by_cell_geometry`. The exporter aggregates that condition
into package-level QC; these objects must not be described as geometry-clean or
scientifically accepted.

The exporter omitted `--save`, so detections were not persisted into the
disposable project. Object indices are contiguous, all 1,453 object IDs are
unique, and no temporary publication files remain. The cell-object JSONL raw
byte SHA-256 is
`15bc2d2a3e19a5e4ecc7cb9c0c2631715d9faaa1131cf8daa04bc0442e9130be`.

## Structural validation and preservation

`ifquant-platform validate-package` returned `status: valid` for structural,
referential, and byte-integrity validation. The canonical package SHA-256 is
`977f2780eaa625c8332e886d1a0dbe6c6749b42bd33000a097713125258fae2f`.
The validator also reports that parameter scope is unattested, split-group
identities are incomplete, package QC is `not_evaluated`, and review state is
`unreviewed`.

The local evidence manifest is
`validation/output/pilot-20260829-engineering-02/attestations/evidence-manifest.json`.
The entire run directory is Git-ignored and local-only, the package contains
workstation-absolute file URIs, and the repository has no configured remote.
Therefore this record is neither independently portable nor durably preserved.

This result does not establish scientific validity, segmentation accuracy,
backend equivalence, model universality, endpoint fitness, or authorization for
biological analysis.

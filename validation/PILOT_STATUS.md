# QuPath pilot status

Status: **not run**. This is an environment-readiness record, not a validation
result.

On 2026-08-29, the authorized input root `D:\Microscopy_Images` was confirmed
to exist and was inspected read-only. No image or companion file was copied,
renamed, modified, or interpreted. No QuPath executable/runtime was available
on this host, so no image was opened, no annotation or channel identity was
asserted, no detection was executed, and no output package was produced.

A future pilot must first:

1. install or explicitly locate a supported QuPath runtime;
2. choose one immutable image and retain every companion artifact (especially
   for compound formats such as VSI);
3. verify image identity, channels, calibration, singleton Z/T dimensionality,
   and supplied annotation-set hash;
4. fill a run-specific copy of `qupath/config/pilot.example.json` without
   committing workstation paths or biological identifiers to the example;
5. execute into a fresh destination; and
6. run `ifquant-platform validate-package` over the resulting package.

Passing those engineering checks would not establish scientific validation,
backend equivalence, or fitness for a biological endpoint.

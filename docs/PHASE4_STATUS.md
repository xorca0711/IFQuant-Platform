# Phase 4 native-QuPath baseline status

## Outcome

The Phase 4 **engineering evaluation implementation is complete**. The
scientific Phase 4 exit gate is not complete and has not been claimed.

The repository now has a prospectively frozen evaluation-plan contract, an
independent Python evaluator, a WKT-to-pixel reference check, deterministic
matching and error metrics, a CLI, schemas, tests, and a synthetic fixture. The
existing run05 native QuPath pilot proves that the configured watershed
executor runs on a complete 2048 x 2048 engineering image. It is not a scored
baseline against reviewed real references.

The connected `D:\Microscopy_Images` folder was inspected on 2026-08-30. It
contained 939 raw microscopy/metadata files (including OIR, VSI, HDF5, ETS and
OMP2INFO) but no QuPath project, QPDATA, reviewed mask, label, GeoJSON,
correction, or reference artifact. Raw pixels cannot be promoted into reference
truth by the detector being evaluated.

## Implemented algorithms

1. Frozen Phase 3 binding: the plan names exact split, reference-set, and
   raster-reference SHA-256 identities. The Phase 3 validators run recursively.
2. Independent reference rasterization: frozen canonical WKT polygons are
   rasterized by pixel-center inclusion; the supplied reference pixel ledger
   must exactly match every selected Phase 3 object identity and pixel.
3. Detection matching: candidate pairs use pixel intersection-over-union. A
   deterministic Hopcroft-Karp bipartite match maximizes match cardinality at
   the prospectively declared IoU threshold; no object is reused.
4. Split and merge accounting: a reference is split when at least two
   predictions exceed the declared reference-overlap fraction; a prediction is
   merged when at least two references exceed the declared prediction-overlap
   fraction.
5. Boundary accuracy: four-connected object boundaries are compared within a
   declared Chebyshev pixel tolerance, reporting precision, recall, and F1.
6. Stratification: reference detection recall is reported by declared size
   strata and explicit crowded/not-crowded labels.
7. Count behavior: prediction-minus-reference signed error and absolute error
   are retained per image and in aggregate.
8. Measurement bias: matched objects retain every signed prediction-minus-
   reference difference and report mean signed and mean absolute error for
   shared morphology/intensity fields.

The synthetic fixture produces perfect detection/boundary/count values and a
deliberate +2 DAPI-mean error. Those values test the software only. They are not
evidence about native QuPath performance.

## Decision gates

| Gate | State | Required evidence |
| --- | --- | --- |
| P4-E1 evaluation contracts and CLI | Pass | Schemas, frozen fixture, recursive hash checks, deterministic report, and tests. |
| P4-E2 native QuPath execution | Engineering pass only | Run05: 1,803 candidates on one full-frame derivative; formal H1/H2 remain open. |
| P4-H1 real reference readiness | Blocked | Exhaustively reviewed real DAPI instances and ignores with reviewer/adjudication lineage. |
| P4-D1 real split freeze | Blocked | User-approved mouse/slide/source-family separation, batch/scanner controls, and locked held-out identities/content. |
| P4-S1 study acceptance criteria | Blocked | Prospective numeric thresholds and aggregation rules approved for the intended biological/acquisition scope. |
| P4-S2 scored native baseline | Blocked by P4-H1/D1/S1 | Run the unchanged native method on frozen images and report detection, split/merge, boundary, count, and measurement-bias evidence. |

## Exact continuation order

1. Create or connect a QuPath project containing reviewed biological ROIs and
   exhaustive nuclear corrections for selected raw images.
2. Supply mouse, slide, source-family, batch, and scanner identities; resolve
   formal H1 and choose the H2 geometry-warning disposition for any reused
   run05 objects.
3. Freeze the real Phase 2 observation revision and Phase 3 reference/split
   revision after reviewer approval.
4. Approve scope-specific numeric Phase 4 acceptance thresholds before looking
   at confirmatory results.
5. Rasterize the frozen references, run native QuPath with an exact method
   identity, evaluate once with `evaluate-segmentation`, and record all failures
   and abstentions.

Only step 5 can close the scientific Phase 4 exit gate. Phase 5 backend
comparisons must not begin before that record exists.

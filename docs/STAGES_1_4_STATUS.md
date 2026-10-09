# Stages 1–4 engineering checkpoint — 2026-10-09

The user authorized implementation of stages 1–4 and MIT licensing. These stages
map to roadmap WP0–WP3; the older Phase 1–5 validation/backend labels describe a
different axis and retain their scientific gates.

| Stage | Implemented and exercised | Open boundary |
| --- | --- | --- |
| 1 — Reproducibility and backend closure | Locked optional dependencies; Windows/Linux CI definition; MIT and external notices; isolated fresh QuPath smoke helper; StarDist run 11 exports, validates and renders QC. | Remote CI not observed; human review and backend accuracy unresolved. |
| 2 — High-resolution intake | Multi-file source identities; calibrated TIFF pyramid selection; bounded window reads; lazy core/halo plans; QuPath native RGB bridge; tile resume, cancellation/failure states, hashes and runtime metrics. | Synthetic pyramid/window checks only; actual scanner-scale throughput, vendor companion completeness and optional codec matrix untested. |
| 3 — Separate H&E module | Bound profile; tissue/background baseline; artifact/reference/anatomy polygons; frozen Lab clustering; accepted-label nearest-centroid alternative; GeoJSON corrections; candidate/annotated area denominators. | Actual stain/lesion accuracy, complete anatomical review, trained nuclei/anatomy models and endpoint-specific lesion validation pending. |
| 4 — Usable imaging workflow | CLI-to-HTML example; tile overlays/masks; explicit marker rules; calibrated cell neighborhoods; ordinal forms; missingness-preserving section/specimen reports. | No custom GUI, spatial enrichment inference, IF–H&E registration, cuff morphometry or automatic severity scoring. |

This completes an engineering implementation across all four stages. It does not
close the roadmap's biological validation requirements or make a scientific
release claim. Detailed commands and limitations are in [the workflow guide](TISSUE_WORKFLOW.md).

## Local evidence

- Original regression baseline: 112 tests and 130 subtests passed before changes.
- Integrated regression: 134 passed and one schema-inventory-count assertion
  failed because the schema collection grew from 15 to 24. The expected inventory
  was updated and producer dictionaries were closed explicitly.
- Affected schema/tissue rerun: 24 tests and 24 subtests passed. Combined with
  unaffected passing regression results, all 135 tests and 139 subtests are
  accounted for. Subsequent report-only changes are recorded by focused checks
  in the evidence artifact. No unrelated tests are repeatedly run.
- Scoped Ruff checks passed. Locked offline environment synchronization and
  source/wheel builds succeeded. GitHub Actions has not yet run remotely here.
- Native TIFF/pyramid window equality, calibration, holes, invalid geometry,
  tile ownership for an 8-billion-pixel virtual plan, tile-size invariance,
  exclusions, input drift, resume, cancellation, correction ancestry, missing
  reviews, weighted specimen pooling and exact physical-radius neighbors are
  covered with synthetic inputs.
- A small synthetic H&E run records memory/time; this is not a WSI performance
  benchmark. No clinical sensitivity, specificity or severity agreement was tested.

## StarDist checkpoint

Fresh run `pilot-20261009-engineering-11-stardist` produced 2,380 candidates:
2,308 accepted and 72 excluded by the image-boundary guard. The accepted set
contains 1,322 topology warnings. Independent structural validation and QC
rendering succeeded. All outputs remain unvalidated engineering candidates.
No formal H1/H2 acceptance or native-versus-StarDist comparison was created.
Run 10 retains the failed sandbox/Java preferences attempt; runs 06–09 remain
historical failed/diagnostic evidence.

## Next development pipeline

1. Test a real high-resolution brightfield slide, its vendor companion inventory,
   calibration, round-trip coordinates and representative tiles; establish a
   measured RAM/I/O envelope before advertising scanner-scale performance.
2. Define lung anatomy/artifact/lesion labels and study sampling with a reviewer;
   develop on training subjects, freeze parameters, and evaluate on independent
   subjects/scanners. Prefer the interpretable baseline until a new model earns
   its added complexity. Preserve corrected revisions and failed cases.
3. Resolve IF segmentation warnings, then benchmark native/StarDist and consider
   InstanSeg under the existing split/evaluation contracts. Add validated
   anatomical endpoints such as cuff burden or alveolar morphometry separately.
4. Add measured IF–H&E transforms and registration errors when paired images
   exist. Then implement SpatialData/AnnData adapters and a small lung spatial-RNA
   example; the supplied Slide-GoTags paper informs a later TME extension.

The [research roadmap](../notes/2026-10-09-development-roadmap.md) contains the
methodology shortlist, papers, alternatives and scientific acceptance criteria.
No sequencing pipeline or inferred-expression model was added in this tranche.

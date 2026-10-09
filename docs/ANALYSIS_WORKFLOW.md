# Optional analysis workflows

These tools extend the independent fluorescence and H&E workflows. They preserve
measured data and declared biological identities; they do not supply reviewed
pathology labels or validated cell types. Current scope and conditional branches
are in the [numbered register](DEVELOPMENT_PLAN.md).

## Install and generate runnable plans

```powershell
uv sync --locked --extra dev --extra imaging --extra morphology --extra performance --extra spatialdata
uv run --no-sync python scripts/demo_development_pipeline.py --output validation/output/development-demo
```

This produces **ten executed synthetic workflows**, editable JSON plans, CSVs,
masks and result documents. All biological names and programs in that demo are
fixtures. Use new destinations for reruns. Run any plan independently with
`python -m ifquant_platform COMMAND PLAN.json --output NEW_RESULT`.

| Command | Demo plan / input | Result and scope |
| --- | --- | --- |
| `compare-masks` | `masks.json` | Class confusion, Dice, IoU and ignored-pixel count; absent classes remain null. Pixels are not biological replicates. |
| `reviewer-agreement` | `agreement.json` | Exact paired-unit agreement and linear weighted kappa; missing ratings retained, undefined marginals abstain. The frozen rubric defines the score ordering. |
| `measure-morphology-profiles` | `morphology.json` | Reviewed cuff area/inner perimeter and septal transect length in calibrated units. Neither is a universal severity score or unbiased 3D stereology. |
| `score-rna-programs` | `programs.json` | Exact feature IDs, species, versioned program registry, coverage and filtering; mean log1p(CP10k) with an explicit library denominator. |
| `domain-baselines` | `domains.json` | Expression-only clustering versus graph-smoothed clustering on the same eligible observations. Cluster numbers have no biological labels. |
| `specimen-associations` | `associations.json` | Paired-unit means aggregated per declared biological unit within stratum, Spearman effect and within-stratum permutation tests. |
| `test-spatial-hypotheses` | `hypotheses.json` | Frozen label pairs/radii; radius graph, normalized mixing score, conditioned nulls, BH and coordinate-jitter sensitivity. |
| `evaluate-registration` | `registration.json` | Fit and held-out errors separately, local landmark support, out-of-image points, sampled grid fold/area diagnostics. |
| `import-slide-gotags` | `gotags.json` | Explicit processed MC38-OVA column profile; author expression status retained separately from nanopore calls, positive observed coverage required for measured calls. Output is a new directory. |
| `import-cell-features` | `cell-features.json` | Explicit MCMICRO-compatible CSV column mapping, exact string cell IDs, coordinates/units, numeric features and nulls. Intensities are not RNA counts. |

Input readers enforce closed plan fields, finite values and bounded capacities.
These new plan formats are versioned runtime contracts; the existing fluorescence,
tissue and spatial schema families remain separate.

## Measured RNA and biological units

Program registries carry `registry_id`, `species`, `feature_id_namespace`, and
per-program exact feature IDs, reference, minimum coverage and interpretation.
No symbol-to-ID, orthologue, species or cell-type conversion is automatic.
Niethamer is a candidate lung-regeneration reference from the
[methodology review](../notes/2026-10-09-development-roadmap.md); curated real
programs must identify their source table/version and injury/timepoint scope.
The demo registry is intentionally synthetic.

`selected_features` normalizes within the supplied panel. For full-library
normalization select `external_full_library` and supply a complete
`observation_id,total_counts` table; totals cannot be smaller than the selected
counts. Missing RNA is never a biological zero. Gene coverage, library-size and
detected-feature filters produce explicit excluded statuses. This simple mean
program score is not Seurat AddModuleScore, deconvolution or lineage inference.

Domain baselines use log1p(CP10k), centered expression SVD, seeded k-means, and an
optional weighted mean over a radius graph (including self). The dense workspace
is capped at 10 million elements and 2,000 supplied features. A declared minimum
feature count is enforced. Smoothing agreement is not accuracy, and inertia from
different feature spaces must not be compared as if they shared a denominator.
**The real Kasmani five-gene interchange panel is not used for domain inference.**

Association input is exactly
`biological_unit_id,stratum,sampling_unit_id,x,y`. An independently verified
sampling manifest must establish the biological units; the tool cannot discover
independence from a CSV. Repeated regions are averaged within each biological
unit. Missing pairs are excluded explicitly. Units occurring in multiple strata
are rejected: longitudinal data need a separately specified repeated-measures
model. Ordinal severity is not an appropriate continuous mean endpoint here.

## Registration and spatial inference

On live trusted VALIS Slide objects, call
`ifquant_platform.registration_qc.export_valis_points(moving_slide, fixed_slide, input_csv, output_csv)`.
This invokes `warp_xy_from_to` with source, point and destination levels **0**.
No registrar pickle is loaded. Input columns are
`point_id,role,source_x,source_y,target_x,target_y`; roles are `observation`,
`fit`, `evaluation`, `probe`. Targets are supplied only for landmarks. The exporter
adds `warped_x,warped_y`. The QC plan binds both image sources, method/version,
run reference, independent held-out reference, exact CSV hash and section relation.

Use a complete rectangular probe grid to test signed triangle area ratios.
Negative/zero ratios expose sampled folds; a finite grid cannot prove global
invertibility. Nearby held-out residuals are local error **proxies**, not confidence
bounds. Unsupported locations retain null error. Registration QC reports do not
automatically promote points into accepted RNA/image joins. In particular, serial
sections never authorize individual-cell identity matching.

Spatial hypothesis plans bind assay and label-file hashes, label pairs, radii,
coordinate units, seed, exclusions, boundary policy, permutation count and jitter.
Label CSV columns are
`observation_id,specimen_id,region_id,coverage_stratum,label,boundary_distance`.
All distances and jitter use the assay frame's `pixel` or `um` unit.
`exclude_boundary_observations` requires supplied distances to the valid window
boundary and uses a common margin of maximum radius + 3 jitter SD.
`conditional_on_observed_window` keeps the window restriction explicit; it is not
an edge-corrected tissue-wide estimator. Gaussian jitter can exceed 3 SD; its
reported range is a sensitivity scenario, not an exclusion guarantee or CI.

The normalized mixing score is
`0.5 × (reference–target edges / reference–reference edges) × (n_reference−1) / n_target`.
Undirected radius edges are counted once. Undefined denominators, undefined null
draws and degenerate nulls abstain. Label shuffles preserve specimen, region and
coverage strata. Enrichment p-values use `(1 + exceedances)/(1 + permutations)`;
BH retains abstentions conservatively in the declared family as p=1. There is no
claim of antigen recognition, signaling or killing from spatial association.

This revises the authors' global shuffles and zero substitution intentionally.
Source formula and API references:
[Slide-GoTags analysis](https://github.com/amitsud/Slide-GoTags_Analysis),
[VALIS point API](https://valis.readthedocs.io/en/latest/registration.html#valis.registration.Slide.warp_xy_from_to).

## Processed Slide-GoTags and source reconciliation

The MC38-OVA profile requires the published author columns
`SIINFEKL_WPRE_status` and `SIINFEKL_WPRE_nanopore_status`, an exact ID column and
an explicit author-value mapping. Optional coverage and clonotype columns must
be declared. Author expression annotations are preserved separately. A positive
author call without observed read coverage stays ambiguous; missing rows remain
not reported. RNA reference-only never becomes DNA wild type. Clonotype presence
does not establish cognate antigen specificity.

The public source-data check compares **240 RCC_1_A rows / six pairs** between
Supplementary Table 13 and Figure 3c. All match. This is reported-statistic
reconciliation, not recomputation from cells. The source workbook lacks cell
coordinates and edge counts; the processed cell-data portal requires sign-in.

```powershell
uv sync --locked --extra imaging --extra wsi-codecs --extra performance
uv run --no-sync python scripts/replay_public_qualification.py --download --output validation/output/public-qualification
```

This downloads three pinned assets (~214 MB total), runs the real WSI window
benchmark and source-table comparison, and retains input hashes. Source data stay
outside Git. The [manifest](../datasets/examples/public-qualification.json)
records URLs and terms. The [paper](https://www.nature.com/articles/s41587-026-03194-1)
is the optional TME methodology reference, not validation of this implementation.

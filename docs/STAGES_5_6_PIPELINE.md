# Stages 5–6: spatial RNA and optional multimodal applications

Plan and initial implementation: 2026-10-09. Stage 5 = roadmap WP4; stage 6 =
WP5. These names do not replace the older Phase 5 segmentation/backend gate.
The intended product remains a tool for future high-resolution tissue images,
lung injury/regeneration first. Omics is optional; the imaging workflow stays usable alone.

**Started in this change:** processed RNA interchange, exact IDs, affine coordinate
checks, tissue-region links, and processed transcript-genotype/TCR missingness.
**Not yet implemented:** native AnnData/SpatialData/Visium adapters, automatic
registration, deconvolution, spatial inference or reproduction of a public paper.
The runnable example is synthetic. This document defines the remaining pipeline
and the evidence required to move each part beyond an engineering prototype.

Local verification: **156 tests and 144 subtests passed**, plus scoped Ruff and
the synthetic CLI import/link/context demonstration. Exact input/output identities
and logs are recorded in `validation/evidence/stages-5-6-20261009.json`.

## Dependency graph

```mermaid
flowchart TD
    I[Stages 1–4: calibrated images and reviewed region revisions] --> C
    A[Processed spatial RNA: counts, IDs, coordinates, specimen] --> B[5A Intake and assay QC]
    B --> C[5B Explicit coordinate transform and registration QC]
    C --> D[5C Region/spot linkage and gene summaries]
    D --> E[5D Optional composition and spatial domains]
    E --> F[5E Lung example and reproducibility report]
    C --> R[6A Same-section or serial-section registration adapter]
    T[Processed genotype, TCR and optional protein data] --> M[6B Exact-ID multimodal observations]
    B --> M
    M --> N[6C Genotype/clonotype spatial hypotheses]
    R --> N
    N --> P[6D Null models and uncertainty sensitivity]
    P --> Q[6E Narrow TME reproduction and optional interaction methods]
```

Registration checks are a dependency of spatial linkage, even though automatic
registration is scheduled in stage 6. Stage 5 can use a supplied, measured transform
or a documented same-image scale conversion. Adjacent sections can support
regional correspondence; they do not establish identical individual cells.

## Stage 5 — associate measured spatial RNA with image phenotypes

| Step / status | Inputs and operations | Output | Exit evidence |
| --- | --- | --- | --- |
| **5A.1 Implemented foundation** | Explicit subject/specimen/section, spot/nucleus/cell entity, XY frame, observation table, feature IDs and sparse integer RNA counts. Validate exact IDs, duplicates, finite coordinates, assay status and input hashes. | `spatial-assay/1`, library totals, source inventory. | Unknown/duplicate IDs and noninteger counts rejected; measured zero distinguished from unassayed/failed; byte drift detected. |
| **5A.2 Next adapter milestone** | Read an explicitly named raw-count layer from AnnData; read Visium positions, barcode/feature tables, sparse matrix and scale factors. Preserve barcode suffixes, duplicate gene symbols with unique feature IDs, and excluded observations. | Round-trip AnnData plus SpatialData elements mapped to named coordinate systems. | Exact observation/feature order and counts survive export/reimport; sparse storage remains sparse; no silent `.var_names_make_unique()` or barcode rewriting. |
| **5B.1 Implemented foundation** | Provided affine from assay frame to base-image pixels; bind both identities and section relationship. Evaluate supplied fit and held-out landmark roles separately in micrometers. | Transform record, inverse round-trip check, per-role RMSE/max error. | Rotation/reflection/anisotropic calibration tests; singular transforms and cross-subject/specimen joins rejected; absence of evaluation landmarks remains `not_evaluated`. |
| **5B.2 Registration qualification** | Review landmark distribution, plane/section pairing, spatial uncertainty and residuals on locations not used for fitting. Record image provenance and downsampling explicitly. | Scope-specific registration acceptance record and uncertainty field. | Numeric tolerance and local landmark coverage prospectively defined for the endpoint. Synthetic zero error is not empirical registration accuracy. |
| **5C.1 Implemented foundation** | Transform point centers to reviewed/pending reference regions; exclude supplied artifacts; abstain at uncertain boundaries and reference overlaps. Reconcile raw RNA totals only over measured linked observations. | `spatial-links/1`, observation CSV, region/feature raw sums and report. | Counts reconcile; holes/edges tested; no hard cell assignment for spots; no numeric aggregate from unassayed observations. |
| **5C.2 Biological feature layer** | Bind lung marker/gene-set versions, species/ID mapping, count filtering and normalization. Retain raw counts alongside normalized summaries; choose section/subject as sampling units. | Versioned region-level RNA programs linked to H&E/IF descriptors. | Held-out gene/protein or independently annotated agreement; gene-set coverage and unknown labels retained. Morphology association does not establish lineage or regenerative fate. |
| **5D Optional composition/domain methods** | Branch on assay resolution. Use supplied single-cell labels or reference mapping for cell/nucleus assays. Consider cell2location for mixed-cell spots with an appropriate reference. Compare simple spatial neighborhoods with BANKSY domains. | Cell abundance estimates with uncertainty, or candidate spatial domains with method identity. | Independent reference suitability; subject-level holdout; stable results across radius/registration choices; new methods outperform a declared baseline for the selected endpoint. |
| **5E Public example and future-image handoff** | Select one manageable influenza-lung spatial-RNA example; inventory accessible files, terms, resolution, preprocessing and biological grouping. Replay the same adapters on future image/assay inputs. | Reproducible acquisition manifest, commands, expected checks and report. | Public example actually reproduced with hashes; limitations and missing native-resolution images explicit. No public-data-only product restriction. |

The current interchange uses small explicit CSVs so identity/coordinate tests do
not require installing a large omics stack. The next adapter milestone adds
AnnData/SpatialData as optional extras with their own lock and CI coverage.
Their APIs support annotated matrices and named spatial transformations;
IFQuant will retain additional review and provenance bindings. Sources:
[AnnData](https://anndata.readthedocs.io/en/stable/generated/anndata.AnnData.html),
[SpatialData transformations](https://spatialdata.scverse.org/en/stable/tutorials/notebooks/notebooks/examples/transformations.html).

For Visium, map `pxl_col_in_fullres` to X and `pxl_row_in_fullres` to Y. Apply a
hires scale only when the target really is that downsampled image; never twice.
`tissue_hires_image.png` is a derivative, not evidence of native scanner resolution.
Visium HD introduces much larger position tables; this initial bounded adapter
does not claim HD-scale capacity. [Official spatial output definitions](https://www.10xgenomics.com/support/software/space-ranger/latest/analysis/outputs/spatial-outputs).

The composition and domain branches are conditional recommendations:
[cell2location](https://cell2location.readthedocs.io/en/latest/) estimates spatial
cell-type abundance using reference expression signatures;
[BANKSY](https://prabhakarlab.github.io/Banksy/) incorporates nearby expression
features for spatial clustering. Neither should be installed or applied merely
because a dataset has coordinates. Keep estimates distinct from direct measurements.

## Stage 6 — optional multimodal/TME applications

| Step / status | Inputs and operations | Output | Exit evidence |
| --- | --- | --- | --- |
| **6A Registration adapter — planned** | Wrap an external registration result such as VALIS; retain source/target image identity, full-resolution direction, affine/deformation representation and independent landmarks. | Adapter-specific transform plus common registration QC. | Transform direction and native coordinate round trips checked; deformation grid/Jacobian and landmark errors inspected; adjacent sections never joined as identical cells. Current implementation accepts supplied 2D affine only. |
| **6B.1 Implemented foundation** | Attach processed transcript genotype and TCR observations by exact observation ID within one assay. Preserve measured, unassayed, failed, ambiguous and unreported states. | `molecular-context/1`, per-target coverage and missingness counts. | Unknown IDs and duplicate target observations rejected; measured calls require positive coverage; no geometric nearest-cell join or fabricated negative call. |
| **6B.2 Slide-GoTags-specific adapter — planned** | Audit one deposited processed sample, its barcode namespaces, spatial coordinates, RNA layer, targeted-variant calls and TCR chains/clonotypes. Preserve dataset sample and preprocessing identities. | Source-specific mapping manifest and processed multimodal bundle. | Every retained join traced to original tables; counts and missingness reconcile with source processing. Current generic interchange is not a completed Slide-GoTags adapter. |
| **6C Hypothesis declaration — planned** | Predeclare variant-expressing population, clonotype/immune population, region, radius/distance, quality exclusions and independent antigen-specificity evidence if available. | Frozen analysis plan and observed distance/neighborhood statistics. | Explicit tested pair set; no post-hoc radius selection masquerading as confirmation. Spatial proximity alone does not establish antigen recognition, contact or signaling. |
| **6D Null and sensitivity analysis — planned** | Randomize labels within appropriate specimen/region/coverage strata while retaining spatial structure; specify exchangeability assumptions. Perturb coordinates using measured registration uncertainty and vary predeclared masks/radii. | Empirical null distribution, effect size, multiple-testing correction and sensitivity envelope. | Null calibration on simulated negatives; subject-level replication; results not driven by density, boundary exclusion or assay coverage. A zero null variance triggers an undefined/abstained result, not an infinite score. |
| **6E Narrow reproduction and optional fusion — planned** | Reproduce one source-defined genotype/clonotype spatial association before broadening. Add protein if measured. Consider LIANA+ only for compatible molecular communication hypotheses; SpatialGlue only for suitably paired spatial modalities. | A reproducible source comparison with explicit discrepancies and optional extension report. | Agreement assessed against the chosen source output, documented exclusions and matched scope. Any inferred interaction or fused domain remains a hypothesis/model result. |

The supplied [Slide-GoTags paper](https://www.nature.com/articles/s41587-026-03194-1)
motivates measured RNA/genotype/TCR linkage. Its data statement lists SCP3655,
SCP3657, SCP3660 and SCP3667; [the authors' code](https://github.com/amitsud/Slide-GoTags)
is the source-specific processing reference. This plan does not claim those
files were downloaded or a paper result reproduced. RNA `reference_only` is a
coverage-qualified transcript observation, not a DNA wild-type diagnosis.
TCR presence and clonotype identity require separate antigen-specificity evidence.

Registration and later molecular interpretation references:
[VALIS](https://valis.readthedocs.io/en/latest/),
[LIANA+](https://liana.readthedocs.io/en/stable/), and the
[earlier methodology shortlist](../notes/2026-10-09-development-roadmap.md).
The detailed null design is an IFQuant proposal, not an asserted default of these tools.

## Implementation sequence and acceptance ledger

| Increment | Dependency | Concrete work | State |
| --- | --- | --- | --- |
| **A — Shared identities/coordinates** | Stage 2 source and stage 3 regions | Five closed schemas, raw-RNA import/validation, affine checks, exact region joins, molecular missingness, tests, synthetic CLI example. | Implemented in this PR; engineering validation only. |
| **B — Native spatial interchange** | A | Explicit raw-layer AnnData import/export, selected Visium format profiles, SpatialData named-frame round trips, sparse-memory checks and adapter-specific fixtures. | Next. |
| **C — Lung public replay** | B | Audit one Kasmani influenza example; ingest metadata/counts/coordinates and available histology; reproduce region/spot overlay and a narrow measured gene summary. | Planned; no download yet. |
| **D — Biological context branch** | C plus appropriate reference/labels | Freeze gene programs and baseline, then conditionally compare reference mapping/cell2location/BANKSY. | Data-dependent; software work need not wait for private images. |
| **E — Registration and processed TME replay** | A/B and paired/source-specific data | VALIS-result adapter, registration uncertainty, Slide-GoTags processed sample schema, exact genotype/TCR joins. | Planned. |
| **F — Spatial hypotheses and nulls** | E plus frozen question and sufficient coverage | Distance/neighborhood tests, stratified nulls, uncertainty sensitivity, one-source reproduction; optional interaction/fusion branches afterward. | Planned. |

Future intended-use evaluation remains roadmap WP6/stage 7. Scientific thresholds
are prospectively specified per endpoint once the relevant acquisition and labels
exist. No universal numeric accuracy criterion is invented in this plan.

## Run the initial pipeline

```powershell
uv sync --locked --extra dev --extra imaging
uv run --no-sync python -m ifquant_platform demo-spatial --output validation/output/spatial-demo
uv run --no-sync python -m ifquant_platform validate-spatial validation/output/spatial-demo/assay.json
```

Open `validation/output/spatial-demo/linked/report.html`. The generated bundle
includes a tiny synthetic image, region GeoJSON, RNA CSVs, an import config,
assay manifest, affine transform/landmark, region RNA counts and `context.json`.
It intentionally includes an artifact point, a shared-boundary point, an
out-of-image point, unassayed RNA and incomplete genotype/TCR coverage. These are
engineering test cases, not simulated biological evidence or reviewer approval.

For your own processed tables:

```powershell
uv run --no-sync python -m ifquant_platform import-spatial import.json --output assay.json
uv run --no-sync python -m ifquant_platform link-spatial assay.json --source source.json --regions regions.json --transform transform.json --boundary-uncertainty-um 2 --output spatial-links
uv run --no-sync python -m ifquant_platform attach-molecular-context assay.json --calls molecular.csv --output context.json
```

`import.json` follows `contracts/spatial/v1/spatial-import.schema.json`; the demo
provides a filled example. CSV paths resolve relative to that config. The user
declares species/subject/specimen/section, assay ID, entity type, frame ID/unit,
XY axis order and top-left/downward convention. Convert other coordinate
conventions explicitly before import. Affines map input coordinates into the
registered image's base pixels, and bind canonical assay/source hashes.

| CSV | Exact header | Semantics |
| --- | --- | --- |
| Observations | `observation_id,x,y,assay_status` | Every supplied observation has coordinates; RNA status is `measured`, `not_assayed`, or `failed`. |
| Features | `feature_id,feature_name` | IDs unique; display names can repeat. No silent species/gene conversion. |
| Counts | `observation_id,feature_id,count` | Sparse nonnegative raw integer RNA counts. Omitted pairs are zero detected counts only for a measured observation; they are not proof of absent expression. |
| Molecular context | `observation_id,modality,target_id,status,value,coverage` | `transcript_genotype` or `tcr`; status measured/not_assayed/failed/ambiguous. A missing row becomes `not_reported`. Positive coverage is required for measured calls; blanks stay null. |

For transcript genotype, measured values are `alternate_detected`, `reference_only`
or `mixed`. For TCR, a measured value is an externally defined clonotype ID; define
its chain/sequence pairing and scope upstream. The current format records supplied
total coverage but does not derive variant calls or assemble TCRs. Whole-cell,
nucleus and spot identities remain distinct even when their string IDs coincide.

### Limits of this first increment

- Up to 200,000 observations, 100,000 features and 1 million sparse count rows;
  no dense matrix is constructed. Duplicate-coordinate detection uses a bounded
  in-memory set, so these limits are engineering guardrails, not benchmarked WSI/HD capacity.
- Up to 10 million point/region and 50 million point/edge comparisons; no spatial
  tree or deformable registration yet. Molecular expansion is capped at 1 million rows.
- Region RNA sums are raw-count reconciliation, not normalized expression,
  differential expression, cell abundance, area burden or biological inference.
- Boundary uncertainty is an explicitly supplied exclusion distance in µm.
  It does not become a statistical confidence interval. Landmark role labels are
  supplied attestations; numerical residuals cannot prove holdout independence.
- A transform without evaluation landmarks remains unqualified. Even a supplied
  evaluation point does not establish sufficient coverage or registration validity.
- Absolute input paths and byte hashes retain provenance; relocated or changed
  input files require a new import. Completed output paths cannot be overwritten.
- `validate-spatial` validates the assay, not a completed multimodal scientific
  study. Independent packaged-output verification for links/context and native
  adapter round trips are subsequent hardening work.
- Public data are a reproducible development example. Future private or newly
  acquired high-resolution images remain first-class intended inputs.

## Resource intake choices

First lung example: [Kasmani influenza spatial sequencing repository](https://github.com/ryanjbrown21/Flu_Spatial_Sequencing),
with GEO accessions GSE202322 (spatial) and GSE202325 (scRNA-seq) from the existing
roadmap. Audit exact sample pairing, age/infection context, image resolution,
file terms and count normalization before selecting a subset. Niethamer's
regeneration atlas remains a candidate expression reference, not measured spatial
ground truth for unrelated images. Select one Slide-GoTags processed deposit only
after the RNA and coordinate adapters work. Raw sequencing and foundation-model
training remain outside this initial pipeline.

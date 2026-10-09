# Active development plan

This is the current execution order for IFQuant Platform. The product is a tool
for future high-resolution tissue images, with lung injury/regeneration first.
H&E and fluorescence work independently; spatial RNA and TME modules are optional.
Public data support software examples and suitable evaluations without limiting
the product to public-data research.

Three numbering systems exist. **Priority 1–5** below is the current work order.
Roadmap **stages 1–7 / WP0–WP6** describe product capabilities. Historical
**fluorescence Phases 1–9** describe governance/backend gates, preserved in
[the fluorescence phase record](DEVELOPMENT_PHASES.md). “Proceed through phase 2”
in the current request authorizes priorities 1 and 2 below, not a reset of those
historical gates.

| Priority / jobs | Deliverable | Completion boundary |
| --- | --- | --- |
| **1.1** Validate completed links/context | Recompute hashes, exact joins, count totals, exclusions and missingness from source inputs; verify CSV and report outputs. | Tampered or incomplete products are rejected. |
| **1.2** AnnData | Explicit sparse raw-count layer, selected XY, exact IDs, obs/var metadata, export/reimport. | Raw counts, ordering, coordinates and missingness survive round trip; no dense matrix. |
| **1.3** Classic Visium | 10x v3 HDF5 and integer Matrix Market; headered/headerless positions; declared fullres/hires/lowres target. | One scale conversion, exact barcodes, preserved in_tissue and missing-matrix positions. No Visium HD claim. |
| **1.4** SpatialData | Named coordinate frames, RNA table/points, optional bounded RGB image pyramid and region geometry/review metadata. | Portable IFQuant-profile store round trip and byte verification. Arbitrary SpatialData discovery is not implemented. |
| **1.5** Dependencies/capacity | Locked optional extras, supported-platform CI, sparse/capacity regression checks and example runtime evidence. | Limits enforced; one example's memory is not a scanner-scale capacity guarantee. |
| **1.6** Subsequent image/upstream interchange | General OME-NGFF source intake and MCMICRO-compatible result mapping. | Follow-up after the first lung replay. Current SpatialData image storage does not provide a general OME-NGFF image reader. |
| **2.1–2.2** Lung resource audit/acquisition | One Kasmani Day 3 young-lung sample, source hashes, provenance/terms, declared feature panel and opt-in downloader. | Deposited bytes verified; source data remain outside Git. |
| **2.3–2.4** Correspondence/report | Deposited scale applied to spot coordinates, real H&E overlay, source in_tissue/context tables and raw gene summaries. | Independent HDF5 count reconciliation and both interchange round trips. No fabricated micrometer calibration or pathological regions. |
| **2.5** Reusable replay | Documented commands/configuration and machine-readable evidence. | Runnable from a clean environment with the declared downloads. |
| **3.1–3.3** Imaging qualification | Real high-resolution intake benchmark; annotation/sampling contracts; LungDamage-inspired and QuPath classifier comparison. | Representative source images and reviewed annotations required for accuracy claims. |
| **3.4–3.5** Segmentation | Resolve StarDist warnings, native/StarDist evaluation, then an InstanSeg executor/comparison if justified. | Independent reviewed references; weights/runtime identities; no promotion from structural checks alone. |
| **3.6–3.7** Morphology/severity | Qualified area endpoints, separately specified cuff/septal measurements, model-specific rubric and reviewer agreement. | Disease/model-specific validity; no universal H&E severity score. |
| **4.1–4.3** Lung RNA features/statistics | Versioned gene mappings/programs, explicit normalization and spatial baselines/nulls. | Coverage, unit of replication, effect sizes and uncertainty reported. |
| **4.4–4.6** Conditional biological context | Appropriate reference mapping/cell2location, BANKSY comparison and morphology–RNA associations. | New methods must address a declared question and be evaluated against a baseline. |
| **5.1–5.3** Registration/TME intake | VALIS-result adapter, independent registration QC, one processed Slide-GoTags adapter. | Source-specific identity/coverage reconciliation and same/serial-section distinctions. |
| **5.4–5.7** TME inference/reproduction | Frozen pairs/radii, conditioned nulls, uncertainty sensitivity and narrow source reproduction. | Spatial association does not establish antigen recognition or killing. LIANA+/SpatialGlue remain conditional. |

Priority 3 can advance alongside the RNA work. It does not depend on omics to make
the imaging product useful. Jobs requiring biological labels remain separate
from software jobs that can be completed with fixtures and public examples.

## Methodology mapping

- **LungDamage, QuPath, ATS/ERS, ATS injury guidance and Predella:** priority 3
  baselines, sampling, denominator definitions and reviewer protocols.
- **InstanSeg, Mesmer/TissueNet:** priority 3 candidate executors/comparisons.
- **AnnData, SpatialData, OME-NGFF, MCMICRO:** priority 1 interoperability, with
  general OME-NGFF and MCMICRO work explicitly left in job 1.6.
- **Kasmani:** priority 2 real lung intake example. **Niethamer:** priority 4
  candidate cell-state/gene-program reference, not spatial truth for another image.
- **Squidpy, BANKSY, cell2location, Tangram:** priority 4 conditional spatial and
  reference-based methods. They are not invoked by the current adapters.
- **VALIS, Slide-GoTags, Slide-tags, Schürch/CODEX:** priority 5 registration,
  molecular provenance and optional TME comparisons.
- **UNI, LIANA+, SpatialGlue, HEST:** conditional representations, interaction,
  multimodal or benchmark work after a compatible input and question are defined.

The full sources and alternatives remain in the
[methodology roadmap](../notes/2026-10-09-development-roadmap.md). Detailed stage
5/6 scientific acceptance gates remain in [the pipeline](STAGES_5_6_PIPELINE.md).
Use [PROGRESS](../PROGRESS.md) for the latest executed evidence rather than
inferring completion from this plan.

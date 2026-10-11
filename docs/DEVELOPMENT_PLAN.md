# Active development plan and numbered register

Updated 2026-10-09 after the user authorized work through all five priorities.
IFQuant Platform targets future high-resolution tissue images, lung injury/regeneration
first, with independent H&E/fluorescence workflows and optional spatial RNA/TME.
Public data are development resources, not a restriction on intended inputs.

**All 31 jobs have been addressed in this development pass. This does not mean all
31 have scientific acceptance or that conditional engines are implemented.**
The machine-readable counterpart is [DEVELOPMENT_REGISTER.json](DEVELOPMENT_REGISTER.json).
See [the execution report](EXECUTION_REPORT.md) for observed runs and verification.

Priority 1–5 is the current work order. Roadmap stages 1–7 / WP0–WP6 describe
product capabilities; historical fluorescence Phases 1–9 remain scoped records.
The earlier authorization stopping at priority 2 has been superseded.

Statuses: **demonstrated** = real-source execution; **implemented** = software or
protocol plus appropriate engineering checks; **implemented_with_gate** = software
exists with a listed validation/comparison gate; **revised_implemented** = a
narrower defensible deliverable with explicit rationale; **conditional** = decision
and activation requirements recorded, engine not implemented/executed.

## Priority 1

| Job | Status | Delivered / evidence | Remaining gate or revision rationale |
| --- | --- | --- | --- |
| **1.1 Completed product validation** | implemented | Rebuild and verify links, context, reports and byte bindings. [Evidence](../tests/test_spatial.py) | No biological acceptance inferred. |
| **1.2 AnnData interchange** | demonstrated | Sparse selected raw counts, exact IDs, obs/var and status; real round trip. [Evidence](../src/ifquant_platform/spatial_adapters.py) | Dense matrices rejected; declared raw layer required. |
| **1.3 Classic Visium interchange** | demonstrated | 10x v3 HDF5 and integer MTX; headered/legacy positions; one scale conversion. [Evidence](../scripts/replay_lung_example.py) | Visium HD and automatic unit inference remain outside this profile. |
| **1.4 SpatialData exchange** | demonstrated | Named frames, RNA points/table, optional image/regions, portable store hashes. [Evidence](../src/ifquant_platform/spatial_exchange.py) | IFQuant-profile import, not arbitrary store discovery. |
| **1.5 Dependencies, capacity and CI** | implemented | Locked main and isolated VALIS environments, pre-allocation capacity guards and Linux/Windows CI. [Evidence](../.github/workflows/tests.yml) | VALIS uses separate Python 3.11 / NumPy 1.26; full optional stack uses x64 on this ARM64 host. Native whole-slide capacity remains to be benchmarked. |
| **1.6 OME-NGFF / MCMICRO intake** | revised implemented | Calibrated NGFF 0.4/0.5 bounded plane with explicit T/Z/channel selection; MCMICRO numeric feature mapping. [Evidence](../src/ifquant_platform/upstream_interchange.py) | Only uint8 planes and canonical TCZYX subsets; arbitrary discovery, 3D analysis and Visium HD remain outside this profile. |

## Priority 2

| Job | Status | Delivered / evidence | Remaining gate or revision rationale |
| --- | --- | --- | --- |
| **2.1 Lung resource audit** | demonstrated | Kasmani GSM6108348 selected; deposited derivative, identity limits and matrix scope recorded. [Evidence](../datasets/examples/kasmani-day3-young.json) | Accession proxy is not an independent mouse identity. |
| **2.2 Pinned acquisition** | demonstrated | Four public files verified; compressed and decoded cache drift rejected. [Evidence](../scripts/replay_lung_example.py) | No source images/counts committed. |
| **2.3 Image correspondence** | demonstrated | Deposited scale and in_tissue flags, real H&E overlay, all 4,992 positions retained. [Evidence](../validation/evidence/priorities-1-2-20261009.json) | Visual correspondence only; no physical calibration or independent registration landmarks. |
| **2.4 Counts and round trips** | demonstrated | 2,486 measured and 2,506 not reported; five source gene totals reconciled and both native round trips passed. [Evidence](../validation/evidence/priorities-1-2-20261009.json) | Five-gene panel is an interchange test, not biological domain evidence. |
| **2.5 Reusable lung replay** | demonstrated | Fresh-output command, pinned inputs, HTML/overlay, memory and timing record. [Evidence](SPATIAL_INTERCHANGE.md) | Source paper biological comparisons not reproduced. |

## Priority 3

| Job | Status | Delivered / evidence | Remaining gate or revision rationale |
| --- | --- | --- | --- |
| **3.1 Real high-resolution qualification** | demonstrated | Real 46,000 x 32,914 source reads plus complete level-1 appearance pipeline and package validation. [Evidence](../scripts/replay_histology_throughput.py) | Reduced-level, single-source throughput only; native-resolution multi-scanner analysis and lung pathology accuracy remain open. |
| **3.2 Annotation and sampling protocol** | implemented | Anatomy, lesion, artifact, uncertainty, exhaustive-negative coverage and biological-unit protocol. [Evidence](IMAGING_QUALIFICATION.md) | Acquisition-specific independent expert annotations still needed. |
| **3.3 Appearance / QuPath classifier comparison** | implemented with gate | Existing frozen appearance baseline plus discrete-label QuPath bridge and mask metrics; real runtime threshold-fixture pass. [Evidence](../qupath/scripts/ExportPixelClassifier.groovy) | Supervised pathology model and held-out reference comparison still required. |
| **3.4 Native / StarDist qualification** | implemented with gate | Previously repaired geometry export, frozen warning evidence and independent object-evaluation framework retained. [Evidence](PHASE5_STATUS.md) | 1,322 accepted StarDist topology warnings still need boundary review; no scientific equivalence claim. |
| **3.5 InstanSeg executor / comparison** | implemented with gate | Pinned CPU H&E ROI and resumable whole-grid nuclei execution; conservative overlap stitching, byte-bound BigTIFF/table package and deterministic rebuild; nine-tile public replay. [Evidence](STITCHING_REGISTRATION.md) | 44 seam flags require review. Independent accuracy, native-resolution multi-scanner throughput, label pyramids and fluorescence-v1 canonical export remain open. |
| **3.6 Morphology endpoints** | revised implemented | Qualified area endpoints; calibrated cuff area per inner perimeter and reviewed septal transects. [Evidence](../src/ifquant_platform/morphology_profiles.py) | Replaced unsupported automatic thickness/stereology interpretation with explicit 2D profile measurements. |
| **3.7 Severity / reviewer agreement** | implemented with gate | Versioned ordinal forms retained; paired agreement, weighted kappa and missingness added. [Evidence](../src/ifquant_platform/imaging_evaluation.py) | Model-specific rubric and real blinded reviewers still needed; no universal score. |

## Priority 4

| Job | Status | Delivered / evidence | Remaining gate or revision rationale |
| --- | --- | --- | --- |
| **4.1 Gene/program registry** | implemented with gate | Five source-cited Niethamer mouse marker panels with exact Ensembl IDs, full coverage and timepoint/interpretation limits. [Evidence](../protocols/niethamer-lung-markers-v1.json) | Marker summaries are not validated cell-state signatures; Day 3 replay cannot establish later iCAP identity. |
| **4.2 RNA filtering / normalization** | implemented | Shared sparse panel/full-library normalization with complete observation identity, safe totals and file binding. [Evidence](../src/ifquant_platform/rna_normalization.py) | Measured-RNA summary only; no lineage, metabolic flux or deconvolution. |
| **4.3 Spatial graph and null baseline** | implemented | Bounded radius graph, explicit units/window, region/coverage-conditioned permutations and effect reports. [Evidence](../src/ifquant_platform/spatial_statistics.py) | Conditional within-specimen inference only. |
| **4.4 Reference mapping / cell2location / Tangram** | conditional | Input, leakage and baseline activation gates specified. [Evidence](ANALYSIS_WORKFLOW.md) | No compatible independent reference selected; engines not installed/executed. A small panel cannot justify deconvolution. |
| **4.5 Domain baseline / BANKSY comparison** | demonstrated | 308-feature public lung replay, expression/graph baselines and pybanksy 1.3.5 feature augmentation with lambda-zero control. [Evidence](../scripts/replay_lung_rna.py) | Fixed-k exploratory partitions; smoothness and partition agreement are not accuracy. No reference domain labels or verified independent mouse replication. |
| **4.6 Morphology–RNA association** | implemented with gate | Within-stratum biological-unit aggregation, rank effect, permutation and BH; repeated-group designs rejected. [Evidence](../src/ifquant_platform/associations.py) | Requires matched endpoints and verified independent biological units; current source replay does not provide those. |

## Priority 5

| Job | Status | Delivered / evidence | Remaining gate or revision rationale |
| --- | --- | --- | --- |
| **5.1 VALIS result adapter** | implemented with gate | Isolated VALIS 1.2.0 executor, calibrated bounded PNG reader and live level-zero point export; real public IHC pair plus controlled-transform replay. [Evidence](STITCHING_REGISTRATION.md) | Native whole-slide reader/warped-image export remains open. Public pair section relation is unknown; no cell-identity claim. |
| **5.2 Registration qualification** | implemented with gate | Separate fit/evaluation errors, local support and sampled folds; controlled public transform RMSE 5.949 micrometers across 16 points; nonrigid public pair sampled without folds. [Evidence](../validation/evidence/stitching-valis-20261011.json) | Real pair has no independent landmarks and undefined accuracy; representative deformation/edge coverage and expert landmark acceptance remain required. |
| **5.3 Processed Slide-GoTags intake** | implemented with gate | MC38-OVA author-column profile, exact IDs, observed coverage, expression/nanopore distinction and clonotype missingness. [Evidence](../src/ifquant_platform/gotags_adapter.py) | Synthetic source-profile fixture only; processed cell download requires portal sign-in. Coverage-free author calls are not promoted. |
| **5.4 Frozen spatial hypotheses** | implemented | Hashes, pairs, radii, units, seed, coverage strata, boundary policy and sensitivity are explicit inputs. [Evidence](../src/ifquant_platform/spatial_statistics.py) | No post-hoc biological hypothesis supplied by the tool. |
| **5.5 Nulls / multiplicity / uncertainty** | revised implemented | Finite-sample corrected conditioned permutations, undefined/degenerate abstention, BH and jitter ranges. [Evidence](../tests/test_analysis_pipeline.py) | Revision of author global shuffle/zero substitution; jitter range is not a confidence interval. |
| **5.6 Narrow source reproduction** | revised implemented | 240 RCC_1_A reported-statistic rows / six pairs match across supplement and figure source. [Evidence](../scripts/reconcile_gotags_source.py) | Full cell-level NMS/p-value reproduction remains gated by authenticated processed data; source tables lack coordinates/edge counts. |
| **5.7 LIANA+ / SpatialGlue / CODEX extensions** | conditional | Activation criteria and comparative evidence requirements retained in methodology roadmap. [Evidence](../notes/2026-10-09-development-roadmap.md) | No paired compatible assays/question/reference that justify these engines yet; not installed or claimed implemented. |

## Next development order

The [public development report](PUBLIC_DEVELOPMENT.md) and
[stitching/registration guide](STITCHING_REGISTRATION.md) record the completed
software and public executions. Whole-grid nuclei stitching/resume and live VALIS
registration are implemented; independent accuracy remains a separate gate.

1. Review seam disagreements and run independent annotated public nuclei comparisons;
   audit model/train overlap before comparing native, StarDist and InstanSeg.
2. Benchmark complete native-resolution slides across scanners, including memory,
   disk and recovery costs. Add label pyramids and deliberate canonical adapters;
   expand formats only with explicit coordinate/intensity semantics.
3. Extend VALIS from bounded calibrated planes to native slide readers/warped-image
   export; qualify independent real paired-slide landmarks and local deformation
   coverage. Public source-series proxies do not establish subject/cell identity.
4. Qualify a compatible scRNA reference, raw-count capacity and independent specimen
   identities before cell2location/Tangram or biological morphology/RNA effects.
5. Obtain supported authenticated Slide-GoTags cells for a frozen cell-level target;
   keep LIANA+/SpatialGlue/CODEX/UNI/HEST conditional on question and inputs.
6. Establish disease-specific severity, expert boundary acceptance and intended-use
   accuracy on representative independently annotated images.

These gaps distinguish software/public-benchmark work, source-access requirements
and independent scientific validation. Public data are development resources, not
an identity restriction. The methodology bibliography remains in the
[research roadmap](../notes/2026-10-09-development-roadmap.md).

# Development phases

> **Scope:** fluorescence governance/backend evidence. Its phase numbers are
> distinct from the current tissue/spatial development priorities. See the
> [active plan](DEVELOPMENT_PLAN.md) and [current progress](../PROGRESS.md).


IFQuant Platform advances through evidence gates rather than feature count. A
phase may prepare later infrastructure in parallel, but no artifact is promoted
into the next phase's scientific role until its exit gate is satisfied.

| Phase | Status | Objective | Required exit evidence |
| --- | --- | --- | --- |
| 0. Engineering foundation | Complete | Establish contracts, canonical packages, narrow QuPath execution, Python validation, provenance, and tests. | Structurally valid package, exact code/configuration identities, hash-bound selected runtime artifacts, and passing tests. |
| 1. Visual QC and pilot stabilization | Engineering rerun complete; formal H1 and H2 records open | Make every DAPI candidate disposition inspectable and resolve boundary-policy ambiguity. | Achieved: deterministic full-frame overlays, reconciled counts, a provisionally acceptable user view, and an independently verified symmetric four-side guard. Still required for biological eligibility: formal H1 review and an H2 geometry-warning disposition. |
| 2. Governed biological-data foundation | Initial contract complete; real intake gated | Replace synthetic fixtures with governed study inputs and user-supplied identities. | Reviewed biological annotations; complete artifact provenance; immutable annotation/correction lineage; mouse/slide/batch/scanner identities present. Detected-object H1/H2 eligibility remains a separate gate. |
| 3. Reference set and split design | Initial engineering infrastructure passing; real-data gates open | Establish reviewed instance reference data and leakage-controlled partitions. | Real frozen reference revision; human-approved source-family ledger and region completeness; image-level split manifest; declared leakage/domain audit; exact held-out IDs and reference content locked. The synthetic fixture cannot satisfy this exit gate. |
| 4. Native QuPath segmentation baseline | Engineering evaluator complete; real scoring blocked by Phase 3/H1/H2 and study-criteria gates | Quantify the native watershed method on frozen observations. | Prospectively declared detection, split/merge, boundary, count, and measurement-bias results on frozen reviewed real references. Synthetic metrics and run05 execution do not satisfy this exit gate. |
| 5. Replaceable segmentation backends | StarDist run 11 export and structural QC succeeded; scientific review/comparison open; InstanSeg not executed | Implement StarDist and InstanSeg as distinct method instances. | Exact weights/preprocessing/runtime identities, successful validated packages and reviewed QC, then frozen-observation comparisons and scope-specific backend decisions. |
| 6. Morphology/intensity classifier baselines | Planned | Establish interpretable object classifiers before deep models. | Calibrated group-aware performance, uncertainty, abstention, and endpoint-bias evidence. |
| 7. QuPath correction and iterative-learning loop | Planned | Operationalize human review without mutating frozen evidence. | Reproducible prediction/correction round trip, immutable lineage, and held-out isolation. |
| 8. Conditional custom models | Conditional | Train a scope-specific CNN only for a predeclared baseline limitation. | Reproducible model package and improvement on frozen data without unacceptable subgroup or domain degradation. |
| 9. Prospective validation and controlled release | Planned | Establish fitness for one declared intended use. | Independent domain/endpoint evidence and explicit scope-specific promotion authorization. |

## Phase advancement rule

The current phase can generate evidence autonomously. Advancement pauses when a
gate requires scientific judgment, biological identity, reviewer acceptance, or
a change in authorization. Structural validity never substitutes for those
decisions.

The Phase 1 sequence and current outcome are:

1. retain accepted and rejected candidate geometry with a deterministic reason
   — complete;
2. render DAPI overview, disposition, and review images with a hash-bound QC
   manifest — complete and byte-repeatable;
3. diagnose the `nucleus_not_covered_by_cell_geometry` population against
   unflagged controls — quantified, with H2 disposition still open;
4. obtain a provisional user view of DAPI appearance and implement
   physical-image boundary handling — complete for engineering iteration, with
   formal H1 review still open; and
5. rerun under a fresh identity after correcting detector-grid endpoint
   asymmetry — complete as run 05.

Phase 2 software work now proceeds in this order:

1. validate immutable image/channel/annotation artifact references;
2. require explicit mouse, slide, batch, and scanner identity rather than
   deriving identity from paths;
3. validate reviewed annotation revisions and parent lineage;
4. expose a read-only governed-observation validation CLI; and
5. admit real observations only after identity, annotation review, and
   correction-lineage evidence are complete; keep any associated detected
   objects ineligible until H1/H2 are resolved.

Split/fold assignment is intentionally not part of Phase 2. It begins in
Phase 3 after a governed observation set exists. Observation governance may
advance while H1/H2 remain open, but run05 detected objects cannot be promoted
into reference, training, or biological endpoint data.

## Phase 3 engineering checkpoint

The initial Phase 3 contract infrastructure now passes its synthetic fixture:

- four governed synthetic images are assigned to three explicit source
  families;
- four canonical DAPI nuclear-reference objects and one explicit ignore region
  are bound to a declared exhaustive four-region ledger;
- reference/ignore geometry uses a strict canonical 2D polygon subset, is
  contained in the closed image domain and governed ROI, has valid topology and
  edge reasons, and contains no image-wide exact duplicates. Nuclear positives
  may neither overlap nor touch any same-image ignore geometry;
- image assignments are exact: `phase3-image-001` and `phase3-image-002` are
  `train`, `phase3-image-003` is `tuning`, and `phase3-image-004` is the locked
  `held_out_test` image;
- mouse, slide, and source-family connected components are built across all
  governed images and kept within one partition. Excluded or otherwise
  unassigned images can bridge assigned partitions, while batch and scanner use
  declared leave-values-out controls;
- the held-out image-ID list and exact held-out reference content are
  canonical-hash committed. The content descriptor binds governed observation
  and biological identities, source/channel/annotation hashes, source families,
  every region-ledger entry, nuclear/ignore records, and task/evaluation/
  selection policy;
- successor policy preserves prior assignments and both held-out commitments,
  rejecting held-out truth, policy, source, or identity drift while permitting
  valid train/tuning-only evolution under policy; and
- read-only reference-set and split validators check canonical records,
  artifacts, nonempty/held-out-positive readiness, distinct adjudication,
  comprehensive chronology, lineage, exact assignment coverage, declared group
  controls, and non-claims. Every governed-observation ancestor's provenance
  code artifact, Phase 3 evaluation-policy and selection-protocol artifacts,
  and reference/split provenance code artifacts must be nonempty and
  byte-attested.

One reference object on `phase3-image-001` is a model-assisted correction with
only one reviewer. It is confined to `train`, and the reference validator
therefore reports `model_assisted_nonconfirmatory_review_count: 1` and
`confirmatory_reference_ready: false`. This deliberate negative readiness
result is part of the engineering test. A distinct adjudicator, independent
second review, or consensus is required for model-assisted confirmatory
readiness; merely repeating a reviewer as adjudicator is rejected.

The fixture identities are reference set
`f0137f493ef2cecede86f933729d12ac169a528608bfc69b96d82e457f0fb935`,
split manifest
`43c32b9c947257b79bd00ae59b09adf64883e0b7554606aaa700b2e6a0d3b47d`,
held-out ID list
`44f3c019439012f5f0136129747a02e98a83354a84e42120f565cd9cdaa70f67`,
and `ifquant_held_out_reference_content_v1` content
`a16120a41f7bf114a4c1608cca05757c09a119f50d290abd5e09861645a25900`.
The current full run discovers 108 tests: 107 pass and one optional JSON-Schema
test is skipped when `jsonschema` is absent. The focused Phase 3 run discovers
37 tests: 36 pass with the same optional skip; the standard-library validation
path passes.

Chronology traverses the current governed-observation-set revision and every
validated ancestor. A direct parent's `provenance.created_at` must be no later
than its child's, and all timestamps bound through every revision—observation,
image/channel/annotation provenance, acquisition when present, and annotation/
identity reviews—must be no later than the reference freeze. Reference
provenance and region/object/ignore reviews are bound to the same freeze. Parent
reference and split revisions must be frozen before successor creation, and the
current reference must be frozen before split creation. Only the initial split
requires that reference freeze to predate the original held-out commitment.
Later reference successors may freeze after the preserved commitment when
held-out content is unchanged, which permits honest train/tuning-only evolution
without reopening held-out truth.

## Phase 3 exit sequence for real data

The next work proceeds in this order:

1. admit real governed observations with reviewed ROI and correction lineage;
2. define source families explicitly, obtain human study approval for that
   ledger, and review exhaustive nuclear-instance and ignore-region coverage
   without inheriting a detector boundary rule;
3. independently review or adjudicate any model-assisted labels intended for
   tuning or confirmatory evaluation;
4. approve the study-specific hard grouping and batch/scanner domain-control
   design;
5. freeze exact image-level train/tuning/held-out assignments and both held-out
   identity/content commitments; and
6. predeclare the native-QuPath evaluation metrics and acceptance thresholds
   before beginning Phase 4 evaluation.

Passing the synthetic contracts does not prove real reference correctness,
discover every hidden related source, establish split optimality or population
representativeness, close H1/H2, or authorize scientific use. Schema checks do
not replace the runtime's cross-record invariants, and v1 prediction-exposure
hashes are asserted identities rather than local byte-attestation. The fixture
is not scientific validation, backend equivalence, model-universality evidence,
or proof that hidden leakage is absent.

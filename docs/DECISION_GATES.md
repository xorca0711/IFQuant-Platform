# Decision gates

> **Platform scope:** these historical fluorescence gates remain applicable to canonical cell backends. H&E, RNA, registration and TME gates are now listed per job in [the current register](DEVELOPMENT_PLAN.md); independent branches need not wait for omics or fluorescence model promotion.

Decision gates distinguish machine-verifiable engineering facts from human
review and scientific promotion. A downstream stage may reject evidence; it may
not reinterpret an absent review as approval.

## Gate register

| Gate | Owner | Current pilot state | Advancement condition |
| --- | --- | --- | --- |
| E0. Source and historical boundary | Python/pipeline | Engineering pass; original source remained read-only. Compound VSI companions are not fully attested. | Bind every consumed source artifact for biological work. |
| E1. Configuration and runtime identity | Groovy + Python | Pass. Script, configuration, method, selected QuPath launcher/core/detector artifacts, and declared environment are hash-bound. This is not a complete Java-classpath or OS attestation. | Continue to fail closed on identity drift and extend runtime coverage before controlled release. |
| E2. Image and channel eligibility | Groovy | Pass for the engineering derivative: fluorescence, singleton Z/T, calibrated UINT16, DAPI mapped. | Repeat against each governed acquisition domain. |
| E3. Annotation eligibility | QuPath + Groovy | Pass as a synthetic fixture only. | Use a reviewed biological annotation version with reviewer lineage. |
| E4. Detector execution | QuPath | Pass: 1,803 native watershed candidates on the complete 2048 × 2048 image. | Preserve complete success/failure and candidate ledgers. |
| E5. Candidate disposition | Groovy + Python | Pass: all 1,803 candidates are retained; 1,700 accepted and 103 excluded within a declared symmetric one-processing-pixel image guard. Independent side counts are top 33, left 23, right 27, bottom 21, with zero accepted guard members. | Continue retaining and reconciling every candidate geometry, guard membership, and reason. |
| E6. Canonical package integrity | Python | Pass for structural, referential, and byte integrity. | Maintain exact hashes, IDs, measurements, counts, QC, and review reconciliation. |
| H1. Visual DAPI detection review | Human reviewer | The user accepted the full-image boundary exclusions as sufficient for the engineering pilot, but the broader detection review has no formal reviewer identity/date/rationale record. This is not a sensitivity/specificity result. | Record the detection review formally, then repeat against governed acquisition domains and reviewed reference objects. |
| H2. Geometry-warning policy | Human reviewer + method owner | Open: 194 accepted objects carry `nucleus_not_covered_by_cell_geometry`; median outside fraction is 0.0410%, maximum 1.6491%. | Confirm exclude, accept under a precise rule, or change the method and rerun. |
| D1. Governed-observation eligibility | Python governance | Initial contract and validator complete; the pilot observation is ineligible because mouse/slide/batch/scanner identities are absent and its annotation is synthetic rather than biologically reviewed. Run05 detected objects are separately ineligible while H1/H2 remain open. | Complete user-supplied identities, reviewed annotations, and immutable correction lineage. Resolve H1/H2 before promoting detected objects. Split assignment remains a separate Phase 3 gate. |
| R1. Nuclear-reference contract integrity | Python governance | Engineering pass on a synthetic fixture: four images, four canonical DAPI nuclear objects, one explicit ignore region, three source families, strict geometry/containment/edge/non-overlap checks, nonempty and per-image readiness checks, distinct adjudication, comprehensive chronology, byte-attested policy/code artifacts, and declared region/count reconciliation. The one model-assisted nonconfirmatory object makes `confirmatory_reference_ready` false. | Keep these checks fail-closed; passing R1 does not satisfy real reference review. |
| R2. Real reference completeness and review | Human reviewers + validation owner | Open. No real reviewed nuclear-reference revision exists. | Review exhaustive real regions, explicit ignores, prediction exposure, correction lineage, and adjudication; freeze a successor rather than mutate a reference revision. |
| D2. Split-manifest structural integrity | Python governance | Engineering pass on the synthetic fixture: exact image-level 2/1/1 assignments, zero declared hard-group overlaps after building components across all governed images, declared batch/scanner leave-values-out controls, and locked IDs plus exact reference content for `phase3-image-004`. | Preserve exact assignments and both commitment hashes in successor validation. This does not prove all relatedness is known. |
| D3. Real split and held-out commitment | Study owner + validation owner | Open. The synthetic split is not a real held-out cohort, leakage proof, or adequacy result. | Human-approve real source families and domain controls; assign whole images; audit mouse/slide/source-family connected groups; lock exact held-out IDs and reference content before model evaluation. |
| S0. Segmentation-evaluation integrity | Python governance | Engineering pass: frozen plan and raster ledgers are hash-bound; reference pixels must independently equal frozen Phase 3 WKT rasterization; deterministic IoU matching, split/merge, boundary, strata, count, and measurement-bias reporting pass a synthetic fixture. | Preserve these checks on real evidence; synthetic scores are not native-QuPath performance. |
| S1. Segmentation performance | Validation owner | Not evaluated on real references. Run05 is execution/QC evidence only. | Approve prospective numeric criteria, then meet detection, split/merge, boundary, strata, count, and bias criteria on the frozen real reference/split. |
| P5-E1. StarDist runtime identity | Groovy + Python | Engineering pass through identity preflight and inference: QuPath, extension JAR, model descriptor, weights, preprocessing, parameters, and exporter bytes are separately hash-bound. | Preserve these identities in a successful fresh package; an inference start is not an export pass. |
| P5-E2. StarDist canonical export | Groovy + Python | Open. Runs 06-09 are preserved diagnostic/failed attempts. Exact intensity keys are bound; a deterministic QC-only geometry repair is staged but not runtime-verified. | Create a new run identity, complete export, validate the package and candidate ledger, and reproduce deterministic QC without overwriting prior evidence. |
| P5-H1. StarDist visual review | Human reviewer | Pending successful P5-E2 output. | Review DAPI detections, exclusions, topology-warning populations, and matched controls; record reviewer, date, and rationale. |
| P5-S1. Backend comparison | Validation + scientific owners | Blocked by real R2/D3/S1 evidence. No backend equivalence or selection exists. | Compare each method separately on the same frozen real references under prospective criteria and authorize only a declared scope. |
| M1. Model or endpoint promotion | Scientific owner | Authorization `none`. | Independent scope-specific validation and explicit promotion decision. |

## Geometry-warning confirmation

The 194 accepted geometry warnings are evidence, not an automatic accept or reject
decision. Phase 1 must not silently delete the objects or relabel them as pass.

The reviewer must choose one of these outcomes after inspecting raw DAPI,
nucleus outlines, cell outlines, spatial context, and matched unflagged controls:

1. **Exclude conservatively** — remove all flagged objects from eligible
   downstream use while retaining them in the immutable QC ledger.
2. **Accept under a declared rule** — only when the observed topology is
   demonstrably expected and the rule is precise enough to test automatically.
3. **Revise and rerun** — change detector parameters, cell expansion, geometry
   handling, or exporter logic; create a new method/run identity and compare it
   to the preserved pilot.

The conservative default is outcome 1 until review supports outcome 2 or a new
run resolves the condition. Phase 2 observation governance may proceed, but
confirmation is required before any run05 detected object becomes eligible for
reference labels, biological object datasets, classifier inputs, or endpoint
aggregation because the choice can change downstream morphology/intensity bias.

The current evidence and local-output layout are summarized in
[`validation/PHASE1_QC_STATUS.md`](../validation/PHASE1_QC_STATUS.md).

## Phase 3 deterministic checks

The Phase 3 validators use bounded, backend-neutral engineering algorithms:

1. Canonical JSON SHA-256 identities bind each nuclear object to its reference
   set, image, include annotation, DAPI target, and normalized polygon geometry.
   Ignore-region identities also bind the controlled reason.
2. Geometry accepts a narrow fail-closed 2D polygon subset. It canonicalizes
   orientation, start vertices, holes, and true multipolygon members; rejects
   repeated/zero-length/collinear vertices, zero area, self-intersection,
   invalid hole/member topology and one-member multipolygons. Exact nuclear and
   ignore duplicates are rejected image-wide rather than only within an
   annotation. It requires containment in the closed image domain
   `[0, width] x [0, height]` and the governed inclusion ROI.
3. `physical_image_edge` ignores must intersect the physical image boundary.
   `physical_specimen_edge` is checked against the governed ROI boundary because
   v1 has no separate specimen-boundary artifact. Nuclear reference geometry
   may neither overlap nor touch any same-image ignore geometry, keeping every
   positive scoreable after ignore removal.
4. Artifact checks require canonical NDJSON ordering, exact byte size, SHA-256,
   record schema, record count, and cross-document identities.
5. The ledger declares the reviewed region scope and reconciles every included
   region's reference and ignore counts. Exclusions require explicit controlled
   reasons; detector guard rules are not inherited as reference truth. The set
   must contain a positive nuclear reference, and each held-out image must have
   a positive reference and confirmatory readiness. A human reviewer still
   decides whether the declared scope is genuinely complete.
6. Review checking requires a decision adjudicator to be distinct from all
   listed reviewers. A model-assisted object without an independent second
   review, consensus, or distinct adjudicator contributes to
   `model_assisted_nonconfirmatory_review_count`, prevents set-level
   confirmatory readiness, and makes its image ineligible for held-out test.
7. Split checking assigns whole images. It forms connected components across
   any shared `mouse_id`, `slide_id`, or `source_family_id` using every governed
   image, including excluded or otherwise unassigned images that can
   transitively bridge assigned partitions, and rejects a component that
   crosses `train`, `tuning`, and `held_out_test`.
8. Batch and scanner controls are explicit per manifest: either values are
   partition-disjoint or named values occur only in `held_out_test`. The
   synthetic fixture uses leave-values-out for both.
9. One held-out commitment hashes the exact ascending image-ID list. A second,
   under `ifquant_held_out_reference_content_v1`, hashes the task, evaluation
   policy, selection protocol, and for every held-out image its complete
   governed observation record (including biological identity and source/
   channel/annotation hashes), source family, all region-ledger entries,
   nuclear objects, and ignore regions.
10. Successors must preserve prior assignments and both locks, so held-out
    truth, policy, source, annotation, biological-identity, and source-family
    drift is rejected. Valid train/tuning-only evolution is allowed under the
    declared policy; newly admitted images cannot enter held-out test.
11. Chronology traverses every governed-observation-set revision in the
    validated parent chain. Each direct parent's `provenance.created_at` must
    not follow its child's, and all ancestor-bound observation/image/channel/
    annotation provenance, acquisition times when present, and annotation/
    identity reviews must not follow the reference freeze. Reference provenance
    and every region/object/ignore review are bound to that freeze too. Parent
    reference/split freezes must not follow successor creation, and the current
    reference freeze must not follow split creation.
12. Only an initial split requires its reference freeze not to follow the
    original held-out commitment. A later reference successor may freeze after
    that preserved commitment when held-out content is unchanged, allowing
    honest train/tuning-only evolution. The commitment and split creation still
    must not follow the split freeze.
13. Provenance code artifacts for every governed-observation revision in the
    parent chain, the Phase 3 evaluation-policy and selection-protocol
    artifacts, and reference/split provenance code artifacts must be nonempty;
    their exact local bytes are verified against declared size and SHA-256.

These checks expose declared overlap and contract drift. They cannot discover
an unrecorded relationship, determine whether a split has enough statistical
power, or establish that labels are biologically correct. Real source-family
approval is a human study gate. Prediction-exposure hashes remain asserted
identities, not locally byte-attested artifacts, in v1. JSON Schema alone does
not enforce all of these cross-record runtime invariants.

## Non-gates in the current validator

`status: valid` does not independently establish DAPI detection accuracy,
recompute intensity from pixels, recompute every measurement from geometry,
prove label correctness, prove absence of hidden leakage, establish split
optimality or population representativeness, prove backend equivalence, verify
endpoint fitness, establish model universality, or authorize model use. The
synthetic fixture is engineering evidence, not scientific validation or proof
of leakage absence. Those checks become explicit gates in later phases.

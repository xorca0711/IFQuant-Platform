# Decision gates

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
| H1. Visual DAPI detection review | Human reviewer | Provisional only: the user described the engineering overlay as seemingly acceptable, but no reviewer identity/date/rationale record has been captured. This is not a sensitivity/specificity result. | Record the review formally, then repeat against governed acquisition domains and reviewed reference objects. |
| H2. Geometry-warning policy | Human reviewer + method owner | Open: 194 accepted objects carry `nucleus_not_covered_by_cell_geometry`; median outside fraction is 0.0410%, maximum 1.6491%. | Confirm exclude, accept under a precise rule, or change the method and rerun. |
| D1. Governed-observation eligibility | Python governance | Initial contract and validator complete; the pilot observation is ineligible because mouse/slide/batch/scanner identities are absent and its annotation is synthetic rather than biologically reviewed. Run05 detected objects are separately ineligible while H1/H2 remain open. | Complete user-supplied identities, reviewed annotations, and immutable correction lineage. Resolve H1/H2 before promoting detected objects. Split assignment remains a separate Phase 3 gate. |
| S1. Segmentation performance | Validation owner | Not evaluated. | Meet prospective detection/boundary/count/bias criteria on frozen reference data. |
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

## Non-gates in the current validator

`status: valid` does not independently establish DAPI detection accuracy,
recompute intensity from pixels, recompute every measurement from geometry,
prove backend equivalence, verify endpoint fitness, or authorize model use.
Those checks become explicit gates in later phases.

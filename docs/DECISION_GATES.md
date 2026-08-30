# Decision gates

Decision gates distinguish machine-verifiable engineering facts from human
review and scientific promotion. A downstream stage may reject evidence; it may
not reinterpret an absent review as approval.

## Gate register

| Gate | Owner | Current pilot state | Advancement condition |
| --- | --- | --- | --- |
| E0. Source and historical boundary | Python/pipeline | Engineering pass; original source remained read-only. Compound VSI companions are not fully attested. | Bind every consumed source artifact for biological work. |
| E1. Configuration and runtime identity | Groovy + Python | Pass. Script, configuration, method, QuPath runtime, and detector implementation are hash-bound. | Continue to fail closed on identity drift. |
| E2. Image and channel eligibility | Groovy | Pass for the engineering derivative: fluorescence, singleton Z/T, calibrated UINT16, DAPI mapped. | Repeat against each governed acquisition domain. |
| E3. Annotation eligibility | QuPath + Groovy | Pass as a synthetic fixture only. | Use a reviewed biological annotation version with reviewer lineage. |
| E4. Detector execution | QuPath | Pass: 1,551 native watershed candidates. | Preserve complete success/failure and candidate ledgers. |
| E5. Candidate disposition | Groovy | 1,453 accepted; 45 cell-not-covered; 53 boundary-touching. | Reconcile every candidate geometry and reason in QC evidence. |
| E6. Canonical package integrity | Python | Pass for structural, referential, and byte integrity. | Maintain exact hashes, IDs, measurements, counts, QC, and review reconciliation. |
| H1. Visual DAPI detection review | Human reviewer | Not performed; no rendered overlay existed in the initial pilot. | Review deterministic overview and zoom evidence against raw DAPI. |
| H2. Geometry-warning policy | Human reviewer + method owner | Open: 182 accepted objects carry `nucleus_not_covered_by_cell_geometry`. | Confirm exclude, accept under a precise rule, or change the method and rerun. |
| D1. Dataset and split eligibility | Python governance | Not eligible; acquisition-group identities are absent and objects are unreviewed. | Complete identities, immutable review/correction lineage, and leakage-safe split manifest. |
| S1. Segmentation performance | Validation owner | Not evaluated. | Meet prospective detection/boundary/count/bias criteria on frozen reference data. |
| M1. Model or endpoint promotion | Scientific owner | Authorization `none`. | Independent scope-specific validation and explicit promotion decision. |

## Geometry-warning confirmation

The 182 geometry warnings are evidence, not an automatic accept or reject
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
run resolves the condition. Confirmation is required before Phase 2 begins,
because the choice changes dataset eligibility and potentially downstream
morphology/intensity bias.

## Non-gates in the current validator

`status: valid` does not independently establish DAPI detection accuracy,
recompute intensity from pixels, recompute every measurement from geometry,
prove backend equivalence, verify endpoint fitness, or authorize model use.
Those checks become explicit gates in later phases.

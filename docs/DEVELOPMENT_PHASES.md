# Development phases

IFQuant Platform advances through evidence gates rather than feature count. A
phase may prepare later infrastructure in parallel, but no artifact is promoted
into the next phase's scientific role until its exit gate is satisfied.

| Phase | Status | Objective | Required exit evidence |
| --- | --- | --- | --- |
| 0. Engineering foundation | Complete | Establish contracts, canonical packages, narrow QuPath execution, Python validation, provenance, and tests. | Structurally valid package, exact code/runtime/configuration identities, and passing tests. |
| 1. Visual QC and pilot stabilization | Human review pending | Make every DAPI candidate disposition inspectable and resolve geometry-policy ambiguity. | Deterministic overlays and review montage; all candidate counts reconcile; a reviewer confirms the geometry-warning disposition policy. |
| 2. Governed biological-data foundation | Blocked by Phase 1 review | Replace synthetic fixtures with governed study inputs and identities. | Reviewed biological annotations; complete artifact provenance; immutable correction lineage; mouse/slide/batch/scanner identities present. |
| 3. Reference set and split design | Planned | Establish reviewed instance reference data and leakage-safe partitions. | Frozen reference version; group-disjoint split manifest; leakage audit; held-out set locked. |
| 4. Native QuPath segmentation baseline | Planned | Quantify the native watershed method on frozen observations. | Prospectively declared detection, split/merge, boundary, count, and measurement-bias results. |
| 5. Replaceable segmentation backends | Planned | Implement StarDist and InstanSeg as distinct method instances. | Exact weights/preprocessing/runtime identities and frozen-observation comparisons; scope-specific backend decisions. |
| 6. Morphology/intensity classifier baselines | Planned | Establish interpretable object classifiers before deep models. | Calibrated group-aware performance, uncertainty, abstention, and endpoint-bias evidence. |
| 7. QuPath correction and iterative-learning loop | Planned | Operationalize human review without mutating frozen evidence. | Reproducible prediction/correction round trip, immutable lineage, and held-out isolation. |
| 8. Conditional custom models | Conditional | Train a scope-specific CNN only for a predeclared baseline limitation. | Reproducible model package and improvement on frozen data without unacceptable subgroup or domain degradation. |
| 9. Prospective validation and controlled release | Planned | Establish fitness for one declared intended use. | Independent domain/endpoint evidence and explicit scope-specific promotion authorization. |

## Phase advancement rule

The current phase can generate evidence autonomously. Advancement pauses when a
gate requires scientific judgment, biological identity, reviewer acceptance, or
a change in authorization. Structural validity never substitutes for those
decisions.

The immediate Phase 1 sequence is:

1. retain accepted and rejected candidate geometry with a deterministic reason;
2. render DAPI overview, disposition, and review images with a hash-bound QC
   manifest;
3. diagnose the `nucleus_not_covered_by_cell_geometry` population against
   unflagged controls;
4. record a reviewer decision without rewriting the original package; and
5. rerun if the detector, geometry policy, or exporter must change.

Phase 2 may begin only after step 4 or 5 closes the warning-policy gate.

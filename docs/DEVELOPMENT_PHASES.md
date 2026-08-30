# Development phases

IFQuant Platform advances through evidence gates rather than feature count. A
phase may prepare later infrastructure in parallel, but no artifact is promoted
into the next phase's scientific role until its exit gate is satisfied.

| Phase | Status | Objective | Required exit evidence |
| --- | --- | --- | --- |
| 0. Engineering foundation | Complete | Establish contracts, canonical packages, narrow QuPath execution, Python validation, provenance, and tests. | Structurally valid package, exact code/configuration identities, hash-bound selected runtime artifacts, and passing tests. |
| 1. Visual QC and pilot stabilization | Engineering rerun complete; formal H1 and H2 records open | Make every DAPI candidate disposition inspectable and resolve boundary-policy ambiguity. | Achieved: deterministic full-frame overlays, reconciled counts, a provisionally acceptable user view, and an independently verified symmetric four-side guard. Still required for biological eligibility: formal H1 review and an H2 geometry-warning disposition. |
| 2. Governed biological-data foundation | Initial contract complete; real intake gated | Replace synthetic fixtures with governed study inputs and user-supplied identities. | Reviewed biological annotations; complete artifact provenance; immutable annotation/correction lineage; mouse/slide/batch/scanner identities present. Detected-object H1/H2 eligibility remains a separate gate. |
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

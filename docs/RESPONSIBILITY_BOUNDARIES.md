# Responsibility boundaries

Clear ownership prevents executable code from becoming hidden scientific
authority. Every new feature should have one primary owner and an explicit
artifact at each boundary.

| Area | Owns | Must not own |
|---|---|---|
| `contracts/` | Field meaning, units, identities, canonical forms, closed schemas, method bindings | Runtime paths, QuPath UI state, training loops, release approval |
| QuPath UI | Viewing, annotation, correction, object and prediction review | Dataset versioning, split assignment, statistical aggregation |
| `qupath/scripts/` | Configured annotation-scoped execution, feature calculation, deterministic export | Hard-coded study paths, model training, hidden endpoint algebra, promotion decisions |
| `src/ifquant_platform/` | Validation, canonicalization, hashing, provenance, QC/review rules, dataset and analytical governance | Interactive annotation editing, backend-specific UI behavior |
| Segmentation adapters | Translate one interface into native QuPath, StarDist, or InstanSeg execution | Claims of equivalence, cross-scope promotion, silent fallback to another backend |
| `ml/` | Training, inference packaging, evaluation, model/preprocessing manifests | Groovy execution control, unversioned datasets, universal-model claims |
| `datasets/` | Immutable manifests, annotation/correction lineage, group-aware splits | Model code, mutable labels without ancestry, random tile leakage |
| `validation/` | Fixtures, integrity checks, performance/bias/calibration/domain-shift evidence | Scientific promotion by implication, post hoc acceptance criteria |
| `pipelines/` | Reproducible orchestration and artifact hand-off | Duplicated contract constants, repairing invalid upstream data |
| `compat/g_surf/` | Frozen compatibility descriptors and regression adapters | Historical authority, release outputs, production pipeline copies, new-core dependencies |

## Boundary invariants

### Meaning versus execution

Semantic choices are versioned in contracts. Effective runtime configuration
and exact code, application, extension, model, and output hashes are recorded in
an execution attestation. One must not be substituted for the other.

### Configuration versus code

Paths, channel bindings, annotation IDs, backend selection, requested features,
and output destinations arrive through validated configuration. Groovy and
Python may reject missing values; they must not silently replace them with
workstation- or cohort-specific defaults.

### Interface versus equivalence

All segmentation backends return the same package shape and status vocabulary.
That gives downstream code a stable interface. It does not make cell boundaries,
counts, measurements, or biological endpoints interchangeable.

### Object evidence versus downstream summaries

Canonical objects, geometries, compartment measurements, calibration, and
provenance precede classification and aggregation. Downstream summaries retain
the identities and method instance from which they were derived.

### Human review versus source labels

QuPath is the review surface. A correction creates a new annotation/object
revision linked to its parent; it never rewrites prior training or validation
labels in place. Reviewer identity and state are provenance, while the accepted
label revision is a versioned dataset input.

### Dataset grouping versus convenience

Python assigns train, validation, and test membership using biological and
acquisition groups. Tiles from the same mouse, slide, batch, or scanner may not
leak across partitions merely because tile-level randomization is convenient.

## Change discipline

- Extend a contract by versioning it; do not reinterpret an existing field.
- Bind exact model weights and preprocessing to each method instance.
- Fail closed on unknown channels, calibration, identities, hashes, or review
  states.
- Preserve failed and abstained units in ledgers rather than dropping them.
- Predeclare validation scope and acceptance criteria before confirmatory use.
- Keep historical compatibility isolated and optional; the core package must run
  without the G-SURF repository.

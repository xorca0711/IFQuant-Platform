# Machine-learning roadmap

## Direction

The first ML task is DAPI-based instance segmentation. The roadmap favors
measurable, scope-specific components over one universal CNN. Morphology and
compartment-intensity object-classifier baselines come before a custom deep
classifier so that added complexity must demonstrate a defined benefit.

Training and evaluation run in Python. QuPath remains the environment for image
inspection, human correction, and prediction review; Groovy does not contain a
training loop.

The phase numbering below follows
[`DEVELOPMENT_PHASES.md`](DEVELOPMENT_PHASES.md); it is not a separate ML-only
sequence.

## Phase 2 — governed biological-data foundation

- Register source images, biological units, channels, calibration, annotations,
  and acquisition domains with content hashes.
- Define canonical cell/nucleus geometry and compartment-feature contracts.
- Establish immutable correction lineage and reviewer states.
- Record mouse, slide, batch, scanner, and other study-specific grouping keys.

## Phase 3 — reference set and split design

- Establish reviewed DAPI instance annotations with explicit reviewer lineage.
- Freeze train, tuning, and held-out test manifests before model comparison.
- Keep mouse, slide, batch, and scanner groups disjoint as the study design
  requires; never assign randomly by tile.
- Run a leakage audit and lock the held-out set before baseline evaluation.

## Phase 4 — native QuPath DAPI baseline

- Run native QuPath watershed with explicit preprocessing, configuration,
  software, and detector identities.
- Evaluate detection, split/merge, boundary, size-stratified, crowded-region,
  count, and downstream measurement behavior against reviewed annotations.
- Preserve per-object matches and signed errors, not only headline overlap
  scores.

## Phase 5 — replaceable segmentation candidates

- StarDist currently has an identity-bound engineering adapter. Runtime
  preflight and inference have executed; canonical export is paused at a
  fail-closed QC geometry calculation, with a deterministic QC-only repair
  staged for a fresh run. InstanSeg has not started.
- Complete and review a valid StarDist package before implementing InstanSeg
  behind the same output interface.
- Bind exact preprocessing, configuration, software, model descriptor, and
  weights identities for every method instance.
- Compare each method separately on the frozen Phase 3 observations and splits.

These backends are candidates, not interchangeable implementations. Their
results remain separate method instances.

## Phase 6 — object-classifier baselines

Build interpretable baselines from verified morphology and compartment-intensity
features. Establish data quality, endpoint association, calibration, and useful
abstention behavior before training a custom CNN. Comparisons use the same
frozen partitions and report uncertainty and subgroup behavior.

## Phase 7 — QuPath correction loop

Expose predictions and uncertainty in QuPath. Human reviewers accept, reject,
split, merge, redraw, or relabel objects. Every correction creates a new version
linked to the source prediction, original annotation, reviewer action, and model
instance. Corrections enter a later dataset version; they do not mutate the
held-out set or silently feed the run that requested them.

## Phase 8 — scope-specific custom models

Train a custom CNN only when a predeclared limitation of simpler baselines
justifies it. A model package must include:

- task and intended-use scope;
- required channels, calibration, and preprocessing;
- training dataset and split-manifest hashes;
- architecture, code, environment, and weights hashes;
- tuning decisions and acceptance criteria;
- calibration and abstention policy;
- scanner, batch, staining, and specimen limitations; and
- evaluation evidence plus known failure modes.

A new scope, acquisition domain, or material preprocessing change requires a new
method instance and renewed evaluation. Success in one domain is not evidence of
universality.

## Phase 9 — prospective validation and controlled release

Partition at the highest leakage-relevant unit. A tile is never the random split
unit. At minimum, evaluate group-disjoint behavior by mouse, slide, batch, and
scanner; when complete separation across all factors is impossible, document the
constraint and use blocked or leave-one-group/domain-out analyses.

Evaluation covers:

- segmentation accuracy and object-count/geometry error;
- bias propagated into morphology, intensity, and declared endpoints;
- score and probability calibration;
- coverage and error under abstention;
- scanner, batch, staining, and specimen domain shift;
- robustness to weak signal, crowding, artifacts, and annotation boundaries;
- subgroup uncertainty and failed-unit accounting; and
- reproducibility from immutable inputs and exact model packages.

Acceptance criteria are prospective and scope-specific. Engineering performance
does not itself establish scientific validity or biological ground truth.

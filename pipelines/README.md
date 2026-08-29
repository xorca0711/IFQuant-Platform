# Pipeline orchestration

`pipelines/` composes versioned contracts, QuPath executors, Python validation,
dataset operations, model workflows, and aggregation. A pipeline coordinates
owners; it does not become a second source of scientific definitions.

A typical flow is:

1. register image, biological identity, channel map, and calibration;
2. bind supplied QuPath annotations and a validated execution configuration;
3. invoke one segmentation backend through the narrow Groovy executor;
4. validate and canonicalize the exported cell-object package in Python;
5. publish reviewed objects or corrections into a versioned dataset;
6. train or evaluate a scope-specific model outside Groovy; and
7. aggregate only compatible packages that pass declared QC and review rules.

Pipeline configuration provides paths, artifact roles, backend selection,
method/model identity, feature requests, and output destinations. Scripts must
not contain workstation-specific paths or silently select channels, thresholds,
annotations, models, or cohorts.

Each run writes to a fresh destination and records exact input, code,
configuration, model, and output hashes plus assigned/succeeded/failed ledgers.
Resume behavior must verify content and completeness; file existence alone is
not evidence of a valid completed stage.

An invalid upstream artifact is rejected rather than repaired downstream.
Pipelines may not infer missing identity, fabricate zero measurements, suppress
failed units, or mix method instances to create an apparently homogeneous
result.

This layout is intentionally independent of the historical G-SURF production
stages. Compatibility adapters remain optional and isolated under
`compat/g_surf/`.

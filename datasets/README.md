# Dataset governance

`datasets/` governs identities and manifests; it is not an untracked dump of
images or labels. Large artifacts may live in an external content-addressed
store, but a versioned manifest must make every consumed byte and relationship
resolvable.

Phase 2 begins with a governed observation-set revision. It records:

- source-image ID, content hash, dimensions, and acquisition identity;
- reviewed mouse/specimen/slide/section identity and biological-unit ID;
- scanner and acquisition-batch identity declared by the image manifest;
- semantic channel mapping and pixel/Z calibration;
- annotation and correction revision with parent lineage and review state;
- byte-bound producer-code provenance and the declared reviewed identity source;
- explicit non-claims for scientific validation, biological ground truth, and
  downstream authorization.

It does **not** assign train, tuning, validation, test, folds, or tiles. Those
memberships belong to a separately versioned Phase 3 split manifest after the
observations and grouping identities are governed.

## Phase 3 split policy

Never assign partitions randomly by tile. Split manifests must prevent leakage
through mouse, slide, batch, and scanner. The precise strategy is study-specific,
but group-disjoint, blocked, or leave-one-domain-out designs are preferred. A
manifest records the grouping keys, algorithm, seed when applicable, constraints,
and resulting memberships so a split can be reproduced and audited.

Tiles and cells inherit the partition of their containing biological/acquisition
group. Corrections to test data do not silently move into training data. If a
rare stratum makes complete separation impossible, document the compromise and
keep the affected evaluation exploratory.

## Version discipline

Images, annotations, splits, model inputs, and corrections are immutable once
published as a dataset version. A change creates a successor manifest with
parent linkage and a reason. Missing identities are errors, not values to infer
from folder names.

Historical G-SURF authority and release outputs are not copied here. Any frozen
compatibility fixture must be separately documented under `compat/g_surf/` and
must not become training truth by implication.

# Architecture

## Status and intent

This is a clean-slate target architecture for engineering development. It does
not import G-SURF scientific authority, recreate the historical production
pipeline, or promote any detector, endpoint, or model.

The central rule is separation of meaning from execution:

1. backend-neutral contracts describe identities, required inputs, semantic
   measurements, and expected evidence;
2. a QuPath backend performs a configured operation and records what ran;
3. a deterministic canonical package carries cell objects and provenance; and
4. Python validates the package and governs all downstream use.

## System layers

### Contract layer

Contracts define stable field meaning, units, coordinate systems, required
identities, canonical serialization, and validation constraints. Scientific or
numerical choices belong here rather than being duplicated in Groovy or model
code. Runtime details, paths, application versions, logs, and output locations
belong in execution attestations instead.

Contract artifacts are closed and versioned. Their canonical form is hashed;
raw-file hashes remain available separately for byte provenance. A change to a
semantic field creates a new contract or method instance rather than silently
changing the meaning of an existing identifier.

The first contract family keeps four identities distinct:

1. a backend-neutral measurement definition describes semantic inputs,
   feature meaning, compartments, units, missingness, and aggregation;
2. a separate parameter set binds every declared parameter slot to an explicit
   applicability scope;
3. a domain-separated method-instance hash binds the canonical identities of
   those two artifacts; and
4. the segmentation run and execution attestation record acquisition channels,
   detector/backend, model weights, preprocessing, scripts, runtime, and paths.

Contract validity and method identity are engineering facts. Authorization,
biological validity, backend comparison, and scientific promotion remain
separate decisions and evidence.

### QuPath execution layer

QuPath is the primary human and image-computation environment. Users view
images, create or review annotations, run cell segmentation, inspect morphology
and intensity measurements, correct objects, and review predictions there.

Groovy scripts are deliberately narrow. They accept configuration and supplied
annotations, invoke one selected backend, calculate requested object features,
and export a deterministic intermediate package plus execution evidence. They
do not own model training, dataset splits, statistical aggregation, endpoint
promotion, or hidden defaults tied to one workstation.

### Python governance layer

The `ifquant_platform` package owns:

- schema loading, canonicalization, and content hashing;
- channel, calibration, coordinate-frame, and identity validation;
- canonical cell-object verification and deterministic normalization;
- detector/model, configuration, and artifact provenance;
- dataset versioning, correction lineage, and group-aware splits;
- model training/evaluation orchestration;
- QC, review-state, aggregation, and statistical rules; and
- the validation CLI.

Producer-reported summaries are evidence, not unquestioned analytical input.
Python recomputes derivable values where possible and refuses incomplete,
ambiguous, duplicated, stale, or hash-inconsistent packages.

## Canonical cell-object package

A package represents a configured observation and its detected objects. At a
minimum it binds the following domains.

### Observation identity

- stable image and acquisition identifiers;
- biological-unit hierarchy needed by the study, such as animal, specimen,
  slide, section, field, and supplied annotation;
- annotation/reference-space identity and content hash; and
- observation, package, and method-instance identifiers.

Blank identifiers are not inferred from filenames. Optional biological levels
remain explicitly absent rather than being fabricated.

### Image semantics

- source-image content identity;
- semantic channel roles mapped to acquisition channels;
- pixel width, height, units, Z spacing when applicable, and dimensional policy;
- coordinate-frame origin, axis order, and geometry units; and
- preprocessing identity and parameters.

### Object geometry and measurements

- stable object ID within the package;
- cell and nucleus geometry with a canonical representation or content hash;
- centroid, area, perimeter, and other declared morphology features;
- compartment-specific intensity statistics for nucleus, cytoplasm, whole cell,
  or other explicitly defined compartments; and
- units, feature-definition identifiers, completeness requirements, and
  evaluability. Canonical v1 rejects the package when a required feature is
  unavailable rather than silently emitting a partial object.

Derived fractions or classifier scores never replace the additive or primitive
evidence needed to verify them.

### Method and execution identity

- segmentation interface and backend identity;
- detector configuration and canonical hash;
- exact model and weights hashes when applicable;
- preprocessing and feature-definition hashes;
- QuPath, extension, script, and runtime versions/hashes; and
- assigned, succeeded, failed, and reviewed observation/object ledgers.

### QC, review, and provenance

- machine QC flags and reasons;
- human review state, reviewer action, and correction lineage;
- immutable input and output artifact roles with content hashes;
- timestamps and run identifiers used as provenance, not scientific identity;
  and
- completeness and publication state.

Canonical ordering and numeric formatting make repeated exports comparable.
Deterministic structure does not imply that different backends produce the same
cells.

## Replaceable segmentation interface

Native QuPath cell detection, StarDist, and InstanSeg are candidate adapters to
one interface. Each adapter receives an annotation-scoped image reference,
channel mapping, calibration, preprocessing contract, and backend configuration.
It returns cell/nucleus objects, declared features, object-level status, and an
execution attestation in the canonical package shape.

The interface standardizes inputs and evidence, not scientific behavior. Backend
changes create distinct method instances. Comparisons must retain signed
differences, failure modes, and scope. Backend equivalence requires a separate,
predeclared validation and is not assumed by this architecture.

## End-to-end flow

1. Register immutable image, biological identity, channels, and calibration.
2. Supply reviewed QuPath annotations and an explicit run configuration.
3. Select a segmentation adapter and execute the narrow Groovy route.
4. Export objects, measurements, ledgers, hashes, and execution attestation.
5. Validate and canonicalize with Python before dataset or analysis use.
6. Route reviewed corrections back through QuPath with explicit lineage.
7. Build versioned datasets and group-aware splits.
8. Train or evaluate a scope-specific model outside Groovy.
9. Aggregate only eligible, compatible, reviewed observations.

Each stage consumes immutable inputs and publishes to a fresh destination. A
downstream stage may reject an artifact but may not repair missing identity,
invent calibration, reinterpret an absent value as zero, or replace a content
hash with a filename match.

## Historical compatibility boundary

`X:\GitHub\IFQuant-Lung` remains a read-only historical G-SURF record. The
compatibility layer may refer to an explicit committed revision and documented
legacy behavior. It must not copy source authority, release outputs, current
working-tree changes, or the historical production directory structure into
the new core. Fiji is retained only as a frozen compatibility/regression
reference, never as the design center of the platform.

## Non-claims

The scaffold does not claim scientific validation, endpoint validity,
biological ground truth, backend equivalence, threshold transferability, or
model universality. A software-conformant export remains an engineering artifact
until independent, scope-appropriate review and validation are complete.

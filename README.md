# IFQuant Platform

IFQuant Platform is the clean-slate successor for cell-level image measurement,
dataset governance, validation, and scope-specific machine learning. It is an
engineering foundation, not a scientifically validated measurement system.

The historical `IFQuant-Lung` repository is a read-only G-SURF record. It may be
identified by a pinned revision for compatibility and regression work, but its
authority files, release outputs, production pipeline layout, and working-tree
state are not part of this repository.

## Architecture at a glance

- **QuPath first:** image viewing, annotations, cell segmentation,
  morphology/intensity measurement, human correction, and prediction review.
- **Narrow Groovy executors:** deterministic, configuration-driven QuPath runs
  and canonical export. Groovy does not train models or govern datasets.
- **Python governed:** `ifquant_platform` owns contracts, canonicalization,
  provenance, dataset manifests and splits, validation, statistics, and
  aggregation.
- **Replaceable models:** native QuPath, StarDist, and InstanSeg are initial
  segmentation candidates behind one interface. A shared interface does not
  assert that their outputs are equivalent.
- **Scoped claims:** detector, preprocessing, model weights, scanner, batch,
  and intended biological scope remain explicit. There is no universal CNN.

## First milestone

The initial milestone establishes:

1. a Python package and repository scaffold;
2. architecture and responsibility boundaries;
3. backend-neutral measurement and provenance contracts;
4. a canonical package for cell identity, geometry, morphology, compartment
   intensities, detector/model identity, QC, review, and provenance;
5. a minimal annotation-scoped QuPath export proof of concept;
6. a common segmentation-backend interface; and
7. tests plus a validation CLI for structural and integrity checks.

The proof of concept is expected to produce engineering artifacts only. It does
not establish biological ground truth, scientific validity, backend
interchangeability, or model generality.

## Local verification

The core validator uses only the Python standard library. From the repository
root:

```powershell
python -m unittest discover -s tests -v
python -m ifquant_platform.cli validate-method `
  contracts/examples/cell-morphology-intensity-v1.json `
  --parameter-set contracts/examples/cell-morphology-intensity-engineering-v1.json
python -m ifquant_platform.cli validate validation/fixtures/minimal-cell-package
python -m ifquant_platform.cli backends
```

When running directly from a source checkout without installing the package,
install it into a virtual environment with `python -m pip install -e .`, or add
the repository's `src` directory through the normal tooling for that
environment. The committed tests bootstrap `src` themselves and need no third-
party package.

The QuPath proof of concept and its configuration are documented under
[`qupath/`](qupath/README.md). A successful Python fixture validation does not
mean the Groovy executor has run on a microscopy image.

## Repository map

- `contracts/` — closed schemas and example contract instances.
- `qupath/scripts/` — small, configuration-driven QuPath executors.
- `src/ifquant_platform/` — Python contracts, verification, provenance, and CLI.
- `ml/` — training/evaluation code and model-package conventions.
- `datasets/` — versioned manifests, annotations, corrections, and group-aware
  split definitions.
- `validation/` — fixtures and engineering validation plans/results.
- `pipelines/` — orchestration that composes contracts and tools.
- `compat/g_surf/` — isolated, frozen compatibility references only.
- `tests/` — contract, deterministic-export, validation, and CLI tests.
- `docs/` — architecture, boundaries, and roadmap.

Start with [the architecture](docs/ARCHITECTURE.md), then read
[the responsibility boundaries](docs/RESPONSIBILITY_BOUNDARIES.md) before adding
a backend or pipeline.

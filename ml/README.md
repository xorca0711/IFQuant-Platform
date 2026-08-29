# Machine-learning workspace

`ml/` contains Python training and evaluation workflows plus conventions for
portable model packages. It does not contain Groovy training code or implicit
datasets.

Initial segmentation candidates are native QuPath, StarDist, and InstanSeg.
Adapters expose a common input/output contract, while each backend retains its
own configuration, preprocessing, code, runtime, and model identity. Common
packaging is not a backend-equivalence claim.

Every training run consumes immutable dataset and split manifests. Every model
package records:

- model ID, version, task, and intended scope;
- required channels, calibration, input geometry, and preprocessing;
- source-code, environment, configuration, and weights hashes;
- training, tuning, and test manifest identities;
- metrics with group and domain stratification;
- calibration and abstention policy;
- known failure modes and unsupported domains; and
- parent model or fine-tuning lineage when applicable.

Begin with DAPI instance segmentation. Before introducing a custom CNN for
object classification, establish morphology/intensity baselines from validated
canonical features. Models are replaceable within declared scopes; no artifact
in this directory should be labeled universal.

Human corrections are collected through QuPath and enter through a new,
versioned dataset manifest. They never mutate frozen labels or held-out splits
in place. See [the ML roadmap](../docs/ML_ROADMAP.md) for staged evaluation.

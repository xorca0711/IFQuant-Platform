# Engineering contract examples

These examples exercise the first generalized measurement-contract boundary.
They are synthetic engineering inputs and carry no endpoint authorization,
scientific validation, backend-equivalence result, or approved acquisition
scope.

| Identity | Canonical SHA-256 |
|---|---|
| `cell-morphology-intensity-v1.json` | `b4699d43736ad279718126bdb0b87733c1c370d903a28d01335515af852c99e6` |
| `cell-morphology-intensity-engineering-v1.json` | `0ab144834e8e57b3ce21787bcfc99f2fe6bf661d695184814a07375876c83027` |
| resolved method instance | `6c47eda4968b78ec47df0253205dfb9bae40ad5677964def25a0ed1ac0938d3d` |

The definition contains backend-neutral morphology and DAPI compartment-
intensity meaning. The separate parameter set has no values because this
definition declares no parameter slots; it still states an explicit
`identifier_only_unattested` engineering scope. Detector thresholds, model
weights, QuPath versions, physical channel indices, and runtime paths belong in
the segmentation and execution contracts rather than this definition.

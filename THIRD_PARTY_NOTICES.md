# Third party software and methods

The MIT license covers this repository's original source. External applications,
libraries, datasets and model weights retain their own licenses. The dependency
lock records versions, not permission to redistribute data or models.

The H&E color baseline is an independent implementation inspired by
[WALIII/LungDamage](https://github.com/WALIII/LungDamage), by William Liberti,
and the methodology in Liberti et al., *Alveolar epithelial cell fate is
maintained in a spatially restricted manner to promote lung regeneration after
acute injury*, Cell Reports 35, 109092 (2021),
[doi:10.1016/j.celrep.2021.109092](https://doi.org/10.1016/j.celrep.2021.109092).
No upstream source or example images are bundled. IFQuant fits a frozen Lab
color model, counts pixels, and measures declared regions. It does not reproduce
the original smoothing, joint-image clustering, rendering or severity labels,
and makes no numerical-equivalence claim.

QuPath, StarDist and any future model extension are separately installed
components. Preserve their code and weight notices when distributing a runtime.
The repository's image demonstration is procedurally generated synthetic data.

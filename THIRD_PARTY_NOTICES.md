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


## Optional public development engines (2026-10-11)

- InstanSeg code (`instanseg-torch` 0.1.2) and the official brightfield_nuclei 0.1.1
  model identify Apache-2.0 terms. The manifest pins the archive and example; the
  model's RDF metadata and embedded test files remain in the ignored cache.
  No upstream implementation or weights are copied into this repository.
- `pybanksy` 1.3.5 is GPL-3.0. It is an optional separately installed dependency;
  the wrapper is original source. A distributed combined runtime must retain and
  comply with applicable third-party terms; MIT does not relicense BANKSY.
- CPU PyTorch 2.8.0 and its dependencies retain their upstream notices. Installing
  an optional runtime does not convey rights to redistribute source datasets.
- Niethamer mouse marker facts are attributed to DOI 10.1016/j.stem.2024.12.002;
  exact symbol/Ensembl mapping uses the pinned Kasmani HDF5 feature table. The
  repository does not redistribute article content or upstream source matrices.

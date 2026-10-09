# Imaging qualification and lesion context

The product targets future obtainable high-resolution tissue images. Its H&E
candidate workflow works without RNA. The present evidence establishes software
execution, with pathological accuracy and intended-use validation still open.

## Acquisition and sampling protocol

1. Preserve raw image members and hashes, scanner, stain, species, animal/patient,
   specimen, section, acquisition batch and calibration. Unknown identity remains
   unknown; a library accession is not an independent animal ID.
2. Define the biological unit and sampling frame before examining outcomes.
   Record whole-slide versus systematic/random fields, seed, field size, section
   spacing, inclusion/exclusion rules, inflation/fixation and orientation when known.
3. Annotate anatomy (alveolar, airway, vascular), artifacts (fold, tear, blur,
   stain failure, edge), lesions and uncertain/uninterpretable tissue separately.
   Establish exhaustive negative coverage before calling a lesion fraction a
   sensitivity/specificity evaluation. Positive polygons alone are insufficient.
4. Freeze the reference revision, training/tuning/test grouping and reviewer scope.
   Split at animal/patient and required acquisition domains, never random adjacent
   tiles. Keep reviewer blinding and independent held-out reference provenance.
5. Compare the frozen LungDamage-inspired appearance baseline and supervised
   QuPath classifier on the same eligible regions. Report per-class overlap,
   denominator, missed/false lesion area, artifacts and abstention. Use independent
   object references for native/StarDist/InstanSeg instance comparisons.
6. Aggregate compatible raw area components under the sampling protocol. Keep
   per-animal results and uncertainty. Pixels, nuclei and fields are not independent
   biological replicates.

These steps operationalize the microscopy/ATS and pathology references in the
[methodology roadmap](../notes/2026-10-09-development-roadmap.md). No prospectively
unspecified numeric acceptance threshold is manufactured from available fixtures.

## Execution evidence and comparison tools

`benchmark-image SOURCE.json --output benchmark.json --tiles 64 --tile-size 512 --seed 42`
records reproducible windows, decoded pixel sums, read times and sampled process
RSS. The real OpenSlide CMU-1 example is 46,000 × 32,914 RGB pixels, three levels,
and metadata-declared 0.499 µm base pixels. The observed 64-window run used about
**90.2 MiB sampled peak RSS**, with **15.2 ms median read time** on this host.
These are window-read measurements on one source/codec, not whole-slide analysis
throughput or lung-specific accuracy. See the pinned public replay in the
[analysis guide](ANALYSIS_WORKFLOW.md).

This run found and fixed a real TIFF bug: level-zero `aszarr()` returned a
multiscale group. The reader now explicitly opens the selected array. Both base
and reduced levels have a pixel-exact regression test. Range downloads require
complete byte ranges, final size and SHA-256 before publication.

For an externally trained QuPath classifier, run
[`ExportPixelClassifier.groovy`](../qupath/scripts/ExportPixelClassifier.groovy)
on a selected image with one JSON config argument and **without `--save`**.
The config records classifier path/hash, all source members, subject, calibration,
native-pixel XYWH, fresh output directory and training provenance. Only discrete
classification output is accepted. The bridge writes an integer label PNG, RGB
crop, source manifest, native crop origin and classification-code mapping.

The exact config keys are documented at the script's closed input check. A
threshold-fixture generator lives beside it. The real QuPath 0.7 runtime smoke
export matched the independently generated fixture mask exactly (768 pixels per
class). This proves label export and grid preservation, not supervised pathology
performance. The source guide is the
[QuPath pixel-classifier API](https://qupath.github.io/javadoc/docs/qupath/opencv/ml/pixel/PixelClassifiers.html).

Use `compare-masks` for bounded registered regions up to 16 million pixels.
Provide explicit class IDs, an ignored reference value and accepted synthetic or
reviewed-reference metadata. External label masks can be compared through this
boundary, but an InstanSeg canonical object exporter is still conditional.

## Morphology and severity boundaries

| Endpoint | Supplied inputs / denominator | Allowed interpretation |
| --- | --- | --- |
| Tissue/airspace/annotated lesion areas | Eligible calibrated area, explicit artifact exclusions and region coverage | 2D descriptive area or fraction; whitespace is not automatically alveolar airspace. |
| Cuff burden | Reviewed airway/vessel polygon with exactly one inner profile; cuff area / inner perimeter | Length-dimensioned 2D burden; **not** radial cuff thickness. |
| Septal transect | Reviewed alveolar LineString and sampling/orientation protocol | Calibrated 2D transect length; **not** unbiased 3D thickness or stereology. |
| Ordinal injury components | Disease/model-specific versioned rubric, anchors, reviewer and unresolved fields | Component grades and paired reviewer agreement; no universal severity formula. |

`measure-morphology-profiles` respects anisotropic base-pixel calibration and
retains sampling-unit IDs. The existing tissue workflow supplies immutable
review/correction lineage and ordinal forms. `reviewer-agreement` adds two-reviewer
confusion, exact agreement and linear weighted kappa; zero expected disagreement
is undefined, not perfect accuracy. Do not average ordinal components in the
continuous morphology/RNA association tool.

StarDist run 11 remains structurally valid with 2,308 accepted objects and 1,322
topology warnings. The geometry repair/execution problem was addressed previously;
warning removal would require review of actual boundaries and is not a cosmetic
cleanup. Native/StarDist accuracy, warning acceptance and InstanSeg comparison
remain behind independent reviewed references. Keep those gates visible rather
than treating structural validity as backend equivalence.

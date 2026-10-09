# Current project state

**Update this before stopping work, every session.**

Last updated: 2026-10-09. Branch: `codex/tissue-spatial-foundation`, based on current
remote main after the earlier StarDist PR was merged. The user authorized a
commit, push and new PR for the stage 1–4 work plus stage 5–6 initiation. GitHub's
PR and workflow pages are authoritative for publication and remote CI state;
no merge or deployment is included in this request.

Stages 1–4 have an implemented engineering workflow: locked dependencies/CI,
successful StarDist export, windowed high-resolution TIFF intake, QuPath
brightfield bridge, separate H&E candidates/corrections, IF cell neighborhoods,
ordinal review forms and specimen reporting. MIT is the user's selected license.
See [stage status](docs/STAGES_1_4_STATUS.md), [usage](docs/TISSUE_WORKFLOW.md) and
[evidence](validation/evidence/stages-1-4-20261009.json).

Latest integrated verification: **156 tests and 144 subtests passed** after the
stage 5–6 foundation was added. Scoped lint and synthetic end-to-end demos pass.
The earlier stage 1–4 checkpoint and build checks remain recorded separately.
See `validation/evidence/stages-5-6-20261009.json` for current local logs and hashes.

StarDist run 11: 2,380 candidates, 2,308 accepted, 72 excluded; 1,322 accepted
topology warnings. Structural validation/QC rendering passed. H1/H2 and all
biological performance claims remain pending. InstanSeg still has no executor.

Future image sources are unrestricted by public-data availability. Current H&E
evidence is synthetic; a real vendor H&E slide, reference labels and biological
review are not available. Do not fill those gaps with generated approvals.

Stages 5–6 now have a [specific pipeline and acceptance ledger](docs/STAGES_5_6_PIPELINE.md).
Initial work implements processed RNA CSV intake, exact-ID/byte validation,
provided affine transforms, point-center links to tissue regions, calibrated
landmark errors, and processed transcript-genotype/TCR missingness. A synthetic
end-to-end example runs. Native AnnData/SpatialData/Visium adapters, automatic
registration, public-paper reproduction and spatial inference remain planned.

Next software increment: native sparse spatial interchange and round-trip checks,
then a small lung public example. Future real scanner-scale images and independent
review still gate intended-use performance, not ongoing software development.

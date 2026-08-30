# Phase 3 work-in-progress handoff

Status: **stopped at the user's request on 2026-08-30; incomplete work is local,
untracked, uncommitted, and not pushed**.

## Stable published baseline

- Local `main` and `origin/main` both point to
  `cff15a8d78a1040b8cfd7e7af029c27092e274b5`.
- The previously approved six-commit push completed before Phase 3 began.
- Run05 uses the complete 2048 × 2048 image. The user considered the symmetric
  full-image boundary exclusions sufficient for this engineering pilot.
- The 103 image-edge candidates remain preserved in the candidate ledger and
  excluded from the 1,700 canonical objects.
- The separate 194 accepted `nucleus_not_covered_by_cell_geometry` warnings
  remain conservatively ineligible unless a later H2 rule is approved.
- `IFQuant-Lung` remains outside the new-core work. Its only observed change is
  the pre-existing `scripts/export_vsi_overviews.groovy` working-tree edit.

## Local Phase 3 snapshot

The following files exist only as untracked work in `IFQuant-Platform`:

- `contracts/nuclear-reference-object.schema.json`
- `contracts/reference-ignore-region.schema.json`
- `contracts/nuclear-reference-set.schema.json`
- `contracts/split-manifest.schema.json`
- `src/ifquant_platform/phase3_validation.py`
- `validation/fixtures/minimal-phase3-reference-split/`

All four draft schemas parse as JSON, but they have not received final
schema/runtime parity review, tests, or integration. Snapshot SHA-256 values over
their current file bytes are:

| Draft file | SHA-256 |
| --- | --- |
| `nuclear-reference-object.schema.json` | `2bfe5fa88e3b6988965c26e8ff043202ba705fe04158ed799c2d5609787be4b5` |
| `reference-ignore-region.schema.json` | `b7c5f6d79d5814d03f74afdd2b76217d7e117b282eeff5683524d4dc18bed85a` |
| `nuclear-reference-set.schema.json` | `72e32d83fe59f5bdf3a7cdb76cdb12608cdfa721f54e4dbf7a2d0db4438e53b6` |
| `split-manifest.schema.json` | `f6caa5c020864a698ecccbfb4121613aff1ee7a176db3ac8d3dc9231f12bc0db` |

The Python validator scaffold is syntactically parseable but incomplete. It is
819 lines, ends inside the reference-region review implementation, and does not
yet provide finished public validators or usable CLI commands. Its current file
SHA-256 is
`9632c8489e510977913f522f4531c41cda4c7c32ce4dac50746521356a9e3c83`.

The synthetic fixture currently contains:

- four distinct source-byte artifacts;
- four image manifests, four DAPI channel maps, and four reviewed ROI scope
  manifests;
- one governed observation set with three mice, four slides, two batches, and
  two scanners;
- byte-bound producer code and a draft selection-protocol artifact; and
- an empty `reference-ignore-regions.jsonl` placeholder.

The governed observation set passes the completed Phase 2 validator with four
observations and canonical SHA-256
`4b299cde8f8e494adc36ef0f8fbeb9ce3362fb93b1a81b3dd78ad98216f05c1c`.
Its current raw file SHA-256 is
`30b89f43035f0c065350565a2353f292102d77a3cc69153550e4ebc67599861d`.

## Not yet implemented or verified

- no `nuclear-reference-objects.jsonl` artifact;
- no completed `nuclear-reference-set.json` fixture;
- no completed `split-manifest.json` fixture or held-out commitment;
- no Phase 3 unit or CLI tests;
- no CLI or package-export integration;
- no full test-suite result for the draft Phase 3 work;
- no final leakage, lineage, lock, or claim-discipline audit; and
- no commit or remote publication of any Phase 3 file.

The draft must not be described as Phase 3 complete, leakage-safe, frozen,
scientifically valid, or usable for training/evaluation.

## Restart sequence

1. Reconcile the four schemas with the unfinished Python scaffold, especially
   prediction-package exposure, exclusion reasons, adjudication states, NDJSON
   artifact fields, and batch/scanner domain-control semantics.
2. Finish the reference-set validator before implementing split validation.
3. Complete canonical nuclear-reference and ignore artifacts, then bind their
   exact hashes and counts into a frozen synthetic reference-set fixture.
4. Complete the split fixture, group/domain audits, held-out commitment, and
   immutable parent-lineage rules.
5. Add fail-closed tests for tampering, incomplete region coverage, model-aided
   reference review, assignment coverage, mouse/slide/source-family leakage,
   batch/scanner domain controls, and lock drift.
6. Run schema validation, the Phase 3 focused tests, the full repository suite,
   an independent audit, and `git diff --check` before any commit or push.

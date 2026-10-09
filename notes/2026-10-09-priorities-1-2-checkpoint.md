# Native spatial interchange and lung replay checkpoint

> Historical saved checkpoint at `2566fc1`. Superseded by the completed development pass in [PROGRESS](../PROGRESS.md) and [the execution report](../docs/EXECUTION_REPORT.md); retain the original in-progress findings below as history.

**Date:** 2026-10-09
**Status:** draft — implementation saved before final verification

## Summary

Saved at the user's request during priorities 1–2: native spatial interchange,
one Kasmani lung example, and a repository-wide documentation scope refresh.
The platform remains a future high-resolution imaging tool with optional omics.
This checkpoint does not claim the priorities are complete.

## Details

- Added completed-product validators, sparse AnnData/Visium adapters, exact-ID
  metadata export and a portable named-frame SpatialData profile with images/regions.
- Preserved filtered-matrix omissions as `not_reported`, never measured zeros.
- Locked optional dependency extras; full stack runs in ignored `.venv-spatial`
  with x64 Python because the ARM64 pyogrio build could not complete.
- Focused tests: 38 passed, 1 failed initially; the naming restriction was fixed
  and the failed SpatialData scene/round-trip/tampering test passed on rerun.
  Scoped lint and compilation passed. Final integrated checks remain pending.
- Downloaded and hashed four GSM6108348 public inputs (~15 MB). The selected
  five-gene panel and data limitations are in `datasets/examples/`.
- Wrote `scripts/replay_lung_example.py`; full replay remains unexecuted at this
  checkpoint. Pixel context is explicit because independent calibration and
  pathological annotations are unavailable.
- Added `docs/DEVELOPMENT_PLAN.md` and `docs/SPATIAL_INTERCHANGE.md`; broader
  README/architecture/subdirectory/historical-phase documentation refresh remains.
- Continue on `codex/tissue-spatial-foundation` and existing GitHub PR #2.
  No merge is authorized. Raw data, environments and generated stores stay ignored.

## Next steps

- Run the replay into a fresh `validation/output/` directory and inspect its
  overlay, independent source count reconciliation and both format round trips.
- Finish adapter edge cases/capacity evidence and optional dependency CI.
- Refresh active documentation and explicitly label historical phase records.
- Run integrated verification, update evidence/status, commit and update PR #2.

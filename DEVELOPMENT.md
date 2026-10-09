# Development decisions and responsibility

## AI disclosure

OpenAI Codex inspected the platform and historical IFQuant-Lung evidence,
researched the methodology roadmap, and authored the 2026-10-09 stage 1–4 and subsequent priorities 1–5 code,
tests and documentation in this working tree. Codex ran local engineering checks
and inspected generated images. No subagents participated in this implementation.
Prior commits contain earlier agent work; this entry does not attribute or
certify that history. Human pathology review has not been supplied.

## Responsibility table

| Date | Item | Proposed by | Decided by | Decision | Reason |
| --- | --- | --- | --- | --- | --- |
| 2026-10-09 | Lung injury/regeneration first; optional TME | Codex and user discussion | User | Accepted direction | Requested biological scope. |
| 2026-10-09 | Tool for future obtainable high-resolution images | User | User | Required scope | Public data availability must not define the product identity. |
| 2026-10-09 | Implement roadmap stages 1–4 | Codex roadmap | User | Authorized implementation | User asked to proceed. This is scope authorization, not acceptance of finished code. |
| 2026-10-09 | Original source license | User response to license question | User | MIT | Explicit selection; third-party terms remain separate. |
| 2026-10-09 | Independent frozen H&E baseline and descriptive reports | Codex | Pending human review | Implemented for review | Avoid copied upstream code and unsupported severity equivalence. |
| 2026-10-09 | Structure and initiate stages 5–6 | User | User | Authorized planning and initial implementation | Shared spatial/assay foundation first; lung scope and optional TME retained. |
| 2026-10-09 | Commit, push and open a GitHub PR | User | User | Authorized | Explicit follow-up request; no merge authorization inferred. |
| 2026-10-09 | CSV/affine foundation before native spatial libraries | Codex | Pending human review | Implemented for review | Test identity, coordinate and missingness behavior before adding heavy adapters or inference methods. |
| 2026-10-09 | Proceed through priorities 1–2 | User | User | Authorized implementation | Native interchange and one real lung intake replay; not the historical fluorescence Phase 2. |
| 2026-10-09 | Refresh legacy-focused repository materials and save progress | User | User | Authorized documentation/checkpoint | Preserve historical evidence while making current scope and remaining jobs explicit. |
| 2026-10-09 | Native adapters and named-frame SpatialData exchange | Codex | Pending human review | In-progress checkpoint | Focused fixtures exercised; real replay and integrated verification remain. |
| 2026-10-09 | Execute all proposed jobs through priority 5 and revise implausible pipelines | User | User | Authorized development pass | Scope expanded beyond the saved priority 1–2 checkpoint; retain scientific gates and rationale. |
| 2026-10-09 | Implemented optional analysis tools and 31-job status register | Codex | Pending human review | Implemented for review | Real-source and synthetic execution evidence are separated from intended-use validation. |

## Rejected or substantially revised AI proposals

| Date | Proposal | Rejected/modified by | Reason and resulting change |
| --- | --- | --- | --- |
| 2026-10-09 | Constrain identity to a public-data research tool | User | Rejected explicitly. Product targets future high-resolution images; public and synthetic data are development resources. |
| 2026-10-09 | Treat annotated lesion area as a generally reviewed lesion fraction | Codex implementation review | Renamed to annotated lesion fraction; accepted polygons do not establish exhaustive negative coverage. |
| 2026-10-09 | Use Groovy JSON imports for QuPath brightfield bridge | Runtime evidence / Codex | QuPath lacked those classes. Switched to bundled GsonTools; fresh synthetic export succeeded. |
| 2026-10-09 | Double-underscore generated table fields | SpatialData runtime / Codex | SpatialData rejects names beginning with double underscores. Renamed generated fields; scene round-trip test passed. |
| 2026-10-09 | Native ARM64 installation for the full SpatialData stack | Dependency build / Codex | pyogrio required unavailable GDAL build inputs. Used an isolated x64 binary environment without changing the user's default Python. |
| 2026-10-09 | Treat base TIFF pyramid series as an array | Real Aperio execution / Codex | It opened a multiscale group. Explicit selected-array opening plus base/reduced-level regression fixed the reader. |
| 2026-10-09 | Use a five-gene replay for domains/deconvolution | Codex methodological review | Rejected. Keep it as interchange evidence; require broad features and compatible independent references for biological comparisons. |
| 2026-10-09 | Interpret cuff area/perimeter or transects as unbiased thickness | Codex methodological review | Replaced with explicit calibrated 2D burden/transect endpoints and sampling/orientation limits. |
| 2026-10-09 | Claim complete Slide-GoTags reproduction from public source tables | Source-data audit / Codex | Tables lack cell coordinates/edge counts; portal needs sign-in. Reconcile 240 reported rows and keep cell-level reproduction gated. |
| 2026-10-09 | Copy author global shuffling and zero substitution for undefined mixing | Codex methodological review | Use specimen/region/coverage-conditioned nulls, +1 p correction, BH, explicit undefined/degenerate abstention and uncertainty scenarios; do not call this an exact author-method reproduction. |

No human scientific approval, model equivalence decision, or code acceptance is
inferred from test completion. See [current progress](PROGRESS.md) and
[local evidence](validation/evidence/stages-1-4-20261009.json).

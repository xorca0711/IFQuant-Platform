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
| 2026-10-11 | Complete feasible software/public-data work and publish a follow-up PR | User | User | Authorized development and publication | No private validation data available; no merge or scientific acceptance authorized. |
| 2026-10-11 | Pinned H&E nuclei executor, broad RNA/BANKSY replay, explicit NGFF planes and throughput qualification | Codex | Pending human review | Implemented for review | Reproducibility evidence remains separate from independent pathology validation. |

| 2026-10-11 | Complete whole-slide InstanSeg stitching and public VALIS execution, update PR #4 | User | User | Authorized development and publication | Explicit request; no merge or scientific acceptance authorized. |
| 2026-10-11 | Conservative tiled nuclei stitching, isolated live registration and bounded public replays | Codex | Pending human review | Implemented for review | Software reconstruction and controlled geometry are separated from independent biological accuracy. |

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

| 2026-10-11 | Leave all InstanSeg/BANKSY/program work conditional on private validation data | Codex implementation review | Revised: public resources suffice for scoped execution and source curation; independent accuracy remains open. |
| 2026-10-11 | Use 500 variable genes in the initial public RNA plan | Capacity check / Codex | Exceeded the existing million-row import guard; reduced to 300 plus cited markers (308 total), retaining full-library denominators. |
| 2026-10-11 | Fit brightfield nuclei into the existing fluorescence-v1 cell executor immediately | Codex implementation review | Revised to an explicit bounded H&E tissue result; whole-slide stitching and a deliberate canonical adapter remain separate work. |
| 2026-10-11 | Install VALIS into the current NumPy 2.x / Python 3.12 environment | Runtime evidence / Codex | Separate locked Python 3.11 / NumPy 1.26 runtime avoids incompatible constraints and failed fastcluster source compilation. |
| 2026-10-11 | Call rigid-only VALIS without a compatibility shim | Runtime evidence / Codex | VALIS 1.2.0 cleanup accesses an absent container; initialize only that empty container and still require completed outputs. |
| 2026-10-11 | Assume physical serial-section identity from public example names | Source evidence / Codex | Relationship is not established; added explicit unknown relation and retained source-series proxy identity. |
| 2026-10-11 | Compare the entire dense 768-pixel inference ROI with exhaustive instance matching | Capacity evidence / Codex | Exceeded the existing four-million-pair guard; retained inference outputs and compared the fixed 512-pixel common window without weakening the guard. |
| 2026-10-11 | Materialize a full tile inventory before enforcing its cap | Targeted review / Codex | Moved the 100,000-tile guard before allocation; dedicated regression and existing package reconstruction passed. |

No human scientific approval, model equivalence decision, or code acceptance is
inferred from test completion. See [current progress](PROGRESS.md) and
[local evidence](validation/evidence/stages-1-4-20261009.json).

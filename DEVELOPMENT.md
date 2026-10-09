# Development decisions and responsibility

## AI disclosure

OpenAI Codex inspected the platform and historical IFQuant-Lung evidence,
researched the methodology roadmap, and authored the 2026-10-09 stage 1–4 code,
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

## Rejected or substantially revised AI proposals

| Date | Proposal | Rejected/modified by | Reason and resulting change |
| --- | --- | --- | --- |
| 2026-10-09 | Constrain identity to a public-data research tool | User | Rejected explicitly. Product targets future high-resolution images; public and synthetic data are development resources. |
| 2026-10-09 | Treat annotated lesion area as a generally reviewed lesion fraction | Codex implementation review | Renamed to annotated lesion fraction; accepted polygons do not establish exhaustive negative coverage. |
| 2026-10-09 | Use Groovy JSON imports for QuPath brightfield bridge | Runtime evidence / Codex | QuPath lacked those classes. Switched to bundled GsonTools; fresh synthetic export succeeded. |

No human scientific approval, model equivalence decision, or code acceptance is
inferred from test completion. See [current progress](PROGRESS.md) and
[local evidence](validation/evidence/stages-1-4-20261009.json).

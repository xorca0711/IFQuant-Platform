# Phase 3 engineering status

The initial Phase 3 engineering contract infrastructure is implemented on the
local `codex/phase3-wip` branch. Closed schemas, strict read-only validators,
CLI commands, tamper tests, and a synthetic reference/split fixture now agree
and pass. **No Phase 3 commit has been pushed to a remote at this checkpoint.**

This is engineering contract infrastructure, not scientific validation. The
repository still does not contain real reviewed nuclear-reference data, a real
held-out cohort, segmentation-performance evidence, or authorization to use
objects for biological inference, training, or endpoint aggregation. The
synthetic fixture is deliberately not confirmatory-ready.

## Preserved decisions and open warnings

- Run05 covers the complete 2048 x 2048 image rather than an inset ROI. The user
  accepted its symmetric full-image edge exclusions as sufficient for this
  engineering pilot. All 1,803 candidates remain traceable: 1,700 canonical
  objects and 103 boundary exclusions retained in the candidate ledger.
- That acceptance resolves the engineering boundary-policy question only. It
  does not establish detection sensitivity, biological ground truth, or formal
  H1 visual-review evidence.
- The separate 194 accepted objects carrying
  `nucleus_not_covered_by_cell_geometry` remain conservatively ineligible.
  They may be promoted only after H2 approves a precise acceptance rule or a
  revised detector/export method is run under a new identity.
- `IFQuant-Lung` remains a read-only historical source. Its unrelated existing
  `scripts/export_vsi_overviews.groovy` working-tree edit is outside this work.

## Implemented Phase 3 engineering deliverables

The Phase 3 implementation now provides:

1. a separate reviewed DAPI nuclear-instance reference-object contract;
2. explicit ignore-region records for truncation, ambiguity, artifacts, and
   other declared exclusions, without inheriting a detector's edge rule;
3. a declared region-completeness ledger that makes reviewed scope explicit and
   reconciles object/ignore counts; whether the declared scope is genuinely
   complete remains a human-review gate;
4. a narrow, fail-closed canonical 2D polygon subset with strict topology,
   in-image/in-ROI containment, edge-reason consistency, and duplicate-geometry
   rejection image-wide; nuclear positives cannot overlap or touch same-image
   ignore geometry;
5. immutable reviewer, distinct-adjudicator, correction,
   prediction-exposure, freeze, and comprehensive upstream/review/successor
   chronology across every governed-observation ancestor revision;
6. nonempty reference sets plus per-held-out-image positive-reference and
   confirmatory-readiness requirements;
7. explicit `source_family_id`, mouse, slide, batch, and scanner identities;
8. exact image-level `train`, `tuning`, and `held_out_test` assignments -- never
   random tile assignment;
9. declared hard-separation checks for mouse, slide, and source-family connected
   groups built across every governed image, including excluded/unassigned
   bridge images, with declared batch/scanner domain-control modes;
10. separate hash-bound held-out ID and reference-content commitments plus
    successor rules that reject held-out truth, policy, source, annotation,
    biological-identity, or source-family drift while allowing valid
    train/tuning-only evolution under policy; and
11. nonempty, byte-attested evaluation-policy and selection-protocol artifacts,
    every governed-observation ancestor's provenance code artifact, and
    reference/split provenance code artifacts; and
12. fail-closed Python validators, CLI commands, synthetic fixtures, and tamper
    tests.

Canonical JSON/NDJSON, SHA-256 bindings, explicit identities, group-aware split
checks, and immutable parent lineage are the engineering mechanisms. Passing
them will mean that an artifact is structurally governed; it will not mean that
the labels are biologically correct or the split is scientifically optimal.

## Passing synthetic fixture

The fixture at `validation/fixtures/minimal-phase3-reference-split/` contains
four governed synthetic images and four reviewed-region declarations. It binds
four canonical DAPI nuclear-reference objects, one explicit `out_of_focus`
ignore region, and three declared source families.

| Partition | Exact image IDs | Reference readiness note |
| --- | --- | --- |
| `train` | `phase3-image-001`, `phase3-image-002` | Image 001 contains the sole model-assisted, single-review object, deliberately confined to training in this fixture. |
| `tuning` | `phase3-image-003` | Human-drawn with independent second review in the synthetic record. |
| `held_out_test` | `phase3-image-004` | Exact locked ID; human-drawn with independent second review in the synthetic record. |

The exact locked held-out list is `["phase3-image-004"]`, with canonical
SHA-256
`44f3c019439012f5f0136129747a02e98a83354a84e42120f565cd9cdaa70f67`.
Its `ifquant_held_out_reference_content_v1` descriptor has SHA-256
`a16120a41f7bf114a4c1608cca05757c09a119f50d290abd5e09861645a25900`.
That descriptor binds the full task, evaluation policy, selection protocol,
and the held-out image's complete governed observation record (including
biological identity and source/channel/annotation hashes), source family, all
region-ledger entries, nuclear-reference objects, and ignore regions.
The split validator reports zero overlap among the *declared*
mouse/slide/source-family connected components built from all governed images,
including any excluded or unassigned bridge images. Batch
`phase3-batch-heldout` and scanner `phase3-scanner-heldout` are explicit
leave-values-out controls.

The model-assisted training object is reference object
`17ab7d193bb3fddd50e64179bb924360548a79d9b6c81631d4d39532cde26e33`.
Its prediction package/run/object/geometry identities are recorded, but its
adjudication method is `single_reviewer`; consequently the reference validator
reports `model_assisted_single_review_count: 1`,
`model_assisted_nonconfirmatory_review_count: 1`, and
`confirmatory_reference_ready: false`. An `adjudicator_decision` cannot reuse a
listed reviewer as adjudicator.

Current canonical manifest identities are:

- nuclear reference set:
  `f0137f493ef2cecede86f933729d12ac169a528608bfc69b96d82e457f0fb935`;
- split manifest:
  `43c32b9c947257b79bd00ae59b09adf64883e0b7554606aaa700b2e6a0d3b47d`;
- held-out image-ID list:
  `44f3c019439012f5f0136129747a02e98a83354a84e42120f565cd9cdaa70f67`;
- held-out reference content:
  `a16120a41f7bf114a4c1608cca05757c09a119f50d290abd5e09861645a25900`.

Geometry validation treats the image as the closed domain
`[0, width] x [0, height]`. Rings must be simple, nonzero-area, canonically
oriented/started, and free of repeated, zero-length, or redundant collinear
vertices; holes and true multipolygon members have stable order and valid
topology. A one-member `MULTIPOLYGON` and semantically duplicate geometry are
rejected. Exact nuclear and ignore duplicates are rejected image-wide,
regardless of annotation. All reference/ignore geometry must be within the
governed inclusion ROI, and nuclear reference geometry may neither overlap nor
touch same-image ignore geometry so held-out positives remain scoreable.
`physical_image_edge` must meet the image boundary; because v1 has no separate
specimen-boundary artifact, `physical_specimen_edge` uses the governed ROI
boundary.

Chronology traverses the current governed-observation-set revision and every
revision in its validated parent chain. Each direct parent's
`provenance.created_at` must be no later than its child's, and all timestamps
bound through every ancestor—observation-set, image/channel/annotation
provenance, acquisition time when present, and annotation/identity reviews—must
be no later than reference freeze. Reference provenance and every
region/object/ignore review are bound to the same freeze. Parent reference and
split freezes must precede successor creation, and the current reference freeze
must precede split creation. Only an initial split requires its reference to be
frozen before the original held-out commitment. A later reference successor
may freeze after the preserved commitment when held-out content is unchanged,
enabling honest train/tuning-only evolution. Evaluation-policy and
selection-protocol artifacts, every observation-ancestor provenance code
artifact, and reference/split provenance code artifacts must be nonempty and
verified by exact byte size and SHA-256.

## Current decision gates

| Gate | State | Required evidence or decision |
| --- | --- | --- |
| Full-image boundary policy | Accepted for the engineering pilot | Preserve all four-side guard membership and candidate dispositions on every rerun. |
| H1: formal DAPI visual review | Open | Capture reviewer identity, date, scope, and rationale on governed images; the informal overlay view is only provisional. |
| H2: geometry-warning disposition | Open; conservative exclusion applies | Exclude, approve a machine-testable acceptance rule, or revise and rerun the method for the 194 warnings. |
| D1: real governed-observation eligibility | Open | Supply real biological/acquisition identities, reviewed ROI annotations, immutable source bytes, and correction lineage. |
| Phase 3 contract parity | Passing for the synthetic engineering fixture | Keep schemas, runtime validation, CLI behavior, canonicalization, chronology, and claim restrictions aligned. Schema alone does not enforce every cross-record runtime invariant. |
| Reference completeness and review | Synthetic mechanism passes; real gate not passed | Provide a nonempty exhaustive real reference revision, with a positive and confirmatory-ready reference on every held-out image, explicit ignores, and complete prediction-exposure/adjudication records. |
| Leakage and domain-control audit | Declared synthetic groups pass after including all governed bridge images; real gate not passed | Human-approve real source families; assign whole mouse/slide/source-family groups; verify the study-specific batch/scanner design. Excluded/unassigned governed images remain component bridges. This check is not proof against unrecorded relatedness. |
| Held-out lock | Synthetic ID/content mechanisms pass; real lock not established | Commit exact real governed IDs and reference content; prohibit reassignment or held-out truth/policy/source/identity drift in successors. |
| Engineering verification | Passing for the current Phase 3 fixture and validator | Current result: 108 tests discovered, 107 passed, and one optional JSON-Schema test skipped because `jsonschema` is absent; focused Phase 3: 37 discovered, 36 passed, same optional skip. Keep tamper/failure tests, runtime audit, and `git diff --check` passing. |
| S1: segmentation performance | Not evaluated | Evaluate prospectively on frozen real references after the preceding gates; synthetic fixtures cannot satisfy this gate. |
| Scientific promotion | Authorization `none` | Requires scope-specific biological, endpoint, calibration, abstention, and domain-shift evidence plus an explicit owner decision. |

## Local verification

After `python -m pip install -e .`, run:

```powershell
python -m unittest discover -s tests -v
ifquant-platform validate-reference-set `
  validation/fixtures/minimal-phase3-reference-split `
  --expect-reference-set-sha256 `
  f0137f493ef2cecede86f933729d12ac169a528608bfc69b96d82e457f0fb935
ifquant-platform validate-split `
  validation/fixtures/minimal-phase3-reference-split `
  --expect-split-manifest-sha256 `
  43c32b9c947257b79bd00ae59b09adf64883e0b7554606aaa700b2e6a0d3b47d `
  --expect-reference-set-sha256 `
  f0137f493ef2cecede86f933729d12ac169a528608bfc69b96d82e457f0fb935 `
  --expect-held-out-test-image-ids-sha256 `
  44f3c019439012f5f0136129747a02e98a83354a84e42120f565cd9cdaa70f67 `
  --expect-held-out-test-reference-content-sha256 `
  a16120a41f7bf114a4c1608cca05757c09a119f50d290abd5e09861645a25900
```

Both reports should return `status: valid`; the reference report should still
return `confirmatory_reference_ready: false`. Changing that negative readiness
result requires stronger review evidence, not a documentation or validator
override.

The full test run currently discovers 108 tests: 107 pass and one optional
JSON-Schema instance check is explicitly skipped because `jsonschema` is not
installed. The focused Phase 3 run discovers 37 tests: 36 pass with the same
one optional skip. The standard-library runtime validator and all adversarial
geometry, readiness, chronology, tamper, and successor-lock tests pass.

## Next review points and development gates

Engineering can maintain and audit this infrastructure without a scientific
confirmation. The next advancement decisions that require human or study-owner
input are:

1. Formalize H1 and resolve H2 before any run05 detected object is eligible.
2. Admit real governed observations with user-supplied mouse, slide, batch, and
   scanner identities plus reviewed ROI/correction lineage.
3. Review exhaustive real DAPI nuclear instances, ignore regions, completeness,
   and every model-assisted annotation exposure; independently review or
   adjudicate confirmatory candidates.
4. Human-approve the real source-family ledger, study-specific hard leakage
   groups, batch/scanner domain-control design, and exact held-out ID/content
   commitments.
5. Predeclare Phase 4 evaluation metrics and acceptance criteria before the
   native QuPath baseline is evaluated.

Until those inputs exist, Phase 3 remains at the engineering-infrastructure
checkpoint. Do not describe the fixture as real reference data, a scientifically
valid or adequate split, leakage proof, H1/H2 closure, backend-equivalence
evidence, model-universality evidence, or authorization. Commit and remote
publication remain separate actions after audit; no Phase 3 remote push has
occurred at this checkpoint.

Two explicit v1 limitations remain: prediction-exposure hashes are asserted
identities rather than local byte-attestation, and JSON Schema does not by
itself enforce all cross-record/runtime invariants. Real source-family approval
is a human study decision. None of these engineering checks converts the
synthetic fixture into scientific validation, backend equivalence, model
universality, or proof that hidden leakage is absent.

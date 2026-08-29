# Drift and Omission Ledger

> N-class Shadow Architect / Tech Lead projection for snapshot `CTX-2026-08-30T02:44:51+08:00`. A finding is not a provider mutation or completion verdict.

## Intervention levels

| Level | Meaning |
|---|---|
| `L0 OBSERVE` | Record a material delta or resolved event; no action required now. |
| `L1 WARN` | Bounded debt or uncertainty; safe work may continue with explicit ceiling. |
| `L2 REVIEW` | The responsible owner must reconcile the contradiction or missing contract before relying on it. |
| `L3 BLOCK` | Continuing the affected completion path would risk authority, source, writer, or evidence corruption. |

## Findings

### `DRIFT-001` — local Shadow runtime unavailable

- level: `L1 WARN`
- source: owner requested `/Users/neon/skills-shared`; execution environment did not mount that host path
- observed: this run read the exact remote `ed3c/skills-shared@52b29b38ded9eaacbf7fb1bfa8ccf69ab37870b9` and applied the Shadow/Tech Lead methods
- missing: local checkout HEAD/status, local monitor process, local runtime/worktree receipt
- disposition: do not claim that the local Shadow daemon/process was opened; describe this as a source-pinned read-only Shadow review
- next safe action: run the same snapshot against the local path when an execution environment with that mount is available, then compare deltas rather than replacing this remote snapshot

### `DRIFT-002` — obsolete #109 PR lineage

- level: `L0 OBSERVE`
- source: Issue #109, old PR #111, landed #112, current PR #118
- observed: #111 encoded the pre-#112 mandatory-specialized-feature assumption and was based on stale provider reality
- action taken: closed #111 as superseded; created #118 from provider-landed `main@281044f…` with head `9e6ff70…`
- residual: #109 is not complete until #118 exact-head verification, merge/default-branch readback, and Issue closure succeed

### `DRIFT-003` — #117 stale blocker and missing dual-edge state

- level: `L2 REVIEW`
- source: #117 body says blocked on #112; #112 is provider-landed
- observed: the start prerequisite is satisfied and branch `agent/issue-117-context-closure` has begun
- missing: #117 body does not distinguish `S: #112` from `C: #109 final provider state`
- next safe action: update #117 to `in_progress`, record #112 as satisfied start edge and #109 as completion-refresh edge; never claim pack completion from the current branch alone

### `DRIFT-004` — #45 body prose contradicts current readiness

- level: `L1 WARN`
- source: #45 marker is `ready`; body still says blocked until #44
- observed: #44 is provider-landed
- effect: an Agent reading only the body may incorrectly refuse a ready daemon-lease atom
- next safe action: after typed Issue readback #82 or a small metadata-only correction, remove stale dependency prose or add a current readback section without changing #45's claim

### `DRIFT-005` — #65 marker remains blocked after named dependency landed

- level: `L2 REVIEW`
- source: #65 names #61 as its completion predecessor; #61 is landed
- observed: marker remains `blocked`
- ambiguity: the real blocker may now be absence of a supported upstream promotion seam rather than dependency waiting
- next safe action: read current pinned Noodle source/runtime and give #65 an explicit blocker owner/reason or move it to ready for the bounded discovery probe

### `DRIFT-006` — #116 rationale may have been superseded by #112

- level: `L2 REVIEW`
- source: #116 says infrastructure atoms need a generic `repo-infra-verify-oracle` because every Issue required a feature
- observed: #112 made the mandatory baseline universal and specialized features optional/additive
- risk: implementing #116 without a recurring specialized behavior would recreate a generic feature-registry pressure that #112 removed
- next safe action: disposition #116 as `DROP`, `HOLD`, or a narrower real-product oracle after a physical baseline insufficiency is observed

### `DRIFT-007` — stale specialized feature markers in the open portfolio

- level: `L1 WARN`
- source: many open Issues still carry `<!-- noodles-feature: verification-skill-oracle -->`
- observed: after #112 the marker is optional and must correspond to an applicable specialized operation, not serve as an admission token
- risk: an unrelated specialized oracle could add cost or imply coverage that the atom does not claim
- next safe action: during #82/Issue audit, retain only markers whose exact physical acceptance truly requires that feature; marker-free Issues continue through mandatory baseline acceptance

### `DRIFT-008` — historical #19 wording is no longer current structural truth

- level: `L0 OBSERVE`
- source: landed #19 required every Issue/order to declare a feature; landed #112 later replaced that root rule
- observed: current code/system contract owns mandatory baseline + optional specialized oracle
- rule: fact reconstruction must resolve supersession by provider order and current source, not quote a closed Issue as timeless specification
- next safe action: derived requirement views must distinguish historical fact from current governing fact

### `DRIFT-009` — #83 write boundary collides with #109

- level: `L3 BLOCK`
- source: #83 and #109 both own `AGENTS.md` and `contracts/system-v1.md`
- observed: #109 has open PR #118
- risk: concurrent implementation creates competing writers and may erase Dune/AF requirements or reintroduce duplication
- block: do not start #83 implementation until #109 provider-lands or is explicitly abandoned; then rebase #83 on provider `main`
- next owner: #83 convergence lane after #82 and #109

### `DRIFT-010` — complete System Specification convergence has no exact Issue

- level: `L1 WARN`
- source: owner conversation proposes Purpose/Non-goals, authority, ownership, Golden Path, verification, autonomy, learning, concurrency, cross-repo, complexity, and stable requirements
- observed: #109 owns only the Dune/AF section; #83 owns canonical procedure/document cleanup
- missing: one narrow post-cleanup atom for the remaining stable constitution sections and requirement evolution rules
- next safe action: after #109 and #83, create a documentation-only spec-convergence Issue with no runtime changes and no fourth hop

### `DRIFT-011` — requirement-bound Issue completeness has no full owner yet

- level: `L2 REVIEW`
- source: owner conversation requires `noodles-requirement`, write boundary, physical trigger, bounded claim, planted negative, readback, residue, non-case, and non-claims
- observed: #82 owns typed provider dependencies/body digest and schedulability; #98 owns write-boundary collision; no current atom owns requirement-ID resolution plus deterministic structural completeness
- next safe action: after #82, create one small extension atom for resolvable requirement ID and fixed section presence/non-empty checks; do not claim natural-language quality validation

### `DRIFT-012` — open Issue descriptions remain uneven

- level: `L2 REVIEW`
- source: 28 open Issues
- observed: older code-intelligence leaves #5–#14 and some runtime atoms omit one or more of exact write boundary, physical trigger, explicit non-case, typed dependency marker, or requirement pointer
- risk: a scheduler/Agent can see a precise leaf but still reconstruct broader rationale or safe writes probabilistically
- next safe action: run an Issue audit after the typed contract lands; patch only missing machine fields and acceptance gaps, not full architecture prose

### `DRIFT-013` — historical #69 closed as completed without a landed fact

- level: `L2 REVIEW`
- source: #69 title/goal `--help`, marker `ready`, GitHub state closed with reason completed, no landed markers/PR receipt
- observed: it is absent from the open denominator, but a naive `closed == complete` projection would misclassify it
- rule: fact reconstruction requires `noodles-state: landed` plus PR/merge/closure readback; GitHub closed state alone is insufficient
- next safe action: encode this negative in future requirement-status projection tests

### `DRIFT-014` — #4 is ready but lacks an explicit typed write boundary

- level: `L2 REVIEW`
- source: #4 declares one bounded canary change but not exact path prefixes
- observed: all stated functional prerequisites are landed
- risk: starting the full Golden Path canary while #109/#117 or another lane owns overlapping files would violate intended concurrency discipline
- next safe action: Tech Lead must choose a disjoint canary surface and record it before dispatch; long-term enforcement belongs to #98

### `DRIFT-015` — no deterministic context-pack completeness checker

- level: `L1 WARN`
- source: #117 acceptance allows review-detected planted omissions when no deterministic seam exists
- observed: the six documents are manually compiled against frozen provider queries
- evidence ceiling: this pack can demonstrate bounded source accounting by review, not prove universal omission detection
- next safe action: use #117 as consumer corpus for skill-concerns #9; admit a hermetic checker only if it detects planted omitted source, duplicate owner, false completion edge, stale PR head, and N-doc-as-evidence cases

### `DRIFT-016` — owner conversation and Dune images are session-bound sources

- level: `L1 WARN`
- source: `SRC-OWNER-CONVERSATION`, `SRC-DUNE-IMAGES`
- observed: the durable repository currently contains only derived Issue/spec text, not a source-lock of raw conversation/images
- risk: future audits may preserve the result but lose exact source wording and denominator
- next safe action: skill-concerns #9 may create an attributed source proposal/lock for the bounded owner brief; do not place raw private conversation or image bytes in a public repository without explicit authorization

### `DRIFT-017` — articles/PDFs were referenced but not retrievable in this boundary

- level: `L1 WARN`
- source: `SRC-ARTICLES-PDFS`
- observed: complete bytes were unavailable; only owner summaries/links exist in the session
- disposition: `ABSENT`, retained in denominator
- next safe action: attach exact public URLs/commit/PDF hashes in a later source-refresh run before asserting that every article/PDF problem is represented

### `DRIFT-018` — no general requirement status projection yet

- level: `L1 WARN`
- source: owner proposal for `./noodles requirements status`
- observed: stable requirement IDs are not yet broadly assigned to Issues; storing status now would create a second mutable truth
- next safe action: first land stable requirement identity and typed Issue links, then implement a read-only projection from spec + Issues + PR/merge/closure receipts; never add `requirements-state.json`

### `DRIFT-019` — no-self-authorization is a design law with partial, not universal, enforcement

- level: `L1 WARN`
- source: owner conversation; current separate trusted workflow and #112 evidence model
- observed: candidate/trusted job separation and exact-head provider gates cover repository admission; each future specialized oracle still needs an admitted identity/digest/trusted relation
- next safe action: bind the law into the post-#83 System Specification and apply it per feature/oracle atom rather than create one global self-certifying registry

### `DRIFT-020` — skill-concerns #9 has proposal identity but no admitted implementation

- level: `L1 WARN`
- source: `ed3c/skill-concerns#9`
- observed: no source lock, scripts, tests, evals, admission receipt, Skill-tree digest, or consumer receipt was read back
- next safe action: complete #117 first; use its exact provider-landed pack as the consumer canary, then implement/admit #9 in skill-concerns without copying Tech Lead/Shadow/control-noodle procedures wholesale

### `DRIFT-021` — context pack cannot prove Agent cognition

- level: `L0 OBSERVE`
- source: #117 non-claims
- observed: complete source accounting, bounded task packets, and route pointers are observable; “Agent completely understood everything” is not
- design target: reduce omission probability and make missing ownership/edges explicit, not claim internal cognition

## Shadow delta summary

| Delta class | Current material delta | Disposition |
|---|---|---|
| architecture | #112 changed verification root to mandatory baseline + optional specialized oracle | governing provider fact; rebase #109/#117/#116 interpretations |
| intent/case | owner expanded from latest-atom execution to full conversation/context closure | #117 owns N projection; skill-concerns #9 owns reusable candidate |
| authority | N docs explicitly denied evidence authority; separate trusted/provider gates retained | no promotion allowed |
| lifecycle | #109 stale PR replaced; Issue moved to `awaiting_land`; #117 start edge now satisfied | complete provider readbacks before closure |
| concurrency | #109 and #117 are disjoint; #83 conflicts with #109 | block #83 until #109 land/rebase |
| evidence | #118 candidate/trusted controls passed but exact receipt initially failed on Issue state | rerun exact same head after `awaiting_land`; do not rewrite candidate merely to manufacture green |

## Candidate Tech Lead packets

These are candidate packets only. This file does not create the Issues.

### `PACK-SPEC-CONVERGE`

- start: #109 provider-landed, #83 provider-landed canonical-owner cleanup
- goal: converge the remaining stable System Specification sections and requirement evolution law
- writer: `contracts/system-v1.md`, minimal pointers only
- forbidden: runtime/provider/workflow behavior, fourth hop, mutable status table
- completion: document-route controls, one-owner readback, provider landing

### `PACK-ISSUE-COMPLETENESS`

- start: #82 provider-landed
- goal: resolve one stable requirement ID and require deterministic structural completeness for schedulable Issues
- writer: nearest Issue parser/read-only adapter/tests; coordinate with #98
- checks: absent/duplicate/malformed requirement, missing/nonempty fixed sections, body digest drift, explicit `none` cases
- non-claim: no natural-language semantic-quality oracle

### `PACK-ISSUE-AUDIT`

- start: `PACK-ISSUE-COMPLETENESS` landed
- goal: audit only open/schedulable Issues; attach missing typed fields and correct stale blocker states
- no bulk prose rewrite
- mandatory cases: #45, #65, #116, stale feature markers, #4 write boundary

### `PACK-CONTEXT-SKILL-CONSUMER`

- start: #117 provider-landed
- target: skill-concerns #9
- goal: source-lock the bounded context-closure concern and add hermetic planted omissions/drift tests
- forbidden: second Tech Lead, scheduler, requirement registry, provider mutation authority, private chain-of-thought capture

## Current L3 blocks

At this snapshot only these program paths are L3-blocked by the Shadow review:

1. starting #83 before #109 provider landing/rebase;
2. treating #117 or any N-class document as completion evidence;
3. admitting skill-concerns #9 before both producer controls and the #117 consumer receipt exist;
4. claiming #109 complete from candidate tests/trusted controls without the rerun exact-head receipt and provider merge/closure;
5. claiming the local `/Users/neon/skills-shared` Shadow monitor ran when the path was not available.

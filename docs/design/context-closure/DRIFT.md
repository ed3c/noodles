# Drift and omission ledger

> N-class planning ledger for `CTX-117-2026-08-30-6e46bf9-provider-20260829T212905Z`. Severity is not an execution, provider, or completion verdict. `[SRC-ORDER-117, OWNER_REQUIREMENT, N]`

## Intervention levels

| Level | Meaning | Authority |
|---|---|---|
| `L0 OBSERVE` | Record a material fact or resolved transition. | `N` |
| `L1 WARN` | Work may continue within an explicit evidence ceiling. | `N` |
| `L2 REVIEW` | Reconcile the contradiction before depending on it. | `N` |
| `L3 BLOCK` | Continuing the affected completion path risks identity, authority, writer, or evidence corruption. | `N` |

## Findings

### `DRIFT-001` The required authenticated GitHub CLI path is unavailable

- Level: `L3 BLOCK` for execute CLI validation, provider mutation, and handoff. `L1 WARN` for bounded local documentation.
- Source: `SRC-GH-CLI-ATTEMPT`, `ABSENT`, `N`; `SRC-PROVIDER-READBACK`, `R_REFERENCE`, `N`.
- Observation: `gh` has no authenticated host, so `./noodles issue validate` fails before readback. Direct public REST and `git ls-remote` succeeded.
- Consequence: the snapshot contains current public Issue and PR facts, but the required execute command cannot validate, mutate, or hand off the Issue.
- Safe action: finish reversible local work and local gates. Restore an authenticated `gh` host before provider mutation or formal handoff.

### `DRIFT-002` The earlier full #117 branch never landed

- Level: `L1 WARN`.
- Source: `SRC-OLD-117`, `HISTORICAL_PROJECTION`, `N`; `SRC-GIT-HISTORY`, `REPOSITORY_FACT`, `N`.
- Observation: `origin/agent/issue-117-context-closure@a417a7a...` contains a 1,035-line six-file synthesis. Baseline ancestry does not contain that branch head.
- Consequence: its provider states and owner-conversation synthesis are source material only.
- Safe action: retain useful denominators and trace pointers with explicit historical classification. Do not replay its authority or stale state.

### `DRIFT-003` The landed #124 pack contains pre-merge status text

- Level: `L2 REVIEW`, repaired in this candidate.
- Source: `SRC-PACK-124`, historical projection; `SRC-BASELINE`, repository fact.
- Observation: the prior files described #124 as `AWAITING LAND` and PR #128 as active. Baseline commit `fdce9f8...` is the merge commit for PR #128.
- Consequence: copying the status forward would contradict repository ancestry.
- Safe action: describe #124 as integrated and provider-closed at `2026-08-29T19:37:21Z`. Refresh before later operational use. `[SRC-PROVIDER-READBACK, R_REFERENCE, N]`

### `DRIFT-004` Current Issue and PR denominators were refreshed

- Level: `L0 OBSERVE`, repaired in this candidate.
- Source: `SRC-PROVIDER-READBACK`, `R_REFERENCE`, `N`; historical denominator in `SRC-OLD-117`.
- Observation: GitHub returned 28 open Issues and three open PRs through `2026-08-29T21:28:21Z`.
- Consequence: the pack can name the frozen portfolio and exact PR heads. It cannot project those facts past the snapshot.
- Safe action: refresh the same endpoints and ETags before operational planning.

### `DRIFT-005` The supplied order matches the public provider body

- Level: `L0 OBSERVE` for body equality. `L3 BLOCK` remains for the required CLI validation and handoff path.
- Source: `SRC-ORDER-117`, `OWNER_REQUIREMENT`, `N`; `SRC-PROVIDER-READBACK`, `R_REFERENCE`, `N`; `SRC-GH-CLI-ATTEMPT`, `ABSENT`, `N`.
- Observation: the exact public body matches the supplied role, target, subject, `ready` state, dependency #112, claim, acceptance, and non-claims. The body contains neither a `noodles-feature` marker nor a `noodles-blocker` marker.
- Consequence: order-to-body drift is not present at the snapshot. The execute Skill's exact `./noodles issue validate` step still has no authenticated CLI receipt.
- Safe action: rerun `./noodles issue validate ed3c/noodles#117` before provider mutation or handoff.

### `DRIFT-006` Raw owner conversation is not repository-addressable

- Level: `L1 WARN`.
- Source: `SRC-OWNER-CONVERSATION`, `OWNER_REQUIREMENT` plus `ABSENT`, `N`.
- Observation: prior projections attribute requirements to a conversation dated 2026-08-28 through 2026-08-30. Raw message IDs and bytes are absent.
- Consequence: the pack can preserve attributed requirements, but it cannot prove complete transcript coverage.
- Safe action: keep coverage `PARTIAL`. Add an authorized source lock later if exact transcript identity matters.

### `DRIFT-007` Dune image bytes and original claims are absent

- Level: `L1 WARN`.
- Source: `SRC-DUNE-IMAGES`, `EXTERNAL_CLAIM` plus `ABSENT`, `N`; adaptation in `SRC-SYSTEM`, `REPOSITORY_FACT`, `N`.
- Observation: the old projection names `IMG_6306.png` and `IMG_6315.png`. The repository contains adapted AF requirements, not the image bytes.
- Consequence: local adaptation is traceable. Original-image truth and completeness are not.
- Safe action: keep the original source external. Do not add private images without explicit authorization.

### `DRIFT-008` Article and PDF identities are missing

- Level: `L2 REVIEW` for a claim of full external-source coverage.
- Source: `SRC-ARTICLES-PDFS`, `ABSENT`, `N`; `SRC-LAUREN-PSTACK`, `EXTERNAL_CLAIM`, `N`.
- Observation: titles, URLs, bytes, hashes, and claim mappings were unavailable.
- Consequence: the pack cannot compile or verify their content.
- Safe action: retain an explicit denominator row. A future source refresh must add exact public identities before content-level claims.

### `DRIFT-009` The performance research is frozen at an older baseline

- Level: `L1 WARN`.
- Source: `SRC-RESEARCH-2026-08-29`, `HISTORICAL_PROJECTION`, `N`.
- Observation: the report uses baseline `2f6f60f...` and says that its Issue ordering and measurements became stale after later merges.
- Consequence: session counts, timing, tokens, and causal inferences are not current facts.
- Safe action: cite the exact research section and rerun the bounded benchmark before making a new performance decision.

### `DRIFT-010` Historical skills-shared methods are not current dependencies

- Level: `L1 WARN`.
- Source: `SRC-OLD-117`, historical method pointers; `SRC-PROVIDER-LOCK`, repository fact.
- Observation: the old branch used Shadow Architect and Tech Lead methods from `ed3c/skills-shared@52b29...`. The current lock marks `skills-shared-compat` disabled.
- Consequence: those methods may explain historical compilation choices, but the Golden Path does not depend on them.
- Safe action: use current pinned pstack and control-noodle methods. Keep historical method use attributed and P-class.

### `DRIFT-011` The pstack multi-phase plan is plan-only

- Level: `L0 OBSERVE`.
- Source: `SRC-PSTACK:pstack/skills/poteto-mode/playbooks/multi-phase-plan.md`, `METHOD_SOURCE`, `P`; `SRC-ORDER-117`, owner requirement.
- Observation: the playbook says to write a plan and stop. The execute Skill and order require implementation of one exact atom.
- Consequence: the plan-only stop instruction conflicts with the more specific execute method.
- Safe action: retain its phase and evidence discipline. Skip its standalone plan deliverable and record the skip in the decision trail.

### `DRIFT-012` #83 and #98 status pointers were refreshed

- Level: `L0 OBSERVE`, repaired in this candidate.
- Source: `SRC-PACK-124`, historical projection; `SRC-PROVIDER-READBACK`, `R_REFERENCE`, `N`.
- Observation: #83 is `awaiting_land` through open PR #129 at head `8def7a8...`. #98 is `ready` and depends on closed #82.
- Consequence: the old status statements happen to remain directionally correct, but only the new snapshot supplies current identities.
- Safe action: refresh both provider objects before starting an overlapping atom.

### `DRIFT-013` A remote #45 candidate exists without provider proof

- Level: `L1 WARN`.
- Source: `SRC-GIT-HISTORY`, `REPOSITORY_FACT`, `N`.
- Observation: remote ref `origin/ed3c-noodles-45-0-execute` and open PR #122 both point to `156cb3ea814b947d05c38177fc44511579d6b013`. Issue #45 is marker state `in_progress`. Baseline ancestry does not contain that head. `[SRC-PROVIDER-READBACK, R_REFERENCE, N]`
- Consequence: the branch, PR, and Issue identities are known. They do not prove checks, runtime lease behavior, merge, or closure.
- Safe action: keep the problem `OPEN` until the named live oracle and exact provider landing are read back.

### `DRIFT-014` #116 is integrated, but its broad rationale may remain superseded

- Level: `L1 WARN`.
- Source: merge #123 in `SRC-GIT-HISTORY`, repository fact; old `DRIFT-006` in `SRC-OLD-117`, historical projection; `SRC-SYSTEM`, canonical rule.
- Observation: baseline contains a repo-infra specialized oracle. The old concern was that #112 removed the need for every Issue to declare a feature.
- Consequence: integration proves the exact oracle bytes exist, not that every infrastructure atom needs that oracle.
- Safe action: apply it only when the exact Issue declares the feature and the behavior is relevant.

### `DRIFT-015` Full typed Issue completeness remains unproven

- Level: `L1 WARN`.
- Source: merge #121 in `SRC-GIT-HISTORY`, repository fact; #98 and #120 owners in `SRC-PACK-124`, historical projection.
- Observation: typed dependencies and provider-body digest are integrated. The available source set does not establish landed write-boundary and full requirement-completeness atoms.
- Consequence: dependency schedulability cannot be inflated into complete Issue quality.
- Safe action: preserve separate owners and completion edges for #98 and #120.

### `DRIFT-016` Repository-wide duplicate-owner detection is partial

- Level: `L1 WARN`.
- Source: `SRC-SYSTEM`, current mechanical coverage section; `REPOSITORY_FACT`, `N`.
- Observation: document-route controls and canonical requirement identity are deterministic. Arbitrary prose duplicate-owner detection is not.
- Consequence: AF-03 is not fully enforced across every text file.
- Safe action: use exact finite owner boundaries. Promote a new check only after a reproduced duplicate-owner failure.

### `DRIFT-017` No deterministic context-pack completeness checker exists

- Level: `L1 WARN`.
- Source: `SRC-ORDER-117`, owner requirement; existing controls in `SRC-N-EVIDENCE-CONTROL`; old `DRIFT-015` in `SRC-OLD-117`.
- Observation: existing gates reject N documents as evidence and verify repository structure. They do not prove that every relevant source or statement appears in this pack.
- Consequence: source accounting is bounded review, not universal omission detection.
- Safe action: keep absent sources visible. Create a new executable checker only if planted omissions produce repeatable failures at a finite boundary.

### `DRIFT-018` Start-readiness can still be mistaken for completion-readiness

- Level: `L2 REVIEW`.
- Source: `SRC-SYSTEM`, concurrency section; `SRC-ORDER-117`, physical acceptance.
- Observation: the order says #117 is ready and schedulable because #112 landed. The completion chain still includes local acceptance, exact PR handoff, trusted verification, merge, closure, and reconcile.
- Consequence: starting this work cannot support an L or R completion claim.
- Safe action: keep `S` and `C` labels in `DAG.md`. Report progress and completion separately.

### `DRIFT-019` N-class files could be laundered through evidence fields

- Level: `L3 BLOCK` if observed.
- Source: `SRC-N-EVIDENCE-CONTROL`, `L_REFERENCE`, `N`; `SRC-SYSTEM`, authority law.
- Observation: `noodles.py` rejects `docs/research/` and `docs/design/` paths in machine evidence fields. The planted negative lives in `tests/test_handoff_and_reconcile.py`.
- Consequence: citing this package as a receipt must fail.
- Safe action: run the focused control and scan evidence allowlists before delivery.

### `DRIFT-020` Candidate-modified bytes cannot admit themselves

- Level: `L2 REVIEW` for each new oracle.
- Source: `SRC-SYSTEM`, `EVIDENCE.NO_SELF_AUTHORIZATION.001`; `REPOSITORY_FACT`, `N`.
- Observation: separate trusted jobs and provider gates cover repository admission. Each optional oracle still needs an admitted identity and exact observed-state binding.
- Consequence: a candidate cannot add prose or a self-report and call itself verified.
- Safe action: keep the general law in the system specification and enforce it at each nearest oracle.

### `DRIFT-021` The #117 molecular trace stops before candidate handoff

- Level: `L2 REVIEW` for #117 completion.
- Source: current chain in `TRACEABILITY.md`; `SRC-PROVIDER-READBACK`, `R_REFERENCE`, `N`; `SRC-GH-CLI-ATTEMPT`, absent.
- Observation: the Issue, predecessor, session presence, worktree, branch, and current portfolio are known. Candidate commit, matching PR, checks, handoff, merge, closure, and reconciliation are not yet present.
- Consequence: the exact task is in progress, not complete.
- Safe action: fill each segment only from its owning command or provider readback.

### `DRIFT-022` Context artifacts cannot prove Agent cognition

- Level: `L0 OBSERVE`.
- Source: `SRC-ORDER-117`, explicit non-claims; `OWNER_REQUIREMENT`, `N`.
- Observation: file coverage, source pointers, decisions, controls, and trace segments are observable. Complete understanding is not.
- Consequence: the design target is visible omission and recoverable context, not an internal-state claim.
- Safe action: preserve this non-claim in every refresh.

### `DRIFT-023` Draft PR #125 overlaps the current #117 atom

- Level: `L3 BLOCK` for opening a second #117 PR or handing off an ambiguous head.
- Source: `SRC-PROVIDER-READBACK`, `R_REFERENCE`, `N`; current branch and diff from `SRC-GIT-HISTORY`, `REPOSITORY_FACT`, `N`.
- Observation: draft PR #125 is open at head `c120c6e3ae242bba5b9f7cd3624164bfcc4137b4` for #117. The current Noodle worktree modifies the same six Markdown files from a different branch and baseline.
- Consequence: opening a new PR would create two provider candidates for one Issue. Repointing or closing #125 would mutate provider state and needs one exact convergence decision.
- Safe action: reuse #125 only through a verified fast-forward or an explicitly authorized replacement. Otherwise close it through the owning provider workflow before opening one exact new PR.

### `DRIFT-024` The default branch advanced through carrier atom #134

- Level: `L0 OBSERVE`, repaired in this candidate.
- Source: `SRC-BASELINE`, `REPOSITORY_FACT`, `N`; `SRC-CARRIER-134`, `R_REFERENCE`, `N`; `SRC-WORKTREE-BASE`, `REPOSITORY_FACT`, `N`.
- Observation: the assigned worktree started at merge #128. Default branch later merged #132 and #134. Both atoms changed only `.noodle.toml`; #134 grants configured write access to shared Git metadata.
- Consequence: the six-file content diff is path-disjoint, but candidate delivery still needs current-main ancestry and direct commit, push, and provider readback.
- Safe action: rebase the candidate onto `6e46bf930726b118179dc91b1431fba96aa17851` before final acceptance. Do not infer provider authentication from the carrier configuration.

## Mandatory review checklist

Use the named source pointer for every answer. `[SRC-ORDER-117, OWNER_REQUIREMENT, N]`

- Does every source family appear as present, historical, unknown, blocked, or absent?
- Does every nontrivial statement carry an exact pointer and classification?
- Are live provider facts fresh, or are they marked `UNKNOWN_CURRENT`?
- Are `S` and `C` edges separate?
- Does each owner problem name a denominator and residual?
- Does each active write boundary have one convergence owner?
- Does every molecular trace show missing segments as `TRACEABILITY_GAP`?
- Does any N-class file appear in an evidence, receipt, or allowlist field?
- Does any merged commit get misread as current Issue closure or runtime proof?
- Does any external claim become an acceptance condition without an exact evidence atom?
- Does any repair change the Issue, session, worktree, or provider subject?
- Does any candidate-modified oracle become the sole authority for its candidate?

## Unmechanized planted negatives

These are review probes, not L-class gates. `[SRC-ORDER-117, OWNER_REQUIREMENT, N]`

1. Remove one denominator source. The omission must remain visible.
2. Replace one `C` edge with `S`. The completion claim must stay open.
3. Assign two writers to one durable value. One convergence owner must be chosen before work starts.
4. Cite this package as evidence. The existing N-evidence control must reject it.
5. Copy a mutable Issue, PR, run, or SHA status into `contracts/system-v1.md`. The move must be rejected as a second mutable truth.
6. Mark a merged commit as a closed Issue without provider closure readback. The trace must remain incomplete.
7. Delete the article and PDF `ABSENT` row. The source denominator must be considered incomplete.

## Candidate next packets

These packets are planning suggestions only. They do not create Issues. `[SRC-OLD-117, HISTORICAL_PROJECTION, N]`

| Packet | Start condition | Bounded goal | Forbidden promotion | Current disposition |
|---|---|---|---|---|
| Provider refresh | Public GitHub REST available | Re-fetch exact #117 body, full Issue denominator, full PR denominator, and relevant heads | Do not copy mutable state into the System Specification. | Completed for snapshot; authenticated mutation remains blocked by `DRIFT-001` |
| External source refresh | Exact authorized URLs, files, or hashes available | Attribute each article, PDF, and image claim | Do not publish private bytes or claim source truth. | `HOLD` |
| Context compiler evaluation | #117 provider-landed consumer exists and a repeated omission is reproduced | Test finite omitted-source, false-edge, duplicate-owner, stale-head, and N-evidence cases | Do not build a scheduler, requirement registry, or evidence database. | `HOLD` |
| Issue completeness | Provider confirms #82 landed, #98 ready, #120 ready, and #83 awaiting land | Close exact typed write-boundary and structural completeness gaps | Do not claim natural-language semantic quality. | `PARTIAL`; #83 completion edge remains open |

## Current L3 blocks

The following paths are blocked at this snapshot. `[SRC-GH-CLI-ATTEMPT, ABSENT, N]` `[SRC-PROVIDER-READBACK, R_REFERENCE, N]` `[SRC-N-EVIDENCE-CONTROL, L_REFERENCE, N]`

1. Claiming the required `./noodles issue validate` receipt or an authenticated schedulability readback.
2. Opening or handing off an exact PR without restored GitHub provider access and resolution of draft PR #125.
3. Treating this package or its decision trail as L or R evidence.
4. Claiming article, PDF, image, or raw-conversation completeness.
5. Claiming task completion before candidate head, local gates, PR, trusted receipt, merge, closure, and reconciliation are read back.

# noodles System Specification v1

This file is the canonical, low-change owner for system-level intent, invariants, authority boundaries, and stable requirement definitions in noodles. It is a constitution, not a project wiki, mutable status store, execution transcript, or correctness oracle.

Executable authority remains in the nearest executable contract/test, trusted workflows, Git, and GitHub readback. Mutable Issue, PR, branch, commit, workflow-run, receipt, and runtime state stays with its owning provider surface and MUST NOT be copied here as current truth.

The repository document route is `AGENTS.md` → this file → `issue-named executable contract/test`, with three nodes maximum. Concretely:

```text
AGENTS.md
  → contracts/system-v1.md when the exact Issue names a system requirement
  → issue-named executable contract/test
  → stop document traversal
```

The exact Issue selects that final executable boundary. A fourth architecture-document hop is not part of the Golden Path.

## 1. Purpose and non-goals

noodles exists to let exact GitHub Issues progress through isolated Agent execution, physical verification, and provider landing without making a Human Verifier the routine correctness oracle. The system optimizes for bounded autonomy, exact provenance, target-local verification, and low architectural entropy.

noodles is not a second Agent OS. It does not replace Noodle scheduling/worktrees, pstack engineering routing, Git, GitHub provider authority, or target-local domain contracts. It does not persist derived status that can be reconstructed from provider facts.

### SYSTEM.PURPOSE.001

The system MUST separate stable intent, intended work, execution, physical verification, and landed provider reality so that no layer can silently impersonate another authority.

## Enforcement hierarchy

Enforcement descends from repository shape, to static/CI gates, to mechanical diagnostics, to soft Agent guidance. Put an invariant at the strongest available layer: the shortest local path should preserve architecture by default; invalid structural states should fail in executable gates; known invalid patterns should name the supported path; rules and Skills explain choices but grant no authority.

Issue admission and completion evidence remain separate seams. Every repository mutation receives the built-in baseline acceptance contract. An optional specialized oracle only adds evidence at completion and never replaces the built-in baseline acceptance contract. Verification-root changes use explicit owner authority plus the same mechanical and provider gates; there is no Issue-number bypass.

### ENFORCEMENT.LADDER_MIGRATION.001

An invariant whose rejection has been paid twice for the same reason MUST migrate up this hierarchy: it is re-sited at the strongest layer that can reject the candidate before the cost is incurred, and its diagnostic MUST name the supported path rather than only the violation. Prior-Issue history of a repeated rejection is an N-class recollection and does not discharge the migration.

Trusted-transition rejection - a candidate changing a value the default-branch verifier pins - has exactly one supported path, the staged transition: widen acceptance on the default branch, then flip the pinned value, then retire the widened acceptance. Rerunning, rebasing, or re-pushing the same candidate cannot resolve it, because the rejecting verifier is the default branch's, not the candidate's.

Admission boundary: `./noodles verify --trusted-preview`, which materializes the default-branch tree from the git object database, runs its test modules against the working-tree candidate under the trusted job's own env contract and command read back from the trusted workflow rather than restated, and reports the exact modules CI would red together with that staging recipe. Controls in `tests/test_trusted_preview.py` plant a pinned-literal change, require the local red plus the recipe, require green against a simulated staged default branch, and require an absent trusted controls step to fail closed rather than report green.

The preview is local shift-left tooling and carries no L or R authority; the trusted CI job remains the only verification authority, and a preview receipt never substitutes for it.

## Agent-friendly architecture

Predictable local Agent behavior is an architectural input. An Issue-solving Agent tends to copy the nearest working pattern, edit the file already in context, choose the shortest passing path, preserve code whose unseen callers are uncertain, and follow requested implementation details even when wider invariants are not visible. Noodles responds by shaping ownership, paths, diagnostics, and gates so the least surprising local action is also the system-correct action.

The design target is local-obvious → globally-correct. The conventional path should require fewer decisions than a shortcut, and the obvious meaning of “done” should be the physically verified meaning.

| ID | System requirement | Admission boundary |
|---|---|---|
| AF-01 | The conventional path has fewer decisions than a shortcut: exact Issue, Noodle-owned isolated worktree, nearest executable contract/test, mandatory baseline acceptance, every applicable specialized oracle, exact-head PR, provider readback. | Routing remains P-class; named executable/provider gates retain only their existing L/R authority. |
| AF-02 | A forbidden dependency, structural state, or authority transition fails mechanically with a diagnostic that names the supported path. | A prohibition is enforced only where a deterministic gate or provider readback rejects it. |
| AF-03 | Every durable value has one obvious owner and one admitted writer or transition surface. Copies are read-only projections, never competing truth. | Ownership prose is N-class until the relevant readback/gate enforces it. |
| AF-04 | Repository mutation occurs only in an admitted isolated worktree owned by Noodle; the shared control checkout is read/reconcile only. | Noodle order/session/worktree readback plus local containment controls. |
| AF-05 | Bootstrap and recovery exceptions are exact, narrow, bounded atoms with receipts and cannot become a second normal path by precedent. | Exact subject/boundary plus nearest executable and provider admission. |
| AF-06 | The locally obvious completion path reaches mandatory exact-head baseline acceptance and every applicable specialized physical oracle before completion or authority is claimed. | Exact-head L evidence followed by existing GitHub R gates. |

### Durable owner and writer map

“One writer” means one admitted mutation or transition surface for a durable value, not one process with all authority.

| Durable value or truth | Canonical owner | Admitted transition surface | Required readback |
|---|---|---|---|
| Stable system intent and requirements | `contracts/system-v1.md` | Exact specification atom | Direct source readback plus route controls |
| Exact Issue goal, target, dependencies, and lifecycle | GitHub Issue | Configured backlog/Issue contract surfaces; trusted lander for closure | Exact provider Issue body/state |
| Scheduling, orders, process isolation, and worktrees | Noodle | Noodle runtime/control APIs | Exact order/session/worktree state |
| Engineering playbook selection | pstack | pinned `poteto-mode` route | Route packet is P-class only |
| Baseline/specialized acceptance | nearest noodles contract/test/oracle | target-local executable verification | operation, observation, artifact/head/tree readback |
| Candidate source | Git in Noodle-owned worktree | repository-mutating Agent in that worktree | status/head/tree/residue |
| Default-branch source, merge, and Issue closure | GitHub | trusted verify/land workflow | exact-head receipt, merge parent, branch head, closure |
| Post-provider reconciliation | noodles + Noodle | `./noodles reconcile` and Noodle control API | provider ancestry, command acknowledgement, released order |

### Design consequences

- **Shortcut failure.** A shortcut is structurally unavailable or fails with a diagnostic naming the supported Golden Path; silent fallback or a second writer is an architecture defect.
- **Nearest contract.** Domain knowledge belongs at the nearest executable boundary. Prose, Skills, route packets, and reviews remain P or N until the named operation executes and its state is read back.
- **Isolation.** No repository-mutating Agent edits the shared control checkout.
- **Exceptions.** Recovery/bootstrap work names one exact subject, trigger, write boundary, completion condition, receipt, and unsupported case.
- **Subtraction.** Before adding a registry, router, framework, manager, or document layer, demonstrate a physical failure the nearest existing seam cannot close.
- **`poteto-mode`.** pstack chooses engineering playbooks probabilistically and owns neither correctness nor GitHub authority.
- **Verification architecture.** Agent-friendly completion means mandatory baseline acceptance, every applicable specialized physical oracle, exact observed-state readback, exact candidate-head/tree binding, and provider admission.

### Current mechanical coverage and follow-up gap

The existing document-route controls verify the declared three-node route, resolve static pointers, and reject a planted fourth architecture-document hop. The AF rows above remain unique by direct deterministic readback. Repository-wide semantic duplicate-owner detection is not yet mechanically proven; until a finite canonical document set and ownership-key seam exist, do not claim that AF-03 is fully enforced across arbitrary prose.

## 3. Authority model

P/L/R/N are authority classes, not confidence levels.

- **P — probabilistic guidance:** model reasoning, pstack routes, reviews, hypotheses, plans.
- **L — local deterministic gate:** executable exit/result with exact subject, controls, readback, and residue where applicable.
- **R — provider-enforced readback:** protected-branch/check/merge/event/closure/provider state.
- **N — non-claim:** documentation, diagrams, inventory, metrics, external claims, or unverified proposals.

### AUTHORITY.NO_LAUNDERING.001

P or N MUST NOT gain L or R authority through repetition, model consensus, prose, moved headings, a passing unrelated test, or a second Agent saying “LGTM”.

### EVIDENCE.NO_SELF_AUTHORIZATION.001

Candidate-modified bytes MUST NOT be the sole authority that admits the same candidate. Trusted/default-branch verification or a pre-admitted oracle identity/readback must independently bind the candidate subject and exact head/tree.

The stable claim classes currently include inventory/containment/provider-pin/document-route/baseline/dependency L gates and protected-branch/exact-head/merge/closure R gates. Their executable definitions remain with the nearest implementation/tests; this specification does not duplicate their mutable receipts.

## 4. Ownership model

### OWNERSHIP.SEPARATION.001

Noodle owns scheduling, orders, process isolation, and worktrees. pstack owns P-class engineering playbook selection. noodles owns target-local correctness extensions, evidence compilation, domain invariants, and policy hooks. Git owns candidate source identity. GitHub owns protected default-branch and landing/closure reality. A target repository owns its own mutation and verification authority.

No layer may become a substitute scheduler, generic worktree manager, generic review framework, mutable requirement-status store, or provider authority merely because it can observe another layer.

### OWNERSHIP.TASK_PROFILE_SOURCE.001

`policy/fitness.json` is the only committed definition of the Codex task profiles. The repository gate, the schedule output contract, the carrier shim, and the contract tests MUST derive their expectation from that one key rather than pin a second copy, so a profile transition touches one file plus at most one staged acceptance. A surface that cannot read the definition — Noodle's own runtime config and frozen provider fixtures — is an exemption declared in the same policy file, not an undeclared duplicate.

The L admission boundary is `verify_repository`: it rejects any tracked file outside the declared exemptions that writes an admitted task model literally, and it rejects a target tree whose profiles differ from the verifying engine tree's definition. The carrier fails closed before spawn when that single definition is unreadable or is not exactly two well-formed schedule/execute profiles, and continues to reject unadmitted, ambiguous, or reasoning-overriding launches.

## 5. Golden Path invariants

```text
exact GitHub Issue
  → deterministic admission
  → Noodle order + isolated worktree
  → pinned poteto-mode engineering route
  → smallest independently useful implementation atom
  → nearest executable contract/test/oracle
  → exact-head L evidence
  → trusted GitHub verification
  → exact-head R landing and closure readback
  → local reconciliation
```

### GOLDEN_PATH.001

Implementation is done only when the candidate has complete local evidence and a PR is handed off; repository reality is done only after trusted provider landing, default-branch/closure readback, and reconciliation. Agent self-report is never the second state.

### GOLDEN_PATH.PROVENANCE.001

Every authoritative completion path MUST preserve exact Issue subject, repository, candidate head/tree, verification identity, and provider landing identity across the boundary that consumes them.

### DEPENDENCY.IMPLICIT_DISCOVERY.001

A discovered implicit dependency MUST become an explicit probe, gate, or typed marker within one atom. `./noodles preflight` is the execute-environment admission boundary. It probes the Python runtime, provider network reach, GitHub authentication readback, Git metadata writes, and feature-verifier availability. The command rejects a missing capability before source edits and does not repair the environment.

## 6. Verification architecture

Tests pass != full product verification when the Issue claims CLI, UI, runtime, performance, provider, or other observable behavior beyond repository acceptance.

Every repository mutation receives mandatory baseline acceptance. A specialized oracle is additive when the Issue declares a feature/behavior requiring one; it never replaces the baseline.

### VERIFICATION.ORACLE.001

Every completion claim whose observable behavior extends beyond static repository state MUST execute the nearest target-local physical oracle and bind the observation to the exact candidate head/tree.

### VERIFICATION.FEATURE_MAP.001

A supported feature SHOULD minimally map feature → code surface → observable transition/journey → physical oracle → evidence. These facts remain target-local; a global registry is not required. Changed supported code must not silently escape verification: it either maps to required journeys/oracles or has an explicit mechanically justified non-case.

### VERIFICATION.FEATURE_MAP.002

When an Issue declares a `noodles-feature:` oracle, `noodles.execute_handoff` MUST compile the exact base..head changed files through that feature's target-local Feature↔Code edge before it flips the Issue to `awaiting_land`. The feature's declared code surface is its one changed code node and its `transitions`/`journeys` are the required-journey denominator; a declared journey whose node never appears in the base..head diff is an unmapped journey and fails closed before the state mutation, because the admitted oracle would otherwise pass vacuously over code the candidate never touched. Changed files are read from the same trusted provider compare readback as `VERIFICATION.COMPONENT_SURFACE.001`, never from a self-report, so a stale or wrong-head receipt cannot launder the mapping. A no-feature-impact subject passes only through the mechanically checked non-case - no feature marker, which forces the acceptance evidence to carry no specialized oracle - and ownership is never inferred from changed path names.

### VERIFICATION.EVIDENCE_BINDING.001

Authoritative evidence MUST bind the requirement/Issue subject, target repository, candidate head/tree, verification/oracle identity, observation/result, and residue outcome. Stale, wrong-subject, wrong-repository, wrong-head/tree, or self-authorized evidence fails closed.

### VERIFICATION.COMPONENT_SURFACE.001

Every schedulable Issue MUST declare exactly one owned component through a `noodles-component:` marker naming a component in the repo-owned map `policy/components.json` (one file, component → path globs; no per-issue filename lists, no policy DSL). Trusted verification MUST compute the candidate's changed files against the merge base from provider compare readback and fail closed when any changed path escapes the declared component's admitted surface, naming the offending paths and the declared component. The admission boundary is the trusted `noodles.py github verify-pr` gate reading the component map from the trusted default-branch checkout, so candidate-modified map bytes never widen the candidate's own admitted surface. The gate bounds where a mutation lands, not intra-component quality; a legitimately cross-component atom declares a component whose admitted surface spans it (the contracts-owned `contract` component), never skips the marker.

### VERIFICATION.COMPONENT_INTRODUCTION.001

A candidate that introduces a new component - a new pinned entry in a `policy/*.lock.json` dependency lock, or a new top-level runtime module - MUST be driven by an Issue whose body answers both gate questions in a machine-detectable `## Component introduction` section: "which invalid state does this make impossible?" and "why can't strengthening the nearest existing contract close the same failure?". Detection is deterministic and diff-derived: `noodles.introduced_components` compares the candidate tree against the trusted default-branch tree, identifying a pinned unit by its container path rather than its pinned scalar, so a version bump of an existing entry is out of scope by construction and needs no section. The admission boundary is the trusted `noodles.py github verify-pr` gate, which fails closed naming every introduction and every unanswered question; the same detector runs inside `verify_repository`, so `./noodles verify --json` reports the identical classification locally.

The gate demands that the answers exist and bind to the exact introducing diff. It does not score them, and it never substitutes for `COMPLEXITY.SUBTRACT.001`: a scored-good answer is still P-class. Mutation locality of already-admitted components remains owned by `VERIFICATION.COMPONENT_SURFACE.001`.

## 7. Autonomy architecture

### AUTONOMY.NO_HUMAN_VERIFIER.001

Human review MUST NOT be required as the routine correctness oracle. Human involvement is limited to goal setting, constraint changes, genuine product preference, root-authority transitions, or admitted escalation that cannot be reduced to an executable/provider fact.

`/goal`, `/loop`, and `/swarm` are P-class search/decomposition/parallelism policies, not runtime authority primitives. They may increase coverage or throughput but cannot authorize completion.

### AUTONOMY.BOUNDED.001

Autonomous retry/search MUST terminate on L+R success or fail closed on exhausted budget, invariant violation, unavailable required oracle/provider, unsupported capability, or a true product decision. Retry is not evidence.

### AUTONOMY.SUPERVISED_RUNNER.001

Unattended operation MUST NOT depend on an operator-session artifact. The repository owns the supervised runner (`./noodles supervise`): it restarts the daemon generation after generation, bounds each generation by a rotation deadline matched to the installation-token lifetime, terminates a generation whose output has gone silent past the wedge deadline, and cools down on a provider rate limit by reading the live bucket — a full primary bucket classifies the failure as secondary limiting and takes the short window, an exhausted bucket waits past `reset`. Machine-local credential material stays untracked: the runner refreshes a generation's token only by executing the operator-configured `NOODLES_TOKEN_COMMAND` and never persists its output.

Before every generation the runner heals exactly the death classes that physically stopped the fleet, and no more. A control checkout ahead of or diverged from the provider is reset only when the reset is content-aware lossless: every non-merge commit in `provider..local` is contained in some remote ref, because a daemon-made merge commit carries no unique content. When real content commits are not contained, the lineage is first salvage-pushed to a dated remote ref and the reset proceeds only after that push reads back at the local tip; a failed salvage push refuses the reset. A lease naming a provably dead pid is cleared, and clearing it cures the matching status ghost (`loop_state` live with no lease held), which is stale by construction and which `daemon_lease.reject_existing_lease` otherwise refuses to start over. A lease held by a live pid, an unreadable lease, and a dirty or non-default-branch control checkout all fail closed.

Admission boundary: `heal_control_checkout`, `rate_limit_cooldown`, `rotation_env`, `run_supervised_generation`, and `supervise` in `noodles.py`, with planted per-class controls in `tests/test_supervised_ceremony.py` — an unsaved-content lineage whose salvage push is planted to fail, a merge-only divergence, a live-pid lease, a planted status ghost, a wedged generation that never exits on its own, a rotation deadline, and burst/exhausted rate-limit buckets.

### AUTONOMY.CEREMONY_ENTRYPOINT.001

A convention that every agent must remember at every call site is a defect of shape, not of discipline. Repeated cross-agent ceremonies MUST exist as executable entrypoints under `./noodles ceremony <verb>`, so the shortest orchestration path is the correct one and the prompt layer keeps only pointers:

- `commit` and `rebase` apply the repository commit identity from `policy/github.json` inline with `git -c`, never by writing git config into a checkout other sessions share, and read back the resulting author/committer identity; a rejected commit unstages exactly the paths it staged, so the next session's commit cannot carry them under its own message.
- `run` selects a workflow run by name against the provider-read branch tip.
- `rerun` fails closed unless the selected run's `head_sha` equals that same provider-read branch tip, because rerunning a stale head cancels the live head's run under the per-PR concurrency group; `--dry-run` proves the guard without spending the rerun.
- `gh` routes through the tracked `.agents/bin/gh` carrier of `PROVIDER.CALL_PACING.001` with argv, stdout, stderr, and exit code unchanged.

Admission boundary: the `ceremony_*` entrypoints in `noodles.py` with planted controls in `tests/test_supervised_ceremony.py` — a planted foreign git config that must not reach the commit, a rejected commit whose staged paths must be gone afterwards, a conflicting rebase that must abort and leave no in-progress state, a stale-head run id that must be refused, and a carrier-routed `gh` invocation.

## 8. Organizational learning

### LEARNING.EXECUTABLE.001

Repeated Agent failure may become durable organizational knowledge only through failure evidence → P-class lesson hypothesis → independent reproduction → non-case → eval → executable test/lint/contract/oracle → planted negative → regression. A single anecdote does not justify a new global rule.

New executable knowledge belongs at the nearest failure boundary, not by default in `AGENTS.md`, a global registry, or a generic policy file.

### LEARNING.CLOSURE_DISPOSITION.001

Retiring a marker-bearing Issue as `not_planned` is a contract event, not knowledge loss. A bare retirement deletes the reasoning chain, so the same proposal returns weeks later and is re-litigated at full cost; a landed closure is exempt because the merge is already its strongest receipt.

The disposition receipt is a comment on the closing thread carrying three elements in a machine-parseable shape: **payload custody**, one line routing every absorbed half to the Issue that now owns it (`PAYLOAD CUSTODY ...: <half> -> owner/repo#N; ...`); a **falsifiable reopen condition**, one line naming the physical evidence that would revive the retired path (`FALSIFIABLE REOPEN CONDITION: ...`); and a **trade-off record**, one line stating what that path would buy and what it costs (`TRADE-OFF RECORD:`).

Admission boundary: the deterministic sweep in `disposition_contract.py` (`sweep_closure_dispositions`), executed by `./noodles reconcile`. It reads back every closed-as-not-planned Issue of each admitted repository by exact paged provider readback — a page walk that overruns its bound fails closed rather than letting a partial page read as complete — filters to those bearing their own exact `noodles-subject` marker, and validates the closing thread. A retirement missing any element is flagged with a diagnostic naming the missing elements and the supported path, then reopened into `blocked` with an owned blocker so a retired atom never re-enters scheduling as work; every flag, body patch, and reopen is confirmed by direct provider readback. Marker-bearing is deliberately weaker than a full contract parse: a retired Issue may carry a body its own parser now rejects, and that is not its closure's defect.

Planted controls in `tests/test_disposition_contract.py` hold the boundary: `ed3c/noodles#151`'s verbatim closing receipt in `tests/fixtures/closure-disposition-receipt.json` is the positive fixture and must sweep clean, a planted bare closure must be flagged and reopened as blocked naming every missing element, and each element planted absent alone must be the only defect reported.

The check reads receipt shape, never whether the trade-off is wise. Legibility becomes mechanical; the judgment stays with the closer, and this gate grants no L or R authority over that judgment.

## 9. Concurrency model

### CONCURRENCY.INDEPENDENCE.001

Correctness MUST NOT depend on a fixed numeric `max_concurrency`. It depends on N-independent invariants: truthful runtime lease/ownership, exact provenance, disjoint admitted mutation boundaries, and duplicate/open-PR exclusion. Numeric caps are capacity controls, not correctness proofs.

Start-readiness and completion-readiness are distinct. A task may start independently while still requiring provider-landed predecessor facts before it may complete or land.

### CONCURRENCY.DECLARED_CAPACITY.001

A repository declaring `.noodle.toml` `[concurrency] max_concurrency > 1` MUST carry `policy/concurrency-proof.json`, recording per N-independent invariant (`I1` lease `ed3c/noodles#45`, `I2` provenance `ed3c/noodles#46`, `I3` boundary disjointness `ed3c/noodles#98`, `I4` open-PR correlation `ed3c/noodles#99`) the landed subject, the provider receipt digest, and the planted-negative test identifiers that keep that invariant alive, plus a `known_residuals` list naming at minimum the scheduler executing in the primary checkout (upstream `ed3c/noodles#85` territory) and out-of-entrypoint writers to the shared checkout (`ed3c/noodles#46`'s own non-claim). The gate asserts the lock exists, parses at schema 1, records exactly those four invariants each with a subject, a 40-character receipt digest, and at least one named control, and that every named identifier resolves to a real `tests.module.Class.test_name` in the tracked suite — resolved with `ast` against the tracked source rather than by importing it, so verify stays side-effect free. The declared number itself is never bounded above: the evidence ceiling replaces the numeric stop-loss (Chef decision 2026-08-29), and N-dependent behaviour — per-lane wall time, repair rate, provider throttling — stays report-only in `./noodles metrics` and never becomes a gate. Non-claims: the lock proves the invariants were admitted, not future liveness or resource sufficiency at any particular N; it does not cap, recommend, or tune any concurrency value; the receipt digest is a recorded provider fact no gate re-reads; and existence of a named control is not evidence of what that control asserts, so a gutted test that kept its name still satisfies the lock. Admission boundary: `skill_contract.validate_concurrency_proof` called from `noodles.verify_repository`, with the shipped-lock positive and the missing-lock, nonexistent-control, single-lane-no-lock, and unbounded-N controls in `tests/test_schedule_contract.py`.

### CONCURRENCY.CLAIM_SCOPE.001

A claimed subject MUST exclude only its dependency-connected component from admission, never its whole repository: components are the connected components of the typed-dependency graph among open issues within one repository, and `max_useful_workers` equals the number of unclaimed components with schedulable members. A live claim whose contract cannot be parsed has unknown edges and fails its repository closed. Admission boundary: `schedule_domain.schedule_decision` with its dependency-component, claimed-exclusion, and malformed-claim controls in `tests/test_schedule_claim.py`.

### CONCURRENCY.WRITE_BOUNDARY.001

Two concurrently admitted lanes MUST have disjoint declared write surfaces, so two green worktrees cannot collide at landing (invariant I3 of the N-independent concurrency proof). Each Issue contract carries exactly one typed `noodles-write-boundary:` marker of exact relative path prefixes, with an explicit `none` for a lane that reserves nothing; prose, absolute, parent-escaping, or otherwise ambiguous boundaries are never parsed and read as undeclared. Admission rejects a candidate order whose boundary intersects any active order's boundary — one declared prefix path-containing the other, matched segment-wise so `tests` never collides with `tests2` — naming both subjects and the intersecting prefix, and rejects a candidate whose own boundary is missing or ambiguous; both rejections leave no provider ref. An active lane whose own boundary is undeclared could write anywhere and blocks overlapping candidates closed. Disjointness is proven only from declared prefixes: a truthful declaration is a contract input whose honesty is a review/landing concern, not proven here, and this does not serialize disjoint work. Admission boundary: `noodles.schedule_publish` reading each candidate's boundary through `noodles.parse_issue_contract` and each active lane's through the schedule snapshot, with `issue_contract.parse_write_boundary` and `issue_contract.boundary_conflict`, held by planted overlapping-rejected, disjoint-admitted, nested-prefix, active-lane, and undeclared-fail-closed controls in `tests/test_schedule_claim.py`.

### CONCURRENCY.WORKTREE_PROVENANCE.001

Every repository-mutating execute handoff MUST bind one exact order to one exact Noodle session, one Git-registered worktree, one non-default branch, one candidate head, and one reconciled provider base (invariant I2 of the N-independent concurrency proof). The reused `validate_handoff_session` boundary ties `NOODLE_SESSION_ID` to that session's `spawn.json` worktree path and to the exact `[order:…]` event; the same admission then reads Git's own worktree registry — no second registry and no worktree creator is introduced here — and rejects a foreign Git common directory, an unregistered worktree, a detached HEAD, the shared default-branch control checkout, a branch that is not the subject's exact execute branch, the same branch checked out in a second registered worktree, a worktree path claimed by a second session, a candidate head that drifted from the head the exact-head handoff boundary already proved, and a branch that does not contain the admitted provider base. Each rejection carries its own diagnostic and fires before any Issue state or handoff mutation, so a rejected candidate leaves no provider residue. The base is reduced physically, not asserted: the control-checkout gate proves provider-exact `HEAD` before spawn, pinned upstream Noodle creates the worktree from that `HEAD`, and this readback proves the resulting branch contains that exact base as carried by the pull request's own base SHA. Two disjoint Issues therefore pass simultaneously only with distinct orders, sessions, registered paths, and branches. This does not stop arbitrary software outside the admitted entrypoints from editing the shared checkout, does not prove candidate correctness, and does not serialize independent work. Non-claims: the base *value* is trusted as the pull request's own `base.sha` field, not independently re-derived — only its *containment* in the candidate branch is physically reduced via `git merge-base --is-ancestor`, which admits any ancestor including the repository root commit, not exclusively the current default-branch tip. The unregistered-worktree rejection (`entry is None` on the registry lookup) is unreachable by construction once the git common-directory check has already passed for the same `root`, so it carries no planted negative; it is a fail-closed guard against a downstream `AttributeError`, not a proven rejection of a reachable state. Admission boundary: `noodles.execute_provenance_admission`, called by `noodles.execute_handoff` before `issue_set_state`, over `noodles.registered_worktrees` and `noodles.session_worktree_paths`, with planted reused-path, duplicate-active-branch, default-branch, detached-head, foreign-worktree, wrong-session, stale-base, unfetched-base, prunable-entry, and branch/head drift controls plus a live two-worktree provenance canary in `tests/test_execute_provenance.py`, and the pre-mutation control in `tests/test_handoff_and_reconcile.py`.

### CONCURRENCY.OPEN_PR_CORRELATION.001

A subject that already has an open pull request MUST NOT be admitted into a fresh execute attempt (invariant I4 of the N-independent concurrency proof). `CONCURRENCY.WORKTREE_PROVENANCE.001`'s duplicate-active-branch control cannot see this class: a second attempt carries its own branch, so the subject's exact execute ref is free and the schedule snapshot reads the subject as unclaimed. Execute admission therefore correlates against the provider's own open pull request list on two independent keys — a head branch equal to the subject's exact execute branch, and the exact one-line `Refs owner/repo#N` body every pull request here must carry — and refuses when either matches, naming every matching pull request and the repair entrypoint that owns an existing pull request. The refusal fires before the default-branch head read and before `noodles.claim_execute_branch`, so a refused candidate creates no provider ref. The correlation keys on the exact subject: a sibling's in-flight pull request never starves an unrelated subject. Correlation and the readback that feeds it are the single exit `noodles.matching_open_pull_requests` — paginated the way `noodles.open_issues` already is, so a match past the provider's first page of open pull requests is not silently missed. Landing stays fail-closed under the same race in the other direction: two lanes verified over one base are both green, but after the first lands the second's verification no longer describes the current default branch, so its merge is refused and the pull request routes to the landing train's ff-only rebase instead of merging a stale base. Non-claims: this does not implement repair, close pull requests, or replace GitHub's strict required-status-checks; the landing half is a regression control over already-shipped behaviour (production evidence: PR #80 drift refusal, PR #68 ff-only), not new enforcement; the per-repository open-PR list is re-read once per surviving candidate rather than hoisted per repository, which bounds provider call count by candidate count, not by an accepted cap; and `repair_contract.find_open_pr_for_subject` — the repair entrypoint the refusal names — still correlates on the PR body alone, so a branch-matched/body-drifted PR that this refusal catches is not yet findable by `./noodles repair` (tracked at `ed3c/noodles#272`, blocked on widening `repair_contract.py`'s declared component first since that map is read from the trusted default branch, not the candidate). Admission boundary: `noodles.matching_open_pull_requests` called from `noodles.subject_open_pull_requests` (`noodles.schedule_publish`, emitting the `open_pr_exists` status with `noodles.OPEN_PR_REPAIR_OWNER`), with the planted body-correlation, lane-branch-correlation, unrelated-sibling-admitted, and beyond-first-page controls in `tests/test_schedule_claim.py`, and the landing-race control plus its up-to-date planted negative in `tests/test_landing_train.py`.

### CONCURRENCY.RECEIPT_VERBATIM.001

The schedule cycle receipt is the single frontier authority and the skill layer retells it verbatim. Every publish outcome MUST carry a status drawn from the machine-owned status set together with that value's exact fixed meaning, so a status name never has to be interpreted from code position; `not_in_winners` names the absence of a subject from the computed winner set and MUST NOT be read as another executor's claim. A published cycle summary MUST quote the receipt's `frontier`, `winners`, `max_useful_workers`, and per-subject status lines byte-for-byte rather than re-deriving or paraphrasing them. Admission boundary: `skill_contract.validate_cycle_receipt` in `./noodles verify` rejecting a receipt whose status value is undefined or whose meaning drifted, `skill_contract.validate_cycle_summary` behind `python3 skill_contract.py summary` rejecting a summary that contradicts the receipt, and the required schedule-skill contract phrases in `skill_contract.validate_backlog_scheduler`, with planted-negative controls in `tests/test_schedule_claim.py` and `tests/test_schedule_contract.py`.

### CONCURRENCY.PROMOTION_SEAM.001

The transient `orders-next.json` → `orders.json` promotion is owned by the pinned upstream `poteto/noodle` runtime recorded in `policy/runtime.lock.json` (release `v0.1.5`), reached through the `noodle start` loop's `build.promote_orders_next` step; Noodle alone promotes, and this repository MUST NOT add a local watcher, second scheduler, polling guard, or runtime-file race to re-implement it. Physically measured against the exact locked binary, that upstream seam re-validates only the compact-orders **schema**: a schema-invalid `orders-next.json` is renamed to `orders-next.json.bad` and never promoted, but any schema-valid payload written directly to `orders-next.json` promotes verbatim. The upstream seam does NOT enforce the semantic-authority rules that `skill_contract.validate_schedule_output` and `noodles.schedule_publish` enforce at the local `python3 skill_contract.py publish` gate — self-schedule ownership, active non-schedule order preservation, admitted-repository (foreign) exclusion, and duplicate-subject exclusion all promote through a direct write. The runtime CLI and config expose no pre-promotion validation hook, output adapter, or permission boundary to inject those checks, and the cook permission profile necessarily grants `.noodle/` writes because the scheduler itself writes `orders-next.candidate.json` there; a direct write to `.noodle/orders-next.json` therefore bypasses the semantic gate whose only binding is the P-class schedule-skill publish-command contract. Disposition for the direct-write bypass is ADAPT_EXTERNAL/HOLD: closing it requires an external-owner change in `poteto/noodle` — a pre-promotion validation hook or a permission boundary denying cook writes to `orders-next.json` — recorded for a follow-up implementation atom; this atom admits the seam's exact reach and preserves the source-backed blocker rather than substituting an unsupported local mechanism. Admission boundary: the guarded live control `test_pinned_runtime_promotion_seam_covers_schema_not_semantic_authority` in `tests/test_schedule_contract.py`, which plants each subject by direct write to `orders-next.json`, runs the exact locked runtime binary through `runtime_contract.resolve_locked_runtime_binary`, and reads the promoted stage's own fields back (not mere subject-id membership, which a pre-existing active order or Noodle's own auto-injected `schedule` bookkeeping order could satisfy regardless of enforcement) as the planted-negative against schema-drift quarantine as the positive control; the local-gate half of the contrast is split across two callers and both are proven — self-schedule ownership and active non-schedule order preservation by `skill_contract.validate_schedule_output`, exercised in the same test via `local_publish`, and admitted-repository (foreign) exclusion and duplicate-subject exclusion by `noodles.schedule_publish`, exercised by `test_foreign_repository_order_is_rejected_before_provider_call` and `test_duplicate_subject_order_is_rejected_before_provider_call` in `tests/test_schedule_claim.py`; the skill-instruction binding is held by `test_schedule_skill_without_deterministic_publish_gate_is_rejected`, which rejects a raw `mv` that skips the publish gate.

### CONCURRENCY.RUNTIME_LEASE.001

`./noodles start` MUST admit at most one truthful upstream Noodle daemon per repository; a ghost `status.json`, stale lease, foreign lease owner, listener-less child, or unrelated `127.0.0.1:3210` occupant fails closed with a distinct diagnostic. Admission boundary: upstream `.noodle/noodle.lock` readback, exact spawned-child pid identity, `lsof` listener ownership, live `/api/snapshot` response, `.noodle/status.json` loop state, planted fake-alive controls, and own-child-only termination with orphan/listener residue readback.

### CONCURRENCY.CLAIM_LIFECYCLE.001

Every execute-branch claim MUST stay mechanically owned across its whole lifecycle: acquisition by atomic provider ref creation; adoption when the subject is open awaiting_land with exactly one open PR and no live session, in which case the re-admitted cook resumes the existing branch and PR through the existing repair/exact-head ceremony; and release when adoption is not admitted, which preserves the claim content on a salvage branch, flips the subject back to ready with a fail-back receipt naming the red required check and the preserved branch, and only then frees the claim name. Session liveness derives only from the provider/session ledger (`.noodle/sessions` event ages), never from a process table, and an orphaned awaiting_land candidate is never a state only an operator notices.

Admission boundary: the deterministic dead-claim detector and sweep in `claim_contract.py` (`dead_claim_snapshot`/`sweep_dead_claims`), executed by the supervised runner loop and `./noodles reconcile`, with planted per-class fixtures in `tests/test_claim_lifecycle.py`; every state flip, salvage ref, and claim-name deletion occurs only behind that detector with direct provider readback of each transition.

## 10. Cross-repository model

### CROSS_REPO.AUTHORITY.001

Authority follows the mutated repository. Cross-repository execution requires target-local Noodle/worktree ownership, target-local contract/oracle admission, target protection/provider readback, and an exact Issue→worktree→PR→merge→closure canary. A central noodles instance may discover or dispatch work but cannot use its own receipt to prove another repository correct.

## 11. Complexity and entropy policy

### COMPLEXITY.SUBTRACT.001

Hard business/security/authority invariants may gate. Architecture-health metrics report and diagnose; they MUST NOT force line golfing or become correctness evidence. Before adding a layer, demonstrate a physical failure that the nearest existing seam cannot close. If deleting a component preserves the real task and all required evidence, prefer deletion.

Derived projections are preferred over duplicated mutable truth. Requirement status, architecture health, and closure views should be reconstructed from stable specification + provider Issues/PRs/receipts rather than hand-maintained mirrors.

## 12. Requirement identity and evolution

### REQUIREMENT.EVOLUTION.001

Stable requirement IDs are semantic identities. Once referenced by an Issue or receipt, an ID MUST NOT silently change meaning. A semantic break creates a new ID; the old ID may be deprecated but must remain resolvable for historical evidence.

Requirement definitions live only in this specification for system-level invariants. Feature-local or Issue-local invariants remain at the nearest executable contract/test and are not promoted here merely because they are important to one change.

### ISSUE_CONTRACT.TIGHTENING_OWNS_MIGRATION.001

An Issue-contract parser tightening that newly disqualifies a previously conforming ready backlog shape MUST own that backlog migration in the same atom. The stable fixture ID and exact subject remain bound; when the candidate parser rejects the trusted literal body, the candidate corpus must carry a changed same-ID body that the candidate parser accepts as ready.

The L admission boundary is the trusted fixture gate in `tests/test_issue_contract.py` over `tests/fixtures/issue-contract-ready-backlog.json`. The trusted controls step runs before the later receipt step receives its step-scoped `GH_TOKEN`. Within the suite, the gate executes the exact candidate `noodles.parse_issue_contract` against trusted and candidate literal bodies in an isolated child, then reads back the exact candidate `noodles.py` provenance. Its migration obligation diagnostic directs mechanically derivable live repair to the intake-normalizer seam `ed3c/noodles#157`.

No live-provider scan is required at this boundary; the fixtures represent durable backlog shapes rather than current provider state. Runtime automatic migration remains owned by `ed3c/noodles#157`, and scheduler no-op or memoization behavior for unchanged backlogs remains owned by `ed3c/noodles#85`.

### ISSUE_CONTRACT.INTAKE_NORMALIZATION.001

A nonconforming open Issue MUST be cured mechanically at intake, never left as silent recurring noise that every sync re-fails and every scheduler pass skips without telling anyone. The backlog adapter is that admission boundary: on sync it repairs each nonconforming open Issue exactly once, recorded by one `<!-- noodles-normalized: <body-sha256> -->` receipt marker that makes a second sync a zero-write no-op, and a conforming Issue is never written at all.

Repair inserts marker lines above the original body and never edits it, so the authored bytes stay intact and a defect the exact parser still reports stays visible instead of being overwritten. A defect whose value is derivable — the single supported role literal, the target and subject the provider already knows, an absent `noodles-depends-on` the body's own explicit declaration lines resolve — is converted, and the Issue continues as `ready`; the normalizer never fabricates Goal, acceptance, or Non-claims prose to manufacture conformance. A defect that is not derivable makes the repair a blocked normalization: `blocked` plus one `intake-normalizer` blocker naming each exact defect, and one comment naming them again and carrying the canonical template. When the authored state marker already exists, the Issue is not rewritten to `blocked`; the adapter's own fail-closed status for a still-unparseable contract keeps it out of admission.

The conventional creation path carries the same shape by default: `.github/ISSUE_TEMPLATE/repository-mutating-atom.md` emits every marker except the provider-owned subject, which intake derives. Admission boundary: the intake normalizer gate in `tests/test_issue_contract.py` over the exact candidate `noodles.adapter_sync` — planted conforming, idempotent-resync, byte-preservation, derivable-migration, and non-derivable-blocked controls, plus the template read from disk. Admission rules themselves are unchanged: normalization only makes an Issue's real shape visible to the existing scheduler.

### REQUIREMENT.PROJECTION.001

LANDED/PARTIAL/HOLD or similar implementation status is derived provider state, not specification truth. Any future `requirements status` view must reconstruct status from this specification plus exact provider Issue/PR/merge/closure facts and must not create a second mutable source of truth.

## 13. Provider and delivery invariants

Trusted verification runs candidate behavior in an isolated/read-only execution context and applies trusted verifier logic from the protected/default-branch authority boundary. Landing merges only the exact verified head and reads back the merge/default-branch/closure facts.

Noodle scheduling/worktree lifecycle and GitHub landing remain separate authorities. Provider landing precedes final local reconciliation; local execution state never substitutes for GitHub reality.

The default delivery topology is one repository-mutating atom → one PR to the configured default branch. Noodle owns dependency ordering and worktree isolation. Stack managers may be considered only after a physical canary proves they close a real throughput failure without invalidating exact-head verification.

### DELIVERY.LANDING_TRAIN.001

After every trusted land, the trusted lander MUST run the landing train: select the oldest open awaiting_land PR whose branch is behind the default branch, perform a mechanical rebase only (git's textual replay; any conflict aborts the rebase and marks the PR with a fail-back diagnostic naming the conflicting paths — content is never auto-resolved), and force-push with a lease on the observed head so trusted verification re-runs on the new exact head without any manual event. The rebased head is a new head and earns its own exact-head receipt; the train grants no verification or landing authority. Admission boundary: the `Landing train mechanical rebase` step in `.github/workflows/land.yml`, held in place by the trusted workflow boundary readback — `./noodles verify` fails closed when the train step, its scoped Contents-write push token, or the token's confinement to that step drifts or disappears.

### PROVIDER.CALL_PACING.001

Provider burst tolerance is a structural property of the repository, never a probabilistic participant's discipline. Every `gh` invocation from a cook environment or a repository adapter MUST resolve through the tracked `.agents/bin/gh` carrier, which serializes concurrent callers on one state file under `flock` and holds a minimum inter-call gap before each attempt; argv, stdin, stdout, stderr, and exit code pass through unchanged. A secondary-limit `403` carrying `Retry-After` MAY be retried exactly once and only for a read-only request; every mutation and every unclassifiable shape fails closed to its caller, which owns idempotency context. Admission boundary: `tests/test_gh_pacing.py` over the tracked carrier - a planted PATH-ordering probe through `.agents/bin/codex`, byte-faithful argv/stdin/stdout/exit passthrough, a planted concurrent burst measured against a zero-gap control, and planted read/mutation `Retry-After` controls driving a fake `gh`.

Pacing reduces but cannot eliminate secondary limiting, because other consumers share the same installation and user buckets; fail-closed handling of a residual `403` is unchanged.

## 14. Non-claims and placement rules

- Passing baseline tests does not prove undeclared product/runtime behavior.
- Agent cross-review is not independent provider verification.
- Architecture metrics and N-class documents are not correctness evidence.
- Derived schedulability is scheduler admission input, not merge/closure authority.
- Tool-specific historical claims and migration-specific evidence belong to their Issue, migration ledger, or nearest executable boundary, not this system specification.
- External Skills may describe what to verify but cannot verify themselves or mutate provider authority.
- A daemon health receipt proves the observation instant, not future liveness; the `AUTONOMY.SUPERVISED_RUNNER.001` runner restarts and heals only this repository's own daemon and claims nothing about it between generations, and noodles still implements no generic process supervisor, generic lease service, retry framework, or replacement Noodle lock. A process name or stale status file alone is not health evidence.
- This specification does not implement typed Issue completeness, Feature Map runtime, organizational-learning runtime, concurrency machinery, cross-repository execution, or a requirement registry.

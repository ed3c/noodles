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

### VERIFICATION.EVIDENCE_BINDING.001

Authoritative evidence MUST bind the requirement/Issue subject, target repository, candidate head/tree, verification/oracle identity, observation/result, and residue outcome. Stale, wrong-subject, wrong-repository, wrong-head/tree, or self-authorized evidence fails closed.

## 7. Autonomy architecture

### AUTONOMY.NO_HUMAN_VERIFIER.001

Human review MUST NOT be required as the routine correctness oracle. Human involvement is limited to goal setting, constraint changes, genuine product preference, root-authority transitions, or admitted escalation that cannot be reduced to an executable/provider fact.

`/goal`, `/loop`, and `/swarm` are P-class search/decomposition/parallelism policies, not runtime authority primitives. They may increase coverage or throughput but cannot authorize completion.

### AUTONOMY.BOUNDED.001

Autonomous retry/search MUST terminate on L+R success or fail closed on exhausted budget, invariant violation, unavailable required oracle/provider, unsupported capability, or a true product decision. Retry is not evidence.

## 8. Organizational learning

### LEARNING.EXECUTABLE.001

Repeated Agent failure may become durable organizational knowledge only through failure evidence → P-class lesson hypothesis → independent reproduction → non-case → eval → executable test/lint/contract/oracle → planted negative → regression. A single anecdote does not justify a new global rule.

New executable knowledge belongs at the nearest failure boundary, not by default in `AGENTS.md`, a global registry, or a generic policy file.

## 9. Concurrency model

### CONCURRENCY.INDEPENDENCE.001

Correctness MUST NOT depend on a fixed numeric `max_concurrency`. It depends on N-independent invariants: truthful runtime lease/ownership, exact provenance, disjoint admitted mutation boundaries, and duplicate/open-PR exclusion. Numeric caps are capacity controls, not correctness proofs.

Start-readiness and completion-readiness are distinct. A task may start independently while still requiring provider-landed predecessor facts before it may complete or land.

### CONCURRENCY.CLAIM_SCOPE.001

A claimed subject MUST exclude only its dependency-connected component from admission, never its whole repository: components are the connected components of the typed-dependency graph among open issues within one repository, and `max_useful_workers` equals the number of unclaimed components with schedulable members. A live claim whose contract cannot be parsed has unknown edges and fails its repository closed. Admission boundary: `schedule_domain.schedule_decision` with its dependency-component, claimed-exclusion, and malformed-claim controls in `tests/test_schedule_claim.py`.

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

### REQUIREMENT.PROJECTION.001

LANDED/PARTIAL/HOLD or similar implementation status is derived provider state, not specification truth. Any future `requirements status` view must reconstruct status from this specification plus exact provider Issue/PR/merge/closure facts and must not create a second mutable source of truth.

## 13. Provider and delivery invariants

Trusted verification runs candidate behavior in an isolated/read-only execution context and applies trusted verifier logic from the protected/default-branch authority boundary. Landing merges only the exact verified head and reads back the merge/default-branch/closure facts.

Noodle scheduling/worktree lifecycle and GitHub landing remain separate authorities. Provider landing precedes final local reconciliation; local execution state never substitutes for GitHub reality.

The default delivery topology is one repository-mutating atom → one PR to the configured default branch. Noodle owns dependency ordering and worktree isolation. Stack managers may be considered only after a physical canary proves they close a real throughput failure without invalidating exact-head verification.

### DELIVERY.LANDING_TRAIN.001

After every trusted land, the trusted lander MUST run the landing train: select the oldest open awaiting_land PR whose branch is behind the default branch, perform a mechanical rebase only (git's textual replay; any conflict aborts the rebase and marks the PR with a fail-back diagnostic naming the conflicting paths — content is never auto-resolved), and force-push with a lease on the observed head so trusted verification re-runs on the new exact head without any manual event. The rebased head is a new head and earns its own exact-head receipt; the train grants no verification or landing authority. Admission boundary: the `Landing train mechanical rebase` step in `.github/workflows/land.yml`, held in place by the trusted workflow boundary readback — `./noodles verify` fails closed when the train step, its scoped Contents-write push token, or the token's confinement to that step drifts or disappears.

## 14. Non-claims and placement rules

- Passing baseline tests does not prove undeclared product/runtime behavior.
- Agent cross-review is not independent provider verification.
- Architecture metrics and N-class documents are not correctness evidence.
- Derived schedulability is scheduler admission input, not merge/closure authority.
- Tool-specific historical claims and migration-specific evidence belong to their Issue, migration ledger, or nearest executable boundary, not this system specification.
- External Skills may describe what to verify but cannot verify themselves or mutate provider authority.
- A daemon health receipt proves the observation instant, not future liveness; noodles implements no supervisor, generic lease service, retry framework, or replacement Noodle lock, and a process name or stale status file alone is not health evidence.
- This specification does not implement typed Issue completeness, Feature Map runtime, organizational-learning runtime, concurrency machinery, cross-repository execution, or a requirement registry.

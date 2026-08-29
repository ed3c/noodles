# System Contract v1

This file defines claim boundaries. Executable authority lives in `noodles.py`, trusted workflows, tests, Git, and GitHub readback.

## State machine

```text
READY Issue
  → Noodle order
  → isolated worktree
  → implementation
  → local L gate
  → PR exact head
  → Issue AWAITING_LAND
  → blocking execute handoff
  → Noodle pending review
  → trusted verify receipt
  → GitHub R gate
  → merged PR readback
  → Issue LANDED + closed readback
  → Noodle machine reconciliation
```

Any missing subject, stale head, absent control, failed test, dirty provider checkout, missing protection, ambiguous PR reference, or provider drift fails closed.

## Decision record policy

This file is the single system-level decision and claim-boundary record for v1; noodles does not maintain a second ADR hierarchy. The repository document route is `AGENTS.md` → this file → `issue-named executable contract/test`, with three nodes maximum. The final node must lead to implementation or physical evidence rather than another architecture document.

Only observed invariants with an executable/readback boundary may be listed as L or R claims. An architecture decision may be recorded before its mechanism exists only when it is explicitly `HOLD` or N-class and states the physical admission criteria. Mutable Issue, PR, runtime, and provider receipts remain with their owning surfaces instead of being copied here.

## Agent-friendly architecture

Predictable local Agent behavior is an architectural input. An Issue-solving Agent tends to copy the nearest working pattern, edit the file already in context, choose the shortest passing path, preserve code whose unseen callers are uncertain, and follow a requested implementation even when the wider system invariant is not visible. Noodles does not treat those tendencies as failures to repair with more prose. It arranges ownership, paths, and executable gates so the least surprising local action is also the system-correct action.

This adapts Dune's agent-friendly design principles as noodles system laws, not as a runtime dependency, implementation template, extra document, or new framework. The design target is local-obvious → globally-correct: an Agent starting from an exact Issue should naturally reach the Golden Path with fewer choices than any shortcut, and the obvious meaning of “done” should be the physically verified meaning.

| ID | System requirement | Admission boundary |
|---|---|---|
| AF-01 | The conventional path has fewer decisions than a shortcut: exact Issue, Noodle-owned isolated worktree, nearest executable contract/test, local oracle, exact-head PR, provider readback. | The route is P-class guidance; each named local or provider gate has only its existing L or R authority. |
| AF-02 | A forbidden dependency, structural state, or authority transition fails mechanically with a diagnostic that names the supported path. | A prohibition is enforced only where a deterministic gate or provider readback already rejects it; prose alone is N-class. |
| AF-03 | Every durable value has one obvious owner and one admitted writer or transition surface. Copies are read-only projections, never competing truth. | The owner map below is the decision record. Mechanical duplicate-ownership coverage is explicitly incomplete below. |
| AF-04 | Repository mutation occurs only in an admitted isolated worktree owned by Noodle; the shared control checkout is a read/reconcile surface, not an Agent edit surface. | Noodle worktree/order/session readback and the existing L-03 containment controls. |
| AF-05 | Bootstrap and recovery exceptions are exact, narrow, bounded atoms with receipts; they pass the nearest executable gate and provider admission when authority changes. | Exact Issue subject, declared boundary, L controls, and R readback; an exception never becomes a second normal path. |
| AF-06 | The locally obvious completion path reaches the nearest required physical oracle before any completion or authority claim. | L-07 feature operation/oracle evidence followed by the existing exact-head R gates. |

### Durable owner and writer map

“One writer” means one admitted mutation or transition surface for the durable value. It does not mean one process has every authority, and it does not turn a prose ownership statement into an L or R guarantee.

| Durable value or truth | Owner | Admitted writer or transition surface | Required readback |
|---|---|---|---|
| Exact Issue goal, target, dependencies, and lifecycle state | GitHub Issue | Configured GitHub backlog adapter; only the trusted lander performs post-merge closure | Exact provider Issue body/state |
| Scheduling, orders, process isolation, and worktrees | Noodle | Noodle control/runtime APIs | Exact order, stage, session, and worktree state |
| Engineering playbook selection and route evidence | pstack | `poteto-mode` through the admitted execute Skill/provider path | Route packet remains P-class and cannot grant correctness or provider authority |
| Feature operation and oracle contract | noodles | `feature_contract.py` and the nearest executable contract/test named by the Issue | Executed operation, observed state, artifact digest, exact candidate head |
| Candidate repository source | Git in the Noodle-owned isolated worktree | The repository-mutating Agent inside that admitted worktree | Git status/tree/head plus local gate residue checks |
| Default-branch source, merge, and Issue closure | GitHub | Trusted verify/land workflows with an expected head SHA | Verify receipt, PR/head/tree, merge parent, default-branch head, closure state |
| Post-provider runtime reconciliation | noodles | `./noodles reconcile`, which drives the Noodle control API and configured backlog adapter after provider readback | Provider-landed ancestry, command acknowledgement, released order |

### Design consequences

- **Shortcut failure.** A shortcut is either structurally unavailable or fails with a diagnostic naming the supported Golden Path. A silent fallback, permissive cache, or second writer is an architecture defect, not convenience.
- **Nearest contract.** Domain knowledge lives at the nearest executable boundary: an invariant in its positive and planted-negative test, an adapter rule in its contract test, and a provider assumption in live provider readback. Prose, Skills, route packets, and reviews remain P or N until the named operation executes and its state is read back.
- **Isolation.** No repository-mutating Agent edits the shared control checkout. New mutation begins in a Noodle-owned isolated worktree; the shared checkout may observe and reconcile provider-landed state only.
- **Exceptions.** Bootstrap or recovery work names one exact subject, trigger, write boundary, expiry/completion condition, receipt, and unsupported case. It uses the same executable/provider admission as normal work and cannot establish a new normal route by precedent.
- **Subtraction.** Before adding a registry, router, framework, manager, or document layer, demonstrate a physical failure that the nearest existing contract cannot close. Prefer deleting or strengthening an existing seam; another abstraction is admitted only when subtraction cannot preserve the required behavior.
- **`poteto-mode`.** pstack selects engineering playbooks probabilistically through `poteto-mode`. It may improve investigation, implementation, review, or cleanup choices, but it owns neither correctness nor GitHub authority and cannot bypass the nearest oracle.
- **Verification architecture.** The architecture is agent-friendly only when the easiest completion path necessarily executes the exact feature operation, checks observed state at the nearest oracle, binds evidence to the candidate head, and then reaches the provider gate. A locally convenient “done” that stops at prose, tests unrelated to the Issue, or model consensus violates AF-06.

### Current mechanical coverage and follow-up gap

L-06 and its controls verify the declared three-node route, resolve its static document pointers, and reject a planted fourth architecture-document hop. The direct specification readback also pins one occurrence of each AF requirement row in this file.

There is no current seam that enumerates every canonical Agent-facing document and rejects a semantic duplicate of an AF durable rule or owner value. Therefore AF-03's repository-wide single-owner property is not mechanically verified by this atom. Follow-up work must first define the finite canonical document set and a deterministic ownership key/readback before adding a duplicate-owner planted negative; until that lands, do not claim more than the route and exact-row controls above.

## Claim registry

| ID | Class | Exact claim | Physical boundary |
|---|---|---|---|
| P-01 | P | External skills can improve routing and implementation choices. | Pinned checkout exists; skill output remains probabilistic. |
| P-02 | P | `AGENTS.md` can route an Agent toward the Golden Path. | Never a correctness gate. |
| L-01 | L | Tracked repository inventory contains only regular files and admitted surfaces. | `git ls-files --stage`, mode checks, required/forbidden paths. |
| L-02 | L | The candidate satisfies the current failing fitness invariants. Architecture-health thresholds remain warning readback only. | Trusted `noodles.py verify` exit code and metrics readback. |
| L-03 | L | Exact Issue/PR/handoff syntax is unambiguous and the completed execute session remains contained. | Parser controls plus exact worktree/order/session event readback and blocking-message controls. |
| L-04 | L | The admitted Noodle runtime and external skills are exact pinned artifacts with release, commit, checksum, license, and discovery readback. | Release tag/commit, executable version, platform asset digest, installed binary digest, detached HEAD, clean status, tree, license digest, SKILL count, configured skill-path discovery. |
| L-05 | L | Migration states cannot be promoted by prose. | Ledger schema and `MIGRATE` physical-evidence requirement. |
| L-06 | L | The declared repository document route has no more than three nodes and every static pointer resolves. | Fitness policy, direct file readback, missing-pointer control, and fourth-node control. |
| L-07 | L | Completion is accepted only after the exact Issue's admitted feature contract runs its declared product operation and its oracle checks observed state at the exact candidate head. | `feature_contract.py` resolution, real code-surface digest/bytes readback, executed `./noodles verify --json` exit and observed state, and handoff evidence controls for missing id, missing operation/oracle, skipped verifier, stale/wrong head, self-report, and artifact-blind packets. |
| R-01 | R | Direct main updates require a PR and the trusted `verify` check. | GitHub protection API readback with admins included and zero required human approvals. |
| R-02 | R | Only the exact verified PR head is merged. | Workflow-run receipt, PR/head/tree readback, merge API SHA precondition. |
| R-03 | R | The provider retained the PR head in a merge commit on default branch. | Merge result, PR readback, merge-parent readback, branch-head readback. |
| R-04 | R | The exact Issue closes only after R-03. | Issue body receipt, state transition, closure readback. |
| N-01 | N | Metrics, diagrams, inventories, and documentation describe the system. | No admission authority. |
| N-02 | N | A tool, adapter, index, or test file exists. | Existence alone proves no behavior. |

## Trusted workflow boundary

`verify.yml` uses `pull_request_target`, so the workflow definition and verifier come from default branch. It executes candidate tests in an ephemeral job with read-only permissions, no persisted checkout credential, and no repository secrets. It then runs the trusted verifier against the exact candidate checkout and emits a receipt.

`land.yml` runs only after successful `verify`. It checks out trusted default-branch code, downloads the exact receipt, validates provider protection and live PR/Issue state, then merges with an expected head SHA. It never executes candidate code with write permission.

## Supervised containment

Upstream Noodle merges a completed cook into local `main` when no blocking stage message exists; that is not a GitHub provider gate. The execute handoff therefore emits one blocking message for its exact Noodle session, which parks the order in `pending-review.json`. This does not create a Human Verifier state:

1. GitHub lander performs the R gate and closes the Issue.
2. `noodles reconcile` reads the provider receipt.
3. local `main` fast-forwards to `origin/main`.
4. the Noodle control API receives `merge` for the now-provider-landed order and returns the exact command acknowledgement.
5. Noodle's local merge is an already-contained/no-op ancestry reconciliation, then `backlog.done` releases the order.

## Delivery topology decision

v1 uses Noodle's Issue dependency graph and isolated worktrees instead of stacked PRs. Every repository-mutating atom opens one PR directly against the configured default branch. A dependent atom starts from provider-landed, reconciled `main`; independent atoms may run in parallel worktrees.

This keeps scheduling with Noodle and landing with the trusted GitHub workflow. Graphite `gt`, Git Town, git-branchless, and equivalent stack managers are unsupported in the Golden Path: they must not restack a verified head, change a PR base, ship a branch, or merge a PR. Their presence would remain P-class convenience and grant no admission authority.

The physical boundary is existing code, not this decision text:

- execute handoff and trusted PR verification reject a base other than the configured default branch;
- the lander merges only the exact verified head and reads back its merge parent and the default-branch head;
- Noodle owns dependency order, worktree isolation, and process lifecycle; it does not prove correctness or provider state.

Reconsider stacked PRs only after a physical canary shows that provider landing latency blocks dependent throughput and a proposed contract preserves exact-head verification across every restack. Until then, adding a stack manager duplicates ownership and increases mutable state without closing a demonstrated failure.

## External control-skill decision — HOLD

`control-noodle` remains an external P-class knowledge bundle owned by `skill-concerns`; it is not a second router, runtime controller, or correctness authority. Noodle continues to schedule and isolate, while noodles owns target-local executable verification and GitHub owns provider admission.

Consumer admission requires all of the following before this decision can leave `HOLD`:

1. `skill-concerns` lands one exact producer commit with a deterministic bundle-admission receipt.
2. noodles pins one selective `control-noodle` provider path and reads back the exact discovered bytes without exceeding the provider budget.
3. Each hard requirement ID named by an Issue maps to one target-local positive control, planted negative control, direct readback, and residue check.
4. A live stale-state-recovery and Issue→worktree→handoff canary passes on the exact admitted Noodle runtime.
5. The exact-head GitHub workflow lands the consumer change and closes its Issue after provider readback.

The skill may describe what to verify; it cannot verify itself or mutate Noodle runtime state. Code-map coverage, a passing producer test suite, or skill discovery alone does not establish complete Noodle behavior. v1 therefore makes no current compatibility or full-requirements claim for `control-noodle`.

## Cross-repository boundary

v1 admits `ed3c/noodles` only. Cross-repository execution is `HOLD` until every target has:

- a local Noodle installation/worktree authority in that target repository;
- the same trusted verify/land workflows or an equivalent provider installation;
- an exact token-scope readback;
- target-specific branch protection;
- one live issue→worktree→PR→merge→closure canary.

A central repo cannot claim physical control of another repo merely because it can read its Issues.

## Non-claims

- Passing tests is not full task verification unless the exact task contract names those tests and readbacks.
- Agent cross-review is not independent provider verification.
- A verification skill existing on disk, or its output, is P-class until the declared feature operation runs and the oracle checks observed state; noodles claims no generic feature registry and verifies no capability without an admitted feature contract.
- Architecture warnings are health signals only. They are not correctness evidence, merge permission, or a reason to compress readable code instead of creating a real seam.
- GrepAI candidates are not source truth and misses are not absence proof.
- Tree-sitter ranges do not prove a context compiler.
- Serena indexing does not prove bounded edit execution.
- Individual adapter PASS results do not prove an end-to-end code-intelligence chain.
- An empty Human approval count does not remove the need for deterministic L and R gates.

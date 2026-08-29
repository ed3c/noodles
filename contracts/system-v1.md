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
- Architecture warnings are health signals only. They are not correctness evidence, merge permission, or a reason to compress readable code instead of creating a real seam.
- GrepAI candidates are not source truth and misses are not absence proof.
- Tree-sitter ranges do not prove a context compiler.
- Serena indexing does not prove bounded edit execution.
- Individual adapter PASS results do not prove an end-to-end code-intelligence chain.
- An empty Human approval count does not remove the need for deterministic L and R gates.

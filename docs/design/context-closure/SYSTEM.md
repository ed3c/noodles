# System Projection

> N-class projection for snapshot `CTX-2026-08-30T02:44:51+08:00`. The executable and provider owners named below remain authoritative; this file is not.

## System boundary

`noodles` is a target-local correctness/evidence extension around upstream Noodle, pinned pstack knowledge, Git, and GitHub. It is not a second Agent OS and does not own generic scheduling, worktree lifecycle, provider truth, or model reasoning quality.

The intended responsibility split is:

```text
Noodle
  owns scheduling, orders, process isolation, and worktrees

pstack / poteto-mode
  owns probabilistic engineering-route selection

noodles
  owns target-local contracts, evidence adapters, gates, repair/reconcile hooks

Git
  owns candidate source identity and ancestry

GitHub
  owns protected default-branch reality, exact-head merge, and Issue closure

target repository
  owns its feature/domain oracles and every authority-bearing local contract
```

## Directory and surface map

This table is compiled from provider tree `afc1ec4ab5077b16b6e03b1091a539737a6b9970`.

| Surface | Intended concern | Admitted writer / transition owner | Primary readback | State-machine role | Main data flow |
|---|---|---|---|---|---|
| `.agents/bin/codex` | Repository-owned Codex carrier boundary | Exact carrier/model atom only | argv/model/effort/isolation controls | carrier launch | Noodle task → exact Codex profile |
| `.agents/skills/schedule/` | Project scheduling procedure | Exact schedule-Skill atom; Noodle still owns order lifecycle | Noodle skill discovery + compact-order contract | schedule proposal | typed backlog → candidate orders |
| `.agents/skills/execute/` | Project implementation/handoff procedure | Exact execute-Skill atom | route resolution, issue digest, handoff controls | execute lane | order → poteto-mode → candidate → handoff |
| `.github/workflows/verify.yml` | Trusted candidate verification | Trusted workflow atom only | semantic workflow validator + run/jobs/receipt | trusted verification | exact PR head → trusted receipt |
| `.github/workflows/land.yml` | Exact-head landing and Issue closure | Trusted land workflow only | protection, PR/head/tree, merge, branch, Issue state | provider landing | trusted receipt → merge/closure |
| `.noodle.toml` | Noodle runtime/configured routing | Exact runtime/routing atom | config and pinned-runtime controls | runtime admission | task type → provider/model/path |
| `.noodle/adapters/github` | Backlog adapter entrypoint | Exact GitHub adapter atom | provider Issue/PR readback | backlog synchronization | GitHub Issues ↔ Noodle backlog |
| `AGENTS.md` | Always-loaded bootloader laws and 3-hop route | Canonical document-owner atom | document-route controls | context routing | Agent start → system/Issue pointer |
| `contracts/system-v1.md` | Stable cross-task claim boundaries and system decisions | System-spec/decision atom | direct source readback + bounded document controls | constitution | requirement/authority law → Issue context |
| `docs/research/**` | N-class research projections | Documentation-only atom | source identity/freshness | research snapshot | sources → analysis |
| `docs/design/**` | N-class design/program projections | Documentation-only atom | source identity/freshness | planning snapshot | sources → DAG/closure packets |
| `feature_contract.py` | Baseline acceptance plus optional specialized feature oracle | Exact verification-contract atom | operation/oracle/evidence tests | completion admission | candidate head/tree → evidence envelope |
| `skill_contract.py` | Skill, schedule, and document-route contracts | Exact contract atom | parser/publish/document controls | structural admission | Skill/order/doc bytes → accept/reject |
| `github_protection.py` | GitHub workflow/protection/landing boundary | Exact provider-security atom | live GitHub API + semantic workflow controls | R gate | receipt + provider state → land/refuse |
| `provider_contract.py` | External Skill provider identity/admission | Exact provider atom | commit/tree/license/admission digests | provider sync/check | lock → detached provider bytes |
| `runtime_contract.py` | Pinned Noodle runtime and local runtime admission | Exact runtime atom | version/asset/binary/process/listener/snapshot | runtime start/readiness | lock + binary → admitted Noodle runtime |
| `repair_contract.py` | Re-entry after trusted check failure | Exact repair atom | Issue/PR/head/session/worktree receipt | repair loop | failed check → same lane/new head |
| `policy/*.json` | Machine-readable exact policy and immutable pins | Nearest owning policy atom | executable consumers and planted drift | gate configuration | candidate/provider state → decision |
| `migrations/skills-shared/ledger.json` | Evidence-bounded migration dispositions | Migration atom only | ledger schema and evidence requirement | capability admission | historical evidence → MIGRATE/REVALIDATE/etc. |
| `tests/` | Positive, planted-negative, non-case, and regression controls | Nearest contract/feature atom | exit code + direct fixtures/readback | local proof | claim boundary → falsification |
| root Python modules | Thin target-local control/evidence implementation | Exact Issue lane in Noodle worktree | tests, source/head/tree, provider readback | implementation | typed input → deterministic decision |
| `noodles` / `noodles.py` | User entrypoint and core command dispatch | Exact CLI/control atom | CLI output, tests, repository gate | system entrypoint | operator/Noodle → contracts/providers/reconcile |

## State Machine A: Issue-to-landed reality

```text
OPEN ISSUE
  │ structural markers / provider body
  ▼
STRUCTURALLY VISIBLE
  │ dependency/provider/body-digest admission
  ▼
SCHEDULABLE
  │ Noodle order
  ▼
ISOLATED WORKTREE
  │ poteto-mode and selected P-class playbook
  ▼
CANDIDATE IMPLEMENTATION
  │ mandatory baseline acceptance
  │ optional declared specialized oracle
  ▼
LOCAL EVIDENCE COMPLETE
  │ exact branch/head + one-line Refs PR
  ▼
AWAITING_LAND
  │ blocking stage message
  ▼
NOODLE PENDING REVIEW
  │ trusted verify exact-head receipt
  ▼
PROVIDER VERIFIED
  │ expected-head merge + merge/default-branch readback
  ▼
ISSUE LANDED + CLOSED
  │ local provider fast-forward + machine merge control
  ▼
RECONCILED
```

Authority by segment:

- Issue understanding and pstack route: `P`;
- baseline/specialized executable acceptance: `L`;
- protected exact-head merge/closure: `R`;
- this diagram: `N`.

## State Machine B: trusted-check repair

```text
AWAITING_LAND PR
  │ required check failure readback
  ▼
FAILED EXACT HEAD
  │ bind Issue + PR + head + session + worktree
  ▼
REPAIR RECEIPT
  │ re-enter same Noodle-owned worktree
  ▼
REPAIR ATTEMPT
  ├─ new exact head → rerun trusted verification
  ├─ attempt budget exhausted → explicit escalation
  └─ identity/worktree drift → fail closed
```

The loop is a runtime repair cycle, not a delivery dependency cycle. It cannot convert failed or unknown verification into PASS.

## State Machine C: failure-to-organizational knowledge

Current status: **proposed / incomplete**, owned by open Issue #21.

```text
OBSERVED FAILURE
  │ pstack reflect or other hypothesis generation
  ▼
P-CLASS LESSON CANDIDATE
  │ preserve occurrence evidence
  ▼
INDEPENDENT REPRODUCTION A + B
  │ plus one non-case
  ▼
EVAL DISTINGUISHES BOUNDARY
  ├─ no → remain P-only guidance
  └─ yes
       ▼
NEAREST TEST / LINT / CONTRACT
       │ planted negative + regression
       ▼
DURABLE EXECUTABLE RULE
```

A single anecdote or direct prose edit must not enter the durable L boundary.

## State Machine D: context-closure planning

```text
SOURCE DENOMINATOR FREEZE
  │ exact identity / classification / freshness
  ▼
SHADOW MONITOR
  │ architecture, intent/case, authority, lifecycle,
  │ concurrency, and evidence deltas
  ▼
TECH LEAD COMPILATION
  │ true start/completion edges, requirement owners,
  │ disjoint writers, convergence owners
  ▼
N-CLASS CONTEXT PACK
  │ SYSTEM / DAG / CLOSURE / TRACEABILITY / DRIFT
  ▼
CANDIDATE TASK PACKETS
  │ explicit provider action is still required
  ▼
EXACT GITHUB ISSUE
```

This State Machine has no implementation or closure authority. The output becomes actionable only when an exact Issue passes the normal target-local lifecycle.

## Primary data and authority flow

```text
System requirement / owner intent                      N or owner authority
        │
        ▼
Exact GitHub Issue body + provider digest              provider fact
        │
        ▼
Noodle scheduler/order/worktree                        execution topology
        │
        ▼
poteto-mode / pstack playbook                          P
        │
        ▼
Candidate source in isolated worktree                  Git subject
        │
        ▼
Baseline acceptance + optional specialized oracle      L
        │
        ▼
Exact-head trusted receipt                             L bound to provider subject
        │
        ▼
Protected GitHub merge and closure                     R
        │
        ▼
Derived requirement status / context projection        N
```

No downstream projection may become an upstream authority. In particular:

- a route packet cannot authorize a merge;
- candidate-modified tests cannot be the sole authority for that candidate;
- a context document cannot serve as evidence;
- a derived `PARTIAL`/`LANDED` status must not be stored as a second mutable truth;
- central planning cannot replace target-repository authority.

## No-self-authorization boundary

Owner conversation proposes the general law:

```text
candidate-modified bytes
must not be the sole authority
for admitting the same candidate
```

Current repository mechanisms partially realize it through separate candidate/trusted jobs, trusted verifier bytes from default branch, exact-head receipts, and provider landing. This pack records the law as an owner requirement and current mechanism as repository/provider facts. It does not claim every future feature oracle already satisfies the law.

## Agent-friendly architecture relationship

Issue #72 already landed a compact Agent-friendly shortest-path summary. Issue #109 is the current convergence atom for complete Dune-derived rationale and requirements `AF-01` through `AF-06` in the system contract.

The intended local optimization is:

```text
correct path
  exact Issue → Noodle worktree → nearest contract → acceptance/oracle → provider gate

shortcut
  shared-root edit / unowned writer / skipped oracle / direct close / stale receipt
  → mechanical refusal or explicit unsupported state
```

PR #118 is not yet provider-landed at this snapshot. The AF section remains a candidate until R readback completes.

## Concurrency relationship

The target design does not derive safety from a fixed concurrency number. Open Issues model four N-independent invariants:

- I1, truthful single Noodle daemon lease: #45;
- I2, exact Issue/session/worktree/branch provenance: #46;
- I3, disjoint declared write boundaries: #98;
- I4, no duplicate lane when an exact open PR exists: #99.

Issue #100 is the convergence owner for binding declared concurrency to evidence that those invariants remain alive. Until those atoms land, concurrency independence is an incomplete design claim.

## Cross-repository relationship

Open Issue #14 owns target-local cross-repository admission. The projected law is:

> Authority follows the mutated repository.

A central noodles instance may discover or plan work. Each target must still own its own Noodle/worktree boundary, feature/domain oracle, protected provider gate, and live canary. No source-side allowlist or central receipt establishes another repository's correctness.

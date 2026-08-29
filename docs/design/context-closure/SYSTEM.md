# System Projection

> N-class projection for `CTX-2026-08-30T02:55:36+08:00`. Executable and provider owners remain authoritative; this file is not.

## Responsibility boundary

```text
Noodle
  scheduling, orders, process isolation, worktrees

pstack / poteto-mode
  probabilistic engineering route and playbook selection

noodles
  target-local contracts, evidence adapters, gates, repair/reconcile hooks

Git
  candidate source identity, tree, ancestry

GitHub
  protected default-branch reality, exact-head verification/merge, Issue closure

target repository
  feature/domain oracles and every local authority-bearing contract
```

## Directory and surface map

Compiled from provider tree `b450cc02578b25a7834754ad170632554e0b4ddd`.

| Surface | Concern | Admitted writer / transition owner | Direct readback | Data flow |
|---|---|---|---|---|
| `.agents/bin/codex` | exact Codex carrier/model boundary | carrier/model atom | argv, model, effort, isolation canary | Noodle task → Codex session |
| `.agents/skills/schedule/` | scheduling procedure | schedule-Skill atom; Noodle still owns orders | Noodle skill discovery + compact-order contract | typed backlog → candidate orders |
| `.agents/skills/execute/` | implementation/handoff procedure | execute-Skill atom | route, Issue digest, acceptance, handoff | order → poteto-mode → candidate → PR |
| `.github/workflows/verify.yml` | trusted candidate verification | trusted workflow atom | semantic workflow validator + run/jobs/receipt | exact PR head → trusted receipt |
| `.github/workflows/land.yml` | exact-head merge and closure | trusted land workflow | protection, PR/head/tree, merge, branch, Issue state | receipt → merge/closure |
| `.noodle.toml` | Noodle routing/runtime config | runtime/routing atom | config and pinned-runtime checks | task key → provider/model/path |
| `.noodle/adapters/github` | backlog/provider adapter | exact adapter atom | provider Issue/PR readback | GitHub Issues ↔ Noodle backlog |
| `AGENTS.md` | always-loaded bootloader and three-hop route | canonical document-owner atom | route and pointer controls | Agent start → system/Issue pointer |
| `contracts/system-v1.md` | stable system decisions and requirements | system-spec atom | direct source + document/spec controls | stable requirement → Issue context |
| `docs/research/**`, `docs/design/**` | N-class research/design projections | documentation-only atom | source identity/freshness | sources → planning projection |
| `feature_contract.py` | mandatory baseline plus optional specialized oracle | verification-contract atom | operation/oracle/evidence tests | exact head/tree → evidence envelope |
| `skill_contract.py` | Skill, schedule, and document-route boundaries | nearest contract atom | parser/publish/route controls | bytes → accept/reject |
| `github_protection.py` | workflow/protection/landing authority | provider-security atom | live API + semantic workflow controls | receipt/provider state → land/refuse |
| `provider_contract.py` | external Skill provider identity | provider atom | commit/tree/license/digests/clean state | lock → detached provider bytes |
| `runtime_contract.py` | pinned Noodle runtime | runtime atom | release/version/asset/binary/process | lock + binary → admitted runtime |
| `repair_contract.py` | same-lane re-entry after failed check | repair atom | Issue/PR/head/session/worktree receipt | failed head → repair/new head |
| `policy/*.json` | exact machine policy and pins | nearest owning policy atom | executable consumers + planted drift | candidate/provider state → decision |
| `migrations/skills-shared/ledger.json` | bounded migration dispositions | migration atom | ledger schema/evidence requirement | historical evidence → disposition |
| `tests/` | positive, planted-negative, non-case, regression | nearest feature/contract atom | exit/output/fixture/readback | claim boundary → falsification |
| root Python modules | thin target-local control implementation | exact Issue lane in Noodle worktree | source/head/tree/tests/provider | typed input → deterministic decision |
| `noodles`, `noodles.py` | user/system entrypoint | exact CLI/control atom | CLI output and repository gate | operator/Noodle → contracts/providers/reconcile |

## State Machine A: Issue to landed reality

```text
OPEN ISSUE
  → STRUCTURALLY VISIBLE
  → PROVIDER/DEPENDENCY/BOUNDARY ADMISSION
  → SCHEDULABLE
  → NOODLE ORDER
  → ISOLATED WORKTREE
  → POTETO-MODE / P-CLASS PLAYBOOK
  → CANDIDATE IMPLEMENTATION
  → MANDATORY BASELINE ACCEPTANCE
  → OPTIONAL APPLICABLE SPECIALIZED ORACLE
  → LOCAL EVIDENCE COMPLETE
  → EXACT-HEAD PR + AWAITING_LAND
  → NOODLE PENDING REVIEW
  → TRUSTED VERIFY RECEIPT
  → PROTECTED EXPECTED-HEAD MERGE
  → ISSUE LANDED + CLOSED
  → LOCAL MACHINE RECONCILIATION
```

Authority:

- understanding/routing: `P`;
- executable acceptance: `L`;
- protected merge/closure: `R`;
- this projection: `N`.

## State Machine B: trusted-check repair

```text
AWAITING_LAND PR
  → FAILED REQUIRED CHECK AT EXACT HEAD
  → BIND ISSUE + PR + HEAD + SESSION + WORKTREE
  → DETERMINISTIC REPAIR RECEIPT
  → RE-ENTER SAME NOODLE WORKTREE
  → NEW EXACT HEAD
  → TRUSTED VERIFICATION
      ├─ pass → provider landing
      ├─ fail → bounded next attempt
      └─ exhausted/unsupported → explicit escalation
```

This operational cycle does not convert failed or unknown verification into PASS.

## State Machine C: failure to executable knowledge

Current owner: open Issue #21.

```text
OBSERVED FAILURE
  → P-CLASS LESSON CANDIDATE
  → TWO INDEPENDENT REPRODUCTIONS
  → ONE NON-CASE
  → EVAL DISTINGUISHES BOUNDARY
      ├─ no → remain P-only
      └─ yes → nearest test/lint/contract
                 → planted negative
                 → regression
                 → durable executable rule
```

A single anecdote or direct `AGENTS.md` edit is not organizational learning.

## State Machine D: context closure

```text
SOURCE DENOMINATOR FREEZE
  → SHADOW MONITOR (read-only)
  → TECH LEAD TRUE-DAG / OWNER / WRITER COMPILATION
  → N-CLASS SYSTEM/DAG/CLOSURE/TRACE/DRIFT PACK
  → CANDIDATE TASK PACKETS
  → SEPARATE EXACT GITHUB ISSUE
```

The pack itself creates no provider or implementation authority.

## Primary data and authority flow

```text
stable requirement / owner intent                   N or owner input
        ↓
exact GitHub Issue body + provider digest           provider fact
        ↓
Noodle order/worktree                               execution topology
        ↓
poteto-mode/playbook                                P
        ↓
candidate Git head/tree                             source subject
        ↓
baseline + optional specialized oracle              L
        ↓
trusted exact-head receipt                          L bound to provider subject
        ↓
protected merge and closure                         R
        ↓
derived status/context projection                   N
```

No downstream projection becomes upstream authority. In particular:

- pstack route evidence cannot authorize merge;
- candidate-modified bytes cannot be the sole authority for the same candidate;
- N documents cannot serve as receipts;
- `LANDED/PARTIAL/HOLD` is derived, not stored as a second status truth;
- central planning cannot replace target-repository authority.

## Landed Agent-friendly architecture

Issue #109 provider-landed through PR #118 at merge `bb42c7c4cf81ebde8d2659ae0ff0c37dbc5d9f24`, tree `b450cc02578b25a7834754ad170632554e0b4ddd`.

The locally obvious path is now defined by AF-01 through AF-06:

```text
exact Issue
  → Noodle-owned worktree
  → nearest executable boundary
  → mandatory baseline
  → every applicable specialized oracle
  → exact-head provider gate
```

A shortcut such as shared-root mutation, competing writer, skipped oracle, stale receipt, or direct closure is an error path, not a parallel Golden Path.

## Current specification and Issue-contract evolution

- #119 owns convergence of `contracts/system-v1.md` into a compact low-change constitution with stable requirement evolution rules.
- #120 owns stable requirement references plus deterministic Issue structural completeness after #82/#98/#83/#119.
- #83 still owns canonical Agent procedure/document cleanup and overlaps #119's system-contract surface; Tech Lead must serialize those writers.

Neither #119 nor #120 is implemented by this context pack.

## Current active provider lanes

| Issue / PR | Concern | Exact head | Snapshot state |
|---|---|---|---|
| #82 / PR #121 | typed dependencies and derived schedulability | `35e0feed1c321c96b43d200ee57f3197a4d38fb4` | `awaiting_land`; exact-head verify failed |
| #45 / PR #122 | truthful Noodle daemon lease, concurrency I1 | `30651b61b8c747c3bd8f684652fb5a59e33a2c1f` | `awaiting_land`; exact-head verify failed |
| #116 / PR #123 | optional repo-infra specialized oracle | `8e35b65ba9f9be051e9a6fca1527d23acac0cf22` | `awaiting_land`; exact-head verify failed |
| #117 | N-class context pack | branch `agent/issue-117-context-closure-rebased` | implementation in progress; no provider PR at snapshot |

Failed lanes remain owned by the same exact repair lifecycle; no separate worker or new Issue is inferred here.

## Concurrency architecture

The intended safety proof is N-independent:

- I1 truthful daemon lease: #45;
- I2 exact Issue/session/worktree/branch provenance: #46;
- I3 disjoint typed write boundaries: #98;
- I4 refusal when an exact open PR/lane already exists: #99;
- convergence/proof lock: #100.

At this snapshot I1 has a candidate PR but no trusted PASS; the other invariants remain open. No concurrency-safety completion claim is justified.

## Cross-repository architecture

Issue #14 owns the target-local contract. The durable law is:

> Authority follows the mutated repository.

A central noodles instance may discover/plan. Each target must still own local Noodle/worktree isolation, its oracle, protection/credential scope, exact-head landing, and a live canary.

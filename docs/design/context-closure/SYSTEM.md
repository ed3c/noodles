# System topology projection

> **N-class only.** This document maps current ownership and intended data flow. Executable authority remains with code, tests, trusted workflows, Git, GitHub, and target-local provider readback.

## System boundary

```text
Stable system requirement
        |
        v
Typed GitHub Issue atom
        |
        v
Noodle order and isolated worktree
        |
        v
pstack / poteto-mode engineering search                 P
        |
        v
implementation candidate
        |
        v
nearest feature/domain physical oracle                  L
        |
        v
trusted exact-head verification and landing             R
        |
        v
provider-landed fact and local Noodle reconciliation
```

## Ownership table

| Durable value or lifecycle | Canonical owner/writer | Readers | Forbidden competing owner |
|---|---|---|---|
| Stable system intent and invariant | `contracts/system-v1.md` | AGENTS pointer, exact Issue, planning tools | Issue prose, README copies, this docs package |
| Exact implementation delta | GitHub Issue body and typed markers | Noodle backlog adapter, scheduler, execute lane | copied order prose as a second mutable truth |
| Issue provider state | GitHub | adapter, trusted workflows, projections | local status file or Agent assertion |
| Scheduling and order lifecycle | upstream Noodle | adapters, control UI/API, reconciliation | noodles custom scheduler or context compiler |
| Worktree and process isolation | upstream Noodle | execute lane, provenance gates | Agent-created shared-root branch/worktree lifecycle |
| Engineering route | pinned pstack `poteto-mode` | execute Agent | noodles router or free-form self-authorization |
| Target-local feature/oracle contract | nearest executable contract/test | execute and trusted verifier | global prose registry |
| Repository source | Git object graph | verifier, oracle, provider | transcript or projection |
| Candidate admission evidence | exact-head L receipt | trusted verifier/lander | candidate self-report alone |
| Merge and Issue closure | GitHub trusted R gate | reconcile and projection | Agent, local merge, second reviewer vote |
| Runtime reconciliation | noodles wrapper plus upstream Noodle control seam | operator and status projection | ad hoc reset or unbound local script |
| Planning projection | `docs/design/context-closure/**` | Shadow/Tech Lead planning | executable completion authority |

## Repository surface map

| Surface | Responsibility | Admitted writer | State machine | Primary data flow |
|---|---|---|---|---|
| `.agents/` | project-owned schedule/execute procedure entrypoints and compatibility mappings | exact Skill/procedure atom | discoverable -> resolved -> invoked -> result | Issue/order -> selected task Skill -> pstack route |
| `.github/workflows/` | trusted candidate verification and exact-head landing | workflow security atom | PR event -> candidate test -> trusted verify -> receipt -> land/skip | candidate head + Issue -> R decision |
| `.noodle.toml` | admitted runtime, provider, model, concurrency, skill path configuration | exact config atom | parsed -> admitted -> runtime invocation | repository policy -> Noodle dispatch |
| `.noodle/` tracked adapters | GitHub backlog/control adapter boundary | adapter atom | provider read -> normalized record -> mutation/readback | GitHub Issue/PR -> Noodle order state |
| `.noodle/` ignored runtime | Noodle sessions, orders, pending reviews, receipts | upstream Noodle and admitted wrapper seams | spawn -> active -> blocked/review -> reconciled/failed | order -> session/worktree -> provider handoff |
| `contracts/` | stable claim boundaries and nearest executable feature/domain contracts | specification or feature atom | defined -> referenced -> exercised -> superseded | requirement -> Issue -> oracle |
| `docs/design/` and `docs/research/` | N-class design/research projections | docs-only atom | snapshot -> current/stale -> superseded | sources -> planning context |
| `migrations/` | evidence-bounded capability disposition | migration atom | HOLD/REVALIDATE/MIGRATE/ADAPT_EXTERNAL/DROP | historical evidence -> admission experiment |
| `policy/` | deterministic repository, provider, runtime, workflow, and evidence constraints | exact policy atom | parsed -> checked -> pass/fail/warn | candidate tree -> L decision |
| `tests/` | positive, planted-negative, non-case, stale-state, and residue falsifiers | nearest implementation atom | fixture -> execution -> observation -> verdict | claim -> evidence |
| root CLI/modules | target-local correctness/evidence compiler and wrapper | exact implementation atom | command -> admission -> action/readback -> result | Issue/runtime/provider -> machine effect |

## State machines

### Issue and delivery

```text
DRAFT_OR_INCOMPLETE
  -> WELL_FORMED
  -> READY_WHEN_DEPENDENCIES_AND_BOUNDARIES_ADMIT
  -> IN_PROGRESS
  -> AWAITING_LAND
  -> PROVIDER_LANDED
  -> CLOSED_AND_RECONCILED
```

Fail-closed side states:

```text
BLOCKED
REPAIRABLE
UNSUPPORTED
ENVIRONMENT_UNAVAILABLE
INVARIANT_VIOLATION
EXHAUSTED
PRODUCT_DECISION_REQUIRED
```

Stored Issue markers are provider facts. Derived readiness must be recomputed from provider state, dependency state, open-PR correlation, write-boundary conflicts, and required authority availability.

### Noodle order and worktree

```text
Issue admitted
  -> order scheduled
  -> isolated worktree/session spawned
  -> execute route selected
  -> implementation and local verification
  -> exact PR/handoff
  -> blocking pending-review containment
  -> GitHub provider landing
  -> local fast-forward and machine merge control
  -> order released and worktree cleaned
```

Noodle owns this lifecycle. Project code may validate provenance and call supported controls; it must not duplicate worktree ownership.

### Verification

```text
Issue requirement and feature ID
  -> resolve nearest contract
  -> compile changed-code impact
  -> required journeys and non-case denominator
  -> operate real artifact
  -> deterministic observation/oracle
  -> bind evidence to Issue/base/head/oracle
  -> trusted verifier checks envelope
  -> provider R gate
```

A test or Skill existing on disk is not an executed oracle.

### Repair

```text
trusted check or landing failure
  -> bind exact Issue/PR/head/session/worktree
  -> classify failure
  -> re-enter exact Noodle lane when repairable
  -> produce new head
  -> repeat trusted verification
  -> land or stop at a bounded terminal class
```

No general retry engine is implied.

### Organizational learning

```text
failure evidence
  -> pstack reflect lesson hypothesis                     P
  -> independent reproductions
  -> explicit non-case
  -> bounded eval
  -> nearest executable test/lint/contract
  -> planted negative and regression
  -> durable L rule after separate admission
```

Reflection prose cannot mutate correctness policy directly.

## Data flows

### Planning/context flow

```text
conversation + Issues/PRs + repo tree + source documents + runtime observations
  -> frozen denominator
  -> Shadow MONITOR deltas
  -> Tech Lead dependency/case/write-boundary compilation
  -> N-class context pack
  -> bounded candidate task packet
  -> canonical three-hop execution route
```

### Execution flow

```text
exact Issue
  -> adapter/provider readback
  -> Noodle order
  -> isolated worktree
  -> poteto-mode and matched playbook
  -> candidate diff
  -> feature/domain oracle
  -> evidence envelope
  -> trusted GitHub verification/landing
  -> provider readback
  -> local reconciliation
```

### Fact reconstruction flow

```text
stable requirement definition
  + exact Issue markers/body digest
  + PR/head/check/merge
  + Issue closure
  + oracle/runtime receipts
  -> derived current status
```

No `landed-facts.json` or stored derived status is introduced.

## Agent-friendly architecture checks

- The supported path must require fewer decisions than a shortcut.
- Shared-root mutation, unsupported routes, stale evidence, direct closure, and unbound local merge should fail with diagnostics naming the supported path.
- Every durable value has one writer.
- Exceptions are bounded atoms with their own receipts and never become an undocumented normal path.
- The locally obvious completion route must reach the required physical oracle and provider gate.

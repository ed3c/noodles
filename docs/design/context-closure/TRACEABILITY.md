# Molecular Traceability Index

> N-class only. This index points to provider/executable truth; it is not a registry or proof surface. Active PR exact heads must be re-read from GitHub rather than treated as stable text here.

## Trace format

```text
source / owner intent
→ requirement or planning hypothesis
→ exact Issue
→ branch/worktree/session when observed
→ PR/provider head readback
→ changed paths
→ test/oracle surface
→ merge/default-branch/closure readback
```

Missing links are `TRACEABILITY_GAP`; they are never filled from inference.

## Active and recently landed lanes

### System Specification convergence — landed

```text
owner intent: stable second-hop constitution, no fourth hop
→ #119
→ PR #126 / exact head 56e2df152f8daec7683ee6d9d3d18ff27197e527
→ contracts/system-v1.md + tests/test_agent_friendly_architecture.py
→ document-route/requirement-identity controls
→ merge 4b3f3e53c642dd33d0f3632bced3006c6cbf2ea3
→ Issue #119 landed/closed
```

### Canonical Agent procedure ownership — active

```text
owner intent: one canonical owner per Agent procedure fact
→ #83
→ branch ed3c-noodles-83-canonical-procedure
→ PR #129; exact head is provider-read at use time
→ AGENTS.md, README.md, schedule/execute Skills, skill_contract.py, nearest test
→ baseline/trusted verification: TRACEABILITY_GAP until provider run completes
→ merge/closure: TRACEABILITY_GAP
```

### Context-closure first molecular leaf — active

```text
owner intent: preserve full program context without touching verified truth
→ planning hypothesis CONTEXT.CLOSURE.PROJECTION.001
→ parent #117
→ implementation #124
→ PR #128; exact head is provider-read at use time
→ docs/design/context-closure/{README,SYSTEM,DAG,CLOSURE,TRACEABILITY,DRIFT}.md only
→ N-class path/readback + mandatory repository baseline
→ merge/closure: TRACEABILITY_GAP
```

### Typed dependency/provider-body truth — landed

```text
owner intent: derive schedulability from provider predecessors
→ #82
→ provider-landed PR #121
→ Issue contract/provider dependency surfaces
→ exact body digest/dependency controls
→ landed reality: PRESENT
```

### Typed disjoint write boundaries — ready

```text
owner intent: concurrency I3, reject overlapping active lane boundaries
→ #98
→ dependency #82 landed
→ lifecycle marker repaired from stale dependency-only blocked to ready
→ branch/worktree/PR: TRACEABILITY_GAP until normal execution starts
→ parser/admission + overlap/disjoint controls
→ provider landing: TRACEABILITY_GAP
```

### Typed Issue completeness — blocked

```text
owner intent: #69-style ready Issue must fail if structurally non-executable
→ #120
→ dependencies #82/#98/#83/#119
→ #82/#119 landed; #98/#83 incomplete
→ implementation/readback: TRACEABILITY_GAP
```

## Verification/autonomy skeleton

| Intent | Owner | Existing pointer | Missing molecular links |
|---|---|---|---|
| pstack higher-order route | #18 | landed provider pointer | exercise within complete #4 canary |
| verification-skill → physical oracle | #19 | Issue contract | implementation PR/head/oracle/landing |
| executable Feature Map canary | #20 | Issue contract | target-local feature contract/oracle/landing |
| changed code → journey → oracle | #66 | Issue contract | #20/#46 prerequisites + evidence |
| unattended single-Issue loop | #4 | lifecycle ready, provider dependencies unresolved | complete Noodle/order/worktree/pstack/oracle/PR/R/reconcile chain |
| failure → executable rule | #21 | Issue contract | #4 + reproductions/non-case/eval/regression |
| bounded multi-Issue program | #22 | Issue contract | #4/#21/#46 + multi-Issue receipt |

## Concurrency skeleton

| Invariant | Owner | Known predecessor | Missing evidence |
|---|---|---|---|
| I1 truthful daemon lease | #45 | #44 historical landed | implementation/live runtime receipt |
| I2 exact worktree/session provenance | #46 | #45 | two-worktree provenance canary |
| I3 typed disjoint write boundaries | #98 | #82 landed | implementation + overlap/disjoint controls |
| I4 exact open-PR exclusion | #99 | #46 | provider readback + race controls |
| invariant proof lock | #100 | I1-I4 | final derived lock/readback |

## Historical architecture-changing Issues

Owner conversation identifies #25, #27, #30, #33, #44, #50, #57, #60, #61, #64/#87, #72, #82, #94, #101, #109, #112, and #119 as material architecture changes. This atom did not re-fetch every historical receipt. Treat that list as `N-DESIGN / PARTIAL PROVIDER RECHECK`; re-read exact GitHub facts before using one as a completion dependency.

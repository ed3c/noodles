# Implementation DAG Projection

> N-class only. Edges are planning projections from provider Issues/readback; they are not scheduler or completion authority.

## Edge semantics

- `READY`: Issue lifecycle state only; derived schedulability may still be false.
- `START`: predecessor facts are sufficient to begin one bounded lane.
- `COMPLETE`: predecessor must provider-land/close/read back before dependent completion/landing.
- `HOLD`: external/unproven prerequisite prevents admission.
- `PARALLEL`: disjoint write boundaries may progress concurrently; not a correctness proof.

Never infer schedulability or `COMPLETE` from `READY` or `START`.

## Current convergence spine

```text
#112 landed
  └─ START → #117
               └─ START → #124 docs-only context leaf (PR #128)

#109 landed
  └─ COMPLETE → #119 System Specification — LANDED via PR #126
                    └─ COMPLETE → #83 canonical Agent procedure owner — ACTIVE PR #129
                                         └─ COMPLETE → #84 structural Agent behavior controls

#82 landed
  ├─ COMPLETE → #98 typed disjoint write boundary — lifecycle READY
  └─ COMPLETE → #83

#82 + #119 + #98 + #83
  └─ COMPLETE → #120 typed requirement/completeness admission
```

#119 no longer owns an active write lease; #83 is the current convergence owner for Agent-facing procedure deduplication. #124 remains disjoint because it writes only `docs/design/context-closure/**`.

## Verification/autonomy spine

```text
#19 verification-skill → physical-oracle contract
  ↓ COMPLETE
#20 executable Feature Map canary
  ├─ COMPLETE → #66 changed-code → journey → oracle gate
  └─ COMPLETE → #4 single-Issue unattended canary

#3 + #15 + #18 + #19 + #20
  └─ COMPLETE → #4
                  ├─ COMPLETE → #21 failure → executable rule
                  ├─ COMPLETE → #5/#6/#7/#8/#10 code-intel atoms
                  └─ with #3 COMPLETE → #14 cross-repo canary

#4 + #21 + #46
  └─ COMPLETE → #22 bounded multi-Issue program
```

#4 lifecycle `ready` is compatible with unresolved dependencies. Under landed #82 semantics, provider-derived schedulability remains false until #19/#20 land. This is expected behavior, not drift.

## Concurrency safety spine

```text
#44 landed
  └─ COMPLETE → #45 truthful Noodle daemon lease
                  └─ COMPLETE → #46 exact worktree/session provenance
                                  ├─ COMPLETE → #78 provider writer identity
                                  └─ COMPLETE → #99 exact open-PR exclusion

#82 landed
  └─ COMPLETE → #98 disjoint typed write boundary — READY

#45 + #46 + #98 + #99
  └─ COMPLETE → #100 concurrency invariant proof lock
```

Correctness is intended to depend on I1 truthful lease, I2 provenance, I3 disjoint boundaries, and I4 open-PR exclusion, not a fixed numeric `max_concurrency`. The full proof is not closed until those atoms land.

## Runtime upstream HOLD spine

```text
poteto/noodle#7 release
poteto/noodle#8 release
        └─ HOLD/COMPLETE → #85 upstream scheduler no-op/prompt ownership admission
```

No local workaround is inferred from the hold.

## Code-intelligence migration spine

```text
#4
 ├─ COMPLETE → #5 SQLite
 ├─ COMPLETE → #6 Tree-sitter
 ├─ COMPLETE → #7 GrepAI
 ├─ COMPLETE → #8 Serena navigation
 └─ COMPLETE → #10 SCIP validation

#5 + #6 + #7 (+ optional #8)
  └─ COMPLETE → #9 minimal causal integration
                  ├─ COMPLETE → #11 LanceDB A/B
                  └─ evidence inputs → #13 v1 convergence

#8
 └─ COMPLETE → #12 Serena bounded edit
```

Architecture diagrams do not create dependencies; exact Issue/provider facts do.

## Context-closure lane

```text
#112 landed
  └─ START → #117 parent closure problem
               └─ START → #124 six-file N projection / PR #128

#124 provider landing + consumer readback
  └─ candidate consumer evidence for external skill-concerns context-closure-engineering admission
```

## Convergence-owner rules

- System-level stable requirements: #119 landed owner `contracts/system-v1.md`.
- Agent procedure deduplication: #83 / PR #129.
- typed dependency/body digest: #82 landed.
- typed write-boundary admission: #98.
- typed requirement/completeness admission: #120 after #98/#83.
- first N-class context materialization: #124; #117 remains parent closure owner.
- feature journey/oracle compilation: #66 after #20/#46.

A new atom that overlaps an active convergence owner waits or explicitly replaces it through provider-backed dependency/readback.

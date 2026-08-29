# System Projection

> N-class planning projection only. Canonical system requirements remain in `contracts/system-v1.md`; executable authority remains in tests/contracts/provider readback.

## Directory ownership map

| Surface | Primary owner | Admitted writer / transition | Readback | State-machine role |
|---|---|---|---|---|
| `.agents/` | repository procedure surface | exact Skill/procedure atom | skill discovery + source readback | P-class engineering route |
| `.noodle/` | upstream Noodle/runtime adapter | Noodle/control APIs and admitted adapter paths | order/session/worktree/runtime state | scheduling + isolation |
| `contracts/` | stable system/feature contract surfaces | exact contract atom | direct source + nearest tests | requirement/oracle boundary |
| `docs/design/` | N-class planning projection | docs-only exact atom | Git tree/path readback | planning/context snapshot |
| `migrations/` | migration evidence disposition | exact migration atom | ledger + source evidence | candidate/admission history |
| `policy/` | deterministic repository policy | exact policy atom | verify/readback | admission gate configuration |
| `tests/` | executable falsifiers | nearest implementation/contract atom | exit/output/readback | L-class proof surface when actually executed |
| `.github/workflows/` | trusted provider integration | exact workflow atom | GitHub workflow/protection readback | trusted verify/land boundary |
| candidate Git worktree | Git + Noodle ownership | repository-mutating Agent in Noodle-owned isolated worktree | head/tree/status/residue | implementation subject |
| GitHub default branch / Issue | GitHub provider | trusted lander / Issue adapter | exact merge/branch/closure state | R-class landed reality |

## Primary system flow

```text
stable System Specification
        ↓ requirement / invariant
exact GitHub Issue
        ↓ deterministic admission
Noodle order + isolated worktree
        ↓
pinned pstack / poteto-mode routing           P
        ↓
smallest implementation atom
        ↓
nearest executable contract/test/oracle       L when executed
        ↓
trusted GitHub verification
        ↓
exact-head merge / closure readback            R
        ↓
local reconciliation
```

Planning documents never sit between the execute Agent and the nearest executable boundary.

## Repair state machine

```text
candidate/PR
   ↓
trusted check failure
   ↓
classify exact failing subject/head/session
   ↓
re-enter same admitted repair lane
   ↓
new candidate head
   ↓
re-run local evidence + trusted verification
   ├─ fail → bounded retry / terminal classification
   └─ pass → exact-head provider landing
```

No repair step may silently replace the exact Issue, session, worktree, or provider subject.

## Organizational-learning state machine

```text
failure evidence
   ↓
reflect / lesson hypothesis                  P
   ↓
independent reproduction A/B
   ↓
non-case
   ↓
eval
   ↓
can lesson become executable?
   ├─ no → retain as P/N guidance
   └─ yes
        ↓
nearest test/lint/contract/oracle
        ↓
planted negative
        ↓
regression suite
```

A single failure does not authorize a new global rule.

## Context-closure planning flow

```text
owner conversation + provider reality + external claims
        ↓
source denominator freeze
        ↓
Shadow Architect MONITOR                     P/N
        ↓
Tech Lead dependency/case compilation        P/N
        ↓
this N-class context pack
        ↓
bounded candidate Issue/task packets
        ↓
normal exact-Issue execution path
```

The context pack has no mutation/landing authority.

## Authority flow

```text
P: model / pstack / Shadow / Tech Lead suggestions
         ↓ may choose procedure
L: executable local gate + exact subject/readback
         ↓ candidate admitted locally
R: GitHub/provider protected-state readback
         ↓ landed reality
N: docs/metrics/diagrams/source projections
```

`P + P` is still P. `N + consensus` is still N. Authority changes only at the owning executable/provider boundary.

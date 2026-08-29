# N-class context-closure projection

> **Authority ceiling: N.** This package is a planning projection. It describes sources, ownership, dependencies, gaps, and candidate work. It cannot satisfy a local L gate, authorize provider landing, close an Issue, or replace the mandatory execution route.

Snapshot date: `2026-08-30`.
Consumer: `ed3c/noodles#117`.
Reusable producer candidate: `ed3c/skill-concerns#9`.
Method sources: the Shadow Architect MONITOR and Tech Lead contracts in `ed3c/skills-shared`.

## Why this package exists

Long conversations and successive implementation requests bias an Agent toward the latest visible atom. Repository Issues contain detailed local acceptance criteria, but no single N-class projection currently preserves the complete source denominator, program DAG, closure gaps, molecular traceability, and drift checks.

This package compiles that planning context without modifying verified contracts. Execute Agents do not need to load it by default.

## Mandatory execution route remains unchanged

```text
AGENTS.md
  -> contracts/system-v1.md when the exact Issue requires system context
  -> exact Issue and nearest executable contract/test
  -> stop document traversal
```

This package is outside that mandatory three-node route. Shadow Architect and Tech Lead may use it to produce bounded task packets. A task packet must still resolve through the canonical route before implementation.

## Source denominator

Every run freezes the denominator before drawing conclusions. A source cannot disappear because it is inaccessible or inconvenient.

| Source class | Required identity | Current treatment |
|---|---|---|
| Owner conversation | conversation date/range and named decisions | `PRESENT`; this snapshot captures the clean-migration, pstack, physical-verification, three-hop, Agent-friendly architecture, specification, Issue-contract, evidence, learning, concurrency, and context-closure decisions discussed through 2026-08-30 |
| `ed3c/noodles` repository | default-branch commit/tree plus relevant file paths | `PRESENT`; exact commit/tree must be refreshed by the implementing lane before any claim about current bytes |
| GitHub Issues | exact `owner/repo#number`, body digest, provider state | `PRESENT`; this projection names known owners but stores no authoritative current state |
| Pull requests and provider events | PR number, candidate head, checks, merge/default-branch/closure readback | `PARTIAL`; traceability gaps remain explicit |
| Runtime/provider observations | runtime version, session/worktree identity, receipt digest | `PARTIAL`; only Issue-owned receipts may authorize claims |
| `ed3c/skills-shared` method contracts | exact repository commit plus concern path | `PRESENT AS METHOD SOURCE`; no implementation authority is transferred |
| `ed3c/skill-concerns` producer candidate | exact Issue and future candidate head | `PRESENT AS CANDIDATE`; not generally admitted before consumer canary |
| Referenced articles, PDFs, videos, and screenshots | URL/file identity, retrieval date, bounded extracted claim | `ABSENT_OR_UNFROZEN`; conversation summaries are hypotheses until a source is frozen |
| Local `/Users/neon/skills-shared` runtime | repository HEAD, worktree, process/monitor receipt | `NOT_EXERCISED_BY_THIS_GITHUB_PROJECTION`; the local operator lane must supply its own receipt |

Allowed missing-source states are exactly:

```text
ABSENT
BLOCKED
NOT_EXERCISED
STALE
```

Missing sources remain in the denominator and block only the claims that depend on them.

## Output ownership

| File | Owns |
|---|---|
| `README.md` | source denominator, authority ceiling, freshness and update law |
| `SYSTEM.md` | directory ownership, state machines, data flows, writer boundaries |
| `DAG.md` | start-readiness and completion-readiness dependencies |
| `CLOSURE.md` | problem-to-requirement-to-evidence closure matrix |
| `TRACEABILITY.md` | molecular requirement/Issue/PR/evidence chain and gaps |
| `DRIFT.md` | drift taxonomy, severity, current findings, next checks |

No file in this package owns executable truth.

## Freshness law

A projection is stale as soon as any bound Issue body, PR head, default branch, provider lock, runtime lock, or canonical specification changes. Stale projections may support investigation but cannot be used to schedule or close work without provider refresh.

## Update procedure

1. Freeze exact source identities and the denominator.
2. Run Shadow Architect in `MONITOR` mode. It may report architecture, ownership, state, evidence, and drift deltas but may not write implementation truth.
3. Run Tech Lead compilation over the full denominator. Compile dependency edges, case owners, write boundaries, convergence owners, and task packets.
4. Update all six files as one projection epoch.
5. Preserve `ABSENT`, `BLOCKED`, `NOT_EXERCISED`, `STALE`, and `TRACEABILITY_GAP` states.
6. Open molecular implementation Issues. Never convert an N finding directly into a completion claim.

## Stop laws

Stop and emit a blocker when:

- a source identity cannot be frozen;
- two active lanes claim the same write boundary;
- an implementation dependency is being used as a completion dependency without its own receipt;
- an N/P statement is being promoted to L/R;
- mutable provider state is being copied as permanent specification truth;
- the requested fix would create a second scheduler, worktree manager, router, registry, or closure database.

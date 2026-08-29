# Implementation DAG

> N-class projection for snapshot `CTX-2026-08-30T02:44:51+08:00`. Re-fetch provider state before execution.

## Edge semantics

This file distinguishes two dependency classes:

- `S` — **start-readiness**. A successor may begin bounded work after the predecessor's named interface or fact is available.
- `C` — **completion-readiness**. The successor must not claim completion or provider landing until the predecessor's exact receipt is provider-landed and read back.

An unlabeled thematic relationship is not a dependency. A closed Issue is not automatically evidence for a broader objective.

External edges use `X`. Runtime repair/reconciliation loops may be cyclic; delivery dependencies must remain acyclic.

## Current stage: context/spec convergence

```text
#112 CONTRACT SPLIT
landed: 281044f5572f9dd261f17fc6d0963b5162471788
        │
        ├─ S ─→ #109 DUNE / AGENT-FRIENDLY SPEC
        │          ├─ old PR #111 closed as superseded
        │          └─ PR #118 head 9e6ff70... awaiting exact-head rerun/landing
        │
        └─ S ─→ #117 N-CLASS CONTEXT PACK
                   branch agent/issue-117-context-closure

#109 provider landing
        └─ C ─→ #117 final source refresh and completion claim

#117 provider landing + exact consumer receipt
        └─ C ─→ ed3c/skill-concerns#9 admission convergence
```

Rationale:

- #112 removed the obsolete assumption that every Issue must carry a pre-admitted specialized feature.
- #117 can start against the landed baseline contract, but its final system/closure projection must incorporate the provider-landed #109 result or preserve #109 as pending.
- `context-closure-engineering` must not be admitted from producer prose alone; #117 supplies the first exact consumer boundary.

### Current disjoint writer lanes

| Lane | Candidate writer boundary | Convergence owner | Collision disposition |
|---|---|---|---|
| #109 / PR #118 | `AGENTS.md`, `contracts/system-v1.md`, `tests/test_agent_friendly_architecture.py` | #109 | Does not overlap #117's fixed docs-only tree. |
| #117 | exactly six files under `docs/design/context-closure/` | #117 | Must not modify #109 surfaces. |
| skill-concerns #9 | `ed3c/skill-concerns` intake/admission/Skill surfaces, not noodles | skill-concerns #9 | Cross-repository consumer receipt edge, not a shared writer. |

## Agent/document architecture stream

```text
#72 compact Agent-friendly shortest path [LANDED]
        │
        ▼
#109 full Dune-derived AF rationale and AF-01..AF-06 [AWAITING LAND]
        │ C
        ▼
#83 one canonical procedure/document owner [BLOCKED on #82]
        │
        ▼
#84 replace prose phrase locks with structural behavior controls [BLOCKED on #83]
```

Additional edge:

```text
#82 typed provider dependency/read-only Issue contract
        └─ C ─→ #83
```

`#109 → #83` is not currently encoded as an Issue dependency, but Tech Lead treats provider-landed #109 as a practical rebase/write-boundary prerequisite because both touch `AGENTS.md` and `contracts/system-v1.md`. This is recorded as a **candidate completion edge**, not silently imposed provider truth.

## Issue admission and concurrency stream

```text
#44 clean/provider-exact control checkout [LANDED]
        │
        ▼
#45 truthful single Noodle daemon lease [READY]
        │ C
        ▼
#46 exact Issue/session/worktree/branch provenance [BLOCKED]
        ├─ C ─→ #99 reject duplicate lane with exact open PR
        ├─ C ─→ #78 persist provider writer thread identity
        └─ C ─→ #66 changed-code → journey → oracle handoff

#81 isolated Codex user-config surface [LANDED]
        │
        ▼
#82 typed provider dependencies and derived schedulability [READY]
        ├─ C ─→ #83 canonical Agent procedure owners
        └─ C ─→ #98 disjoint typed write-boundary admission

#46 + #82
        └─ C ─→ admission surface shared by #98 / #99

#45 + #46 + #98 + #99
        └─ C ─→ #100 concurrency proof lock
```

Convergence owners:

- Issue-contract/provider-body/digest and dependency eligibility: #82;
- daemon liveness/ownership: #45;
- worktree/session provenance: #46;
- path-write exclusion: #98;
- duplicate/open-PR exclusion: #99;
- N-independent concurrency admission: #100.

## Verification and autonomy stream

```text
#18 poteto-mode routing [LANDED]
        │
        ▼
#19 verification-skill → physical-oracle contract [LANDED]
        │
        ▼
#20 executable metrics CLI feature-map canary [LANDED]
        │
        ├──────────────┐
        │              │
        ▼              ▼
#4 single-Issue      #66 changed-code → journey → oracle
Golden Path          also needs #46
[READY]              [BLOCKED]
        │
        ▼
#21 repeated failure → executable organizational rule [BLOCKED]
        │
        ▼
#22 bounded three-Issue autonomous program [BLOCKED]
```

#4 is the convergence owner for the first complete no-Human-Verifier Issue-to-reconcile canary. The landed infrastructure proves pieces of the path; it does not replace this end-to-end denominator.

## Feature/oracle refinement

```text
#112 mandatory baseline + optional specialized oracle [LANDED]
        │
        ├─ REVIEW ─→ #116 repo-infra specialized oracle
        │              current rationale was created under the pre-#112
        │              every-Issue-needs-feature doctrine
        │
        └─ governs all marker-free future docs/infra atoms
```

#116 is not a prerequisite for #117 or #109. It should proceed only if a recurring infrastructure behavior requires a specialized product operation beyond the mandatory baseline. It must not recreate a generic feature-registry requirement.

## Code-intelligence migration stream

```text
#4 Golden Path canary [C]
        ├─→ #5 SQLite exact-subject evidence atom
        ├─→ #6 Tree-sitter structural byte-range atom
        ├─→ #7 GrepAI candidate-only retrieval atom
        ├─→ #8 Serena read-only navigation validation
        └─→ #10 fresh SCIP validation

#5 + #6 + #7
        └─ C ─→ #9 minimal code-intelligence integration canary

#8
        └─ C ─→ #12 bounded Serena edit lifecycle

#9 with measured retrieval bottleneck
        └─ C ─→ #11 LanceDB A/B admission experiment

#5 + #6 + #7 + #9
        └─ C ─→ #13 code-intelligence v1 convergence

#8 / #10 / #11 / #12
        └─ optional evidence inputs to #13 only when their own receipts justify inclusion
```

No edge permits the historical GrepAI→SCIP→SQLite→Tree-sitter→Serena architecture diagram to become a production claim. Each atom proves only its own boundary.

## Cross-repository stream

```text
#3 GitHub protection / landing authority [LANDED]
#4 same-repository unattended canary [OPEN]
        │
        └─ C ─→ #14 target-local cross-repository execution contract
```

Target-local authority is a hard design boundary: every target repository must own its Noodle/worktree lifecycle, oracle, protection, credential scope, and live canary.

## Runtime/upstream stream

```text
poteto/noodle#7 scheduler decision-state empty-result memo
        ┐
poteto/noodle#8 selected-skill prompt ownership
        ┴─ X/C ─→ immutable upstream release
                         │
                         ▼
                    noodles #85 runtime admission
```

#85 remains blocked until both upstream changes are present in an immutable release with source/tag/asset readback. Local reimplementation would duplicate Noodle ownership.

## Order-promotion bypass stream

```text
#61 architecture-warning separation [LANDED]
        │
        ▼
#65 prove non-bypassable upstream orders-promotion seam [marker BLOCKED]
```

The stated predecessor #61 is landed. #65 therefore requires blocker re-evaluation. It may still remain blocked if the pinned upstream runtime exposes no supported seam, but that blocker must be explicit and current rather than inherited dependency prose.

## Runtime repair loop

This is an allowed operational cycle, not a delivery DAG cycle:

```text
exact PR head
  → trusted check failure
  → deterministic repair receipt
  → re-enter same Noodle worktree
  → new exact head
  → trusted verification
  ├─ pass → provider landing
  └─ fail → bounded next repair or explicit escalation
```

Current landed atoms supporting the loop include #50, #54, #57, and #60. The loop does not prove that every failure is repairable.

## Open-Issue denominator by stream

Each open leaf appears once as a primary stream owner here. Cross-stream prerequisite mentions above do not create duplicate ownership.

| Stream | Open Issues |
|---|---|
| autonomy / learning | #4, #21, #22 |
| code intelligence | #5, #6, #7, #8, #9, #10, #11, #12, #13 |
| cross repository | #14 |
| runtime/concurrency/session | #45, #46, #78, #98, #99, #100 |
| order promotion / upstream | #65, #85 |
| feature-impact compilation | #66 |
| Issue/document contracts | #82, #83, #84 |
| current specification/context convergence | #109, #117 |
| optional infrastructure oracle review | #116 |

Count: `28`, matching `SRC-OPEN-ISSUES` at the snapshot.

## Phase exit for this implementation stage

The current stage is complete only when:

1. #109 receives an exact-head trusted receipt and provider landing, or remains explicitly pending in the final #117 snapshot;
2. #117 contains exactly the six bounded N-class documents and accounts for the full source/open-Issue/open-PR denominators;
3. every stale or contradictory edge is in `DRIFT.md` with a next owner;
4. one provider PR for #117 passes the mandatory baseline and lands without treating this pack as evidence;
5. skill-concerns #9 remains a separate next-stage admission unless its consumer receipt and producer controls are both available.

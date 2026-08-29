# Implementation DAG

> N-class projection for `CTX-2026-08-30T02:55:36+08:00`. Re-fetch provider state before operational use.

## Edge semantics

- `S`: start-readiness. A successor may begin bounded work after the named interface/fact exists.
- `C`: completion-readiness. A successor cannot claim completion before the predecessor's exact provider receipt lands.
- `X`: external dependency outside `ed3c/noodles`.

A thematic relation is not a dependency. Runtime repair cycles may be cyclic; delivery dependencies must remain acyclic.

## Current program convergence

```text
#112 baseline acceptance / optional specialized oracle [LANDED]
        ├─ S/C ─→ #109 Dune / AF-01..AF-06 [LANDED]
        └─ S ───→ #117 N-class context pack [IN PROGRESS]

#109 [LANDED]
        ├─ C ───→ #117 final refresh
        └─ C ───→ #119 canonical System Specification [READY]

#117 provider landing + consumer receipt
        └─ C/X ─→ ed3c/skill-concerns#9 admission convergence

#119 [READY]
        └─ C ───→ #120 stable requirement + Issue completeness

#82 + #98 + #83 + #119
        └─ C ───→ #120 [BLOCKED]
```

#117 is documentation-only and disjoint from current code/system writers. It may land independently as an N projection; its content cannot satisfy #119/#120.

## Active lanes at snapshot

| Lane | Writer boundary | PR/head | Verify state | Convergence owner |
|---|---|---|---|---|
| #82 | Issue contract/adapter/schedule-facing provider readback | #121 / `35e0feed1c321c96b43d200ee57f3197a4d38fb4` | failed run `33269399728` | #82 |
| #45 | daemon lease/start admission/runtime tests/system claim row | #122 / `30651b61b8c747c3bd8f684652fb5a59e33a2c1f` | failed run `33269402820` | #45 |
| #116 | `feature_contract.py` and focused repo-infra oracle tests | #123 / `8e35b65ba9f9be051e9a6fca1527d23acac0cf22` | failed run `33269502401` | #116 |
| #117 | exactly six files under `docs/design/context-closure/` | no PR at snapshot | implementation in progress | #117 |

The three failed PRs remain in their exact Issue/PR lanes. Repair means same lane, new exact head, rerun; not a duplicate Issue or inferred PASS.

## Document and specification stream

```text
#72 compact Agent-friendly shortest path [LANDED]
  → #109 complete Dune-derived AF requirements [LANDED]
  → #119 canonical low-change System Specification [READY]
  → #83 canonical Agent procedure/document owners [BLOCKED on #82]
  → #84 structural behavior controls replacing phrase locks [BLOCKED on #83]
```

Writer ordering:

- #119 writes `contracts/system-v1.md`.
- #83 writes `AGENTS.md`, `README.md`, `contracts/system-v1.md`, and repository Skills.
- Therefore #83 must rebase after #119 even though its formal marker currently names #82 only. Tech Lead treats `#119 C→#83` as a necessary write/convergence edge unless the #83 boundary is narrowed before implementation.

## Issue admission and concurrency stream

```text
#44 clean/provider-exact control checkout [LANDED]
  → #45 truthful single daemon lease / I1 [AWAITING_LAND, PR FAILED]
  → #46 exact Issue/session/worktree/branch provenance / I2 [BLOCKED]
       ├─→ #99 exact open-PR duplicate-lane refusal / I4
       ├─→ #78 provider writer-thread identity
       └─→ #66 changed-code → journey → oracle handoff

#81 isolated Codex user config [LANDED]
  → #82 typed dependencies/body digest/schedulability [AWAITING_LAND, PR FAILED]
       ├─→ #83 canonical procedures
       └─→ #98 typed disjoint write-boundary admission / I3

#46 + #82
  → shared admission seam for #98/#99

#45 + #46 + #98 + #99
  → #100 N-independent concurrency proof lock

#82 + #98 + #83 + #119
  → #120 stable requirement and deterministic completeness
```

Current convergence owners:

- dependency/provider-body truth: #82;
- daemon lease/liveness: #45;
- exact worktree/session provenance: #46;
- write-boundary exclusion: #98;
- duplicate/open-PR exclusion: #99;
- full Issue completeness: #120;
- concurrency proof: #100.

## Verification and autonomy stream

```text
#18 poteto-mode routing [LANDED]
  → #19 verification procedure → physical oracle [LANDED]
  → #20 executable metrics feature canary [LANDED]
  → #112 mandatory baseline + optional specialized oracle [LANDED]
       ├─→ #4 single-Issue unattended Golden Path [READY]
       ├─→ #66 changed-code/feature/journey/oracle compiler [also needs #46]
       └─→ #116 repo-infra optional oracle [AWAITING_LAND, PR FAILED]

#4
  → #21 repeated failure → executable organizational rule
  → with #21 and #46 → #22 bounded three-Issue autonomous program
```

#4 remains the convergence owner for the first complete no-Human-Verifier Issue→worktree→oracle→verify→merge→close→reconcile canary. Landed components do not close its denominator.

## Code-intelligence stream

```text
#4
  ├─→ #5 SQLite exact-subject evidence atom
  ├─→ #6 Tree-sitter structural byte-range atom
  ├─→ #7 GrepAI candidate-only retrieval atom
  ├─→ #8 Serena read-only navigation validation
  └─→ #10 fresh SCIP validation

#5 + #6 + #7
  → #9 minimal integration canary

#8
  → #12 bounded Serena edit lifecycle

#9 plus measured retrieval bottleneck
  → #11 LanceDB A/B experiment

#5 + #6 + #7 + #9
  → #13 code-intelligence v1 convergence
```

#8/#10/#11/#12 are conditional inputs to #13 only when their own receipts justify inclusion. No historical architecture diagram proves a causal chain.

## Cross-repository stream

```text
#3 GitHub exact-head authority [LANDED]
#4 same-repository unattended canary [OPEN]
  → #14 target-local cross-repository contract
```

The target repository must own its own worktree, oracle, protection/credential boundary, landing, and live canary.

## Upstream/runtime and order-promotion stream

```text
poteto/noodle#7 decision-state empty-schedule memo
poteto/noodle#8 selected-skill prompt ownership
  → X/C immutable upstream release
  → #85 exact runtime admission
```

```text
#61 architecture warning separation [LANDED]
  → #65 bounded discovery of non-bypassable upstream order-promotion seam
```

#65's named predecessor is landed, but its marker remains blocked. Its current blocker must be re-read as an upstream-seam availability question rather than stale dependency waiting.

## Runtime repair loop

```text
exact PR head
  → trusted check failure
  → exact repair receipt
  → same Noodle worktree
  → new exact head
  → trusted verification
      ├─ pass → provider landing
      └─ fail → bounded retry or explicit escalation
```

Current examples at snapshot: PRs #121, #122, and #123 are failed exact-head lanes. This is an operational cycle, not a delivery-DAG cycle.

## Full open-Issue leaf denominator

Every open Issue at the snapshot appears exactly once as a primary stream owner.

| Stream | Open Issues |
|---|---|
| autonomy / learning | #4, #21, #22 |
| code intelligence | #5, #6, #7, #8, #9, #10, #11, #12, #13 |
| cross repository | #14 |
| runtime / concurrency / session | #45, #46, #78, #98, #99, #100 |
| order promotion / upstream | #65, #85 |
| feature-impact / optional oracle | #66, #116 |
| Issue / Agent document contracts | #82, #83, #84, #120 |
| context and specification convergence | #117, #119 |

Count: `29`, matching the provider denominator.

## Stage exit for this implementation phase

This phase is complete only when:

1. the six-file #117 projection is refreshed against landed #109 and the full 29-Issue/3-PR denominator;
2. #117 changes no non-N surface;
3. the Issue is moved through exact-head baseline acceptance, provider merge/closure, and readback without using these docs as evidence;
4. skill-concerns #9 remains a separate next-stage admission until its producer controls and #117 consumer receipt both exist;
5. active failed lanes #121/#122/#123 remain explicitly failed or later traced to their exact replacement heads, never silently counted as landed.

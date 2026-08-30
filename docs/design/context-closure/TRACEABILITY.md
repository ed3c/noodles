# Molecular traceability index

> N-class index for `CTX-117-2026-08-30-63e776e-provider-20260830T004730Z`. This file points to Git, executable, and provider owners. It is not a registry, receipt, or proof surface. `[SRC-ORDER-117, OWNER_REQUIREMENT, N]`

## Trace shape

```text
source or owner problem
  -> bounded requirement or hypothesis
  -> exact Issue
  -> Noodle order, session, worktree, and branch
  -> PR and exact candidate head
  -> changed paths
  -> positive, planted-negative, and non-case controls
  -> local or specialized observed-state receipt
  -> merge, default-branch, Issue closure, and reconciliation readback
```

Missing segments are `TRACEABILITY_GAP`. A nearby Issue, commit message, closed provider object, or Agent memory cannot fill them. `[SRC-ORDER-117, OWNER_REQUIREMENT, N]` `[SRC-SYSTEM, REPOSITORY_FACT, N]`

## Landed architecture-changing atoms

The candidate and merge subjects below came from current GitHub merged-PR readback and the current Git object graph. Marker values came from exact Issue bodies. The table is still an N-class index; it does not replay hosted receipts or runtime oracles. `[SRC-PROVIDER-READBACK, R_REFERENCE, N]` `[SRC-GIT-HISTORY, REPOSITORY_FACT, N]`

| Issue / PR | Candidate -> merge | Marker at snapshot | Bounded changed boundary | Residual trace gap |
|---|---|---|---|---|
| #25 / PR #26 | `2c8aea981036676cb3a03450015a2e9e6ed519c3` -> `5b8ca52692fa7853612437cb729c6bd0f662f5af` | closed / `landed` | Register schedule task type | Hosted receipt and runtime replay not re-fetched |
| #27 / PR #28 | `f0b8fd12859f4820177ad49b85c969fc13cd4ca1` -> `333aecf2c7e2b4d161731d140ba2eef77eef6f95` | closed / `landed` | Pre-admit Noodle-owned worktree root | Runtime worktree canary not replayed |
| #30 / PR #31 | `e59315c067056f27e70a482ab316c4ff4b1ed6c9` -> `e5a7296fa977cd6c0ff06edd7680fc8f9197782c` | closed / `landed` | Prevent scheduler self-order churn | Live scheduler replay not run |
| #33 / PR #34 | `3e1248a62ead5b53b23f33d0f2f55a16cd3a6c04` -> `d042609707a1ebe8f84454319a4cb61fa602cb54` | closed / `landed` | Park execute handoff until provider landing | Current end-to-end canary remains #4 |
| #44 / PR #55 | `8094ad17df7fc814f999f5ccc4aea38819cf811d` -> `d7dfc48ac8263483ea9f639f6940a6bd639441aa` | closed / `landed` | Reject dirty/provider-stale control checkout | Does not close daemon lease |
| #50 / PR #51 | `e0361e9e00fe8a5bc901c66185c8fbf6582a53ef` -> `c8d54a3eaaa6fceead97bd1231ec3e7ded544b99` | closed / `landed` | Re-enter exact failed worktree | Current #83 repair remains open |
| #57 / PR #59 | `19ccdd1c8b9853e5c33d18f9b010a92fa95c80d2` -> `a9ab424c414ce5702e3153e24e226c8010377b64` | closed / `landed` | Execute repair command in exact worktree | No universal repair claim |
| #60 / PR #68 | `1aacbf54908948b65b57d3480da9f28d3c53d7ce` -> `915b4ea23e4a7cdea47d2caa7a5add58e077ddc6` | closed / `landed` | Admit clean-behind state for reconciliation fast-forward | Current reconciliation not exercised here |
| #61 / PR #67 | `83ceceaf991b3576a69da7ee98bcb84687a41c4e` -> `cbbd82beca1d62067df83b0b7d9e3973dbb69ff0` | closed / `landed` | Separate architecture warnings from merge invariants | Does not prove architecture quality |
| #64 / PR #87 | `1c8d8139ecbb169b39dca9cec8cdc768ff90956b` -> `69cfced02a6ecb2656ea6d67879d6343fff1f276` | closed / `landed` | Replace lexical workflow checks with semantic controls | Future workflow changes still need exact controls |
| #72 / PR #73 | `c748cf26c6d10b5f39dee5d7a2dd9c8e1af7c73c` -> `2f6f60fe8323189379605fa651ff1206eb217472` | closed / `landed` | Encode Agent-friendly shortest path | Later specification convergence supersedes detail placement |
| #82 / PR #121 | `061fc49720d6a22815e0c6b56ab2516ee3820355` -> `bbc37a084b5eccd6f313499790cf335276d0670c` | closed / `in_progress` | Typed provider dependency/body-digest contract | Provider marker mismatch blocks dependent completion |
| #94 / PR #102 | `233a401b19ca1e90dadac248bebf588b93587e7f` -> `f4a31738a4576e5f32a5579ad23472140615aba8` | closed / `landed` | N-class path convention and typed evidence rejection | Does not verify N-document truth |
| #101 / PR #104 | `c0dab95f5713b08faf130b5de3918b88e9349924` -> `1bccf30f13c5277b54a4483295a324db16e7e951` | closed / `landed` | Demote health warnings out of hard merge gate | Metrics remain descriptive |
| #109 / PR #118 | `9e6ff70ea2ec516d0535a5275b4117f17f44f72b` -> `bb42c7c4cf81ebde8d2659ae0ff0c37dbc5d9f24` | closed / `landed` | Dune-derived AF requirements | Original image truth absent |
| #112 / PR #115 | `1b3f41cb268f16f28fcc9d301937d7854fa35484` -> `281044f5572f9dd261f17fc6d0963b5162471788` | closed / `landed` | Separate Issue admission from completion evidence | Feature behavior remains target-local |
| #119 / PR #126 | `56e2df152f8daec7683ee6d9d3d18ff27197e527` -> `4b3f3e53c642dd33d0f3632bced3006c6cbf2ea3` | closed / `landed` | Canonical System Specification convergence | Implementation status remains provider-derived |
| #124 / PR #128 | `7c7b7d15c427646b68584e2251890e9c9cc88e3e` -> `fdce9f8f843f0b1842ef38d23a0a58cfb1ba428e` | closed / `landed` | First six-file N-class context pack | Mutable status prose became stale |
| #132 / PR #133 | `3fb4cfd613defd12ae2294e5aa8ec206e86bdb8c` -> `745426927f37340c30bd169223cd50f9ae7ca507` | closed / `landed` | Admitted network egress for isolated cooks | No provider-action guarantee |
| #134 / PR #135 | `9b2c1d248e2ab1450d7368b1d4b0e9a950a5c447` -> `6e46bf930726b118179dc91b1431fba96aa17851` | closed / `landed` | Shared Git-metadata write access | No commit/push guarantee for every cook |
| #130 / PR #136 | `eefd40f6b47e085fdefa255020a91c21e0b28c1a` -> `63e776e0f454f978cbccb7639cb278de1497f60a` | closed / `landed` | Stable unsupported-route prefix in trusted verifier | Existing #83 head has not consumed it |

Source for every row: `SRC-PROVIDER-READBACK`, `R_REFERENCE`, `N`; candidate/merge ancestry also `SRC-GIT-HISTORY`, `REPOSITORY_FACT`, `N`.

## Active molecular lanes

### #117 bounded context compilation

```text
owner requirement and exact Issue #117
  -> dependency #112 closed / landed
  -> Noodle order and isolated worktree
  -> branch ed3c-noodles-117-0-execute at 63e776e...
  -> six declared docs/design/context-closure/*.md paths
  -> focused N-evidence positive and planted negative
  -> tests/run.sh + ./noodles verify + direct path/readback + zero residue
  -> existing draft PR #125 at 1a0b814...                 CONVERGENCE_GAP
  -> current candidate head                               TRACEABILITY_GAP
  -> non-draft exact-head handoff                         TRACEABILITY_GAP
  -> trusted verify receipt                               TRACEABILITY_GAP
  -> merge/default branch/Issue closure                   TRACEABILITY_GAP
  -> local reconciliation                                 TRACEABILITY_GAP
```

The existing PR already names #117, but its current provider diff contains three paths outside the six-file boundary. A second PR would split ownership; convergence must preserve one provider lane and make the final provider changed-file readback exactly the six declared paths. `[SRC-ORDER-117, OWNER_REQUIREMENT, N]` `[SRC-PR-CHECKS, R_REFERENCE, N]`

### #83 canonical Agent procedure repair

```text
#82 and #119 predecessor intent
  -> Issue #83 marker awaiting_land
  -> existing PR #129 at 8def7a80...
  -> trusted verify FAIL because candidate omitted stable refusal prefix
  -> #130 landed stable prefix on main at 63e776e...
  -> repair same #83 branch/worktree/PR                    TRACEABILITY_GAP
  -> fresh exact-head trusted receipt                      TRACEABILITY_GAP
  -> merge/closure                                         TRACEABILITY_GAP
```

#82's provider marker remains `in_progress`, and the current PR head remains the old failing subject. Both gaps stay explicit. `[SRC-PROVIDER-READBACK, R_REFERENCE, N]` `[SRC-PR-CHECKS, R_REFERENCE, N]`

### #45 truthful daemon lease

```text
Issue #45 marker in_progress, dependency marker absent
  -> PR #122 at 156cb3ea...
  -> candidate self-tests PASS
  -> trusted verify FAIL / merge state DIRTY
  -> exact runtime lease receipt                           TRACEABILITY_GAP
  -> merge/closure                                         TRACEABILITY_GAP
```

The open candidate does not close I1 or any downstream concurrency invariant. `[SRC-PR-CHECKS, R_REFERENCE, N]`

### #127 start-entrypoint driver

```text
Issue #127 marker in_progress, depends-on none
  -> PR #131 at a85c655...
  -> mixed candidate check history
  -> trusted verify FAIL/SKIPPED / branch BEHIND
  -> repaired exact head                                   TRACEABILITY_GAP
  -> merge/closure                                         TRACEABILITY_GAP
```

The PR is provider evidence routing, not completion. `[SRC-PR-CHECKS, R_REFERENCE, N]`

### #98 and #120 admission lanes

```text
#82 implementation merge exists
  -> #82 provider closed but marker in_progress            CLOSURE_GAP
  -> #98 lifecycle ready but not schedulable
  -> #120 lifecycle ready but not schedulable
#83 still open/awaiting_land
  -> #120 completion blocked
```

#98 is not an exact dependency of #120 in the current body; earlier projections that drew that edge are stale planning input. `[SRC-PROVIDER-READBACK, R_REFERENCE, N]`

## Open-portfolio trace groups

The exact 27-Issue denominator is in `DAG.md`. These group pointers preserve the forward owner and missing molecular links without fabricating per-Issue evidence. `[SRC-PROVIDER-READBACK, R_REFERENCE, N]`

| Group | Exact Issues | Known owner surface | Missing molecular links |
|---|---|---|---|
| Unattended/autonomy | #4, #21, #22 | Issue bodies and system requirements | Valid dependencies/blockers, candidate heads, oracles, landing, reconciliation |
| Code intelligence | #5–#13 | Issue bodies and migration ledger | Valid blockers/dependencies, causal integration receipts, provider landings |
| Cross-repository | #14 | Issue body and cross-repo system requirement | Valid contract and target-local Issue/worktree/oracle/provider canary |
| Concurrency | #45, #46, #78, #98–#100, #127 | Issue bodies, open PRs #122/#131 | I1–I4 receipts and proof lock |
| Promotion/feature coverage | #65, #66 | Issue bodies and control-noodle maps | Valid contracts, current-subject map, required journeys/oracles |
| Agent/spec convergence | #83, #84, #120 | PR #129 and current system spec | Same-lane #83 repair, #82 provider correction, #84/#120 execution |
| Runtime upstream | #85 | foreign predecessor text | Same-repository-valid contract plus exact upstream release readback |
| Context closure | #117 | this exact Issue and draft PR #125 | Current head, handoff, trusted receipt, merge/closure/reconcile |

## Known unavailable identity segments

- Raw owner-conversation message IDs and transcript bytes. `[SRC-OWNER-CONVERSATION, ABSENT, N]`
- Raw Dune image bytes and original claims. `[SRC-DUNE-IMAGES, ABSENT, N]`
- Exact Lauren/pstack article link set. `[SRC-LAUREN-PSTACK, ABSENT, N]`
- Exact article/PDF titles, URLs, bytes, hashes, and claim mappings. `[SRC-ARTICLES-PDFS, ABSENT, N]`
- Primary PDF identity behind the procedural-shadow “PDF-derived” rubric. `[SRC-ARTICLES-PDFS, EXTERNAL_CLAIM plus ABSENT, N]`
- Hosted receipt artifacts for historical architecture-changing atoms. `[SRC-PROVIDER-READBACK, R_REFERENCE plus ABSENT, N]`
- An admitted `context-closure-engineering` Skill tree, PR, or consumer receipt. `[SRC-CONTEXT-SKILL-9, R_REFERENCE, N]`
- Proof that a future Agent read, understood, or used every source. `[SRC-ORDER-117, OWNER_REQUIREMENT, N]`

# Implementation DAG projection

> N-class projection for `CTX-117-2026-08-30-63e776e-provider-20260830T004730Z`. Edges guide planning only. Noodle and provider readback own admission and completion. `[SRC-ORDER-117, OWNER_REQUIREMENT, N]` `[SRC-SYSTEM, REPOSITORY_FACT, N]`

## Edge semantics

| Edge | Meaning | Closure authority | Source and class |
|---|---|---|---|
| `S` | Start-readiness. A readable interface or fact is sufficient for bounded, reversible work to begin. | None | `SRC-SKILLS-SHARED:agentic-tech-lead-orchestration/SKILL.md`; `METHOD_SOURCE`, `P` |
| `C` | Completion-readiness. The predecessor must close through its own exact provider/evidence lane before the successor may complete or land. | Current provider readback | `SRC-SYSTEM`; `REPOSITORY_FACT`, `N` |
| `X` | External dependency. Another repository must expose an exact target-local fact. | Target-local provider readback | `SRC-SYSTEM`; `REPOSITORY_FACT`, `N` |
| `HOLD` | A named source, experiment, supported seam, or authority is absent. | None until the hold changes | `SRC-AGENTS`; `REPOSITORY_FACT`, `N` |
| `PARALLEL` | Two bounded writers appear path-disjoint. | No safety proof | `SRC-SYSTEM`; `REPOSITORY_FACT`, `N` |

Lifecycle `ready`, adapter schedulability, `S`, and `C` are four different facts. `S` never satisfies `C`. `[SRC-ORDER-117, OWNER_REQUIREMENT, N]` `[SRC-SKILLS-SHARED:github-issue-dag-projection.md, METHOD_SOURCE, P]`

## Exact current completion graph

Only exact `noodles-depends-on` markers appear as solid `C` edges below. A missing marker, invalid cross-repository entry, or legacy prose relationship is not silently upgraded into this graph. `[SRC-PROVIDER-READBACK, R_REFERENCE, N]` `[SRC-AGENTS, REPOSITORY_FACT, N]`

```text
#112 provider closed + marker landed
  C -> #117 ready and schedulable

#82 provider closed + marker in_progress             COMPLETION GAP
  C -> #83 awaiting_land
  C -> #98 ready
  C -> #120 ready

#119 provider closed + marker landed
  C -> #83 awaiting_land
  C -> #120 ready

#83 provider open + marker awaiting_land             COMPLETION GAP
  C -> #84 blocked
  C -> #120 ready

#46 provider open + marker blocked                   INVALID BLOCKER CONTRACT
  C -> #78 blocked
  C -> #99 blocked

#45 + #46 + #98 + #99
  C -> #100 blocked

poteto/noodle#7 + poteto/noodle#8
  X -> #85 blocked                                    INVALID SAME-REPO CONTRACT
```

Exact Issue-contract readback makes #117 the only currently schedulable open Issue in this denominator. #98 and #120 are lifecycle `ready` but fail dependency readiness because closed Issue #82 still carries marker `in_progress`; #120 also waits for open #83. `[SRC-ORDER-117, R_REFERENCE, N]` `[SRC-PROVIDER-READBACK, R_REFERENCE, N]`

## Start-readiness graph

```text
#124 landed six-file materialization
  S -> #117 source-bound refresh and full compilation

#130 landed stable "Unsupported routes fail closed:" prefix
  S -> repair the existing #83 lane without changing #130's verifier ownership

#112 landed baseline/specialized decoupling
  S -> #117 documentation-only candidate

current GitHub portfolio + pinned public method bytes
  S -> bounded Shadow/Tech Lead projection
```

These start edges are planning results. They do not authorize #83, #117, or any other completion transition. `[SRC-PACK-124, REPOSITORY_FACT, N]` `[SRC-GIT-HISTORY, REPOSITORY_FACT, N]` `[SRC-SKILLS-SHARED, METHOD_SOURCE, P]`

## Current #117 lane

```text
#112 provider readback satisfied
  S -> Noodle-owned #117 worktree at 63e776e...

#124 landed pack + historical #117 projection
  S -> current six-file compilation

local focused controls + baseline acceptance + direct readback + zero residue
  C -> one exact non-draft PR head

draft PR #125 at 1a0b814... already owns Refs ed3c/noodles#117
  HOLD -> remove its three-path provider-diff surplus by converging the current six-file candidate onto that one provider lane

trusted exact-head verification
  C -> provider merge + default-branch + Issue closure readback

provider landing
  C -> local Noodle reconciliation
```

The lane may start because #112 is closed/landed. It cannot complete from the start edge, from these documents, or from the existing draft PR. `[SRC-ORDER-117, OWNER_REQUIREMENT, N]` `[SRC-PREDECESSOR-112, R_REFERENCE, N]` `[SRC-PR-CHECKS, R_REFERENCE, N]`

## Integrated architecture facts

| Atom | Exact repository/provider pointer | Bounded fact | Residual | Source and class |
|---|---|---|---|---|
| #112 | PR #115 candidate `1b3f41c...`, merge `281044f...`, Issue closed/landed | Baseline acceptance and specialized feature evidence are separate. | No undeclared feature behavior is proven. | `SRC-PREDECESSOR-112`; `R_REFERENCE`, `N` |
| #119 | PR #126 candidate `56e2df1...`, merge `4b3f3e5...`, Issue closed/landed | Canonical System Specification is integrated. | Mutable implementation status remains provider-owned. | `SRC-GIT-HISTORY`, `SRC-PROVIDER-READBACK`; `REPOSITORY_FACT` plus `R_REFERENCE`, `N` |
| #124 | PR #128 candidate `7c7b7d1...`, merge `fdce9f8...`, Issue closed/landed | First six-file context pack is integrated. | Content freshness was not durable. | `SRC-PACK-124`; `REPOSITORY_FACT` plus `R_REFERENCE`, `N` |
| #130 | PR #136 candidate `eefd40f...`, merge/current main `63e776e...`, Issue closed/landed | Trusted route refusal now keys the stable prefix. | Existing #83 head still fails until repaired. | `SRC-GIT-HISTORY`, `SRC-PR-CHECKS`; `REPOSITORY_FACT` plus `R_REFERENCE`, `N` |
| #132/#134 | PRs #133/#135, merges `7454269...`/`6e46bf9...` | Carrier config grants network and shared Git-metadata access. | Config does not prove every future provider action. | `SRC-GIT-HISTORY`, `SRC-CARRIER-134`; `REPOSITORY_FACT` plus `R_REFERENCE`, `N` |
| #82 | PR #121 candidate `061fc49...`, merge `bbc37a0...`; Issue provider closed but marker `in_progress` | Typed dependency code is in main. | Its own provider marker blocks dependent completion readback. | `SRC-GIT-HISTORY`, `SRC-PROVIDER-READBACK`; `REPOSITORY_FACT` plus `R_REFERENCE`, `N` |

## Historical thematic graph

The following dotted relationships preserve owner intent from the earlier context projection. They are not current Issue-contract edges where exact dependency markers are absent. `[SRC-OLD-117, HISTORICAL_PROJECTION, N]` `[SRC-PROVIDER-READBACK, R_REFERENCE, N]`

```text
verification/autonomy:
  #19 ...> #20 ...> #4 ...> #21 ...> #22
                       \...> #14
                       \...> #5/#6/#7/#8/#10 ...> #9 ...> #13

code intelligence:
  #5 + #6 + #7 ...> #9 ...> #11 and #13
  #8 ...> #12

concurrency:
  #44 ...> #45 ...> #46 ...> #78 and #99
  #82 ...> #98
  #45 + #46 + #98 + #99 ...> #100

feature coverage:
  #20 + #46 ...> #66
```

These relationships must be normalized into valid exact Issue contracts before scheduler or completion use. A diagram does not create a dependency. `[SRC-AGENTS, REPOSITORY_FACT, N]`

## Current open-Issue denominator

GitHub returned these 27 open Issues at the snapshot. “Adapter disposition” is the exact `./noodles issue contract` result or the common parse failure observed for the named group. `[SRC-PROVIDER-READBACK, R_REFERENCE, N]`

| Issue(s) | Marker state | Exact dependency marker | Adapter disposition | Bounded owner |
|---|---|---|---|---|
| #4 | `ready` | absent | not schedulable; dependency marker absent | Unattended Issue-to-reconcile canary |
| #5–#14 | `blocked` | absent | parse fails; exact blocker marker absent | Code-intelligence leaves/convergence and cross-repo canary |
| #21–#22 | `blocked` | absent | parse fails; exact blocker marker absent | Executable learning and bounded autonomy |
| #45 | `in_progress` | absent | not schedulable; wrong lifecycle plus missing dependency marker | Truthful daemon lease |
| #46 | `blocked` | absent | parse fails; exact blocker marker absent | Worktree/session provenance |
| #65–#66 | `blocked` | absent | parse fails; exact blocker marker absent | Promotion seam and changed-code journey gate |
| #78 | `blocked` | #46 | parse fails; exact blocker marker absent | Provider writer identity |
| #83 | `awaiting_land` | #82, #119 | not schedulable; lifecycle and #82 marker mismatch | Canonical Agent procedure owner |
| #84 | `blocked` | #83 | parse fails; exact blocker marker absent | Structural procedure controls |
| #85 | `blocked` | foreign poteto/noodle #7/#8 | parse fails; cross-repository dependency rejected | Upstream runtime admission |
| #98 | `ready` | #82 | not schedulable; #82 is closed/`in_progress` | Typed disjoint write boundaries |
| #99 | `blocked` | #46 | parse fails; exact blocker marker absent | Exact open-PR exclusion |
| #100 | `blocked` | #45, #46, #98, #99 | parse fails; exact blocker marker absent | Concurrency proof lock |
| #117 | `ready` | #112 | schedulable; no adapter reasons | Full bounded program context |
| #120 | `ready` | #82, #83, #119 | not schedulable; #82 marker mismatch and #83 open | Typed requirement completeness |
| #127 | `in_progress` | none | not schedulable; wrong lifecycle | Two-state start-entrypoint driver |

## Current open-PR denominator

| PR | Draft | Exact head | Merge/check readback | Issue relation and consequence |
|---|---:|---|---|---|
| #122 | no | `156cb3ea814b947d05c38177fc44511579d6b013` | `DIRTY`; candidate self-tests PASS, trusted `verify` FAIL | Exactly `Refs ed3c/noodles#45`; no lease, merge, or closure claim follows. |
| #125 | yes | `1a0b81441a44d6179240dd7355f12a7fdfed2058` | `BEHIND`; candidate self-tests PASS, trusted `verify` FAIL | Exactly `Refs ed3c/noodles#117`, but provider changed-file readback includes `.noodle.toml`, `contracts/system-v1.md`, and `tests/test_agent_friendly_architecture.py` beyond the six declared files. It is the one-PR convergence lane, not yet an admissible final surface. |
| #129 | no | `8def7a80f2e6d2a4acb9a2cdc1005ac489d59086` | `DIRTY`; candidate self-tests PASS, trusted `verify` FAIL | Exactly `Refs ed3c/noodles#83`; must be repaired on the same lane after #130. |
| #131 | no | `a85c65530201b0f2d7eb6f7e4063b1fa92b7c4f4` | `BEHIND`; mixed candidate self-test history, trusted `verify` FAIL/SKIPPED | Exactly `Refs ed3c/noodles#127`; open candidate is not provider completion. |

Source for the whole table: `SRC-PR-CHECKS`, `R_REFERENCE`, `N`.

## Convergence owners

| Concern | Exact owner | Current use | Source and class |
|---|---|---|---|
| Stable system requirements | #119 and `contracts/system-v1.md` | Canonical; #117 does not edit it. | `SRC-SYSTEM`, `SRC-GIT-HISTORY`; `REPOSITORY_FACT`, `N` |
| Typed dependency/provider body | #82 and `issue_contract.py` | Code integrated; provider marker drift remains. | `SRC-GIT-HISTORY`, `SRC-PROVIDER-READBACK`; mixed `REPOSITORY_FACT` and `R_REFERENCE`, `N` |
| Trusted execute-route prefix | #130 and `skill_contract.py` | Landed; #83 must consume it without rewriting its authority. | `SRC-GIT-HISTORY`; `REPOSITORY_FACT`, `N` |
| Agent procedure deduplication | #83 / PR #129 | One existing repair lane; no sibling PR. | `SRC-PR-CHECKS`; `R_REFERENCE`, `N` |
| Typed write boundaries | #98 | Ready marker, completion blocked by #82 marker drift. | `SRC-PROVIDER-READBACK`; `R_REFERENCE`, `N` |
| Typed requirement completeness | #120 | Separate from #98; completion waits on #82/#83. | `SRC-PROVIDER-READBACK`; `R_REFERENCE`, `N` |
| First context materialization | #124 | Landed source input. | `SRC-PACK-124`; mixed `REPOSITORY_FACT` and `R_REFERENCE`, `N` |
| Full bounded context compilation | #117 worktree / existing PR #125 | The worktree is the current six-file writer; #125 is the provider relation whose history and changed-file readback still require convergence. | `SRC-ORDER-117`, `SRC-PR-CHECKS`; `OWNER_REQUIREMENT` plus `R_REFERENCE`, `N` |
| Reusable context compiler | `ed3c/skill-concerns#9` | Producer proposal only; consumer #117 does not admit it. | `SRC-CONTEXT-SKILL-9`; `R_REFERENCE`, `N` |

# Implementation DAG projection

> N-class projection for `CTX-117-2026-08-30-6e46bf9-provider-20260829T212905Z`. Edges guide planning only. Noodle and provider readback own admission and completion. `[SRC-ORDER-117, OWNER_REQUIREMENT, N]` `[SRC-SYSTEM, REPOSITORY_FACT, N]`

## Edge semantics

| Edge | Meaning | Completion authority | Source and class |
|---|---|---|---|
| `S` | Start-readiness. A named interface or fact is sufficient to begin bounded work. | None | `SRC-SYSTEM`, concurrency section; `REPOSITORY_FACT`, `N` |
| `C` | Completion-readiness. The predecessor must provider-land and read back before the successor may complete or land. | Current provider readback | `SRC-SYSTEM`, concurrency and Golden Path sections; `R_REFERENCE`, `N` |
| `X` | External dependency. A target outside this repository must expose the named immutable fact. | Target-local provider readback | `SRC-SYSTEM`, cross-repository section; `R_REFERENCE`, `N` |
| `HOLD` | The named experiment, supported seam, or target-local authority is absent. | None until the hold condition changes | `SRC-AGENTS`, NO PROSE MIGRATION; `REPOSITORY_FACT`, `N` |
| `PARALLEL` | Two bounded writers appear disjoint. | No safety proof | `SRC-SYSTEM`, concurrency section; `N` |

`READY`, `S`, and `C` are different. Lifecycle `ready` does not prove derived schedulability. Start-readiness does not prove completion-readiness. `[SRC-ORDER-117, OWNER_REQUIREMENT, N]` `[SRC-SYSTEM, REPOSITORY_FACT, N]`

## Facts available at this snapshot

| Fact | Exact pointer | What it establishes | What it does not establish | Class |
|---|---|---|---|---|
| #112 integration | merge #115, commit `281044f5572f9dd261f17fc6d0963b5162471788` in `SRC-GIT-HISTORY`; closed and marker state `landed` in `SRC-PREDECESSOR-112` | Baseline ancestry contains mandatory baseline acceptance plus optional specialized verification. The provider predecessor is satisfied at the snapshot. | Future provider state or every behavior beyond the atom | `REPOSITORY_FACT` plus `R_REFERENCE`, `N` |
| #109 integration | merge #118, commit `bb42c7c4cf81ebde8d2659ae0ff0c37dbc5d9f24`; closed in `SRC-PROVIDER-READBACK` | Baseline ancestry contains AF-01 through AF-06 changes, and the Issue is provider-closed at the snapshot. | Repository-wide semantic owner enforcement | `REPOSITORY_FACT` plus `R_REFERENCE`, `N` |
| #82 integration | merge #121, commit `bbc37a084b5eccd6f313499790cf335276d0670c` | Baseline ancestry contains typed dependency and derived schedulability changes. | Current dependent Issue states | `REPOSITORY_FACT`, `N` |
| #116 integration | merge #123, commit `79ebb22e554ca3279f6688345d8607db66c4bd19`; closed in `SRC-PROVIDER-READBACK` | Baseline ancestry contains `repo-infra-verify-oracle`, and the Issue is provider-closed at the snapshot. | Broad need for the optional oracle | `REPOSITORY_FACT` plus `R_REFERENCE`, `N` |
| #119 integration | merge #126, commit `4b3f3e53c642dd33d0f3632bced3006c6cbf2ea3`; closed in `SRC-PROVIDER-READBACK` | Baseline ancestry contains canonical System Specification convergence, and the Issue is provider-closed at the snapshot. | Future requirement implementation state | `REPOSITORY_FACT` plus `R_REFERENCE`, `N` |
| #124 integration | merge #128, commit `fdce9f8f843f0b1842ef38d23a0a58cfb1ba428e`; closed in `SRC-PROVIDER-READBACK` | Baseline contains the first six-file context pack, and the Issue is provider-closed at the snapshot. | Current content freshness | `REPOSITORY_FACT` plus `R_REFERENCE`, `N` |
| #132 integration | merge #133, commit `745426927f37340c30bd169223cd50f9ae7ca507`; closed in `SRC-PROVIDER-READBACK` | Baseline ancestry grants admitted network egress through `.noodle.toml`. | GitHub authentication or provider mutation authority | `REPOSITORY_FACT` plus `R_REFERENCE`, `N` |
| #134 integration | merge #135, commit `6e46bf930726b118179dc91b1431fba96aa17851`; closed in `SRC-CARRIER-134` | Current default branch grants isolated cooks configured write access to shared Git metadata. | A successful commit, authenticated GitHub API access, or provider handoff | `REPOSITORY_FACT` plus `R_REFERENCE`, `N` |
| #117 admission | Exact Issue #117 is open, marker state `ready`, depends on #112, and declares no feature. Exact Issue #112 is closed with marker state `landed`, PR #115, head `1b3f41c...`, and merge `281044f...`. | The provider body matches the supplied order markers, and the declared predecessor is provider-landed at the snapshot. | Future completion, hosted checks, or handoff through the required CLI | `SRC-PROVIDER-READBACK`, `SRC-PREDECESSOR-112`; `R_REFERENCE`, `N` |
| Current Issue and PR portfolio | `SRC-PROVIDER-READBACK` | 28 open Issues and three open PRs with exact heads through `2026-08-29T21:28:21Z`. | Future provider state or hosted check results | `R_REFERENCE`, `N` |

## Current #117 lane

```text
#112 integration present in baseline
  S -> #117 admitted execute session

#124 six-file materialization present in baseline
  S -> #117 full context, closure, drift, and traceability compilation

#117 draft PR #125 already exists at c120c6e...
  HOLD -> choose one exact convergence path before handoff

#117 local controls at exact candidate head
  C -> one exact PR and issue handoff

trusted exact-head provider receipt
  C -> merge, default-branch readback, and Issue closure

provider landing
  C -> local Noodle reconciliation
```

Sources: `SRC-ORDER-117`, `OWNER_REQUIREMENT`, `N`; `SRC-BASELINE`, `REPOSITORY_FACT`, `N`; `SRC-PROVIDER-READBACK`, `R_REFERENCE`, `N`; `SRC-SYSTEM`, `REPOSITORY_FACT`, `N`.

The local work may start because the supplied order says #112 satisfied admission. Completion still requires focused controls, baseline acceptance, direct readback, zero residue, exact PR handoff, trusted verification, merge, closure, and reconciliation. `[SRC-ORDER-117, OWNER_REQUIREMENT, N]` `[SRC-AGENTS, REPOSITORY_FACT, N]`

## System and Agent document convergence

```text
#72 compact Agent-friendly route              integrated in baseline
  C -> #109 AF-01 through AF-06               merge #118 in baseline
       C -> #119 canonical System Specification merge #126 in baseline

#82 typed dependency contract                 merge #121 in baseline
  C -> #83 canonical Agent procedure owner    awaiting_land through PR #129
       C -> #84 structural procedure controls blocked on #83

#82 + #119 + #98 + #83
  C -> #120 typed requirement completeness    ready; depends on #82, #83, #119
```

Sources: integrated nodes use `SRC-GIT-HISTORY`, `REPOSITORY_FACT`, `N`. Successor states and declared dependencies use `SRC-PROVIDER-READBACK`, `R_REFERENCE`, `N`. Older thematic edges use `SRC-PACK-124` and `SRC-OLD-117`, `HISTORICAL_PROJECTION`, `N`.

The current pack does not assign a new writer for `AGENTS.md` or `contracts/system-v1.md`. #117 writes only the six files in this directory. `[SRC-ORDER-117, OWNER_REQUIREMENT, N]`

## Verification and autonomy stream

```text
#18 poteto-mode route                         merge #39 in baseline
  C -> #19 feature verification contract      merge #103 in baseline
       C -> #20 metrics feature canary         merge #110 in baseline

#3 + #15 + #18 + #19 + #20
  C -> #4 unattended single-Issue canary       ready; legacy body lacks noodles-depends-on
       C -> #21 failure to executable rule     blocked; legacy body lacks noodles-depends-on
       C -> #22 bounded multi-Issue program    blocked; legacy body lacks noodles-depends-on

#20 + #46
  C -> #66 changed code to journey to oracle   blocked; legacy body lacks noodles-depends-on
```

Sources: merge nodes use `SRC-GIT-HISTORY`, `REPOSITORY_FACT`, `N`. Current states and missing typed dependency markers use `SRC-PROVIDER-READBACK`, `R_REFERENCE`, `N`. Thematic predecessor edges use `SRC-OLD-117`, `HISTORICAL_PROJECTION`, `N`. The system requirements come from `SRC-SYSTEM`, `REPOSITORY_FACT`, `N`.

The merged parts prove only their bounded repository atoms. They do not close the end-to-end #4, #21, #22, or #66 denominators. `[SRC-SYSTEM, REPOSITORY_FACT, N]` `[SRC-OLD-117, HISTORICAL_PROJECTION, N]`

## Concurrency stream

```text
#44 clean and provider-exact control checkout integrated
  C -> #45 truthful daemon lease               in_progress through PR #122
       C -> #46 exact session and worktree provenance, blocked legacy Issue
            C -> #78 provider writer identity, blocked on #46
            C -> #99 open-PR exclusion, blocked on #46

#82 typed provider dependency truth integrated
  C -> #98 disjoint typed write boundary       ready; depends on landed #82

#45 + #46 + #98 + #99
  C -> #100 concurrency invariant proof lock, blocked on #45, #46, #98, #99

#127 two-state start-entrypoint driver         in_progress; no open PR in provider snapshot
```

Sources: integrated nodes and remote candidate `origin/ed3c-noodles-45-0-execute@156cb3e...` use `SRC-GIT-HISTORY`, `REPOSITORY_FACT`, `N`. Current Issue and PR states use `SRC-PROVIDER-READBACK`, `R_REFERENCE`, `N`. Thematic edges use `SRC-PACK-124` or `SRC-OLD-117`, `HISTORICAL_PROJECTION`, `N`.

The intended invariants are I1 truthful lease, I2 exact provenance, I3 disjoint writes, and I4 duplicate PR exclusion. A numeric concurrency setting cannot replace them. `[SRC-SYSTEM, REPOSITORY_FACT, N]`

## Code-intelligence migration stream

```text
#4
  C -> #5 SQLite evidence atom
  C -> #6 Tree-sitter byte-range atom
  C -> #7 GrepAI retrieval atom
  C -> #8 Serena navigation validation
  C -> #10 SCIP validation

#5 + #6 + #7
  C -> #9 minimal causal integration
       C -> #11 LanceDB experiment after a measured bottleneck
       C -> #13 v1 convergence

#8
  C -> #12 bounded Serena edit lifecycle
```

Source: `SRC-OLD-117`, historical migration stream; `HISTORICAL_PROJECTION`, `N`. The migration dispositions remain in `SRC-BASELINE:migrations/skills-shared/ledger.json`, `REPOSITORY_FACT`, `N`. GitHub marks #5 through #14 blocked at `SRC-PROVIDER-READBACK`, `R_REFERENCE`, `N`.

An architecture diagram cannot create these dependencies or prove a production causal chain. Each atom closes only its declared evidence boundary. `[SRC-AGENTS, REPOSITORY_FACT, N]`

## Cross-repository stream

```text
#3 target GitHub protection and landing controls integrated
#4 same-repository unattended canary still not established here
  C -> #14 target-local cross-repository canary
```

Sources: #3 merge is in `SRC-GIT-HISTORY`, `REPOSITORY_FACT`, `N`. #4 and #14 planning edges use `SRC-OLD-117`, `HISTORICAL_PROJECTION`, `N`. The authority rule comes from `SRC-SYSTEM`, `REPOSITORY_FACT`, `N`.

Every mutated repository must own its Noodle worktree, oracle, protection, credential scope, and live canary. A central noodles receipt cannot prove the target repository correct. `[SRC-SYSTEM, REPOSITORY_FACT, N]`

## Runtime and upstream holds

```text
poteto/noodle#7 immutable release fact
poteto/noodle#8 immutable release fact
  X and C -> noodles #85 runtime admission

#61 architecture warning split integrated
  S -> #65 supported non-bypassable order-promotion seam or HOLD
```

Source: `SRC-OLD-117`, runtime and order-promotion streams; `HISTORICAL_PROJECTION`, `N`. GitHub marks #65 and #85 blocked at `SRC-PROVIDER-READBACK`, `R_REFERENCE`, `N`. The external release facts remain `UNKNOWN_CURRENT` because this snapshot queried only `ed3c/noodles`.

No local wrapper is inferred for an upstream-owned missing seam. `[SRC-AGENTS, REPOSITORY_FACT, N]`

## Current open-Issue denominator

GitHub returned these 28 open Issues through `2026-08-29T21:28:21Z`. A missing dependency value means the legacy body has no exact `noodles-depends-on` marker. `[SRC-PROVIDER-READBACK, R_REFERENCE, N]`

| Issue | Marker state | Declared dependency | Bounded owner |
|---|---|---|---|
| #4 | `ready` | missing | Unattended Issue-to-reconcile canary |
| #5 | `blocked` | missing | SQLite evidence atom |
| #6 | `blocked` | missing | Tree-sitter byte-range atom |
| #7 | `blocked` | missing | GrepAI retrieval atom |
| #8 | `blocked` | missing | Serena navigation validation |
| #9 | `blocked` | missing | Code-intelligence integration |
| #10 | `blocked` | missing | SCIP validation |
| #11 | `blocked` | missing | LanceDB experiment |
| #12 | `blocked` | missing | Serena edit lifecycle |
| #13 | `blocked` | missing | Code-intelligence convergence |
| #14 | `blocked` | missing | Cross-repository canary |
| #21 | `blocked` | missing | Failure-to-executable-rule path |
| #22 | `blocked` | missing | Bounded multi-Issue program |
| #45 | `in_progress` | missing | Truthful Noodle daemon lease |
| #46 | `blocked` | missing | Worktree provenance |
| #65 | `blocked` | missing | Order-promotion seam |
| #66 | `blocked` | missing | Changed-code journey gate |
| #78 | `blocked` | #46 | Provider writer identity |
| #83 | `awaiting_land` | #82 and #119 | Canonical Agent procedure owner |
| #84 | `blocked` | #83 | Structural procedure controls |
| #85 | `blocked` | foreign `poteto/noodle#7` and `#8` | Upstream runtime admission |
| #98 | `ready` | #82 | Disjoint write-boundary admission |
| #99 | `blocked` | #46 | Exact open-PR exclusion |
| #100 | `blocked` | #45, #46, #98, and #99 | Concurrency proof lock |
| #117 | `ready` | #112 | Full bounded program context |
| #120 | `ready` | #82, #83, and #119 | Typed requirement completeness |
| #127 | `in_progress` | none | Two-state start-entrypoint driver |
| #130 | `ready` | none | Trusted execute-route refusal |

The current count equals the old snapshot count by coincidence. Membership and states are provider facts from this snapshot, not continuity inferred from the count. `[SRC-PROVIDER-READBACK, R_REFERENCE, N]` `[SRC-OLD-117, HISTORICAL_PROVIDER_FACT, N]`

## Current open-PR denominator

| PR | Draft | Exact head | Issue relation | Completion consequence |
|---|---|---|---|---|
| #122 | no | `156cb3ea814b947d05c38177fc44511579d6b013` | Body is exactly `Refs ed3c/noodles#45` | #45 remains `in_progress`; live lease behavior is not proven by the PR. |
| #125 | yes | `c120c6e3ae242bba5b9f7cd3624164bfcc4137b4` | Body is exactly `Refs ed3c/noodles#117` | Overlaps this atom's six-file write boundary. One exact convergence decision is required before handoff. |
| #129 | no | `8def7a80f2e6d2a4acb9a2cdc1005ac489d59086` | Body is exactly `Refs ed3c/noodles#83` | #83 remains `awaiting_land` until exact-head landing and closure readback. |

Source: `SRC-PROVIDER-READBACK`, `R_REFERENCE`, `N`. Exact PR bodies, heads, bases, draft flags, and states were read. Hosted checks and future merges remain separate.

## Convergence owners

| Concern | Last known owner | Basis | Current use |
|---|---|---|---|
| Stable system requirements | #119 and `contracts/system-v1.md` | merge #126 plus `SRC-SYSTEM`, `REPOSITORY_FACT`, `N` | Canonical owner. #117 does not edit it. |
| Typed dependency and provider body | #82 and `issue_contract.py` | merge #121, `REPOSITORY_FACT`, `N` | Integrated owner. |
| Agent procedure deduplication | #83 | `SRC-PROVIDER-READBACK`, `R_REFERENCE`, `N` | `awaiting_land` through PR #129 at the snapshot. |
| Typed write-boundary admission | #98 | `SRC-PROVIDER-READBACK`, `R_REFERENCE`, `N` | `ready` and depends on landed #82 at the snapshot. |
| Typed requirement completeness | #120 | `SRC-PROVIDER-READBACK`, `R_REFERENCE`, `N` | `ready`; completion still depends on #83 landing. |
| First context materialization | #124 | merge #128, `REPOSITORY_FACT`, `N` | Baseline input to #117. |
| Full bounded program context | #117 | `SRC-ORDER-117`, `OWNER_REQUIREMENT`, `N` | Current six-file writer. |
| Feature journey and oracle compilation | #66 | `SRC-OLD-117`, `HISTORICAL_PROJECTION`, `N`; `SRC-PROVIDER-READBACK`, `R_REFERENCE`, `N` | Current marker state `blocked`; thematic completion edges remain historical. |

A new atom that overlaps an owner must wait for current provider readback or name an exact replacement. `[SRC-SYSTEM, REPOSITORY_FACT, N]`

# System projection

> N-class lookup projection for `CTX-117-2026-08-30-63e776e-provider-20260830T004730Z`. Canonical system requirements remain in `contracts/system-v1.md`. Executable and provider boundaries remain authoritative. `[SRC-SYSTEM, REPOSITORY_FACT, N]`

Source IDs resolve through `README.md`. A diagram carries the class of its cited source, but the diagram itself remains `N`.

## Responsibility boundary

`noodles` is a target-local control and evidence extension around upstream Noodle. It is not a second Agent OS, scheduler, worktree manager, requirement-status store, or provider authority. `[SRC-AGENTS, REPOSITORY_FACT, N]` `[SRC-SYSTEM, REPOSITORY_FACT, N]`

| Owner | Durable responsibility | Admitted transition | Required readback | Source and class |
|---|---|---|---|---|
| Noodle | Scheduling, orders, process isolation, and worktrees | Noodle runtime and control APIs | Exact order, session, process, and worktree state | `SRC-AGENTS`, `SRC-SYSTEM`; `REPOSITORY_FACT`, `N` |
| pstack | Probabilistic engineering route selection | Pinned `poteto-mode` route | Route packet only | `SRC-PSTACK`; `METHOD_SOURCE`, `P` |
| noodles | Target-local contracts, evidence adapters, domain invariants, and policy hooks | Exact repository atom | Nearest executable control and direct source readback | `SRC-AGENTS`, `SRC-SYSTEM`; `REPOSITORY_FACT`, `N` |
| Git | Candidate source identity and ancestry | Commit in the Noodle-owned worktree | Exact head, tree, diff, and status | `SRC-SYSTEM`; `REPOSITORY_FACT`, `N` |
| GitHub | Protected default branch, merge, checks, and Issue closure | Trusted verify and land workflows | Exact PR head, receipt, merge parent, branch head, and Issue state | `SRC-SYSTEM`; `R_REFERENCE`, `N` |
| Target repository | Feature and domain acceptance | Target-local contract, test, or oracle | Exact operation and observed artifact | `SRC-SYSTEM`, `SRC-CONTROL-NOODLE`; `L_REFERENCE` plus `METHOD_SOURCE`, `N` |

## Directory and surface map

This table describes tree `40bf4bc6f1215c36307b5c7c5628fc51ce932d46`. It does not describe live process health. `[SRC-BASELINE, REPOSITORY_FACT, N]`

| Surface | Concern | Admitted writer or transition | Readback | Role | Source and class |
|---|---|---|---|---|---|
| `.agents/bin/codex` | Repository-owned Codex carrier | Exact carrier or model atom | Argument, model, effort, and isolation controls | Carrier launch | `SRC-BASELINE`, `SRC-SYSTEM`; `REPOSITORY_FACT`, `N` |
| `.agents/skills/schedule/` | Project schedule procedure | Exact schedule-Skill atom; Noodle keeps order ownership | Skill discovery and compact-order controls | Schedule proposal | `SRC-BASELINE`, `SRC-AGENTS`; `REPOSITORY_FACT`, `N` |
| `.agents/skills/execute/` | Project execute and handoff procedure | Exact execute-Skill atom | Route, Issue digest, acceptance, and handoff controls | Candidate lane | `SRC-BASELINE`, `SRC-EXECUTE`; `REPOSITORY_FACT` plus `METHOD_SOURCE`, `P` |
| `.github/workflows/verify.yml` | Trusted candidate verification | Exact workflow atom | Semantic workflow validation and hosted receipt | Trusted verification | `SRC-BASELINE`, `SRC-SYSTEM`; `R_REFERENCE`, `N` |
| `.github/workflows/land.yml` | Exact-head merge and Issue closure | Exact workflow atom | Protection, receipt, merge, branch, and closure readback | Provider landing | `SRC-BASELINE`, `SRC-SYSTEM`; `R_REFERENCE`, `N` |
| `.noodle.toml` | Runtime, routing, network, and shared Git-metadata write configuration | Exact runtime or carrier atom | Configuration and pinned-runtime controls | Runtime admission | `SRC-BASELINE`, `SRC-CARRIER-134`; `REPOSITORY_FACT` plus `R_REFERENCE`, `N` |
| `.noodle/adapters/github` | GitHub backlog adapter | Exact adapter atom | Provider Issue and PR readback | Backlog input | `SRC-BASELINE`, `SRC-SYSTEM`; `R_REFERENCE`, `N` |
| `AGENTS.md` | Always-loaded laws and three-node route | Exact canonical document atom | Document-route controls and source readback | Context routing | `SRC-AGENTS`, `SRC-DOCUMENT-CONTROL`; `REPOSITORY_FACT` plus `L_REFERENCE`, `N` |
| `contracts/system-v1.md` | Stable system intent and requirements | Exact specification atom | Requirement identity and document-route controls | Constitution | `SRC-SYSTEM`, `SRC-DOCUMENT-CONTROL`; `REPOSITORY_FACT` plus `L_REFERENCE`, `N` |
| `docs/research/**` | N-class research | Documentation-only atom | Git path and source identity | Research snapshot | `SRC-N-EVIDENCE-CONTROL`; `L_REFERENCE`, `N` |
| `docs/design/**` | N-class design and program context | Documentation-only atom | Git path and source identity | Planning snapshot | `SRC-N-EVIDENCE-CONTROL`; `L_REFERENCE`, `N` |
| `feature_contract.py` | Baseline acceptance and optional feature oracle | Exact verification atom | Operation, observation, artifact, head, and tree controls | Completion admission | `SRC-BASELINE`, `SRC-SYSTEM`; `L_REFERENCE`, `N` |
| `issue_contract.py` | Typed Issue markers and derived dependency eligibility | Exact Issue-contract atom | Parser, provider body, digest, and predecessor controls | Admission | `SRC-BASELINE`, merge #121 in `SRC-GIT-HISTORY`; `L_REFERENCE`, `N` |
| `skill_contract.py` | Skill, schedule, and document route contracts | Exact contract atom | Parser, publish, provider-path, and route controls | Structural admission | `SRC-BASELINE`, `SRC-DOCUMENT-CONTROL`; `L_REFERENCE`, `N` |
| `github_protection.py` | Provider protection and landing checks | Exact provider-security atom | Live API and semantic workflow controls | Provider gate | `SRC-BASELINE`, `SRC-SYSTEM`; `R_REFERENCE`, `N` |
| `provider_contract.py` | External Skill provider identity | Exact provider atom | Commit, tree, license, admission, and residue | Method admission | `SRC-PROVIDER-LOCK`; `L_REFERENCE`, `N` |
| `runtime_contract.py` | Pinned Noodle runtime admission | Exact runtime atom | Version, asset, binary, process, listener, and snapshot | Runtime start | `SRC-BASELINE`; `L_REFERENCE`, `N` |
| `repair_contract.py` | Re-entry after a trusted failure | Exact repair atom | Issue, PR, head, session, worktree, and attempt receipt | Repair loop | `SRC-BASELINE`, `SRC-SYSTEM`; `L_REFERENCE`, `N` |
| `claim_contract.py` | Dead-claim detection, adoption, and release | Exact claim-lifecycle atom | Issue state, open PR, ledger session age, head, salvage ref, and release receipt | Claim lifecycle | `SRC-BASELINE`, `SRC-SYSTEM`; `L_REFERENCE`, `N` |
| `policy/*.json` | Machine-readable policy and pins | Nearest owning policy atom | Executable consumer and planted drift | Gate configuration | `SRC-BASELINE`; `L_REFERENCE`, `N` |
| `migrations/skills-shared/ledger.json` | Evidence-bounded migration disposition | Exact migration atom | Schema and evidence pointer | Candidate history | `SRC-BASELINE`, `SRC-AGENTS`; `REPOSITORY_FACT`, `N` |
| `tests/` | Positive, planted-negative, non-case, and regression controls | Nearest owning atom | Exit code, fixture, and direct readback | Local falsification | `SRC-BASELINE`, `SRC-SYSTEM`; `L_REFERENCE`, `N` |
| Candidate worktree | One exact repository mutation | Execute Agent inside Noodle-owned isolation | Head, tree, diff, and residue | Candidate subject | `SRC-ORDER-117`, `SRC-AGENTS`; `OWNER_REQUIREMENT`, `N` |

The admitted control-noodle Feature Map, Code Map, and cross-map freeze repository commit `c820cacf92d4ad5ee033224d7a1d247f287642ed`. They describe the supervised Issue-to-reconcile journey at that subject. They do not map current tree `40bf4bc6...`, and no current Feature Map coverage claim follows from their presence. `[SRC-CONTROL-NOODLE, METHOD_SOURCE, P]` `[SRC-BASELINE, REPOSITORY_FACT, N]`

## Issue to reconciled state machine

The canonical sequence comes from `SRC-SYSTEM`. Current provider state for #117 comes from the frozen provider snapshot, not this diagram. `[SRC-SYSTEM, REPOSITORY_FACT, N]` `[SRC-PROVIDER-READBACK, R_REFERENCE, N]`

```text
exact GitHub Issue
  -> deterministic admission
  -> Noodle order and isolated worktree
  -> pinned poteto-mode route                         P
  -> smallest implementation atom
  -> mandatory baseline and applicable oracle        L when executed
  -> one exact-head PR
  -> trusted GitHub verification
  -> exact-head merge and Issue closure               R when read back
  -> local reconciliation
```

Implementation handoff and repository completion are different facts. A local candidate may have complete `L` evidence while merge, default-branch, closure, and reconciliation remain open. `[SRC-SYSTEM, REPOSITORY_FACT, N]`

## Repair state machine

The repair loop preserves the Issue, PR, session, and worktree identities. It cannot convert a failed or unknown result into PASS. `[SRC-SYSTEM, REPOSITORY_FACT, N]`

```text
trusted failure at exact PR head
  -> classify Issue, PR, head, session, and worktree
  -> re-enter the same admitted repair lane
  -> produce a new exact candidate head
  -> rerun local and trusted verification
     -> pass: exact-head provider landing
     -> fail: bounded retry or terminal classification
```

## Failure to executable knowledge state machine

The system specification requires failure evidence, independent reproduction, a non-case, an eval, a nearest executable rule, a planted negative, and regression. The old provider projection assigned the remaining implementation to #21. Issue #21 has marker state `blocked` in the frozen provider snapshot. `[SRC-SYSTEM, REPOSITORY_FACT, N]` `[SRC-OLD-117, HISTORICAL_PROJECTION, N]` `[SRC-PROVIDER-READBACK, R_REFERENCE, N]`

```text
observed failure
  -> lesson hypothesis                                  P
  -> independent reproduction
  -> non-case
  -> eval
  -> nearest test, lint, contract, or oracle
  -> planted negative
  -> regression                                         L when run
```

One failure or one prose rule does not establish organizational learning. `[SRC-SYSTEM, REPOSITORY_FACT, N]`

## Context compilation state machine

This flow describes the #117 documentation process. It creates no scheduler, Issue, evidence, or provider authority. `[SRC-ORDER-117, OWNER_REQUIREMENT, N]`

```text
source denominator freeze
  -> classify repository, provider, method, owner, and absent sources
  -> compile architecture and authority deltas          P and N
  -> separate start and completion edges                P and N
  -> assign problem, case, writer, and convergence owners
  -> write six N-class files
  -> run existing local controls                         L when run
  -> exact PR and provider handoff                       R still external
```

## Data and authority flow

No downstream projection may become an upstream authority. `[SRC-SYSTEM, REPOSITORY_FACT, N]`

```text
stable system requirement or owner intent               N or owner input
  -> exact GitHub Issue and provider body                provider-owned fact
  -> Noodle order, session, and worktree                 execution topology
  -> pstack method selection                             P
  -> candidate Git head and tree                         Git subject
  -> baseline and specialized observed-state checks      L
  -> trusted exact-head receipt                          L bound to provider subject
  -> protected merge and closure readback                R
  -> context, metrics, and status projections            N
```

The following promotions are forbidden by the canonical specification. `[SRC-SYSTEM, REPOSITORY_FACT, N]`

- A Skill route cannot authorize a merge.
- Candidate-modified bytes cannot be the sole authority that admits the same candidate.
- A closed Issue cannot prove undeclared runtime behavior.
- An N-class document cannot serve as completion evidence.
- A derived status cannot become a second mutable truth.
- A central repository receipt cannot prove another repository correct.

## Context pack non-claims

The #117 order denies the following claims. `[SRC-ORDER-117, OWNER_REQUIREMENT, N]`

- The pack is not the System Specification, Issue provider, requirement registry, scheduler, worktree manager, execution authority, or evidence database.
- The pack does not prove Agent cognition, source completeness, article or PDF truth, Full Autopilot, concurrency safety, Feature Map coverage, organizational learning, or cross-repository admission.
- The pack does not modify verified Agent or system contracts.

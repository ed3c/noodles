# Context Closure Pack

> **N-class projection only.** Nothing in this directory authorizes implementation, verification, merge, Issue closure, provider mutation, or promotion from P/N to L/R. Files under `docs/research/**` and `docs/design/**` are forbidden as completion evidence by the landed N-class evidence boundary.

Snapshot ID: `CTX-2026-08-30T02:55:36+08:00`

## Exact repository/provider subject

- repository: `ed3c/noodles`
- default branch: `main`
- default-branch commit: `bb42c7c4cf81ebde8d2659ae0ff0c37dbc5d9f24`
- default-branch tree: `b450cc02578b25a7834754ad170632554e0b4ddd`
- open-Issue denominator: `29`
- open-PR denominator: `3`
- context-pack branch: `agent/issue-117-context-closure-rebased`
- retrieval time: `2026-08-30T02:55:36+08:00`

The previous internal draft was frozen before #109 landed. This snapshot supersedes its status-sensitive projections while preserving historical receipts in `TRACEABILITY.md`.

## Why this pack exists

Conversation-driven implementation can overweight the newest atom and drop older constraints, dependencies, evidence ceilings, non-claims, write boundaries, and unresolved global objectives. This pack gives Shadow Architect and Tech Lead a bounded source denominator from which to compile current State Machines, true start/completion DAG edges, closure status, molecular traceability, and drift findings.

It is not a fourth mandatory Agent hop. Execute Agents continue to use:

```text
AGENTS.md
  → contracts/system-v1.md only when the exact Issue triggers a system decision
  → exact Issue and nearest executable contract/test
  → stop document traversal
```

## Source and evidence vocabulary

| Classification | Meaning |
|---|---|
| `OWNER_REQUIREMENT` | Explicit owner intent or constraint. Design input, not physical proof. |
| `DESIGN_PROPOSAL` | Architecture or control not yet provider-landed. |
| `REPOSITORY_FACT` | Direct readback from an exact commit/tree/file. |
| `PROVIDER_FACT` | Direct Issue, PR, workflow, merge, branch, or closure readback. |
| `METHOD_SOURCE` | Pinned external procedure used to conduct this review. |
| `EXTERNAL_CLAIM` | Article, screenshot, post, or third-party statement not independently established here. |
| `ABSENT` | Required source not accessible at this execution boundary. |
| `BLOCKED` | Source is known but a prerequisite prevents a complete conclusion. |

P/L/R/N remains separate:

- `P`: Skills, prompts, model reasoning, routing, review;
- `L`: executed local control with positive/planted-negative/readback/residue;
- `R`: provider-enforced exact-head/merge/closure readback;
- `N`: inventory, projection, diagram, metric, or unverified description.

This directory is always N even when it points to L/R receipts elsewhere.

## Frozen source denominator

| ID | Exact identity | Classification | Freshness / ceiling |
|---|---|---|---|
| `SRC-OWNER-CONVERSATION` | Owner conversation from 2026-08-28 through this snapshot, including clean migration, no routine Human Verifier, pstack, verification/oracles, Dune-style Agent-friendly architecture, typed Issues, System Specification, evidence binding, no-self-authorization, derived state, and low-entropy constraints | `OWNER_REQUIREMENT` + `DESIGN_PROPOSAL` | Session-bound. Derived repository text does not make the raw conversation an L/R source. |
| `SRC-NOODLES-MAIN` | `ed3c/noodles@bb42c7c4cf81ebde8d2659ae0ff0c37dbc5d9f24`, tree `b450cc02578b25a7834754ad170632554e0b4ddd` | `REPOSITORY_FACT` | Exact at retrieval; stale when `main` moves. |
| `SRC-OPEN-ISSUES` | GitHub search `repo:ed3c/noodles is:issue is:open`, total `29` | `PROVIDER_FACT` | Exact at retrieval. Full denominator listed in `DAG.md` and `TRACEABILITY.md`. |
| `SRC-OPEN-PRS` | PR #121 head `35e0feed1c321c96b43d200ee57f3197a4d38fb4`; PR #122 head `30651b61b8c747c3bd8f684652fb5a59e33a2c1f`; PR #123 head `8e35b65ba9f9be051e9a6fca1527d23acac0cf22` | `PROVIDER_FACT` | All three exact-head verify runs were failed at retrieval; no landing claim. |
| `SRC-LANDED-109` | Issue #109; PR #118; candidate `9e6ff70ea2ec516d0535a5275b4117f17f44f72b`; verify run `33269034678`; merge `bb42c7c4cf81ebde8d2659ae0ff0c37dbc5d9f24`; tree `b450cc02578b25a7834754ad170632554e0b4ddd`; land run `33269089675` | `PROVIDER_FACT` | Exact landed Dune/AF boundary. |
| `SRC-SPEC-119` | Open Issue #119, canonical low-change System Specification convergence | `DESIGN_PROPOSAL` + `PROVIDER_FACT` | Ready. It writes `contracts/system-v1.md`; it conflicts with #83 until convergence is ordered. |
| `SRC-ISSUE-120` | Open Issue #120, stable requirement plus deterministic Issue completeness | `DESIGN_PROPOSAL` + `PROVIDER_FACT` | Blocked on #82/#98/#83/#119. |
| `SRC-SKILLS-SHARED` | `ed3c/skills-shared@52b29b38ded9eaacbf7fb1bfa8ccf69ab37870b9` | `METHOD_SOURCE` | Exact remote substitute for this run. |
| `SRC-SHADOW` | `skills/spatial-loop-systems-engineering/SKILL.md` at `SRC-SKILLS-SHARED` | `METHOD_SOURCE` | Applied read-only in `MONITOR` posture. No local daemon/process claim. |
| `SRC-TECH-LEAD` | `skills/agentic-tech-lead-orchestration/SKILL.md` at `SRC-SKILLS-SHARED` | `METHOD_SOURCE` | Applied for true dependency edges, ownership, disjoint writers, and convergence. |
| `SRC-PROCEDURAL-SHADOW` | `skills/procedural-shadow-runtime/SKILL.md` at `SRC-SKILLS-SHARED` | `METHOD_SOURCE` | Used to separate mention, execution, verification, and evidence ceilings. |
| `SRC-CONTROL-NOODLE` | `ed3c/skill-concerns@c91dbd04d1997b2e0f77907c9c2a40f55b787107`, `skills/control-noodle/SKILL.md` | `METHOD_SOURCE` | Source-frozen domain procedure; maintained map is memory, not current authority. |
| `SRC-FEATURE-MAP` | Same skill-concerns commit, `skills/feature-map-engineering/README.md` | `METHOD_SOURCE` | Hermetic evidence ceiling; target-local adapter and live behavior remain consumer-owned. |
| `SRC-CONTEXT-SKILL-ISSUE` | `ed3c/skill-concerns#9` | `DESIGN_PROPOSAL` | Open; admission waits for producer controls and this pack's exact consumer receipt. |
| `SRC-DUNE-IMAGES` | Owner-supplied `IMG_6306.png`, `IMG_6315.png` | `EXTERNAL_CLAIM` + `DESIGN_PROPOSAL` | Raw image bytes are session-bound; adapted AF-01..AF-06 are now provider-landed through #109. |
| `SRC-LAUREN-PSTACK` | Owner-supplied links/statements about pstack, verification, cloud agents, and throughput | `EXTERNAL_CLAIM` | Motivation only; no throughput number is an acceptance condition. |
| `SRC-LOCAL-SKILLS-SHARED` | `/Users/neon/skills-shared` | `ABSENT` | Host path was not mounted. This run cannot claim a local Shadow process, local HEAD, or local worktree receipt. |
| `SRC-ARTICLES-PDFS` | Articles/PDFs referenced in conversation but not supplied as complete retrievable bytes here | `ABSENT` | Retained in denominator. No content-level closure claim. |

## Current provider denominator

Open Issues at retrieval:

```text
#4 #5 #6 #7 #8 #9 #10 #11 #12 #13 #14 #21 #22
#45 #46 #65 #66 #78 #82 #83 #84 #85 #98 #99 #100
#116 #117 #119 #120
```

Open PRs at retrieval:

| PR | Issue | Exact head | Verify state |
|---|---|---|---|
| #121 | #82 | `35e0feed1c321c96b43d200ee57f3197a4d38fb4` | failed run `33269399728` |
| #122 | #45 | `30651b61b8c747c3bd8f684652fb5a59e33a2c1f` | failed run `33269402820` |
| #123 | #116 | `8e35b65ba9f9be051e9a6fca1527d23acac0cf22` | failed run `33269502401`; earlier head also failed |

A failed check is not a closed atom. The existing repair lane owns any subsequent same-Issue/new-head attempt.

## Update procedure

1. Freeze a new snapshot ID, exact default-branch commit/tree, full open-Issue denominator, and full open-PR/head denominator.
2. Preserve every inaccessible source as `ABSENT` or `BLOCKED`.
3. Re-read current tree/provider facts; never copy the previous projection forward as reality.
4. Apply Shadow Architect read-only across architecture, intent/cases, authority, lifecycle, concurrency, and evidence.
5. Let Tech Lead assign true `S` start edges and `C` completion edges, one owner per requirement/case, disjoint writer boundaries, and convergence owners.
6. Reconcile all six files as one snapshot. Every open leaf appears exactly once in the current leaf index.
7. Before delivery, prove the branch changes only these six Markdown files and contains no N-doc evidence reference.
8. Re-run executable repository controls; their result is owned by those controls, never this text.

## Stop laws

Stop and report rather than infer when:

- source identity/freshness is unknown;
- Issue/PR/head/body drift occurs after freeze;
- a thematic relation is being promoted into a dependency;
- two lanes claim the same writer or convergence owner;
- N/P is being promoted into L/R;
- an N document is proposed as evidence;
- a target-local oracle/runtime/provider/credential is unavailable;
- this pack would become a fourth mandatory hop;
- completion would require changing already verified system/Agent documents.

## File responsibilities

- `SYSTEM.md`: directory ownership, writers, State Machines, and data/authority flows.
- `DAG.md`: start/completion edges, active lanes, convergence owners, and all open leaves.
- `CLOSURE.md`: owner problem/requirement closure matrix.
- `TRACEABILITY.md`: source → Issue → branch/session → PR/head → paths → controls → landing index.
- `DRIFT.md`: omissions, contradictions, stale state, authority drift, and exact next actions.

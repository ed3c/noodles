# Context Closure Pack

> **N-class projection.** This directory describes sources, topology, closure, traceability, and drift. It cannot authorize implementation, verification, merge, Issue closure, provider mutation, or any P-to-L/R promotion. Nothing under `docs/research/**` or `docs/design/**` is admissible completion evidence.

Snapshot ID: `CTX-2026-08-30T02:44:51+08:00`

Repository subject:

- repository: `ed3c/noodles`
- provider default branch: `main`
- provider commit: `281044f5572f9dd261f17fc6d0963b5162471788`
- provider tree: `afc1ec4ab5077b16b6e03b1091a539737a6b9970`
- open-Issue denominator: `28`
- open-PR denominator at freeze: `1`, PR `#118`
- current #109 candidate head: `9e6ff70ea2ec516d0535a5275b4117f17f44f72b`
- #117 working branch at freeze: `agent/issue-117-context-closure`

## Scope

This pack exists because conversation-driven execution can overweight the latest atom and silently lose earlier constraints, non-claims, dependencies, evidence ceilings, and unfinished closure obligations. It gives Shadow Architect and Tech Lead one bounded projection from which to compile exact task packets.

Execute Agents do **not** load this directory as a fourth document hop. Their repository route remains:

```text
AGENTS.md
  → contracts/system-v1.md when the exact Issue triggers a system-level decision
  → exact Issue and nearest executable contract/test
  → stop document traversal
```

The pack may identify a missing Issue or propose a candidate packet. It does not create authority for that packet. Provider mutation remains a separate exact-subject action.

## Source and evidence vocabulary

| Classification | Meaning |
|---|---|
| `OWNER_REQUIREMENT` | Direction or constraint explicitly supplied by the repository owner. It is a design input, not physical proof. |
| `DESIGN_PROPOSAL` | A proposed architecture, requirement, DAG edge, or control not yet provider-landed. |
| `REPOSITORY_FACT` | Direct readback from an exact repository commit/tree/file. |
| `PROVIDER_FACT` | Direct GitHub Issue, PR, workflow, merge, branch, or closure readback. |
| `METHOD_SOURCE` | A pinned external procedure used to conduct Shadow/Tech Lead analysis. |
| `EXTERNAL_CLAIM` | Article, post, screenshot, or third-party statement not independently established by this pack. |
| `ABSENT` | A required source was not accessible at this execution boundary. |
| `BLOCKED` | The source is known but a prerequisite prevents a complete conclusion. |

P/L/R/N is separate from source classification:

- `P`: probabilistic guidance, including Skills, prompts, model reasoning, and reviews;
- `L`: local executable result with positive/planted-negative controls and direct readback;
- `R`: provider-enforced exact-head/merge/closure readback;
- `N`: description, inventory, projection, metric, diagram, or unverified claim.

This directory is always N even when it points to L/R receipts elsewhere.

## Frozen source denominator

| ID | Exact identity or pointer | Classification | Freshness / status |
|---|---|---|---|
| `SRC-OWNER-CONVERSATION` | Owner conversation spanning 2026-08-28 through this snapshot, including clean migration, Human Verifier removal, pstack, verification/oracles, Dune-style Agent-friendly architecture, typed Issues, evidence binding, no-self-authorization, derived state, and low-entropy requirements | `OWNER_REQUIREMENT` + `DESIGN_PROPOSAL` | Session-bound. Raw conversation is not a repository artifact; claims must remain attributed and N until implemented. |
| `SRC-NOODLES-MAIN` | `ed3c/noodles@281044f5572f9dd261f17fc6d0963b5162471788`, tree `afc1ec4ab5077b16b6e03b1091a539737a6b9970` | `REPOSITORY_FACT` | Exact at freeze; stale when `main` moves. |
| `SRC-NOODLES-TREE` | Git tree API for tree `afc1ec4ab5077b16b6e03b1091a539737a6b9970` | `REPOSITORY_FACT` | Exact at freeze. Used for `SYSTEM.md`; not a runtime-health claim. |
| `SRC-OPEN-ISSUES` | GitHub search `repo:ed3c/noodles is:issue is:open`, total `28` | `PROVIDER_FACT` | Exact at freeze; re-fetch before using the DAG operationally. |
| `SRC-OPEN-PRS` | GitHub search `repo:ed3c/noodles is:pr is:open`, PR `#118` only | `PROVIDER_FACT` | Exact at freeze; PR/head drift invalidates dependent rows. |
| `SRC-LANDED-ISSUES` | Closed Issues whose provider body records `noodles-state: landed`; selected architecture-changing subset indexed in `TRACEABILITY.md` | `PROVIDER_FACT` | Exact for cited Issue receipts; selection law is architecture/operating-fact impact, not every historical leaf. |
| `SRC-PR-118` | `ed3c/noodles#118`, base `281044f…`, head `9e6ff70…` | `PROVIDER_FACT` | Candidate tests and trusted controls passed in run `33268884263`; first receipt attempt failed because Issue #109 had not yet entered `awaiting_land`. Reopened after state correction. Landing pending. |
| `SRC-SKILLS-SHARED` | `ed3c/skills-shared@52b29b38ded9eaacbf7fb1bfa8ccf69ab37870b9` | `METHOD_SOURCE` | Pinned remote substitute used for this run. |
| `SRC-SHADOW` | `skills/spatial-loop-systems-engineering/SKILL.md` at `SRC-SKILLS-SHARED` | `METHOD_SOURCE` | Applied in read-only `MONITOR` posture. No local Shadow daemon/process claim. |
| `SRC-TECH-LEAD` | `skills/agentic-tech-lead-orchestration/SKILL.md` at `SRC-SKILLS-SHARED` | `METHOD_SOURCE` | Applied for true dependency DAG, case ownership, write boundaries, and convergence ownership. |
| `SRC-PROCEDURAL-SHADOW` | `skills/procedural-shadow-runtime/SKILL.md` at `SRC-SKILLS-SHARED` | `METHOD_SOURCE` | Used only to separate mention, execution, and verification dispositions. |
| `SRC-CONTROL-NOODLE` | `ed3c/skill-concerns@c91dbd04d1997b2e0f77907c9c2a40f55b787107`, `skills/control-noodle/SKILL.md` | `METHOD_SOURCE` | Admitted source-frozen domain procedure. Its maps are maintained memory, not current target authority. |
| `SRC-FEATURE-MAP` | Same skill-concerns commit, `skills/feature-map-engineering/README.md` | `METHOD_SOURCE` | Hermetic evidence ceiling only; target-local adapters and live behavior remain consumer-owned. |
| `SRC-CONTEXT-SKILL-ISSUE` | `ed3c/skill-concerns#9` | `DESIGN_PROPOSAL` | Open. Reusable Skill admission waits for one exact noodles consumer receipt. |
| `SRC-DUNE-IMAGES` | Owner-supplied images `IMG_6306.png` and `IMG_6315.png` in the conversation | `EXTERNAL_CLAIM` + `DESIGN_PROPOSAL` | Image bytes are not persisted in this repository. The adapted requirements are being implemented by Issue #109; original images remain session-bound. |
| `SRC-LAUREN-PSTACK` | Owner-supplied links and statements about pstack, verification, cloud agents, and PR throughput | `EXTERNAL_CLAIM` | Architectural motivation only. No numeric throughput claim is used as a noodles acceptance condition. |
| `SRC-LOCAL-SKILLS-SHARED` | `/Users/neon/skills-shared` | `ABSENT` | The host path was not mounted in this execution environment. This run therefore cannot claim a local monitor process, local working tree, or local runtime receipt. |
| `SRC-ARTICLES-PDFS` | Articles/PDFs referenced in the owner conversation but not supplied as complete retrievable bytes to this execution boundary | `ABSENT` | Keep in denominator. No content-level closure claim is made. |

## Update procedure

1. Freeze a new snapshot ID and exact repository/provider subjects.
2. Re-fetch the full open-Issue and open-PR denominators. Never continue a partial page as if complete.
3. Re-read current tree surfaces rather than copying this pack forward from memory.
4. Preserve every inaccessible source as `ABSENT` or `BLOCKED`.
5. Run Shadow Architect in read-only `MONITOR` mode and classify deltas in architecture, intent/cases, authority, lifecycle, concurrency, and evidence.
6. Let Tech Lead compile only true start/completion dependencies, one owner per requirement/case, disjoint writer boundaries, and convergence owners.
7. Update all six files as one projection. Do not update only the latest topic.
8. Reconcile every open leaf exactly once in `TRACEABILITY.md`; put every unowned or contradictory item in `DRIFT.md`.
9. Before delivery, verify that only these six Markdown files changed and that no N-class path appears in an evidence allowlist or receipt field.
10. Re-run repository controls. Their result is owned by executable surfaces, not by this text.

## Stop laws

Stop and report rather than infer when any of the following occurs:

- source identity or freshness cannot be established;
- an Issue/PR/head/body changed after the snapshot;
- a dependency is merely related rather than a true start/completion predecessor;
- two lanes claim the same write surface or convergence ownership;
- a local/P claim is being promoted to provider completion;
- an N-class document is proposed as evidence;
- the target-local oracle, runtime, provider, or credential is unavailable;
- the pack would become a mandatory fourth document hop;
- completing the pack would require modifying already verified system/Agent documents.

## File responsibilities

- `SYSTEM.md`: directory ownership, writers, State Machines, and data/authority flows.
- `DAG.md`: start/completion edges, stream owners, and convergence points.
- `CLOSURE.md`: owner problem/requirement closure matrix.
- `TRACEABILITY.md`: molecular source → Issue → PR/head → paths → controls → landing index.
- `DRIFT.md`: omissions, contradictions, stale state, authority drift, and candidate next packets.

---
name: schedule
description: Convert exact GitHub Issue contracts into minimal dependency-aware Noodle orders.
schedule: "When provider-backed backlog state requires new or revised orders"
---

# Schedule

Use this skill only for scheduling. Do not implement code here.

## Inputs

Read the backlog adapter output. Each valid item has an exact ID `owner/repo#N`, a provider-backed state, its declared `dependencies`, a derived `schedulable` flag with exact `reasons`, and the provider `body_sha256`.

Read `./noodles issue contract owner/repo#N` for the typed goal, physical acceptance, and non-claims of an item you intend to schedule. Never invent a `gh` command and never re-derive dependency waiting by hand.

## Admission

Schedule an item only when all are true:

1. ID parses as one exact GitHub Issue subject.
2. `./noodles issue validate owner/repo#N` passes for each Issue included in the published proposal. Run it only on those finalists, never across the backlog: the adapter's typed `schedulable`/`reasons` verdict is authoritative for all earlier filtering, and re-validating what the deterministic sync already computed burns provider quota without adding safety - the publish gate and admission still fail closed on any drift.
3. Issue state is `ready`.
4. The target repository is admitted by `policy/github.json`.
5. The adapter reports `schedulable: true`, which means every declared predecessor read back closed and `landed`.
6. The Issue describes one repository-mutating atom or one evidence-only audit atom.
7. No other executor claims the Issue: its exact execute branch does not already exist on the provider and its marker is not `in_progress`. A provider-rejected branch creation is another executor's claim; skip it without ordering or marker edits.

Do not schedule an item whose `reasons` are non-empty, and never patch an Issue marker to represent dependency waiting: eligibility is re-derived from provider truth on every sync. Reject when the target, subject, acceptance evidence, or non-claims are ambiguous. Reserve `blocked` for a real blocker with an explicit `<!-- noodles-blocker: owner: reason -->`.

## Ownership boundary

Noodle alone injects and owns the transient `schedule` order. Scheduler output contains only non-schedule work orders. Never emit an order whose `id` is `schedule`, and never use `schedule` as a stage.

Read `.noodle/orders.json` only to identify active order IDs; never modify it. Do not re-emit any active non-schedule order. Omitting it lets Noodle preserve its exact order and stage fields, including the active cook's session and worktree identity.

Write the complete proposal to `.noodle/orders-next.candidate.json`, then publish it through the deterministic repository contract:

```bash
python3 skill_contract.py publish .noodle/orders-next.candidate.json
```

Never write `.noodle/orders-next.json` directly. A rejected candidate must be corrected and published again; do not bypass the diagnostic.

## Order construction

Create one order per Issue. Use the exact Issue subject as `order_id`.

The order must have exactly one `execute` stage. Do not create generic planning, review, shipping, or human-approval stages. pstack performs engineering lifecycle routing inside the execute stage.

Read `required_codex_task_profiles.execute.model` from `policy/fitness.json` and set that exact model on the order's only `execute` stage. The repository-owned Codex carrier applies the paired reasoning effort from the same profile. Do not infer a model alias, substitute another supported model, add a reasoning field that pinned Noodle cannot parse, or rely on the routing default: the schedule carrier and execute carrier are intentionally distinct task types.

Pass this context verbatim:

```text
subject: owner/repo#N
target: owner/repo
claim: exact claim from Issue
physical acceptance: exact positive/negative/readback/residue requirements
non-claims: exact exclusions
dependencies: exact landed subjects
```

## Parallelism

Sibling Issues may run concurrently only when their target paths/contracts are disjoint or the Issue explicitly records a safe merge boundary. Dependency edges, not optimistic Agent judgment, determine ordering.

Admission is oldest-first among ready P0 Issues: prove disjointness against the oldest ready P0, and when the overlap cannot be proven, defer the newer sibling - never the older Issue. A whole-loop atom therefore drains the queue and runs solo instead of starving behind a stream of narrower newcomers.

Before deferring a sibling behind an active order, re-verify that the blocking claim is alive: an active order whose session is dead and whose execute branch no longer exists on the provider is stale residue to report for recovery, not a write-boundary blocker.

## Cycle summary

The publish gate writes the deterministic cycle receipt to `.noodle/schedule-cycle.json`. That receipt is the single frontier authority for the cycle, and every status value in it carries its own fixed `meaning` string.

Quote `frontier`, `winners`, `max_useful_workers`, and every per-subject status line verbatim from `.noodle/schedule-cycle.json`. Never re-derive, rename, or paraphrase a decision the receipt already states. Write the summary to `.noodle/schedule-summary.md` using the receipt's exact lines:

```text
frontier: <receipt frontier array as compact JSON>
winners: <receipt winners array as compact JSON>
max_useful_workers: <receipt max_useful_workers>
owner/repo#N: <status> - <that status's meaning from the receipt>
```

Then validate the summary against the receipt before publishing it:

```bash
python3 skill_contract.py summary .noodle/schedule-summary.md
```

A summary that contradicts the receipt fails this step and names the missing verbatim line. Correct the summary; never edit the receipt to match a story.

Status meanings are owned by `skill_contract.SCHEDULE_CLAIM_STATUS_MEANINGS` and emitted in the receipt. Read them there; this skill never restates them.

### Diagnostic routing

- signal: consecutive empty proposals while `mise.json` still lists schedulable ready issues; action: quote the receipt verbatim, then run the starvation diagnostic in order (remote claim branches vs their subject issue states -> claimed components vs ready pool -> receipt status definitions), and publish the diagnostic as data, never a re-derived causal story; why: a re-derived causal story misdiagnosed the 2026-08-31 starvation for hours.

## Prohibitions

- Do not schedule prose-only architecture migration.
- Do not infer that an adapter chain works because individual adapters exist.
- Do not schedule a Human Verifier.
- Do not ask an Agent to merge or close an Issue.
- Do not create a custom worktree; Noodle owns it.
- Do not add a capability that an external owner already supplies.

## Output

Publish Noodle orders with exact IDs and dependency order through the ownership gate above. If nothing is admitted, publish `{"orders": []}` and record the fail-closed reason.

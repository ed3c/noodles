---
name: schedule
description: Convert exact GitHub Issue contracts into minimal dependency-aware Noodle orders.
schedule: "When provider-backed backlog state requires new or revised orders"
---

# Schedule

Use this skill only for scheduling. Do not implement code here.

## Inputs

Read the backlog adapter output. Each valid item has an exact ID `owner/repo#N` and a provider-backed state.

## Admission

Schedule an item only when all are true:

1. ID parses as one exact GitHub Issue subject.
2. `./noodles issue validate owner/repo#N` passes.
3. Issue state is `ready`.
4. The target repository is admitted by `policy/github.json`.
5. Every declared predecessor has provider state `landed` and is closed.
6. The Issue describes one repository-mutating atom or one evidence-only audit atom.

Reject or mark `blocked` when the target, subject, dependency, acceptance evidence, or non-claims are ambiguous.

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

## Prohibitions

- Do not schedule prose-only architecture migration.
- Do not infer that an adapter chain works because individual adapters exist.
- Do not schedule a Human Verifier.
- Do not ask an Agent to merge or close an Issue.
- Do not create a custom worktree; Noodle owns it.
- Do not add a capability that an external owner already supplies.

## Output

Publish Noodle orders with exact IDs and dependency order through the ownership gate above. If nothing is admitted, publish `{"orders": []}` and record the fail-closed reason.

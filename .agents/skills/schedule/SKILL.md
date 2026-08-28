---
name: schedule
description: Convert exact GitHub Issue contracts into minimal dependency-aware Noodle orders.
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

## Order construction

Create one order per Issue. Use the exact Issue subject as `order_id`.

The order must have one `execute` stage unless the Issue itself proves that a second physical stage is necessary. Do not create generic planning, review, shipping, or human-approval stages. pstack performs engineering lifecycle routing inside the execute stage.

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

Write Noodle orders with exact IDs and dependency order. If nothing is admitted, emit no mutating order and record the fail-closed reason.

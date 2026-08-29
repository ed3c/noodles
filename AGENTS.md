# AGENTS.md

`noodles` is a clean control/evidence extension around upstream Noodle. It is not `skills-shared v2`, not another scheduler, and not another Agent OS.

## Golden Path

1. Read the exact GitHub Issue and validate its `noodles-*` markers.
2. Let Noodle own scheduling, process isolation, and worktrees.
3. Load external engineering knowledge through pinned provider paths.
4. Route the task with pstack; read only the nearest relevant contract and test.
5. Implement the smallest independently useful atom in the Noodle worktree.
6. Run `./noodles verify`, commit, push, set the Issue to `awaiting_land`, then open one PR with exactly one `Refs owner/repo#N` line.
7. Let trusted GitHub workflows verify the exact head, merge with that head SHA, read back the merge event, then close the exact Issue.
8. Let `./noodles reconcile` fast-forward local `main` and release Noodle's supervised containment point after provider readback.

Human Verifier is not an operational state. A person may set goals, change constraints, or handle an admitted escalation; a person is never the routine correctness oracle or merge gate.

## Agent document route

Repository-owned context uses at most three nodes:

1. `AGENTS.md` supplies always-loaded ownership and execution laws.
2. `contracts/system-v1.md` is loaded only for claim boundaries, delivery topology, cross-repository admission, or another system-level decision.
3. The exact Issue selects the nearest executable contract/test; inspect its implementation and evidence, then stop document traversal.

`./noodles verify` checks this route's declared nodes and pointers. That proves document structure, not Agent cognition: choosing and reading the route remains P-class.

## Agent-friendly shortest path

Make the locally obvious path the globally correct path: exact Issue → isolated Noodle worktree → nearest executable contract/test → mandatory baseline acceptance and any applicable physical oracle → exact-head provider gate. Keep one obvious owner/writer for each durable value, and admit exceptions only as exact bounded atoms.

For the Dune-derived rationale, ownership map, limits of current enforcement, and requirements `AF-01` through `AF-06`, read `contracts/system-v1.md`, then follow the exact Issue to its nearest executable contract/test and stop document traversal.

Comments, prose, Skills, reviews, and model consensus may guide routing and implementation, but they never replace executable tests, type/static restrictions, CI, or provider readback.

## Guarantee classes

| ID | Class | Meaning | Allowed authority |
|---|---|---|---|
| P-01 | P — probabilistic guidance | Rules, skills, prompts, routing, model reasoning. They can fail or be skipped. | May propose and navigate; never proves correctness. |
| L-01 | L — local deterministic gate | Executable gate with exit code, positive control, planted negative control, direct readback, and residue check. | May reject a candidate locally. |
| R-01 | R — provider-enforced readback | GitHub branch protection, exact-head check, merge API result, merge-parent/default-branch readback, and Issue closure readback. | May admit and land a candidate. |
| N-01 | N — non-claim | Inventory, diagrams, metrics, prose, or “component exists.” | Describes; never proves. |

Never upgrade P or N into L or R by repetition, consensus, a second Agent's review, or documentation.

## Domain knowledge placement

Place domain knowledge at the nearest executable contract/test boundary:

- domain invariant → immutable positive/negative test;
- provider assumption → live provider readback;
- parsing/adapter rule → adapter contract test;
- workflow rule → trusted workflow plus exact event/readback test.

A file near a test is still N until the test executes. Agent selection of the test is P. The test result is L. GitHub enforcement/readback is R.

## Ownership

```text
Noodle          scheduling / orders / process isolation / worktrees
pstack          engineering lifecycle routing
Agent Skills    replaceable knowledge loading
Git + GitHub    source and provider authority
noodles         correctness extensions, evidence adapters, domain invariants, policy hooks
```

Do not implement a custom scheduler, generic worker manager, custom worktree lifecycle, generic retry engine, generic review framework, or generic release ledger here.

## NO PROSE MIGRATION

A capability enters `noodles` only when all are true:

1. historical physical evidence exists or a fresh physical experiment passes;
2. the exact claim and non-claims are recorded;
3. Noodle, pstack, Agent Skills, Git, or GitHub does not already own the lifecycle;
4. the implementation is the smallest independently useful atom;
5. the capability passes the local gate and provider admission path.

Migration dispositions are only `MIGRATE`, `REVALIDATE`, `ADAPT_EXTERNAL`, `DROP`, and `HOLD`.

## Issue and PR contract

Every schedulable Issue must contain exactly one of each:

```text
<!-- noodles-role: repository-mutating-atom -->
<!-- noodles-target: owner/repo -->
<!-- noodles-subject: owner/repo#123 -->
<!-- noodles-state: ready|in_progress|awaiting_land|landed|blocked -->
```

Every repository mutation runs `./noodles acceptance verify`, which binds the exact candidate head/tree to `tests/run.sh`, `./noodles verify`, and zero residue. Add one optional `<!-- noodles-feature: feature-id -->` only when the Issue needs a specialized physical oracle; run `./noodles acceptance verify --feature <feature-id>`. The specialized oracle is additive and cannot replace or weaken the baseline. Unknown feature ids fail at completion with a diagnostic instead of making the Issue disappear from scheduling.

One Issue equals one repository-mutating atom. A PR contains exactly one line:

```text
Refs owner/repo#123
```

Do not use `Closes`, `Fixes`, or `Resolves`. Only the provider lander closes the Issue after merge readback.

## Call order

```bash
./noodles verify
./noodles providers sync
./noodles github protect audit
./noodles start
```

`./noodles start` fails closed unless local fitness, pinned providers, and GitHub protection readback all pass.

## Entropy and quality budget

`policy/fitness.json` is the executable budget. `./noodles metrics --json` reports, but does not itself prove, tracked surfaces, line-distribution entropy, markdown share, test/code ratio, provider count, workflows, and claim counts.

Adding a layer requires a physical failure that cannot be closed by strengthening the nearest existing contract/test. Delete a component when the same real task still passes without it.

## Completion claim

A task is complete only when:

```text
exact Issue
→ isolated Noodle worktree
→ exact candidate head
→ L gates + controls + readback + zero residue
→ trusted GitHub verify receipt
→ exact-head merge
→ merge-parent and default-branch readback
→ exact Issue closure readback
→ local Noodle reconciliation
```

Anything earlier is progress, not completion.

---
name: execute
description: Implement one exact GitHub Issue atom, produce physical evidence, and hand off one PR to the provider lander.
schedule: "When one exact admitted GitHub Issue atom is ready for implementation"
---

# Execute

This skill operates inside the Noodle-created isolated worktree.

## Required sequence

1. Parse the order ID as `owner/repo#N`.
2. Run `./noodles issue validate owner/repo#N` and read the exact Issue.
3. Confirm the target repository equals the current worktree repository.
4. Read `AGENTS.md`, then only the nearest contract/test named by the Issue.
5. Route the work through the most relevant external pstack/engineering skill. External skill output is P-class guidance only.
6. Inspect current source and reproduce the exact behavior before editing.
7. Implement the smallest independently useful atom.
8. Add or strengthen immutable positive and planted-negative controls at the nearest boundary.
9. Run the exact task acceptance plus `tests/run.sh` and `./noodles verify`.
10. Inspect direct source/runtime/provider readback and confirm zero residue.
11. Commit and push the current worktree branch. Never push `main`.
12. Open exactly one non-draft PR to `main` with exactly one line `Refs owner/repo#N`.
13. Run `./noodles feature verify <feature-id>` for the exact Issue's `noodles-feature` id at the pushed head.
14. Run `./noodles issue handoff owner/repo#N --pr N`. This validates the exact PR head/body, sets the Issue to `awaiting_land`, and emits one blocking `stage_message` for the current `NOODLE_SESSION_ID`.
15. Stop immediately after the handoff succeeds. GitHub verify/land and local machine reconciliation own completion.

## Routing contract

Every execute task enters `poteto-mode` before any matched playbook or leaf skill.
Do not bypass `poteto-mode` by entering a leaf skill directly.
Record the selected P-class route and required physical oracle in the evidence packet.

Immutable route fixtures:

- `investigation` -> `poteto-mode/playbooks/investigation.md`; oracle `exact issue readback plus direct source/runtime/provider readback`
- `function-boundary feature work` -> `architect` plus `poteto-mode/playbooks/feature.md`; oracle `tests plus direct source/runtime readback`
- `long multi-phase work` -> `show-me-your-work` plus `poteto-mode/playbooks/multi-phase-plan.md`; oracle `decision trail plus direct readback`
- `verification skill work` -> `create-verification-skill` or `maintain-verification-skill`; oracle `declared feature operation plus deterministic observed-state check`
- `CLI control` -> mapped `control-cli`; oracle `same-surface reproduction plus direct readback`
- `pre-commit cleanup` -> mapped `deslop`; oracle `diff/status readback`

Unsupported routes fail closed: `control-ui`, Cursor `create-skill`, Cursor `/loop`, Graphite `gt`, cloud-agent infrastructure, standalone `goal`.
If a referenced playbook or mapped skill does not resolve from the pinned provider bytes, fail closed.

## Evidence packet

The PR body must contain only:

```text
Refs owner/repo#N
```

Report the claim, exact candidate head, positive control, planted-negative control, direct readback, residue result, and non-claims in the final task response. Do not include `Closes`, `Fixes`, or `Resolves` in the PR body.

## Runtime verification

`tests pass` is insufficient when the Issue names a real product/runtime behavior. Operate the actual feature, collect the named evidence, compare expected versus observed, and include only the receipt/digest needed for the contract. Do not commit generated receipts.

Output from `create-verification-skill` or `maintain-verification-skill` stays P-class until `./noodles feature verify <feature-id>` runs the declared operation and its oracle checks observed state. Run it at the exact candidate head after the final commit; `./noodles issue handoff` re-reads the exact Issue's `noodles-feature` id, resolves that contract, and rejects a missing, stale, wrong-head, self-reported, or artifact-blind evidence packet.

## Failure handling

Fail closed and return a blocking stage message when:

- exact Issue markers are missing or drifted;
- the candidate cannot reproduce the stated behavior;
- a required runtime/provider is unavailable;
- a negative control does not fail;
- source/provider readback differs from the tested subject;
- the worktree contains unrelated changes or residue;
- the task would require inventing a scheduler, worktree manager, generic registry, or unproven dependency.

A failure becomes a new rule/test candidate only after independent repeated evidence; do not edit `AGENTS.md` from one anecdote.

## Authority

Agent reasoning and external skills are P. Local executable gates are L. GitHub exact-head merge/event/closure readback is R. Descriptions and diagrams are N. Never claim R from P or L.

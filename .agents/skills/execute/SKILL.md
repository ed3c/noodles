---
name: execute
description: Implement one exact GitHub Issue atom, produce physical evidence, and hand off one PR to the provider lander.
schedule: "When one exact admitted GitHub Issue atom is ready for implementation"
---

# Execute

This skill operates inside the Noodle-created isolated worktree.

## Required sequence

0. Run `./noodles preflight` before any source edit. Stop if it names a missing capability.
1. Parse the order ID as `owner/repo#N`.
2. Run `./noodles issue validate owner/repo#N` and read the exact Issue.
3. Confirm the target repository equals the current worktree repository.
4. Read `AGENTS.md`, then only the nearest contract/test named by the Issue.
5. Route the work through the most relevant external pstack/engineering skill. External skill output is P-class guidance only.
6. Inspect current source and reproduce the exact behavior before editing.
7. Implement the smallest independently useful atom.
8. Add or strengthen immutable positive and planted-negative controls at the nearest boundary. Hold each planted defect as a patch file and drive the plant/confirm-red/revert/confirm-green ritual with `./noodles ceremony plant --patch <file>` and `./noodles ceremony unplant --patch <file>`; that is the admitted path here because the ritual runs while the working tree carries this atom's own uncommitted edits to the same files, and `git checkout -- <file>` discards the whole working-tree copy with no diff and no confirmation.
9. Run the exact task acceptance plus `tests/run.sh` and `./noodles verify`.
10. Inspect direct source/runtime/provider readback and confirm zero residue.
11. Commit and push the current worktree branch. Never push `main`.
12. Open exactly one non-draft PR to `main` with exactly one line `Refs owner/repo#N`.
13. Run `./noodles feature verify <feature-id>` for the exact Issue's `noodles-feature` id at the pushed head.
14. Run `./noodles issue handoff owner/repo#N --pr N`. This validates the exact PR head/body, admits worktree provenance, sets the Issue to `awaiting_land`, and emits one blocking `stage_message` for the current `NOODLE_SESSION_ID`. The worktree-provenance admission this step performs stays load-bearing (`policy/concurrency-proof.json` invariant I2) and is not skippable on the cook route. The one piece that is now this route's ceremony only, not a gate other routes can skip, is feature-journey compilation: the declared feature's journey map is compiled by `./noodles github verify-pr` for every candidate regardless of which writer set `awaiting_land`, so running it here again buys the cook route nothing extra.
15. Confirm the provider verification run for the exact pushed head started after the Issue reached `awaiting_land`; the run triggered by the push necessarily predates the handoff, so re-run that exact workflow run once and confirm it is queued or running.
16. Stop immediately after the handoff succeeds and the post-handoff verification is underway. GitHub verify/land and local machine reconciliation own completion.

## Cross-repository navigation

`./noodles ceremony checkout` is the admitted navigation surface for a cross-repository atom, and it is the only one: it materializes the target clone at its exact commit and builds the pinned exact-commit index in the same step, so no call site is left at which remembering to index is a discipline problem. Unguided text search over an unfamiliar tree is not a substitute — a schedule cycle receipt that claims work on a foreign repository and names no `code_intel_checkout` is refused by `./noodles verify`.

`./noodles ceremony lookup --checkout-receipt <path> --module <module> --name <name>` answers one exact-symbol question against that index and writes the receipt that a later "the code does X" has to cite. A missing pinned binary, a stale or commit-mismatched index, and a real miss are three different receipt states; none of them means the symbol is absent.

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

Unsupported routes fail closed: the immutable route fixtures above are the whole admitted set, so a task that matches none of them is an unknown route and stops here rather than proceeding best-effort.
If a referenced playbook or mapped skill does not resolve from the pinned provider bytes, fail closed.

Pinned route bundles, assembled at provider sync from the exact pinned bytes in traversal order:

- `investigation` -> `.noodle/bundles/investigation.md`
- `function-boundary feature work` -> `.noodle/bundles/function-boundary-feature-work.md`
- `long multi-phase work` -> `.noodle/bundles/long-multi-phase-work.md`
- `verification skill work` -> `.noodle/bundles/verification-skill-work.md`
- `CLI control` -> `.noodle/bundles/cli-control.md`
- `pre-commit cleanup` -> `.noodle/bundles/pre-commit-cleanup.md`

Read the pinned route bundle for the selected route before the live files. A bundle is a byte-preserving cache of the same pinned bytes in the same traversal order, never a substitute for the routing decision and never a summary. If a bundle is absent, stale, or fails its digest chain, load the pinned files live; every other pinned skill stays reachable only that way.

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

When the atom is committed but PR creation or handoff is blocked, push the branch first and name the exact missing capability in the blocking stage message: committed-but-unpushed work strands the atom locally and invites an unauthorized local merge of an unverified branch.

A failure becomes a new rule/test candidate only after independent repeated evidence; do not edit `AGENTS.md` from one anecdote.

## Authority

Agent reasoning and external skills are P. Local executable gates are L. GitHub exact-head merge/event/closure readback is R. Descriptions and diagrams are N. Never claim R from P or L.

# AGENTS.md

`noodles` is a clean control/evidence extension around upstream Noodle. It is not `skills-shared v2`, not another scheduler, and not another Agent OS.

## Golden Path

1. Read the exact GitHub Issue and validate its `noodles-*` markers.
2. Let Noodle own scheduling, process isolation, and worktrees.
3. Load external engineering knowledge through pinned provider paths.
4. Route the task with pstack; read only the nearest relevant contract and test.
5. Implement the smallest independently useful atom in the Noodle worktree.
6. Follow the canonical execute sequence in `.agents/skills/execute/SKILL.md`; this file never restates its step order. Several writers can set `awaiting_land` — `./noodles issue handoff` on the Noodle-cook route among them — and reaching it is an unauthenticated precondition, not landing authority: `train_select` reads it only to pick a candidate to *attempt*, and `./noodles github verify-pr` is what actually recompiles component surface and declared feature journeys from provider truth. No writer of the marker can turn eligibility into a receipt; that is the only path to one.
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

The skills-shared migration station is closed (`ed3c/noodles#293`): its probes, evidence documents, and capability ledger were deleted, and git history is the whole archive. `policy/fitness.json` forbids the `migrations` path name, so resurrecting the station reds `./noodles verify` rather than quietly re-entering the tree.

## Issue and PR contract

Every schedulable Issue must contain exactly one of each:

```text
<!-- noodles-role: repository-mutating-atom -->
<!-- noodles-target: owner/repo -->
<!-- noodles-subject: owner/repo#123 -->
<!-- noodles-state: ready|in_progress|awaiting_land|landed|blocked -->
<!-- noodles-component: name -->
<!-- noodles-depends-on: none|owner/repo#N[, owner/repo#N] -->
<!-- noodles-executor: gha-agentic|gha-runtime|local-noodle -->
<!-- noodles-runtime: bun-ts|gui-simulator|host-toolchain|none|persistent-daemon|private-network|python|shell|unbounded-duration|usb-device -->
<!-- noodles-write-boundary: path[, path]|none -->
<!-- noodles-evidence: drive-full-v1|github-only-v1 -->
```

`noodles-component` names one lowercase token from `policy/components.json`. `parse_issue_contract` accepts a missing value at scheduling time, but `component_surface_errors` at the land-time `github verify-pr` gate rejects a candidate whose Issue omits it or whose changed files fall outside that component's declared path globs.

Path globs bound which files a candidate may touch and say nothing about what those files start coupling to, so `component_import_edge_errors` judges the import edges the diff *introduces*: every changed `.py` file is parsed on both the trusted base tree and the candidate, and a newly added import that resolves to a repository module outside the declared component's globs fails closed naming the file, the import, and the component. An edge already present on the base tree is the base tree's declaration and is not re-judged; stdlib and absent names resolve to no repository module and are not edges. A component whose surface is the whole repository (`contract`) is bounded by neither check: `component_import_edge_errors` short-circuits on `"*" in globs`, same as `component_owner_errors` below, rather than relying on `fnmatch.fnmatchcase(x, "*")` matching everything by coincidence — and nothing restricts which Issue may declare `contract` in the first place, filed as `ed3c/noodles#278`. Its own disposition of the wave-8 finding is `issue_contract.py` on the `carrier` surface — `runtime_contract.py` really does read the subject grammar from `issue_contract.SUBJECT_RE`, so declaring the coupling is the honest cure and deleting it would only hide it. Ceiling: relative imports (`from . import x`) are not resolved, which this flat single-package layout never produces; a second, unrelated ceiling is runtime loading via `importlib` (`tests/support.py`'s `spec_from_file_location`, `tests/test_gh_pacing.py`'s `SourceFileLoader`) — both real instances load targets that already sit inside every component's globs, so neither has produced a false negative, but this AST walk cannot see either one and would not catch a future load that crossed a real boundary.

`ed3c/noodles#257` and `ed3c/noodles#268` land on the same trust boundary `ed3c/noodles#276` already names: `.github/workflows/verify.yml`'s `verify` job checks out `.trusted` from `${{ github.event.repository.default_branch }}` — the default branch, as it stood *before* the candidate merges — and it is that tree's `noodles.py`, not the candidate's own, that produces `receipt["gates"]` for `github verify-pr`. A gate therefore never protects the PR that introduces it: `git show 8cdf580:noodles.py | grep '"gates":'` (the base `#257` and `#268` were cut from) has no `component-import-edges`, `git show 0ec3cbf:noodles.py | grep '"gates":'` (`#257`'s own head) has it but no `component-ownership`, and only a PR opened after `#268` merges is verified by a trusted engine carrying both. This is not a defect to fix — trusting the candidate's own verifier to judge itself would let a candidate weaken the very check meant to catch it — but it means neither atom's own introducing PR is protected by the gate it ships; `tests/run.sh`'s planted-negative controls (`ComponentImportEdgeGateTests`, `ComponentOwnerGateTests`) are SANDBOX-tier evidence that the gate's logic works against fixtures, not PROD-tier evidence that it ran against that PR's real diff.

Non-claim, and the reason this gate proves less than it looks like it proves: only edges the diff *introduces* are judged, so the surfaces already on `main` are not certified honest by it. Measured with the gate's own resolver they carry `carrier` 40, `docs` 86, `schedule` 42, `verify` 33 standing cross-surface edges (`GrandfatheredImportDebtTests` recomputes this against the live tree instead of quoting a fixed sentence the tree drifts past — landing-train traffic on `main` moved these counts twice while this exact reconcile was in flight, and the test caught both times before merge). This sentence is the disclosure itself, not a copy of one: `disclosed_standing_edge_counts` parses these four numbers straight out of this line in the candidate's own `AGENTS.md` and compares them against the candidate's own tree, so a stale paragraph is a red, and updating this paragraph is how a candidate that legitimately moves an edge lands. `ed3c/noodles#306` is why it reads rather than restates: the expected counts used to be a literal inside the test module, which `pull_request_target` supplies from the default branch while the measurement comes from the candidate, so no candidate that moved an edge could make its own trusted verify pass, and none could merge to update the literal — the same deadlock `ed3c/noodles#285` cured for the sibling ratchet below. `ed3c/noodles#276` landed the measurement, not a refusal: `repository_metrics` publishes `cross_surface_import_edges` per component, read out of `./noodles verify --json`, and `policy/fitness.json` `max_cross_surface_import_edges` ratchets each one report-only so it can only shrink. Growth is still not itself refused: `component_import_edge_errors` owns refusing *undeclared* new edges on the diff, and a blanket growth ban would forbid every new `tests/test_*.py`, each of which adds one `docs` edge merely by importing the module it tests. Every production-to-production edge is dispositioned in the comment beside `cross_surface_import_edges`: most leave `noodles.py`, whose real boundary is per-definition in `policy/component-owners.json` rather than its file glob; `repair_contract.py -> runtime_contract.py` waits on `ed3c/noodles#272`; and `retrieval_contract.py -> evidence_ledger.py` should be declared away by listing `evidence_ledger.py` under `carrier` (and `trusted_preview.py` under `verify`, unowned the same way), which is a staged transition rather than this atom. "The component-surface gate is green" still means the coupling did not get worse, not that the declaration is true.

Both of those checks are file-level, and `noodles.py` is listed under `schedule`, `verify`, and `carrier` at once, so its glob matched every component before any atom existed. `policy/component-owners.json` gives such a file a hand-kept definition-level owner, and `component_owner_errors` refuses a candidate whose changed top-level definition is owned by a component the Issue does not declare, naming the file, the definition, and both components. Ownership is maintained, never derived: it is read from the trusted default-branch checkout, so a candidate cannot widen its own ownership, and a component whose surface is the whole repository (`contract`) is not bounded by it either. Its disposition of `ed3c/noodles#189` is `schedule_publish: ["schedule"]` — the dispatch really is schedule-domain logic, so a future atom wiring into it declares `schedule`.

Non-claim: a definition with no entry is unowned and this check stays silent on it, so the map's coverage is exactly its honesty. `tests/test_component_surface.py::ComponentOwnerMapTests` holds the entries that do exist to real components, real definitions, and files more than one component admits; it does not require the map to be complete. A file the candidate no longer carries at all is a file-level event judged by `policy/fitness.json` `required_paths`, not a definition-level crossing; deleting a definition inside a kept file is a crossing. `noodles.py` currently carries 162 top-level definitions and the map names 18 (11 `schedule`, 7 `verify`); the other 144 are unowned. `ed3c/noodles#278` made that a number rather than a silence: `repository_metrics` reports `unowned_top_level_definitions` and `policy/fitness.json` `max_unowned_top_level_definitions` ratchets it. The ratchet is deliberately report-only — a refusing threshold is read from the trusted default branch, so it would deadlock every candidate that legitimately adds a definition, the shape `ed3c/noodles#285` already hit. #278 also closed the same-shaped `contract` (`glob "*"`) declarability gap: `contract_component_bypass_errors` refuses a whole-repository declaration whose changed files a single ordinary component already admits, keyed on the glob rather than on the name, so an atom that really spans still passes while one that declared `contract` to skip all three gates does not.

Every repository mutation runs `./noodles acceptance verify`, which binds the exact candidate head/tree to `tests/run.sh`, `./noodles verify`, and zero residue. Add one optional `<!-- noodles-feature: feature-id -->` only when the Issue needs a specialized physical oracle; run `./noodles acceptance verify --feature <feature-id>`. The specialized oracle is additive and cannot replace or weaken the baseline. Unknown feature ids fail at completion with a diagnostic instead of making the Issue disappear from scheduling.

`noodles-depends-on` is parsed exactly: `none` or comma-separated same-repository subjects. A duplicate marker, duplicate entry, foreign repository, self-dependency, or dependency prose fails closed. A missing marker is undeclared, never "no dependencies": the Issue is reported non-schedulable with that exact reason instead of blocking an already-landed Issue's reconciliation.

Dependency waiting is never stored. `./noodles issue contract owner/repo#N` reads each declared predecessor's own provider state and derives schedulability from it, so a landed predecessor releases its dependents without anyone patching a mirrored marker. A failed predecessor read is never satisfied. `blocked` therefore means a real blocker and requires one `<!-- noodles-blocker: owner: reason -->` that is not dependency waiting.

A finding that is not an atom therefore has no Issue: intake normalizes every open Issue into one or blocks it. Its durable home is `docs/findings/register.json` — append one `{id, date, severity, finding, receipts[], owner_component, status}` entry, and `.noodle/adapters/github sync` lists every open entry alongside ready work until someone promotes it to a real Issue and records `promoted_to`. Appending is the only admitted mutation; `LEARNING.FINDINGS_REGISTER.001` owns the shape gate, the reader, and the non-claims. Do not answer a disclosed-not-fixed finding with prose on a record you are about to close.

Trusted code judges HOW a value is derived and disclosed; it never remembers WHAT the value currently is. A trusted test that pins a strict literal of candidate-mutable state is not merely stale when it drifts — `pull_request_target` runs `main`'s copy of every `tests/` module against the candidate, so the candidate computes a new value, is compared against a number only `main` holds, cannot edit trusted code from inside its own PR, and no rerun or rebase turns that green. `ed3c/noodles#285`, `#306`, `#304`/`#301` and `#311` each paid for that shape once. `ed3c/noodles#315` made it a class: `tests/test_trusted_literals.py` carries one detection rule that both the sweep and the guard use, `policy/trusted-literals.json` carries every live instance's committed disposition (`invariant` with a written reason, or `deferred` to a `docs/findings/register.json` id that owns the conversion) plus what this atom converted, and a NEW undispositioned literal reds. Both halves read the candidate — findings from its `tests/`, dispositions from its `policy/` — so the guard is not itself the deadlock it refuses: a candidate that legitimately adds an invariant-shaped literal adds its row in the same commit. Non-claim: the rule judges syntax, so it does not flag an empty-or-false literal (`assertEqual(errors, [])` is an absence check, not a memorized value), it cannot follow a value laundered through a module it does not parse, and a name the scope uses as a filesystem root is treated as a fixture tree rather than as candidate state — which is why every finding needs a human-written disposition instead of an automatic verdict.

"Keep one obvious owner/writer for each durable value" has a mechanical carrier for the classes that name themselves, not just the paragraph above. `policy/ownership-keys.json` is the finite ownership-key registry `AF-03`'s caveat asked for: each row names one durable-value class, the ONE path that owns it, a `select` locator into that owner document, a written reason, and the read-only projections admitted to carry a copy. `skill_contract.validate_ownership_registry` recomputes each class's current values from the candidate's own owner document and scans the candidate's tracked tree — an occurrence in an unregistered file is a refusal naming the class, the owner and the path; an admitted projection is derivation-checked against the owner's current values, so a projection the pin moved past reds naming itself rather than sitting in prose nobody re-reads. Everything is read from the candidate, never from the trusted policy root, for the reason `ed3c/noodles#315` named: a trusted-side copy of a value the candidate legally owns deadlocks every candidate that moves it. The task-model single-source rule that used to be this repository's one concrete instance of the law is retired into a registry row, so there is one implementation; its `policy/fitness.json` exemption key outlives it for one staging window only, because `pull_request_target` runs the default branch's copy of the retired function against the candidate's own policy document and deleting the key there raises `KeyError` inside the trusted verifier — filed as findings-register entry 10, step 3 of widen -> flip -> retire. Non-claims: scope is the enumerated classes and never arbitrary prose semantics; occurrence is substring containment, so a class whose values are short or word-like is not registrable, which is why disclosed counts and state-vocabulary sets are named absent rather than implied present; and the detector refuses, it never rewrites — atoms and humans cure.

Executor admission classifies the exact Issue before any claim, branch, checkout, or worktree exists.
`issue_contract.CAPABILITY_TABLE` is the single bounded table — data, not a policy DSL: each `runtime`
and `evidence` token names the exact lanes that can physically supply it, and the admitted lane set is
the intersection. GitHub-hosted lanes supply only portable, non-interactive, bounded-duration work with
no private device or network dependency; `usb-device`, `gui-simulator`, `private-network`,
`persistent-daemon`, `host-toolchain`, `unbounded-duration`, and `drive-full-v1` evidence are
`local-noodle` only, and `none` is contradictory on `gha-runtime`. A duplicate marker, a malformed
value, an unknown value, and a missing marker each produce their own diagnostic; nothing defaults to a
lane. A hosted lane gets only the ephemeral execute branch for that run and never a managed worktree;
the local lane additionally emits one idempotent provider-backed handoff task keyed by the source Issue
body digest and bound to target, required local capability, and write boundary, while Noodle remains the
sole owner of the persistent worktree lifecycle.

Every trusted verify run packages its own evidence before it emits a landing receipt.
`noodles.evidence_publication` reads the candidate as untrusted bytes — verification receipt,
runner/tool metadata, pinned dependency locks, pinned workflow definitions — scrubs a bounded set of
credential value shapes, and binds them to one canonical manifest under the deterministic custody key
`GitHub-Actions-Evidence/v1/<owner>/<repo>/issue-<N>/pr-<N>/<head>/run-<id>-attempt-<n>`, with
content-addressed blobs at `.../blobs/sha256/<digest>`. That folder is the idempotency key: a retry
recomputes the same path instead of growing a second tree. A wrong-head or wrong-attempt folder, a
missing or extra member, a short read, a tampered digest, an empty denominator, and a credential that
reached the archive each fail closed, and a scrub diagnostic carries the member and pattern id but
never the value. Durable Drive transport is not admitted — no Google credential path exists inside
Actions — so the publication reports `custody_unadmitted`: today only the manifest itself — folder,
digests, byte counts, blob paths, never raw content — reaches the GitHub artifact spool inside
`noodles-receipt.json`; the member bytes it describes are read, hashed, and discarded when the job
ends, so no `blobs/sha256/*` object exists anywhere yet. That spool is a bounded retry surface, not
the durable store. Custody is evidence: never correctness, never merge authority, and no admission
path reads it.

The hosted agentic lane's mutation boundary is judged as data at the trusted boundary, never by the
job that proposes it. One target-local execution task is identified by the sha256 of its exact typed
declaration — target, subject, provider body digest, base head, runtime, evidence policy, write
boundary — so the idempotency nonce is derived and never supplied: two dispatches carrying the exact
same declaration converge on the same task by construction. That convergence is proven only at the
function level today: `gha_execution_task`'s sole production caller (`gha_pull_request_admission`,
reached from the trusted checkout) always passes an empty `active_tasks`, so `task_reused`,
`gha_duplicate_claim`, and `gha_boundary_conflict` are reachable only from
`tests/test_gha_execution.py`, not from a real concurrent dispatch — filed at `ed3c/noodles#266`
alongside the seven declaration-mismatch statuses that are self-consistent for the same reason.
`schedule_publish` derives and stores the same identity in the schedule cycle receipt's
`binding["task"]` before it claims a branch, but nothing reads that value back — the verify-time gate
recomputes its own task fresh from provider truth (`pr.base.sha`, not the stored value), so a stale
schedule-time identity cannot admit a wrong candidate, but the receipt field itself rides through
`skill_contract.validate_cycle_receipt` unvalidated, same as #266's filing above. Issue prose is never
an input: an injected paragraph changes the body digest, which makes an in-flight dispatch stale, but
it can never widen the target, the lane, or the boundary. `gha_apply_admission` then judges one Agent
proposal — one branch, one PR body, one changed-path set — inside `verify_pull_request`, which runs
from the trusted checkout of the default branch. Trusted workflow bytes are refused first and
unconditionally, so a task whose declared boundary contains `.github` still cannot rewrite the gate
that judges it; a default-branch push, a foreign branch, a path outside the declared boundary, a
`Closes` or multi-line PR body, and a candidate carrying no bound evidence publication each fail
closed with their own diagnostic. Failure routing on a non-zero deterministic-runtime exit is not
implemented here: an earlier draft of this atom shipped a `gha_failure_disposition` router with zero
production callers (only `tests/test_gha_execution.py` called it), and it was removed rather than
landed as dead code. The runtime step's first real caller — `ed3c/noodles#267`'s live canary — owns
routing a real non-zero exit into the bounded repair lane when it exists.

Three halves of that lane are named absent, not implied present. The gh-aw workflow source, its
compiled lock workflow, and the pinned compiler/action commits are not here: `policy/fitness.json`
pins `max_workflows` to exactly 2 and `verify_repository` enforces equality, so a third workflow file
needs its own atom (`ed3c/noodles#265`). Cross-repository `repository_dispatch` stays held by
`policy/github.json`'s `cross_repository_status`, so the seven declaration comparisons in
`gha_execution_task` are self-consistent at the same-repository canary and refuse a real foreign
sender only after `ed3c/noodles#266`; the machine-readable origin digest in the PR body belongs to
that same atom, because the lander's exactly-one-`Refs`-line invariant has to be widened with it. And
no Issue declares `gha-agentic` yet, so this gate has executed zero times on the provider: its
evidence is L, never R, until `ed3c/noodles#267` runs one live canary.

One Issue equals one repository-mutating atom. A PR contains exactly one line:

```text
Refs owner/repo#123
```

Do not use `Closes`, `Fixes`, or `Resolves`. Only the provider lander closes the Issue after merge readback.

## Call order

`README.md` owns the bootstrap call order and `./noodles --help` owns the live verb list; this file restates neither. A second command sequence here would be a second writer that drifts silently — the copy that lived here had already lost `./noodles runtime check` and named `github protect audit` where the bootstrap needs `github protect apply`. `AUTONOMY.SUPERVISED_RUNNER.001` in `contracts/system-v1.md` owns the unattended-operation requirement.

## Ceremony entrypoints

Conventions every agent would otherwise have to remember at every call site are executables, not prose. Use `./noodles ceremony <verb>` and keep no duplicate rulebook: `commit`/`rebase` apply the repository commit identity inline, `run` selects a workflow run by name at the provider-read branch tip, `rerun` refuses a run whose head is not that tip (`--dry-run` proves the guard), `gh` routes through the paced carrier, `edit-body` performs a provider-read compare-and-swap with full SHA-256 digests, persists drifted live bytes, and verifies post-write readback, and `plant`/`unplant` apply and reverse a planted defect as the exact hunks of one patch file so the co-resident uncommitted work `git checkout -- <file>` would have discarded stays untouched. The invariants live in `AUTONOMY.CEREMONY_ENTRYPOINT.001`.

## Entropy and quality budget

`policy/fitness.json` is the executable budget. `./noodles metrics --json` reports, but does not itself prove, tracked surfaces, line-distribution entropy, markdown share, test/code ratio, provider count, workflows, and claim counts.

Adding a layer requires a physical failure that cannot be closed by strengthening the nearest existing contract/test. Delete a component when the same real task still passes without it.

That law has a mechanical carrier, not just this paragraph: a candidate adding a new pinned lock entry or a new top-level module fails trusted verify unless its Issue answers both gate questions under `## Component introduction` (`VERIFICATION.COMPONENT_INTRODUCTION.001`). Version bumps of existing pinned entries are out of scope.

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

## 工程法則的實證歸屬 (Rule → Evidence Routing)

全局 `~/.claude/CLAUDE.md` 的工程法則不直接指向迴圈目錄——法則層綁死在某個 repo 的
目錄結構上，迴圈改名即斷。**本節是那一跳的落點**：法則指到這裡，這裡指到擁有實證的 Harness。

| 法則主題 | 實證 Harness |
|---|---|
| 驗收參數飄移／宣稱前數解壓層數（表徵-性質邊界） | ed3c/noodles#191（收據自述語意）＋ ed3c/skill-concerns#13（monitor 同源三紀律） |

Anything earlier is progress, not completion.

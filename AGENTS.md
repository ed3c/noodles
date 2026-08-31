# AGENTS.md

`noodles` is a clean control/evidence extension around upstream Noodle. It is not `skills-shared v2`, another scheduler, or another Agent OS.

## Agent document route

Repository-owned context uses at most three nodes:

1. Read `AGENTS.md` for stable ownership, isolation, authority, and routing laws.
2. Read `contracts/system-v1.md` only when the exact Issue names a system-level requirement or decision.
3. Read the exact Issue and its nearest executable contract/test; then stop document traversal.

`./noodles verify` checks the declared route and pointers. That proves repository structure, not Agent cognition: choosing and applying the route remains P-class.

## Stable laws

- Noodle owns scheduling, orders, process isolation, and worktrees.
- pstack `poteto-mode` owns P-class engineering playbook selection; it never grants correctness or landing authority.
- noodles owns target-local deterministic admission, evidence binding, domain invariants, and policy hooks.
- Git owns candidate source identity; GitHub owns protected default-branch merge and Issue-closure reality.
- Repository mutation occurs only in a Noodle-owned isolated worktree. The shared control checkout is read/reconcile only.
- Human Verifier is not an operational state. Human involvement is reserved for goals, constraint changes, genuine product preference, root-authority transitions, or admitted escalation.
- **NO PROSE MIGRATION.** A capability or authority claim does not enter noodles merely because prose, a diagram, or another Agent repeats it; use the owning executable/provider admission seam.
- P/N never become L/R through repetition, review consensus, prose, or a moved heading.
- Every repository mutation runs `./noodles acceptance verify`. An optional `<!-- noodles-feature: feature-id -->` adds a specialized oracle; it never replaces mandatory baseline acceptance.
- Follow the Dune-derived Agent-friendly requirements `AF-01` through `AF-06` in `contracts/system-v1.md`: make the supported path locally obvious and shortcuts mechanically fail.
- Domain knowledge belongs at the nearest executable contract/test/oracle. A nearby file or Skill is not evidence until the declared operation executes and its exact state is read back.
- Do not create a custom scheduler, worktree manager, generic retry/review/release framework, mutable requirement-status store, or unproven registry.

## Authority classes

The exact authority vocabulary below is stable because repository verification treats these tokens as invariants:

- **P — probabilistic guidance:** model reasoning, rules, Skills, routing, and plans; proposes/navigates only.
- **L — local deterministic gate:** executable local gate with exact subject, controls, readback, and residue; may reject/admit locally.
- **R — provider-enforced readback:** GitHub/provider protected-state readback; may establish landed provider reality.
- **N — non-claim:** docs, diagrams, metrics, inventories, or unverified proposals; describes only.

## Canonical procedure owners

Do not duplicate mutable procedure steps here. Resolve them at the owning surface:

| Procedure | Canonical owner |
|---|---|
| Issue parsing, dependency/provider-body readback, schedulability | `./noodles issue contract`, `noodles.py`, nearest Issue-contract tests |
| Order construction and publication | `.agents/skills/schedule/SKILL.md` + `skill_contract.py publish` |
| Implementation, pstack routing, exact PR creation, feature verification, handoff | `.agents/skills/execute/SKILL.md` + `./noodles issue handoff` |
| Repository/runtime/provider/bootstrap/start commands | `README.md`, CLI `--help`, and lock files under `policy/` |
| Stable system rationale and requirements | `contracts/system-v1.md` |
| Migration disposition/evidence ceiling | `migrations/skills-shared/ledger.json` and exact migration Issues |
| Trusted verification/landing | `.github/workflows/verify.yml`, `.github/workflows/land.yml`, provider readback |

## 工程法則的實證歸屬 (Rule → Evidence Routing)

These rows are pointers, not copied procedures or proofs.

全局 `~/.claude/CLAUDE.md` 的工程法則不直接指向迴圈目錄——法則層綁死在某個 repo 的
目錄結構上，迴圈改名即斷。**本節是那一跳的落點**：法則指到這裡，這裡指到擁有實證的 Harness。

| 法則主題 / Rule theme | 實證 Harness / Owning evidence surface |
|---|---|
| 驗收參數飄移／宣稱前數解壓層數（表徵-性質邊界） | ed3c/noodles#191（收據自述語意）＋ ed3c/skill-concerns#13（monitor 同源三紀律） |
| Enforcement layering: repository shape → executable gate → diagnostic → soft guidance | `contracts/system-v1.md`, `./noodles verify`, nearest contract tests |
| Three-tier Agent read-surface discipline | `policy/fitness.json` document-route declaration + document-route tests |
| Isolation and one admitted writer per durable value | Noodle worktree/runtime readback + nearest ownership/containment tests |
| Baseline acceptance plus additive specialized oracle | feature/acceptance contracts and `./noodles acceptance verify` / `./noodles feature verify` |
| Exact-head provider landing | trusted GitHub workflows + merge/default-branch/Issue-closure readback |

## Completion language

An Agent may report **implementation complete, awaiting provider landing** after the canonical execute/handoff procedure succeeds. Do not report repository/task completion until the trusted provider has landed the exact head and the owning readback/reconciliation path confirms it.

# Drift and omission ledger

> N-class planning ledger for `CTX-117-2026-08-30-63e776e-provider-20260830T004730Z`. Severity is not an execution, provider, or completion verdict. `[SRC-ORDER-117, OWNER_REQUIREMENT, N]`

## Intervention levels

| Level | Meaning | Authority |
|---|---|---|
| `L0 OBSERVE` | Record a material fact or a bounded resolved transition. | `N` |
| `L1 WARN` | Work may continue within an explicit evidence ceiling. | `N` |
| `L2 REVIEW` | Reconcile the contradiction before depending on it. | `N` |
| `L3 BLOCK` | Continuing the named transition risks identity, authority, writer, or evidence corruption. | `N` |

The levels are the pinned read-only Shadow vocabulary. They grant no implementation or provider authority. `[SRC-SKILLS-SHARED:spatial-loop-systems-engineering/SKILL.md, METHOD_SOURCE, P]`

## Findings

### `DRIFT-001` Closed Issue #82 still carries marker `in_progress`

- Level: `L3 BLOCK` for dependent completion/admission.
- Source: exact #82 body and `./noodles issue contract` readbacks in `SRC-PROVIDER-READBACK`, `R_REFERENCE`, `N`.
- Observation: PR #121 merged and GitHub Issue #82 is closed, but its exact marker is `noodles-state: in_progress`.
- Consequence: #83, #98, and #120 cannot consume #82 as “closed and landed”; #98/#120 lifecycle `ready` is not schedulability.
- Safe action: repair the owning provider marker/state through an authorized exact provider path, then re-read each dependent.

### `DRIFT-002` Draft PR #125 already owns #117's provider relation

- Level: `L3 BLOCK` for opening a second #117 PR; `L2 REVIEW` for handoff until convergence.
- Source: PR #125 body/head/draft readback in `SRC-PR-CHECKS`, `R_REFERENCE`, `N`.
- Observation: draft PR #125 has body exactly `Refs ed3c/noodles#117` and head `1a0b81441a44d6179240dd7355f12a7fdfed2058`, but provider changed-file readback includes `.noodle.toml`, `contracts/system-v1.md`, and `tests/test_agent_friendly_architecture.py` in addition to the six declared Markdown files.
- Consequence: a sibling PR would create two provider candidates for one Issue, while handing off the present #125 head would violate the exact six-file physical boundary. The existing head is behind and its trusted verify summary is failing.
- Safe action: converge the current verified candidate onto the same PR by a non-destructive fast-forwardable history, read back exactly six provider changed files, then make that one PR non-draft.

### `DRIFT-003` #83 has not consumed landed #130

- Level: `L2 REVIEW` before #83's next trusted run.
- Source: #83 owner comments, PR #129, and PR #136/current-main readback in `SRC-PROVIDER-READBACK`, `SRC-PR-CHECKS`, and `SRC-GIT-HISTORY`.
- Observation: #130 landed the stable `Unsupported routes fail closed:` prefix at main `63e776e...`, but PR #129 remains at old head `8def7a8...` and trusted verify still fails.
- Consequence: #83 is not completion-ready, and #120 remains blocked.
- Safe action: repair the same #83 branch/worktree/PR; do not create a sibling lane or rewrite #130's trusted-owner boundary.

### `DRIFT-004` Every observed open PR has a failing trusted verify summary

- Level: `L2 REVIEW` for each named PR's completion.
- Source: exact check rollups for #122/#125/#129/#131 in `SRC-PR-CHECKS`, `R_REFERENCE`, `N`.
- Observation: candidate self-tests are green for #122/#125/#129, mixed for #131; the trusted `verify` summary is failing for all four observed heads.
- Consequence: an open head, green candidate job, or PR relation cannot be promoted to exact-head provider readiness.
- Safe action: diagnose and rerun each owning lane at a new exact head; do not borrow another PR's result.

### `DRIFT-005` The landed #124 pack contained pre-merge status prose

- Level: `L0 OBSERVE`; repaired in this refresh.
- Source: `SRC-PACK-124`, mixed `REPOSITORY_FACT` and historical projection, `N`.
- Observation: the landed files described #124/PR #128 as awaiting land even though PR #128 merged as `fdce9f8...` and Issue #124 closed/landed.
- Consequence: mutable provider status copied into N-class prose drifted immediately.
- Safe action: keep snapshot timestamps and force future readers to re-read provider state.

### `DRIFT-006` The provider denominator changed again

- Level: `L0 OBSERVE`.
- Source: `SRC-PROVIDER-READBACK`, `R_REFERENCE`, `N`.
- Observation: the current snapshot contains 27 open Issues and four open PRs. #130 is now closed/landed; PR #131 now exists.
- Consequence: equality with any older count or membership cannot be inferred.
- Safe action: rerun the exact provider queries before operational planning.

### `DRIFT-007` Raw owner conversation is not repository-addressable

- Level: `L1 WARN`.
- Source: `SRC-OWNER-CONVERSATION`, `OWNER_REQUIREMENT` plus `ABSENT`, `N`.
- Observation: #117 and earlier projections attribute requirements to 2026-08-28 through 2026-08-30, but raw message IDs and bytes are unavailable.
- Consequence: this pack preserves attributed requirements, not complete transcript proof.
- Safe action: keep coverage `PARTIAL`; add an authorized source lock only when exact transcript identity is available.

### `DRIFT-008` Dune, Lauren, article, and PDF source identities are incomplete

- Level: `L2 REVIEW` for any claim of full external-source coverage.
- Source: `SRC-DUNE-IMAGES`, `SRC-LAUREN-PSTACK`, and `SRC-ARTICLES-PDFS`; mixed `EXTERNAL_CLAIM` and `ABSENT`, `N`.
- Observation: raw Dune images, Lauren link set, other titles/URLs/bytes/hashes, and the primary PDF behind the procedural-shadow “PDF-derived” rubric are absent.
- Consequence: the pack cannot verify or completely map their claims.
- Safe action: retain exact `ABSENT` rows. A future source-refresh atom may add authorized public identities without treating them as truth.

### `DRIFT-009` Performance research is frozen at an older baseline

- Level: `L1 WARN`.
- Source: `SRC-RESEARCH-2026-08-29`, `HISTORICAL_PROJECTION`, `N`.
- Observation: the report uses baseline `2f6f60f...` and says later Issue ordering and measurements became stale.
- Consequence: session counts, time, tokens, and causal inferences are not current facts.
- Safe action: rerun the bounded benchmark before using its numbers for a new decision.

### `DRIFT-010` Exact skills-shared methods are task inputs but not enabled providers

- Level: `L1 WARN`.
- Source: #117/#9 method requirements in `SRC-ORDER-117` and `SRC-CONTEXT-SKILL-9`; disabled provider in `SRC-PROVIDER-LOCK`; bytes in `SRC-SKILLS-SHARED`.
- Observation: this atom read exact pinned Shadow/Tech Lead/procedural method bytes, while the Golden Path provider lock keeps `skills-shared-compat` disabled.
- Consequence: the methods can shape P-class compilation but cannot become a runtime dependency or correctness authority.
- Safe action: keep every use attributed and P-class. Do not copy the procedures into repository contracts.

### `DRIFT-011` Admitted Feature/Code maps target an older repository commit

- Level: `L2 REVIEW` for current Feature Map coverage.
- Source: `SRC-CONTROL-NOODLE`, `METHOD_SOURCE`, `P`; `SRC-BASELINE`, `REPOSITORY_FACT`, `N`.
- Observation: the maps freeze `c820cacf...`; current baseline is `63e776e...`.
- Consequence: map presence cannot prove current changed-code-to-journey coverage.
- Safe action: preserve the stale-subject gap; #66 or a future exact map atom must bind current source.

### `DRIFT-012` Most legacy open Issues fail the current typed contract

- Level: `L3 BLOCK` for scheduling those Issues.
- Source: the exact open-Issue loop through `./noodles issue contract` in `SRC-PROVIDER-READBACK`, `R_REFERENCE`, `N`.
- Observation: #4/#45 lack dependency markers; the blocked legacy set lacks required exact blocker markers; #85 declares foreign-repository dependencies.
- Consequence: old thematic DAGs are not executable scheduler graphs.
- Safe action: repair each Issue through an exact provider-body atom or authorized backlog path; never infer missing markers from prose.

### `DRIFT-013` Ready marker still does not mean schedulable

- Level: `L2 REVIEW`.
- Source: exact contracts for #4/#98/#117/#120 in `SRC-PROVIDER-READBACK`, `R_REFERENCE`, `N`.
- Observation: only #117 has no adapter reason. #4 lacks dependency declaration; #98 waits on closed/`in_progress` #82; #120 waits on #82 and open #83.
- Consequence: lifecycle status cannot substitute for provider-derived eligibility or completion readiness.
- Safe action: display lifecycle, adapter schedulability, start readiness, and completion readiness separately.

### `DRIFT-014` Earlier DAGs included thematic edges not present in exact markers

- Level: `L2 REVIEW` for scheduler/completion use.
- Source: `SRC-OLD-117`, `HISTORICAL_PROJECTION`, `N`; exact current markers in `SRC-PROVIDER-READBACK`, `R_REFERENCE`, `N`.
- Observation: verification, code-intelligence, autonomy, and some convergence relationships survive only in historical planning text.
- Consequence: they may explain intent but cannot order current execution.
- Safe action: keep dotted historical edges separate from the exact completion graph.

### `DRIFT-015` N-class files are forbidden evidence inputs

- Level: `L3 BLOCK` if an Issue/receipt cites this directory as proof.
- Source: `SRC-N-EVIDENCE-CONTROL`, `L_REFERENCE`, `N`; `AUTHORITY.NO_LAUNDERING.001` in `SRC-SYSTEM`.
- Observation: `noodles.py` rejects `docs/research/` and `docs/design/` in machine evidence fields; the focused test plants the negative.
- Consequence: passing document checks cannot make the pack L/R evidence.
- Safe action: replay the focused control and scan tracked evidence/receipt allowlists before delivery.

### `DRIFT-016` No deterministic checker proves context completeness

- Level: `L1 WARN`.
- Source: #117 acceptance in `SRC-ORDER-117`; producer proposal in `SRC-CONTEXT-SKILL-9`; existing boundary in `SRC-N-EVIDENCE-CONTROL`.
- Observation: current gates reject authority laundering and enforce repository/document shape. They do not prove every conversation/article/source statement appears.
- Consequence: completeness remains bounded source accounting and explicit absence, not universal proof.
- Safe action: create a checker only after a finite repeated omission failure and its own exact Issue.

### `DRIFT-017` The reusable context compiler is proposed, not admitted

- Level: `L1 WARN`.
- Source: current open `ed3c/skill-concerns#9` in `SRC-CONTEXT-SKILL-9`, `R_REFERENCE`, `N`.
- Observation: no associated admitted Skill tree, PR, source-lock receipt, hermetic result, or consumer receipt was observed.
- Consequence: #117 cannot load or claim that producer capability.
- Safe action: finish #117 as the consumer evidence candidate; let the producer repository run its own admission path.

### `DRIFT-018` The pstack multi-phase playbook is plan-only

- Level: `L0 OBSERVE`.
- Source: `SRC-PSTACK:playbooks/multi-phase-plan.md`, `METHOD_SOURCE`, `P`; exact execute obligation in `SRC-EXECUTE`.
- Observation: the playbook says to deliver a plan and stop, while this exact execute atom requires the six-file implementation.
- Consequence: its phase/evidence discipline is usable; its standalone stop rule cannot replace the exact Issue.
- Safe action: record the route and use its verification sequencing without creating a seventh plan file.

### `DRIFT-019` A context pack cannot prove Agent cognition

- Level: `L0 OBSERVE`.
- Source: exact non-claims in `SRC-ORDER-117`, `OWNER_REQUIREMENT`, `N`.
- Observation: files, source pointers, controls, and traces are observable; complete internal understanding is not.
- Consequence: the design goal is recoverability and visible omission, not a cognition claim.
- Safe action: retain this non-claim in every refresh.

## Mandatory review checklist

Each answer must name a source ID and classification. `[SRC-ORDER-117, OWNER_REQUIREMENT, N]`

- Does every source family remain present, historical, unknown, blocked, or absent?
- Does every nontrivial statement have an exact source pointer and classification?
- Are mutable provider facts timestamped and re-readable?
- Are lifecycle, adapter schedulability, `S`, and `C` separate?
- Does each problem name its denominator, residual, and owner?
- Does each active write boundary have one convergence owner?
- Does every molecular chain expose missing segments as `TRACEABILITY_GAP`?
- Does any N-class path appear in an evidence or receipt allowlist?
- Does a merged commit get misread as runtime proof or correct provider marker state?
- Does an external claim become acceptance without an exact source/evidence atom?
- Does a repair change Issue, session, worktree, branch, or PR identity?
- Does a candidate-modified oracle become the sole authority for its own candidate?

## Unmechanized planted negatives

These remain N/P review probes, not local deterministic gates. `[SRC-ORDER-117, OWNER_REQUIREMENT, N]`

1. Remove one denominator source; the omission must remain visible.
2. Replace one `C` edge with `S`; completion must remain open.
3. Assign two active writers to one durable value; one convergence owner must be selected.
4. Cite this pack as completion evidence; the existing N-evidence control must reject it.
5. Mark #82 “landed” from merge ancestry while its provider marker remains `in_progress`; the dependency gap must remain.
6. Delete the article/PDF `ABSENT` row; source accounting must become incomplete.
7. Treat an open PR with green candidate tests as provider-ready despite trusted verify failure; the transition must remain blocked.

## Candidate next packets

These are planning proposals only. They do not mutate or create Issues. `[SRC-SKILLS-SHARED:agentic-tech-lead-orchestration/SKILL.md, METHOD_SOURCE, P]`

| Packet | Start condition | Bounded goal | Forbidden promotion | Current disposition |
|---|---|---|---|---|
| #82 provider-state repair | Exact #82 body and provider closure available | Make the closed provider Issue expose the exact landed marker expected by its own contract | Do not infer from merge ancestry or edit dependent mirrors. | Ready for authorized provider repair; not owned by #117 |
| #117 one-PR convergence | Local candidate controls pass | Fast-forward the existing #125 lane to current main/candidate, prove provider changed-file readback is exactly the six declared files, make it non-draft, and hand off exact head | Do not open a sibling PR or force-push shared history. | Required by current atom |
| #83 same-lane repair | #130 landed and current main readable | Preserve #83 ownership changes while consuming stable trusted prefix | Do not create a sibling lane or weaken #130. | Open via PR #129 |
| Legacy contract normalization | Exact owner decision per Issue | Add valid dependency/blocker markers without changing claims | Do not reconstruct dependencies from this N pack. | Required before most legacy scheduling |
| External source refresh | Exact authorized URLs/files/hashes available | Bind article/PDF/image claims to primary identities | Do not publish private bytes or call sources true. | `HOLD` |
| Context compiler admission | #117 consumer evidence and producer source lock available | Run producer-side finite omission/edge/authority controls | Do not make it a scheduler, registry, or evidence database. | Open at `ed3c/skill-concerns#9` |

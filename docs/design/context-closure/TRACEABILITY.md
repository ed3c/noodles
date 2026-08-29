# Molecular Traceability Index

> N-class projection for snapshot `CTX-2026-08-30T02:44:51+08:00`. A row points to provider or executable evidence; it does not reproduce or replace that evidence.

## Trace shape

```text
owner source / problem
  → bounded requirement or hypothesis
  → exact Issue
  → branch / Noodle worktree / session when available
  → PR and exact candidate head
  → changed paths
  → positive / planted-negative / non-case controls
  → local or specialized oracle receipt
  → merge / default-branch / Issue-closure readback
```

Use `TRACEABILITY_GAP` for every unavailable segment. Never fill a gap from memory or a nearby Issue.

## Architecture-changing landed atoms

| Problem / requirement | Issue | PR / candidate / merge | Changed surface or owning boundary | Controls / oracle pointer | Closure readback | Gaps / ceiling |
|---|---|---|---|---|---|---|
| clean migration control plane | #1 | PR #2; head `18aaa10583e859ca4112046360ed5d180e0ba8b0`; merge `0fafd79186215e16e18b5d214d8556ee7abe8e0f`; tree `c33b52586f2d825a262afe24c696351a9dbfd674` | initial minimal control/evidence tree | 13 positive/adversarial tests; exact-tree verify twice | #1 body records main/tree/Issue closure | bootstrap exception only; no post-bootstrap autonomy claim |
| candidate/trusted job isolation | #16 | PR #17; head `af07c7aca3330ef15dc079e737d9572f108ac053`; merge `95b2bc3039f02a8b6d860c335ec16b41c6174981` | trusted workflow boundary and nearest tests | missing job dependency and candidate-script-in-trusted-job negatives | #16 landed marker/receipt | does not prove task behavior |
| GitHub protected exact-head landing | #3 | PR #29; head `078086b69e91ee1dcbea74815d5069e220ef2386`; merge `f1c09d00ef832673d7fb7aaf3ba096a692a58ef9` | protection policy / land token boundary | strict check, zero human approvals, admin enforcement, token failure controls | #3 landed provider body | full single-Issue canary remains #4 |
| pinned Noodle/provider runtime | #15 | PR #32; head `12c923f29b6fe00717ca94ed90bd47a788eea55b`; merge `04d1d5408e9dd509029431c3288b52c205c83e67` | runtime/provider locks, checks, discovery | wrong version/checksum/commit/path/license/dirty/missing controls | #15 landed provider body | session behavior is not implied |
| pstack `poteto-mode` route | #18 | PR #39; head `dae74d307a7664c2c0886892eb071d859b09e8cc`; merge `7a63f266d41301a8dd0d7b7c370d3e3c1110aebd` | provider mapping, execute route, compatibility fixtures | route fixtures, missing/dangling/unsupported/broad-root negatives | #18 landed provider body | routing remains P; no cloud/goal/loop claim |
| schedule task registration | #25 | PR #26; head `2c8aea981036676cb3a03450015a2e9e6ed519c3`; merge `5b8ca52692fa7853612437cb729c6bd0f662f5af` | schedule Skill/frontmatter and gate | positive task discovery; missing-frontmatter negative | #25 landed | no scheduler ownership transfer |
| Noodle worktree root | #27 | PR #28; head `f0b8fd12859f4820177ad49b85c969fc13cd4ca1`; merge `333aecf2c7e2b4d161731d140ba2eef77eef6f95` | `.gitignore` / worktree-root gate | check-ignore and missing-rule control | #27 landed | no candidate correctness claim |
| scheduler self-order churn | #30 | PR #31; head `e59315c067056f27e70a482ab316c4ff4b1ed6c9`; merge `e5a7296fa977cd6c0ff06edd7680fc8f9197782c` | schedule Skill / order publish contract | active-order preservation and self-schedule negative | #30 landed | does not prove all scheduler liveness |
| provider containment before local release | #33 | PR #34; head `3e1248a62ead5b53b23f33d0f2f55a16cd3a6c04`; merge `d042609707a1ebe8f84454319a4cb61fa602cb54` | execute handoff / blocking event / reconcile | missing/wrong/nonblocking message, wrong PR/session, pre-land reconcile | #33 landed | blocking event is coordination, not proof |
| execute task registration | #37 | PR #38; head `94f3faaf9b025435bfd91e45841f501c357cc000`; merge `56aec92df88e875e0f8b5c9504cf4564d2579aa9` | execute Skill task frontmatter and dispatch | unresolved/missing/ad-hoc/schedule-stage negatives | #37 landed | route success does not prove task correctness |
| dirty/provider-stale control checkout | #44 | PR #55; head `8094ad17df7fc814f999f5ccc4aea38819cf811d`; merge `d7dfc48ac8263483ea9f639f6940a6bd639441aa` | common start/reconcile checkout gate | tracked/untracked/wrong/behind/ahead/diverged controls | #44 landed | post-admission writes remain possible outside boundary |
| control-noodle provider replacement | #49 | PR #56; head `0af94799137a815551380f1303e5818c12881ca7`; merge `bd2783b8885a2e2ff934c99bf7f264e34b34c601` | provider lock/discovery path | exact tree/license/admission/Skill digests and Matt-residue negatives | #49 landed | no deterministic route-quality claim |
| exact failed-check repair lane | #50 | PR #51; head `e0361e9e00fe8a5bc901c66185c8fbf6582a53ef`; merge `c8d54a3eaaa6fceead97bd1231ec3e7ded544b99` | repair receipt and same-lane re-entry | wrong/stale/already-landed/missing-check/head controls; bounded attempts | #50 landed | arbitrary repairs not guaranteed |
| exact worktree repair command placement | #57 | PR #59; head `19ccdd1c8b9853e5c33d18f9b010a92fa95c80d2`; merge `a9ab424c414ce5702e3153e24e226c8010377b64` | repair worktree execution helper | exact top/head positive; missing/wrong worktree/project negatives | #57 landed | Noodle still owns worktree lifecycle |
| ff-only provider reconciliation | #60 | PR #68; head `1aacbf54908948b65b57d3480da9f28d3c53d7ce`; merge `915b4ea23e4a7cdea47d2caa7a5add58e077ddc6` | reconcile checkout admission | clean-behind passes; dirty/wrong/ahead/diverged fail | #60 landed | stale startup still forbidden |
| architecture warnings vs hard invariants | #61 / #101 | PR #67 merge `cbbd82beca1d62067df83b0b7d9e3973dbb69ff0`; PR #104 merge `1bccf30f13c5277b54a4483295a324db16e7e951` | fitness/reporting gates | planted report-only breaches stay green; provider/workflow/dependency/residue stay red | Issues landed | metrics do not prove architecture quality |
| semantic trusted workflow validation | #64 | PR #87; head `1c8d8139ecbb169b39dca9cec8cdc768ff90956b`; merge `69cfced02a6ecb2656ea6d67879d6343fff1f276` | bounded verify/land semantic validator | phrase-preserving wrong trigger/job/permission/comment/disabled controls | #64 landed | service availability/candidate behavior not proved |
| task-type Codex profiles | #70 | PR #96; head `4bd436b530dbdfd55558b79118bd99fdad6a50ac`; merge `96d0ced7f24ebb8628210d588e1759fe30ce1ebd` | carrier/task model policy | missing/alias/mismatched/unknown/placeholder controls and exact canaries | #70 landed | no model superiority or deterministic behavior claim |
| compact Agent-friendly shortest path | #72 | PR #73; head `c748cf26c6d10b5f39dee5d7a2dd9c8e1af7c73c`; merge `2f6f60fe8323189379605fa651ff1206eb217472` | `AGENTS.md` only | document route positive/missing-pointer/fourth-hop | #72 landed | full rationale and owner map remain #109 |
| eval child denied real GitHub mutation | #74 | PR #80; head `e579c9dcb25a4d0d111b78ffccb9a4cb20bb1c58`; merge `331d99c2028e5fd14f8491ebcc1d750f599f74de` | eval subprocess HOME/PATH/gh shim | mutation verbs/unexpected argv/real-gh/symlink/provider-contact negatives | #74 landed | production sessions unchanged |
| Codex user-config isolation | #81 | PR #88; head `81fc9605756f3f9d5e6e722c212263c7fe95d420`; merge `68e88a584c33e25ba66fd90cd93e2de61a4c2344` | carrier/config isolation | user-only skill injection and isolation removal controls; live canaries | #81 landed | does not reduce repository-owned context |
| N-class docs cannot be evidence | #94 | PR #102; head `233a401b19ca1e90dadac248bebf588b93587e7f`; merge `f4a31738a4576e5f32a5579ad23472140615aba8` | `docs/research/**`, `docs/design/**`, handoff evidence validation | N-path evidence negative and machine-artifact positive | #94 landed | prose content remains unverified |
| verification skill to physical oracle | #19 | PR #103; head `0ef86fa37f3acc08a1b7b2f126b3e35273bf73e4`; merge `8cc289dedabe881a22433653a7e002acdb530ebc` | `feature_contract.py`, handoff evidence, tests | missing/unknown/skipped/stale/self-report/artifact-blind controls | #19 landed | architecture later refined by #112 |
| executable metrics feature canary | #20 | PR #110; head `eea62a910c47106df0fad20c2668ab52fdcba4c5`; merge `245517bc49a16c9fedb69ca2fd25bd3239bb1b15` | metrics CLI feature contract | malformed/wrong metric/skipped/unmapped/stale controls | #20 landed | only one CLI feature admitted |
| baseline acceptance decoupled from optional feature | #112 | PR #115; head `1b3f41cb268f16f28fcc9d301937d7854fa35484`; merge `281044f5572f9dd261f17fc6d0963b5162471788`; tree `afc1ec4ab5077b16b6e03b1091a539737a6b9970` | parser, baseline evidence, optional feature, docs/policy/tests | marker-free visibility, mandatory baseline, additive feature, unknown/stale/wrong-tree/self-report/fourth-hop negatives | protected main and post-land acceptance readback recorded in #112 | root transition used explicit owner authority; no permanent bypass remains |

## Current in-flight atoms

| Problem / requirement | Issue | Branch / PR / head | Current changed paths | Current controls | Provider state | Traceability gaps |
|---|---|---|---|---|---|---|
| full Dune-derived Agent-friendly system law | #109 | branch `agent/issue-109-agent-friendly-architecture-rebased`; PR #118; head `9e6ff70ea2ec516d0535a5275b4117f17f44f72b` | `AGENTS.md`, `contracts/system-v1.md`, `tests/test_agent_friendly_architecture.py` | candidate self-tests and trusted positive/planted-negative controls passed in run `33268884263`; first receipt failed only on pre-handoff Issue state | Issue now `awaiting_land`; PR reopened for exact-head rerun | merge/default-head/Issue closure not yet available; no Noodle worktree/session identity was available to this remote execution |
| N-class program context pack | #117 | branch `agent/issue-117-context-closure`; no PR at initial freeze | exactly six planned files under `docs/design/context-closure/` | existing repository N-evidence and document controls will be reused; this atom adds no new L gate | Issue body originally stale-blocked on landed #112; branch implementation started | `TRACEABILITY_GAP`: no Noodle order/worktree/session, PR/head, hosted acceptance, merge, or closure receipt yet |
| reusable context-closure Skill | skill-concerns #9 | no producer PR observed in this snapshot | proposed skill-concerns intake/admission surfaces | proposal names source lock, Shadow/Tech Lead methods, and consumer canary | open | `TRACEABILITY_GAP`: no source lock, scripts/tests/evals, admission receipt, Skill-tree digest, or #117 consumer receipt |

## Open leaf index

Every open noodles Issue at the snapshot appears once below. “Primary stream” is a planning owner, not provider metadata.

| Issue | Marker state | Primary stream | Immediate completion predecessor(s) | Current trace status |
|---|---|---|---|---|
| #4 | ready | autonomy | landed #3/#15/#18/#19/#20 | no end-to-end PR/receipt yet |
| #5 | blocked | code intelligence | #4 | no implementation trace |
| #6 | blocked | code intelligence | #4 | no implementation trace |
| #7 | blocked | code intelligence | #4 | no implementation trace |
| #8 | blocked | code intelligence | #4 | no implementation trace |
| #9 | blocked | code-intel convergence | #5/#6/#7 | no implementation trace |
| #10 | blocked | code intelligence | #4 | no implementation trace |
| #11 | blocked | code-intel experiment | #9 plus measured bottleneck | no implementation trace |
| #12 | blocked | code intelligence | #8 | no implementation trace |
| #13 | blocked | code-intel convergence | #5/#6/#7/#9; optional #8/#10/#11/#12 | no implementation trace |
| #14 | blocked | cross repository | #3/#4 | no target-local canary trace |
| #21 | blocked | learning | #4 | no reproduced lesson/eval trace |
| #22 | blocked | bounded autopilot | #4/#21/#46 | no three-Issue program trace |
| #45 | ready | daemon/concurrency I1 | #44 landed | no live lease PR/receipt |
| #46 | blocked | provenance/concurrency I2 | #45 | no two-worktree provenance receipt |
| #65 | blocked | upstream order-promotion seam | stated #61 landed | blocker requires re-evaluation |
| #66 | blocked | changed-code/feature/oracle compiler | #20/#46 | #20 leaf exists; compiler absent |
| #78 | blocked | session identity | #46 | raw-only historical observation; no supported seam receipt |
| #82 | ready | typed Issue/provider dependencies | #81 landed | no implementation PR observed |
| #83 | blocked | canonical Agent document owners | #82; practical rebase after #109 | no implementation PR observed |
| #84 | blocked | structural Agent behavior controls | #83 | no implementation PR observed |
| #85 | blocked | upstream runtime | poteto/noodle #7/#8 in immutable release | external source/release absent |
| #98 | blocked | concurrency I3 | #82 | no typed write-boundary implementation |
| #99 | blocked | concurrency I4 | #46 | no open-PR admission implementation |
| #100 | blocked | concurrency convergence | #45/#46/#98/#99 | no proof lock |
| #109 | awaiting_land | system/Agent-friendly spec | #112 landed | PR #118 head traced; R receipt pending |
| #116 | ready | optional infra oracle review | none | design may be superseded by #112 rationale; no PR observed |
| #117 | stale blocked at initial freeze; implementation started | context closure | S: #112 landed; C: #109 final state | branch traced; no PR/landing yet |

Count: `28`, matching the provider open-Issue denominator.

## Open PR index

| PR | Issue reference | Base | Head | Check/landing state at snapshot |
|---|---|---|---|---|
| #118 | `Refs ed3c/noodles#109` | `main@281044f5572f9dd261f17fc6d0963b5162471788` | `9e6ff70ea2ec516d0535a5275b4117f17f44f72b` | first verify run completed failure only because Issue was not yet `awaiting_land`; Issue corrected and PR reopened; new exact-head result pending |

## Known unavailable identity segments

The following are deliberately not inferred:

- local host worktree/session/process state for the current #109/#117 lanes;
- the local `/Users/neon/skills-shared` checkout/head/status;
- raw owner-conversation message IDs or a durable repository URI;
- raw Dune screenshot bytes inside this repository;
- complete article/PDF bytes and independent verification;
- future merge/default-branch/closure receipts for #109/#117;
- producer implementation/receipt for skill-concerns #9.

Each remains `TRACEABILITY_GAP`, `ABSENT`, or pending rather than being collapsed into a success claim.

# Closure matrix projection

> **N-class only.** A row records what must be checked. It does not close the source problem. `Issue closed` is evidence input, not sufficient closure by itself.

## Closure states

```text
CLOSED
  exact objective, denominator, controls, provider readback, and residuals are closed

PARTIAL
  a bounded subclaim is provider-landed but the source objective has open residuals

OPEN
  an owner exists and completion evidence is absent

HOLD
  admission prerequisites or supported authority are absent

UNOWNED
  no exact Issue or executable owner exists

DRIFT
  recorded state conflicts with provider/current-source reality
```

## Core objective matrix

| Source problem or owner intent | Stable requirement / bounded hypothesis | Owning Issues or surfaces | Historical evidence | Residual / non-claim | Projected closure |
|---|---|---|---|---|---|
| Build `noodles` as clean migration rather than `skills-shared v2` | Noodle owns orchestration; noodles owns only target-local correctness/evidence extensions | bootstrap #1, runtime #15, pstack #18, system contract | minimal control plane, exact runtime/provider admission, pstack routing were provider-landed historically | later feature/concurrency/context work must not regrow generic registries or schedulers | `PARTIAL`: architectural boundary exists; ongoing additions require review |
| Remove Human Verifier as routine bottleneck | Human is goal setter, constraint owner, or admitted escalation; L/R gates own routine completion | trusted workflow, #3, #16, #33, #4 | branch protection, verifier isolation, provider-before-release containment have landed evidence | one complete Issue-to-reconcile canary is still the decisive objective | `OPEN` via #4 |
| Make pstack a replaceable higher-order engineering control plane | nontrivial execute enters pinned `poteto-mode`; output stays P | #15, #18, provider lock and discovery | pinned provider bytes/discovery and route compatibility were landed | routing quality and Agent obedience remain probabilistic; unsupported routes stay unsupported | `PARTIAL/CLOSED for bounded route admission`; not correctness |
| Turn verification Skills into physical evidence | selected procedure must operate a real artifact and bind a deterministic oracle to exact head | #19 | requirement and Issue exist | feature contract, operation, envelope, stale-head controls not yet provider-landed | `OPEN` |
| Create executable Feature Map rather than prose | feature -> code surface -> transition/journey -> oracle -> evidence | #20, #66 | design and Issue contracts exist | first CLI canary and changed-code denominator remain open | `OPEN` |
| Ensure tests passing is not overclaimed as verification | completion claim selects exact required oracle; test-only non-case is explicit | #19, #20, #66, system contract | claim boundary documented | executable universal handoff gate remains open | `OPEN` |
| Make failures repairable without routine human work | failed exact head re-enters same Issue/PR/session/worktree lane with bounded retry | #50, #54, #57 and repair surfaces | exact-lane repair and startup/runtime defects have landed subclaims | does not prove every failure repairable; terminal taxonomy and program-level repair rate remain open | `PARTIAL` |
| Convert repeated Agent failure into executable organizational knowledge | reflect hypothesis -> reproductions -> non-case -> eval -> nearest rule -> regression | #21 | Issue exists | no complete promotion canary yet | `OPEN` |
| Prove bounded Full Autopilot rather than claim unbounded autonomy | three exact Issues, dependencies, disjoint writes, bounded failure/repair, L/R completion | #4, #21, #22 and concurrency lane | substrate pieces exist | single-Issue, learning, and concurrency prerequisites remain open | `HOLD/OPEN` |
| Make concurrency correctness independent of numeric N | I1 lease + I2 provenance + I3 disjoint writes + I4 open-PR exclusion | #45, #46, #82, #98, #99, #100 | control-checkout and worktree substrate exists | four invariant receipts and proof lock remain incomplete | `OPEN` |
| Consume Issues from other repositories without central authority laundering | authority follows mutated target; target-local Noodle/oracle/GitHub gate | cross-repo Issue #14 and system contract | boundary documented | no target-local cross-repo canary | `HOLD` |
| Keep complexity at an iteration sweet spot | security/business invariants gate; architecture metrics report; subtract before add | #61, #101, policy/metrics | report-only demotion historically landed | warnings still require periodic design review; no numeric metric proves architecture quality | `PARTIAL/CLOSED for gate classification` |
| Keep Agent context complete without increasing mandatory document hops | complete source denominator -> N projection -> Tech Lead task packet; execution route remains 3 nodes | #72, #83, #109, #117, skill-concerns#9 | three-hop route and N-doc authority restrictions historically landed | canonical ownership convergence, context pack, and producer consumer canary remain open | `OPEN` |
| Make correct path locally obvious | AF-01..AF-06 live in stable spec; shortcuts impossible or diagnostic | #109 and subsequent enforcement atoms | Issue defined and implementation lane started | docs alone do not prove behavior; enforcement coverage must be derived from existing/new gates | `OPEN/PARTIAL` |
| Prevent incomplete template Issues from scheduling | typed requirement/deps/write-boundary/body digest plus structural completeness | #82 and future ISSUE-CONTRACT atom; invalid example #69 | current parser has some exact markers | requirement pointer, completeness compiler, audit and rejection receipt remain open | `OPEN` |
| Reconstruct landed facts without a second registry | spec + Issues + PRs + receipts -> derived requirement status | future projection atom after typed requirements | provider data exists | requirement IDs not consistently attached; no status command should precede source completeness | `HOLD` |

## Source-specific closure questions

Every source claim must answer all of these before `CLOSED`:

1. What exact source problem was asserted?
2. What denominator of cases or journeys defines completion?
3. Which stable requirement or bounded hypothesis owns it?
4. Which Issue owns implementation?
5. Which exact candidate head was exercised?
6. Which positive, planted-negative, and non-case controls ran?
7. Which direct source/runtime/provider observation was read back?
8. Which residue was checked?
9. Which provider event made the fact repository reality?
10. Which residual non-claims remain?

## Closure anti-patterns

The following never close a row:

- an Issue is closed but its source denominator was not executed;
- several Agents agree;
- a Skill or component exists;
- local tests pass without the named product/runtime/provider oracle;
- implementation PR is open or green but not exact-head landed;
- one adapter passes while a claimed causal chain is untested;
- architecture prose describes the intended invariant;
- a stale projection says the dependency is complete;
- a Human manually checked the result without an executable/provider receipt.

## Next convergence packets

### Packet A: context pack consumer

```text
owner: noodles#117
write boundary: docs/design/context-closure/**
completion: six N files + frozen denominator + traceability/drift gaps + exact docs-only diff
non-claim: no execution authority
```

### Packet B: reusable producer

```text
owner: skill-concerns#9
inputs: frozen source identities and concern-owner pointers
outputs: bounded N projection and task packets
completion: hermetic negatives + noodles consumer receipt
non-claim: no Tech Lead/Shadow/runtime ownership
```

### Packet C: canonical specification and Issue admission

```text
owners: #109, #83, SPEC-CONVERGE, ISSUE-CONTRACT
completion: stable requirements, one owner per durable rule, typed Issue references, incomplete-ready rejection
non-claim: natural-language design quality remains P-class review
```

### Packet D: physical verification path

```text
owners: #19 -> #20 -> #66 -> #4
completion: real artifact operation, feature impact denominator, exact-head evidence envelope, provider-complete canary
non-claim: one canary is not universal coverage
```

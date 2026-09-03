# Codex/Claude differential canary: one issue class, two providers, six axes

> **N-class.** This is a measurement report, not evidence. It grants no L or R authority, closes no
> acceptance clause, and is never completion evidence for any atom including its own. Every number
> below is one sample from one issue class on one host on one day; the raw receipts it points at are
> the artefacts, this file is their index. `[ed3c/noodles#406, MEASUREMENT, N]`

Trigger: `ed3c/noodles#406`. Subject class: `ed3c/noodles#274` (documentation-plus-trusted-test atom,
declared write-boundary `contracts/system-v1.md, tests/test_noodles.py`).

## 1. What was held constant, and what was not

| Held constant | Value |
| --- | --- |
| Repository snapshot | `7717443` (`origin/main` at run start). Both lanes were later rebased together, twice, as the default branch advanced — always in lockstep, never one lane ahead of the other. Final base for both: `bc92cb2`. |
| Worktrees | two independent worktrees off that one commit; `canary/274-claude`, `canary/274-codex` |
| Task input | `ed3c/noodles#274` body, provider raw bytes, sha256 `82257e8187b9ba98655e2f625b6632f909a7e0ab90ccd8d96b14d5a95e50d4c9` (wire side: `issue.body` UTF-8 bytes from `GET /repos/ed3c/noodles/issues/274`) |
| Rules given | the same hard-rule block, scoped per worktree (`receipts/codex-instructions.md` is the Codex lane's copy; the Claude lane received the wave's own copy of the same rules) |
| Test oracle | `bash tests/run.sh`, `./noodles verify`, `./noodles verify --trusted-preview`, planted negative red-then-green, three-dot write-boundary subset — unchanged, run by the same driver in both lanes |
| Suite mutex | one exclusive lock; suites queued, never overlapped |

| Not held constant — named, not hidden | Effect |
| --- | --- |
| Reconnaissance order | The Claude lane operator had already read `contracts/system-v1.md`, the `RepositoryGateTests` region of `tests/test_noodles.py`, `tests/run.sh`, `tests/test_trusted_literals.py` and `policy/fitness.json` before either lane started, because the same operator had to read them to drive the canary at all. The Codex lane paid for that reading inside its own clock. **The wall-clock axis is therefore not a clean comparison and is reported with this subsidy attached.** |
| Design exposure | The Codex lane finished first, and its diff was read before the Claude lane's implementation was typed. The Claude lane's design (paragraph-scoped `assertIn`, no strict-equal because `policy/` is outside the boundary) was fixed before that exposure; the keystrokes were not. **Convergence between the two diffs is therefore not independent evidence.** |
| Monitor identity | Only one cross-provider monitor pairing was affordable (see §5). The correlated-miss axis carries `n=1` pairing. |

## 2. Lane configurations

| | lane-codex | lane-claude |
| --- | --- | --- |
| Implementer | `codex exec`, codex-cli `0.149.0` | Claude Code subagent, Opus 5 (1M context) |
| Model / effort | the model at `policy/fitness.json` → `required_codex_task_profiles.execute.model`, resolved at run time against base `bff2719`, with `model_reasoning_effort=high` — the profile that file declares for this task type (`ed3c/noodles#70`) | host default; no effort knob exposed to the session |
| Sandbox / approvals | `-s workspace-write`, `approval_policy=never`, `-C <worktree>`, `--add-dir <repo>/.git` | host sandbox; git identity inline per commit |
| Structured output | `--output-schema receipts/codex-output-schema.json`, `--output-last-message` | none available |
| Event stream | `--json` JSONL, 130 events captured | none available |
| Retries used | 0 of 1 allowed | 0 of 1 allowed |
| SUPERVISION_DIVERSITY | **provider-diverse** — implemented by Codex, monitored by Claude | **provider-diverse** — implemented by Claude, monitored by Codex (`codex exec -s read-only`); the same lane also received a config-diverse-only self-pass, recorded separately |

The Codex model is named by pointer rather than spelled, throughout this file including §8's ledger
row. That is not an omission: `policy/ownership-keys.json` registers `task-profile-model` as owned by
`policy/fitness.json`, and this report is not one of its admitted projections. A report that copied
the value would be a second writer of it — the exact drift that registry exists to refuse, arriving
in prose, which is where it usually arrives. The draft did copy it, and
`tests/test_agent_friendly_architecture.py` red on this file by name; the fix was to point rather
than to seek an exemption, because `policy/` is outside this atom's declared write-boundary and an
N-class report is the weakest possible reason to widen a policy.

## 3. Two-layer validation, asserted rather than assumed

`--output-schema` conformance is SHAPE correctness only. The Codex lane's final message validated
against the schema and asserted `status: "implemented"`, `positive_control: "OK"`,
`planted_negative: "FAILED (failures=1)"`. None of that was treated as evidence of anything. The
repository's own admission gates ran unchanged on top of the resulting tree, by a driver the model
did not control, and the schema-valid report was neither consulted nor trusted when they did.

The demonstration that the two layers are genuinely separate is §5: the schema-valid, self-declared
`implemented` result carried two defects that the unchanged gates also do not catch, and that only a
reading monitor found. A green filter and a schema-valid report agreeing with each other is not
independent confirmation — they are blind to the same things.

Failure-class vocabulary the driver was prepared to name on a retry (turn failure / context
exhaustion / tool failure / interrupted output / process termination / protocol drift /
schema-valid-but-semantically-refused): **not exercised — neither lane failed its first attempt.**
The vocabulary is recorded so the next run's first failure is classified rather than described.

## 4. Measurement discrimination, exercised before the live lanes

Per `ed3c/noodles#406`'s acceptance, the two computed axes were exercised against planted fixtures
with known values, in both directions, **before** either was applied to a lane.

`tests/test_differential_measurement.py` carries the computations and their controls:

| Control | Planted value | Asserted |
| --- | --- | --- |
| `confirmed_rate` ranks by rate, not raw count | noisy monitor 1 confirmed of 10; precise monitor 3 of 3 | raw count ranks noisy **above** precise; the rate ranks it **below** |
| `confirmed_rate` reaches both extremes | 2 of 2, and 0 of 2 | `1.0` and `0.0` — the metric is not a constant |
| `confirmed_rate` on an empty pass | `[]` | `(0, 0, 0.0)`, not a division error |
| `confirmed_rate` on an unverified finding | no `confirmed` key | counts against the monitor, does not read as a pass |
| `rework_distance` on an unchanged first result | `(0, 40)` | `0.0` |
| `rework_distance` on a two-thirds rewrite | `(30, 45)` | `2/3` |
| `rework_distance` discriminates | `(0, 45)` vs `(30, 45)` | the two are **not equal** |

Positive control: 8 tests, `OK` (`receipts/fixture-positive.log`).
Planted negatives, red-then-green by inverse edit (`receipts/fixture-negatives.log`):

| Planted defect | Verdict planted | Verdict after inverse edit |
| --- | --- | --- |
| `confirmed_rate` returns the raw count as its rate | `FAILED (failures=3)`, exit 1 | `OK`, exit 0 |
| `rework_distance` ratio collapses to constant `0.0` | `FAILED (failures=2)`, exit 1 | `OK`, exit 0 |

Ceiling, stated: `rework_distance` counts changed lines, not semantic edits. A one-character
correction and a one-line rewrite score the same.

## 5. The six axes, each with its denominator

### 5.1 Tokens

| | lane-codex | lane-claude |
| --- | --- | --- |
| Denominator | one `codex exec` invocation, one `turn.completed` event, implementation only | whole subagent session, not separable |
| input | 1,926,899 (1,805,184 cached) | — |
| output | 10,818 (4,172 reasoning) | — |
| Source | `turn.completed.usage` in `receipts/codex-events-attempt1.jsonl` | **UNMEASURED** |

The Claude lane has **no provider-usage record readable from inside the session**: no transcript
JSONL exists for the subagent under `~/.claude/projects/`, and the host exposes no per-turn usage
event. The only available number is the harness's remaining-budget counter, which covers the whole
lane including this report and is not a provider usage record; it is a proxy, and it is not
reported as a token count.

**This is the axis's real finding: the two surfaces are not symmetrically instrumented.** The Codex
lane's cost is a receipt; the Claude lane's cost is an inference. Any routing decision that claims a
token comparison between them is claiming a measurement one side cannot produce.

### 5.2 Wall-clock

| | lane-codex | lane-claude |
| --- | --- | --- |
| Denominator | process start to process exit of one `codex exec` | first prompt of the lane to first-result commit |
| First result | **317.7 s** | **114 s** |
| Subsidy | none — all reading inside the clock | ~9 minutes of prior repository reconnaissance, outside the clock, shared with this report |

**Comparable? No.** The raw ratio is 2.8× in the Claude lane's favour and the subsidy is roughly the
size of the gap. The honest statement this run supports is that the two lanes finished a small
documentation-plus-test atom in the same order of magnitude, and that a wall-clock claim about a lane
whose operator did the reading beforehand is a claim about when the stopwatch started.

### 5.3 Local-filter pass rate

Denominator: filter invocations per lane. Each invocation runs the four automated gates the table
columns name; the fifth gate — the atom's planted negative going red and its inverse edit returning
it to green — is a separate receipted script per lane, because it mutates the tree and must not run
inside a suite. Both lanes' fifth-gate receipts:
`receipts/claude-controls-round3.log`, `receipts/codex-controls-round3.log`, each showing
`POSITIVE_EXIT=0`, `NEGATIVE_EXIT=1`, `RESTORED_EXIT=0`, and `tests.test_trusted_literals` `OK`.

| Lane | Invocation | Base | `tests/run.sh` | `verify` | `verify --trusted-preview` | boundary ⊆ | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| lane-codex | 1 — first result, unrepaired | `7717443` | **0** — 1011 tests, `OK (skipped=1)`, 464 s | **0** | **1** | **0** | red on preview only |
| lane-codex | 2 — admitted | `a384130` | **0** — 1022 tests, `OK (skipped=1)`, 448 s | **0** | **1** | **0** | red on preview only |
| lane-claude | 1 — admitted | `a384130` | **0** — 1022 tests, `OK (skipped=1)`, 436 s | **0** | **1** | **0** | red on preview only |
| lane-codex | 3 — admitted, rebased onto `bc92cb2` | `bc92cb2` | **0** — 1024 tests, `OK (skipped=1)`, 457 s | **0** | **0** | **0** | **GREEN** |
| lane-claude | 2 — admitted, rebased onto `bc92cb2` | `bc92cb2` | **0** — 1024 tests, `OK (skipped=1)`, 452 s | **0** | **0** | **0** | **GREEN** |
| lane-report | 1 — admitted | `bc92cb2` | see `receipts/filter-lane-report-*.log` | | | | |

#### The preview reds are base drift, and the attribution is evidenced, not asserted

`./noodles verify --trusted-preview` fetches `origin/main` **itself, at the moment it runs**, and
runs the default branch's test modules over the candidate tree. Every preview this lane ran was
overtaken between its rebase and its verdict — including the one this report itself went through:

| Preview run | Base the candidate sat on | `origin/main` the preview fetched | Would-red tests |
| --- | --- | --- | --- |
| lane-codex #1 | `7717443` | `a384130` (`ed3c/noodles#412`) | 27 |
| lane-codex #2 | `a384130` | `bc92cb2` (`ed3c/noodles#320`) | 15 |
| this report, #1 | `bff2719` | `c76cdf5` | 7 — but see below: only **one** was drift-shaped, and it was this file's own defect |

The last row is the honest one, and it is the row that stops this section from being self-serving.
Six of its seven reds were neither drift nor this atom: they are `StartUnattendedTests` cases that
bind a loopback socket, and the driver's sandbox denied `bind(127.0.0.1:0)` with `EPERM`. That was
established by changing exactly one variable and re-running rather than by reasoning about it. The
seventh was real, was this file's, and is described in the note below. A preview red is therefore
three populations — base drift, host environment, and genuine defect — and a lane that reads the
count instead of the names will attribute all three to whichever it expected.

The attribution is checkable rather than argued, on two independent legs:

1. **Every named red belongs to a surface this atom does not touch.** Task-profile, schedule-contract,
   ownership-registry, gh-pacing, migration-station and metrics-threshold tests. The atom changes
   `contracts/system-v1.md` and one method in `tests/test_noodles.py`; none of the reds names either.
2. **The moving commits explain them directly.** `git diff a384130..bc92cb2 --name-only` is
   `AGENTS.md`, the retired migration station's tree (retired whole by `ed3c/noodles#293`; its path is
   deliberately not spelled here — see the note below), `policy/fitness.json`,
   `policy/components.json`, `policy/ownership-keys.json`, `tests/test_noodles.py`. `bc92cb2` retires
   that station and re-pins the fitness thresholds; a candidate that still
   carries it reds `test_resurrected_migration_station_is_rejected` and
   `test_the_retired_migration_station_leaves_no_tracked_reader` — which is exactly what the second
   preview named, and exactly what the trusted-transition paragraph this very atom documents predicts.

> **Why the path is not spelled.** `test_the_retired_migration_station_leaves_no_tracked_reader`
> sweeps *every tracked file* for the retired station's path, and the first draft of the paragraph
> above — the paragraph that explains that gate — red on it by name. Prose describing a retired
> identifier is a tracked reader of it, and the gate does not read intent. This is the same shape as
> §2's owned-value pointer, found by a different gate on the same file, and it is the third time in
> this lane that a report about other readers' blind spots was caught by a reader it had not itself
> modelled. The measurement in §5.6 says a green suite and a self-declared success are blind to the
> same things; the correction to that is not a better provider, it is one more independent reader —
> and here the extra reader was the repository, for free.

**This is the report's sharpest operational finding, and it is a finding about the wave, not about
either provider.** The trusted preview is a function of the default branch at the instant of the run,
and the run costs ~8 minutes plus mutex queue. In a wave landing a PR every ~20 minutes, a lane can
be overtaken between rebase and verdict, and the preview will say `trusted-transition deadlock: no
rerun and no rebase can turn it green` — which is true of the pinned-value case it was written for
and misleading here, where one more rebase is exactly the fix. A lane that reads that sentence
literally spends its bounded retries on a staged transition it does not need.

The costed consequence for this canary: **three of the run's five full-filter invocations were spent
re-establishing a base, not evaluating either provider's work.** Every red was on `--trusted-preview`
and every green was on `tests/run.sh` and `./noodles verify`, in every invocation, in both lanes.

### 5.4 Monitor findings, confirmed / total

Denominator: findings raised by that monitor on that diff. Confirmation = an independent reader
reproduced the named defect against repository evidence.

| Monitor | Diff read | Protocol | Findings | Confirmed | Rate |
| --- | --- | --- | --- | --- | --- |
| Codex (execute-profile model, `-s read-only`) | lane-claude `0f46426` | dedicated invocation, checklist of five defect classes, schema-bound output | 2 | 2 | **1.00** |
| Claude (Opus 5) | lane-codex `526642f` | inline reading during lane supervision, no checklist | 1 | 1 | **1.00** |

Findings, and what confirmed each:

| Id | Monitor | Diff | Finding | Confirmation | Disposition |
| --- | --- | --- | --- | --- | --- |
| F1 | Codex | lane-claude | The acceptance's planted negative ran as an out-of-band inverse edit, so nothing in the committed suite reds when the receipt is removed | **CONFIRMED.** The same test class already carries the durable shape for exactly this — `test_admission_termination_shape_rejects_mismatched_states` asserts its oracle reds on a mismatched input "rather than vacuous". The shape was available and unused. | FIXED in both lanes: containment moved into a helper, committed control reds in both directions |
| F2 | Codex | lane-claude | The paragraph is selected by candidate-current prose and by first hit, so a reworded rule deadlocks against `main`'s copy, and a preceding paragraph quoting the anchor selects the wrong block | **CONFIRMED.** The deadlock half is the exact class `contracts/system-v1.md` documents one paragraph above the assertion; the wrong-block half follows from `next()` returning the first match. | PARTIALLY FIXED: anchor narrowed to the rule's operative clause, ceiling recorded next to it rather than chased — the acceptance requires paragraph scoping, which requires *some* candidate-owned anchor |
| C1 | Claude | lane-codex | `next(generator)` with no default raises a bare `StopIteration` when the paragraph is absent | **CONFIRMED.** `ENFORCEMENT.LADDER_MIGRATION.001`, three paragraphs above the guarded text, requires the diagnostic to name the supported path rather than only the violation; `StopIteration` names nothing. | FIXED in lane-codex (absent in lane-claude, which already had a default) |

Both rates are `1.00`, on denominators of 2 and 1. **At these denominators the axis does not
discriminate between the providers, and reporting it as if it did would be the exact noise-reward
this metric exists to refuse.** The discriminating number is §5.6.

### 5.5 Rework distance

Denominator: `git diff --numstat` added+deleted lines, `base...admitted`.

| Lane | First result | Admitted | `first..admitted` | `base...admitted` | Ratio |
| --- | --- | --- | --- | --- | --- |
| lane-codex | `526642f` | `0c9433b` | 33 + 4 = **37** | 1 + 1 + 44 = **46** | **0.804** |
| lane-claude | `0f46426` | `1eae83c` | 26 + 1 = **27** | 1 + 1 + 41 = **43** | **0.628** |

Both lanes were reworked by the same two findings, so the gap between them is one defect wide: C1
existed only in the Codex lane, and repairing it is the 10 extra lines. Read the absolute numbers
before the ratio — both are high because the atom is small (a 46-line atom rewritten by 37 lines is
0.80; the same 37 lines against a 500-line atom would be 0.07), and a ratio near 1 on a tiny atom is
not the same warning as a ratio near 1 on a large one.

**What this axis actually caught:** first-pass wall-clock (§5.2) said the Claude lane was 2.8× faster.
Rework says both lanes then paid for the same two omissions, and the faster lane paid 27 lines of it.
Neither lane's first result was admissible as produced. A routing decision made on §5.2 alone would
have been made on a number that had not finished happening yet.

### 5.6 Correlated miss

Denominator: defect classes present in **both** diffs, so both monitors had the same opportunity.
There are two — F1 (no durable negative) and F2 (candidate-owned anchor). C1 existed in one diff
only and is excluded from this axis, because a monitor cannot miss what its diff does not contain.

| Monitor | Shared classes it had opportunity on | Caught | Missed | Correlated miss |
| --- | --- | --- | --- | --- |
| Codex, reading lane-claude | 2 | 2 | 0 | **0 / 2** |
| Claude, reading lane-codex | 2 | 0 | 2 | **2 / 2** |

Both monitor passes were cross-provider — each model read a diff the other model wrote — so this
table is not diverse-versus-not. It is Codex-as-monitor `2/2` against Claude-as-monitor `0/2` on the
same two defect classes, which if taken at face value points the opposite way from the direction the
hybrid topology assumed when it made Claude the quality mainline.

**And it is confounded, decisively enough that it must not be read as a provider result.** The two
monitor passes did not run the same protocol. The Codex monitor received a dedicated invocation with
an explicit checklist naming five defect classes — one of which is *"a trusted-suite assertion that
pins candidate-current state and would deadlock a future candidate"*, which is F2 almost verbatim.
The Claude monitor read the diff inline during lane supervision with no checklist. **The most
parsimonious explanation of this table is the checklist, not the provider.**

That is the useful result. The supervision-diversity premium this canary can actually evidence is a
*protocol* premium, and a checklist is far cheaper to deploy than a second provider. The provider
question is not answered here; a run that gives both monitors the identical checklist would answer
it, and is the obvious next atom.

Second-arrival note: the ceiling on comparing monitors that read different diffs is cited from this
run's own construction (shared classes only), not re-derived per finding.

## 6. Diff provenance — no cross-merge

The two lanes were separate `git worktree` checkouts of one clone, created from the same commit and
never merged into one another. The assertion is mechanical: neither lane's history contains the
other's commits, and each lane's three-dot diff against the default branch names only its own files.

| Branch | Base | Commits | Author of each | Contains the other lane's commits? | Three-dot files |
| --- | --- | --- | --- | --- | --- |
| `canary/274-codex` | `a384130` | `526642f` implement, `0c9433b` monitor repair | `526642f` written by `codex exec`; `0c9433b` written by the Claude monitor | **no** | `contracts/system-v1.md`, `tests/test_noodles.py` |
| `canary/274-claude` | `a384130` | `0f46426` implement, `1eae83c` monitor repair | both written by the Claude lane operator | **no** | `contracts/system-v1.md`, `tests/test_noodles.py` |
| `canary/406-report` | `a384130` | this report plus its measurement controls | Claude | **no** | `docs/codex-claude-differential-canary.md`, `tests/test_differential_measurement.py` |

Both lanes converged on materially the same implementation: the receipt appended to the
staged-transition paragraph, and a paragraph-scoped `assertIn` control in `RepositoryGateTests`,
`assertIn` in both cases because a strict-equal would demand a `policy/trusted-literals.json` row
that neither atom's write-boundary could supply. **That convergence is not independent evidence** —
see §1: the Codex lane finished first and its diff was read before the Claude lane's implementation
was typed.

Landing disposition, per the canary's own pre-declared rule (the Codex branch ships if its filter is
green, so that a Codex-implemented atom passes the unchanged machine gates end to end):

**`canary/274-codex` ships.** On the base `bc92cb2`, at head `6ea25a2`, the full local filter was
green on all four gates — `tests/run.sh` 1024 tests `OK (skipped=1)` in 457 s, `./noodles verify` 0,
`./noodles verify --trusted-preview` 0, three-dot diff a subset of the declared write-boundary — and
the branch was pushed. **A Codex-implemented atom passed this repository's unchanged machine gates
end to end.** That is the single fact this canary existed to produce, and it is now a receipt rather
than an argument. Landing itself remains the machine's: no PR was opened by this lane, no merge was
performed by hand.

`canary/274-claude` is recorded **UNMERGED, reason = canary-duplicate**, at head `5df8da4`, on the
same base, with its own green filter — `tests/run.sh` 1024 tests `OK (skipped=1)` in 452 s, verify 0,
trusted-preview 0, boundary subset 0. It is a complete, independently filtered implementation of the
same atom, pushed for inspection; it is not landed because the two lanes implement one issue and only
one may. **Both providers' work cleared the same gates**; the landing choice between them was the
canary's pre-declared rule, not a quality verdict.

Neither branch contains the other's commits, which is the mechanical form of "no cross-merge".

## 7. Raw receipts

All paths relative to the lane workspace
`scratchpad/wave27/f1/receipts/`. Nothing below is inlined wholesale.

| Receipt | What it is |
| --- | --- |
| `issue-274-raw.json`, `issue-406-raw.json` | provider raw bytes, `GET /repos/ed3c/noodles/issues/{274,406}` |
| `issue-274-body.md` | the exact prompt payload; wire side `issue.body` UTF-8 bytes, sha256 `82257e81…50d4c9`, 3206 bytes |
| `codex-instructions.md` | the hard-rule block given to the Codex lane |
| `codex-prompt-attempt1.txt` | the assembled prompt as sent (7265 bytes) |
| `codex-output-schema.json` | the `--output-schema` file |
| `codex-events-attempt1.jsonl` | full JSONL event stream, 130 events, including `turn.completed.usage` |
| `codex-last-message-attempt1.json` | `--output-last-message` structured final report |
| `codex-stderr-attempt1.log` | the lane's stderr |
| `monitor-prompt-lane-claude.txt`, `monitor-events-lane-claude.jsonl`, `monitor-findings-lane-claude.json` | the Codex monitor pass over the Claude lane |
| `monitor-findings-lane-codex-by-claude.json` | the Claude monitor pass over the Codex lane, including its own recorded misses |
| `fixture-positive.log`, `fixture-negatives.log` | §4 measurement-discrimination controls, both directions |
| `fixture-negatives-round2.log` | the same two controls re-run on the final rebased head, on an isolated byte-identical copy rather than in the worktree, because a full filter was queued on the mutex at the time and a plant landing inside that window would have been tested as if it were the atom; the log carries the three matching sha256 that make the copy the same oracle |
| `filter-lane-report-<UTC>.log` | the report branch's own full filter — the last gate this file passes through, and the one that caught it copying an owned value |
| `claude-controls.log`, `claude-controls-round2.log`, `codex-controls-round2.log` | per-lane positive and planted-negative controls, red-then-green by inverse edit |
| `filter-lane-codex-round1-base7717443.log` | the Codex lane's first-result filter, including the 27-test stale-base preview red |
| `filter-lane-*-<UTC>.log` | every subsequent full-filter invocation, one file per invocation |
| `bin/` | every driver in this run: `run_codex.sh`, `run_monitor.sh`, `filter_body.sh`, `withlock.py`, `patch_codex.py` |

`withlock.py` deserves a line: the wave's mutex is specified as `flock -x`, and this host ships no
`flock(1)`. The wrapper makes the identical `flock(2)` call on the identical path from Python, so the
kernel still releases it on process exit including on signal. A lane that had silently skipped the
mutex instead would have overlapped a 464-second suite with another lane's.


## 8. Dispatcher-ledger row

The dispatcher ledger is the wave's own record, not a tracked file in this repository, so the row is
emitted here for the dispatcher to record rather than written into `docs/findings/register.json`
(whose entries are chained findings, a different artefact with a different discipline):

```
lane=F1  trigger=ed3c/noodles#406  subject-class=ed3c/noodles#274  date=2026-09-03
base=bc92cb2bcd3f  provider-probe=codex-cli 0.149.0
codex-model = policy/fitness.json#required_codex_task_profiles.execute.model @bff2719 (pointer, not copied: policy/ownership-keys.json owns this value)
canary/274-codex  @6ea25a2  SHIPPED    filter=green/4  impl=codex:<codex-model>/high  monitor=claude:opus-5    SUPERVISION_DIVERSITY=provider-diverse
canary/274-claude @5df8da4  UNMERGED   filter=green/4  impl=claude:opus-5             monitor=codex:<codex-model> SUPERVISION_DIVERSITY=provider-diverse
           reason=canary-duplicate (one issue, two lanes; landing rule pre-declared, not a quality verdict)
canary/406-report @<head>   report     docs/codex-claude-differential-canary.md + tests/test_differential_measurement.py
axes: tokens codex=1.93M in/10.8k out, claude=UNMEASURED(no per-turn usage on surface)
      wall first-result codex=317.7s claude=114s(+~9min reconnaissance outside clock)
      filter 5 invocations, 3 lost to origin/main drift, 2 green
      findings confirmed/total codex-monitor=2/2 claude-monitor=1/1
      rework codex=37/46=0.80 claude=27/43=0.63
      correlated-miss claude-monitor=2/2 codex-monitor=0/2  CONFOUNDED by monitor protocol
retries-used=0/1 per lane; failure-class vocabulary not exercised
follow-up: identical-checklist monitor rerun (own atom); ed3c/noodles#70 profile table informed, not amended
```

## 9. Non-claims

- No routing change follows from this. One issue class, one sample, one host, one day. The
  `ed3c/noodles#70` profile table is informed, not amended; an amendment is its own atom with this
  report as its trigger.
- No provider verdict beyond this issue class. A documentation-plus-trusted-test atom exercises
  reading comprehension and repository-convention conformance. It does not exercise multi-file
  refactoring, debugging, or long-horizon planning, and this report says nothing about those.
- The canary driver consumed `codex exec --json` directly. The typed terminal-state migration and
  the event adapter remain owned by their own rescoped atoms; this run did not wait on them and does
  not substitute for them.
- The single monitor pairing means the correlated-miss result is a first datapoint, not a rate.

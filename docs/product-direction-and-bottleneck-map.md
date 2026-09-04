# Product direction and bottleneck map

**Class: N — session-adjudicated record. Never gate-bearing. Nothing in this
file may be cited as verification authority, evidence of closure, or
admission for anything it describes. Every section stays N-class until its
own path is physically walked; the graduation rule governing that boundary
expansion is §4's own subject.**

Subject: `ed3c/noodles#453`. Distilled 2026-09-04 from a 2026-09-04 operator
adjudication that otherwise existed only in a session transcript and a
tmpdir ledger. Five sections, each quantitative claim carrying a receipt
pointer (issue number, run id, or ledger archive path) or an explicit
`DECLARED` mark.

## 1. Six physical bottlenecks

Each row: the bottleneck, its measured numbers, its landed/open carriers, and
the product line it maps to.

| # | Bottleneck | Measured | Carriers | Product line |
|---|---|---|---|---|
| B1 | Landing serialization | `~6m50s` clear-queue vs `~62min` congested-tail per landed head (`gh run list`, 2026-09-01/02); a strict cold-start deadlock was separately observed 2026-09-04 | landed `ed3c/noodles#394`; open `#433`, `#179` | The Landing Control Plane itself, exported via the landed `#187` reusable-workflow shape |
| B2 | Verify duration | `~450s` local per run; `9–12min` per CI landing verify | `#419` (branch-coverage report-first surface), ecosystem ladders in `#417`; adapters built only on real repo admission (no pre-build) | Verify-as-a-service surface for onboarding ecosystems |
| B3 | Inference supply | The 2026-09-03 provider storm sank four dispatcher waves (see `docs/landing-strategy-and-salvage.md` §2 for the salvage receipt) | `#407` (six-mode fail-soft machine, landed/closed); `#450` (codex-cloud executor plurality, open) | Executor-plurality resilience |
| B4 | Credential-execute path | Three independent failures in one night (2026-09-03) | `#434` (preflight auth bound to `gh` binary, not write access); `#449` (drive-full-v1 uploader identity/WIF provisioning) | Credential-adapter hardening |
| B5 | Operator decision bandwidth | The one bottleneck this map does not claim is automatable | standing authorizations, gate-first admission, one-line-decision-plus-receipts | This *is* the product moat, not a bottleneck to engineer away |
| B6 | Local-machine resources | Swap to 2.4GB of 4GB under three-wave overlap (measured 2026-09-03; see runbook §7.4) | being dissolved by B3's cloud executors | No further investment — a self-resolving bottleneck |

**Verification status.** B1's timings, B3's storm date, and B6's swap
measurement are `MEASURED`/PROD, each with the run-history or ledger receipt
named above. B2's per-run durations are `MEASURED`/SANDBOX (local + CI
timing, not independently cross-checked). B4's "three independent failures"
is `DECLARED` — the count is the operator's own tally from the same night,
not re-derived from a provider-side log here. B5's non-automatability is
`DECLARED` by adjudication, not measured (there is no experiment that would
falsify it as framed).

## 2. pstack's true shape

**Claim.** pstack is not a scheduler, an evolution engine, or a measurement
system. Its shape is idea-to-self-verifying-skill realization: Launch /
Doctor / Drive / Evidence / Cleanup / Feature Map, plus prove-once
end-to-end, composed with poteto-mode deterministic routing.

**What it adapts to:** domain onboarding, deterministic routing, methodology
packaging — each new domain gets a skill born through the same six-stage
shape and the same prove-once receipt.

**What it does NOT adapt to** (explicitly out of scope, each owned
elsewhere):

- continuous evolution — owned by `sc` (skill-concerns)'s own evolution
  loops, not pstack;
- measurement — owned by `ed3c/skill-concerns#169`'s paired-lane
  differential instrument;
- landing authority — owned by the lander (`#433`'s thin shim), never
  duplicated inside pstack.

**Product role.** The domain-onboarding kit: every B2 ecosystem adapter's
verification skill is born through pstack, gated by the dual-standard birth
check (pstack's own create/maintain-verification-skill shape crossed with
skill-concerns' eight-gate mechanical admission).

**Verification status.** `DECLARED`. This is an architectural boundary
statement adjudicated in session, not yet exercised against a second domain
actually onboarding through it — B1's export section (below) names the exact
event that would promote it.

## 3. The inference straight-line's position

**Claim.** The inference straight-line is not a seventh bottleneck; it is
**B5's lever**. Better priors shrink the operator's residual adjudication
load — it does not remove B5, it reduces what B5 has to spend on each
decision.

**Instrument.** Its four-axis decomposition and measuring instrument live in
`ed3c/skill-concerns#169`, not in this repository — this map cites the
instrument by reference rather than re-deriving it.

**Evidence available today.** The adoption-agent natural experiment
(report-as-prior: minutes vs hours to productive adoption) is directional
evidence for the lever, not a closed measurement. Skill-as-prior specifically
remains measurement-unproven, and the 2026-09-03 storm-night corpus stays
`INSTRUMENT_SUSPECTED` — three waves without a clean before/after read is a
bounded diagnosis under two hypotheses (the instrument is broken, or the
workload distribution moved during the storm), not a verdict either way.

**Verification status.** `DECLARED` for the position claim (lever, not
bottleneck); the supporting evidence is honestly marked directional /
`INSTRUMENT_SUSPECTED`, not `MEASURED`.

## 4. Domain-expansion order (declared)

**Order:** second repository onto the train (B1) → its runtime adapter (B2,
built only on that repo's actual admission, never pre-built) → its
verification skill's dual-standard birth (pstack, §2 above). The remaining
bottlenecks (B3–B6) are consumed along that path rather than engineered
ahead of it.

**Boundary sentence** (standing adjudication, cited not revisited): the
product is the **Autonomous Change Admission + Landing Control Plane**, NOT
an Agent OS.

**The graduation rule this section's own header cites.** Every section in
this file, and in `docs/landing-strategy-and-salvage.md`, stays N-class —
never gate-bearing, never spec authority — until the exact path it declares
has been physically walked. B1's export section is the concrete instance:
it graduates from N-class into `contracts/system-v1.md` only when a *second*
repository actually lands a candidate through this train, not when the
architecture is merely well-argued. Boundary expansion is therefore an
evidence event (a repo lands), not an enthusiasm event (someone is convinced
by the doc).

**Verification status.** `DECLARED`. No second repository has yet admitted;
this section names the exact readback that would flip it (`gh` query against
the second repository's own landing-train run history, once one exists).

## 5. The backlog-ETA decomposition law

**Operator question, 2026-09-04:** "how long until all issues are solved?"

**Adjudication:** no new skill. The birth gate refuses on coverage (no
domain this question names is currently uncovered by an existing skill), and
the standing anti-prediction ruling refuses the model class (this machine
does not build predictive-ETA models; it measures).

**The law.** The question decomposes into three parts, each with a different
estimator, and only the first is a straight line:

1. **MECHANICAL part** (implemented-awaiting-land + small well-specified
   atoms): `ETA = queue_depth × measured_cycle_time / parallelism` — pure
   arithmetic over the fourth curve's own numbers (the landing-economics
   pass's measured cycle time), no skill needed.
2. **DECISION-BOUND part** (`BLOCKED_EXTERNAL`): not time-estimable at all.
   Each item in this class is one operator sentence away and zero
   engineering away; estimating it as a duration is a category error, not a
   hard estimation problem — there is no engineering effort curve to fit.
3. **UNKNOWN part** (atoms whose contradiction or platform semantics must
   still be discovered): bounded by **budget**, never by estimate. The
   decompression instrument is `ed3c/skill-concerns#147`'s five-layer
   fan-out, paired with the over-enumeration negative arm. Measured tonight
   (2026-09-04): roughly one atom in five needed real exploration (live
   experiments, platform-semantics reading) and one to three decompression
   layers; the deep class (trusted-transition deadlocks) hit three-plus
   layers.

**The trend inflection is produced, not predicted.** Freezing speculative
filing (a ruled standing decision — no new tickets for speculative work,
only a newly measured defect earns one) plus keeping the drain running turns
net-open negative the same day; the fourth curve then attributes that turn
after the fact. It is a produced outcome of two policy choices, not a
forecast of one.

**Verification status.** The one-in-five exploration ratio and the
one-to-three (three-plus for the deep class) decompression-layer counts are
`MEASURED`, tonight only — one measurement night is not yet a stable rate.
The three-way decomposition itself and the "produced not predicted"
framing are `DECLARED`: adjudicated reasoning about why estimation fails on
parts 2 and 3, not something falsifiable by a single run.

## Non-claims

No spec-book entry: every section stays N-class until its path is physically
walked (B1's export section graduates only when a second repository actually
lands through the train). No new mechanism anywhere: every carrier named
above already exists as a landed feature or an open issue; this file only
writes the map. No commitment to timelines and no commitment to building B2
adapters before their repositories admit — the standing no-prebuild ruling
is cited here, not revisited.

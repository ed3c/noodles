# Landing strategy and salvage

**Class: N — session-adjudicated record. Never gate-bearing. Nothing in this
file may be cited as verification authority, evidence of closure, or
admission for anything it describes. Each section states its own
verification status; promotion into `contracts/system-v1.md` requires the
physical verification named in that section, carried by the owning issue.**

Subject: `ed3c/noodles#438`. Distilled 2026-09-04 from the 2026-09-03
dispatcher session ledger (a tmpdir file that dies with the session) and
scattered issue paragraphs — the operator-adjudicated knowledge named in the
triggering issue had no repository home before this file. Three independent
bodies of knowledge, each honestly marked `MEASURED` / `PARTIALLY VERIFIED` /
`DECLARED`.

## 1. The three-beat async landing strategy — `PARTIALLY VERIFIED`

**Claim.** Landing under the parallel topology decomposes into three beats,
governed by a displacement-conservation law: opening a candidate never
displaces work already in flight, only queues behind it. Two accelerator-hold
classes carry that law:

- **lane-green opens a PR without flipping anything** — a lane reaching green
  locally publishes its candidate but does not itself advance `main` or
  cancel a sibling's in-flight verify; the flip is a separate, later beat.
- **the pre-stack integration worktree is the single absorption point** —
  every candidate destined for a batch lands its diff into one shared
  pre-stack worktree first, so the fan-in from N parallel lanes collapses to
  one integration surface instead of N pairwise rebases.
- **the flip itself is collision-ordered** — when two candidates' write
  boundaries intersect, the later one queues at the flip, not at
  implementation (worktrees already dissolve the implementation-layer
  collision; see §7.7 of the operator runbook, "write-boundary collisions
  bind landing, not implementation").

**Receipt.** The #394 lane built the pre-stack manifest producer and measured
the landing train's two physical regimes over this machine's own run history
(`gh run list --repo ed3c/noodles --limit 30`, 2026-09-01/02): the
clear-queue regime lands one head per **~6m50s**; the congested-tail regime
averages **~62 minutes per landed head** over the same machinery — the
difference is the quadratic rebase-reverify tax a `strict`-checked serial
train pays on every queued sibling. The verified-batch capability (one
verified identity over n heads; rejects wrong base, wrong count, duplicate
heads, reordered members) is landed on `main`; the train's clear-queue path
still consumes heads one by one, so the batch capability is `DECLARED` while
the tax itself is `PRODUCTION`-measured.

**Verification status.** The two regimes and their timings are measured
(SANDBOX/PROD arrival: `gh run list`, computed from `createdAt` deltas). The
displacement-conservation law and the three accelerator-hold classes as a
named mechanism are `DECLARED` — adjudicated in session, not yet exercised
against a planted collision.

**Owning issues.** Mechanization: `ed3c/noodles#394` (verified-batch
capability, landed), `ed3c/noodles#433` (lander pinned behind a thin shim so
lander changes merge dead and activate by one line), `ed3c/noodles#436`
(sole-coupler acceptance widened so the verified-batch coupling can land
staged). None of the three closes this section's `DECLARED` half; each
narrows it.

## 2. The storm-salvage protocol — `MEASURED`

**Claim.** An API-layer agent death during a provider outage does not
destroy the workspace it was operating in — the workspace (worktree, branch,
uncommitted diff) is durable state outside the dying process. The salvage
formula: **verify identity → push the surviving branch → adopt-mode
resume.**

**Receipt.** Fully verified live during the 2026-09-03 provider incident: a
529 error storm, confirmed against the provider's own status-page receipt at
**13:26 UTC**. Agents mid-task died with the storm; their worktrees and
uncommitted branches survived on disk and were salvaged by the formula above
without re-deriving the lost work.

**Two measured lessons from the same night:**

- **Resume caching is longest-unchanged-PREFIX.** A resumed session's cache
  hit is bounded by the longest prefix of tool calls that matches exactly;
  editing any earlier call in the sequence invalidates the entire cached
  suffix after it, not just the edited call. Salvage that reorders or
  retroactively edits early steps pays for the whole tail again.
- **Email-privacy rejection of clone-inherited global identity is cured by
  repo-local identity set immediately after clone.** A fresh `git clone`
  inherits the machine's global `user.email`; pushing under that identity
  is rejected when the global email is a private one GitHub will not accept
  on a push. The cure is `git config user.name` / `user.email` scoped to
  the clone, run in the same motion as the clone — not deferred to first
  commit, since a forgotten identity fails at push time, after the work is
  already done.

**Verification status.** `MEASURED` / `PRODUCTION`: the storm, the status-page
receipt, and the salvage recovery are one incident with a timestamp, not a
constructed scenario. The two lessons are themselves measured (each caused
at least one real salvage failure before the cure was known), not merely
declared best practice.

## 3. Model-tier degradation practice — `MEASURED`, boundary `DECLARED`

**Claim.** When a provider incident names specific model tiers as degraded or
unavailable, the dispatcher may temporarily route surviving pipeline stages
to an unaffected tier (observed: Opus-tier stages tailing to Sonnet-tier)
without touching workflow semantics or landing authority. This is routing a
tier substitution for the duration of a named incident, not a standing
policy change — the substitution reverts once the incident's own status page
clears.

**Receipt.** Verified live the same 2026-09-03 storm night: the affected
tier was named by the incident, surviving stages were re-routed to the
unaffected tier, and the wave completed under the substitution with no
change to which stages verify, which stage lands, or who holds landing
identity.

**Boundary with provider fail-soft.** This practice is distinct from, and
finer-grained than, `ed3c/noodles#407`'s six-mode fail-soft machine, which
governs provider-level availability transitions (mode, not tier) and stays
untouched by this section — model-tier degradation operates *inside* a
single fail-soft mode, substituting which tier executes a stage, never which
mode the provider is in. `#407` is landed (six-mode machine with transition
receipts, closed); this section does not modify it, extend it, or claim any
part of its acceptance.

**Verification status.** The substitution itself and its outcome (wave
completed, semantics and landing authority unchanged) are `MEASURED`/PROD.
The general rule — *any* named-tier incident may be handled this way — is
`DECLARED`: one incident is one data point, not a policy proven across
incident shapes.

## Non-claims

No mechanization lands with this file. The strategy's machine carriers are
`ed3c/noodles#394`/`#433`/`#436` and the accelerator-hold derivations they
produce; this file only writes the N-class record that survives the
dispatcher session. No section here is promoted into the spec book —
promotion requires the physical verification each section names as pending,
walked by its owning issue.

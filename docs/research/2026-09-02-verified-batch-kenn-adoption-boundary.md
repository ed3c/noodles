# Verified-batch and Kenn adoption boundary

Date: 2026-09-02  
Guarantee class: N — non-claim  
Subject: ed3c/noodles#362

## Decision

This document records routing constraints. It proves no runtime behavior, CI reduction,
correctness property, or landing authority.

| Surface | Disposition | Reconsider only when |
|---|---|---|
| Native `verified_batch` (#343) | PROCEED | Implement the bounded deterministic Git primitive described below |
| AgentsView | HOLD | Existing noodles receipts cannot answer one explicit token, cost, context, or tool-use question |
| Roborev | HOLD | Review-addressable defects form a meaningful measured share of GitHub Actions failures |
| Kenn Forge | HOLD | At least two operational thresholds below are reached |
| Kata | DROP | A future physical failure shows GitHub Issues and Noodle cannot remain the sole task-state owner |
| Forking the Kenn stack | DROP | No current evidence justifies a second control plane |

## Native verified-batch boundary

#343 proceeds first as a pure-ish repository-owned Git primitive. An exact base and
exactly three ordered compatible member heads produce a deterministic integration
object and canonical manifest.

The primitive may:

- select already-supplied member records;
- construct the integration object;
- describe ordered membership;
- verify candidate identity using Git object readback.

The primitive may not:

- decide eligibility or CI truth;
- call the GitHub API or publish a remote ref;
- merge `main`, close an Issue, or change noodles state;
- retry indefinitely, bisect, schedule, or own a queue;
- authorize `land.yml`.

“Compatible” means the Git objects can be integrated mechanically. It does not mean
the members are green. Determinism requires fixed commit metadata and reconstruction
of the same manifest, tree, parent graph, and candidate SHA in two independent
temporary repositories.

`rust-lang/bors` and `bors-ng` are reference implementations and test oracles only.
No runtime, dependency, source tree, service, database, or control plane is imported,
vendored, forked, or deployed.

## Trusted authority boundary

No Kenn tool may enter or influence:

`verify.yml → receipt → land.yml`

The existing generic boundary remains authoritative: pinned Actions and
repository-owned trusted executables verify provider truth, bind the exact candidate
head, emit the receipt, and permit the existing lander to act. This is an architectural
rule, not a Kenn-specific brand blacklist.

A Kenn result may be advisory metadata. It is never an L-class gate, R-class receipt,
eligibility marker, merge input, or state owner.

## Optional-tool gates

### AgentsView

HOLD until a named observability question cannot be answered from existing noodles
receipts. A future probe, if justified, is one isolated local session, metadata-only,
with no raw transcript upload and disposable state. The probe cannot join production
verification or landing.

### Roborev

HOLD. One review cannot demonstrate a lower GitHub Actions failure rate. A future
one-shot probe may run only in a disposable clone and may measure planted-defect
recall, false positives, latency, cost, and residue. It may not install hooks, run a
daemon, auto-fix source, or start a refine loop.

### Kenn Forge

HOLD until at least two of these measured conditions are true:

- five or more sustained concurrent local worktrees;
- ten or more manual Issue, PR, or session lookups per week;
- three or more workspace or claim mistakes per week;
- two or more hours of manual triage per week;
- an observed visibility gap in the noodles CLI.

If admitted later, Forge is a rebuildable read-only projection. It cannot own claims,
worktrees, task state, retries, merges, or authoritative evidence.

### Kata

DROP for noodles integration because it would duplicate the existing GitHub
Issue/Noodle state owner. Do not add a vendor-specific prohibition gate without a
repeated observed failure.

## Execution order

1. Implement and land #343.
2. Run the normal GitHub Actions gates.
3. Design a separate provider canary after #343 is on the default branch.
4. Measure CI run count, runner minutes, wall-clock time, exact tested SHA, and exact
   landed SHA.
5. Probe AgentsView only for a demonstrated observability gap.
6. Probe Roborev only when review-addressable defects are a meaningful share of CI
   reds.
7. Consider Forge only after its thresholds are met.
8. Add deterministic bisect only if red-batch measurements justify it.

A failed batch optimization falls back to the existing one-PR train. Batching is not a
correctness dependency.

## External source identities

The following identities were inspected on 2026-09-02. External descriptions and
license observations are time-stamped research and may change:

- https://kenn.io/
- https://wesmckinney.com/blog/agentic-engineering-aug-2026/
- https://github.com/kenn-io/agentsview
- https://github.com/kenn-io/roborev
- https://github.com/kenn-io/forge
- https://github.com/kenn-io/kata

At the inspected revisions, AgentsView, Roborev, and Kata declared MIT licenses. Kenn
Forge declared Elastic License 2.0, which restricts offering the software as a hosted
or managed service that exposes a substantial set of its functionality without
separate permission. These observations are research notes, not legal advice.

## Non-claims

- This N-class document is not L- or R-class evidence.
- No Kenn tool is installed, executed, depended on, forked, or integrated.
- No #343 implementation or provider canary is performed here.
- No CI-time, review-quality, commercial-use, or provider-capability claim is proven.
- No workflow, source, policy, dependency, lockfile, Issue state, scheduler, queue,
  worktree owner, merge owner, retry engine, or observability backend is changed.
- This document cannot be used as a verification receipt, landing gate, or completion
  proof.
- The existing provider lander remains the sole merge authority; this decision creates
  no alternative landing path.

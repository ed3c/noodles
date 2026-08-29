# Drift ledger projection

> **N-class only.** Findings are planning signals. A finding becomes a blocker or landed fact only through its owning executable/provider boundary.

## Severity

```text
L0 OBSERVE
  inventory or possible mismatch; no immediate claim impact

L1 WARN
  bounded inconsistency or stale projection; schedule only after refresh

L2 REVIEW
  ownership, denominator, write-boundary, or evidence ambiguity requires an exact owner

L3 BLOCK
  current path could authorize the wrong subject, skip mandatory evidence, collide writers, or launder N/P into L/R
```

## Drift dimensions

| Dimension | Check |
|---|---|
| Source denominator | every named conversation, repository, Issue/PR, article/PDF, runtime observation, and method source is present or explicitly missing |
| Source identity | repository commit/tree, Issue body digest, PR head, provider lock, runtime lock and document identity are exact |
| Requirement ownership | stable rationale has one owner; Issue-specific facts are not copied into the specification |
| Issue completeness | exact subject, requirement/hypothesis, dependency, write boundary, trigger, bounded claim, controls, readback, residue, non-case, non-claims |
| State consistency | stored Issue marker, provider open/closed state, PR state, dependency state, and local order state do not contradict |
| Start/completion edges | every completion dependency has its own receipt rather than inheriting a start dependency |
| Writer ownership | no overlapping active worktree/file leases or competing durable writers |
| Authority | P/N statements are not presented as local L or provider R evidence |
| Evidence binding | receipt binds target, Issue, body digest, base, head, feature/journey, oracle identity, observation and residue |
| Impact coverage | every changed supported code surface maps to a feature/journey/oracle or explicit mechanically checked non-case |
| Repair boundedness | retry has exact lane identity, attempt bound, terminal taxonomy and residue control |
| Projection freshness | this package is regenerated after relevant canonical/provider changes |
| Cross-repository authority | authority follows the mutated target repository; central planning does not prove target correctness |

## Current findings

### D-001 — Local Shadow monitor receipt is not part of this snapshot

Severity: `L1 WARN`.

The requested local source is `/Users/neon/skills-shared`. This GitHub projection records the intended method and opens a monitor epoch, but it does not contain local HEAD/worktree/process output. The local operator lane must bind:

```text
repo path
HEAD/tree
worktree status
monitor invocation
start/end timestamp
detected deltas
residue
```

Claims depending on a live local monitor remain `NOT_EXERCISED` here.

### D-002 — Complete article/PDF/video source denominator is unfrozen

Severity: `L2 REVIEW`.

The conversation contains source summaries and screenshots about Lauren/pstack, verification, Dune Agent-friendly architecture, and related systems. Exact URLs/files, retrieval timestamps, extracted bounded claims, and source digests are not all captured in this package. Preserve this as `ABSENT_OR_UNFROZEN`; do not silently treat conversation paraphrases as independently verified facts.

Owner: future source-freeze packet under #117 or the producer Skill canary.

### D-003 — System specification convergence is split across active/planned atoms

Severity: `L2 REVIEW`.

`#109` owns Dune-derived AF requirements, `#83` owns canonical document/procedure writers, and a future SPEC-CONVERGE atom is intended to organize the full stable specification. These write boundaries may overlap `AGENTS.md` and `contracts/system-v1.md`.

Required action:

- refresh current PR/worktree leases;
- serialize overlapping writers;
- finish one bounded atom before opening the next;
- never merge two independently rewritten specification owners.

### D-004 — Incomplete READY Issue example exists

Severity: `L3 BLOCK` for scheduling that subject.

`#69 --help` has historically contained only generic template acceptance and lacks a bounded trigger, requirement, write boundary, exact claim, specialized controls, and non-case. Marker completeness is not executable completeness.

Owner: ISSUE-CONTRACT atom plus open-Issue audit. Until that gate lands, scheduling must refuse or manually block incomplete subjects rather than infer intent.

### D-005 — Dependency waiting and explicit blocker state may drift

Severity: `L2 REVIEW`.

Several historical Issues remained `blocked` after predecessors were landed. `#82` owns deriving eligibility from provider dependencies and separating dependency waiting from a true blocker owner/reason.

Check on every epoch:

```text
all dependencies landed and closed?
Issue still open?
explicit blocker owner/reason exists?
open exact PR already exists?
write boundary conflicts?
```

### D-006 — Feature/oracle enforcement remains incomplete

Severity: `L3 BLOCK` for universal physical-verification claims.

`#19`, `#20`, and `#66` represent the P-to-L oracle contract, first feature canary, and changed-code impact compiler. Until their exact receipts land, the repository cannot claim every relevant completion path necessarily operates the real product/runtime artifact.

### D-007 — Full unattended and multi-Issue autonomy remain open

Severity: `L3 BLOCK` for Full Autopilot claims.

Substrate components have landed, but `#4`, `#21`, and `#22` remain the decisive single-Issue, learning, and bounded multi-Issue canaries. PR throughput or route discovery does not close these objectives.

### D-008 — Concurrency correctness is not yet independent of N

Severity: `L3 BLOCK` for arbitrary-concurrency safety claims.

I1–I4 owners are #45, #46, #98, and #99; #100 binds their receipts. Until all are provider-landed and live negatives remain in the suite, `max_concurrency` is capacity configuration, not evidence.

### D-009 — Candidate self-authorization must be checked at every oracle boundary

Severity: `L2 REVIEW`.

Trusted verifier isolation was historically repaired, but feature-local contracts may be changed by the same candidate they judge. Every future evidence envelope must use trusted bytes or a pre-admitted oracle identity/digest. Candidate-created tests are useful evidence but cannot be the sole authority for that candidate.

### D-010 — Context-closure producer is not yet admitted

Severity: `L1 WARN`.

`ed3c/skill-concerns#9` is a candidate concern owner. This consumer package may proceed as a target-local N projection, but it cannot claim the reusable Skill has passed source lock, hermetic negatives, and consumer canary.

### D-011 — Derived status must not become stored truth

Severity: `L2 REVIEW`.

Future `requirements status` output should be derived from specification, Issue/PR/provider state and receipts. Do not create or manually curate a mutable `landed-facts.json`, closure database, or status registry.

### D-012 — Three-hop execution route must not absorb this package

Severity: `L3 BLOCK` if violated.

This package is for Shadow/Tech Lead planning. Adding it as a mandatory fourth read node for every execute Agent would increase context entropy and contradict the landed route contract. Task packets may cite one exact finding, but execution must return to `AGENTS.md -> system contract when triggered -> exact Issue/nearest executable boundary`.

## Epoch checks

Before declaring this projection current:

- [ ] default branch commit/tree frozen;
- [ ] all referenced Issue bodies and provider states refreshed;
- [ ] open PR heads/checks/base branches refreshed;
- [ ] active local/Noodle worktrees and write leases read back;
- [ ] runtime/provider lock state refreshed where relevant;
- [ ] source documents frozen or explicitly missing;
- [ ] no N path is referenced as completion evidence;
- [ ] start and completion edges separately reviewed;
- [ ] all L3 findings have an owner or explicit unsupported state;
- [ ] six-file diff and zero out-of-boundary residue confirmed.

## Promotion law

A drift finding may become a durable rule only through:

```text
finding
  -> exact owner Issue
  -> repeated physical reproduction where required
  -> non-case
  -> nearest executable control
  -> planted negative
  -> trusted provider landing
```

Editing this ledger never promotes the finding by itself.

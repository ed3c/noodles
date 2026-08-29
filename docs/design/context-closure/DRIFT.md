# Drift Ledger

> N-class only. Severity is a planning signal, not execution or provider authority.

Severity: `L0 OBSERVE`, `L1 WARN`, `L2 REVIEW`, `L3 BLOCK`.

## Current findings

| Severity | Finding | Provider/source observation | Safe next action |
|---|---|---|---|
| L2 REVIEW | #117 remained manually `blocked` after prerequisite #112 provider-landed. | #112 closed/landed; #117 body still named it as blocker before repair. | Repaired #117 to lifecycle `ready`; keep dependency waiting derived. |
| L3 BLOCK | #124 was lifecycle `ready` while its exact subject marker was `pending`. | #124 provider body before repair. | Repaired to exact `ed3c/noodles#124`; exact-subject validation remains mandatory. |
| L0 OBSERVE | #119 has now provider-landed and closed. | PR #126 exact head `56e2df152f8daec7683ee6d9d3d18ff27197e527`, merge/default branch `4b3f3e53c642dd33d0f3632bced3006c6cbf2ea3`. | #83 may now own procedure convergence; do not retain #119 as active writer. |
| L0 OBSERVE | #83 is active via PR #129 after #82/#119 landing. | provider Issue/PR readback | Treat #83 as current writer for Agent procedure/document/Skill ownership. |
| L0 OBSERVE | #4 is lifecycle `ready` while #19/#20 remain open, so derived schedulability is false. | #4 dependencies + landed #82 semantics. | Expected behavior; leave lifecycle `ready`, let provider-derived eligibility decide. |
| L2 REVIEW | #98 remained manually `blocked` after its only predecessor #82 landed and no separate blocker was declared. | #98 + #82 readback. | Repaired #98 to lifecycle `ready`; normal admission decides execution. |
| L2 REVIEW | Many open Issues retain old `noodles-feature: verification-skill-oracle` markers even though #112 made specialized feature verification optional/additive. | provider Issue portfolio snapshot | Audit each marker when its Issue becomes active; remove only when unrelated to the changed feature surface. |
| L2 REVIEW | #120 depends on #82/#119/#98/#83; two predecessors remain incomplete. | #120 body + current provider states. | Keep #120 blocked until #98/#83 land. |
| L1 WARN | Repository-wide semantic duplicate-owner detection is not mechanically proven. | #109/#119 design + document controls. | #83 should define finite canonical Agent-facing owners; #84 can strengthen structural behavior. |
| L1 WARN | Raw owner conversation is outside repository storage. | source denominator | Preserve `PARTIAL`; do not claim complete context/cognition capture. |
| L1 WARN | Historical architecture-changing Issue list is not fully re-fetched in this docs atom. | TRACEABILITY historical set | Re-read provider evidence only when a future completion edge depends on it. |
| L1 WARN | Article/PDF/social claims remain external. | owner conversation denominator | Keep `EXTERNAL-CLAIM` unless separately verified. |
| L2 REVIEW | #124 branch was originally based on pre-#119 main, causing trusted cross-version spec tests to fail after #119 landed. | trusted run on PR #128 | Rebase/reconstruct #124 candidate on latest protected main without weakening tests. |
| L0 OBSERVE | #83 and #124 write boundaries are disjoint. | #83 Agent/README/Skill contract surfaces vs #124 docs-only package | May progress concurrently; landing remains independent. |

## Mandatory review checklist

Inspect on every planning refresh:

- requirement/source problem with no Issue owner;
- Issue missing exact subject, dependencies, trigger, bounded claim, write boundary/owner, physical acceptance, non-case, or non-claims;
- stale manual `blocked` used only for dependency waiting;
- lifecycle `ready` misread as schedulable/completion-ready;
- Issue/PR/head/body mismatch;
- active write-boundary overlap or duplicate durable owner;
- P/N statement promoted above evidence ceiling;
- START edge used as COMPLETE edge;
- changed supported code with no feature/journey/oracle or explicit no-impact non-case;
- stale base/head causing trusted cross-version contract failure;
- N document cited as L/R evidence;
- leaf completion while global case denominator remains open;
- repair that changes subject/session/worktree identity;
- candidate-modified oracle used as sole authority for the same candidate.

## Unmechanized planted negatives

These remain review procedures, not deterministic gates:

1. Remove one denominator source and verify omission remains visible.
2. Replace a completion edge with only a start edge and reject the projection.
3. Add two owners for one durable value and require one convergence owner.
4. Cite this N package as correctness proof and reject authority laundering.
5. Copy mutable run/SHA/status into stable specification truth and reject the move.

If these deserve executable authority, promote them through their own exact Issue and nearest test; do not silently upgrade this document.

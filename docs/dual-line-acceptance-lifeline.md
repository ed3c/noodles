# Dual-line acceptance: one atom's micro lifeline (draft)

**Class: N — research note. Never gate-bearing. Points ①–⑧ describe behavior that has
session receipts but has NOT been machine-verified as a document; point ⑨ is prospective.
Promotion of any part into `contracts/system-v1.md` requires its own verified atom.**

## The lifeline

```
--- LOCAL LINE (implementation + cheap filter, seconds-scale) -------------------
(1) implement: fresh clone only (scratchpad); the shared tree is never touched
(2) L-grade filter: tests/run.sh + ./noodles verify + planted red-then-green.
    "The cloud will catch it" is a listed violation, not a strategy.
(3) ceremony triple: commit (inline identity + Refs trailer) -> push branch ->
    open PR (body is exactly one Refs line)
(4) state flip: issue -> awaiting_land. The local line's last act; omitting it
    turned an entire wave's queue red once (2026-09-01 receipts).
--- HANDOFF LINE (zero local actions past this point) ---------------------------
--- CLOUD LINE (final acceptance + landing, ~10-minute grade, R-level evidence) -
(5) acceptance point 1, candidate-self-tests: the candidate's own suite on a real
    runner. Authority: none — its green admits nothing (a candidate never
    certifies itself).
(6) acceptance point 2, trusted verify (pull_request_target): the default
    branch's judge code, the candidate as data, an exact-head receipt.
    THE ONLY acceptance point holding admission authority. The parallel-verify
    transition changes this point's topology, never its seat of authority.
(7) acceptance point 3, land preflight: issue open + awaiting_land, drift checks,
    exact-head comparison. It verifies ceremony coherence, not code — the
    premature-"landed" incident of 2026-09-02 died exactly here.
(8) the five-action bundle: merge -> close issue -> rewrite markers -> anchor
    comment -> pump the next head. A bare merge by any other channel produces a
    half-landed orphan; "merge" in the machine class is the name of this
    ceremony, not of an API call.
(9) PROSPECTIVE acceptance point 4, the cloud line: merge timing for the
    issue-NNN-* class with the merged-via marker; advisory checks over the
    machine class whose agreement rate accrues in the ledger toward ratchet
    promotion. Unverified until its first receipted merge.
```

## Division criteria

| failure class | must die at | cost |
|---|---|---|
| logic errors, red tests, planted controls that fail to go red | local (2) — deferring to the cloud is a violation | seconds |
| ceremony gaps (body format, state marker, markers) | local (3)(4) self-check; leaks die at (7) | free locally vs one 10-minute cloud round |
| provider behavior, token boundary, real CI timing | only the cloud (5)(6) can kill these — physics no mock carries | 10 min/round, buying evidence, not waste |
| the right to enter the default branch | always and only (6) plus branch protection (enforce_admins verified true by readback) | — |

## One-line closure

The local line kills everything cheaply decidable before handing off; the cloud line
spends only on what the local line physically cannot buy. Each acceptance point kills
exactly one failure class no other point can, and authority lives at (6) alone.

## Session receipts behind ①–⑧ (pointers, not authority)

The wave-18 tail drain and its three stall classes; the premature-landed marker
incident and its one-line cure; the dual-line merge adjudication (enforce_admins
readback, class partition, merged-via ceiling). Dispatcher ledger materials, 2026-09-01/02.

## Retirement criterion

Each numbered point graduates individually when a verified atom lands its behavior as
specification or validator text; the file retires when nothing unpromoted remains.

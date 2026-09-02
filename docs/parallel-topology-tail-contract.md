# Landing-tail recovery contract under the parallel topology (draft)

**Class: N — research note. Never gate-bearing. Nothing in this file may be cited as
verification authority; promotion into `contracts/system-v1.md` requires the physical
verification recorded in the table below, carried by the topology line's own atom.**

## The question this document holds open

Under the parallel verify topology, each of the three serial-era stall classes must be
adjudicated into exactly one of two fates, with evidence:

| stall class (serial-era receipt) | fate A: impossible by construction | fate B: owned recovery | physical verification required before spec promotion |
|---|---|---|---|
| dependency-red head (successor parked while predecessor open) | batch carries dependency order | owner + event named in writer map | planted control: constructing the state is refused at an earlier gate — run it, record the refusal |
| stale-green head (verified, then base advanced; strict blocks merge) | batch re-verifies the combined head | owner + event | planted control: a deliberately staled green either cannot exist or is recovered by the named owner within one event — observe one real recovery |
| land-run failure residue (green PR stranded after a failed merge attempt) | queue atomicity | owner + single bounded retry | planted control: a failed land leaves either nothing (atomic) or a state the owner provably picks up once |

Rules for filling the table:
- A checked "fate A" cell is a claim about construction — it needs its planted control
  RUN (the state manufactured and refused), not argued.
- A checked "fate B" cell needs a writer-map row in the spec for the named owner; an
  owner named here but absent from the writer map is a dangling pointer.
- An unfilled row means that class falls back to the serial cures parked in
  ed3c/noodles#332, which un-parks for exactly that row.

## Context receipts (serial-era, for the before/after comparison)

- Serial cost structure: ~10 min verify per fresh head, one head per pump; three stall
  classes each produced a live wedge on 2026-09-01/02 (quota-consumption cure wave and
  the wave-18 tail drain), receipts in the dispatcher ledger materials.
- The parked serial cures and their acceptance shapes: ed3c/noodles#332.
- The dual-line merge adjudication (enforce_admins readback, class partition, merged-via
  marker and its cooperative ceiling): dispatcher wave notes, 2026-09-02.

## Promotion criterion

This document graduates (and retires) when the flip atom lands the filled table as spec
text under the delivery heading, each checked cell carrying its run receipt. Until then
this file answers questions and gates nothing.

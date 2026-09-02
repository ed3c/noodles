# Slop-safe refactor contract (draft)

**Class: N — research note. Never gate-bearing. Nothing here may be cited as
verification authority; each clause graduates individually when a refactor atom
lands it as executable acceptance, and this file retires when nothing unpromoted
remains.**

## Purpose

A refactor is the mutation class agents copy worst: the diff is large, the
behavior claim is "nothing changed", and every clause below exists because its
violation has either happened in this machine or has a named receipt shape.
A refactor atom's Physical acceptance SHOULD instantiate every applicable
clause as a runnable control; a clause that does not apply is declared
inapplicable by name, never skipped silently.

## The six clauses

### R1 — Data in, data out identical, INCLUDING the side-effect set

Same inputs produce same outputs — and "output" is the full observable set:
return values, files written, provider calls issued, state mutated. Pure
functions compare returns; effectful ones compare effect sequences. Carrier:
the full suite green, plus an effect-log comparison where the subject has
effects the suite does not pin.

### R2 — Blast radius: bidirectional data flows identical

Everything that feeds the moved code and everything it feeds behaves
identically. Carrier today: the whole suite (green after = flows held).
A symbol graph makes the radius VISIBLE (caller/callee closure); the suite is
what makes "identical" PROVEN. Do not confuse the viewer with the oracle.

### R3 — The admission surface moves, it never changes

The number-one slop shape: a refactor that "tidies" a trusted gate's predicate
while relocating it — behavior shifts while tests stay green, because the test
read the predicate that moved. Carrier: the refactor diff touches no trusted
gate's decision logic; gates are moved verbatim or not at all; zero
test-semantics changes beyond mechanical import-path updates, asserted in the
atom.

### R4 — Intermediate observable states unchanged, not just endpoints

Endpoint-identical trajectories can still differ mid-flight: marker
transitions, session event order, receipt states. For every polymorphic state
the subject emits, name the producing line before and after; a state only
tests construct is a state that does not exist. Carrier: state-transition
controls per the subject's own contract, not just end-to-end assertions.

### R5 — Reversibility receipt

Every refactor atom carries its inverse: one command (or one revert per staged
batch) restores the prior tree, proven once in the atom's controls. A
restructuring you cannot roll back is not a refactor, it is a bet. Batches
that would defeat review land as a short series, each independently
revertible.

### R6 — Deletion requires a zero-consumer PROOF, and grep cannot give one

Moving and renaming need R1–R5 only. DELETING a symbol needs proof that no
consumer exists — and "temporarily zero callers" (a capability a filed atom is
about to consume) is indistinguishable from "dead" at the byte and structure
levels. Only the symbol graph plus the open-issue ledger can separate them:
zero occurrences AND zero filed consumers. This is the one clause where
code-intel is a NECESSARY condition, not an accelerator. Until the runtime
symbol surface lands, deletion-type refactors either keep the symbol (move it
aside, ownership-dispositioned) or carry a hand-audit naming every searched
surface and the open-issue sweep.

## Applicability table (fill per atom)

| clause | applies? | control instantiated at |
|---|---|---|
| R1 I/O + effects | | |
| R2 blast radius | | |
| R3 admission surface | | |
| R4 intermediate states | | |
| R5 reversibility | | |
| R6 deletion proof | | |

## Receipts behind the clauses (pointers, not authority)

R3: the ratchet that acquired merge authority by omission, and its
normalization cure. R4: the write-boundary widening that was never re-checked
mid-claim. R5: the unplant carrier adjudication (two lost-work incidents).
R6: the ownership gravity-well drain's own non-claims (moves at measured
seams, no deletions) and the code-intel surface chain it deliberately does
not wait for. Dispatcher ledger materials, 2026-09-01 through 09-03.

## Graduation and retirement

The gravity-well drain atom is this contract's first consumer: its acceptance
already instantiates R1–R5 and declares R6 inapplicable (move-type, no
deletions). Each clause graduates when some atom's landed acceptance carries
it as an executable control that a later atom can cite by path; the file
retires when all six have landed carriers.

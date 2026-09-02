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

## The sensitivity layer — oracle strength is a separate claim

The six clauses prove one thing: under the CURRENTLY ENCODED observable
contract, candidate and baseline are equivalent. A green suite says nothing
about its own blind spots — whether the oracle can even see the distinctions
that matter. Oracle sensitivity is a separate claim requiring separate
evidence, and it must never be folded into the equivalence claim itself.

> Observable behavior is preserved by executable regression oracles; oracle
> strength is demonstrated by adversarial sensitivity. Mutation testing,
> planted negatives, property tests, and fault injection strengthen the
> oracle; they do not replace it, discover architecture, or independently
> prove correctness.

### The confidence ladder (cost-ordered, cumulative; no rung replaces a lower one)

1. Regression green — the floor: the encoded contract holds.
2. Red-then-green — sensitivity to one specific historical bug.
3. Planted negative — sensitivity to one designed invariant violation.
4. Differential mutation — systematically generated local semantic
   perturbations of the touched surface (`>=`→`>`, `and`→`or`, `==`→`!=`,
   dropped guard clauses), each re-running the suite. A surviving mutant is
   not a refactor failure; it is a measured oracle blind spot.

### Mutation contract (proposed MUTATION.SENSITIVITY.001 — not yet spec)

Mutation testing measures oracle sensitivity. It does not establish
architectural correctness, discover module boundaries, or independently
prove behavioral equivalence.

Required only when risk triggers it:

- **T1 — a refactor edits executable semantics inside a moved or owned
  definition** (conditionals, state transitions, normalization,
  authorization, retry, provider matching, evidence admission): differential
  mutation on the touched surface. Mechanical relocation — imports and paths
  only, zero semantic edits — requires none; the six clauses suffice.
- **T2 — a new or modified oracle/gate lands** (verification, authorization,
  state-transition, evidence-binding, provider-admission,
  scheduler-concurrency code): mutate the gate itself. The question is:
  when this gate is deliberately broken, does anything turn red?
- **T3 — first establishment of a failure-class guard**: mutate the guard's
  predicate (invert it, drop one classification, skip one AST shape) and
  require detection — upgrading the guard from one planted literal to
  sensitivity evidence.

Disposition, never score:

- Every surviving mutant is DISPOSITIONED, never required dead:
  `KILLED | EQUIVALENT | NON_OBSERVABLE_BY_CONTRACT | OUT_OF_SCOPE` — the
  last two with bounded machine-readable reasons, never free prose.
- No global mutation score may ever become a merge gate. A scalar objective
  gets optimized as a scalar (the line-count ratchet that acquired merge
  authority is this machine's own receipt); demanding all-mutants-killed
  produces pointless tests, implementation distortion, and mutation gaming.
- Differential scoping (changed semantic surfaces only) is an optimization
  only: it must not change the meaning of killed, survived, or error.

### The formal shape

```
RefactorSafe(B, C) :=
    Observable(B) == Observable(C)
    AND Sensitivity(C) >= Sensitivity(B)
    AND ArchitectureInvariants(C) == PASS
```

Observable is decided by the suite, physical feature oracles, provider
readback, and planted controls. Sensitivity by mutation, fault injection,
property tests, and negative controls. ArchitectureInvariants by ownership,
dependency direction, component surface, single-writer, and provider
authority. code-intel appears nowhere in RefactorSafe: it only reduces the
time to find the candidate seam. Its single necessity is R6, where the
zero-consumer claim of a deletion-type refactor is one architecture
invariant whose only sufficient evidence is the symbol graph plus the
open-issue ledger — evidence for one invariant in one refactor type, never
an oracle of equivalence.

### Sources (primary)

- Uncle Bob × Matt Pocock transcript — mutation mechanics; agents make the
  overnight run cheap: <https://sozai.app/transcript/uncle-bob-software-fundamentals-ai/>
- SwarmForge — cleaner (behavior-preserving) / architect (structure) /
  hardener (mutation) / QA (executable acceptance) are separate concerns:
  <https://github.com/unclebob/swarm-forge>
- mutate4java — differential mutation by declaration fingerprint:
  <https://github.com/unclebob/mutate4java>
- Acceptance Pipeline mutator spec — "Differential mutation is an
  optimization only": <https://github.com/unclebob/Acceptance-Pipeline-Specification/blob/main/mutator-spec.md>

## Applicability table (fill per atom)

| clause | applies? | control instantiated at |
|---|---|---|
| R1 I/O + effects | | |
| R2 blast radius | | |
| R3 admission surface | | |
| R4 intermediate states | | |
| R5 reversibility | | |
| R6 deletion proof | | |
| Sensitivity trigger T1–T3 | | |

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
deletions); for the same reason trigger T1 does not fire for it — mechanical
relocation adds no sensitivity obligation. Each clause graduates when some
atom's landed acceptance carries it as an executable control that a later
atom can cite by path. The sensitivity layer graduates when the mutation
contract lands in the specification with an executable differential-mutation
carrier; until then it binds nothing. The file retires when the six clauses
and the sensitivity layer all have landed carriers.

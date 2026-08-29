# Program DAG projection

> **N-class only.** Edges below are planning hypotheses derived from current source and Issue history. Provider state and completion receipts must be refreshed before scheduling.

## Edge semantics

Two edge types are mandatory.

```text
START edge
A must be available before B can safely begin.

COMPLETION edge
A's exact provider-landed receipt is required before B can truthfully complete.
```

A start edge never proves a completion edge. Every completion edge requires an exact subject and receipt boundary.

Optional or advisory edges are explicitly marked and may not silently become blockers.

## Top-level convergence DAG

```text
#109 Agent-friendly architecture carrier
  START/COMPLETE
        |
        v
#83 canonical document/procedure ownership cleanup
        |
        v
SPEC-CONVERGE atom
  system-v1 becomes canonical stable specification
  stable requirement identifiers and evolution law
        |
        v
ISSUE-CONTRACT atom
  typed requirement/dependency/write-boundary/body-digest
  structural completeness and readiness derivation
        |
        v
OPEN-ISSUE AUDIT
  add only missing typed facts
  reject or repair incomplete READY items such as #69
        |
        +-------------------------------+
        |                               |
        v                               v
Admission/concurrency lane          Verification lane
#82 typed provider deps            #19 oracle contract
#45 truthful daemon lease              |
#46 exact worktree provenance          v
#98 disjoint write boundaries       #20 feature-map canary
#99 exact open-PR exclusion             |
#100 invariant proof lock              v
        |                            #66 changed-code -> journeys -> oracle
        +---------------+---------------+
                        |
                        v
                       #4
          unattended single-Issue Golden Path
                        |
                        v
                       #21
        repeated failure -> executable rule
                        |
                        v
             requirement-status projection
                        |
                        v
                       #22
           bounded multi-Issue autonomous program
                        |
                        v
                    cross-repo canary
       authority follows each mutated target repository
```

The exact live readiness of these nodes is not stored here. Refresh from GitHub and target-local receipts.

## Context-closure producer/consumer DAG

```text
skills-shared method sources
  procedural-shadow-runtime
  agentic-tech-lead-orchestration
  spatial-loop-systems-engineering
        |
        | source-frozen method input
        v
skill-concerns#9
  context-closure-engineering producer candidate
        |
        | hermetic producer acceptance
        +-----------------------+
                                |
noodles#117                     |
  target-local N-class pack     |
        |                       |
        | consumer canary       |
        +-----------+-----------+
                    |
                    v
         producer admission convergence
                    |
                    v
       optional future pinned provider use
```

The consumer pack can be authored before general producer admission. It does not prove the reusable Skill is correct. Producer admission requires both hermetic controls and at least one exact consumer receipt.

## Current implementation families

### Landed substrate family

The following families have historical provider-landed evidence in repository Issues. Exact current code must still be read back.

```text
bootstrap control plane
trusted verifier isolation
branch protection and exact-head landing
runtime/provider pinning and discovery
schedule/execute task registration
Noodle-owned worktree-root admission
scheduler self-order rejection
provider-before-local-release containment
start-loop and script-mode recovery
repair re-entry into exact Noodle lane
control-checkout admission and reconcile fast-forward
pstack poteto-mode routing admission
semantic workflow-boundary checks
architecture health warnings separated from hard invariants
N-class docs/evidence-path restriction
```

These facts do not imply the full unattended, Feature Map, learning, concurrency, or cross-repository objectives are closed.

### Open verification family

```text
#19 verification-skill -> physical-oracle contract
  COMPLETION -> #20 executable Feature Map canary
#20
  COMPLETION -> #66 changed-code impact compiler
#19 + #20 + admission prerequisites
  COMPLETION -> #4 single-Issue canary
```

### Open concurrency family

```text
#45 I1 truthful daemon lease
  COMPLETION -> #46 I2 exact provenance
#82 typed Issue contract
  COMPLETION -> #98 I3 write-boundary admission
#46
  COMPLETION -> #99 I4 open-PR exclusion
#45 + #46 + #98 + #99
  COMPLETION -> #100 invariant proof lock
```

`max_concurrency` is not itself a correctness proof.

### Open autonomy and learning family

```text
#4 single-Issue provider-complete canary
  COMPLETION -> #21 one repeated-failure promotion
#4 + #21 + concurrency proof
  COMPLETION -> #22 three-Issue bounded program
```

### Open model/eval family

```text
provider-mutation denial
  -> hermetic fixtures/canonical roots
  -> baseline-owned mutation scoring
  -> frozen denominator and attempt budget
  -> distinct carrier support / behavioral admission / configured default
```

Model/judge results remain P-class behavioral evidence and cannot authorize repository reality.

## Molecular task-packet form

Every leaf packet emitted from this DAG must contain:

```text
subject
requirement or bounded hypothesis
START dependencies
COMPLETION dependencies
write boundary
positive control
planted negative
non-case
readback
residue
provider boundary
non-claims
convergence owner
```

A packet without a completion owner is not schedulable as a closure atom.

## Anti-drift checks

Before each scheduling epoch:

1. Refresh Issue body digest and provider state.
2. Refresh open PR/head correlation.
3. Recompute dependencies from provider truth.
4. Detect overlapping active write boundaries.
5. Detect nodes that are locally implemented but lack completion receipts.
6. Detect newly introduced Issues missing a DAG family or convergence owner.
7. Preserve unsupported and missing-source nodes rather than deleting them.

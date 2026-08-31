# noodles

A clean, small correctness/evidence layer around [Noodle](https://github.com/poteto/noodle), external pstack skills, Git, and GitHub.

`noodles` is not `skills-shared v2` and does not reimplement an Agent OS.

```text
GitHub Issue
    ↓
Noodle scheduler / orders / worktrees
    ↓
external pstack engineering routing          P
    ↓
smallest implementation atom
    ↓
noodles local gate + physical readback       L
    ↓
trusted GitHub exact-head lander             R
    ↓
merge + Issue closure readback
    ↓
Noodle machine reconciliation
```

## Bootstrap and normal entrypoint

One-time/operator bootstrap uses the CLI and lock files as the source of truth:

```bash
./noodles verify
./noodles runtime check
./noodles providers sync
./noodles github protect apply
```

After protection is installed, `./noodles start` is the normal unattended entrypoint. It verifies the repository, admits the locked Noodle runtime, synchronizes locked external Skills, proves configured skill-path discovery, audits GitHub protection, starts Noodle, re-enters failed `awaiting_land` lanes through the exact parked worktree, and reconciles completed provider landings without a routine Human Verifier.

For exact runtime/provider versions, commits, digests, and admitted paths, read `policy/runtime.lock.json` and `policy/providers.lock.json` or run the corresponding readback command. This README intentionally does not duplicate those mutable pin values.

## Authority

| Layer | Owns | Does not prove |
|---|---|---|
| Noodle | scheduling, isolated worktrees, process lifecycle | GitHub merge/Issue closure |
| pstack / Agent Skills | engineering playbooks and knowledge | correctness |
| `noodles` local gate | inventory, contracts, controls, readback, residue | provider state |
| GitHub | protected branch, exact-head merge, event/closure readback | model reasoning quality |

## Candidate-only retrieval

`policy/retrieval.lock.json` pins the grepai executable, its exact version and binary digest, the full
argv, the embed model digest, and both probe queries. `./noodles verify` gates that pin on every host,
including CI where grepai is absent.

`./noodles retrieval probe --index-root DIR` is the physical oracle. The index stays outside the
candidate tree because `grepai init` writes `.grepai/` and appends to `.gitignore`. The contract is
`query → candidate paths → direct source readback`: only paths and line ranges are taken from the tool
and the bytes are read back from the candidate tree. `hit != source truth`, `miss != absence`, and the
result authority is candidate-only — an empty result is reported as a missing, empty, or stale index,
never as absence.

## Issue and delivery contract

The parser and provider readback are the canonical Issue-contract owners. Inspect an exact Issue without copying its marker schema here:

```bash
./noodles issue validate ed3c/noodles#123
./noodles issue contract ed3c/noodles#123
```

The read-only contract exposes the exact provider body digest, declared dependencies, derived schedulability/reasons, and typed sections owned by the Issue/provider bytes. Dependency waiting is derived from predecessor provider truth; it is not mirrored in this README or stored as another status.

An implementation PR body is exactly:

```text
Refs ed3c/noodles#123
```

The Agent never uses an auto-close keyword and never merges or closes the Issue. The trusted lander does that only after exact-head readback.

## Commands

```bash
./noodles verify                         # deterministic repository gate
./noodles metrics --json                 # architecture-health disclosure
./noodles structural verify              # pinned tree-sitter ranges read back from real source bytes
./noodles runtime check                  # exact release/commit/asset/binary readback
./noodles runtime discover               # prove Noodle sees configured skill paths
./noodles providers sync                 # materialize exact locked providers
./noodles providers check                # detached/clean/head/tree/license/blob readback
./noodles retrieval probe --index-root DIR  # pinned grepai candidate paths + direct source readback
./noodles issue validate REPO#N          # exact Issue syntax/contract validation
./noodles issue contract REPO#N          # typed provider-backed Issue readback
./noodles issue handoff REPO#N --pr N    # exact PR/head/body + provider handoff
./noodles acceptance verify              # mandatory exact-head baseline acceptance
./noodles feature verify FEATURE         # additive specialized physical oracle
./noodles github protect audit
./noodles github protect apply
./noodles repair                         # exact failed awaiting_land repair lane
./noodles reconcile                      # provider-landed machine reconciliation
./noodles start                          # normal unattended entrypoint
```

Use command `--help`, the nearest Skill, and executable tests for step-level procedure. `AGENTS.md` is only the stable bootloader and pointer map.

## Why Noodle stays `supervised`

Noodle's local execution/review lifecycle is orchestration, not GitHub exact-head provider enforcement. `supervised` is a machine containment point: GitHub verifies/lands the exact head; `noodles reconcile` then fast-forwards the admitted local default branch and releases the corresponding Noodle state after provider readback.

## Fitness and architecture health

`policy/fitness.json` owns repository invariants and report thresholds. `./noodles verify` fails physical repository/authority violations. `./noodles metrics --json` reports architecture-health indicators such as module size, tracked surfaces, markdown share, line entropy, and test/code ratio; those indicators do not become correctness proof or force line golfing.

Resolve complexity pressure at a real seam. Before adding a registry, manager, router, or document layer, demonstrate a physical failure the nearest existing seam cannot close.

## Migration

`migrations/skills-shared/ledger.json` owns migration dispositions and evidence ceilings. It starts from observed claims rather than architecture prose. The admitted disposition vocabulary remains local to that ledger; this README does not duplicate its current capability state.

`ed3c/skills-shared` remains unchanged and is not a Golden Path runtime dependency.

## Current scope

The current provider policy admits `ed3c/noodles`. Cross-repository execution requires target-local Noodle/worktree authority, target-local physical oracles, trusted provider enforcement, and a live target-repository canary. The System Specification owns that stable rule; open Issues own implementation state.

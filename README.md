# noodles

A clean, small correctness/evidence layer around [Noodle](https://github.com/poteto/noodle), external pstack skills, Git, and GitHub.

`noodles` is not `skills-shared v2` and does not reimplement an Agent OS.

```text
GitHub Issue
    ↓
Noodle scheduler / orders / worktrees
    ↓
external pstack + engineering skills       P
    ↓
smallest implementation atom
    ↓
noodles local gate + physical readback      L
    ↓
trusted GitHub exact-head lander            R
    ↓
merge + Issue closure readback
    ↓
Noodle machine reconciliation
```

## One call order

```bash
./noodles verify
./noodles runtime check
./noodles providers sync
./noodles github protect apply   # one-time, requires an admin-capable gh token
./noodles start                  # one daemon generation
./noodles supervise              # unattended: heal, restart, rotate, cool down
```

This is the only bootstrap call order in the repository; `AGENTS.md` points here instead of keeping a second copy. The execute and schedule Skills own their own per-Issue step sequences, a different fact this file does not restate.

After protection is installed, `./noodles start` is the normal unattended entrypoint. It verifies the repository, admits the exact Noodle runtime binary, synchronizes exact external skill commits, proves configured skill-path discovery, audits GitHub protection, starts Noodle, re-enters failed `awaiting_land` lanes through the exact parked worktree to emit deterministic repair receipts, and reconciles completed provider landings without a Human Verifier. It fails closed unless local fitness, pinned providers, and GitHub protection readback all pass. `./noodles supervise` owns unattended operation per `AUTONOMY.SUPERVISED_RUNNER.001`; `./noodles supervise --heal-only` prints the heal receipt without spawning a daemon.

## Why Noodle stays `supervised`

Noodle `auto` merges a completed worktree into local `main`. That is useful orchestration, but it is not GitHub exact-head/provider enforcement. `supervised` is used as a machine containment point. The GitHub lander merges and closes; `noodles reconcile` then fast-forwards local `main` and releases the Noodle review automatically.

## Authority

| Layer | Owns | Does not prove |
|---|---|---|
| Noodle | scheduling, isolated worktrees, process lifecycle | GitHub merge/Issue closure |
| pstack / Agent Skills | engineering playbooks and knowledge | correctness |
| `noodles` local gate | inventory, contracts, controls, readback, residue | provider state |
| GitHub | protected branch, exact-head merge, event/closure readback | model reasoning quality |

## External skills

The admitted upstream Noodle runtime is pinned in `policy/runtime.lock.json` to an exact release tag, tag commit, platform asset digest, and installed binary digest. `./noodles runtime check` reads those values back from the live `poteto/noodle` release plus the local binary that `./noodles start` will execute.

Enabled providers are fetched outside Git history under `.noodle/providers/` and locked to immutable commits. `policy/providers.lock.json` is the sole owner of every source, commit, subpath, and admission digest, and `./noodles providers check` reads them back from the live remotes. This file copies none of those values: the copy that lived here had drifted to the wrong source repository while still showing a matching commit, which is exactly the failure a second writer produces.

`ed3c/skills-shared` appears in that lock as a disabled compatibility source, not a Golden Path dependency.

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

## Issue contract

`AGENTS.md` owns the marker list, `noodles.parse_issue_contract` is the parser of record, and `.github/ISSUE_TEMPLATE/repository-mutating-atom.md` is the authorable starting body. This file carries no marker example: a stale example reads as authoritative and produces a non-schedulable Issue.

`./noodles issue validate ed3c/noodles#123` rejects a drifted body against the parser, and `./noodles issue contract ed3c/noodles#123` returns the parsed contract read-only, with the provider body digest and schedulability derived from each declared predecessor's own landed/closed readback.

The implementation PR contains exactly:

```text
Refs ed3c/noodles#123
```

The Agent never uses an auto-close keyword and never merges or closes the Issue. The lander does that after exact-head readback.

## Commands

```bash
./noodles verify                    # deterministic repository gate
./noodles metrics --json            # entropy and quality disclosure
./noodles structural verify         # pinned tree-sitter ranges read back from the real source bytes
./noodles runtime check             # exact release/commit/asset/binary readback
./noodles runtime discover          # prove Noodle sees every configured skill path
./noodles providers sync            # exact detached provider checkouts
./noodles providers check           # HEAD/tree/license/blob/admission/SKILL/detached/clean readback
./noodles retrieval probe --index-root DIR  # pinned grepai candidate paths + direct source readback
./noodles issue validate REPO#N     # exact Issue contract
./noodles issue handoff REPO#N --pr N  # exact head/body + awaiting_land + blocking current-session handoff
./noodles github protect audit
./noodles github protect apply
./noodles repair                    # read failed awaiting_land PR lanes and emit exact repair receipts
./noodles reconcile                 # one machine reconciliation pass
./noodles start                     # unattended Noodle + reconciliation
```

## Fitness budget

The executable budget is `policy/fitness.json`. It limits tracked files, root surfaces, maximum file size, markdown share, entropy range, test/code ratio, external providers, workflows, dependency manifests, special Git modes, and runtime residue.

```bash
./noodles metrics --json
```

Metrics are N-class disclosure. `./noodles metrics --json` reports every metric and emits explicit architecture warnings/readback when report-only thresholds are exceeded.

`./noodles verify` fails only physical repository invariants. Provider count, workflow count, runtime dependency manifests, tracked residue, and the other exact repository contracts remain L-class gates. Architecture-health indicators such as module size, markdown share, line entropy, test/code ratio, and tracked-file count stay visible as warnings and do not become correctness proof by appearing in a failing gate.

Resolve module-size pressure at a real module seam. Do not delete useful newlines, compress readable code, or revert already useful seams merely to shrink a metric.

## Migration

`migrations/skills-shared/ledger.json` starts from observed claims, not architecture prose. The only dispositions are:

```text
MIGRATE | REVALIDATE | ADAPT_EXTERNAL | DROP | HOLD
```

The migration law is `NO PROSE MIGRATION`: evidence or a fresh experiment first, smallest atom second.

## Current scope

The v1 provider policy admits `ed3c/noodles`. Different repositories require target-local Noodle/worktree authority, trusted workflows, protection, token-scope readback, and a live canary. That expansion is intentionally held behind Issues rather than hidden behind an unproven “multi-repo” claim.

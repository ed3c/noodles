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
./noodles start
```

After protection is installed, `./noodles start` is the normal unattended entrypoint. It verifies the repository, admits the exact Noodle runtime binary, synchronizes exact external skill commits, proves configured skill-path discovery, audits GitHub protection, starts Noodle, re-enters failed `awaiting_land` lanes through the exact parked worktree to emit deterministic repair receipts, and reconciles completed provider landings without a Human Verifier.

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

Enabled providers are fetched outside Git history under `.noodle/providers/` and locked to immutable commits:

- Cursor pstack: `cursor/plugins@68836ddaf5697224520f1847d90cdb90ca8babaa`, `pstack/skills`;
- skill-concerns control-noodle: `ed3c/skill-concerns@c91dbd04d1997b2e0f77907c9c2a40f55b787107`, `skills/control-noodle`, admission tree digest `969111ff62cc68a1df82e036f2fe892e4ab9a850bbf2020f0f4253f6db866581`.

`ed3c/skills-shared` remains unchanged and is a disabled compatibility source, not a Golden Path dependency.

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

```text
<!-- noodles-role: repository-mutating-atom -->
<!-- noodles-target: ed3c/noodles -->
<!-- noodles-subject: ed3c/noodles#123 -->
<!-- noodles-state: ready -->
<!-- noodles-feature: verification-skill-oracle -->
<!-- noodles-depends-on: none -->
```

`./noodles issue contract ed3c/noodles#123` returns that contract read-only, with the provider body digest and schedulability derived from each declared predecessor's own landed/closed readback.

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

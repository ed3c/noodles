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
- Matt Pocock engineering skills: `mattpocock/skills@6654f6b60cd9d5be8b54c6fafe44346dabeb3b76`, `skills/engineering`.

`ed3c/skills-shared` remains unchanged and is a disabled compatibility source, not a Golden Path dependency.

## Issue contract

```text
<!-- noodles-role: repository-mutating-atom -->
<!-- noodles-target: ed3c/noodles -->
<!-- noodles-subject: ed3c/noodles#123 -->
<!-- noodles-state: ready -->
```

The implementation PR contains exactly:

```text
Refs ed3c/noodles#123
```

The Agent never uses an auto-close keyword and never merges or closes the Issue. The lander does that after exact-head readback.

## Commands

```bash
./noodles verify                    # deterministic repository gate
./noodles metrics --json            # entropy and quality disclosure
./noodles runtime check             # exact release/commit/asset/binary readback
./noodles runtime discover          # prove Noodle sees every configured skill path
./noodles providers sync            # exact detached provider checkouts
./noodles providers check           # HEAD/tree/license/SKILL/detached/clean readback
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

Metrics are N-class disclosure. Threshold enforcement by `verify` is L-class.

## Migration

`migrations/skills-shared/ledger.json` starts from observed claims, not architecture prose. The only dispositions are:

```text
MIGRATE | REVALIDATE | ADAPT_EXTERNAL | DROP | HOLD
```

The migration law is `NO PROSE MIGRATION`: evidence or a fresh experiment first, smallest atom second.

## Current scope

The v1 provider policy admits `ed3c/noodles`. Different repositories require target-local Noodle/worktree authority, trusted workflows, protection, token-scope readback, and a live canary. That expansion is intentionally held behind Issues rather than hidden behind an unproven “multi-repo” claim.

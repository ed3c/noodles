# noodles Agent-Friendly Architecture

> Rendered from `fixtures/noodles/context-pack.json`. Evidence bindings live in `fixtures/noodles/evidence-manifest.json`. This document is a compact Agent-facing projection, not an evidence database.

## Contributor context

Issue-solving Agents operate with narrow task context and should not require a complete model of noodles. The repository bounds document traversal and routes work toward the nearest executable authority. `[AF.CONTEXT_ROUTE:L]`

## Design objective

**Make the locally obvious noodles change the globally correct change without laundering guidance into verification authority.** `[AF.BEST_PATH:MIXED]`

## Architecture contract

1. **Conventional path first.** The supported path should require fewer decisions than a shortcut. `[AF.BEST_PATH:MIXED]`
2. **Mechanical rejection.** Forbidden structural or authority states should fail at deterministic/provider boundaries with supported-path diagnostics. `[AF.FORBIDDEN:L]`
3. **One admitted writer.** Every durable truth has one obvious owner and admitted mutation or transition surface. Coverage is partial where no executable duplicate-writer check exists. `[AF.WRITER:MIXED]`
4. **Isolation.** Local mutation is isolated from shared control surfaces. This is not evidence of Dune-style Feature-owned source topology. `[AF.ISOLATION:MIXED]`
5. **Explicit exceptions.** Bootstrap, recovery, and cross-boundary exceptions remain explicit, bounded, and evidence-gated. `[AF.EXCEPTIONS:MIXED]`

## Architecture carriers

- **Exact GitHub Issue** → one repository-mutating atom, target, lifecycle and declared boundaries. `[AF.BEST_PATH]`
- **Noodle-owned worktree** → mutation containment away from the shared control checkout. `[AF.ISOLATION]`
- **Nearest executable contract/test/oracle** → target-local deterministic acceptance rather than prose authority. `[AF.BEST_PATH, AF.FORBIDDEN]`
- **Durable owner/writer map** → separates intent, Issue lifecycle, scheduling/worktrees, candidate source, provider reality and reconciliation. `[AF.WRITER]`
- **Trusted GitHub verification and landing** → exact-head provider admission, merge and closure reality. `[AF.BEST_PATH, AF.FORBIDDEN]`

## Domain divergence from Dune

Dune's supplied reference shapes product source topology through Feature-owned folders, reserved-file discovery, a Client writer, typed Host boundary, and one-way package imports. Noodles primarily shapes Issue/worktree/component/evidence/provider topology. The shared invariant pressure is isolation and low-decision correct paths; the concrete architecture is not identical. `[AF.ISOLATION:MIXED]`

Noodles additionally separates probabilistic guidance, local deterministic evidence, provider-enforced reality and non-claims. Do not upgrade P/N evidence by repetition or consensus. `[AF.BEST_PATH:MIXED]`

## Do not infer

- AGENTS.md prose is mechanical enforcement.
- Phrase-presence tests prove runtime architecture correctness.
- All fitness thresholds are hard gates.
- `contract:*` makes unrestricted cross-component mutation the normal path.
- Noodles implements Dune Feature-owned folders or reserved-file auto-discovery.
- Local tests alone authorize merge or completion.
- One-writer is mechanically proven across arbitrary repository semantics.

## Best Path

```text
Exact Issue + declared component/feature
  -> Noodle-owned isolated worktree
  -> AGENTS.md
  -> system contract only when required
  -> issue-selected nearest executable contract/test
  -> STOP document traversal
  -> smallest independently useful atom
  -> mandatory baseline acceptance
  -> every applicable specialized physical oracle
  -> evidence bound to exact candidate head/tree
  -> trusted GitHub verification
  -> exact-head landing + provider readback
  -> reconciliation
```

## Evidence lookup rule

Every bracketed material claim resolves by `claim_id` through `context-pack.json` to one or more entries in `evidence-manifest.json`. Evidence authority must match the rendered ceiling. Missing or stale bindings degrade the claim to `UNKNOWN`; they are never repaired by analogy, semantic similarity, another Agent, or prose repetition.

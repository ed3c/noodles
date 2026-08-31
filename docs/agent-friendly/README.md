# Agent-friendly architecture — compile-input material (N-class)

Imported from `ed3c/ai-content-notes` PR #77 (branch `agent/noodles-agent-friendly-fixture`,
head `c461dd5e30630597b061dd6ad9ce5f4512bd3e49`). That PR was never merged; these bytes never
reached `ai-content-notes` `main`. `ed3c/ai-content-notes#83` separates the product lines and
retargets the noodles-subject files here, where the repository they describe can own them.

Everything in this directory is **N-class inventory**. It describes; it proves nothing. No
gate, no verifier, and no document route reads any of it. See AGENTS.md "Guarantee classes".

## Files

| File | What it is | Source blob |
|---|---|---|
| `context-pack.json` | Structured Context Pack: invariants, carriers, claims with authority ceilings, divergences, negative claims, Best Path. Compile **input**. | `eeb4ae9ebd07cc63fcd94d2488cbad2bd90bb90e` |
| `evidence-manifest.json` | Claim-to-evidence bindings: path, locator, evidence kind, authority class, stated limits. Compile **input**. | `d0027026b560c4950f649cc735f9e4c8a76bb568` |
| `agent-friendly-architecture.md` | The render produced from the two inputs above. **Pre-guard.** | `f9e8e35dc350d70463809d294acb2069089013a7` |

All three are byte-identical to their PR #77 originals: `git hash-object` on the copies
reproduces the blob SHAs above.

## The render is pre-guard, not a product

`agent-friendly-architecture.md` predates the rendered-contract guard that
`ed3c/skill-concerns` issue #19 admits. Run against that guard
(`skills/agent-friendly-architecture-compiler/scripts/validate_rendered_contract.py`,
candidate branch `agent/agent-friendly-architecture-compiler`) it exits `1` with 22 findings:

```text
10x missing required heading  (every one of ## Context Model .. ## Best Path Decision Rule)
 3x rendered hot path leaks black-box/compiler vocabulary
      (Noodle-owned, context-pack.json, evidence-manifest.json)
 8x load-bearing Best Path semantic missing
 1x rendered product exposes evidence/compiler machinery in the hot path
```

It is kept as a red-corpus artifact. Do not cite it as a compliant render, and do not treat
it as this repository's architecture document — `AGENTS.md` and `contracts/system-v1.md` are.

## Binding audit (this is where the material is stale)

`context-pack.json` and `evidence-manifest.json` both pin
`ed3c/noodles@b9d4a56d29fcdbf3f56f29411018a1afdcc43e05` (merge of `ed3c/noodles#234`,
2026-08-31), which is a real ancestor of `main`, not current `main`. The bindings were
resolved once, by hand, at import:

- 8 of the 9 evidence entries still resolve at current `main`: `E-DOC-ROUTE`, `E-SYSTEM-AF`,
  `E-VERIFY-REPO`, `E-ISSUE-PARSER`, `E-FITNESS`, `E-COMPONENTS`, `E-AGENTS`, `E-PROVIDER`.
- `E-SINGLE-PROFILE` is **wrong as written**: its `path` is `skill_contract.py`, but
  `validate_task_profile_single_source` is defined in `noodles.py`. It was wrong at the pinned
  revision too, so this is an authoring defect in the imported manifest, not drift.
- `context-pack.json`'s own `evidence_manifest` field still reads `"fixtures/noodles/evidence-manifest.json"`
  — its path inside the source PR before this retarget. The correct file is the sibling
  `evidence-manifest.json` in this same directory; `fixtures/noodles/` does not exist in this
  repository. This is the same class of import-time staleness as `E-SINGLE-PROFILE` above, not
  a new one. No validator reads this field (grep confirms no `.py` file references
  `evidence_manifest`), so nothing turns red on either the wrong pointer or its correction; the
  bytes stay frozen per this directory's own identity claim and the correction lives here
  instead.

Nothing recomputes this audit. It is a snapshot taken at import, and it decays: an evidence
entry that resolves today can point at a moved or deleted locator tomorrow with nothing
turning red. Re-resolve before relying on any binding.

## Non-claims

- These files are not enforcement, not a gate dependency, and not admission evidence.
- The authority classes (`P`/`L`/`R`/`N`, `MIXED`, `SOURCE`) are the source PR's own
  classification. Importing them here does not re-derive or upgrade any of them.
- No claim is made that the render ever passed a guard, or that a guard-passing render of
  this Context Pack exists.
- The pinned revision is historical. No current workflow run, merge, or provider readback is
  claimed by anything in this directory.
- The landing Issue for this material declares `noodles-feature: verification-skill-oracle` by
  precedent (matching issue #198), not because that oracle's code surface
  (`.agents/skills/execute/SKILL.md`) has any relationship to these files. A green
  `--feature verification-skill-oracle` run proves that unrelated invariant still holds; it is
  not a content-specific check of anything in this directory and should not be read as one.

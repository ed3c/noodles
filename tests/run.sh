#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# constraint: ed3c/noodles#313 - every atom's acceptance carries "zero residue (no .noodle/ runtime
# constraint: state written by any test outside its own temporary directory)", and the check lanes
# constraint: actually run is `git status --untracked-files=all`, which .gitignore's `.noodle/*` makes
# constraint: blind to precisely that residue. This observer can see it, so the clause is evaluated
# constraint: rather than reported satisfied unmeasured. It runs from an EXIT trap because residue is
# constraint: written whether the suite passes or not: under `set -e` a red suite would otherwise skip
# constraint: the check entirely, which is the same never-evaluated shape this atom exists to cure.
noodle_residue() {
  PYTHONPATH="$ROOT" python3 -c 'import sys
from pathlib import Path
import codex_isolation
print("\n".join(codex_isolation.noodle_runtime_residue(Path(sys.argv[1]), error_cls=SystemExit)))' "$ROOT"
}
# constraint: the clause forbids WRITING runtime state, so the two sets are differenced rather than
# constraint: compared: a suite that removes state a lane already had, or a daemon whose state is
# constraint: collected mid-run, is a disappearance and must not be reported as a write. Only added
# constraint: paths red; removed paths are named on stderr so the difference is never silent.
residue_gate() {
  local status=$?
  local after added removed
  after="$(noodle_residue)"
  added="$(comm -13 <(printf '%s\n' "$RESIDUE_BEFORE" | sort) <(printf '%s\n' "$after" | sort))"
  removed="$(comm -23 <(printf '%s\n' "$RESIDUE_BEFORE" | sort) <(printf '%s\n' "$after" | sort))"
  if [ -n "$removed" ]; then
    printf 'note: .noodle/ runtime state present before the suite is absent after it; this is a removal, not a write:\n%s\n' "$removed" >&2
  fi
  if [ -n "$added" ]; then
    printf 'zero-residue clause failed: the suite wrote .noodle/ runtime state into %s\n' "$ROOT" >&2
    printf 'added .noodle/ paths:\n%s\n' "$added" >&2
    exit 1
  fi
  exit "$status"
}
RESIDUE_BEFORE="$(noodle_residue)"
trap residue_gate EXIT
PYTHONPATH="$ROOT" python3 -m unittest discover -s tests -v
./noodles verify --json

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
residue_gate() {
  local status=$?
  local after
  after="$(noodle_residue)"
  if [ "$RESIDUE_BEFORE" != "$after" ]; then
    printf 'zero-residue clause failed: the suite wrote .noodle/ runtime state into %s\n' "$ROOT" >&2
    printf 'ignored .noodle/ paths before:\n%s\nignored .noodle/ paths after:\n%s\n' "$RESIDUE_BEFORE" "$after" >&2
    exit 1
  fi
  exit "$status"
}
RESIDUE_BEFORE="$(noodle_residue)"
trap residue_gate EXIT
PYTHONPATH="$ROOT" python3 -m unittest discover -s tests -v
./noodles verify --json

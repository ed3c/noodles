#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# constraint: ed3c/noodles#413 - the pinned lint toolchain, provisioned here rather than assumed.
# constraint: The pin is READ out of policy/ruff.toml and never restated: ruff's own
# constraint: `required-version` refuses to run under any other version, so a lane that silently
# constraint: carries a different ruff is a red rather than a differently-configured green.
# constraint: This is the candidate's own local filter, so provisioning belongs here and not only in
# constraint: a workflow step: `pull_request_target` runs the DEFAULT BRANCH's workflow, so on the
# constraint: PR that first introduces this gate no trusted step exists yet that could install it,
# constraint: and the candidate-self-tests job runs exactly this script. A developer lane is told
# constraint: the command instead of having its environment mutated underneath it; only CI, whose
# constraint: runner is disposable, installs unattended.
LINT_PIN="$(python3 -c 'import sys, tomllib; print(tomllib.load(open(sys.argv[1], "rb"))["required-version"])' "$ROOT/policy/ruff.toml")"
if ! ruff --version 2>/dev/null | grep -qx "ruff ${LINT_PIN#==}"; then
  if [ -n "${GITHUB_ACTIONS:-}" ]; then
    python3 -m pip install --quiet --disable-pip-version-check "ruff${LINT_PIN}"
    ruff --version | grep -qx "ruff ${LINT_PIN#==}"
  else
    printf 'lint toolchain missing: policy/ruff.toml pins ruff %s; install it with `python3 -m pip install "ruff%s"`\n' "${LINT_PIN#==}" "$LINT_PIN" >&2
    exit 1
  fi
fi
# constraint: ed3c/noodles#415 - the pinned type checker, provisioned on exactly the terms above and
# constraint: for exactly the same reasons. The pin is READ out of the trusted baseline's tool.version
# constraint: and never restated; unlike ruff, basedpyright has no `required-version` of its own, so
# constraint: `type_gate_errors` refuses a mismatched version itself and this check only makes the
# constraint: refusal arrive as a sentence a lane can act on rather than as a gate failure.
TYPE_PIN="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["tool"]["version"])' "$ROOT/policy/basedpyright-baseline.json")"
if ! basedpyright --version 2>/dev/null | grep -qx "basedpyright ${TYPE_PIN}"; then
  if [ -n "${GITHUB_ACTIONS:-}" ]; then
    python3 -m pip install --quiet --disable-pip-version-check "basedpyright==${TYPE_PIN}"
    basedpyright --version | grep -qx "basedpyright ${TYPE_PIN}"
  else
    printf 'type toolchain missing: policy/basedpyright-baseline.json pins basedpyright %s; install it with `python3 -m pip install "basedpyright==%s"`\n' "$TYPE_PIN" "$TYPE_PIN" >&2
    exit 1
  fi
fi
# constraint: the syntax and type gates run FIRST, against the policy this tree carries: a refusal
# constraint: discovered after the whole suite is lane-speed feedback nobody got. `./noodles verify`
# constraint: below runs both again through the CI-shaped call, and the two must agree.
PYTHONPATH="$ROOT" python3 -c 'import sys
from pathlib import Path
import noodles
root = Path(sys.argv[1])
paths = {relative for _, relative in noodles.tracked_entries(root)}
errors = [*noodles.lint_gate_errors(root, root, paths), *noodles.type_gate_errors(root, root, paths)]
print("\n".join(errors))
raise SystemExit(1 if errors else 0)' "$ROOT"
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

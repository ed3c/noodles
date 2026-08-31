"""Local reproduction of the trusted verify boundary, before the push.

`pull_request_target` runs the DEFAULT-BRANCH workflow and the DEFAULT-BRANCH test modules against
the candidate tree as data. A candidate that changes a value those modules pin therefore reds only
in CI - after the branch, the PR, and the wait - and the fix is never "try again" but the staged
transition (widen acceptance on the default branch, flip, retire).

This module runs that same step locally: the trusted tree is materialized from the git object
database at the default-branch tip, the candidate is the working tree, and both the env contract and
the command are read back from the trusted workflow rather than restated here.

Ceiling: the candidate is the working tree, and trusted modules that read the candidate through git
plumbing see only its committed state. Run the preview on a committed candidate.
"""
from __future__ import annotations
import os
import re
import shlex
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any
import github_protection
WORKSPACE_EXPRESSION = "${{ github.workspace }}"
STAGING_RECIPE = (
    "trusted-transition deadlock: the default-branch verifier rejects this candidate, so no rerun "
    "and no rebase can turn it green. Named supported path is the staged transition - widen "
    "acceptance on the default branch first, then flip the pinned value, then retire the widened "
    "acceptance."
)
# constraint: anchored on unittest's own outcome header shape (method then parenthesized dotted identity) because a failing test's diagnostic text routinely embeds its own "FAIL: ..." line, and a prefix scan reports those as pins CI would red
OUTCOME_LINE = re.compile(r"^(?:FAIL|ERROR): (\S+ \(\S+\).*)$")
DEFAULT_TIMEOUT = 1800.0


def _git(root: Path, argv: list[str], *, error_cls: type[Exception], what: str) -> str:
    completed = subprocess.run(["git", *argv], cwd=str(root), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if completed.returncode != 0:
        raise error_cls(f"trusted preview cannot {what}: {(completed.stderr or completed.stdout).strip()}")
    return completed.stdout.strip()


def _fetch_trusted_ref(root: Path, trusted_ref: str, *, error_cls: type[Exception]) -> str:
    """Refresh exactly the one remote-tracking ref the preview judges against.

    A ref with no remote component, or one naming a remote this clone does not have, is a distinct
    reported state rather than a silent no-op: the receipt must never let "ran against a stale local
    ref" look like "ran against the default-branch tip"."""
    remote, _, branch = trusted_ref.partition("/")
    if not branch:
        return f"skipped: {trusted_ref!r} names no remote"
    if remote not in _git(root, ["remote"], error_cls=error_cls, what="list git remotes").split():
        return f"skipped: no git remote named {remote!r}"
    _git(root, ["fetch", "--quiet", remote, f"+refs/heads/{branch}:refs/remotes/{remote}/{branch}"], error_cls=error_cls, what=f"fetch {trusted_ref}")
    return f"fetched {trusted_ref}"


def _materialize(root: Path, sha: str, destination: Path, *, error_cls: type[Exception]) -> None:
    destination.mkdir(parents=True)
    archive = destination.parent / "trusted.tar"
    _git(root, ["archive", "--format=tar", "-o", str(archive), sha], error_cls=error_cls, what=f"export the trusted tree at {sha}")
    with tarfile.open(archive) as bundle:
        bundle.extractall(destination, filter="data")
    archive.unlink()


def preview_trusted_verify(
    root: Path,
    *,
    trusted_ref: str = "origin/main",
    error_cls: type[Exception] = RuntimeError,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    root = root.resolve()
    fetch = _fetch_trusted_ref(root, trusted_ref, error_cls=error_cls)
    sha = _git(root, ["rev-parse", f"{trusted_ref}^{{commit}}"], error_cls=error_cls, what=f"resolve trusted ref {trusted_ref!r}")
    with tempfile.TemporaryDirectory(prefix="noodles-trusted-preview-") as name:
        workspace = Path(name).resolve()
        trusted = workspace / ".trusted"
        _materialize(root, sha, trusted, error_cls=error_cls)
        (workspace / ".candidate").symlink_to(root)
        env_contract, run_contract = github_protection.trusted_controls_contract(trusted, error_cls=error_cls)
        overrides = {key: value.replace(WORKSPACE_EXPRESSION, str(workspace)) for key, value in env_contract.items()}
        env = os.environ.copy()
        env.update(overrides)
        argv = shlex.split(run_contract)
        if argv and argv[0] == "python3":
            argv[0] = sys.executable
        try:
            completed = subprocess.run(argv, cwd=str(workspace), env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise error_cls(f"trusted preview could not execute the trusted controls command {run_contract!r}: {exc}") from exc
    output = completed.stdout or ""
    would_red = sorted({match.group(1).strip() for match in (OUTCOME_LINE.match(line) for line in output.splitlines()) if match})
    ok = completed.returncode == 0
    return {
        "ok": ok,
        "trusted_ref": trusted_ref,
        "trusted_sha": sha,
        "fetch": fetch,
        "candidate_root": str(root),
        "env_contract": env_contract,
        "env": overrides,
        "command": run_contract,
        "returncode": completed.returncode,
        "would_red": would_red,
        "diagnostic": None if ok else STAGING_RECIPE,
        "tail": output.splitlines()[-20:],
    }

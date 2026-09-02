"""Deterministic, provider-agnostic construction of a three-member Git batch."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
MEMBER_COUNT = 3
OBJECT_ID_RE = re.compile(r"[0-9a-f]{40,64}")
IDENTITY_ENV = {
    "GIT_AUTHOR_NAME": "noodles verified batch",
    "GIT_AUTHOR_EMAIL": "verified-batch@invalid",
    "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z",
    "GIT_COMMITTER_NAME": "noodles verified batch",
    "GIT_COMMITTER_EMAIL": "verified-batch@invalid",
    "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z",
}


class BatchError(ValueError):
    """The supplied batch cannot be represented by the declared exact identity."""


@dataclass(frozen=True)
class BatchMember:
    pr_number: int
    head_sha: str


def canonical_manifest(manifest: Mapping[str, Any]) -> str:
    """Return the one portable byte representation of a batch manifest."""
    return json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"


def _git(repository: Path, *arguments: str, env: Mapping[str, str] | None = None) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=str(repository),
        env=None if env is None else {**os.environ, **env},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
        raise BatchError(f"git {' '.join(arguments)} failed: {detail}")
    return completed.stdout.strip()


def _commit(repository: Path, object_id: str) -> str:
    if not isinstance(object_id, str) or OBJECT_ID_RE.fullmatch(object_id) is None:
        raise BatchError(f"invalid object id: {object_id!r}")
    resolved = _git(repository, "rev-parse", "--verify", f"{object_id}^{{commit}}")
    if resolved != object_id:
        raise BatchError(f"object id is not an exact commit: {object_id!r}")
    return resolved


def _members(repository: Path, members: Sequence[BatchMember]) -> tuple[BatchMember, ...]:
    if len(members) != MEMBER_COUNT:
        raise BatchError(f"verified batch requires exactly {MEMBER_COUNT} members")
    normalized: list[BatchMember] = []
    for member in members:
        if not isinstance(member, BatchMember):
            raise BatchError("members must be BatchMember records")
        if isinstance(member.pr_number, bool) or not isinstance(member.pr_number, int) or member.pr_number <= 0:
            raise BatchError(f"invalid PR number: {member.pr_number!r}")
        normalized.append(BatchMember(member.pr_number, _commit(repository, member.head_sha)))
    if len({member.pr_number for member in normalized}) != MEMBER_COUNT:
        raise BatchError("duplicate PR number")
    if len({member.head_sha for member in normalized}) != MEMBER_COUNT:
        raise BatchError("duplicate member head")
    return tuple(normalized)


def _message(position: int, member: BatchMember) -> str:
    return f"noodles verified batch v1\n\nposition {position}\npr {member.pr_number}\nhead {member.head_sha}\n"


def construct_batch(repository: str | Path, base_sha: str, members: Sequence[BatchMember]) -> dict[str, Any]:
    """Construct immutable Git objects without updating a ref or repository state file."""
    root = Path(repository).resolve()
    base = _commit(root, base_sha)
    ordered = _members(root, members)
    current = base
    integrations: list[dict[str, Any]] = []
    for position, member in enumerate(ordered, start=1):
        tree = _git(root, "merge-tree", "--write-tree", current, member.head_sha)
        if OBJECT_ID_RE.fullmatch(tree) is None:
            raise BatchError(f"merge-tree returned a non-tree identity: {tree!r}")
        message = _message(position, member)
        candidate = _commit_tree(root, tree, current, member.head_sha, message)
        integrations.append(
            {
                "position": position,
                "pr_number": member.pr_number,
                "head_sha": member.head_sha,
                "commit_sha": candidate,
                "tree_sha": tree,
                "parents": [current, member.head_sha],
            }
        )
        current = candidate
    return {
        "schema_version": SCHEMA_VERSION,
        "base_sha": base,
        "members": [{"pr_number": member.pr_number, "head_sha": member.head_sha} for member in ordered],
        "integrations": integrations,
        "batch_sha": current,
    }


def _commit_tree(repository: Path, tree: str, first_parent: str, second_parent: str, message: str) -> str:
    completed = subprocess.run(
        ["git", "commit-tree", tree, "-p", first_parent, "-p", second_parent],
        cwd=str(repository),
        env={**os.environ, **IDENTITY_ENV},
        input=message,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise BatchError(f"git commit-tree failed: {completed.stderr.strip() or completed.stdout.strip()}")
    candidate = completed.stdout.strip()
    if OBJECT_ID_RE.fullmatch(candidate) is None:
        raise BatchError(f"commit-tree returned an invalid identity: {candidate!r}")
    return candidate


def verify_candidate_identity(repository: str | Path, manifest: Mapping[str, Any]) -> None:
    """Fail unless object bytes reconstruct the manifest's exact ordered identity."""
    if set(manifest) != {"schema_version", "base_sha", "members", "integrations", "batch_sha"}:
        raise BatchError("manifest fields are not canonical")
    if manifest["schema_version"] != SCHEMA_VERSION:
        raise BatchError("unsupported manifest schema")
    raw_members = manifest["members"]
    if not isinstance(raw_members, list):
        raise BatchError("manifest members must be a list")
    members = [
        BatchMember(member["pr_number"], member["head_sha"])
        if isinstance(member, dict) and set(member) == {"pr_number", "head_sha"}
        else _invalid_member()
        for member in raw_members
    ]
    reconstructed = construct_batch(repository, manifest["base_sha"], members)
    if canonical_manifest(reconstructed) != canonical_manifest(manifest):
        raise BatchError("manifest does not match Git object readback")
    root = Path(repository).resolve()
    for integration in reconstructed["integrations"]:
        commit = integration["commit_sha"]
        parents = _git(root, "rev-list", "--parents", "-n", "1", commit).split()
        if parents != [commit, *integration["parents"]]:
            raise BatchError(f"parent graph mismatch at position {integration['position']}")
        if _git(root, "show", "-s", "--format=%T", commit) != integration["tree_sha"]:
            raise BatchError(f"tree mismatch at position {integration['position']}")


def _invalid_member() -> BatchMember:
    raise BatchError("manifest member fields are not canonical")

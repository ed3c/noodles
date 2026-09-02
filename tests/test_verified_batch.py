from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import verified_batch


FIXED_ENV = {
    "GIT_AUTHOR_NAME": "fixture",
    "GIT_AUTHOR_EMAIL": "fixture@invalid",
    "GIT_AUTHOR_DATE": "2001-01-01T00:00:00Z",
    "GIT_COMMITTER_NAME": "fixture",
    "GIT_COMMITTER_EMAIL": "fixture@invalid",
    "GIT_COMMITTER_DATE": "2001-01-01T00:00:00Z",
}


def git(root: Path, *arguments: str, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=str(root),
        env={**os.environ, **FIXED_ENV, **(env or {})},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout)
    return completed.stdout.strip()


class VerifiedBatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="noodles-verified-batch-")
        self.root = Path(self.temp.name) / "origin"
        self.root.mkdir()
        git(self.root, "init", "-q")
        git(self.root, "config", "user.name", "fixture")
        git(self.root, "config", "user.email", "fixture@invalid")
        (self.root / "base.txt").write_text("base\n", encoding="utf-8")
        git(self.root, "add", "base.txt")
        git(self.root, "commit", "-q", "-m", "base")
        self.base = git(self.root, "rev-parse", "HEAD")
        self.heads: list[str] = []
        for position in range(1, 4):
            git(self.root, "checkout", "-q", "-B", f"member-{position}", self.base)
            (self.root / f"member-{position}.txt").write_text(f"member {position}\n", encoding="utf-8")
            git(self.root, "add", f"member-{position}.txt")
            git(
                self.root,
                "commit",
                "-q",
                "-m",
                f"member {position}",
                env={
                    "GIT_AUTHOR_DATE": f"2001-01-0{position + 1}T00:00:00Z",
                    "GIT_COMMITTER_DATE": f"2001-01-0{position + 1}T00:00:00Z",
                },
            )
            self.heads.append(git(self.root, "rev-parse", "HEAD"))
        git(self.root, "checkout", "-q", "--detach", self.base)
        self.members = [verified_batch.BatchMember(index, head) for index, head in enumerate(self.heads, 101)]

    def tearDown(self) -> None:
        self.temp.cleanup()

    def refs(self, root: Path | None = None) -> str:
        return git(root or self.root, "for-each-ref", "--format=%(refname) %(objectname)")

    def test_constructs_same_identity_in_independent_repositories_without_ref_residue(self) -> None:
        before = self.refs()
        first = verified_batch.construct_batch(self.root, self.base, self.members)
        verified_batch.verify_candidate_identity(self.root, first)
        self.assertEqual(before, self.refs())

        replica = Path(self.temp.name) / "replica"
        shutil.copytree(self.root, replica)
        replica_before = self.refs(replica)
        second = verified_batch.construct_batch(replica, self.base, self.members)
        verified_batch.verify_candidate_identity(replica, second)

        self.assertEqual(verified_batch.canonical_manifest(first), verified_batch.canonical_manifest(second))
        self.assertEqual(first["batch_sha"], second["batch_sha"])
        self.assertEqual(replica_before, self.refs(replica))
        self.assertEqual(
            [first["base_sha"], *self.heads],
            [first["integrations"][0]["parents"][0]]
            + [integration["parents"][1] for integration in first["integrations"]],
        )

    def test_rejects_wrong_count_duplicate_pr_and_duplicate_head(self) -> None:
        with self.assertRaisesRegex(verified_batch.BatchError, "exactly 3"):
            verified_batch.construct_batch(self.root, self.base, self.members[:2])
        duplicate_pr = [self.members[0], verified_batch.BatchMember(101, self.heads[1]), self.members[2]]
        with self.assertRaisesRegex(verified_batch.BatchError, "duplicate PR"):
            verified_batch.construct_batch(self.root, self.base, duplicate_pr)
        duplicate_head = [self.members[0], self.members[1], verified_batch.BatchMember(103, self.heads[1])]
        with self.assertRaisesRegex(verified_batch.BatchError, "duplicate member head"):
            verified_batch.construct_batch(self.root, self.base, duplicate_head)

    def test_reordered_member_changes_identity_and_stale_manifest_fails(self) -> None:
        first = verified_batch.construct_batch(self.root, self.base, self.members)
        reordered = verified_batch.construct_batch(self.root, self.base, [self.members[1], self.members[0], self.members[2]])
        self.assertNotEqual(first["batch_sha"], reordered["batch_sha"])

        stale = deepcopy(first)
        stale["batch_sha"] = reordered["batch_sha"]
        with self.assertRaisesRegex(verified_batch.BatchError, "does not match"):
            verified_batch.verify_candidate_identity(self.root, stale)

    def test_rejects_wrong_base_and_missing_object(self) -> None:
        manifest = verified_batch.construct_batch(self.root, self.base, self.members)
        wrong_base = deepcopy(manifest)
        wrong_base["base_sha"] = self.heads[0]
        with self.assertRaises(verified_batch.BatchError):
            verified_batch.verify_candidate_identity(self.root, wrong_base)
        missing = "0" * len(self.base)
        with self.assertRaises(verified_batch.BatchError):
            verified_batch.construct_batch(self.root, missing, self.members)

    def test_mechanical_conflict_fails_without_ref_residue(self) -> None:
        conflict_heads: list[str] = []
        for position, value in enumerate(("one\n", "two\n", "three\n"), start=1):
            git(self.root, "checkout", "-q", "-B", f"conflict-{position}", self.base)
            (self.root / "base.txt").write_text(value, encoding="utf-8")
            git(self.root, "add", "base.txt")
            git(
                self.root,
                "commit",
                "-q",
                "-m",
                f"conflict {position}",
                env={
                    "GIT_AUTHOR_DATE": f"2001-02-0{position}T00:00:00Z",
                    "GIT_COMMITTER_DATE": f"2001-02-0{position}T00:00:00Z",
                },
            )
            conflict_heads.append(git(self.root, "rev-parse", "HEAD"))
        git(self.root, "checkout", "-q", "--detach", self.base)
        members = [verified_batch.BatchMember(index, head) for index, head in enumerate(conflict_heads, 201)]
        before = self.refs()
        with self.assertRaisesRegex(verified_batch.BatchError, "merge-tree"):
            verified_batch.construct_batch(self.root, self.base, members)
        self.assertEqual(before, self.refs())


if __name__ == "__main__":
    unittest.main()

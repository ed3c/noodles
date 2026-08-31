from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from unittest import mock

import noodles
from tests.support import CANDIDATE_ROOT, cmd, execute_branch_name, handoff_fixture


class ExecuteProvenanceAdmissionTests(unittest.TestCase):
    """ed3c/noodles#46: one order binds one session, one registered worktree, one non-default branch, one reconciled base."""

    SUBJECT = "ed3c/noodles#33"

    def setUp(self) -> None:
        self.temp, self.root, self.binary, self.session_id = handoff_fixture(CANDIDATE_ROOT, self.SUBJECT)
        self.addCleanup(self.temp.cleanup)
        self.root = self.root.resolve()
        self.temp_dir = Path(self.temp.name).resolve()
        self.branch = execute_branch_name(self.SUBJECT)
        self.head = cmd(["git", "rev-parse", "HEAD"], self.root)
        self.base = cmd(["git", "rev-parse", "main"], self.root)
        self.sessions = self.root / ".noodle" / "sessions"

    def admit(self, **overrides: object) -> dict:
        payload = {
            "root": self.root,
            "subject_value": self.SUBJECT,
            "session_id": self.session_id,
            "head": self.head,
            "base_sha": self.base,
            "default_branch": "main",
        }
        payload.update(overrides)
        return noodles.execute_provenance_admission(**payload)

    def reject(self, pattern: str, **overrides: object) -> str:
        with self.assertRaisesRegex(noodles.GateError, pattern) as raised:
            self.admit(**overrides)
        return str(raised.exception)

    def write_session(self, name: str, worktree_path: Path, subject: str) -> None:
        session = self.sessions / name
        session.mkdir(parents=True)
        (session / "spawn.json").write_text(json.dumps({
            "worktree_path": str(worktree_path),
            "worktree_name": worktree_path.name,
        }))
        (session / "events.ndjson").write_text(json.dumps({
            "type": "action",
            "payload": {"message": f"[order:{subject}] fixture"},
            "timestamp": "2026-08-29T00:00:00Z",
            "session_id": name,
        }) + "\n")

    def test_positive_readback_binds_every_provenance_field(self) -> None:
        receipt = self.admit()
        self.assertEqual(receipt, {
            "order": self.SUBJECT,
            "session_id": self.session_id,
            "session_spawn": str(self.sessions / self.session_id / "spawn.json"),
            "repository": "ed3c/noodles",
            "git_common_dir": str(self.root / ".git"),
            "worktree_path": str(self.root),
            "branch": self.branch,
            "default_branch": "main",
            "candidate_head": self.head,
            "base_sha": self.base,
        })
        self.assertNotEqual(receipt["candidate_head"], receipt["base_sha"])

    def test_default_branch_checkout_is_refused(self) -> None:
        cmd(["git", "checkout", "-q", "main"], self.root)
        self.reject("refuses default branch main")

    def test_detached_head_is_refused(self) -> None:
        cmd(["git", "checkout", "-q", "--detach"], self.root)
        self.reject("detached HEAD")

    def test_branch_that_is_not_the_exact_order_branch_is_refused(self) -> None:
        cmd(["git", "checkout", "-q", "-b", "ed3c-noodles-34-0-execute"], self.root)
        self.reject(f"execute branch ed3c-noodles-34-0-execute != exact order branch {self.branch}")

    def test_same_branch_in_a_second_registered_worktree_is_refused(self) -> None:
        duplicate = self.temp_dir / "duplicate"
        cmd(["git", "worktree", "add", "--force", "-q", str(duplicate), self.branch], self.root)
        self.reject(f"execute branch {self.branch} is already checked out in registered worktree {duplicate}")

    def test_foreign_git_common_directory_is_refused(self) -> None:
        foreign = self.temp_dir / "foreign"
        (foreign / ".noodle").mkdir(parents=True)
        session = self.sessions / self.session_id
        target = foreign / ".noodle" / "sessions" / self.session_id
        target.mkdir(parents=True)
        (target / "spawn.json").write_text((session / "spawn.json").read_text())
        (target / "events.ndjson").write_text((session / "events.ndjson").read_text())
        with mock.patch.dict("os.environ", {"NOODLE_PROJECT_DIR": str(foreign)}, clear=False):
            self.reject(f"is foreign: git common directory .* is outside Noodle project {foreign}")

    def test_worktree_path_reused_by_a_second_session_is_refused(self) -> None:
        self.write_session("reused-path-session", self.root, self.SUBJECT)
        self.reject("registered to sessions .* and reused-path-session; provenance is ambiguous")

    def test_wrong_session_is_refused_by_the_reused_handoff_session_boundary(self) -> None:
        self.write_session("elsewhere-session", self.temp_dir / "elsewhere", self.SUBJECT)
        self.reject("!= current worktree", session_id="elsewhere-session")
        self.reject("current Noodle session does not exist", session_id="missing-session")

    def test_head_drift_under_the_admitted_candidate_head_is_refused(self) -> None:
        cmd(["git", "commit", "-q", "--allow-empty", "-m", "drift"], self.root)
        drifted = cmd(["git", "rev-parse", "HEAD"], self.root)
        self.assertNotEqual(drifted, self.head)
        self.reject(f"execute worktree HEAD {drifted} != admitted candidate head {self.head}")

    def test_stale_base_not_contained_by_the_candidate_branch_is_refused(self) -> None:
        cmd(["git", "checkout", "-q", "-b", "stale-base", "main"], self.root)
        cmd(["git", "commit", "-q", "--allow-empty", "-m", "stale base"], self.root)
        stale = cmd(["git", "rev-parse", "HEAD"], self.root)
        cmd(["git", "checkout", "-q", self.branch], self.root)
        self.reject(f"does not contain admitted provider base {stale}", base_sha=stale)
        self.reject("requires an exact reconciled provider base", base_sha="")

    def test_base_object_not_present_in_worktree_is_distinguished_from_not_an_ancestor(self) -> None:
        missing = "deadbeef" * 5
        self.reject(f"cannot verify provider base {missing} in worktree {self.root}", base_sha=missing)

    def test_prunable_stale_worktree_entry_does_not_block_the_branch(self) -> None:
        duplicate = self.temp_dir / "duplicate"
        cmd(["git", "worktree", "add", "--force", "-q", str(duplicate), self.branch], self.root)
        shutil.rmtree(duplicate)
        receipt = self.admit()
        self.assertEqual(receipt["branch"], self.branch)

    def test_unreadable_spawn_record_in_an_unrelated_session_fails_the_handoff_closed(self) -> None:
        unrelated = self.sessions / "unrelated-session"
        unrelated.mkdir(parents=True)
        (unrelated / "spawn.json").write_text("not json")
        self.reject(r"cannot read JSON .*unrelated-session/spawn\.json")

    def test_two_disjoint_orders_pass_only_with_distinct_provenance(self) -> None:
        other_subject = "ed3c/noodles#34"
        other_branch = execute_branch_name(other_subject)
        other_root = self.temp_dir / other_branch
        cmd(["git", "worktree", "add", "-q", "-b", other_branch, str(other_root), "main"], self.root)
        self.write_session("session-34", other_root, other_subject)
        other_head = cmd(["git", "rev-parse", "HEAD"], other_root)

        mine = self.admit()
        theirs = noodles.execute_provenance_admission(
            other_root, other_subject, "session-34", other_head, self.base, "main"
        )
        for field in ("order", "session_id", "worktree_path", "branch"):
            self.assertNotEqual(mine[field], theirs[field])
        self.assertEqual(mine["git_common_dir"], theirs["git_common_dir"])

        with self.assertRaisesRegex(noodles.GateError, "!= current worktree"):
            noodles.execute_provenance_admission(
                other_root, other_subject, self.session_id, other_head, self.base, "main"
            )
        with self.assertRaisesRegex(noodles.GateError, f"is not tied to exact order {other_subject}"):
            noodles.execute_provenance_admission(
                self.root, other_subject, self.session_id, self.head, self.base, "main"
            )
        with self.assertRaisesRegex(noodles.GateError, "!= current worktree"):
            noodles.execute_provenance_admission(
                self.root, self.SUBJECT, "session-34", self.head, self.base, "main"
            )


if __name__ == "__main__":
    unittest.main()

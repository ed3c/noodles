from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

import noodles
from tests.support import CANDIDATE_ROOT, cmd, handoff_fixture


class RepairTests(unittest.TestCase):
    SUBJECT = "ed3c/noodles#33"
    WORKTREE_NAME = "ed3c-noodles-33-0-execute"

    def setUp(self) -> None:
        self.temp, self.root, self.binary, self.session_id = handoff_fixture(
            CANDIDATE_ROOT,
            subject=self.SUBJECT,
            worktree_name=self.WORKTREE_NAME,
        )
        self.addCleanup(self.temp.cleanup)
        self.head = cmd(["git", "rev-parse", "HEAD"], self.root)
        self.review = {
            "order_id": self.SUBJECT,
            "session_id": self.session_id,
            "worktree_name": self.WORKTREE_NAME,
            "worktree_path": str(self.root),
        }

    def issue_body(self, state: str = "awaiting_land") -> str:
        return (
            "<!-- noodles-role: repository-mutating-atom -->\n"
            "<!-- noodles-target: ed3c/noodles -->\n"
            f"<!-- noodles-subject: {self.SUBJECT} -->\n"
            f"<!-- noodles-state: {state} -->\n"
        )

    def pr(self, **overrides: object) -> dict:
        payload = {
            "number": 44,
            "state": "open",
            "merged": False,
            "draft": False,
            "body": f"Refs {self.SUBJECT}",
            "head": {"sha": self.head, "ref": self.WORKTREE_NAME},
            "base": {"ref": "main"},
        }
        payload.update(overrides)
        return payload

    def gh_payloads(self, *, pr: dict | None = None, issue_state: str = "open", contract_state: str = "awaiting_land") -> dict[str, object]:
        pr_payload = pr or self.pr()
        return {
            "repos/ed3c/noodles/pulls?state=open&per_page=100": [pr_payload],
            "repos/ed3c/noodles/issues/33": {"number": 33, "state": issue_state, "body": self.issue_body(contract_state)},
            f"repos/ed3c/noodles/actions/runs?head_sha={self.head}&per_page=100": {
                "workflow_runs": [{
                    "id": 777,
                    "name": "verify",
                    "path": ".github/workflows/verify.yml",
                    "event": "pull_request_target",
                    "status": "completed",
                    "conclusion": "failure",
                    "head_sha": self.head,
                    "html_url": "https://example.invalid/runs/777",
                    "workflow_id": 11,
                }]
            },
            "repos/ed3c/noodles/actions/runs/777": {
                "id": 777,
                "name": "verify",
                "path": ".github/workflows/verify.yml",
                "event": "pull_request_target",
                "status": "completed",
                "conclusion": "failure",
                "head_sha": self.head,
                "html_url": "https://example.invalid/runs/777",
                "workflow_id": 11,
            },
            "repos/ed3c/noodles": {"full_name": "ed3c/noodles", "default_branch": "main"},
            "repos/ed3c/noodles/actions/workflows/verify.yml": {
                "id": 11,
                "name": "verify",
                "path": ".github/workflows/verify.yml",
                "state": "active",
            },
            "repos/ed3c/noodles/actions/runs/777/jobs?per_page=100": {
                "jobs": [{
                    "id": 99073595935,
                    "name": "candidate-self-tests",
                    "status": "completed",
                    "conclusion": "failure",
                    "html_url": "https://example.invalid/jobs/99073595935",
                }]
            },
        }

    def test_positive_repair_receipt_reenters_exact_worktree_and_is_idempotent(self) -> None:
        events_path = self.root / ".noodle" / "sessions" / self.session_id / "events.ndjson"
        payloads = self.gh_payloads()
        with mock.patch.object(noodles, "http_json", return_value={"pending_reviews": [self.review]}), \
             mock.patch.object(noodles, "gh_api", side_effect=lambda endpoint, **_kwargs: payloads[endpoint]):
            first = noodles.repair_pending_reviews(self.root, "http://noodle.test")
            second = noodles.repair_pending_reviews(self.root, "http://noodle.test")

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        receipt = first[0]
        self.assertEqual(receipt["failed_workflow_run"]["id"], 777)
        self.assertEqual(receipt["failed_job"]["id"], 99073595935)
        self.assertEqual(receipt["session"]["id"], self.session_id)
        self.assertEqual(receipt["session"]["worktree_name"], self.WORKTREE_NAME)
        written = json.loads(Path(receipt["repair_receipt_path"]).read_text())
        self.assertEqual(written["head_sha"], self.head)
        events = [json.loads(line) for line in events_path.read_text().splitlines()]
        repair_events = [item for item in events if item["type"] == "repair_receipt"]
        self.assertEqual(len(repair_events), 1)
        self.assertEqual(repair_events[0]["payload"]["head_sha"], self.head)

    def test_changed_worktree_head_fails_closed(self) -> None:
        readme = self.root / "README.md"
        readme.write_text(readme.read_text() + "\nrepair drift\n")
        cmd(["git", "add", "README.md"], self.root)
        cmd(["git", "commit", "-q", "-m", "drift"], self.root)
        pr = self.pr()
        payloads = self.gh_payloads(pr=pr)
        with mock.patch.object(noodles, "gh_api", side_effect=lambda endpoint, **_kwargs: payloads[endpoint]):
            with self.assertRaisesRegex(noodles.GateError, "worktree head"):
                noodles.repair_review(self.root, self.SUBJECT, self.review, pr)

    def test_missing_failed_check_fails_closed(self) -> None:
        pr = self.pr()
        payloads = self.gh_payloads(pr=pr)
        payloads[f"repos/ed3c/noodles/actions/runs?head_sha={self.head}&per_page=100"] = {"workflow_runs": []}
        with mock.patch.object(noodles, "gh_api", side_effect=lambda endpoint, **_kwargs: payloads[endpoint]):
            with self.assertRaisesRegex(noodles.GateError, "no completed failed workflow run"):
                noodles.repair_review(self.root, self.SUBJECT, self.review, pr)

    def test_already_landed_issue_fails_closed(self) -> None:
        pr = self.pr()
        payloads = self.gh_payloads(pr=pr, issue_state="closed", contract_state="landed")
        with mock.patch.object(noodles, "gh_api", side_effect=lambda endpoint, **_kwargs: payloads[endpoint]):
            with self.assertRaisesRegex(noodles.GateError, "open and awaiting_land"):
                noodles.repair_review(self.root, self.SUBJECT, self.review, pr)

    def test_stale_session_identity_fails_closed(self) -> None:
        review = dict(self.review)
        review["session_id"] = "wrong-session"
        pr = self.pr()
        payloads = self.gh_payloads(pr=pr)
        with mock.patch.object(noodles, "gh_api", side_effect=lambda endpoint, **_kwargs: payloads[endpoint]):
            with self.assertRaisesRegex(noodles.GateError, "session"):
                noodles.repair_review(self.root, self.SUBJECT, review, pr)

    def test_repair_attempts_exhausted_emits_escalation(self) -> None:
        events_path = self.root / ".noodle" / "sessions" / self.session_id / "events.ndjson"
        with events_path.open("a", encoding="utf-8") as handle:
            for index in range(noodles.REPAIR_MAX_ATTEMPTS):
                handle.write(json.dumps({
                    "type": "repair_receipt",
                    "payload": {
                        "issue_subject": self.SUBJECT,
                        "pr_number": 44,
                        "head_sha": f"{index + 1:040x}",
                    },
                    "timestamp": "2026-08-29T00:00:00Z",
                    "session_id": self.session_id,
                }) + "\n")
        pr = self.pr()
        payloads = self.gh_payloads(pr=pr)
        with mock.patch.object(noodles, "gh_api", side_effect=lambda endpoint, **_kwargs: payloads[endpoint]):
            with self.assertRaisesRegex(noodles.GateError, "attempts exhausted"):
                noodles.repair_review(self.root, self.SUBJECT, self.review, pr)
        events = [json.loads(line) for line in events_path.read_text().splitlines()]
        escalations = [item for item in events if item["type"] == "repair_escalation"]
        self.assertEqual(len(escalations), 1)
        self.assertEqual(escalations[0]["payload"]["attempts"], noodles.REPAIR_MAX_ATTEMPTS)

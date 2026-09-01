from __future__ import annotations

import ast
import json
import textwrap
import unittest
from pathlib import Path
from unittest import mock

import noodles
import runtime_contract
from tests.support import CANDIDATE_ROOT, ISSUE_DEPENDS_ON_MARKER, ISSUE_FEATURE_MARKER, cmd, handoff_fixture


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
            f"{ISSUE_FEATURE_MARKER}\n"
            f"{ISSUE_DEPENDS_ON_MARKER}\n"
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
            # constraint: ed3c/noodles#272 - find_open_pr_for_subject now reads through the
            # constraint: paginated shared exit noodles.matching_open_pull_requests, so the
            # constraint: fixture answers that endpoint shape and nothing else.
            "repos/ed3c/noodles/pulls?state=open&per_page=100&page=1": [pr_payload],
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
                    "run_attempt": 1,
                    "pull_requests": [{"number": 44}],
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
                "run_attempt": 1,
                "pull_requests": [{"number": 44}],
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

    def test_worktree_exec_reads_exact_top_and_head_from_pending_review_worktree(self) -> None:
        top = runtime_contract.worktree_exec(
            self.root,
            self.WORKTREE_NAME,
            ["git", "rev-parse", "--show-toplevel"],
            error_cls=AssertionError,
        )
        head = runtime_contract.worktree_exec(
            self.root,
            self.WORKTREE_NAME,
            ["git", "rev-parse", "HEAD"],
            error_cls=AssertionError,
        )

        self.assertEqual(Path(top).resolve(), self.root.resolve())
        self.assertEqual(head, self.head)

    def test_worktree_exec_rejects_missing_worktree_name(self) -> None:
        with self.assertRaisesRegex(AssertionError, "pending review worktree_name is missing"):
            runtime_contract.worktree_exec(
                self.root,
                " ",
                ["git", "rev-parse", "HEAD"],
                error_cls=AssertionError,
            )

    def test_worktree_exec_rejects_unknown_worktree_name_with_diagnostics(self) -> None:
        with self.assertRaisesRegex(AssertionError, "unknown worktree"):
            runtime_contract.worktree_exec(
                self.root,
                "missing-worktree",
                ["git", "rev-parse", "HEAD"],
                error_cls=AssertionError,
            )

    def test_worktree_exec_rejects_wrong_project_root_with_diagnostics(self) -> None:
        with mock.patch.dict("os.environ", {"NOODLE_PROJECT_DIR": str(self.root.parent)}, clear=False):
            with self.assertRaisesRegex(AssertionError, "Noodle runtime directory missing from project"):
                runtime_contract.worktree_exec(
                    self.root,
                    self.WORKTREE_NAME,
                    ["git", "rev-parse", "HEAD"],
                    error_cls=AssertionError,
                )

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


class RepairOpenPrCorrelationTests(unittest.TestCase):
    """ed3c/noodles#272 - the refusal and its named remedy correlate on the same two keys.

    `schedule_publish`'s `open_pr_exists` refusal names an open PR and routes the caller to
    `./noodles repair`. While those two correlated differently the machine manufactured a dead
    end: the scheduler said "that PR exists, go repair it" and the repair verb answered
    "no such PR".
    """

    REPOSITORY = "ed3c/noodles"
    SUBJECT = "ed3c/noodles#82"

    def pull(self, number: int, *, body: str, head_ref: str) -> dict:
        return {"number": number, "state": "open", "body": body, "head": {"ref": head_ref}}

    def provider(self, pulls: list[dict]):
        prefix = f"repos/{self.REPOSITORY}/pulls?state=open&per_page=100&page="

        def api(endpoint: str, **_kwargs: object) -> object:
            if endpoint.startswith(prefix):
                page = int(endpoint.removeprefix(prefix))
                return pulls[(page - 1) * 100:page * 100]
            raise AssertionError(f"unexpected provider call: {endpoint}")

        return api

    def test_lane_branch_match_with_a_drifted_body_resolves_to_the_pr_the_refusal_names(self) -> None:
        # constraint: ed3c/noodles#272 - the reproduced failing shape: head branch equals
        # constraint: execute_branch(subject) but the body is not the exact one-line `Refs`.
        # constraint: The body-only predicate raised GateError here while the refusal pointed at
        # constraint: this exact PR, so the remedy the refusal named had no path to it.
        target = self.pull(9, body="WIP: no exact reference line", head_ref=noodles.execute_branch(self.SUBJECT))
        with mock.patch.object(noodles, "gh_api", side_effect=self.provider([target])):
            found = noodles.find_open_pr_for_subject(self.REPOSITORY, self.SUBJECT)
            named = noodles.subject_open_pull_requests(self.REPOSITORY, self.SUBJECT)
        self.assertEqual(found, target)
        self.assertEqual([f"{self.REPOSITORY}#{found['number']}"], named)

    def test_body_match_on_a_foreign_branch_still_resolves(self) -> None:
        target = self.pull(7, body=f"Refs {self.SUBJECT}", head_ref="fix-82-second-attempt")
        with mock.patch.object(noodles, "gh_api", side_effect=self.provider([target])):
            found = noodles.find_open_pr_for_subject(self.REPOSITORY, self.SUBJECT)
            named = noodles.subject_open_pull_requests(self.REPOSITORY, self.SUBJECT)
        self.assertEqual(found, target)
        self.assertEqual([f"{self.REPOSITORY}#{found['number']}"], named)

    def test_planted_negative_pr_with_neither_key_is_still_not_matched(self) -> None:
        # constraint: ed3c/noodles#272 - the shared exit narrows as well as widens: a foreign
        # constraint: branch with a drifted body correlates on nothing and must stay unfound.
        foreign = self.pull(11, body="WIP: unrelated work", head_ref="fix-something-else")
        with mock.patch.object(noodles, "gh_api", side_effect=self.provider([foreign])):
            with self.assertRaisesRegex(noodles.GateError, "got 0"):
                noodles.find_open_pr_for_subject(self.REPOSITORY, self.SUBJECT)
            self.assertEqual(noodles.subject_open_pull_requests(self.REPOSITORY, self.SUBJECT), [])

    def test_planted_negative_a_sibling_subjects_open_pr_is_not_this_subjects_pr(self) -> None:
        sibling = self.pull(12, body=f"Refs {self.REPOSITORY}#83", head_ref=noodles.execute_branch(f"{self.REPOSITORY}#83"))
        with mock.patch.object(noodles, "gh_api", side_effect=self.provider([sibling])):
            with self.assertRaisesRegex(noodles.GateError, "got 0"):
                noodles.find_open_pr_for_subject(self.REPOSITORY, self.SUBJECT)

    def test_match_beyond_the_first_page_is_reachable_by_the_remedy(self) -> None:
        # constraint: ed3c/noodles#272 - pagination is inherited from the shared exit; the
        # constraint: unpaginated read stopped correlating past the provider's first 100 PRs.
        filler = [
            self.pull(100 + index, body=f"Refs {self.REPOSITORY}#{900 + index}", head_ref=f"filler-{index}")
            for index in range(100)
        ]
        target = self.pull(9, body=f"Refs {self.SUBJECT}", head_ref="fix-82-second-attempt")
        with mock.patch.object(noodles, "gh_api", side_effect=self.provider(filler + [target])):
            self.assertEqual(noodles.find_open_pr_for_subject(self.REPOSITORY, self.SUBJECT), target)

    def test_readback_find_open_pr_for_subject_carries_no_correlation_predicate_of_its_own(self) -> None:
        # constraint: ed3c/noodles#272 - "one shared exit" stays true only while the remedy holds
        # constraint: no second copy of the rule. Read the definition's own source: every engine
        # constraint: attribute it reaches for must be the shared exit or the error type, so a
        # constraint: re-added `parse_pr_reference`/`gh_api`/head-ref predicate reds here.
        source = (CANDIDATE_ROOT / "repair_contract.py").read_text(encoding="utf-8")
        definition = noodles.top_level_definitions(source, "repair_contract.py")["find_open_pr_for_subject"]
        reached = {
            node.attr
            for node in ast.walk(ast.parse(textwrap.dedent(definition)))
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "engine"
        }
        self.assertEqual(reached, {"matching_open_pull_requests", "GateError"})

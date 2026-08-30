from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest import mock

import github_protection
import noodles
from tests.support import (
    CANDIDATE_ROOT,
    FEATURE,
    ISSUE_DEPENDS_ON_MARKER,
    ISSUE_FEATURE_MARKER,
    cmd,
    control_checkout_fixture,
    handoff_fixture,
    write_acceptance_evidence,
)


class ContractParserTests(unittest.TestCase):
    BODY = f"""<!-- noodles-role: repository-mutating-atom -->
<!-- noodles-target: ed3c/noodles -->
<!-- noodles-subject: ed3c/noodles#7 -->
<!-- noodles-state: ready -->
{ISSUE_FEATURE_MARKER}
{ISSUE_DEPENDS_ON_MARKER}
"""

    def test_issue_contract_positive(self) -> None:
        parsed = noodles.parse_issue_contract(self.BODY, "ed3c/noodles#7")
        self.assertEqual(parsed["state"], "ready")

    def test_issue_contract_rejects_target_drift(self) -> None:
        with self.assertRaises(noodles.GateError):
            noodles.parse_issue_contract(self.BODY.replace("noodles-target: ed3c/noodles", "noodles-target: ed3c/other"))

    def test_pr_reference_is_exact_and_non_closing(self) -> None:
        self.assertEqual(noodles.parse_pr_reference("Refs ed3c/noodles#7\n"), "ed3c/noodles#7")
        with self.assertRaises(noodles.GateError):
            noodles.parse_pr_reference("Claim\nRefs ed3c/noodles#7\n")
        with self.assertRaises(noodles.GateError):
            noodles.parse_pr_reference("Refs ed3c/noodles#7\nRefs ed3c/noodles#8\n")
        with self.assertRaises(noodles.GateError):
            noodles.parse_pr_reference("Closes #7\nRefs ed3c/noodles#7\n")

    def test_state_marker_replacement_is_single(self) -> None:
        changed = noodles.replace_marker(self.BODY, "state", "awaiting_land")
        self.assertEqual(noodles.parse_issue_contract(changed)["state"], "awaiting_land")


class NonClaimEvidenceTests(unittest.TestCase):
    BODY = ContractParserTests.BODY

    def test_n_class_is_a_path_prefix_property_without_per_file_marker(self) -> None:
        self.assertEqual(noodles.N_CLASS_PREFIXES, ("docs/research/", "docs/design/"))
        study = CANDIDATE_ROOT / "docs/research/2026-08-29-noodle-shared-vs-noodles-performance.md"
        text = study.read_text(encoding="utf-8")
        self.assertNotIn("<!-- noodles-", text)
        self.assertIn("#64", text)
        self.assertIn("#86", text)

    def test_evidence_field_citing_n_class_path_fails_closed_naming_the_reference(self) -> None:
        for line in (
            "- Evidence: docs/research/2026-08-29-noodle-shared-vs-noodles-performance.md",
            "Claim: see `docs/design/handoff-shape.md` for the proof",
            "**Acceptance**: docs/research/study.md",
        ):
            with self.assertRaises(noodles.GateError) as raised:
                noodles.parse_issue_contract(f"{self.BODY}\n{line}\n", "ed3c/noodles#7")
            self.assertIn("docs/", str(raised.exception))

    def test_machine_artifact_evidence_and_plain_prose_mentions_pass(self) -> None:
        body = (
            f"{self.BODY}\n"
            "- The study is landed at `docs/research/2026-08-29-noodle-shared-vs-noodles-performance.md`.\n"
            "- Evidence: tests/run.sh exit 0 and receipt sha256 digest readback.\n"
        )
        self.assertEqual(noodles.parse_issue_contract(body, "ed3c/noodles#7")["state"], "ready")


class ExecuteHandoffTests(unittest.TestCase):
    SUBJECT = "ed3c/noodles#33"

    def setUp(self) -> None:
        self.temp, self.root, self.binary, self.session_id = handoff_fixture(CANDIDATE_ROOT)
        self.addCleanup(self.temp.cleanup)
        self.head = cmd(["git", "rev-parse", "HEAD"], self.root)
        write_acceptance_evidence(self.root, self.head, FEATURE)
        self.issue = mock.patch.object(
            noodles,
            "issue_read",
            return_value={"body": ContractParserTests.BODY.replace("ed3c/noodles#7", self.SUBJECT)},
        )
        self.issue.start()
        self.addCleanup(self.issue.stop)

    def pr(self, **overrides: object) -> dict:
        payload = {
            "state": "open",
            "draft": False,
            "body": f"Refs {self.SUBJECT}",
            "head": {"sha": self.head},
            "base": {"ref": "main"},
        }
        payload.update(overrides)
        return payload

    def failed_verify_source(self) -> dict:
        return {"run": {
            "id": 91,
            "head_sha": self.head,
            "status": "completed",
            "conclusion": "failure",
            "run_attempt": 1,
            "pull_request_numbers": [44],
        }}

    def trusted_verify_source(self, *, attempt: int = 1, status: str = "completed", conclusion: str = "failure") -> dict:
        return {"run": {
            "id": 91,
            "head_sha": self.head,
            "status": status,
            "conclusion": conclusion,
            "run_attempt": attempt,
            "pull_request_numbers": [44],
        }}

    def test_legacy_stage_does_not_suppress_exact_rerun_receipt_or_duplicate_post(self) -> None:
        pr = self.pr()
        events_path = self.root / ".noodle" / "sessions" / self.session_id / "events.ndjson"
        message = f"Provider handoff ready: {self.SUBJECT} PR #44 exact head {self.head}; park until trusted provider landing readback."
        with events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "type": "stage_message",
                "payload": {"message": message, "blocking": True},
                "timestamp": "2026-08-29T00:00:00Z",
                "session_id": self.session_id,
            }) + "\n")
        with mock.patch.dict(os.environ, {"NOODLE_SESSION_ID": self.session_id}, clear=False), \
             mock.patch.object(noodles, "issue_set_state"), \
             mock.patch.object(github_protection, "failed_required_workflow_run_readback", return_value=self.failed_verify_source()) as failed_run, \
             mock.patch.object(github_protection, "trusted_workflow_run_readback", return_value=self.trusted_verify_source()), \
             mock.patch.object(noodles, "gh_api", return_value=None) as api:
            receipt = noodles.execute_handoff(self.root, self.SUBJECT, 44, pr)

        self.assertEqual(receipt["session_id"], self.session_id)
        self.assertEqual(receipt["head"], self.head)
        self.assertEqual(receipt["verification_rerun"]["workflow_run_id"], 91)
        self.assertEqual(receipt["verification_rerun"]["head_sha"], self.head)
        self.assertEqual(receipt["verification_rerun"]["baseline_run_attempt"], 1)
        events = [json.loads(line) for line in events_path.read_text().splitlines()]
        handoffs = [item for item in events if item["type"] == "stage_message"]
        reruns = [item for item in handoffs if item["payload"].get("workflow_run_id") == 91]
        self.assertEqual(len(handoffs), 2)
        self.assertEqual(len(reruns), 1)
        self.assertIs(reruns[0]["payload"]["blocking"], True)
        self.assertIn(self.SUBJECT, reruns[0]["payload"]["message"])
        failed_run.assert_called_once_with(
            api,
            noodles.GateError,
            "ed3c/noodles",
            self.head,
            name="verify",
            path=".github/workflows/verify.yml",
            event="pull_request_target",
            default_branch="main",
            pr_number=44,
        )
        api.assert_called_once_with("repos/ed3c/noodles/actions/runs/91/rerun", method="POST")

        with mock.patch.dict(os.environ, {"NOODLE_SESSION_ID": self.session_id}, clear=False), \
             mock.patch.object(noodles, "issue_set_state"), \
             mock.patch.object(github_protection, "failed_required_workflow_run_readback") as repeated_failed_run, \
             mock.patch.object(noodles, "gh_api") as repeated_api:
            noodles.execute_handoff(self.root, self.SUBJECT, 44, pr)
        events = [json.loads(line) for line in events_path.read_text().splitlines()]
        self.assertEqual(sum(item["type"] == "stage_message" for item in events), 2)
        repeated_failed_run.assert_not_called()
        repeated_api.assert_not_called()

    def test_first_handoff_orders_state_admission_rerun_and_stage_emission(self) -> None:
        calls: list[str] = []

        def select(*_args: object, **_kwargs: object) -> dict:
            calls.append("select")
            return self.failed_verify_source()

        def post(endpoint: str, *, method: str = "GET", payload: object | None = None, token: str | None = None) -> None:
            self.assertEqual((endpoint, method, payload, token), ("repos/ed3c/noodles/actions/runs/91/rerun", "POST", None, None))
            calls.append("post")

        def emit(*_args: object, **_kwargs: object) -> dict:
            calls.append("stage")
            return {
                "session_id": self.session_id,
                "head": self.head,
                "message": "handoff",
                "blocking": True,
                "verification_rerun": {"workflow_run_id": 91, "head_sha": self.head, "baseline_run_attempt": 1},
            }

        def intent(*_args: object, **_kwargs: object) -> dict:
            calls.append("intent")
            return {
                "issue_subject": self.SUBJECT,
                "pr_number": 44,
                "head_sha": self.head,
                "workflow_run_id": 91,
                "baseline_run_attempt": 1,
            }

        def trusted(*_args: object, **_kwargs: object) -> dict:
            calls.append("read")
            return self.trusted_verify_source()

        with mock.patch.dict(os.environ, {"NOODLE_SESSION_ID": self.session_id}, clear=False), \
             mock.patch.object(noodles, "issue_set_state", side_effect=lambda *_args: calls.append("state")), \
             mock.patch.object(github_protection, "failed_required_workflow_run_readback", side_effect=select), \
             mock.patch.object(noodles, "emit_handoff_rerun_intent", side_effect=intent), \
             mock.patch.object(github_protection, "trusted_workflow_run_readback", side_effect=trusted), \
             mock.patch.object(noodles, "gh_api", side_effect=post), \
             mock.patch.object(noodles, "emit_blocking_handoff", side_effect=emit):
            noodles.execute_handoff(self.root, self.SUBJECT, 44, self.pr())

        self.assertEqual(calls, ["state", "select", "intent", "read", "post", "stage"])

    def test_state_admission_failure_queries_no_workflow_and_emits_no_stage(self) -> None:
        with mock.patch.dict(os.environ, {"NOODLE_SESSION_ID": self.session_id}, clear=False), \
             mock.patch.object(noodles, "issue_set_state", side_effect=noodles.GateError("state admission failed")), \
             mock.patch.object(github_protection, "failed_required_workflow_run_readback") as failed_run, \
             mock.patch.object(noodles, "gh_api") as api, \
             mock.patch.object(noodles, "emit_blocking_handoff") as emit:
            with self.assertRaisesRegex(noodles.GateError, "state admission failed"):
                noodles.execute_handoff(self.root, self.SUBJECT, 44, self.pr())

        failed_run.assert_not_called()
        api.assert_not_called()
        emit.assert_not_called()

    def test_wrong_head_failed_run_causes_no_post_or_stage(self) -> None:
        with mock.patch.dict(os.environ, {"NOODLE_SESSION_ID": self.session_id}, clear=False), \
             mock.patch.object(noodles, "issue_set_state"), \
             mock.patch.object(github_protection, "failed_required_workflow_run_readback", side_effect=noodles.GateError("no completed failed workflow run")), \
             mock.patch.object(noodles, "gh_api") as api, \
             mock.patch.object(noodles, "emit_blocking_handoff") as emit:
            with self.assertRaisesRegex(noodles.GateError, "no completed failed workflow run"):
                noodles.execute_handoff(self.root, self.SUBJECT, 44, self.pr())

        api.assert_not_called()
        emit.assert_not_called()

    def test_rerun_post_failure_emits_no_blocking_stage(self) -> None:
        with mock.patch.dict(os.environ, {"NOODLE_SESSION_ID": self.session_id}, clear=False), \
             mock.patch.object(noodles, "issue_set_state"), \
             mock.patch.object(github_protection, "failed_required_workflow_run_readback", return_value=self.failed_verify_source()), \
             mock.patch.object(github_protection, "trusted_workflow_run_readback", return_value=self.trusted_verify_source()), \
             mock.patch.object(noodles, "gh_api", side_effect=noodles.GateError("rerun failed")), \
             mock.patch.object(noodles, "emit_blocking_handoff") as emit:
            with self.assertRaisesRegex(noodles.GateError, "rerun failed"):
                noodles.execute_handoff(self.root, self.SUBJECT, 44, self.pr())
        emit.assert_not_called()

    def test_successful_post_then_stage_failure_is_adopted_without_second_post(self) -> None:
        provider_attempt = 1

        def trusted(*_args: object, **_kwargs: object) -> dict:
            if provider_attempt == 1:
                return self.trusted_verify_source()
            return self.trusted_verify_source(attempt=2, status="queued", conclusion="")

        def post(*_args: object, **_kwargs: object) -> None:
            nonlocal provider_attempt
            provider_attempt = 2

        with mock.patch.dict(os.environ, {"NOODLE_SESSION_ID": self.session_id}, clear=False), \
             mock.patch.object(noodles, "issue_set_state"), \
             mock.patch.object(github_protection, "failed_required_workflow_run_readback", return_value=self.failed_verify_source()) as failed_run, \
             mock.patch.object(github_protection, "trusted_workflow_run_readback", side_effect=trusted), \
             mock.patch.object(noodles, "gh_api", side_effect=post) as api:
            with mock.patch.object(noodles, "emit_blocking_handoff", side_effect=noodles.GateError("stage failed")):
                with self.assertRaisesRegex(noodles.GateError, "stage failed"):
                    noodles.execute_handoff(self.root, self.SUBJECT, 44, self.pr())

            receipt = noodles.execute_handoff(self.root, self.SUBJECT, 44, self.pr())

        self.assertEqual(receipt["verification_rerun"]["workflow_run_id"], 91)
        self.assertEqual(receipt["verification_rerun"]["baseline_run_attempt"], 1)
        failed_run.assert_called_once()
        api.assert_called_once_with("repos/ed3c/noodles/actions/runs/91/rerun", method="POST")

    def test_durable_intent_rejects_attempt_drift_without_post_or_stage(self) -> None:
        with mock.patch.dict(os.environ, {"NOODLE_SESSION_ID": self.session_id}, clear=False):
            noodles.emit_handoff_rerun_intent(
                self.root, self.SUBJECT, 44, self.head, 91, 1, self.session_id, error_cls=noodles.GateError
            )
        with mock.patch.dict(os.environ, {"NOODLE_SESSION_ID": self.session_id}, clear=False), \
             mock.patch.object(noodles, "issue_set_state"), \
             mock.patch.object(github_protection, "failed_required_workflow_run_readback") as failed_run, \
             mock.patch.object(
                 github_protection,
                 "trusted_workflow_run_readback",
                 return_value=self.trusted_verify_source(attempt=3, status="queued", conclusion=""),
             ), \
             mock.patch.object(noodles, "gh_api") as api, \
             mock.patch.object(noodles, "emit_blocking_handoff") as emit:
            with self.assertRaisesRegex(noodles.GateError, "attempt drifted"):
                noodles.execute_handoff(self.root, self.SUBJECT, 44, self.pr())
        failed_run.assert_not_called()
        api.assert_not_called()
        emit.assert_not_called()

    def test_durable_intent_wrong_head_fails_before_provider_mutation(self) -> None:
        events_path = self.root / ".noodle" / "sessions" / self.session_id / "events.ndjson"
        with events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "type": "handoff_verify_rerun_intent",
                "payload": {
                    "issue_subject": self.SUBJECT,
                    "pr_number": 44,
                    "head_sha": "f" * 40,
                    "workflow_run_id": 91,
                    "baseline_run_attempt": 1,
                },
                "timestamp": "2026-08-29T00:00:00Z",
                "session_id": self.session_id,
            }) + "\n")
        with mock.patch.dict(os.environ, {"NOODLE_SESSION_ID": self.session_id}, clear=False), \
             mock.patch.object(noodles, "issue_set_state"), \
             mock.patch.object(github_protection, "failed_required_workflow_run_readback") as failed_run, \
             mock.patch.object(noodles, "gh_api") as api:
            with self.assertRaisesRegex(noodles.GateError, "head drifted"):
                noodles.execute_handoff(self.root, self.SUBJECT, 44, self.pr())
        failed_run.assert_not_called()
        api.assert_not_called()

    def test_wrong_session_id_fails_before_emission(self) -> None:
        with mock.patch.dict(os.environ, {"NOODLE_SESSION_ID": "wrong-session"}, clear=False), \
             mock.patch.object(noodles, "issue_set_state") as set_state:
            with self.assertRaisesRegex(noodles.GateError, "session"):
                noodles.execute_handoff(self.root, self.SUBJECT, 44, self.pr())
        set_state.assert_not_called()

    def test_non_blocking_runtime_event_fails_direct_readback(self) -> None:
        self.temp.cleanup()
        self.temp, self.root, self.binary, self.session_id = handoff_fixture(CANDIDATE_ROOT, blocking=False)
        self.addCleanup(self.temp.cleanup)
        self.head = cmd(["git", "rev-parse", "HEAD"], self.root)
        write_acceptance_evidence(self.root, self.head, FEATURE)
        with mock.patch.dict(os.environ, {"NOODLE_SESSION_ID": self.session_id}, clear=False), \
             mock.patch.object(noodles, "issue_set_state"), \
             mock.patch.object(github_protection, "failed_required_workflow_run_readback", return_value=self.failed_verify_source()), \
             mock.patch.object(github_protection, "trusted_workflow_run_readback", return_value=self.trusted_verify_source()), \
             mock.patch.object(noodles, "gh_api", return_value=None):
            with self.assertRaisesRegex(noodles.GateError, "blocking"):
                noodles.execute_handoff(self.root, self.SUBJECT, 44, self.pr())

    def test_wrong_pr_body_head_or_base_fails_closed(self) -> None:
        with mock.patch.dict(os.environ, {"NOODLE_SESSION_ID": self.session_id}, clear=False), \
             mock.patch.object(noodles, "issue_set_state"), \
             mock.patch.object(github_protection, "failed_required_workflow_run_readback") as failed_run, \
             mock.patch.object(noodles, "gh_api") as api:
            with self.assertRaises(noodles.GateError):
                noodles.execute_handoff(self.root, self.SUBJECT, 44, self.pr(body="Claim\nRefs ed3c/noodles#33"))
            with self.assertRaisesRegex(noodles.GateError, "head"):
                noodles.execute_handoff(self.root, self.SUBJECT, 44, self.pr(head={"sha": "f" * 40}))
            with self.assertRaisesRegex(noodles.GateError, "base"):
                noodles.execute_handoff(self.root, self.SUBJECT, 44, self.pr(base={"ref": "dependent-feature"}))
        failed_run.assert_not_called()
        api.assert_not_called()

    def test_handoff_citing_n_class_path_as_evidence_fails_before_emission(self) -> None:
        body = (
            "<!-- noodles-role: repository-mutating-atom -->\n"
            "<!-- noodles-target: ed3c/noodles -->\n"
            f"<!-- noodles-subject: {self.SUBJECT} -->\n"
            "<!-- noodles-state: ready -->\n"
            "<!-- noodles-feature: verification-skill-oracle -->\n"
            f"{ISSUE_DEPENDS_ON_MARKER}\n\n"
            "- Evidence: docs/research/2026-08-29-noodle-shared-vs-noodles-performance.md\n"
        )
        with mock.patch.dict(os.environ, {"NOODLE_SESSION_ID": self.session_id}, clear=False), \
             mock.patch.object(noodles, "issue_read", return_value={"state": "open", "body": body}), \
             mock.patch.object(noodles, "gh_api", return_value={"state": "open", "body": body}) as api:
            with self.assertRaisesRegex(noodles.GateError, "docs/research/"):
                noodles.execute_handoff(self.root, self.SUBJECT, 44, self.pr())
        self.assertTrue(all(call.kwargs.get("method", "GET") == "GET" for call in api.call_args_list))
        events_path = self.root / ".noodle" / "sessions" / self.session_id / "events.ndjson"
        events = [json.loads(line) for line in events_path.read_text().splitlines()]
        self.assertEqual([item for item in events if item["type"] == "stage_message"], [])

    def test_missing_pr_fails_before_issue_or_session_mutation(self) -> None:
        with mock.patch.object(noodles, "gh_api", side_effect=noodles.GateError("missing PR")), \
             mock.patch.object(noodles, "issue_set_state") as set_state:
            self.assertEqual(noodles.main(["--root", str(self.root), "issue", "handoff", self.SUBJECT, "--pr", "404"]), 1)
        set_state.assert_not_called()


class ReconcileTests(unittest.TestCase):
    def test_reconcile_checkout_admission_fails_before_snapshot_or_merge(self) -> None:
        with mock.patch.object(noodles, "reconcile_checkout_admission", side_effect=noodles.GateError("dirty")) as admit, \
             mock.patch.object(noodles, "http_json") as http_json, \
             mock.patch.object(noodles, "git") as git_cmd:
            with self.assertRaisesRegex(noodles.GateError, "dirty"):
                noodles.reconcile_once(CANDIDATE_ROOT, "http://noodle.test")
        admit.assert_called_once_with(CANDIDATE_ROOT)
        http_json.assert_not_called()
        git_cmd.assert_not_called()

    def test_provider_landed_sends_exact_merge_control_and_accepts_status_ack(self) -> None:
        calls: list[tuple[str, object]] = []

        def fake_http(url: str, *, payload: object | None = None) -> dict:
            calls.append((url, payload))
            if payload is None:
                return {"pending_reviews": [{"order_id": "ed3c/noodles#33"}]}
            return {"id": payload["id"], "action": "merge", "status": "ok"}

        def fake_git(_root: Path, *args: str, check: bool = True) -> str:
            if args == ("fetch", "--quiet", "origin", "main"):
                return ""
            if args == ("merge", "--ff-only", "origin/main"):
                return ""
            if args == ("rev-parse", "refs/remotes/origin/main"):
                return "b" * 40
            if args == ("rev-parse", "HEAD"):
                return "b" * 40
            raise AssertionError(f"unexpected git args: {args}")

        with mock.patch.object(noodles, "reconcile_checkout_admission", return_value={"branch": "main"}), \
             mock.patch.object(noodles, "http_json", side_effect=fake_http), \
             mock.patch.object(noodles, "provider_landed", return_value=(44, "a" * 40, "b" * 40)), \
             mock.patch.object(noodles, "git", side_effect=fake_git) as git_cmd:
            completed = noodles.reconcile_once(CANDIDATE_ROOT, "http://noodle.test")

        self.assertEqual(completed, ["ed3c/noodles#33"])
        self.assertEqual(calls[1][1]["action"], "merge")
        self.assertEqual(calls[1][1]["order_id"], "ed3c/noodles#33")
        git_cmd.assert_any_call(CANDIDATE_ROOT, "fetch", "--quiet", "origin", "main")
        git_cmd.assert_any_call(CANDIDATE_ROOT, "merge", "--ff-only", "origin/main")
        git_cmd.assert_any_call(CANDIDATE_ROOT, "rev-parse", "refs/remotes/origin/main")
        git_cmd.assert_any_call(CANDIDATE_ROOT, "rev-parse", "HEAD")

    def test_reconcile_uses_admitted_default_branch_for_fetch_and_merge(self) -> None:
        def fake_http(url: str, *, payload: object | None = None) -> dict:
            if payload is None:
                return {"pending_reviews": [{"order_id": "ed3c/noodles#33"}]}
            return {"id": payload["id"], "action": "merge", "status": "ok"}

        def fake_git(_root: Path, *args: str, check: bool = True) -> str:
            if args == ("fetch", "--quiet", "origin", "trunk"):
                return ""
            if args == ("merge", "--ff-only", "origin/trunk"):
                return ""
            if args == ("rev-parse", "refs/remotes/origin/trunk"):
                return "b" * 40
            if args == ("rev-parse", "HEAD"):
                return "b" * 40
            raise AssertionError(f"unexpected git args: {args}")

        with mock.patch.object(noodles, "reconcile_checkout_admission", return_value={"branch": "trunk"}), \
             mock.patch.object(noodles, "http_json", side_effect=fake_http), \
             mock.patch.object(noodles, "provider_landed", return_value=(44, "a" * 40, "b" * 40)), \
             mock.patch.object(noodles, "git", side_effect=fake_git) as git_cmd:
            noodles.reconcile_once(CANDIDATE_ROOT, "http://noodle.test")

        git_cmd.assert_any_call(CANDIDATE_ROOT, "fetch", "--quiet", "origin", "trunk")
        git_cmd.assert_any_call(CANDIDATE_ROOT, "merge", "--ff-only", "origin/trunk")

    def test_machine_merge_rejects_control_ack_drift(self) -> None:
        responses = [
            {"pending_reviews": [{"order_id": "ed3c/noodles#33"}]},
            {"id": "wrong", "action": "merge", "status": "ok"},
        ]
        def fake_git(_root: Path, *args: str, check: bool = True) -> str:
            if args == ("fetch", "--quiet", "origin", "main"):
                return ""
            if args == ("merge", "--ff-only", "origin/main"):
                return ""
            if args == ("rev-parse", "refs/remotes/origin/main"):
                return "b" * 40
            if args == ("rev-parse", "HEAD"):
                return "b" * 40
            raise AssertionError(f"unexpected git args: {args}")

        with mock.patch.object(noodles, "reconcile_checkout_admission", return_value={"branch": "main"}), \
             mock.patch.object(noodles, "http_json", side_effect=responses), \
             mock.patch.object(noodles, "provider_landed", return_value=(44, "a" * 40, "b" * 40)), \
             mock.patch.object(noodles, "git", side_effect=fake_git):
            with self.assertRaisesRegex(noodles.GateError, "rejected machine reconciliation"):
                noodles.reconcile_once(CANDIDATE_ROOT, "http://noodle.test")

    def test_reconcile_rejects_post_merge_head_drift_before_control_ack(self) -> None:
        calls: list[tuple[str, object]] = []

        def fake_http(url: str, *, payload: object | None = None) -> dict:
            calls.append((url, payload))
            if payload is None:
                return {"pending_reviews": [{"order_id": "ed3c/noodles#33"}]}
            return {"id": payload["id"], "action": "merge", "status": "ok"}

        def fake_git(_root: Path, *args: str, check: bool = True) -> str:
            if args == ("fetch", "--quiet", "origin", "main"):
                return ""
            if args == ("merge", "--ff-only", "origin/main"):
                return ""
            if args == ("rev-parse", "refs/remotes/origin/main"):
                return "b" * 40
            if args == ("rev-parse", "HEAD"):
                return "c" * 40
            raise AssertionError(f"unexpected git args: {args}")

        with mock.patch.object(noodles, "reconcile_checkout_admission", return_value={"branch": "main"}), \
             mock.patch.object(noodles, "http_json", side_effect=fake_http), \
             mock.patch.object(noodles, "provider_landed", return_value=(44, "a" * 40, "b" * 40)), \
             mock.patch.object(noodles, "git", side_effect=fake_git):
            with self.assertRaisesRegex(noodles.GateError, "readback drift"):
                noodles.reconcile_once(CANDIDATE_ROOT, "http://noodle.test")

        self.assertEqual(calls, [("http://noodle.test/api/snapshot", None)])

    def test_preland_reconcile_sends_no_control(self) -> None:
        calls: list[tuple[str, object]] = []

        def fake_http(url: str, *, payload: object | None = None) -> dict:
            calls.append((url, payload))
            return {"pending_reviews": [{"order_id": "ed3c/noodles#33"}]}

        with mock.patch.object(noodles, "reconcile_checkout_admission", return_value={"branch": "main"}), \
             mock.patch.object(noodles, "http_json", side_effect=fake_http), \
             mock.patch.object(noodles, "provider_landed", side_effect=noodles.GateError("not landed")):
            completed = noodles.reconcile_once(CANDIDATE_ROOT, "http://noodle.test")

        self.assertEqual(completed, [])
        self.assertEqual(calls, [("http://noodle.test/api/snapshot", None)])

    def test_physical_behind_checkout_fast_forwards_cleanly_before_control_ack(self) -> None:
        temp, root, provider = control_checkout_fixture()
        self.addCleanup(temp.cleanup)
        local_before = cmd(["git", "rev-parse", "HEAD"], root)
        path = provider / "behind.txt"
        path.write_text("provider ahead\n", encoding="utf-8")
        cmd(["git", "add", "behind.txt"], provider)
        cmd(["git", "commit", "-q", "-m", "provider ahead"], provider)
        provider_head = cmd(["git", "rev-parse", "HEAD"], provider)
        command_log: list[tuple[str, ...]] = []
        real_git = noodles.git

        def logging_git(repo_root: Path, *args: str, check: bool = True) -> str:
            command_log.append(args)
            return real_git(repo_root, *args, check=check)

        def fake_http(_url: str, *, payload: object | None = None) -> dict:
            if payload is None:
                return {"pending_reviews": [{"order_id": "ed3c/noodles#33"}]}
            self.assertEqual(cmd(["git", "rev-parse", "HEAD"], root), provider_head)
            return {"id": payload["id"], "action": "merge", "status": "ok"}

        with mock.patch.object(noodles, "http_json", side_effect=fake_http), \
             mock.patch.object(noodles, "provider_landed", return_value=(44, "a" * 40, "b" * 40)), \
             mock.patch.object(noodles, "git", side_effect=logging_git):
            completed = noodles.reconcile_once(root, "http://noodle.test")

        self.assertEqual(completed, ["ed3c/noodles#33"])
        self.assertEqual(cmd(["git", "rev-parse", "HEAD"], root), provider_head)
        self.assertEqual(cmd(["git", "status", "--porcelain=v1", "--untracked-files=all"], root), "")
        self.assertNotEqual(local_before, provider_head)
        self.assertTrue(any(args == ("fetch", "--quiet", "origin", "main") for args in command_log))
        self.assertTrue(any(args == ("merge", "--ff-only", "origin/main") for args in command_log))
        self.assertFalse(any(args and args[0] in {"checkout", "reset"} for args in command_log))

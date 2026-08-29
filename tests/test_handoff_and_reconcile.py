from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest import mock

import noodles
from tests.support import (
    CANDIDATE_ROOT,
    ISSUE_FEATURE_MARKER,
    cmd,
    control_checkout_fixture,
    handoff_fixture,
    write_feature_evidence,
)


class ContractParserTests(unittest.TestCase):
    BODY = f"""<!-- noodles-role: repository-mutating-atom -->
<!-- noodles-target: ed3c/noodles -->
<!-- noodles-subject: ed3c/noodles#7 -->
<!-- noodles-state: ready -->
{ISSUE_FEATURE_MARKER}
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
        write_feature_evidence(self.root, self.head)
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

    def test_positive_handoff_emits_one_blocking_message_for_exact_session(self) -> None:
        pr = self.pr()
        with mock.patch.dict(os.environ, {"NOODLE_SESSION_ID": self.session_id}, clear=False), \
             mock.patch.object(noodles, "issue_set_state"):
            receipt = noodles.execute_handoff(self.root, self.SUBJECT, 44, pr)

        self.assertEqual(receipt["session_id"], self.session_id)
        self.assertEqual(receipt["head"], self.head)
        events_path = self.root / ".noodle" / "sessions" / self.session_id / "events.ndjson"
        events = [json.loads(line) for line in events_path.read_text().splitlines()]
        handoffs = [item for item in events if item["type"] == "stage_message"]
        self.assertEqual(len(handoffs), 1)
        self.assertIs(handoffs[0]["payload"]["blocking"], True)
        self.assertIn(self.SUBJECT, handoffs[0]["payload"]["message"])

        with mock.patch.dict(os.environ, {"NOODLE_SESSION_ID": self.session_id}, clear=False), \
             mock.patch.object(noodles, "issue_set_state"):
            noodles.execute_handoff(self.root, self.SUBJECT, 44, pr)
        events = [json.loads(line) for line in events_path.read_text().splitlines()]
        self.assertEqual(sum(item["type"] == "stage_message" for item in events), 1)

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
        write_feature_evidence(self.root, self.head)
        with mock.patch.dict(os.environ, {"NOODLE_SESSION_ID": self.session_id}, clear=False), \
             mock.patch.object(noodles, "issue_set_state"):
            with self.assertRaisesRegex(noodles.GateError, "blocking"):
                noodles.execute_handoff(self.root, self.SUBJECT, 44, self.pr())

    def test_wrong_pr_body_head_or_base_fails_closed(self) -> None:
        with mock.patch.dict(os.environ, {"NOODLE_SESSION_ID": self.session_id}, clear=False), \
             mock.patch.object(noodles, "issue_set_state"):
            with self.assertRaises(noodles.GateError):
                noodles.execute_handoff(self.root, self.SUBJECT, 44, self.pr(body="Claim\nRefs ed3c/noodles#33"))
            with self.assertRaisesRegex(noodles.GateError, "head"):
                noodles.execute_handoff(self.root, self.SUBJECT, 44, self.pr(head={"sha": "f" * 40}))
            with self.assertRaisesRegex(noodles.GateError, "base"):
                noodles.execute_handoff(self.root, self.SUBJECT, 44, self.pr(base={"ref": "dependent-feature"}))

    def test_handoff_citing_n_class_path_as_evidence_fails_before_emission(self) -> None:
        body = (
            "<!-- noodles-role: repository-mutating-atom -->\n"
            "<!-- noodles-target: ed3c/noodles -->\n"
            f"<!-- noodles-subject: {self.SUBJECT} -->\n"
            "<!-- noodles-state: ready -->\n"
            "<!-- noodles-feature: verification-skill-oracle -->\n\n"
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

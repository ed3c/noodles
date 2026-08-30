from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import feature_contract
import github_protection
import noodles
import skill_contract
from tests.support import (
    CANDIDATE_ROOT,
    FEATURE,
    ISSUE_DEPENDS_ON_MARKER,
    ISSUE_FEATURE_MARKER,
    acceptance_evidence,
    cmd,
    code_surface_digest,
    copy_tracked,
    handoff_fixture,
    write_acceptance_evidence,
)

SUBJECT = "ed3c/noodles#33"
ISSUE_BODY = (
    "<!-- noodles-role: repository-mutating-atom -->\n"
    "<!-- noodles-target: ed3c/noodles -->\n"
    f"<!-- noodles-subject: {SUBJECT} -->\n"
    "<!-- noodles-state: ready -->\n"
    f"{ISSUE_FEATURE_MARKER}\n"
    f"{ISSUE_DEPENDS_ON_MARKER}\n"
)


class FeatureVerifierTests(unittest.TestCase):
    """The declared operation must physically run and the oracle must read the real artifact."""

    def candidate_copy(self) -> Path:
        temp = tempfile.TemporaryDirectory(prefix="noodles-feature-test-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / "repo"
        copy_tracked(CANDIDATE_ROOT, root)
        return root

    def test_positive_control_runs_operation_and_admits_direct_readback_with_zero_residue(self) -> None:
        root = self.candidate_copy()
        with contextlib.redirect_stdout(io.StringIO()):
            exit_code = noodles.main(["--root", str(root), "feature", "verify", FEATURE.feature_id])
        self.assertEqual(exit_code, 0)

        evidence = json.loads((root / feature_contract.EVIDENCE_PATH).read_text())
        self.assertEqual(evidence["feature_id"], FEATURE.feature_id)
        self.assertEqual(evidence["operation"], list(FEATURE.operation))
        self.assertEqual(evidence["observed"], {"returncode": 0, "ok": True, "errors": []})
        self.assertEqual(evidence["head"], cmd(["git", "rev-parse", "HEAD"], root))
        self.assertEqual(evidence["code_surface"], FEATURE.code_surface)
        self.assertEqual(evidence["code_surface_sha256"], code_surface_digest(root))

        admitted = feature_contract.admit_feature_evidence(
            root, FEATURE.feature_id, evidence["head"], error_cls=noodles.GateError
        )
        self.assertEqual(admitted, evidence)
        self.assertEqual(cmd(["git", "status", "--porcelain=v1", "--untracked-files=all"], root), "")

    def test_committed_skill_canary_rebinds_head_and_artifact_digest(self) -> None:
        root = self.candidate_copy()
        original_digest = code_surface_digest(root)
        surface = root / FEATURE.code_surface
        surface.write_text(surface.read_text() + "\n<!-- bounded canary fixture -->\n", encoding="utf-8")
        cmd(["git", "add", FEATURE.code_surface], root)
        cmd(["git", "commit", "-q", "-m", "test: plant bounded skill canary"], root)

        evidence = feature_contract.verify_feature(root, FEATURE.feature_id, error_cls=noodles.GateError)

        self.assertEqual(evidence["head"], cmd(["git", "rev-parse", "HEAD"], root))
        self.assertEqual(evidence["code_surface_sha256"], code_surface_digest(root))
        self.assertNotEqual(evidence["code_surface_sha256"], original_digest)
        self.assertEqual(evidence["observed"], {"returncode": 0, "ok": True, "errors": []})
        self.assertEqual(cmd(["git", "status", "--porcelain=v1", "--untracked-files=all"], root), "")

    def test_operation_that_never_touches_the_real_artifact_fails_closed(self) -> None:
        root = self.candidate_copy()
        surface = root / FEATURE.code_surface
        surface.write_text(
            surface.read_text().replace(
                skill_contract.EXECUTE_VERIFICATION_P_CLASS_PHRASE,
                "Verification skill output may be trusted once the skill exists on disk.",
                1,
            ),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(noodles.GateError, "oracle rejected observed"):
            feature_contract.verify_feature(root, FEATURE.feature_id, error_cls=noodles.GateError)
        self.assertFalse((root / feature_contract.EVIDENCE_PATH).exists())

    def test_operation_reporting_failure_is_not_admitted(self) -> None:
        root = self.candidate_copy()
        (root / ".noodle.toml").write_text(
            (root / ".noodle.toml").read_text().replace('mode = "supervised"', 'mode = "auto"'), encoding="utf-8"
        )
        cmd(["git", "add", "-A"], root)
        cmd(["git", "commit", "-q", "-m", "planted operation failure"], root)
        with self.assertRaisesRegex(noodles.GateError, "operation .* failed"):
            feature_contract.verify_feature(root, FEATURE.feature_id, error_cls=noodles.GateError)

    def test_missing_issue_feature_is_structurally_valid_but_unknown_declared_feature_is_deferred(self) -> None:
        for feature_id in ("", "   ", None, "some-other-feature"):
            with self.subTest(feature_id=feature_id):
                with self.assertRaises(noodles.GateError):
                    feature_contract.resolve_feature(feature_id, error_cls=noodles.GateError)
        marker_free = noodles.parse_issue_contract(ISSUE_BODY.replace(ISSUE_FEATURE_MARKER, ""), SUBJECT)
        self.assertEqual(marker_free["feature"], "")
        unknown = noodles.parse_issue_contract(ISSUE_BODY.replace(FEATURE.feature_id, "some-other-feature"), SUBJECT)
        self.assertEqual(unknown["feature"], "some-other-feature")
        self.assertEqual(noodles.parse_issue_contract(ISSUE_BODY, SUBJECT)["feature"], FEATURE.feature_id)

    def test_baseline_acceptance_binds_exact_head_tree_and_operations(self) -> None:
        root = self.candidate_copy()
        head = cmd(["git", "rev-parse", "HEAD"], root)
        results = (
            mock.Mock(returncode=0, stdout="tests passed", stderr=""),
            mock.Mock(returncode=0, stdout=json.dumps({"ok": True, "errors": []}), stderr=""),
        )
        with mock.patch.object(feature_contract, "_run_operation", side_effect=results):
            evidence = feature_contract.verify_acceptance(root, None, error_cls=noodles.GateError)
        self.assertEqual(evidence["head"], head)
        self.assertEqual(evidence["tree"], cmd(["git", "rev-parse", "HEAD^{tree}"], root))
        self.assertEqual(evidence["baseline"]["contract_id"], feature_contract.BASELINE_CONTRACT_ID)
        self.assertIsNone(evidence["specialized"])

    def test_baseline_is_mandatory_and_specialized_is_additive(self) -> None:
        root = self.candidate_copy()
        head = cmd(["git", "rev-parse", "HEAD"], root)
        packet = acceptance_evidence(root, head, FEATURE)
        path = root / feature_contract.ACCEPTANCE_EVIDENCE_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(packet), encoding="utf-8")
        admitted = feature_contract.admit_acceptance_evidence(
            root, FEATURE.feature_id, head, error_cls=noodles.GateError
        )
        self.assertEqual(admitted, packet)
        packet["baseline"] = None
        path.write_text(json.dumps(packet), encoding="utf-8")
        with self.assertRaisesRegex(noodles.GateError, "baseline acceptance"):
            feature_contract.admit_acceptance_evidence(root, FEATURE.feature_id, head, error_cls=noodles.GateError)

    def test_baseline_rejects_dirty_residue_before_running_operations(self) -> None:
        root = self.candidate_copy()
        (root / "untracked-residue.txt").write_text("residue", encoding="utf-8")
        with mock.patch.object(feature_contract, "_run_operation") as operation:
            with self.assertRaisesRegex(noodles.GateError, "zero residue"):
                feature_contract.verify_acceptance(root, None, error_cls=noodles.GateError)
        operation.assert_not_called()

    def test_contract_without_operation_or_oracle_fails_closed(self) -> None:
        hollow = feature_contract.FeatureContract(
            feature_id="hollow-feature", code_surface=FEATURE.code_surface, operation=(), oracle_phrases=(), oracle=""
        )
        with mock.patch.dict(feature_contract.ADMITTED_FEATURES, {hollow.feature_id: hollow}):
            with self.assertRaisesRegex(noodles.GateError, "no code surface, product operation, and oracle"):
                feature_contract.verify_feature(CANDIDATE_ROOT, hollow.feature_id, error_cls=noodles.GateError)

    def test_verify_rejects_execute_surface_without_verification_route_contract(self) -> None:
        root = self.candidate_copy()
        cases = (
            (skill_contract.EXECUTE_VERIFICATION_ROUTE, "verification-skill fixture"),
            (skill_contract.EXECUTE_VERIFICATION_P_CLASS_PHRASE, "verification-skill P-class refusal"),
        )
        for phrase, label in cases:
            with self.subTest(contract=label):
                surface = root / FEATURE.code_surface
                content = surface.read_text()
                self.assertIn(phrase, content)
                surface.write_text(content.replace(phrase, "Route freely.", 1), encoding="utf-8")
                result = noodles.verify_repository(root, CANDIDATE_ROOT)
                surface.write_text(content, encoding="utf-8")
                self.assertFalse(result["ok"])
                self.assertTrue(any(label in item for item in result["errors"]), result["errors"])


class FeatureEvidenceHandoffTests(unittest.TestCase):
    """The L gate resolves the Issue's feature contract and admits only exact-head physical evidence."""

    def setUp(self) -> None:
        self.temp, self.root, self.binary, self.session_id = handoff_fixture(CANDIDATE_ROOT, subject=SUBJECT)
        self.addCleanup(self.temp.cleanup)
        self.head = cmd(["git", "rev-parse", "HEAD"], self.root)
        failed_run = {
            "run": {
                "id": 91,
                "head_sha": self.head,
                "status": "completed",
                "conclusion": "failure",
                "run_attempt": 1,
                "pull_request_numbers": [44],
            }
        }
        self.failed_run_patch = mock.patch.object(
            github_protection,
            "failed_required_workflow_run_readback",
            return_value=failed_run,
        )
        self.gh_api_patch = mock.patch.object(noodles, "gh_api", return_value=None)
        self.trusted_run_patch = mock.patch.object(
            github_protection,
            "trusted_workflow_run_readback",
            return_value=failed_run,
        )
        self.failed_run_patch.start()
        self.trusted_run_patch.start()
        self.gh_api_patch.start()
        self.addCleanup(self.failed_run_patch.stop)
        self.addCleanup(self.trusted_run_patch.stop)
        self.addCleanup(self.gh_api_patch.stop)
        self.pr = {
            "state": "open",
            "draft": False,
            "body": f"Refs {SUBJECT}",
            "head": {"sha": self.head},
            "base": {"ref": "main"},
        }

    def handoff(self) -> tuple[mock.MagicMock, object]:
        with mock.patch.dict(os.environ, {"NOODLE_SESSION_ID": self.session_id}, clear=False), \
             mock.patch.object(noodles, "issue_read", return_value={"body": ISSUE_BODY}), \
             mock.patch.object(noodles, "issue_set_state") as set_state:
            return set_state, noodles.execute_handoff(self.root, SUBJECT, 44, self.pr)

    def assert_rejected(self, pattern: str) -> None:
        with mock.patch.dict(os.environ, {"NOODLE_SESSION_ID": self.session_id}, clear=False), \
             mock.patch.object(noodles, "issue_read", return_value={"body": ISSUE_BODY}), \
             mock.patch.object(noodles, "issue_set_state") as set_state:
            with self.assertRaisesRegex(noodles.GateError, pattern):
                noodles.execute_handoff(self.root, SUBJECT, 44, self.pr)
        set_state.assert_not_called()
        events = (self.root / ".noodle" / "sessions" / self.session_id / "events.ndjson").read_text()
        self.assertNotIn("stage_message", events)

    def test_positive_control_admits_verified_feature_evidence(self) -> None:
        write_acceptance_evidence(self.root, self.head, FEATURE)
        set_state, receipt = self.handoff()
        set_state.assert_called_once_with(SUBJECT, "awaiting_land")
        self.assertEqual(receipt["feature"], FEATURE.feature_id)
        self.assertEqual(receipt["feature_code_surface_sha256"], code_surface_digest(self.root))

    def test_marker_free_issue_uses_mandatory_baseline_without_specialized_oracle(self) -> None:
        marker_free_body = ISSUE_BODY.replace(ISSUE_FEATURE_MARKER, "")
        write_acceptance_evidence(self.root, self.head)
        with mock.patch.dict(os.environ, {"NOODLE_SESSION_ID": self.session_id}, clear=False), \
             mock.patch.object(noodles, "issue_read", return_value={"body": marker_free_body}), \
             mock.patch.object(noodles, "issue_set_state") as set_state:
            receipt = noodles.execute_handoff(self.root, SUBJECT, 44, self.pr)
        set_state.assert_called_once_with(SUBJECT, "awaiting_land")
        self.assertEqual(receipt["acceptance"], feature_contract.BASELINE_CONTRACT_ID)
        self.assertIsNone(receipt["feature"])

    def test_wrong_tree_baseline_evidence_fails_closed(self) -> None:
        write_acceptance_evidence(self.root, self.head, FEATURE, tree="0" * 40)
        self.assert_rejected("stale acceptance evidence tree")

    def test_skipped_verifier_fails_closed(self) -> None:
        self.assert_rejected("verifier was skipped")

    def test_stale_wrong_head_evidence_fails_closed(self) -> None:
        write_acceptance_evidence(self.root, "f" * 40, FEATURE)
        self.assert_rejected("stale acceptance evidence head")

    def test_agent_self_report_alone_fails_closed(self) -> None:
        (self.root / feature_contract.ACCEPTANCE_EVIDENCE_PATH).write_text(
            json.dumps({"feature_id": FEATURE.feature_id, "verified": True, "note": "I ran the operation"}),
            encoding="utf-8",
        )
        self.assert_rejected("agent self-report")

    def test_evidence_that_never_observed_the_real_artifact_fails_closed(self) -> None:
        packet = acceptance_evidence(self.root, self.head, FEATURE)
        packet["specialized"]["code_surface_sha256"] = "0" * 64
        (self.root / feature_contract.ACCEPTANCE_EVIDENCE_PATH).write_text(json.dumps(packet), encoding="utf-8")
        self.assert_rejected("never observed the real artifact")

    def test_evidence_without_declared_operation_or_passing_observation_fails_closed(self) -> None:
        packet = acceptance_evidence(self.root, self.head, FEATURE)
        packet["specialized"]["operation"] = ["true"]
        (self.root / feature_contract.ACCEPTANCE_EVIDENCE_PATH).write_text(json.dumps(packet), encoding="utf-8")
        self.assert_rejected("records no declared operation")
        packet = acceptance_evidence(self.root, self.head, FEATURE)
        packet["specialized"]["observed"] = {"returncode": 1, "ok": False, "errors": ["boom"]}
        (self.root / feature_contract.ACCEPTANCE_EVIDENCE_PATH).write_text(json.dumps(packet), encoding="utf-8")
        self.assert_rejected("does not record a passing declared operation")

    def test_unadmitted_issue_feature_id_fails_closed(self) -> None:
        write_acceptance_evidence(self.root, self.head, FEATURE)
        with mock.patch.dict(os.environ, {"NOODLE_SESSION_ID": self.session_id}, clear=False), \
             mock.patch.object(
                 noodles,
                 "issue_read",
                 return_value={"body": ISSUE_BODY.replace(FEATURE.feature_id, "ghost-feature")},
             ), \
             mock.patch.object(noodles, "issue_set_state") as set_state:
            with self.assertRaisesRegex(noodles.GateError, "unadmitted noodles-feature"):
                noodles.execute_handoff(self.root, SUBJECT, 44, self.pr)
        set_state.assert_not_called()


if __name__ == "__main__":
    unittest.main()

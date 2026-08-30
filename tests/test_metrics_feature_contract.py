"""Instantiate the #19 feature-contract machinery for the real `./noodles metrics --json` CLI path:
same generic verify/admit pipeline, a metrics-specific oracle that independently recomputes a
source-tree metric instead of trusting a self-reported ok/errors envelope."""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import feature_contract
import github_protection
import noodles
from tests.support import (
    CANDIDATE_ROOT,
    ISSUE_DEPENDS_ON_MARKER,
    cmd,
    code_surface_digest,
    copy_tracked,
    handoff_fixture,
    write_acceptance_evidence,
)

FEATURE = feature_contract.METRICS_CLI_FEATURE
SUBJECT = "ed3c/noodles#20"
ISSUE_FEATURE_MARKER = f"<!-- noodles-feature: {FEATURE.feature_id} -->"
ISSUE_BODY = (
    "<!-- noodles-role: repository-mutating-atom -->\n"
    "<!-- noodles-target: ed3c/noodles -->\n"
    f"<!-- noodles-subject: {SUBJECT} -->\n"
    "<!-- noodles-state: ready -->\n"
    f"{ISSUE_FEATURE_MARKER}\n"
    f"{ISSUE_DEPENDS_ON_MARKER}\n"
)


def real_tracked_files(root: Path) -> int:
    """Independent readback used only to assert against: the metrics command's own stdout at HEAD."""
    listing = cmd(["git", "ls-tree", "-r", "HEAD"], root)
    return sum(1 for line in listing.splitlines() if line.split(" ", 1)[0] in {"100644", "100755"})


class MetricsFeatureVerifierTests(unittest.TestCase):
    """The real ./noodles metrics --json command must physically run and the oracle must
    independently recompute the reported metric from the git tree, not trust the CLI's own report."""

    def candidate_copy(self) -> Path:
        temp = tempfile.TemporaryDirectory(prefix="noodles-metrics-feature-test-")
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
        self.assertEqual(evidence["head"], cmd(["git", "rev-parse", "HEAD"], root))
        self.assertEqual(evidence["code_surface"], FEATURE.code_surface)
        self.assertEqual(evidence["code_surface_sha256"], code_surface_digest(root, FEATURE))

        # constraint: the CLI-reported tracked_files must equal an independently recomputed count at the same head.
        real = subprocess.run(
            [str(root / "noodles"), "--root", str(root), "metrics", "--json"],
            cwd=root, text=True, capture_output=True, check=True,
        )
        self.assertEqual(json.loads(real.stdout)["tracked_files"], real_tracked_files(root))
        self.assertEqual(evidence["observed"]["ok"], True)
        self.assertEqual(evidence["observed"]["returncode"], 0)
        self.assertEqual(evidence["observed"]["oracle_metric_value"], real_tracked_files(root))

        admitted = feature_contract.admit_feature_evidence(
            root, FEATURE.feature_id, evidence["head"], error_cls=noodles.GateError
        )
        self.assertEqual(admitted, evidence)
        self.assertEqual(cmd(["git", "status", "--porcelain=v1", "--untracked-files=all"], root), "")

    def test_wrong_feature_id_fails_closed(self) -> None:
        for feature_id in ("", "   ", None, "some-other-feature", "verification-skill-oracle-typo"):
            with self.subTest(feature_id=feature_id):
                with self.assertRaises(noodles.GateError):
                    feature_contract.resolve_feature(feature_id, error_cls=noodles.GateError)

    def test_changed_code_surface_without_contract_coverage_fails_closed(self) -> None:
        root = self.candidate_copy()
        surface = root / FEATURE.code_surface
        content = surface.read_text()
        target = FEATURE.oracle_phrases[0]
        self.assertIn(target, content)
        surface.write_text(content.replace(target, "def repository_metrics(root):", 1), encoding="utf-8")
        with self.assertRaisesRegex(noodles.GateError, "oracle rejected observed"):
            feature_contract.verify_feature(root, FEATURE.feature_id, error_cls=noodles.GateError)
        self.assertFalse((root / feature_contract.EVIDENCE_PATH).exists())

    def test_skipped_command_execution_fails_closed(self) -> None:
        """Never running the declared operation leaves no evidence; nothing self-reported is trusted."""
        root = self.candidate_copy()
        self.assertFalse((root / feature_contract.EVIDENCE_PATH).exists())
        with self.assertRaisesRegex(noodles.GateError, "verifier was skipped"):
            feature_contract.admit_feature_evidence(
                root, FEATURE.feature_id, cmd(["git", "rev-parse", "HEAD"], root), error_cls=noodles.GateError
            )

    def test_malformed_output_fails_closed(self) -> None:
        root = self.candidate_copy()
        surface = root / FEATURE.code_surface
        content = surface.read_text()
        broken = content.replace(
            'print(json.dumps(metrics, indent=2, sort_keys=True) if args.json else json.dumps(metrics, sort_keys=True))',
            'print(json.dumps([metrics]) if args.json else json.dumps(metrics, sort_keys=True))',
            1,
        )
        self.assertNotEqual(broken, content)
        surface.write_text(broken, encoding="utf-8")
        with self.assertRaisesRegex(noodles.GateError, "malformed output"):
            feature_contract.verify_feature(root, FEATURE.feature_id, error_cls=noodles.GateError)
        self.assertFalse((root / feature_contract.EVIDENCE_PATH).exists())

    def test_oracle_rejects_planted_wrong_metric(self) -> None:
        """Edit the reporting line on disk without committing: the CLI subprocess (reads the working
        tree) reports a wrong number while the git-ls-tree oracle (reads the committed head) does not
        move, so the two disagree and the oracle must fail closed instead of accepting the CLI's word."""
        root = self.candidate_copy()
        surface = root / FEATURE.code_surface
        content = surface.read_text()
        planted = content.replace('"tracked_files": len(regular),', '"tracked_files": len(regular) + 1,', 1)
        self.assertNotEqual(planted, content)
        surface.write_text(planted, encoding="utf-8")
        with self.assertRaisesRegex(noodles.GateError, "planted wrong metric"):
            feature_contract.verify_feature(root, FEATURE.feature_id, error_cls=noodles.GateError)
        self.assertFalse((root / feature_contract.EVIDENCE_PATH).exists())


class MetricsFeatureEvidenceHandoffTests(unittest.TestCase):
    """The Issue's declared feature id must force this verifier to execute before handoff admits."""

    def setUp(self) -> None:
        self.temp, self.root, self.binary, self.session_id = handoff_fixture(CANDIDATE_ROOT, subject=SUBJECT)
        self.addCleanup(self.temp.cleanup)
        self.head = cmd(["git", "rev-parse", "HEAD"], self.root)
        failed_run = {
            "run": {"id": 91, "head_sha": self.head, "status": "completed", "conclusion": "failure"}
        }
        self.failed_run_patch = mock.patch.object(
            github_protection,
            "failed_required_workflow_run_readback",
            return_value=failed_run,
        )
        self.gh_api_patch = mock.patch.object(noodles, "gh_api", return_value=None)
        self.failed_run_patch.start()
        self.gh_api_patch.start()
        self.addCleanup(self.failed_run_patch.stop)
        self.addCleanup(self.gh_api_patch.stop)
        self.pr = {
            "state": "open",
            "draft": False,
            "body": f"Refs {SUBJECT}",
            "head": {"sha": self.head},
            "base": {"ref": "main"},
        }

    def assert_rejected(self, pattern: str) -> None:
        with mock.patch.dict(os.environ, {"NOODLE_SESSION_ID": self.session_id}, clear=False), \
             mock.patch.object(noodles, "issue_read", return_value={"body": ISSUE_BODY}), \
             mock.patch.object(noodles, "issue_set_state") as set_state:
            with self.assertRaisesRegex(noodles.GateError, pattern):
                noodles.execute_handoff(self.root, SUBJECT, 44, self.pr)
        set_state.assert_not_called()

    def test_positive_control_admits_verified_feature_evidence(self) -> None:
        write_acceptance_evidence(self.root, self.head, FEATURE)
        with mock.patch.dict(os.environ, {"NOODLE_SESSION_ID": self.session_id}, clear=False), \
             mock.patch.object(noodles, "issue_read", return_value={"body": ISSUE_BODY}), \
             mock.patch.object(noodles, "issue_set_state") as set_state:
            receipt = noodles.execute_handoff(self.root, SUBJECT, 44, self.pr)
        set_state.assert_called_once_with(SUBJECT, "awaiting_land")
        self.assertEqual(receipt["feature"], FEATURE.feature_id)
        self.assertEqual(receipt["feature_code_surface_sha256"], code_surface_digest(self.root, FEATURE))

    def test_skipped_verifier_fails_closed(self) -> None:
        self.assert_rejected("verifier was skipped")

    def test_stale_wrong_head_evidence_fails_closed(self) -> None:
        write_acceptance_evidence(self.root, "f" * 40, FEATURE)
        self.assert_rejected("stale acceptance evidence head")

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

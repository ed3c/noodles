from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import trusted_preview
from tests.support import CANDIDATE_ROOT, cmd, initialize_repo

PINNED_MODULE = '''\
import os
import pathlib
import unittest

ACCEPTED = {accepted}
DECOY = "\\nFAIL: planted decoy line that is diagnostic prose, not a test identity"


class PinnedLiteralTests(unittest.TestCase):
    def test_candidate_keeps_the_pinned_literal(self) -> None:
        candidate = pathlib.Path(os.environ["NOODLES_CANDIDATE_ROOT"]).resolve()
        observed = (candidate / "pinned.txt").read_text(encoding="utf-8").strip()
        self.assertIn(observed, ACCEPTED, DECOY)
'''
PINNED_TEST_ID = "test_candidate_keeps_the_pinned_literal (test_pinned.PinnedLiteralTests.test_candidate_keeps_the_pinned_literal)"


class TrustedPreviewTests(unittest.TestCase):
    def planted_transition_repo(self) -> Path:
        """A repository whose default-branch suite pins a literal the working tree already changed.

        The workflow is copied verbatim from this repository, so the preview reads the real trusted
        env contract and the real trusted command rather than a hand-written stand-in."""
        temp = tempfile.TemporaryDirectory(prefix="noodles-trusted-preview-test-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / "repo"
        (root / ".github/workflows").mkdir(parents=True)
        (root / "tests").mkdir()
        shutil.copy2(CANDIDATE_ROOT / ".github/workflows/verify.yml", root / ".github/workflows/verify.yml")
        (root / "tests/test_pinned.py").write_text(PINNED_MODULE.format(accepted='{"alpha"}'), encoding="utf-8")
        (root / "pinned.txt").write_text("alpha\n", encoding="utf-8")
        initialize_repo(root)
        (root / "pinned.txt").write_text("beta\n", encoding="utf-8")
        return root

    def stage_widened_acceptance(self, root: Path) -> None:
        cmd(["git", "checkout", "-q", "-b", "staged"], root)
        (root / "tests/test_pinned.py").write_text(PINNED_MODULE.format(accepted='{"alpha", "beta"}'), encoding="utf-8")
        cmd(["git", "add", "tests/test_pinned.py"], root)
        cmd(["git", "commit", "-q", "-m", "widen acceptance"], root)

    def test_planted_pinned_literal_reds_locally_and_greens_after_a_staged_default_branch(self) -> None:
        root = self.planted_transition_repo()

        deadlocked = trusted_preview.preview_trusted_verify(root, trusted_ref="main", error_cls=AssertionError, timeout=120)

        self.assertFalse(deadlocked["ok"], deadlocked["tail"])
        self.assertIn("FAIL: planted decoy line", "\n".join(deadlocked["tail"]))
        self.assertEqual(deadlocked["would_red"], [PINNED_TEST_ID])
        self.assertEqual(deadlocked["diagnostic"], trusted_preview.STAGING_RECIPE)
        self.assertEqual(deadlocked["trusted_sha"], cmd(["git", "rev-parse", "main"], root))
        self.assertEqual(deadlocked["fetch"], "skipped: 'main' names no remote")

        self.stage_widened_acceptance(root)
        staged = trusted_preview.preview_trusted_verify(root, trusted_ref="staged", error_cls=AssertionError, timeout=120)

        self.assertTrue(staged["ok"], staged["tail"])
        self.assertEqual(staged["would_red"], [])
        self.assertIsNone(staged["diagnostic"])
        self.assertEqual((root / "pinned.txt").read_text(encoding="utf-8").strip(), "beta")

    def test_preview_env_and_command_are_read_back_from_the_trusted_workflow(self) -> None:
        root = self.planted_transition_repo()

        receipt = trusted_preview.preview_trusted_verify(root, trusted_ref="main", error_cls=AssertionError, timeout=120)

        workspace = Path(receipt["env"]["PYTHONPATH"]).parent
        self.assertEqual(receipt["env_contract"], {"NOODLES_CANDIDATE_ROOT": f"{trusted_preview.WORKSPACE_EXPRESSION}/.candidate", "PYTHONPATH": f"{trusted_preview.WORKSPACE_EXPRESSION}/.trusted", "NOODLES_OFFLINE_TESTS": "1"})
        self.assertEqual(receipt["env"], {"NOODLES_CANDIDATE_ROOT": f"{workspace}/.candidate", "PYTHONPATH": f"{workspace}/.trusted", "NOODLES_OFFLINE_TESTS": "1"})
        self.assertEqual(receipt["command"], "python3 -m unittest discover -s .trusted/tests -v")
        self.assertEqual(receipt["candidate_root"], str(root.resolve()))

    def test_absent_trusted_controls_step_fails_closed_instead_of_reporting_green(self) -> None:
        root = self.planted_transition_repo()
        cmd(["git", "checkout", "-q", "-b", "workflowless"], root)
        cmd(["git", "rm", "-q", ".github/workflows/verify.yml"], root)
        cmd(["git", "commit", "-q", "-m", "drop trusted workflow"], root)

        with self.assertRaises(AssertionError) as raised:
            trusted_preview.preview_trusted_verify(root, trusted_ref="workflowless", error_cls=AssertionError, timeout=120)

        self.assertIn("trusted verify workflow absent", str(raised.exception))


if __name__ == "__main__":
    unittest.main()

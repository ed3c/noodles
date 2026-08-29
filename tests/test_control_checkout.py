from __future__ import annotations

import unittest
from pathlib import Path

import noodles
from tests.support import cmd, control_checkout_fixture


class ControlCheckoutAdmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp, self.root, self.provider = control_checkout_fixture()
        self.addCleanup(self.temp.cleanup)

    def provider_commit(self, relative: str, content: str, message: str) -> str:
        path = self.provider / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        cmd(["git", "add", relative], self.provider)
        cmd(["git", "commit", "-q", "-m", message], self.provider)
        return cmd(["git", "rev-parse", "HEAD"], self.provider)

    def control_commit(self, relative: str, content: str, message: str) -> str:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        cmd(["git", "add", relative], self.root)
        cmd(["git", "commit", "-q", "-m", message], self.root)
        return cmd(["git", "rev-parse", "HEAD"], self.root)

    def test_clean_default_branch_at_provider_head_passes_with_readback(self) -> None:
        receipt = noodles.control_checkout_admission(self.root)
        self.assertEqual(receipt["branch"], "main")
        self.assertEqual(receipt["local_head"], cmd(["git", "rev-parse", "HEAD"], self.root))
        self.assertEqual(receipt["provider_head"], cmd(["git", "rev-parse", "HEAD"], self.provider))
        self.assertEqual(receipt["relation"], "equal")
        self.assertEqual(receipt["porcelain"], [])
        self.assertEqual(receipt["ignored"], [])
        self.assertTrue(receipt["clean"])

    def test_ignored_runtime_evidence_remains_admitted_via_git_readback(self) -> None:
        runtime_receipt = self.root / ".noodle/runtime/receipt.json"
        runtime_receipt.parent.mkdir(parents=True, exist_ok=True)
        runtime_receipt.write_text("{}\n", encoding="utf-8")
        worktree_marker = self.root / ".worktrees/tmp/marker.txt"
        worktree_marker.parent.mkdir(parents=True, exist_ok=True)
        worktree_marker.write_text("ignored\n", encoding="utf-8")

        receipt = noodles.control_checkout_admission(self.root)

        self.assertEqual(receipt["porcelain"], [])
        self.assertTrue(any(".noodle/runtime" in line for line in receipt["ignored"]))
        self.assertTrue(any(".worktrees" in line for line in receipt["ignored"]))
        self.assertTrue(receipt["clean"])

    def test_reconcile_clean_default_branch_at_provider_head_passes_with_readback(self) -> None:
        receipt = noodles.reconcile_checkout_admission(self.root)
        self.assertEqual(receipt["branch"], "main")
        self.assertEqual(receipt["local_head"], cmd(["git", "rev-parse", "HEAD"], self.root))
        self.assertEqual(receipt["provider_head"], cmd(["git", "rev-parse", "HEAD"], self.provider))
        self.assertEqual(receipt["relation"], "equal")
        self.assertEqual(receipt["porcelain"], [])
        self.assertEqual(receipt["ignored"], [])
        self.assertTrue(receipt["clean"])

    def test_tracked_dirty_checkout_fails_closed(self) -> None:
        path = self.root / "README.md"
        path.write_text(path.read_text(encoding="utf-8") + "\ntracked dirty\n", encoding="utf-8")
        with self.assertRaisesRegex(noodles.GateError, "non-ignored changes"):
            noodles.control_checkout_admission(self.root)

    def test_reconcile_tracked_dirty_checkout_fails_closed(self) -> None:
        path = self.root / "README.md"
        path.write_text(path.read_text(encoding="utf-8") + "\ntracked dirty\n", encoding="utf-8")
        with self.assertRaisesRegex(noodles.GateError, "non-ignored changes"):
            noodles.reconcile_checkout_admission(self.root)

    def test_untracked_nonignored_checkout_fails_closed(self) -> None:
        (self.root / "scratch.txt").write_text("dirty\n", encoding="utf-8")
        with self.assertRaisesRegex(noodles.GateError, "non-ignored changes"):
            noodles.control_checkout_admission(self.root)

    def test_reconcile_untracked_nonignored_checkout_fails_closed(self) -> None:
        (self.root / "scratch.txt").write_text("dirty\n", encoding="utf-8")
        with self.assertRaisesRegex(noodles.GateError, "non-ignored changes"):
            noodles.reconcile_checkout_admission(self.root)

    def test_wrong_branch_fails_closed(self) -> None:
        cmd(["git", "checkout", "-q", "-b", "topic"], self.root)
        with self.assertRaisesRegex(noodles.GateError, "default branch main"):
            noodles.control_checkout_admission(self.root)

    def test_reconcile_wrong_branch_fails_closed(self) -> None:
        cmd(["git", "checkout", "-q", "-b", "topic"], self.root)
        with self.assertRaisesRegex(noodles.GateError, "default branch main"):
            noodles.reconcile_checkout_admission(self.root)

    def test_behind_checkout_fails_closed(self) -> None:
        provider_head = self.provider_commit("behind.txt", "provider ahead\n", "provider ahead")
        with self.assertRaisesRegex(noodles.GateError, "behind"):
            noodles.control_checkout_admission(self.root)
        self.assertEqual(provider_head, cmd(["git", "rev-parse", "HEAD"], self.provider))

    def test_reconcile_behind_checkout_passes_with_readback(self) -> None:
        local_head = cmd(["git", "rev-parse", "HEAD"], self.root)
        provider_head = self.provider_commit("behind.txt", "provider ahead\n", "provider ahead")
        receipt = noodles.reconcile_checkout_admission(self.root)
        self.assertEqual(receipt["branch"], "main")
        self.assertEqual(receipt["local_head"], local_head)
        self.assertEqual(receipt["provider_head"], provider_head)
        self.assertEqual(receipt["relation"], "behind")
        self.assertTrue(receipt["clean"])

    def test_ahead_checkout_fails_closed(self) -> None:
        local_head = self.control_commit("ahead.txt", "local ahead\n", "local ahead")
        with self.assertRaisesRegex(noodles.GateError, "ahead"):
            noodles.control_checkout_admission(self.root)
        self.assertEqual(local_head, cmd(["git", "rev-parse", "HEAD"], self.root))

    def test_reconcile_ahead_checkout_fails_closed(self) -> None:
        local_head = self.control_commit("ahead.txt", "local ahead\n", "local ahead")
        with self.assertRaisesRegex(noodles.GateError, "ahead"):
            noodles.reconcile_checkout_admission(self.root)
        self.assertEqual(local_head, cmd(["git", "rev-parse", "HEAD"], self.root))

    def test_diverged_checkout_fails_closed(self) -> None:
        self.control_commit("local-only.txt", "local only\n", "local only")
        self.provider_commit("provider-only.txt", "provider only\n", "provider only")
        with self.assertRaisesRegex(noodles.GateError, "diverged"):
            noodles.control_checkout_admission(self.root)

    def test_reconcile_diverged_checkout_fails_closed(self) -> None:
        self.control_commit("local-only.txt", "local only\n", "local only")
        self.provider_commit("provider-only.txt", "provider only\n", "provider only")
        with self.assertRaisesRegex(noodles.GateError, "diverged"):
            noodles.reconcile_checkout_admission(self.root)

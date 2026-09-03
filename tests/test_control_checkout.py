from __future__ import annotations

import ast
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import noodles
import tests.support as support
from tests.support import CANDIDATE_ROOT, clone_fixture, cmd, control_checkout_fixture, initialize_repo


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


CLONE_ARGV_HEAD = ("git", "clone")
CLONE_OWNER = "clone_fixture"


def clone_argv_sites(source: str, label: str) -> list[str]:
    """Every `["git", "clone", ...]` argv literal in `source`, as `<label>:<line> in <function>`.

    ed3c/noodles#359 - the coverage instrument. A count would answer "how many did I fix"; this
    answers "which sites exist", so a clone added tomorrow at a site nobody thought of is named rather
    than silently uncovered. The head is a TUPLE constant, never a list literal, so this detector
    cannot match its own source."""
    owner: dict[int, str] = {}

    def visit(node: ast.AST, function: str) -> None:
        for child in ast.iter_child_nodes(node):
            name = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else function
            if isinstance(child, ast.List):
                head = tuple(item.value for item in child.elts[:2] if isinstance(item, ast.Constant))
                if head == CLONE_ARGV_HEAD:
                    owner[child.lineno] = name
            visit(child, name)

    visit(ast.parse(source, filename=label), "<module>")
    return [f"{label}:{line} in {owner[line]}" for line in sorted(owner)]


class FixtureCloneRaceImmunityTests(unittest.TestCase):
    """ed3c/noodles#359 - the setup-side sibling of the ed3c/noodles#319 teardown race.

    A `candidate-self-tests` run was lost at SETUP to `git clone ... fatal: hardlink different from
    source` and never had a home. `support.clone_fixture` carries the cure and its full receipt,
    including why `--no-hardlinks` is not it. These are the controls: the coverage sweep that says
    which sites the cure reaches, a deterministic red-then-green pair for the retry itself, and one
    live concurrent writer showing setup surviving it.

    Honest about direction: the concurrent-writer control asserts only that setup does NOT fail. Its
    RED direction is the recorded reproduction in `clone_fixture`'s docstring (4/150 and 3/150 across
    the two forms), not an assertion here - a test that demanded the race fire would itself be the
    coin flip ed3c/noodles#310 and ed3c/noodles#312 exist to refuse."""

    def source_repo(self) -> tuple[Path, Path]:
        temp = tempfile.TemporaryDirectory(prefix="noodles-fixture-clone-test-", ignore_cleanup_errors=True)
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        source = base / "source"
        source.mkdir()
        (source / "seed.txt").write_text("seed\n", encoding="utf-8")
        initialize_repo(source)
        return base, source

    def test_every_clone_in_the_trusted_suite_routes_through_the_race_immune_form(self) -> None:
        sites = [
            site
            for path in sorted((CANDIDATE_ROOT / "tests").rglob("*.py"))
            for site in clone_argv_sites(path.read_text(encoding="utf-8"), path.relative_to(CANDIDATE_ROOT).as_posix())
        ]
        offenders = [site for site in sites if not site.endswith(f" in {CLONE_OWNER}")]

        self.assertTrue(sites, "the sweep enumerated no clone at all; the detector stopped seeing the shape it sweeps")
        self.assertEqual(offenders, [])

    def test_planted_negative_a_clone_outside_the_owner_is_named_not_silently_covered(self) -> None:
        planted = (
            "def helper(source, destination, cwd):\n"
            '    cmd(["git", "clone", "-q", str(source), str(destination)], cwd)\n'
        )
        sites = clone_argv_sites(planted, "planted.py")

        self.assertTrue(sites)
        self.assertIn("in helper", sites[0])
        self.assertFalse(any(site.endswith(f" in {CLONE_OWNER}") for site in sites))

    def test_positive_control_a_quiet_source_clones_to_the_same_head(self) -> None:
        base, source = self.source_repo()
        destination = base / "clone"

        clone_fixture(source, destination, base)

        self.assertEqual(cmd(["git", "rev-parse", "HEAD"], destination), cmd(["git", "rev-parse", "HEAD"], source))

    def test_a_first_attempt_that_loses_leaves_nothing_behind_and_the_next_one_wins(self) -> None:
        """Deterministic stand-in for the race: something is in the way, exactly once.

        The real writer is unidentified and low-rate, so it cannot be the trigger a control depends
        on. What the cure actually promises is testable without it - a failed attempt is cleaned up
        and retaken - and this input makes git refuse the first attempt for certain."""
        base, source = self.source_repo()
        destination = base / "clone"
        destination.mkdir()
        (destination / "in-the-way.txt").write_text("occupied\n", encoding="utf-8")

        clone_fixture(source, destination, base)

        self.assertEqual(cmd(["git", "rev-parse", "HEAD"], destination), cmd(["git", "rev-parse", "HEAD"], source))
        self.assertFalse((destination / "in-the-way.txt").exists())

    def test_planted_negative_the_same_input_reds_when_the_retry_is_taken_away(self) -> None:
        base, source = self.source_repo()
        destination = base / "clone"
        destination.mkdir()
        (destination / "in-the-way.txt").write_text("occupied\n", encoding="utf-8")

        with mock.patch.object(support, "FIXTURE_CLONE_ATTEMPTS", 1):
            with self.assertRaises(AssertionError) as raised:
                clone_fixture(source, destination, base)

        self.assertIn("already exists", str(raised.exception))

    def test_a_source_that_is_being_written_during_the_clone_does_not_fail_setup(self) -> None:
        base, source = self.source_repo()
        stop = threading.Event()

        def churn() -> None:
            tick = 0
            while not stop.is_set():
                tick += 1
                (source / "churn.txt").write_text(f"churn {tick}\n", encoding="utf-8")
                for argv in (["git", "add", "churn.txt"], ["git", "commit", "-q", "-m", f"churn {tick}"],
                             ["git", "repack", "-a", "-d", "-q"], ["git", "gc", "--prune=now", "--quiet"]):
                    try:
                        cmd(argv, source)
                    except AssertionError:
                        return

        writer = threading.Thread(target=churn, daemon=True)
        writer.start()
        self.addCleanup(writer.join, 30)
        self.addCleanup(stop.set)
        for index in range(5):
            with self.subTest(clone=index):
                destination = base / f"clone-{index}"
                clone_fixture(source, destination, base)
                self.assertTrue((destination / ".git").is_dir())

    def test_a_source_that_is_genuinely_broken_still_fails_with_gits_own_diagnostic(self) -> None:
        base, _ = self.source_repo()

        with self.assertRaises(AssertionError) as raised:
            clone_fixture(base / "absent", base / "clone", base)

        self.assertIn("does not exist", str(raised.exception))

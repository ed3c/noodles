"""ed3c/noodles#433 - the lander is the one singleton no worktree isolates, so pin the logic it runs.

`workflow_run` always executes the DEFAULT BRANCH's copy of the entry workflow file. That is a
platform fact and no amount of repository design changes it: the entry is unpinnable by
construction. What the platform does allow is for that entry to be thin - to resolve a revision out
of trusted policy, check it out over itself, and let every later step run those bytes. A lander
change then MERGES dead and ACTIVATES by moving one value, instead of going live the instant it
lands and being curable only by a revert that has to pass through the queue it may have broken.

The two directions this module drives are the whole claim:

* pin unmoved - a merged lander-logic change alters nothing, because the entry keeps executing the
  revision the pin names;
* pin flipped - the same merged change becomes live, and flipping back restores the previous bytes
  byte-identically rather than approximately.

Both run against a real local git repository whose "lander logic" is one file, so the pin's effect
is a byte comparison rather than a mocked assertion about one. The second half of the module holds
the entry itself to declaring the handoff: `lander_shim_errors` reads the candidate's own land.yml,
and the planted negative proves `verify_repository` really consumes it rather than merely defining
it.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import noodles
from tests.support import ENGINE_ROOT, copy_tracked

LANDER_FILE = "lander_logic.txt"
BASELINE = "landing logic as it stands today\n"
PLANTED = "landing logic with a merged change that must stay dead until the pin moves\n"


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=str(root), text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {completed.stderr.strip()}")
    return completed.stdout.strip()


def _commit(root: Path, message: str, *, lander: str, pin: str) -> str:
    (root / LANDER_FILE).write_text(lander, encoding="utf-8")
    (root / "policy/github.json").write_text(json.dumps({"lander_pin": pin}, indent=2) + "\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=noodles-fixture", "-c", "user.email=fixture@example.invalid", "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "HEAD")


class LanderPinActivationTests(unittest.TestCase):
    """The pin decides which bytes land, and nothing else does."""

    def build(self, work: Path) -> tuple[Path, dict[str, str]]:
        """A four-commit history that replays a lander change's whole life: merged, activated, reverted.

        No remote is configured on purpose. `lander_checkout` fetches only an object it does not
        already have, so a local history exercises the real production function rather than a mock
        of it, and an accidental network dependency in that function would red here."""
        root = work / "repo"
        (root / "policy").mkdir(parents=True)
        _git(root, "init", "--quiet", "-b", "main")
        revisions = {}
        revisions["baseline"] = _commit(root, "baseline lander", lander=BASELINE, pin="0" * 40)
        revisions["merged"] = _commit(root, "merge the lander change with the pin unmoved", lander=PLANTED, pin=revisions["baseline"])
        revisions["activated"] = _commit(root, "flip the pin forward", lander=PLANTED, pin=revisions["merged"])
        revisions["reverted"] = _commit(root, "flip the pin back", lander=PLANTED, pin=revisions["baseline"])
        return root, revisions

    def probe(self, root: Path, tip: str) -> tuple[dict, bytes]:
        """Run the entry at `tip` exactly as the land job does, and read the landing bytes back."""
        _git(root, "checkout", "--force", "--quiet", tip)
        receipt = noodles.lander_checkout(root)
        return receipt, (root / LANDER_FILE).read_bytes()

    def test_a_merged_lander_change_stays_dead_while_the_pin_is_unmoved(self) -> None:
        with tempfile.TemporaryDirectory(prefix="noodles-lander-pin-", ignore_cleanup_errors=True) as name:
            root, revisions = self.build(Path(name))
            receipt, landing_bytes = self.probe(root, revisions["merged"])
            self.assertEqual(receipt["entry_sha"], revisions["merged"])
            self.assertEqual(receipt["lander_sha"], revisions["baseline"])
            self.assertEqual(receipt["pin"], revisions["baseline"])
            self.assertTrue(receipt["readback"])
            self.assertEqual(landing_bytes, BASELINE.encode("utf-8"))

    def test_a_pin_flip_activates_the_merged_change_and_flipping_back_restores_it_byte_identically(self) -> None:
        with tempfile.TemporaryDirectory(prefix="noodles-lander-pin-", ignore_cleanup_errors=True) as name:
            root, revisions = self.build(Path(name))
            _receipt, before = self.probe(root, revisions["merged"])
            activated_receipt, activated = self.probe(root, revisions["activated"])
            reverted_receipt, after = self.probe(root, revisions["reverted"])
            self.assertEqual(activated_receipt["lander_sha"], revisions["merged"])
            self.assertEqual(activated, PLANTED.encode("utf-8"))
            self.assertEqual(reverted_receipt["lander_sha"], revisions["baseline"])
            self.assertNotEqual(activated, before)
            self.assertEqual(after, before)

    def test_planted_negative_a_pin_that_is_not_a_full_commit_sha_is_refused(self) -> None:
        with tempfile.TemporaryDirectory(prefix="noodles-lander-pin-", ignore_cleanup_errors=True) as name:
            root, revisions = self.build(Path(name))
            _git(root, "checkout", "--force", "--quiet", revisions["merged"])
            for planted in ("", "main", revisions["baseline"][:12], revisions["baseline"] + "0", "z" * 40):
                with self.subTest(pin=planted):
                    (root / "policy/github.json").write_text(json.dumps({"lander_pin": planted}) + "\n", encoding="utf-8")
                    with self.assertRaisesRegex(noodles.GateError, "must be a full 40-hex commit sha"):
                        noodles.lander_checkout(root)

    def test_planted_negative_a_pin_naming_a_revision_that_does_not_exist_refuses(self) -> None:
        """The entry has no remote here, so an unreachable pin is a hard refusal rather than a fetch
        that quietly resolves to whatever the default branch already had."""
        with tempfile.TemporaryDirectory(prefix="noodles-lander-pin-", ignore_cleanup_errors=True) as name:
            root, revisions = self.build(Path(name))
            _git(root, "checkout", "--force", "--quiet", revisions["merged"])
            (root / "policy/github.json").write_text(json.dumps({"lander_pin": "0" * 40}) + "\n", encoding="utf-8")
            with self.assertRaises(noodles.GateError):
                noodles.lander_checkout(root)
            self.assertEqual((root / LANDER_FILE).read_bytes(), PLANTED.encode("utf-8"))


class LanderShimGateTests(unittest.TestCase):
    """The unpinnable entry must declare the handoff, and declare it before it lands anything."""

    def mutated(self, mutate) -> list[str]:
        with tempfile.TemporaryDirectory(prefix="noodles-lander-shim-", ignore_cleanup_errors=True) as name:
            root = Path(name) / "tree"
            root.mkdir(parents=True)
            (root / ".github/workflows").mkdir(parents=True)
            path = root / noodles.LANDER_WORKFLOW_PATH
            path.write_text(mutate((ENGINE_ROOT / noodles.LANDER_WORKFLOW_PATH).read_text(encoding="utf-8")), encoding="utf-8")
            return noodles.lander_shim_errors(root)

    def test_the_shipped_entry_hands_landing_off_to_the_pinned_lander(self) -> None:
        self.assertEqual(noodles.lander_shim_errors(ENGINE_ROOT), [])

    def test_planted_negative_an_entry_with_the_handoff_removed_is_refused(self) -> None:
        errors = self.mutated(lambda text: text.replace(noodles.LANDER_SHIM_BLOCK + "\n", ""))
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("verbatim", errors[0])

    def test_planted_negative_a_handoff_disabled_by_an_if_expression_is_refused(self) -> None:
        errors = self.mutated(
            lambda text: text.replace(
                noodles.LANDER_SHIM_BLOCK,
                noodles.LANDER_SHIM_BLOCK.splitlines()[0] + "\n        if: false\n" + noodles.LANDER_SHIM_BLOCK.splitlines()[1] + "\n",
            )
        )
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("verbatim", errors[0])

    def test_the_ordering_check_reads_a_command_word_not_a_fixed_line(self) -> None:
        """`noodles.py github land` is a prefix of the handoff command, and the merge step's `run:`
        is a folded scalar the trusted boundary readback normalises before comparing - so it may
        legally be reflowed. Both facts are what the ordering check has to survive, and a fixed-line
        search survives neither."""
        folded = "        run: >-\n          python3 noodles.py github land\n"
        flat = "        run: python3 noodles.py github land\n"

        def reflow(text: str) -> str:
            # constraint: a replace() that matched nothing would leave this control green while
            # constraint: proving nothing, so the mutation asserts it really happened.
            self.assertIn(folded, text)
            return text.replace(folded, flat, 1)

        self.assertEqual(self.mutated(reflow), [])

    def test_planted_negative_a_handoff_declared_after_the_merge_step_is_refused(self) -> None:
        def move_after_the_merge(text: str) -> str:
            without = text.replace(noodles.LANDER_SHIM_BLOCK + "\n", "")
            return without.replace("      - name: Mint landing-train push GitHub App token\n", noodles.LANDER_SHIM_BLOCK + "\n      - name: Mint landing-train push GitHub App token\n")

        errors = self.mutated(move_after_the_merge)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("before its pinned-lander handoff", errors[0])

    def test_planted_negative_verify_repository_really_consumes_the_shim_gate(self) -> None:
        """A gate nothing calls is prose. This plants the defect in a full candidate copy and drives
        the repository gate the trusted verify actually runs, so the wiring is what is on trial."""
        with tempfile.TemporaryDirectory(prefix="noodles-lander-wiring-", ignore_cleanup_errors=True) as name:
            candidate = Path(name) / "candidate"
            copy_tracked(ENGINE_ROOT, candidate)
            self.assertEqual(noodles.verify_repository(candidate, ENGINE_ROOT)["errors"], [])
            path = candidate / noodles.LANDER_WORKFLOW_PATH
            path.write_text(path.read_text(encoding="utf-8").replace(noodles.LANDER_SHIM_BLOCK + "\n", ""), encoding="utf-8")
            planted = noodles.verify_repository(candidate, ENGINE_ROOT)["errors"]
            self.assertEqual([error for error in planted if "verbatim" in error], planted)
            self.assertTrue(planted)


if __name__ == "__main__":
    unittest.main()

"""ed3c/noodles#435 - the one-shot protection-apply GHA job built for #389 had no live trigger
once that Issue closed, and its own probe already failed closed at App-token mint: the App
deliberately never holds Administration:write, kept off the same installation key that already
holds Contents:write so a compromised trusted workflow cannot first weaken protection and then
write past it. That left a dead job reading to a future maintainer as "noodles can auto-repair
branch protection" when by adjudication it cannot and should not on this App.

Subtraction, not addition: the dead job is deleted (`.github/workflows/land.yml`) and the
adjudicated capability state is recorded as data where readers look (`policy/github.json`)
instead of prose nobody re-reads. This module holds two physical acceptance halves:

* a repo-wide readback that the dead job left no residue, with a planted-negative control that
  proves the readback would actually catch a lingering reference rather than passing vacuously;
* the recorded capability state itself: `protection_write` is false with a reason naming both
  Administration:write and Contents:write, and the future Protection-Operator App is recorded as
  arrival topology DECLARED, with the receipt path it does not yet have, never claimed EXERCISED.

A third half was cut in reconcile: a fixture that branched on `policy["protection_write"]` and
then asserted the literal dict its own else-branch had just built. Its poisoned `gh_api` recorder
sat in a branch `protection_write: false` makes unreachable, so no production code ran and the
only failure it could ever produce - the flag flipping to true - is already asserted directly and
more cheaply by `test_capability_contract_declares_write_false_read_true_with_reason`.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.support import CANDIDATE_ROOT

GITHUB_POLICY_PATH = CANDIDATE_ROOT / "policy/github.json"
LAND_WORKFLOW_PATH = CANDIDATE_ROOT / ".github/workflows/land.yml"
# constraint: relative, not absolute: under a differing NOODLES_CANDIDATE_ROOT the scanned copy of
# constraint: this module is a different file from `__file__`, so an absolute self-exclusion stops
# constraint: excluding it and the scanner reports its own planted-negative string as residue.
SELF_RELATIVE = Path("tests") / Path(__file__).name
RESIDUE_GLOBS = (
    "*.py",
    "*.md",
    "tests/*.py",
    ".github/workflows/*.yml",
    ".github/workflows/*.md",
    "docs/*.md",
    "docs/**/*.md",
    "policy/*.json",
    "contracts/*.md",
)


def _protection_apply_residue(root: Path) -> list[str]:
    """Every scanned file under root whose bytes still name the dead label trigger, excluding
    this scanner's own module (whose planted-negative control legally contains the label)."""
    hits: list[str] = []
    seen: set[Path] = set()
    for pattern in RESIDUE_GLOBS:
        for path in root.glob(pattern):
            resolved = path.resolve()
            if not path.is_file() or resolved in seen or path.relative_to(root) == SELF_RELATIVE:
                continue
            seen.add(resolved)
            if "protection-apply" in path.read_text(encoding="utf-8", errors="ignore"):
                hits.append(str(path.relative_to(root)))
    return sorted(hits)


class DeadProtectionApplyWorkflowRemovedTests(unittest.TestCase):
    def test_repo_wide_readback_finds_no_protection_apply_residue(self) -> None:
        self.assertEqual(_protection_apply_residue(CANDIDATE_ROOT), [])

    def test_planted_negative_residue_is_caught_not_missed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="noodles-protection-residue-", ignore_cleanup_errors=True) as tmp:
            planted = Path(tmp) / "leftover.md"
            planted.write_text("still wired to protection-apply\n", encoding="utf-8")
            self.assertEqual(_protection_apply_residue(Path(tmp)), ["leftover.md"])

    def test_land_workflow_no_longer_declares_the_dead_job_or_its_trigger(self) -> None:
        workflow = LAND_WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertNotIn("permission-administration: write", workflow)
        self.assertNotIn("types: [labeled]", workflow)
        self.assertIn("\n  land:\n", workflow)


class ProtectionWriteCapabilityContractTests(unittest.TestCase):
    def policy(self) -> dict:
        return json.loads(GITHUB_POLICY_PATH.read_text(encoding="utf-8"))

    def test_capability_contract_declares_write_false_read_true_with_reason(self) -> None:
        policy = self.policy()
        self.assertIs(policy["protection_write"], False)
        self.assertIs(policy["protection_read"], True)
        reason = policy["protection_write_reason"]
        self.assertIsInstance(reason, str)
        self.assertIn("Administration:write", reason)
        self.assertIn("Contents:write", reason)


class ProtectionOperatorAppArrivalTopologyTests(unittest.TestCase):
    def test_capability_contract_names_the_declared_future_app_receipt_path(self) -> None:
        policy = json.loads(GITHUB_POLICY_PATH.read_text(encoding="utf-8"))
        status = policy["protection_operator_app"]
        self.assertTrue(status.startswith("DECLARED"))
        for token in ("provision", "install-scoped", "write-back-verified"):
            self.assertIn(token, status)

    def test_agents_md_names_the_same_declared_topology(self) -> None:
        agents = (CANDIDATE_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Protection-Operator App", agents)
        self.assertIn("arrival topology **DECLARED**, never EXERCISED", agents)
        self.assertIn("ed3c/noodles#435", agents)


if __name__ == "__main__":
    unittest.main()

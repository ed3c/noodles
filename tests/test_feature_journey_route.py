"""Route truth for the journey-compilation gate (ed3c/noodles#264).

`ed3c/noodles#242` put the gate inside `./noodles issue handoff`, a route the lanes that actually
land cannot take: `execute_provenance_admission` admits only a registered Noodle worktree on the
exact `execute_branch(subject)`, while wave-9 atoms landed from ordinary clones on their own
branches and reached `awaiting_land` by writing the marker directly. The gate existed and was
bypassable, and both routes ended green.

These controls hold the gate at the confluence instead: a candidate whose issue reached
`awaiting_land` by a direct marker flip is refused with its own diagnostic when the declared
feature's code surface is absent from the exact base..head diff, and the same candidate passes
once that surface is really changed.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import feature_contract
import noodles
from tests.support import CANDIDATE_ROOT

HEAD_SHA = "c" * 40
SUBJECT = "ed3c/noodles#900264"
FEATURE = feature_contract.VERIFICATION_SKILL_FEATURE


def issue_body(*, feature: str | None = FEATURE.feature_id, state: str = "awaiting_land") -> str:
    """A body whose `awaiting_land` marker was written directly - no handoff produced it."""
    feature_marker = f"<!-- noodles-feature: {feature} -->\n" if feature is not None else ""
    return (
        "<!-- noodles-role: repository-mutating-atom -->\n"
        "<!-- noodles-target: ed3c/noodles -->\n"
        f"<!-- noodles-subject: {SUBJECT} -->\n"
        f"<!-- noodles-state: {state} -->\n"
        "<!-- noodles-component: schedule -->\n"
        f"{feature_marker}"
        "<!-- noodles-depends-on: none -->\n\n"
        "## Goal\n\nCompile the declared journey where landing flows.\n\n"
        "## Physical acceptance\n\n- Planted controls fail closed.\n\n"
        "## Non-claims\n\n- The marker flip itself is never authorized by this gate.\n"
    )


class FeatureJourneyRouteGateTests(unittest.TestCase):
    def run_verify(self, body: str, changed_files: list[str]) -> tuple[object, mock.MagicMock]:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        event_path = base / "event.json"
        event_path.write_text(
            json.dumps(
                {
                    "pull_request": {
                        "number": 11,
                        "head": {"sha": HEAD_SHA},
                        "base": {"ref": "main"},
                        "draft": False,
                        "body": f"Refs {SUBJECT}",
                    },
                    "repository": {"full_name": "ed3c/noodles"},
                }
            ),
            encoding="utf-8",
        )

        def fake_git(root: Path, *args: str, check: bool = True) -> str:
            if args == ("rev-parse", "HEAD"):
                return HEAD_SHA
            if args == ("rev-parse", "HEAD^{tree}"):
                return "d" * 40
            raise AssertionError(f"unexpected git call: {args}")

        with mock.patch.object(noodles, "issue_read", return_value={"state": "open", "body": body}), \
                mock.patch.object(noodles, "merge_base_changed_files", return_value=changed_files), \
                mock.patch.object(noodles, "verify_repository", return_value={"ok": True, "errors": [], "metrics": {}}) as repository, \
                mock.patch.object(noodles, "git", side_effect=fake_git):
            receipt = noodles.verify_pull_request(CANDIDATE_ROOT, event_path, base, base / "receipt.json")
        return receipt, repository

    def test_positive_control_changed_feature_surface_compiles_into_the_landing_receipt(self) -> None:
        receipt, _ = self.run_verify(issue_body(), [FEATURE.code_surface])
        self.assertIn("feature-journey", receipt["gates"])
        self.assertEqual(receipt["feature"], FEATURE.feature_id)
        self.assertEqual(receipt["feature_changed_node"], FEATURE.code_surface)
        self.assertEqual(receipt["feature_journeys"], list(FEATURE.journeys))
        self.assertEqual(receipt["feature_transitions"], list(FEATURE.transitions))

    def test_planted_negative_direct_marker_flip_with_an_unmapped_journey_is_refused(self) -> None:
        with self.assertRaises(noodles.GateError) as raised:
            self.run_verify(issue_body(), ["AGENTS.md"])
        diagnostic = str(raised.exception)
        self.assertIn("candidate feature-journey gate failed", diagnostic)
        self.assertIn("unmapped journey", diagnostic)
        self.assertIn(FEATURE.code_surface, diagnostic)
        self.assertIn("Supported path", diagnostic)
        self.assertIn(SUBJECT, diagnostic)

    def test_planted_negative_fails_closed_before_the_repository_gate_runs(self) -> None:
        with mock.patch.object(noodles, "verify_repository") as repository:
            with self.assertRaises(noodles.GateError):
                self.run_verify(issue_body(), ["AGENTS.md"])
        repository.assert_not_called()

    def test_planted_negative_unadmitted_feature_id_is_refused_naming_the_supported_path(self) -> None:
        with self.assertRaises(noodles.GateError) as raised:
            self.run_verify(issue_body(feature="handoff-route-truth"), ["AGENTS.md"])
        diagnostic = str(raised.exception)
        self.assertIn("candidate feature-journey gate failed", diagnostic)
        self.assertIn("unadmitted noodles-feature", diagnostic)
        self.assertIn("drop the noodles-feature marker", diagnostic)

    def test_positive_control_marker_free_issue_carries_the_gate_with_no_compiled_map(self) -> None:
        receipt, repository = self.run_verify(issue_body(feature=None), ["AGENTS.md"])
        self.assertIn("feature-journey", receipt["gates"])
        self.assertIsNone(receipt["feature"])
        self.assertIsNone(receipt["feature_changed_node"])
        repository.assert_called_once()


class HandoffRouteIsNotTheLandingRouteTests(unittest.TestCase):
    """The evidence the arm choice rests on, held as an executable readback."""

    def test_the_wave_nine_lane_branches_are_not_admissible_execute_branches(self) -> None:
        landed = ("fix-46-worktree-admission", "fix-99-exclusive-admission", "fix-100-concurrency-invariants")
        for branch in landed:
            with self.subTest(branch=branch):
                self.assertNotEqual(branch, noodles.execute_branch("ed3c/noodles#46"))
                self.assertNotEqual(branch, noodles.execute_branch("ed3c/noodles#99"))
                self.assertNotEqual(branch, noodles.execute_branch("ed3c/noodles#100"))

    def test_the_marker_writer_is_unconstrained_so_reaching_awaiting_land_grants_nothing(self) -> None:
        # constraint: ed3c/noodles#264 - issue_set_state admits awaiting_land from any state and the
        # constraint: backlog adapter exposes it as a verb, which is why the gate cannot sit behind it.
        self.assertIn("awaiting_land", noodles.ALLOWED_ISSUE_STATES)
        self.assertIn("edit = \".noodle/adapters/github edit\"", (CANDIDATE_ROOT / ".noodle.toml").read_text(encoding="utf-8"))
        self.assertIn("    issue_set_state(item_id, new_status)", (CANDIDATE_ROOT / "noodles.py").read_text(encoding="utf-8"))

    def test_the_journey_gate_has_exactly_one_home_and_it_is_the_landing_route(self) -> None:
        # constraint: ed3c/noodles#264 - the declaration anchors are composed at runtime; writing
        # constraint: `def <symbol>(` literally here would make this file a second declaration site
        # constraint: for the retrieval ground truth in tests/test_lancedb_ab.py.
        source = (CANDIDATE_ROOT / "noodles.py").read_text(encoding="utf-8")
        self.assertEqual(source.count("compile_handoff_feature_map("), 1)
        handoff = source.split(f"def {'execute_handoff'}(", 1)[1].split("\ndef ", 1)[0]
        self.assertNotIn("compile_handoff_feature_map", handoff)
        verify = source.split(f"def {'verify_pull_request'}(", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("compile_handoff_feature_map", verify)


if __name__ == "__main__":
    unittest.main()

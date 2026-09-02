from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

import noodles
import skill_contract
from tests.support import CANDIDATE_ROOT


class AgentFriendlyArchitectureTests(unittest.TestCase):
    def test_document_route_and_agent_friendly_spec_readback(self) -> None:
        policy = json.loads((CANDIDATE_ROOT / "policy/fitness.json").read_text())
        paths = {relative for _, relative in noodles.tracked_entries(CANDIDATE_ROOT)}
        self.assertEqual(skill_contract.validate_agent_document_route(CANDIDATE_ROOT, paths, policy), [])

        missing = {**policy, "agent_document_route": ["AGENTS.md", "missing.md"]}
        self.assertTrue(
            any(
                "pointer missing" in error
                for error in skill_contract.validate_agent_document_route(CANDIDATE_ROOT, paths, missing)
            )
        )

        fourth_hop = {
            **policy,
            "agent_document_route": [*policy["agent_document_route"], "ARCHITECTURE.md"],
        }
        self.assertTrue(
            any(
                "maximum is 3" in error
                for error in skill_contract.validate_agent_document_route(CANDIDATE_ROOT, paths, fourth_hop)
            )
        )

        system_contract = (CANDIDATE_ROOT / "contracts/system-v1.md").read_text()
        agents = (CANDIDATE_ROOT / "AGENTS.md").read_text()
        self.assertIn("## Agent-friendly architecture", system_contract)
        self.assertIn("## Enforcement hierarchy", system_contract)
        self.assertIn("issue-named executable contract/test", system_contract)
        self.assertIn("Predictable local Agent behavior", system_contract)
        self.assertIn("local-obvious → globally-correct", system_contract)
        self.assertIn("### Durable owner and writer map", system_contract)
        self.assertIn("mandatory baseline acceptance", system_contract)
        for phrase in (
            "**Shortcut failure.**",
            "**Nearest contract.**",
            "**Isolation.**",
            "**Exceptions.**",
            "**Subtraction.**",
            "**`poteto-mode`.**",
            "**Verification architecture.**",
            "### Current mechanical coverage and follow-up gap",
        ):
            self.assertIn(phrase, system_contract)
        for requirement_id in ("AF-01", "AF-02", "AF-03", "AF-04", "AF-05", "AF-06"):
            self.assertEqual(system_contract.count(f"| {requirement_id} |"), 1)
        self.assertIn("contracts/system-v1.md", agents)
        self.assertIn("`AF-01` through `AF-06`", agents)
        self.assertNotIn("### Durable owner and writer map", agents)

    def test_system_specification_requirement_identity_and_mutable_state_controls(self) -> None:
        system_contract = (CANDIDATE_ROOT / "contracts/system-v1.md").read_text()
        requirement_ids = re.findall(r"(?m)^### ([A-Z][A-Z0-9_.-]+)$", system_contract)
        self.assertGreaterEqual(len(requirement_ids), 12)
        self.assertEqual(len(requirement_ids), len(set(requirement_ids)))

        for requirement_id in (
            "AUTHORITY.NO_LAUNDERING.001",
            "EVIDENCE.NO_SELF_AUTHORIZATION.001",
            "OWNERSHIP.SEPARATION.001",
            "GOLDEN_PATH.001",
            "VERIFICATION.ORACLE.001",
            "VERIFICATION.FEATURE_MAP.001",
            "VERIFICATION.EVIDENCE_BINDING.001",
            "AUTONOMY.NO_HUMAN_VERIFIER.001",
            "AUTONOMY.BOUNDED.001",
            "LEARNING.EXECUTABLE.001",
            "CONCURRENCY.INDEPENDENCE.001",
            "CROSS_REPO.AUTHORITY.001",
            "COMPLEXITY.SUBTRACT.001",
            "REQUIREMENT.EVOLUTION.001",
            "ISSUE_CONTRACT.TIGHTENING_OWNS_MIGRATION.001",
            "REQUIREMENT.PROJECTION.001",
            "DEPENDENCY.IMPLICIT_DISCOVERY.001",
        ):
            self.assertEqual(system_contract.count(f"### {requirement_id}"), 1)

        for phrase in (
            "MUST own that backlog migration in the same atom",
            "tests/fixtures/issue-contract-ready-backlog.json",
            "exact candidate `noodles.parse_issue_contract`",
            "trusted controls step",
            "later receipt step receives its step-scoped `GH_TOKEN`",
            "migration obligation",
            "intake-normalizer seam `ed3c/noodles#157`",
            "No live-provider scan is required",
            "A discovered implicit dependency MUST become an explicit probe, gate, or typed marker within one atom.",
            "`./noodles preflight` is the execute-environment admission boundary",
        ):
            self.assertIn(phrase, system_contract)

        noodles_source = (CANDIDATE_ROOT / "noodles.py").read_text()
        self.assertIn("def preflight(root: Path) -> dict[str, Any]:", noodles_source)
        self.assertIn('sub.add_parser("preflight")', noodles_source)

        mutable_fact_patterns = (
            r"(?im)^\s*(?:current\s+)?(?:pr|pull request)\s*#\d+",
            r"(?im)^\s*(?:current\s+)?workflow(?:-run)?\s*(?:id|#)?\s*[:=]?\s*\d+",
            r"(?im)^\s*(?:current\s+)?(?:head|merge|commit|tree)\s*[:=]\s*[0-9a-f]{40}\s*$",
            r"(?im)^\s*[A-Z0-9_.-]+\s*=\s*(?:LANDED|PARTIAL|HOLD)\s*$",
        )
        for pattern in mutable_fact_patterns:
            self.assertIsNone(re.search(pattern, system_contract), pattern)

        planted_duplicate = system_contract + "\n### VERIFICATION.ORACLE.001\n\nDuplicate.\n"
        planted_ids = re.findall(r"(?m)^### ([A-Z][A-Z0-9_.-]+)$", planted_duplicate)
        self.assertNotEqual(len(planted_ids), len(set(planted_ids)))


class OwnershipRegistryTests(unittest.TestCase):
    """ed3c/noodles#325 - AF-03's one-writer law as a readback over a finite ownership-key registry.

    Until this atom the contract's own AF-03 caveat said repository-wide duplicate-owner detection
    was unproven "until a finite canonical document set and ownership-key seam exist", and the
    evidence manifest named exactly ONE concrete rule (the task-profile literal check) with the
    stated limit "not repository-wide semantic duplicate-writer proof". That rule is now one
    registered class among several, judged by one implementation."""

    OWNER_BYTES = json.dumps({"pins": [{"commit": "aaaaaaaabbbbbbbbccccccccdddddddd"}]})

    def tracked(self) -> set[str]:
        return {relative for _, relative in noodles.tracked_entries(CANDIDATE_ROOT)}

    def registry(self) -> dict:
        return json.loads((CANDIDATE_ROOT / skill_contract.OWNERSHIP_REGISTRY_PATH).read_text())

    def fixture(self, registry: dict, files: dict[str, str]) -> tuple[Path, set[str]]:
        temp = tempfile.TemporaryDirectory(prefix="noodles-ownership-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        for relative, text in {skill_contract.OWNERSHIP_REGISTRY_PATH: json.dumps(registry), **files}.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return root, set(files) | {skill_contract.OWNERSHIP_REGISTRY_PATH}

    def one_class(self, projections: list[dict] | None = None) -> dict:
        return {
            "schema_version": 1,
            "classes": [
                {
                    "id": "pin",
                    "owner": "policy/owner.json",
                    "select": ["pins", "*", "commit"],
                    "why": "fixture",
                    "projections": [] if projections is None else projections,
                }
            ],
        }

    def test_positive_control_the_shipped_registry_names_a_tracked_owner_for_every_class(self) -> None:
        registry = self.registry()
        tracked = self.tracked()
        self.assertTrue(registry["classes"], "the registry enumerates no class at all")
        for entry in registry["classes"]:
            with self.subTest(ownership_class=entry["id"]):
                self.assertIn(entry["owner"], tracked)
                self.assertTrue(entry["why"].strip())
        self.assertEqual(skill_contract.validate_ownership_registry(CANDIDATE_ROOT, tracked), [])

    def test_the_subsumed_task_profile_rule_leaves_exactly_one_implementation(self) -> None:
        """Readback for "subsumed or wired through the same detector, leaving one implementation":
        the retired function is gone from the tree and the class that replaced it names the same
        owner and the same value locator.

        Its `task_profile_literal_exempt_paths` policy key deliberately outlives it for one staging
        window. `pull_request_target` runs the DEFAULT BRANCH's `validate_task_profile_single_source`
        against the candidate's own policy, so deleting the key raises KeyError inside the trusted
        verifier - `./noodles verify --trusted-preview` reproduced exactly that as two reds no rerun
        could clear. The key has no reader in this tree, which is asserted here so the residue cannot
        quietly become a second writer; the retirement is filed as findings-register entry 9."""
        source = (CANDIDATE_ROOT / "noodles.py").read_text()
        self.assertNotIn("validate_task_profile_single_source", source)
        self.assertNotIn("task_profile_literal_exempt_paths", source)
        classes = {entry["id"]: entry for entry in self.registry()["classes"]}
        self.assertEqual(classes["task-profile-model"]["owner"], skill_contract.POLICY_FITNESS_PATH)
        self.assertEqual(classes["task-profile-model"]["select"], ["required_codex_task_profiles", "*", "model"])

    def test_planted_control_a_duplicated_pin_in_an_unregistered_file_is_refused_naming_the_owner(self) -> None:
        root, tracked = self.fixture(
            self.one_class(),
            {"policy/owner.json": self.OWNER_BYTES, "docs/copy.md": "pinned at aaaaaaaabbbbbbbbccccccccdddddddd today\n"},
        )
        errors = skill_contract.validate_ownership_registry(root, tracked)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("docs/copy.md writes pin value", errors[0])
        self.assertIn("policy/owner.json owns", errors[0])

    def test_planted_negative_control_a_registered_projection_carrying_the_current_value_passes(self) -> None:
        root, tracked = self.fixture(
            self.one_class([{"path": "docs/copy.md", "why": "admitted read-only projection"}]),
            {"policy/owner.json": self.OWNER_BYTES, "docs/copy.md": "pinned at aaaaaaaabbbbbbbbccccccccdddddddd today\n"},
        )
        self.assertEqual(skill_contract.validate_ownership_registry(root, tracked), [])

    def test_planted_negative_control_an_unregistered_file_carrying_no_owned_value_is_never_scanned_into_a_finding(self) -> None:
        root, tracked = self.fixture(
            self.one_class(),
            {"policy/owner.json": self.OWNER_BYTES, "docs/unrelated.md": "no pins here, only prose about commits\n"},
        )
        self.assertEqual(skill_contract.validate_ownership_registry(root, tracked), [])

    def test_a_projection_the_owner_moved_past_reds_naming_itself(self) -> None:
        """Derivation, not string comparison alone: the projection is resolved against the owner's
        CURRENT values, so the drift this law exists to prevent - a pin copied out and left behind
        when the lock moved - reds instead of sitting in prose nobody re-reads."""
        root, tracked = self.fixture(
            self.one_class([{"path": "docs/copy.md", "why": "admitted read-only projection"}]),
            {"policy/owner.json": self.OWNER_BYTES, "docs/copy.md": "pinned at eeeeeeeeffffffff0000000011111111 today\n"},
        )
        errors = skill_contract.validate_ownership_registry(root, tracked)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("carries none of the owner's current values", errors[0])

    def test_planted_registry_row_with_no_owner_path_fails_validation(self) -> None:
        registry = self.one_class()
        registry["classes"][0]["owner"] = "policy/absent.json"
        root, tracked = self.fixture(registry, {"policy/owner.json": self.OWNER_BYTES})
        errors = skill_contract.validate_ownership_registry(root, tracked)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("which this tree does not track", errors[0])

    def test_a_class_that_selects_nothing_searchable_is_refused_rather_than_silently_green(self) -> None:
        registry = self.one_class()
        registry["classes"][0]["select"] = ["pins", "*", "absent"]
        root, tracked = self.fixture(registry, {"policy/owner.json": self.OWNER_BYTES})
        errors = skill_contract.validate_ownership_registry(root, tracked)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("the class describes nothing", errors[0])

    def test_a_class_without_a_written_reason_is_refused(self) -> None:
        registry = self.one_class()
        registry["classes"][0]["why"] = "   "
        root, tracked = self.fixture(registry, {"policy/owner.json": self.OWNER_BYTES})
        self.assertIn("carries no written reason", " ".join(skill_contract.validate_ownership_registry(root, tracked)))

    def test_the_contract_names_the_registry_seam_and_keeps_the_arbitrary_prose_caution(self) -> None:
        contract = (CANDIDATE_ROOT / "contracts/system-v1.md").read_text()
        self.assertIn(skill_contract.OWNERSHIP_REGISTRY_PATH, contract)
        self.assertIn("arbitrary prose", contract)


if __name__ == "__main__":
    unittest.main()

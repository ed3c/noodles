from __future__ import annotations

import json
import re
import unittest

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
        self.assertIn("## 2. Agent-friendly architecture", system_contract)
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
            "REQUIREMENT.PROJECTION.001",
        ):
            self.assertEqual(system_contract.count(f"### {requirement_id}"), 1)

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


if __name__ == "__main__":
    unittest.main()

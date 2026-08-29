from __future__ import annotations

import json
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
        self.assertIn("## Agent-friendly architecture", system_contract)
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


if __name__ == "__main__":
    unittest.main()

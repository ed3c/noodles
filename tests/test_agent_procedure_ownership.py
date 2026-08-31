from __future__ import annotations

import re
import unittest

from tests.support import CANDIDATE_ROOT


def procedure_is_canonical(text: str) -> bool:
    pr = text.find("Open exactly one non-draft PR")
    handoff = text.find("Run `./noodles issue handoff")
    stop = text.find("Stop immediately after the handoff succeeds")
    return -1 not in (pr, handoff, stop) and pr < handoff < stop


class AgentProcedureOwnershipTests(unittest.TestCase):
    def test_agents_is_bootloader_and_pointer_map_not_duplicate_procedure_owner(self) -> None:
        agents = (CANDIDATE_ROOT / "AGENTS.md").read_text()
        self.assertIn("## Canonical procedure owners", agents)
        self.assertIn("## 工程法則的實證歸屬", agents)
        self.assertIn("contracts/system-v1.md", agents)
        self.assertIn(".agents/skills/execute/SKILL.md", agents)
        self.assertNotIn("## Call order", agents)
        self.assertNotIn("## Issue and PR contract", agents)
        self.assertNotIn("<!-- noodles-role:", agents)
        self.assertNotIn("set the Issue to `awaiting_land`, then open", agents)

    def test_readme_points_to_locks_and_parser_without_copying_mutable_pins_or_marker_schema(self) -> None:
        readme = (CANDIDATE_ROOT / "README.md").read_text()
        self.assertIn("policy/runtime.lock.json", readme)
        self.assertIn("policy/providers.lock.json", readme)
        self.assertIn("./noodles issue contract", readme)
        self.assertNotIn("<!-- noodles-role:", readme)
        self.assertNotRegex(readme, r"(?i)(?:cursor/plugins|skill-concerns)@[0-9a-f]{40}")
        self.assertNotRegex(readme, r"admission tree digest\s+`[0-9a-f]{64}`")

    def test_schedule_order_is_provider_identity_envelope_not_issue_prose_copy(self) -> None:
        schedule = (CANDIDATE_ROOT / ".agents/skills/schedule/SKILL.md").read_text()
        self.assertIn("provider_body_sha256", schedule)
        self.assertIn("The order is a routing envelope, not a copy of the Issue.", schedule)
        self.assertNotIn("one evidence-only audit atom", schedule)
        copied_fields = (
            "claim: exact claim from Issue",
            "physical acceptance: exact positive/negative/readback/residue requirements",
            "non-claims: exact exclusions",
        )
        for phrase in copied_fields:
            self.assertNotIn(phrase, schedule)

    def test_execute_skill_is_canonical_pr_then_handoff_sequence(self) -> None:
        execute = (CANDIDATE_ROOT / ".agents/skills/execute/SKILL.md").read_text()
        self.assertTrue(procedure_is_canonical(execute))
        self.assertIn("Unsupported routes fail closed: any engineering route not in the admitted fixtures above", execute)
        self.assertNotIn("Unsupported routes fail closed: `control-ui`", execute)

        planted_old_order = """
Run `./noodles issue handoff owner/repo#N --pr N`.
Open exactly one non-draft PR to `main`.
Stop immediately after the handoff succeeds.
"""
        self.assertFalse(procedure_is_canonical(planted_old_order))

    def test_system_spec_remains_system_owner_not_procedure_copy(self) -> None:
        spec = (CANDIDATE_ROOT / "contracts/system-v1.md").read_text()
        self.assertIn("# noodles System Specification v1", spec)
        self.assertIn("REQUIREMENT.EVOLUTION.001", spec)
        self.assertNotIn("./noodles issue handoff owner/repo#N --pr N", spec)
        self.assertNotIn("python3 skill_contract.py publish .noodle/orders-next.candidate.json", spec)


if __name__ == "__main__":
    unittest.main()

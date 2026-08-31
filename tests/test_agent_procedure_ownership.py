"""One canonical owner per Agent-facing procedure fact (ed3c/noodles#83).

Each rule below names the fact, the file that owns it, and the file that must not
restate it. A restatement is not a style problem: the two copies drift, and an
Agent that reads the wrong one is told to do something the CLI physically
refuses. Every rule carries a planted negative that reinstates the exact
historical drift it was written against.
"""
from __future__ import annotations

import json
import re
import unittest

from tests.support import CANDIDATE_ROOT

HANDOFF_OWNER = "`./noodles issue handoff`"
EXECUTE_SKILL = ".agents/skills/execute/SKILL.md"
PROVIDER_LOCK = "policy/providers.lock.json"
BASH_FENCE = "```bash"
HEX_RUN = re.compile(r"[0-9a-f]{40,}")
MARKER = re.compile(r"<!--\s*noodles-[a-z-]+:")


def pinned_literals(lock: object) -> set[str]:
    """Every hex-looking pinned scalar the provider lock owns."""
    if isinstance(lock, dict):
        return set().union(*(pinned_literals(value) for value in lock.values()))
    if isinstance(lock, list):
        return set().union(*(pinned_literals(item) for item in lock))
    return {lock} if isinstance(lock, str) and HEX_RUN.fullmatch(lock) else set()


def procedure_ownership_errors(agents: str, readme: str, lock: object) -> list[str]:
    errors: list[str] = []

    for number, line in enumerate(agents.splitlines(), 1):
        if "awaiting_land" in line and not line.lstrip().startswith("<!--") and HANDOFF_OWNER not in line:
            errors.append(
                f"AGENTS.md:{number} states an `awaiting_land` procedure without naming its sole writer "
                f"{HANDOFF_OWNER}; the execute Skill owns the step order"
            )
    if EXECUTE_SKILL not in agents:
        errors.append(f"AGENTS.md must point at {EXECUTE_SKILL} instead of restating the execute sequence")

    if BASH_FENCE in agents:
        errors.append("AGENTS.md carries a command sequence; README.md and `./noodles --help` own the call order")
    if BASH_FENCE not in readme:
        errors.append("README.md must own the bootstrap call order")
    if "README.md" not in agents:
        errors.append("AGENTS.md must point at README.md for the call order")

    pinned = pinned_literals(lock)
    for literal in sorted({match.group() for match in HEX_RUN.finditer(readme)}):
        owner = f"that {PROVIDER_LOCK} owns" if literal in pinned else "that some lock file owns"
        errors.append(f"README.md copies pinned value {literal} {owner}")
    if PROVIDER_LOCK not in readme:
        errors.append(f"README.md must point at {PROVIDER_LOCK} for provider pins")

    for number, line in enumerate(readme.splitlines(), 1):
        if MARKER.search(line):
            errors.append(f"README.md:{number} copies a noodles-* marker example; the parser and AGENTS.md are canonical")

    return sorted(set(errors))


class AgentProcedureOwnershipTests(unittest.TestCase):
    def setUp(self) -> None:
        self.agents = (CANDIDATE_ROOT / "AGENTS.md").read_text()
        self.readme = (CANDIDATE_ROOT / "README.md").read_text()
        self.lock = json.loads((CANDIDATE_ROOT / PROVIDER_LOCK).read_text())

    def errors(self, *, agents: str | None = None, readme: str | None = None) -> list[str]:
        return procedure_ownership_errors(
            self.agents if agents is None else agents,
            self.readme if readme is None else readme,
            self.lock,
        )

    def test_every_agent_facing_procedure_fact_has_exactly_one_owner(self) -> None:
        self.assertEqual(self.errors(), [])

    def test_handoff_before_pr_order_is_rejected(self) -> None:
        planted = self.agents.replace(
            "6. Follow the canonical execute sequence",
            "6. Run `./noodles verify`, commit, push, set the Issue to `awaiting_land`, then open one PR with "
            "exactly one `Refs owner/repo#N` line.\n6. Follow the canonical execute sequence",
            1,
        )
        self.assertNotEqual(planted, self.agents)
        self.assertTrue(any("sole writer" in error for error in self.errors(agents=planted)))

    def test_second_call_order_block_in_agents_is_rejected(self) -> None:
        planted = self.agents + "\n```bash\n./noodles verify\n./noodles start\n```\n"
        self.assertTrue(any("call order" in error for error in self.errors(agents=planted)))

    def test_copied_provider_pin_in_readme_is_rejected(self) -> None:
        commit = self.lock["providers"][0]["commit"]
        self.assertRegex(commit, HEX_RUN)
        planted = self.readme + f"\n- Cursor pstack: `cursor/plugins@{commit}`, `pstack/skills`.\n"
        errors = self.errors(readme=planted)
        self.assertTrue(any(f"copies pinned value {commit}" in error for error in errors), errors)

    def test_copied_marker_example_in_readme_is_rejected(self) -> None:
        planted = self.readme + "\n```text\n<!-- noodles-role: repository-mutating-atom -->\n```\n"
        self.assertTrue(any("marker example" in error for error in self.errors(readme=planted)))

    def test_readme_keeps_owning_what_agents_released(self) -> None:
        self.assertIn("./noodles supervise", self.readme)
        self.assertIn("AUTONOMY.SUPERVISED_RUNNER.001", self.readme)
        self.assertIn("./noodles issue validate", self.readme)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import ast
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import unittest
from pathlib import Path
from unittest import mock

import daemon_lease
import noodles
import runtime_contract
import skill_contract
from tests.support import (
    ADMISSION_RECEIPT_GRACE_SECONDS,
    CANDIDATE_ROOT,
    ENGINE_ROOT,
    backlog_project,
    cmd,
    codex_real_bin_export,
    codex_real_bin_resolution,
    copy_tracked,
    cursor_pstack_fixture,
    graphql_backlog_payload,
    handoff_fixture,
    provider_fixture,
    runtime_lock_shape_errors,
    runtime_release_reader,
    assert_valid_start_entrypoint_receipt,
    script_mode_gateerror_identity,
    start_entrypoint_with_delayed_listener,
    tree_digest,
    validate_script_mode_gateerror_identity,
    validate_start_entrypoint_receipt,
    write_fake_codex_stub,
    write_noodle_stub,
    write_skill_discovery_fixture,
)
TASK_PROFILES = skill_contract.task_profiles(ENGINE_ROOT)
EXECUTE_MODEL = TASK_PROFILES["execute"]["model"]
# constraint: ed3c/noodles#253 - two Agent-facing procedure facts, one owner each, decided on the
# constraint: two Skills' own bytes. `noodles.parse_issue_contract` raises `unsupported noodles-role`
# constraint: for every value but `repository-mutating-atom`, so schedule admission may not offer a
# constraint: second role the parser refuses; and the refusal rule behind ed3c/noodles#130's stable
# constraint: prefix is a positive rule over the admitted route fixtures, so the branded inventory
# constraint: ed3c/noodles#252 stopped requiring may not come back after that prefix either.
RETIRED_ROLE_PROSE = "evidence-only audit atom"
RETIRED_ROUTE_INVENTORY = (
    "`control-ui`",
    "Cursor `create-skill`",
    "Cursor `/loop`",
    "Graphite `gt`",
    "cloud-agent infrastructure",
    "standalone `goal`",
)

# constraint: ed3c/noodles#293 - composed, never written literally: the repository-wide readback
# constraint: below scans every tracked file, and a literal here would be its own counterexample.
RETIRED_STATION = "migrations" + "/" + "skills-shared"


def agent_procedure_owner_errors(schedule_skill: str, execute_skill: str) -> list[str]:
    """ed3c/noodles#253 - the pure predicate both the positive control and its planted negatives call,
    so reinstating either historical drift is a red instead of a rewritten assertion."""
    errors = [
        f"schedule Skill admits the role {RETIRED_ROLE_PROSE!r}, which noodles.parse_issue_contract "
        "refuses with `unsupported noodles-role`"
    ] if RETIRED_ROLE_PROSE in schedule_skill else []
    prefix = skill_contract.EXECUTE_UNSUPPORTED_PHRASE
    rules = [line for line in execute_skill.splitlines() if line.startswith(prefix)]
    if len(rules) != 1:
        return [*errors, f"execute Skill must carry exactly one line starting with {prefix!r}, found {len(rules)}"]
    errors.extend(
        f"execute Skill unsupported route refusal names retired route inventory {item!r}; the rule "
        "after the stable prefix is positive over the admitted route fixtures"
        for item in RETIRED_ROUTE_INVENTORY
        if item in rules[0]
    )
    return errors


class RepositoryGateTests(unittest.TestCase):
    def verify(self, root: Path = CANDIDATE_ROOT) -> dict:
        return noodles.verify_repository(root, ENGINE_ROOT)

    def baseline_metrics(self) -> dict:
        return dict(noodles.repository_metrics(CANDIDATE_ROOT))

    def passing_metrics(self) -> dict:
        metrics = self.baseline_metrics()
        policy = json.loads((ENGINE_ROOT / "policy/fitness.json").read_text())
        metrics.update(
            {
                "tracked_files": policy["max_tracked_files"],
                "max_file_lines": policy["max_file_lines"],
                "markdown_share": policy["max_markdown_share"],
                "normalized_line_entropy": policy["min_normalized_entropy"],
                "test_to_executable_ratio": policy["min_test_to_executable_ratio"],
                "unowned_top_level_definitions": policy["max_unowned_top_level_definitions"],
                "cross_surface_import_edges": dict(policy["max_cross_surface_import_edges"]),
            }
        )
        return metrics

    def verify_with_metrics(self, *, overrides: dict[str, object], root: Path = CANDIDATE_ROOT) -> dict:
        metrics = self.passing_metrics()
        metrics.update(overrides)
        with mock.patch.object(noodles, "repository_metrics", return_value=metrics):
            return noodles.verify_repository(root, ENGINE_ROOT)

    def mutated_copy(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temp = tempfile.TemporaryDirectory(prefix="noodles-test-", ignore_cleanup_errors=True)
        root = Path(temp.name) / "repo"
        copy_tracked(CANDIDATE_ROOT, root)
        return temp, root

    def commit(self, root: Path, message: str = "mutation") -> None:
        cmd(["git", "add", "-A"], root)
        cmd(["git", "commit", "-q", "-m", message], root)

    def test_positive_baseline_passes(self) -> None:
        result = self.verify()
        self.assertTrue(result["ok"], result["errors"])
        self.assertTrue(result["errors"] == [] and all(w.startswith("architecture warning ") for w in result["warnings"]), result)

    def test_untagged_comment_variants_fail_with_distinct_diagnostics(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        shell_path = root / "tests/run.sh"
        shell_lines = shell_path.read_text().splitlines()
        shell_lines.insert(2, "# reminder: keep this fast")
        shell_path.write_text("\n".join(shell_lines) + "\n")
        # constraint: ed3c/noodles#84 - the probe needs any tracked assignment line, and the previous
        # constraint: anchor was a prose phrase constant that atom retired. Re-anchoring here was the
        # constraint: widening half of the staged transition; ed3c/noodles#277 flipped it by deleting
        # constraint: that constant, so this anchor must stay a real assignment in skill_contract.py.
        phrase = 'CONCURRENCY_PROOF_PATH = "policy/concurrency-proof.json"'
        py_path = root / "skill_contract.py"
        py_mutated = py_path.read_text().replace(phrase, f"# {phrase}", 1)
        py_path.write_text(py_mutated)
        lineno = py_mutated.splitlines().index(f"# {phrase}") + 1
        self.commit(root)
        result = self.verify(root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("tests/run.sh:3" in item for item in result["errors"]))
        self.assertTrue(any(f"skill_contract.py:{lineno}" in item for item in result["errors"]))

    def test_auto_mode_is_rejected(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        path = root / ".noodle.toml"
        path.write_text(path.read_text().replace('mode = "supervised"', 'mode = "auto"'))
        self.commit(root)
        result = self.verify(root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("mode must be" in item for item in result["errors"]))

    def test_codex_task_profiles_are_exact(self) -> None:
        with (CANDIDATE_ROOT / ".noodle.toml").open("rb") as handle:
            config = tomllib.load(handle)
        self.assertEqual(set(TASK_PROFILES), {"schedule", "execute"})
        self.assertEqual(config["routing"]["defaults"]["model"], TASK_PROFILES["schedule"]["model"])
        self.assertEqual(config["agents"]["codex"]["path"], ".agents/bin")
        result = self.verify()
        self.assertTrue(result["ok"], result["errors"])

    def test_a_second_task_profile_literal_is_rejected(self) -> None:
        """ed3c/noodles#325 preserved this control against the new carrier: the task-model rule is no
        longer its own function, it is one registered class in policy/ownership-keys.json, and the
        refusal now names the owner instead of naming this one rule."""
        for relative in ("noodles.py", ".agents/bin/codex", "tests/test_schedule_contract.py"):
            with self.subTest(reader=relative):
                temp, root = self.mutated_copy()
                self.addCleanup(temp.cleanup)
                path = root / relative
                path.write_text(path.read_text() + f'\n# constraint: planted second definition {EXECUTE_MODEL}\n')
                self.commit(root)
                result = self.verify(root)
                self.assertFalse(result["ok"])
                expected = f"{relative} writes task-profile-model value {EXECUTE_MODEL!r}, which policy/fitness.json owns"
                self.assertTrue(any(expected in item for item in result["errors"]), result["errors"])

    def test_ownership_registry_projection_must_name_a_tracked_path(self) -> None:
        """The ed3c/noodles#277-shaped half of the retired rule, preserved: an exemption that names a
        path the tree does not carry has stopped describing this repository."""
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        path = root / "policy/ownership-keys.json"
        registry = json.loads(path.read_text())
        registry["classes"][0]["projections"].append({"path": "policy/absent.json", "why": "planted"})
        path.write_text(json.dumps(registry, indent=2) + "\n")
        self.commit(root)
        result = noodles.verify_repository(root, root)
        self.assertFalse(result["ok"])
        self.assertTrue(
            any("admits projection 'policy/absent.json', which this tree does not track" in item for item in result["errors"]),
            result["errors"],
        )

    def test_runtime_lock_is_pinned_by_shape_derivation_and_internal_consistency(self) -> None:
        """ed3c/noodles#315 converted this from a strict-equal literal of the whole `runtime` object.

        The literal was the pattern's exact shape: this module is what `pull_request_target` runs
        from the DEFAULT BRANCH against a candidate tree, so a candidate that legitimately bumped the
        Noodle release was compared against bytes only `main` could hold and could never merge to
        update them. The candidate carries its own release, commit and digests; the trusted side
        keeps the invariant that they are exactly pinned, exactly shaped, and internally consistent -
        `tests/support.runtime_lock_shape_errors` owns that judgement and
        `tests/test_trusted_literals.py::ConvertedValueDeadlockTests` holds the fixture pair proving
        a legal move stays green under it."""
        self.assertEqual(runtime_lock_shape_errors(CANDIDATE_ROOT), [])

    # constraint: ed3c/noodles#301 - refusal is scoped to the retired source; generic provider
    # constraint: schema and pin validity remain owned by the repository provider gate.
    RETIRED_PROVIDER_NAME = "skills-" + "shared"
    RETIRED_PROVIDER_POINTER = f"https://github.com/ed3c/{RETIRED_PROVIDER_NAME}.git"

    def retired_compat_entry(self) -> dict:
        name = f"{self.RETIRED_PROVIDER_NAME}-compat"
        return {
            "name": name,
            "source": self.RETIRED_PROVIDER_POINTER,
            "commit": "52b29b38ded9eaacbf7fb1bfa8ccf69ab37870b9",
            "subpath": ".",
            "destination": f".noodle/providers/{name}",
            "license_path": "LICENSE",
            "enabled": False,
            "authority": "P",
            "purpose": "Explicitly disabled compatibility source; not a Golden Path dependency.",
        }

    def retired_provider_in_locks(self, root: Path) -> list[str]:
        # constraint: ed3c/noodles#301 - the refusing half of the readback, and the written ceiling on
        # constraint: the prose half below. `provider_sync` fetches only what `policy/*.lock.json`
        # constraint: names, and JSON carries no string concatenation, so a lock entry cannot hide the
        # constraint: retired repository from a substring scan the way source can - which is exactly
        # constraint: what RETIRED_PROVIDER_NAME's own `"skills-" + "shared"` demonstrates. A
        # constraint: re-coupling that spells the name anywhere in a lock file, as a provider name or
        # constraint: inside a source URL, reds here whatever it does elsewhere in the tree.
        return sorted(
            relative
            for relative in cmd(["git", "ls-files", "policy"], root).splitlines()
            if relative.endswith(".lock.json")
            and (root / relative).is_file()
            and self.RETIRED_PROVIDER_NAME in (root / relative).read_text(encoding="utf-8", errors="ignore")
        )

    def live_pointer_offenders(self, root: Path) -> list[str]:
        # constraint: ed3c/noodles#301 repository-wide readback - historical-provenance documents may
        # constraint: still name the retired repository in prose; a clone URL is the only shape
        # constraint: provider sync can fetch, so it is the exact carrier of a live pointer.
        # constraint: Non-claim, and not a small one: this matches one exact literal, so a tracked
        # constraint: file that assembles the URL from parts is invisible to it. That is not
        # constraint: hypothetical - RETIRED_PROVIDER_NAME above does exactly that, deliberately, so
        # constraint: this control's own bytes are not an offender. Read this as prose hygiene over
        # constraint: the tracked tree; `retired_provider_in_locks` is the check that refuses,
        # constraint: because the one surface provider sync reads cannot concatenate.
        return [
            relative
            for relative in cmd(["git", "ls-files"], root).splitlines()
            if (root / relative).is_file()
            and self.RETIRED_PROVIDER_POINTER in (root / relative).read_text(encoding="utf-8", errors="ignore")
        ]

    def test_no_tracked_file_is_a_live_pointer_to_the_retired_source(self) -> None:
        self.assertEqual(self.live_pointer_offenders(CANDIDATE_ROOT), [])

    def test_no_policy_lock_names_the_retired_repository(self) -> None:
        self.assertEqual(self.retired_provider_in_locks(CANDIDATE_ROOT), [])

    def test_readded_disabled_retired_provider_entry_reds_both_controls(self) -> None:
        # constraint: ed3c/noodles#301 planted negative - the re-coupling this atom removes costs one
        # constraint: boolean, so the control plants the cheapest re-addition (still enabled: false,
        # constraint: under the provider budget, well-formed for validate_provider_lock) and runs the
        # constraint: three controls above against it. Disabled is not neutral: all three red.
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        path = root / "policy/providers.lock.json"
        payload = json.loads(path.read_text())
        payload["providers"].append(self.retired_compat_entry())
        path.write_text(json.dumps(payload, indent=2) + "\n")
        self.commit(root)
        self.assertEqual(self.live_pointer_offenders(root), ["policy/providers.lock.json"])
        self.assertEqual(self.retired_provider_in_locks(root), ["policy/providers.lock.json"])

    def test_retired_codex_routing_model_is_rejected(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        path = root / ".noodle.toml"
        config = path.read_text()
        admitted = f'model = "{tomllib.loads(config)["routing"]["defaults"]["model"]}"'
        self.assertIn(admitted, config)
        path.write_text(config.replace(admitted, 'model = "gpt-5.6-pro"', 1))
        self.commit(root)
        result = self.verify(root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("routing model must be schedule model" in item for item in result["errors"]))

    def test_scheduler_frontmatter_positive_fixture_passes(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        path = root / ".agents/skills/schedule/SKILL.md"
        content = path.read_text()
        if "\nschedule:" not in content:
            content = content.replace(
                "description: Convert exact GitHub Issue contracts into minimal dependency-aware Noodle orders.\n",
                "description: Convert exact GitHub Issue contracts into minimal dependency-aware Noodle orders.\n"
                'schedule: "When provider-backed backlog state requires new or revised orders"\n',
                1,
            )
        path.write_text(content)
        result = self.verify(root)
        self.assertTrue(result["ok"], result["errors"])

    def test_noodle_worktree_root_positive_fixture_passes(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        path = root / ".gitignore"
        content = path.read_text()
        if ".worktrees/\n" not in content:
            path.write_text(content + ".worktrees/\n")
            self.commit(root)
        result = self.verify(root)
        self.assertTrue(result["ok"], result["errors"])

    def test_missing_noodle_worktree_ignore_is_rejected(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        path = root / ".gitignore"
        content = path.read_text()
        path.write_text("\n".join(line for line in content.splitlines() if line != ".worktrees/") + "\n")
        result = self.verify(root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("Noodle worktree root .worktrees" in item for item in result["errors"]))

    def test_backlog_skill_without_scheduler_frontmatter_is_rejected(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        path = root / ".agents/skills/schedule/SKILL.md"
        content = path.read_text()
        path.write_text("\n".join(line for line in content.splitlines() if not line.startswith("schedule:")) + "\n")
        result = self.verify(root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("scheduler-capable" in item for item in result["errors"]))

    def test_execute_skill_without_task_frontmatter_is_rejected(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        path = root / ".agents/skills/execute/SKILL.md"
        content = path.read_text()
        path.write_text("\n".join(line for line in content.splitlines() if not line.startswith("schedule:")) + "\n")
        result = self.verify(root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("project task skill 'execute'" in item for item in result["errors"]))

    def test_execute_skill_unsupported_route_refusal_transition(self) -> None:
        """ed3c/noodles#252 asserts the *shape* of the refusal rule, never a brand it must contain.
        Trusted verify runs the default branch's copy of this module over the candidate tree
        (`.github/workflows/verify.yml`: `PYTHONPATH: .trusted`, `NOODLES_CANDIDATE_ROOT:
        .candidate`), so a `keep this brand` assertion here is `main` requiring every candidate to
        keep it, and no edit inside the de-branding successor's own PR can clear it. What stays
        load-bearing: the stable line-start prefix, exactly one rule line, that each replacement
        really replaced the rule it names, and the same accept/reject verdicts as before.

        ed3c/noodles#253 landed the de-branding and retires the widened acceptance in the other
        direction: the rule the Skill now carries is positive over the admitted route fixtures, so
        the brand is refused rather than required and cannot silently return."""
        stable_refusal = "Unsupported routes fail closed:"
        self.assertEqual(skill_contract.EXECUTE_UNSUPPORTED_PHRASE, stable_refusal)

        branded_result = self.verify()
        self.assertTrue(branded_result["ok"], branded_result["errors"])
        branded_content = (CANDIDATE_ROOT / ".agents/skills/execute/SKILL.md").read_text()
        branded_rules = [line for line in branded_content.splitlines() if line.startswith(stable_refusal)]
        self.assertEqual(len(branded_rules), 1)
        self.assertNotIn("`control-ui`", branded_rules[0])

        cases = (
            ("generic", "Unsupported routes fail closed: any route not explicitly admitted above.", True),
            ("deleted", "", False),
            ("weakened", "Unsupported routes may proceed best-effort:", False),
            (
                "negated prose",
                "This obsolete wording, Unsupported routes fail closed:, no longer applies; unsupported routes may proceed.",
                False,
            ),
        )
        for label, replacement, accepted in cases:
            with self.subTest(case=label):
                temp, root = self.mutated_copy()
                self.addCleanup(temp.cleanup)
                path = root / ".agents/skills/execute/SKILL.md"
                content = path.read_text()
                refusal_rules = [line for line in content.splitlines() if line.startswith(stable_refusal)]
                self.assertEqual(len(refusal_rules), 1)
                path.write_text(content.replace(refusal_rules[0], replacement, 1))
                # constraint: ed3c/noodles#252 - the brand-free replacement for the generic case's
                # constraint: retired `assertNotIn(<brand>, ...)` guard. It proves the same thing
                # constraint: that brand did - the mutation really removed the rule this case names -
                # constraint: for every case, on whatever inventory the candidate's own rule carries.
                self.assertNotIn(refusal_rules[0], path.read_text())

                result = self.verify(root)
                self.assertEqual(result["ok"], accepted, result["errors"])
                if not accepted:
                    self.assertTrue(any("unsupported route refusal" in item for item in result["errors"]))

    def test_agent_facing_procedure_facts_have_exactly_one_owner(self) -> None:
        """ed3c/noodles#253 - the two facts this atom gave back to their owners. Schedule admission
        offered `evidence-only audit atom`, a role `noodles.parse_issue_contract` refuses, so an
        Agent that read the Skill was told to admit something the CLI physically rejects. The execute
        refusal rule inventoried brand names behind ed3c/noodles#130's stable prefix, so the admitted
        set was stated twice and the two copies could drift. Each planted negative reinstates the
        exact historical bytes."""
        schedule_skill = (CANDIDATE_ROOT / ".agents/skills/schedule/SKILL.md").read_text()
        execute_skill = (CANDIDATE_ROOT / ".agents/skills/execute/SKILL.md").read_text()
        self.assertEqual(agent_procedure_owner_errors(schedule_skill, execute_skill), [])
        self.assertEqual(schedule_skill.count(RETIRED_ROLE_PROSE), 0)

        for label, planted_schedule, planted_execute, expected in (
            (
                "role the parser refuses",
                schedule_skill.replace(
                    "6. The Issue describes one repository-mutating atom.",
                    f"6. The Issue describes one repository-mutating atom or one {RETIRED_ROLE_PROSE}.",
                    1,
                ),
                execute_skill,
                "unsupported noodles-role",
            ),
            (
                "brand reintroduced after the stable prefix",
                schedule_skill,
                execute_skill.replace(
                    skill_contract.EXECUTE_UNSUPPORTED_PHRASE,
                    f"{skill_contract.EXECUTE_UNSUPPORTED_PHRASE} `control-ui`,",
                    1,
                ),
                "retired route inventory",
            ),
        ):
            with self.subTest(case=label):
                self.assertNotEqual((planted_schedule, planted_execute), (schedule_skill, execute_skill))
                errors = agent_procedure_owner_errors(planted_schedule, planted_execute)
                self.assertTrue(any(expected in error for error in errors), errors)

    def test_execute_skill_without_required_p_contract_is_rejected(self) -> None:
        cases = (
            (
                skill_contract.EXECUTE_PREFLIGHT_PHRASE,
                "Implementation may begin before environment admission.",
                "step-0 preflight",
            ),
            (
                skill_contract.EXECUTE_ENTRYPOINT_PHRASE,
                "Execute may route directly to a leaf skill.",
                "poteto-mode entrypoint",
            ),
            (
                skill_contract.EXECUTE_BYPASS_PHRASE,
                "Leaf skill routing is permitted when it seems faster.",
                "direct leaf bypass refusal",
            ),
        )
        for phrase, replacement, label in cases:
            with self.subTest(contract=label):
                temp, root = self.mutated_copy()
                self.addCleanup(temp.cleanup)
                path = root / ".agents/skills/execute/SKILL.md"
                content = path.read_text()
                self.assertIn(phrase, content)
                path.write_text(content.replace(phrase, replacement, 1))
                result = self.verify(root)
                self.assertFalse(result["ok"])
                self.assertTrue(any(label in item for item in result["errors"]))

    def test_schedule_ownership_and_active_order_survive_as_behavior_controls(self) -> None:
        """ed3c/noodles#84 - the invariants the two removed sentences existed to enforce are that a
        proposal never carries Noodle's transient `schedule` order and never re-emits an active
        non-schedule order. Both are decided on the exact proposed bytes by the publish gate, so
        rewording the Skill's prose is admitted while the gate still refuses both shapes."""
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        path = root / ".agents/skills/schedule/SKILL.md"
        content = path.read_text()
        reworded = content.replace(
            "Noodle alone injects and owns the transient `schedule` order.",
            "Only Noodle may inject or own the transient `schedule` order.",
            1,
        ).replace("Do not re-emit any active non-schedule order.", "Leave every active non-schedule order out.", 1)
        self.assertNotEqual(reworded, content)
        path.write_text(reworded)
        result = self.verify(root)
        self.assertTrue(result["ok"], result["errors"])

        current = {"orders": [{"id": "ed3c/noodles#30", "status": "active", "stages": [{"task_key": "execute"}]}]}
        for order_id, expected in (
            ("schedule", "scheduler output must not contain Noodle-owned transient schedule order 'schedule'"),
            (
                "ed3c/noodles#30",
                "scheduler output must omit active non-schedule order 'ed3c/noodles#30'; "
                "Noodle preserves its exact order/stage fields",
            ),
        ):
            with self.subTest(order=order_id):
                proposed = {"orders": [{"id": order_id, "stages": [{"do": "execute", "model": EXECUTE_MODEL}]}]}
                self.assertEqual(skill_contract.validate_schedule_output(current, proposed, TASK_PROFILES), [expected])

    def test_schedule_publish_entrypoint_must_stay_a_runnable_block(self) -> None:
        """ed3c/noodles#84 - the publish gate is proven by argv inside a fenced block, so a copy that
        survives only in prose, in a comment, or in a second dead example no longer admits."""
        command = " ".join(skill_contract.SCHEDULE_PUBLISH_ENTRYPOINT)
        for label, mutate in (
            ("moved into prose", lambda text: text.replace(f"```bash\n{command}\n```", f"Run {command} to publish.")),
            ("moved into a comment", lambda text: text.replace(f"```bash\n{command}\n```", f"<!-- {command} -->")),
            ("duplicated", lambda text: text.replace(f"```bash\n{command}\n```", f"```bash\n{command}\n{command}\n```")),
        ):
            with self.subTest(case=label):
                temp, root = self.mutated_copy()
                self.addCleanup(temp.cleanup)
                path = root / ".agents/skills/schedule/SKILL.md"
                content = path.read_text()
                mutated = mutate(content)
                self.assertNotEqual(mutated, content)
                self.assertIn(command, mutated)
                path.write_text(mutated)
                result = self.verify(root)
                self.assertFalse(result["ok"])
                self.assertTrue(any("deterministic publish gate" in item for item in result["errors"]), result["errors"])

    def test_execute_route_refusal_must_be_owned_by_the_route_fixture_section(self) -> None:
        """ed3c/noodles#84 - the unknown-route refusal keeps ed3c/noodles#130's byte-identical
        line-start prefix, and adds ownership: one document line, in the section that declares the
        route fixtures. Historical bytes parked elsewhere no longer satisfy it."""
        prefix = skill_contract.EXECUTE_UNSUPPORTED_PHRASE
        source = (CANDIDATE_ROOT / ".agents/skills/execute/SKILL.md").read_text()
        rule = next(line for line in source.splitlines() if line.startswith(prefix))
        for label, mutate in (
            ("moved into a comment", lambda text: text.replace(rule, f"<!-- {rule} -->", 1)),
            ("moved into a dead example", lambda text: text.replace(rule, f"```text\n{rule}\n```", 1)),
            ("moved into an unrelated section", lambda text: text.replace(rule, "", 1).replace("## Authority\n", f"## Authority\n\n{rule}\n", 1)),
            ("duplicated", lambda text: text.replace(rule, f"{rule}\n{rule}", 1)),
        ):
            with self.subTest(case=label):
                temp, root = self.mutated_copy()
                self.addCleanup(temp.cleanup)
                path = root / ".agents/skills/execute/SKILL.md"
                content = path.read_text()
                mutated = mutate(content)
                self.assertNotEqual(mutated, content)
                self.assertIn(prefix, mutated)
                path.write_text(mutated)
                result = self.verify(root)
                self.assertFalse(result["ok"])
                self.assertTrue(any("unsupported route refusal" in item for item in result["errors"]), result["errors"])

    def test_agent_guarantee_classes_are_structural_not_exact_prose(self) -> None:
        """ed3c/noodles#84 - replaces the removed `required_agent_phrases` grep. The invariant is
        that AGENTS.md owns exactly one guarantee-class table defining P/L/R/N once each; wording is
        free, and the same bytes parked in a fence, a comment, or a duplicate table are not
        ownership."""
        code = "\n".join(
            line
            for line in (CANDIDATE_ROOT / "noodles.py").read_text().splitlines()
            if not line.strip().startswith("#")
        )
        self.assertNotIn("required_agent_phrases", code)
        lines = (CANDIDATE_ROOT / "AGENTS.md").read_text().splitlines()
        row = next(line for line in lines if line.startswith("| P-01 |"))
        start = end = lines.index(row)
        while start and lines[start - 1].startswith("|"):
            start -= 1
        while end + 1 < len(lines) and lines[end + 1].startswith("|"):
            end += 1
        table = "\n".join(lines[start : end + 1])
        cases = (
            ("reworded class", lambda text: text.replace("P — probabilistic guidance", "P – model-side guidance", 1), True),
            ("row deleted", lambda text: text.replace(f"{row}\n", "", 1), False),
            ("authority emptied", lambda text: text.replace(row, row[: row.rindex("|", 0, row.rindex("|"))] + "|  |", 1), False),
            ("table fenced", lambda text: text.replace(table, f"```text\n{table}\n```", 1), False),
            ("table duplicated", lambda text: text.replace(table, f"{table}\n\nSecond owner:\n\n{table}", 1), False),
        )
        for label, mutate, admitted in cases:
            with self.subTest(case=label):
                temp, root = self.mutated_copy()
                self.addCleanup(temp.cleanup)
                path = root / "AGENTS.md"
                content = path.read_text()
                mutated = mutate(content)
                self.assertNotEqual(mutated, content)
                path.write_text(mutated)
                result = self.verify(root)
                self.assertEqual(result["ok"], admitted, result["errors"])
                if not admitted:
                    self.assertTrue(any("guarantee" in item for item in result["errors"]), result["errors"])

    def test_orphaned_workflow_phrase_lists_are_gone_and_no_gate_reads_them(self) -> None:
        """ed3c/noodles#84 - the six workflow phrase lists had no consumer anywhere and every gate
        stayed green while they described nothing. Direct readback of the policy file plus every
        tracked source, so the deletion is proven, not asserted.

        Key names are assembled at runtime: this file is itself tracked source, so a literal would
        satisfy the very absence it checks."""
        policy = json.loads((CANDIDATE_ROOT / "policy/fitness.json").read_text())
        sources = "\n".join(
            path.read_text(errors="ignore")
            for path in sorted(CANDIDATE_ROOT.rglob("*.py"))
            if ".git" not in path.parts
        )
        for stem in (
            "trusted_verify_workflow",
            "candidate_self_test_job",
            "candidate_self_test_job_forbidden",
            "trusted_verification_job",
            "trusted_verification_job_forbidden",
            "trusted_land_workflow",
        ):
            key = f"{stem}_phrases"
            with self.subTest(key=key):
                self.assertNotIn(key, policy)
                self.assertNotIn(key, sources)

    def test_schedule_skill_without_deterministic_publish_gate_is_rejected(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        path = root / ".agents/skills/schedule/SKILL.md"
        content = path.read_text()
        command = "python3 skill_contract.py publish .noodle/orders-next.candidate.json"
        self.assertIn(command, content)
        path.write_text(content.replace(command, "mv .noodle/orders-next.candidate.json .noodle/orders-next.json", 1))
        result = self.verify(root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("deterministic publish gate" in item for item in result["errors"]))

    def test_schedule_output_accepts_only_new_non_schedule_orders(self) -> None:
        current = {
            "orders": [{
                "id": "ed3c/noodles#30",
                "status": "active",
                "stages": [{"task_key": "execute", "status": "active", "prompt": "exact"}],
            }]
        }
        proposed = {
            "orders": [{
                "id": "ed3c/noodles#31",
                "stages": [{"do": "execute", "model": EXECUTE_MODEL, "prompt": "next"}],
            }]
        }
        self.assertEqual(skill_contract.validate_schedule_output(current, proposed, TASK_PROFILES), [])

    def test_schedule_output_rejects_stage_without_do(self) -> None:
        proposed = {
            "orders": [{
                "id": "ed3c/noodles#37",
                "stages": [{"prompt": "untyped ad-hoc stage"}],
            }]
        }
        self.assertEqual(
            skill_contract.validate_schedule_output({"orders": []}, proposed, TASK_PROFILES),
            ["scheduler output order 'ed3c/noodles#37' stage[0] requires canonical non-empty do"],
        )

    def test_schedule_output_rejects_unresolved_do(self) -> None:
        proposed = {
            "orders": [{
                "id": "ed3c/noodles#37",
                "stages": [{"do": "review", "prompt": "wrong task type"}],
            }]
        }
        self.assertEqual(
            skill_contract.validate_schedule_output({"orders": []}, proposed, TASK_PROFILES),
            [
                "scheduler output order 'ed3c/noodles#37' stage[0] has unresolved do 'review'; "
                "expected 'execute'"
            ],
        )

    def test_schedule_output_rejects_multiple_execute_stages(self) -> None:
        proposed = {
            "orders": [{
                "id": "ed3c/noodles#37",
                "stages": [
                    {"do": "execute", "prompt": "first"},
                    {"do": "execute", "prompt": "second"},
                ],
            }]
        }
        self.assertEqual(
            skill_contract.validate_schedule_output({"orders": []}, proposed, TASK_PROFILES),
            ["scheduler output order 'ed3c/noodles#37' must contain exactly one stage; found 2"],
        )

    def test_schedule_output_rejects_schedule_stage(self) -> None:
        proposed = {
            "orders": [{
                "id": "ed3c/noodles#37",
                "stages": [{"do": "schedule", "prompt": "self-owned"}],
            }]
        }
        self.assertEqual(
            skill_contract.validate_schedule_output({"orders": []}, proposed, TASK_PROFILES),
            ["scheduler output order 'ed3c/noodles#37' must not contain a schedule stage"],
        )

    def test_planted_negative_schedule_self_order_fixture_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="noodles-schedule-negative-", ignore_cleanup_errors=True) as temp_name:
            root = Path(temp_name)
            shutil.copytree(ENGINE_ROOT / "policy", root / "policy")
            runtime = root / ".noodle"
            runtime.mkdir()
            (runtime / "orders.json").write_text('{"orders": []}')
            candidate_path = runtime / "orders-next.candidate.json"
            candidate_path.write_text(json.dumps({
                "orders": [{
                    "id": " schedule ",
                    "stages": [{"do": "schedule"}],
                }]
            }))

            with self.assertRaisesRegex(
                ValueError,
                "scheduler output must not contain Noodle-owned transient schedule order 'schedule'",
            ):
                skill_contract.publish_schedule_output(root, candidate_path)

            self.assertTrue(candidate_path.exists())
            self.assertFalse((runtime / "orders-next.json").exists())

    def test_schedule_output_cannot_rewrite_active_non_schedule_order(self) -> None:
        current = {
            "orders": [{
                "id": "ed3c/noodles#30",
                "status": "active",
                "stages": [{"task_key": "execute", "status": "active", "prompt": "original"}],
            }]
        }
        proposed = {
            "orders": [{
                "id": "ed3c/noodles#30",
                "stages": [{"do": "execute", "prompt": "rewritten"}],
            }]
        }
        errors = skill_contract.validate_schedule_output(current, proposed, TASK_PROFILES)
        self.assertEqual(
            errors,
            [
                "scheduler output must omit active non-schedule order 'ed3c/noodles#30'; "
                "Noodle preserves its exact order/stage fields"
            ],
        )

    def test_schedule_publish_is_atomic_and_does_not_mutate_active_orders(self) -> None:
        with tempfile.TemporaryDirectory(prefix="noodles-schedule-contract-", ignore_cleanup_errors=True) as temp_name:
            root = Path(temp_name)
            shutil.copytree(ENGINE_ROOT / "policy", root / "policy")
            runtime = root / ".noodle"
            runtime.mkdir()
            current = {
                "orders": [{
                    "id": "ed3c/noodles#30",
                    "status": "active",
                    "stages": [{"task_key": "execute", "status": "active", "prompt": "exact"}],
                }]
            }
            candidate = {"orders": []}
            (runtime / "orders.json").write_text(json.dumps(current))
            candidate_path = runtime / "orders-next.candidate.json"
            candidate_path.write_text(json.dumps(candidate))

            destination = skill_contract.publish_schedule_output(root, candidate_path)

            self.assertEqual(destination, (runtime / "orders-next.json").resolve())
            self.assertEqual(json.loads((runtime / "orders.json").read_text()), current)
            self.assertEqual(json.loads(destination.read_text()), candidate)
            self.assertFalse(candidate_path.exists())

    def test_symlink_is_rejected(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        (root / "escape").symlink_to("README.md")
        self.commit(root)
        result = self.verify(root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("forbidden git mode 120000" in item for item in result["errors"]))

    def test_tracked_residue_is_rejected(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        (root / "__pycache__").mkdir()
        (root / "__pycache__/x.pyc").write_bytes(b"residue")
        cmd(["git", "add", "-f", "__pycache__/x.pyc"], root)
        cmd(["git", "commit", "-q", "-m", "tracked residue"], root)
        result = self.verify(root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("forbidden tracked residue" in item for item in result["errors"]))

    def test_agent_document_route_negative_controls(self) -> None:
        policy = json.loads((ENGINE_ROOT / "policy/fitness.json").read_text())
        paths = {relative for _, relative in noodles.tracked_entries(CANDIDATE_ROOT)}
        wrong = {**policy, "agent_document_route": ["AGENTS.md", "missing.md"]}
        self.assertTrue(any("pointer missing" in error for error in skill_contract.validate_agent_document_route(CANDIDATE_ROOT, paths, wrong)))
        policy["agent_document_route"].append("README.md")
        self.assertTrue(any("maximum is 3" in error for error in skill_contract.validate_agent_document_route(CANDIDATE_ROOT, paths, policy)))

    def test_issue_template_uses_baseline_without_copying_a_specialized_feature(self) -> None:
        body = noodles.issue_template("ed3c/noodles", 120, "Exact atom")
        self.assertNotIn("noodles-feature", body)
        self.assertEqual(noodles.parse_issue_contract(body, "ed3c/noodles#120")["feature"], "")

    def test_adapter_sync_keeps_marker_free_and_uncurable_issues_visible(self) -> None:
        marker_free = noodles.issue_template("ed3c/noodles", 120, "Baseline atom")
        unknown = marker_free.replace(
            "<!-- noodles-depends-on: none -->",
            "<!-- noodles-feature: future-specialized-oracle -->\n<!-- noodles-depends-on: none -->",
        ).replace("#120", "#121")
        invalid = marker_free.replace("#120", "#122").replace(
            "<!-- noodles-subject: ed3c/noodles#122 -->\n",
            "<!-- noodles-subject: ed3c/noodles#122 -->\n<!-- noodles-subject: ed3c/noodles#122 -->\n",
        )
        issues = [
            {"number": 120, "state": "open", "title": "Baseline atom", "body": marker_free, "html_url": "https://example/120"},
            {"number": 121, "state": "open", "title": "Future oracle", "body": unknown, "html_url": "https://example/121"},
            {"number": 122, "state": "open", "title": "Broken atom", "body": invalid, "html_url": "https://example/122"},
        ]

        def fake(endpoint: str, *, method: str = "GET", payload: object | None = None, token: object | None = None) -> object:
            if endpoint == "graphql":
                return graphql_backlog_payload(issues)
            if method == "PATCH":
                return {"number": 122, "state": "open", "body": payload["body"]}
            return {"id": 1}

        stdout = io.StringIO()
        with backlog_project(), \
             mock.patch.dict(os.environ, {"NOODLES_REPOSITORIES": "ed3c/noodles"}, clear=False), \
             mock.patch.object(noodles, "gh_api", side_effect=fake), \
             mock.patch("sys.stdout", stdout):
            self.assertEqual(noodles.adapter_sync(), 0)
        readback = [json.loads(line) for line in stdout.getvalue().splitlines()]
        issue_lines = [item for item in readback if item.get("kind") != "finding"]
        self.assertEqual([item["status"] for item in issue_lines], ["ready", "ready", "blocked"])
        self.assertIn("expected one noodles-subject marker, found 2", issue_lines[2]["diagnostic"])
        # constraint: ed3c/noodles#263 - open register findings ride this same backlog surface, so
        # constraint: the reader exists by construction; they follow the issues and never precede them.
        finding_lines = [item for item in readback if item.get("kind") == "finding"]
        self.assertEqual(finding_lines, readback[len(issue_lines):])
        self.assertEqual(finding_lines, noodles.findings_backlog_items(noodles.repo_root()))

    def test_acceptance_enforcement_hierarchy_has_no_issue_number_bypass(self) -> None:
        agents = (CANDIDATE_ROOT / "AGENTS.md").read_text()
        system_contract = (CANDIDATE_ROOT / "contracts/system-v1.md").read_text()
        self.assertIn("Every repository mutation runs `./noodles acceptance verify`", agents)
        self.assertIn("optional `<!-- noodles-feature: feature-id -->`", agents)
        self.assertIn("## Enforcement hierarchy", system_contract)
        self.assertIn("built-in baseline acceptance contract", system_contract)
        self.assertIn("optional specialized oracle", system_contract)
        for executable in ("noodles.py", "feature_contract.py"):
            self.assertNotIn("#112", (CANDIDATE_ROOT / executable).read_text())

    def test_unpinned_provider_is_rejected(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        path = root / "policy/providers.lock.json"
        payload = json.loads(path.read_text())
        payload["providers"][0]["commit"] = "main"
        path.write_text(json.dumps(payload))
        self.commit(root)
        result = self.verify(root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("not pinned" in item for item in result["errors"]))

    def test_resurrected_migration_station_is_rejected(self) -> None:
        # constraint: ed3c/noodles#293 - the retired station is archived by git history alone. The
        # constraint: owning surface for its non-return is verify's forbidden-tracked-residue check,
        # constraint: driven by policy/fitness.json forbidden_path_names, so a resurrection is a red
        # constraint: exit code rather than a convention nobody executes. The station path is
        # constraint: composed at runtime so this file is not itself a tracked occurrence of it.
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        relative = f"{RETIRED_STATION}/ledger.json"
        path = root / relative
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"schema_version": 1, "capabilities": []}), encoding="utf-8")
        self.commit(root)
        result = self.verify(root)
        self.assertFalse(result["ok"])
        self.assertIn(f"forbidden tracked residue: {relative}", result["errors"])

    def test_the_retired_migration_station_leaves_no_tracked_reader(self) -> None:
        # constraint: ed3c/noodles#293 - repository-wide readback: no tracked byte names the station.
        for _mode, relative in noodles.tracked_entries(CANDIDATE_ROOT):
            source = CANDIDATE_ROOT / relative
            self.assertNotIn(RETIRED_STATION, source.read_text(encoding="utf-8", errors="ignore"), relative)

    def test_untrusted_workflow_boundary_is_rejected(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        path = root / ".github/workflows/verify.yml"
        path.write_text(path.read_text().replace("pull_request_target:", "pull_request:"))
        self.commit(root)
        result = self.verify(root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("trusted boundary" in item for item in result["errors"]))

    def test_trusted_verify_rejects_serial_candidate_dependency(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        path = root / ".github/workflows/verify.yml"
        workflow = path.read_text()
        independent = "  verify:\n"
        serial = "  verify:\n    needs: candidate-self-tests\n"
        self.assertIn(independent, workflow)
        self.assertNotIn(serial, workflow)
        path.write_text(workflow.replace(independent, serial, 1))
        self.commit(root)
        result = self.verify(root)
        self.assertFalse(result["ok"])
        self.assertIn("trusted verify job must be independent of candidate jobs", result["errors"])

    def test_trusted_verify_rejects_candidate_script_execution(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        path = root / ".github/workflows/verify.yml"
        workflow = path.read_text()
        marker = "  verify:\n"
        self.assertIn(marker, workflow)
        prefix, trusted_job = workflow.split(marker, 1)
        steps = "    steps:\n"
        self.assertIn(steps, trusted_job)
        planted = "      - name: Planted candidate script execution\n        run: .candidate/tests/run.sh\n\n"
        path.write_text(prefix + marker + trusted_job.replace(steps, steps + planted, 1))
        self.commit(root)
        result = self.verify(root)
        self.assertFalse(result["ok"])
        self.assertIn("trusted verify job must not execute candidate scripts", result["errors"])

    def test_report_only_architecture_thresholds_emit_warnings_without_failing_verify(self) -> None:
        policy = json.loads((ENGINE_ROOT / "policy/fitness.json").read_text())
        cases = (
            (
                "max_file_lines",
                "max_file_lines",
                "max",
                policy["max_file_lines"] + 1,
                policy["max_file_lines"],
                "architecture warning max_file_lines=1001 exceeds 1000",
            ),
            (
                "markdown_share",
                "max_markdown_share",
                "max",
                round(policy["max_markdown_share"] + 0.000001, 6),
                policy["max_markdown_share"],
                "architecture warning markdown_share=0.580001 exceeds 0.58",
            ),
            (
                "normalized_line_entropy",
                "min_normalized_entropy",
                "min",
                round(policy["min_normalized_entropy"] - 0.000001, 6),
                policy["min_normalized_entropy"],
                "architecture warning normalized_line_entropy=0.479999 below 0.48",
            ),
            (
                "test_to_executable_ratio",
                "min_test_to_executable_ratio",
                "min",
                round(policy["min_test_to_executable_ratio"] - 0.000001, 6),
                policy["min_test_to_executable_ratio"],
                "architecture warning test_to_executable_ratio=0.199999 below 0.2",
            ),
            (
                "tracked_files",
                "max_tracked_files",
                "max",
                policy["max_tracked_files"] + 1,
                policy["max_tracked_files"],
                "architecture warning tracked_files=39 exceeds 38",
            ),
            ("root_surfaces", "max_root_surfaces", "max", policy["max_root_surfaces"] + 1, policy["max_root_surfaces"], "architecture warning root_surfaces=10 exceeds 9"),
        )
        for metric_key, policy_key, direction, planted_value, threshold, warning in cases:
            with self.subTest(metric=metric_key):
                result = self.verify_with_metrics(overrides={metric_key: planted_value})
                self.assertTrue(result["ok"], result.get("errors"))
                self.assertEqual(result.get("errors"), [])
                self.assertEqual(result.get("warnings"), [warning])
                # constraint: ed3c/noodles#276 and ed3c/noodles#278 - the per-component cross-surface
                # constraint: entries and the unowned-definition ratchet both share this readback, so
                # constraint: the fitness table's own entries are selected by name here rather than by
                # constraint: total length; all three families still have to be complete.
                readback = result.get("warning_readback", [])
                fitness_entries = [item for item in readback if item["metric"] in skill_contract.REPORT_ONLY_FITNESS_LIMITS]
                self.assertEqual(len(fitness_entries), len(skill_contract.REPORT_ONLY_FITNESS_LIMITS))
                self.assertEqual(
                    {item["metric"] for item in readback if item["metric"].startswith("cross_surface_import_edges[")},
                    {f"cross_surface_import_edges[{name}]" for name in result["metrics"]["cross_surface_import_edges"]},
                )
                self.assertEqual(
                    [item["metric"] for item in readback
                     if item not in fitness_entries and not item["metric"].startswith("cross_surface_import_edges[")],
                    ["unowned_top_level_definitions"],
                )
                warning_entries = [item for item in readback if item["status"] == "warning"]
                self.assertEqual(
                    warning_entries,
                    [{
                        "metric": metric_key,
                        "policy_key": policy_key,
                        "classification": "report-only",
                        "authority": "N",
                        "direction": direction,
                        "threshold": threshold,
                        "value": planted_value,
                        "status": "warning",
                        "message": warning,
                    }],
                )
                self.assertEqual(
                    {item["metric"] for item in fitness_entries if item["status"] == "ok"},
                    set(skill_contract.REPORT_ONLY_FITNESS_LIMITS) - {metric_key},
                )
                self.assertEqual(result["metrics"][metric_key], planted_value)
                self.assertFalse(any(f"fitness {metric_key}=" in item for item in result.get("errors", [])))

    def test_enabled_provider_count_still_fails_closed(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        path = root / "policy/providers.lock.json"
        payload = json.loads(path.read_text())
        # constraint: ed3c/noodles#304 - the count control plants its own well-formed third entry. It
        # constraint: used to flip the lock's one disabled compatibility entry, which coupled a
        # constraint: provider-budget control to a retired source staying in the lock forever.
        payload["providers"].append({
            "name": "count-probe",
            "source": "https://github.com/ed3c/count-probe.git",
            "commit": "7" * 40,
            "subpath": "skills",
            "destination": ".noodle/providers/count-probe",
            "license_path": "LICENSE",
            "enabled": True,
            "authority": "P",
            "purpose": "Planted third enabled provider; exists only to exceed the budget.",
        })
        path.write_text(json.dumps(payload))
        self.commit(root)
        with mock.patch.object(noodles, "repository_metrics", return_value=self.baseline_metrics()):
            result = self.verify(root)
        self.assertFalse(result["ok"])
        self.assertIn("enabled providers 3 exceed limit 2", result["errors"])

    def test_workflow_count_still_fails_closed(self) -> None:
        # constraint: ed3c/noodles#311 - the limit is read from the CANDIDATE copy's own policy, and
        # constraint: the control reds one above AND one below it. Pinning the trusted number here is
        # constraint: what made this an equality no candidate could ever change: the default branch
        # constraint: judged every candidate against its own count. Equality, not ceiling - a ceiling
        # constraint: would let an atom silently drop a tracked workflow file.
        _hold, root = self.mutated_copy()
        self.addCleanup(_hold.cleanup)
        limit = json.loads((root / "policy/fitness.json").read_text())["max_workflows"]
        workflows = sorted(path.name for path in (root / ".github/workflows").iterdir())
        self.assertEqual(len(workflows), limit)
        for observed in (limit + 1, limit - 1):
            with self.subTest(observed=observed):
                temp, case = self.mutated_copy()
                self.addCleanup(temp.cleanup)
                if observed > limit:
                    (case / ".github/workflows/extra.yml").write_text("name: extra\non: workflow_dispatch\njobs: {}\n")
                else:
                    (case / ".github/workflows" / workflows[0]).unlink()
                self.commit(case)
                with mock.patch.object(noodles, "repository_metrics", return_value=self.baseline_metrics()):
                    result = self.verify(case)
                self.assertFalse(result["ok"])
                self.assertIn(f"workflow count must equal {limit}, got {observed}", result["errors"])

    def test_planted_negative_a_malformed_candidate_workflow_limit_falls_back_to_the_trusted_pin(self) -> None:
        # constraint: ed3c/noodles#311 - reading the candidate's own number must not become a way to
        # constraint: disable the equality: a candidate that declares no usable limit is judged
        # constraint: against the default branch's pin rather than passing unchecked.
        trusted = json.loads((ENGINE_ROOT / "policy/fitness.json").read_text())
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        path = root / "policy/fitness.json"
        for planted in (None, "3", True, [3], "absent"):
            with self.subTest(planted=planted):
                payload = json.loads(path.read_text())
                if planted == "absent":
                    payload.pop("max_workflows", None)
                else:
                    payload["max_workflows"] = planted
                path.write_text(json.dumps(payload, indent=2) + "\n")
                self.assertEqual(noodles.candidate_workflow_limit(root, trusted), trusted["max_workflows"])
        path.write_text("{ not json")
        self.assertEqual(noodles.candidate_workflow_limit(root, trusted), trusted["max_workflows"])

    def test_runtime_dependency_manifest_still_fails_closed(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        path = root / "package.json"
        path.write_text("{}\n")
        self.commit(root)
        with mock.patch.object(noodles, "repository_metrics", return_value=self.baseline_metrics()):
            result = self.verify(root)
        self.assertFalse(result["ok"])
        self.assertIn("runtime dependency manifest forbidden: package.json", result["errors"])

    def test_metrics_readback_preserves_metrics_and_reports_warning_metadata(self) -> None:
        policy = json.loads((ENGINE_ROOT / "policy/fitness.json").read_text())
        metrics = self.passing_metrics()
        metrics["max_file_lines"] = policy["max_file_lines"] + 1
        with mock.patch.object(noodles, "repository_metrics", return_value=metrics):
            readback = noodles.metrics_readback(CANDIDATE_ROOT, ENGINE_ROOT)
        self.assertEqual(readback["max_file_lines"], metrics["max_file_lines"])
        self.assertEqual(readback["warnings"], ["architecture warning max_file_lines=1001 exceeds 1000"])
        self.assertEqual(
            [item for item in readback["warning_readback"] if item["status"] == "warning"],
            [{
                "metric": "max_file_lines",
                "policy_key": "max_file_lines",
                "classification": "report-only",
                "authority": "N",
                "direction": "max",
                "threshold": policy["max_file_lines"],
                "value": policy["max_file_lines"] + 1,
                "status": "warning",
                "message": "architecture warning max_file_lines=1001 exceeds 1000",
            }],
        )

    def test_metrics_stay_inside_budget(self) -> None:
        metrics = noodles.repository_metrics(CANDIDATE_ROOT)
        policy = json.loads((ENGINE_ROOT / "policy/fitness.json").read_text())
        self.assertTrue(all(isinstance(metrics.get(k), (int, float)) for k in skill_contract.REPORT_ONLY_FITNESS_LIMITS))
        self.assertTrue(all(not skill_contract.threshold_exceeded(metrics[k], d, policy[p]) for k, (d, p) in skill_contract.FAILING_FITNESS_LIMITS.items()))


class FixtureTeardownTests(unittest.TestCase):
    """ed3c/noodles#319: a fixture's teardown must not be able to red a run.

    Observed three times in one lane's verify runs, on two different fixtures and on candidates that
    touch neither: `shutil.rmtree` walks a fixture's git tree with `os.scandir`, something repopulates
    a directory before the matching `os.rmdir`, and the run reports `ERROR: <test name>` for a test
    whose own assertions all passed. The writer is not identified, and this disposition deliberately
    does not depend on identifying it: cleanup is not part of what any control asserts, so cleanup is
    made unable to fail.

    The sweep's coverage is defined by the check below, never by a count: a grep-and-count sweep of
    this class landed disposed at 30 files and was already 15 call sites behind `main` by the time it
    rebased, because every new fixture written meanwhile is a fresh instance. What holds is the closed
    set - one constructor for temporary trees under `tests/`, matched by attribute AND by bare name,
    every one of them carrying the disposition - which a new instance cannot join silently."""

    # constraint: ed3c/noodles#319 - `tempfile.mkdtemp` is listed to be refused, not dispositioned:
    # constraint: it has no cleanup contract at all, so every caller hand-writes a teardown and each
    # constraint: one is a fresh chance to write a raising `shutil.rmtree`. One constructor for
    # constraint: temporary trees is what makes the coverage check a closed set rather than a sample.
    TEMPORARY_TREE_CONSTRUCTORS = ("TemporaryDirectory", "mkdtemp")

    def temporary_tree_calls(self) -> list[tuple[str, int, str, list[str]]]:
        """Every temporary-tree construction under tests/, by attribute OR by bare name.

        The bare-name arm is not decoration: `from tempfile import TemporaryDirectory` is one import
        line away, and an attribute-only walk would report a clean sweep while the bypass compiles."""
        calls: list[tuple[str, int, str, list[str]]] = []
        for path in sorted((CANDIDATE_ROOT / "tests").rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                elif isinstance(node.func, ast.Name):
                    name = node.func.id
                else:
                    continue
                if name not in self.TEMPORARY_TREE_CONSTRUCTORS:
                    continue
                relative = path.relative_to(CANDIDATE_ROOT).as_posix()
                calls.append((relative, node.lineno, name, [keyword.arg or "**" for keyword in node.keywords]))
        return calls

    def test_every_fixture_temporary_directory_tolerates_a_failed_cleanup(self) -> None:
        calls = self.temporary_tree_calls()
        self.assertTrue(calls, "no temporary-tree call sites found under tests/")
        undisposed = [
            f"{path}:{line} ({name})"
            for path, line, name, keywords in calls
            if name != "TemporaryDirectory" or "ignore_cleanup_errors" not in keywords
        ]
        self.assertEqual(undisposed, [], "these call sites can still fail a run from teardown")

    def test_the_disposition_really_swallows_a_cleanup_failure_on_this_python(self) -> None:
        """The coverage check above proves the kwarg is written; this proves it does what it claims.

        The planted failure is the exact observed one - `os.rmdir` answering ENOTEMPTY partway through
        the walk - so this is the negative control for the coverage check above: without the kwarg the
        same planted failure escapes and reds the run."""
        for ignore, expect_raise in ((True, False), (False, True)):
            with self.subTest(ignore_cleanup_errors=ignore):
                temp = tempfile.TemporaryDirectory(prefix="noodles-teardown-control-", ignore_cleanup_errors=ignore)
                name = temp.name
                self.addCleanup(shutil.rmtree, name, True)
                with mock.patch("os.rmdir", side_effect=OSError(39, "Directory not empty")):
                    if expect_raise:
                        with self.assertRaises(OSError):
                            temp.cleanup()
                    else:
                        temp.cleanup()

    def planted_teardown_run(self, ignore: bool) -> unittest.TestResult:
        """One passing test whose fixture teardown hits the observed ENOTEMPTY, run for real."""
        owner = self

        class PlantedFixtureTest(unittest.TestCase):
            def test_its_own_assertion_passes(self) -> None:
                temp = tempfile.TemporaryDirectory(prefix="noodles-teardown-composition-", ignore_cleanup_errors=ignore)
                owner.addCleanup(shutil.rmtree, temp.name, True)
                self.addCleanup(temp.cleanup)
                (Path(temp.name) / "repopulated").mkdir()
                self.assertTrue(Path(temp.name).is_dir())

        result = unittest.TestResult()
        with mock.patch("os.rmdir", side_effect=OSError(39, "Directory not empty")):
            unittest.TestLoader().loadTestsFromTestCase(PlantedFixtureTest).run(result)
        return result

    def test_a_planted_teardown_failure_leaves_the_run_reporting_the_tests_own_outcome(self) -> None:
        """The composition the two controls above do not prove: what unittest's verdict becomes.

        `addCleanup(temp.cleanup)` is how every fixture in this suite disposes of its tree, and a
        cleanup that raises is reported as `ERROR: <test name>` against a test whose assertions all
        passed - the whole observed defect, and not something either the coverage check or the
        cleanup-in-isolation check can see. So run a real one-test suite under the planted ENOTEMPTY
        and read unittest's own verdict. The `False` arm is the planted negative: same plant, same
        assertions, disposition removed, and the run reds on the teardown."""
        for ignore, successful in ((True, True), (False, False)):
            with self.subTest(ignore_cleanup_errors=ignore):
                result = self.planted_teardown_run(ignore)
                self.assertEqual(result.failures, [], "the planted test's own assertions must not move")
                self.assertIs(result.wasSuccessful(), successful)
                if not successful:
                    self.assertIn("Directory not empty", result.errors[0][1])


class StartUnattendedTests(unittest.TestCase):
    def test_control_checkout_admission_fails_before_runtime_provider_sync_or_spawn(self) -> None:
        with mock.patch.object(noodles, "control_checkout_admission", side_effect=noodles.GateError("dirty")) as admit, \
             mock.patch.object(noodles, "verify_repository") as verify, \
             mock.patch.object(noodles, "runtime_check") as runtime_check, \
             mock.patch.object(noodles, "provider_sync") as provider_sync, \
             mock.patch.object(noodles.subprocess, "Popen") as popen:
            with self.assertRaisesRegex(noodles.GateError, "dirty"):
                noodles.start_unattended(CANDIDATE_ROOT, "http://noodle.test", 0.25)
        admit.assert_called_once_with(CANDIDATE_ROOT)
        verify.assert_not_called()
        runtime_check.assert_not_called()
        provider_sync.assert_not_called()
        popen.assert_not_called()

    def test_wrapper_polls_repair_reconcile_and_sleeps_before_clean_exit(self) -> None:
        process = mock.Mock(returncode=0)
        process.poll.side_effect = [None, 0, 0]
        policy = {
            "repository": "ed3c/noodles",
            "default_branch": "main",
            "required_check": "verify",
        }

        with mock.patch.object(noodles, "control_checkout_admission", return_value={"branch": "main"}), \
             mock.patch.object(noodles, "verify_repository", return_value={"ok": True, "errors": []}), \
             mock.patch.object(noodles, "runtime_check", return_value={"binary_path": "/tmp/noodle"}), \
             mock.patch.object(noodles, "provider_sync"), \
             mock.patch.object(noodles, "skill_discovery_check"), mock.patch.object(noodles.codex_isolation, "codex_surface_canary"), \
             mock.patch.object(noodles, "protection_policy", return_value=policy), \
             mock.patch.object(noodles, "protection_readback"), \
             mock.patch.object(noodles.runtime_contract, "noodle_project_root", return_value=CANDIDATE_ROOT), \
             mock.patch.object(noodles.daemon_lease, "reject_existing_lease"), \
             mock.patch.object(noodles.daemon_lease, "admit_started_daemon", return_value={"admitted": True}), \
             mock.patch.object(noodles.subprocess, "Popen", return_value=process), \
             mock.patch.object(noodles, "repair_pending_reviews") as repair, \
             mock.patch.object(noodles, "sweep_dead_claims", return_value=[]) as sweep, \
             mock.patch.object(noodles, "reconcile_once") as reconcile, \
             mock.patch.object(time, "sleep") as sleep:
            result = noodles.start_unattended(CANDIDATE_ROOT, "http://noodle.test", 0.25)

        self.assertEqual(result, 0)
        repair.assert_called_once_with(CANDIDATE_ROOT, "http://noodle.test")
        sweep.assert_called_once_with(CANDIDATE_ROOT)
        reconcile.assert_called_once_with(CANDIDATE_ROOT, "http://noodle.test")
        sleep.assert_called_once_with(0.25)
        process.terminate.assert_not_called()

    def repair_receipt(self, subject: str, attempt: int, *, conclusion: str = "failure", job: str = "verify", head: str = "a" * 40) -> dict:
        return {
            "issue_subject": subject,
            "head_sha": head,
            "failed_workflow_run": {"conclusion": conclusion},
            "failed_job": {"name": job, "conclusion": conclusion},
            "repair": {"attempt": attempt},
        }

    def test_wrapper_declares_a_struggle_for_the_repeating_subject_only(self) -> None:
        """ed3c/noodles#323 - the production emitter, both directions. `#900` repeats one signature
        and is declared exactly once at the policy threshold, then contributes nothing further;
        `#901` carries a different signature every attempt and is never declared, so a lane still
        producing evidence is not stopped alongside the one that is not."""
        process = mock.Mock(returncode=0)
        process.poll.side_effect = [None, None, None, None, 0, 0]
        policy = {"repository": "ed3c/noodles", "default_branch": "main", "required_check": "verify"}
        polls = [
            [self.repair_receipt("ed3c/noodles#900", 1), self.repair_receipt("ed3c/noodles#901", 1, conclusion="timed_out")],
            [self.repair_receipt("ed3c/noodles#900", 2), self.repair_receipt("ed3c/noodles#901", 2, conclusion="cancelled")],
            [self.repair_receipt("ed3c/noodles#900", 3), self.repair_receipt("ed3c/noodles#901", 3, job="trusted-preview")],
            [self.repair_receipt("ed3c/noodles#900", 4), self.repair_receipt("ed3c/noodles#901", 4, conclusion="startup_failure")],
        ]

        with mock.patch.object(noodles, "control_checkout_admission", return_value={"branch": "main"}), \
             mock.patch.object(noodles, "verify_repository", return_value={"ok": True, "errors": []}), \
             mock.patch.object(noodles, "runtime_check", return_value={"binary_path": "/tmp/noodle"}), \
             mock.patch.object(noodles, "provider_sync"), \
             mock.patch.object(noodles, "skill_discovery_check"), mock.patch.object(noodles.codex_isolation, "codex_surface_canary"), \
             mock.patch.object(noodles, "protection_policy", return_value=policy), \
             mock.patch.object(noodles, "protection_readback"), \
             mock.patch.object(noodles.runtime_contract, "noodle_project_root", return_value=CANDIDATE_ROOT), \
             mock.patch.object(noodles.daemon_lease, "reject_existing_lease"), \
             mock.patch.object(noodles.daemon_lease, "admit_started_daemon", return_value={"admitted": True}), \
             mock.patch.object(noodles.subprocess, "Popen", return_value=process), \
             mock.patch.object(noodles, "repair_pending_reviews", side_effect=polls), \
             mock.patch.object(noodles, "sweep_dead_claims", return_value=[]), \
             mock.patch.object(noodles, "reconcile_once"), \
             mock.patch.object(time, "sleep"), \
             mock.patch.object(sys, "stderr", io.StringIO()) as captured:
            noodles.start_unattended(CANDIDATE_ROOT, "http://noodle.test", 0.25)
            emitted = captured.getvalue()

        declarations = [line for line in emitted.splitlines() if line.startswith("NOODLES_STRUGGLE_DETECTED:")]
        threshold = json.loads((CANDIDATE_ROOT / "policy/fitness.json").read_text())["struggle_same_signature_attempts"]
        self.assertEqual(len(declarations), 1, emitted)
        self.assertIn("subject ed3c/noodles#900", declarations[0])
        self.assertIn(f"attempts {threshold}", declarations[0])
        self.assertIn("reason same_signature", declarations[0])
        self.assertIn("signature controls=[verify]", declarations[0])
        self.assertNotIn("ed3c/noodles#901", emitted)

    def test_wrapper_refuses_to_start_when_the_repetition_bound_is_not_a_policy_value(self) -> None:
        """Planted negative for the "thresholds live in policy" clause: with the key gone the
        generation fails closed before it spawns anything, rather than falling back to a literal."""
        policy = {"repository": "ed3c/noodles", "default_branch": "main", "required_check": "verify"}
        fitness = json.loads((CANDIDATE_ROOT / "policy/fitness.json").read_text())
        del fitness["struggle_same_signature_attempts"]
        with mock.patch.object(noodles, "control_checkout_admission", return_value={"branch": "main"}), \
             mock.patch.object(noodles, "verify_repository", return_value={"ok": True, "errors": []}), \
             mock.patch.object(noodles, "runtime_check", return_value={"binary_path": "/tmp/noodle"}), \
             mock.patch.object(noodles, "provider_sync"), \
             mock.patch.object(noodles, "skill_discovery_check"), mock.patch.object(noodles.codex_isolation, "codex_surface_canary"), \
             mock.patch.object(noodles, "protection_policy", return_value=policy), \
             mock.patch.object(noodles, "protection_readback"), \
             mock.patch.object(noodles, "load_json", return_value=fitness), \
             mock.patch.object(noodles.subprocess, "Popen") as popen:
            with self.assertRaisesRegex(noodles.GateError, "struggle_same_signature_attempts"):
                noodles.start_unattended(CANDIDATE_ROOT, "http://noodle.test", 0.25)
        popen.assert_not_called()

    def test_wrapper_does_not_swallow_non_gate_exceptions(self) -> None:
        process = mock.Mock(returncode=0)
        process.poll.side_effect = [None, None]
        policy = {"repository": "ed3c/noodles", "default_branch": "main", "required_check": "verify"}
        with mock.patch.object(noodles, "control_checkout_admission", return_value={"branch": "main"}), mock.patch.object(noodles, "verify_repository", return_value={"ok": True, "errors": []}), mock.patch.object(noodles, "runtime_check", return_value={"binary_path": "/tmp/noodle"}), mock.patch.object(noodles, "provider_sync"), mock.patch.object(noodles, "skill_discovery_check"), mock.patch.object(noodles.codex_isolation, "codex_surface_canary"), mock.patch.object(noodles, "protection_policy", return_value=policy), mock.patch.object(noodles, "protection_readback"), mock.patch.object(noodles.runtime_contract, "noodle_project_root", return_value=CANDIDATE_ROOT), mock.patch.object(noodles.daemon_lease, "reject_existing_lease"), mock.patch.object(noodles.daemon_lease, "admit_started_daemon", return_value={"admitted": True}), mock.patch.object(noodles.subprocess, "Popen", return_value=process), mock.patch.object(noodles, "repair_pending_reviews", side_effect=RuntimeError("boom")):
            with self.assertRaisesRegex(RuntimeError, "boom"):
                noodles.start_unattended(CANDIDATE_ROOT, "http://noodle.test", 0.25)
        process.terminate.assert_called_once()

    def test_script_mode_repair_path_shares_one_gate_error_identity(self) -> None:
        readback = script_mode_gateerror_identity()
        self.assertEqual(validate_script_mode_gateerror_identity(readback), [])

    def test_documented_start_entrypoint_retries_delayed_listener_in_script_mode(self) -> None:
        result = start_entrypoint_with_delayed_listener()
        assert_valid_start_entrypoint_receipt(result)

    def test_documented_start_entrypoint_negative_control_detects_unreachable_listener(self) -> None:
        result = start_entrypoint_with_delayed_listener(start_listener=False)
        with self.assertRaisesRegex(AssertionError, "listener never became reachable|listener never served snapshot readback"):
            assert_valid_start_entrypoint_receipt(result)

    def test_offline_start_entrypoint_retries_delayed_listener_with_codex_real_bin_exported(self) -> None:
        with mock.patch.dict(os.environ, {"NOODLES_OFFLINE_TESTS": "1"}, clear=False):
            result = start_entrypoint_with_delayed_listener()
        assert_valid_start_entrypoint_receipt(result)

    def test_start_entrypoint_terminates_promptly_on_admission_receipt_line(self) -> None:
        # constraint: planted control - stub prints the admission receipt line, so termination must land well before the grace ceiling, proving the line-triggered path fires
        result = start_entrypoint_with_delayed_listener(emit_admission_receipt=True)
        assert_valid_start_entrypoint_receipt(result)
        self.assertIs(result.get("admission_receipt_seen"), True)
        wait_seconds = result.get("admission_wait_seconds")
        assert isinstance(wait_seconds, float)
        self.assertLess(
            wait_seconds,
            ADMISSION_RECEIPT_GRACE_SECONDS / 2,
            "admission receipt line took as long to notice as a silent entrypoint would",
        )

    def _assert_admission_termination_shape(self, result) -> None:
        # constraint: two-state oracle - an entrypoint with real admission (ed3c/noodles#45 candidate) admits against the serving stub and emits its receipt, so termination must be receipt-triggered; one without (current main) never prints the line, so termination must fall back to the grace deadline
        wait_seconds = result.get("admission_wait_seconds")
        assert isinstance(wait_seconds, float)
        if result.get("admission_receipt_seen") is True:
            self.assertLess(
                wait_seconds,
                ADMISSION_RECEIPT_GRACE_SECONDS / 2,
                "entrypoint emitted an admission receipt yet termination waited for the grace ceiling",
            )
        else:
            self.assertIs(result.get("admission_receipt_seen"), False)
            self.assertGreaterEqual(
                wait_seconds,
                ADMISSION_RECEIPT_GRACE_SECONDS - 0.5,
                "silent entrypoint was terminated before the grace ceiling elapsed",
            )
            self.assertLess(
                wait_seconds,
                ADMISSION_RECEIPT_GRACE_SECONDS + 2,
                "terminator overran the grace ceiling by more than scheduling slack accounts for",
            )

    def test_start_entrypoint_terminates_at_grace_deadline_when_admission_receipt_never_arrives(self) -> None:
        result = start_entrypoint_with_delayed_listener()
        assert_valid_start_entrypoint_receipt(result)
        self._assert_admission_termination_shape(result)

    def test_admission_termination_shape_rejects_mismatched_states(self) -> None:
        # constraint: planted control - proves both branches of the two-state oracle are falsifiable rather than vacuous
        with self.assertRaises(AssertionError):
            self._assert_admission_termination_shape(
                {"admission_receipt_seen": True, "admission_wait_seconds": ADMISSION_RECEIPT_GRACE_SECONDS + 0.1}
            )
        with self.assertRaises(AssertionError):
            self._assert_admission_termination_shape(
                {"admission_receipt_seen": False, "admission_wait_seconds": 0.1}
            )

    def test_start_entrypoint_receipt_accepts_admission_evidence_without_legacy_repair_diagnostic(self) -> None:
        # constraint: planted control - the ed3c/noodles#45 lease-admission candidate replaces the repair-retry path entirely, so this stderr never carries the legacy diagnostic; shape matches noodles.py's real compact `{"daemon_lease": receipt}` emission
        receipt = {
            "returncode": 0,
            "stderr": '{"daemon_lease":{"admitted":true,"listener_pids":[4242],"loop_state":"running"}}\n',
            "entrypoint_exists": True,
            "listener_after_exit": [],
            "lease_after_exit": "4242",
        }
        self.assertEqual(validate_start_entrypoint_receipt(receipt), [])

    def test_start_entrypoint_receipt_rejects_stderr_with_neither_diagnostic(self) -> None:
        # constraint: planted control - stderr carries neither the legacy repair diagnostic nor admission-path evidence, so both the widened connection check and the lane's admission assertions must fail
        receipt = {
            "returncode": 0,
            "stderr": "nothing relevant here\n",
            "entrypoint_exists": True,
            "listener_after_exit": [],
            "lease_after_exit": "4242",
        }
        self.assertEqual(
            validate_start_entrypoint_receipt(receipt),
            [
                "wrapper never diagnosed startup connection refusal on repair path",
                "wrapper never admitted a truthful Noodle daemon lease",
                "listener ownership readback missing from the admission receipt",
                "listener never served snapshot readback with a live runtime status",
            ],
        )

    def test_start_entrypoint_stub_materializes_live_looking_runtime_surface(self) -> None:
        def assert_materialized(receipt: dict[str, object]) -> None:
            lock_pid = receipt.get("runtime_lock_pid")
            self.assertIsNotNone(lock_pid, "stub never claimed a runtime lock")
            self.assertTrue(str(lock_pid).isdigit(), f"lock did not name a pid: {lock_pid!r}")
            status = receipt.get("runtime_status")
            self.assertIsInstance(status, dict, f"stub never published status.json: {status!r}")
            assert isinstance(status, dict)
            self.assertEqual(status.get("loop_state"), "running")
            self.assertEqual(
                receipt.get("listener_response"),
                {"pending_reviews": [], "unclaimed_orders": []},
                "stub never served a valid /api/snapshot response",
            )

        assert_materialized(start_entrypoint_with_delayed_listener())

        with self.assertRaises(AssertionError):
            assert_materialized(start_entrypoint_with_delayed_listener(start_listener=False))

    def test_codex_real_bin_export_materializes_fixture_only_in_offline_mode(self) -> None:
        temp = tempfile.TemporaryDirectory(prefix="noodles-codex-real-bin-export-", ignore_cleanup_errors=True)
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)

        with mock.patch.dict(os.environ, {"NOODLES_OFFLINE_TESTS": "1"}, clear=False):
            exported = codex_real_bin_export(base)
        self.assertIsNotNone(exported)
        assert exported is not None
        self.assertTrue(Path(exported).is_file())
        self.assertTrue(os.access(exported, os.X_OK))

        env = dict(os.environ)
        env.pop("NOODLES_OFFLINE_TESTS", None)
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertIsNone(codex_real_bin_export(base))

    def test_codex_real_bin_override_is_load_bearing_for_planted_resolver(self) -> None:
        temp = tempfile.TemporaryDirectory(prefix="noodles-codex-real-bin-fixture-", ignore_cleanup_errors=True)
        self.addCleanup(temp.cleanup)
        fake_codex = Path(temp.name) / "fake-codex"
        write_fake_codex_stub(fake_codex)

        resolved = codex_real_bin_resolution(override=fake_codex)
        self.assertEqual(resolved["returncode"], 0)
        self.assertEqual(str(resolved["stdout"]).strip(), str(fake_codex))

        unresolved = codex_real_bin_resolution(override=None)
        self.assertNotEqual(unresolved["returncode"], 0)
        self.assertIn(
            "NOODLES_CODEX_WRAPPER_FAIL: cannot resolve real codex binary",
            str(unresolved["stderr"]),
        )


class ProviderPhysicalTests(unittest.TestCase):
    def test_exact_detached_checkout_and_readback(self) -> None:
        temp, candidate = provider_fixture()
        self.addCleanup(temp.cleanup)
        old = os.environ.get("NOODLES_TEST_ALLOW_LOCAL_PROVIDER")
        os.environ["NOODLES_TEST_ALLOW_LOCAL_PROVIDER"] = "1"
        try:
            receipts = noodles.provider_sync(candidate)
            lock = json.loads((candidate / "policy/providers.lock.json").read_text())["providers"][0]
            self.assertEqual(receipts[0]["license_blob"], cmd(["git", "rev-parse", "HEAD:LICENSE"], candidate / ".noodle/providers/fixture"))
            expected = {
                "commit": lock["commit"],
                "skill_count": 1,
                "skill_path": "skills/control-noodle",
                "license_path": "LICENSE",
                "admission_path": lock["admission"]["path"],
                "admission_sha256": lock["admission"]["sha256"],
                "admission_skill": lock["admission"]["skill"],
                "admission_skill_tree_sha256": lock["admission"]["skill_tree_sha256"],
                "subject_file_sha256": lock["admission"]["subject_files"],
            }
            for key, value in expected.items(): self.assertEqual(receipts[0][key], value)
            self.assertTrue(receipts[0]["detached"])
            self.assertTrue(receipts[0]["clean"])
            self.assertEqual(noodles.provider_check(candidate)[0]["commit"], receipts[0]["commit"])
            (candidate / ".noodle/providers/fixture/LICENSE").write_text("tampered\n")
            with self.assertRaises(noodles.GateError):
                noodles.provider_check(candidate)
        finally:
            if old is None:
                os.environ.pop("NOODLES_TEST_ALLOW_LOCAL_PROVIDER", None)
            else:
                os.environ["NOODLES_TEST_ALLOW_LOCAL_PROVIDER"] = old

    def test_provider_check_rejects_missing_locked_skill_subpath(self) -> None:
        temp, candidate = provider_fixture(subpath="skills/missing"); self.addCleanup(temp.cleanup)
        with mock.patch.dict(os.environ, {"NOODLES_TEST_ALLOW_LOCAL_PROVIDER": "1"}, clear=False):
            with self.assertRaisesRegex(noodles.GateError, "has no SKILL.md"):
                noodles.provider_sync(candidate)
    def test_provider_check_rejects_missing_locked_license_path(self) -> None:
        temp, candidate = provider_fixture(license_path="NOTICE"); self.addCleanup(temp.cleanup)
        with mock.patch.dict(os.environ, {"NOODLES_TEST_ALLOW_LOCAL_PROVIDER": "1"}, clear=False):
            with self.assertRaisesRegex(noodles.GateError, "license path missing"):
                noodles.provider_sync(candidate)
    def test_provider_sync_materializes_exact_cursor_team_kit_mapping(self) -> None:
        temp, candidate = cursor_pstack_fixture()
        self.addCleanup(temp.cleanup)
        with mock.patch.dict(os.environ, {"NOODLES_TEST_ALLOW_LOCAL_PROVIDER": "1"}, clear=False):
            receipts = noodles.provider_sync(candidate)
        cursor = next(item for item in receipts if item["name"] == runtime_contract.CURSOR_PSTACK_PROVIDER)
        compat_root = Path(cursor["compatibility_root"])
        self.assertTrue((compat_root / "execute" / "SKILL.md").is_file())
        self.assertTrue((compat_root / "schedule" / "SKILL.md").is_file())
        for skill in runtime_contract.CURSOR_PSTACK_COMPAT_SKILLS:
            mapped_root = compat_root / skill
            self.assertTrue(mapped_root.is_dir())
            self.assertFalse(mapped_root.is_symlink())
            skill_file = mapped_root / "SKILL.md"
            self.assertTrue(skill_file.is_symlink())
            self.assertEqual(
                skill_file.resolve(),
                (candidate / runtime_contract.CURSOR_PSTACK_DESTINATION / runtime_contract.CURSOR_PSTACK_COMPAT_SOURCE_ROOT / skill / "SKILL.md").resolve(),
            )
        self.assertEqual(cmd(["git", "status", "--short"], candidate), "")

    def test_provider_check_rejects_cursor_provider_dirty_checkout_with_diagnostic(self) -> None:
        temp, candidate = cursor_pstack_fixture()
        self.addCleanup(temp.cleanup)
        installed_license = candidate / runtime_contract.CURSOR_PSTACK_DESTINATION / "pstack/LICENSE"
        with mock.patch.dict(os.environ, {"NOODLES_TEST_ALLOW_LOCAL_PROVIDER": "1"}, clear=False):
            noodles.provider_sync(candidate)
            installed_license.write_text("tampered\n")
            with self.assertRaisesRegex(noodles.GateError, "provider cursor-pstack checkout is dirty"):
                noodles.provider_check(candidate)

    def test_provider_sync_rematerializes_only_control_cli_without_source_drift(self) -> None:
        temp, candidate = cursor_pstack_fixture()
        self.addCleanup(temp.cleanup)
        compat_root = candidate / runtime_contract.PROJECT_SKILLS_ROOT
        control_cli_root = compat_root / "control-cli"
        deslop_root = compat_root / "deslop"
        provider_source_root = candidate / runtime_contract.CURSOR_PSTACK_DESTINATION / runtime_contract.CURSOR_PSTACK_COMPAT_SOURCE_ROOT
        control_cli_source_root = provider_source_root / "control-cli"
        control_ui_skill = provider_source_root / "control-ui/SKILL.md"
        unrelated_skill = provider_source_root / "review-and-ship/SKILL.md"
        with mock.patch.dict(os.environ, {"NOODLES_TEST_ALLOW_LOCAL_PROVIDER": "1"}, clear=False):
            noodles.provider_sync(candidate)
            expected_source_digest = tree_digest(provider_source_root)
            expected_deslop_digest = tree_digest(deslop_root)
            control_ui_bytes = control_ui_skill.read_bytes()
            unrelated_bytes = unrelated_skill.read_bytes()
            shutil.rmtree(control_cli_root)
            os.symlink(
                os.path.relpath(provider_source_root, start=control_cli_root.parent),
                control_cli_root,
                target_is_directory=True,
            )

            self.assertTrue(control_cli_root.is_symlink())
            self.assertEqual(control_cli_root.resolve(), provider_source_root.resolve())

            noodles.provider_sync(candidate)

        self.assertEqual(tree_digest(provider_source_root), expected_source_digest)
        self.assertEqual(control_ui_skill.read_bytes(), control_ui_bytes)
        self.assertEqual(unrelated_skill.read_bytes(), unrelated_bytes)
        self.assertEqual(tree_digest(deslop_root), expected_deslop_digest)
        self.assertTrue(control_cli_root.is_dir())
        self.assertFalse(control_cli_root.is_symlink())
        self.assertEqual(sorted(path.name for path in control_cli_root.iterdir()), sorted(path.name for path in control_cli_source_root.iterdir()))
        for entry in control_cli_root.iterdir():
            self.assertTrue(entry.is_symlink())
            self.assertEqual(entry.resolve(), (control_cli_source_root / entry.name).resolve())
        self.assertFalse((compat_root / "control-ui").exists())
        self.assertFalse((compat_root / "review-and-ship").exists())

    def test_provider_check_rejects_missing_mapped_cursor_skill_file(self) -> None:
        temp, candidate = cursor_pstack_fixture()
        self.addCleanup(temp.cleanup)
        provider_source_root = candidate / runtime_contract.CURSOR_PSTACK_DESTINATION / runtime_contract.CURSOR_PSTACK_COMPAT_SOURCE_ROOT
        with mock.patch.dict(os.environ, {"NOODLES_TEST_ALLOW_LOCAL_PROVIDER": "1"}, clear=False):
            noodles.provider_sync(candidate)
            expected_digest = tree_digest(provider_source_root)
            (candidate / runtime_contract.PROJECT_SKILLS_ROOT / "control-cli" / "SKILL.md").unlink()
            with self.assertRaisesRegex(noodles.GateError, "control-cli missing mapped entry SKILL.md"):
                noodles.provider_check(candidate)
        self.assertEqual(tree_digest(provider_source_root), expected_digest)
        self.assertTrue((provider_source_root / "deslop" / "SKILL.md").is_file())

    def test_provider_check_rejects_dangling_mapped_cursor_skill_file(self) -> None:
        temp, candidate = cursor_pstack_fixture()
        self.addCleanup(temp.cleanup)
        provider_source_root = candidate / runtime_contract.CURSOR_PSTACK_DESTINATION / runtime_contract.CURSOR_PSTACK_COMPAT_SOURCE_ROOT
        with mock.patch.dict(os.environ, {"NOODLES_TEST_ALLOW_LOCAL_PROVIDER": "1"}, clear=False):
            noodles.provider_sync(candidate)
            expected_digest = tree_digest(provider_source_root)
            mapped_skill = candidate / runtime_contract.PROJECT_SKILLS_ROOT / "control-cli" / "SKILL.md"
            mapped_skill.unlink()
            os.symlink("../missing/SKILL.md", mapped_skill)
            with self.assertRaisesRegex(noodles.GateError, "control-cli entry SKILL.md does not resolve to pinned provider bytes"):
                noodles.provider_check(candidate)
        self.assertEqual(tree_digest(provider_source_root), expected_digest)
        self.assertTrue((provider_source_root / "control-ui/SKILL.md").is_file())
        self.assertTrue((provider_source_root / "review-and-ship/SKILL.md").is_file())


class RuntimePhysicalTests(unittest.TestCase):
    def runtime_candidate(self, version: str = "v9.9.9") -> tuple[tempfile.TemporaryDirectory[str], Path, Path, str]:
        temp = tempfile.TemporaryDirectory(prefix="noodles-runtime-test-", ignore_cleanup_errors=True)
        candidate = Path(temp.name) / "candidate"
        copy_tracked(CANDIDATE_ROOT, candidate)
        runtime_path = Path(temp.name) / "bin"
        runtime_path.mkdir()
        binary = runtime_path / "noodle"
        write_noodle_stub(binary, version)
        lock_path = candidate / "policy/runtime.lock.json"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "runtime": {
                "repository": "poteto/noodle",
                "release": version,
                "commit": "1" * 40,
                "command": "noodle",
                "platforms": {
                    "darwin_arm64": {
                        "asset_name": "noodle_darwin_arm64.tar.gz",
                        "asset_sha256": "2" * 64,
                        "binary_sha256": runtime_contract.sha256_file(binary),
                    }
                },
            },
        }
        lock_path.write_text(json.dumps(payload))
        return temp, candidate, binary, "darwin_arm64"

    def test_runtime_check_reads_back_exact_release_commit_asset_and_binary(self) -> None:
        temp, candidate, binary, platform_key = self.runtime_candidate()
        self.addCleanup(temp.cleanup)
        reader = runtime_release_reader("v9.9.9", "1" * 40, "noodle_darwin_arm64.tar.gz", "2" * 64)
        with mock.patch.dict(os.environ, {"PATH": f"{binary.parent}:{os.environ.get('PATH', '')}"}, clear=False):
            receipt = runtime_contract.runtime_check(candidate, reader, error_cls=noodles.GateError, platform_key=platform_key)
        self.assertEqual(receipt["version"], "v9.9.9")
        self.assertEqual(receipt["commit"], "1" * 40)
        self.assertEqual(receipt["binary_sha256"], runtime_contract.sha256_file(binary))
        self.assertTrue((candidate / ".noodle/receipts/runtime/noodle.json").exists())

    def test_runtime_check_rejects_missing_binary(self) -> None:
        temp, candidate, _binary, platform_key = self.runtime_candidate()
        self.addCleanup(temp.cleanup)
        reader = runtime_release_reader("v9.9.9", "1" * 40, "noodle_darwin_arm64.tar.gz", "2" * 64)
        with mock.patch.dict(os.environ, {"PATH": ""}, clear=False):
            with self.assertRaisesRegex(noodles.GateError, "command not found"):
                runtime_contract.runtime_check(candidate, reader, error_cls=noodles.GateError, platform_key=platform_key)

    def test_runtime_check_rejects_version_drift(self) -> None:
        temp, candidate, binary, platform_key = self.runtime_candidate(version="v9.9.9")
        self.addCleanup(temp.cleanup)
        write_noodle_stub(binary, "v9.9.8")
        lock = json.loads((candidate / "policy/runtime.lock.json").read_text())
        lock["runtime"]["platforms"][platform_key]["binary_sha256"] = runtime_contract.sha256_file(binary)
        (candidate / "policy/runtime.lock.json").write_text(json.dumps(lock))
        reader = runtime_release_reader("v9.9.9", "1" * 40, "noodle_darwin_arm64.tar.gz", "2" * 64)
        with mock.patch.dict(os.environ, {"PATH": f"{binary.parent}:{os.environ.get('PATH', '')}"}, clear=False):
            with self.assertRaisesRegex(noodles.GateError, "version"):
                runtime_contract.runtime_check(candidate, reader, error_cls=noodles.GateError, platform_key=platform_key)

    def test_runtime_check_rejects_asset_checksum_drift(self) -> None:
        temp, candidate, binary, platform_key = self.runtime_candidate()
        self.addCleanup(temp.cleanup)
        reader = runtime_release_reader("v9.9.9", "1" * 40, "noodle_darwin_arm64.tar.gz", "3" * 64)
        with mock.patch.dict(os.environ, {"PATH": f"{binary.parent}:{os.environ.get('PATH', '')}"}, clear=False):
            with self.assertRaisesRegex(noodles.GateError, "asset digest"):
                runtime_contract.runtime_check(candidate, reader, error_cls=noodles.GateError, platform_key=platform_key)

    def test_skill_discovery_reads_all_configured_paths(self) -> None:
        temp, candidate, binary, _platform_key = self.runtime_candidate()
        self.addCleanup(temp.cleanup)
        output = write_skill_discovery_fixture(candidate)
        compat_source_root = (candidate / runtime_contract.CURSOR_PSTACK_DESTINATION / runtime_contract.CURSOR_PSTACK_COMPAT_SOURCE_ROOT).resolve()
        cursor_root = (candidate / runtime_contract.CURSOR_PSTACK_NATIVE_ROOT).resolve()
        project_root = (candidate / runtime_contract.PROJECT_SKILLS_ROOT).resolve()
        with mock.patch.dict(os.environ, {"NOODLES_TEST_SKILLS_OUTPUT": output}, clear=False):
            receipt = runtime_contract.skill_discovery_check(candidate, binary, error_cls=noodles.GateError)
        expected_paths = {
            "control-noodle": str((candidate / runtime_contract.CONTROL_NOODLE_DISCOVERY_ROOT / "SKILL.md").resolve()),
            "control-cli": str((compat_source_root / "control-cli/SKILL.md").resolve()),
            "poteto-mode": str((cursor_root / "poteto-mode/SKILL.md").resolve()),
            "schedule": str((candidate / runtime_contract.PROJECT_SKILLS_ROOT / "schedule" / "SKILL.md").resolve()),
        }
        for skill, path in expected_paths.items(): self.assertEqual(receipt["required_skill_paths"][skill]["resolved_path"], path)
        self.assertEqual(receipt["skills_by_path"][str(project_root)], 5)
        self.assertTrue((candidate / ".noodle/receipts/runtime/skills.json").exists())

    def test_skill_discovery_rejects_missing_configured_path(self) -> None:
        temp, candidate, binary, _platform_key = self.runtime_candidate()
        self.addCleanup(temp.cleanup)
        project_skill = (candidate / ".agents/skills/execute").resolve()
        output = f"execute\t{project_skill.parent}\ttrue\t{project_skill / 'SKILL.md'}\n"
        with mock.patch.dict(os.environ, {"NOODLES_TEST_SKILLS_OUTPUT": output}, clear=False):
            with self.assertRaisesRegex(noodles.GateError, "missing configured paths"):
                runtime_contract.skill_discovery_check(candidate, binary, error_cls=noodles.GateError)

    def test_skill_discovery_rejects_unrelated_cursor_team_kit_skill(self) -> None:
        temp, candidate, binary, _platform_key = self.runtime_candidate()
        self.addCleanup(temp.cleanup)
        output = write_skill_discovery_fixture(candidate, compat_skills=("control-cli", "deslop", "control-ui"))
        with mock.patch.dict(os.environ, {"NOODLES_TEST_SKILLS_OUTPUT": output}, clear=False):
            with self.assertRaisesRegex(noodles.GateError, "compatibility discovery must expose exactly control-cli, deslop"):
                runtime_contract.skill_discovery_check(candidate, binary, error_cls=noodles.GateError)

    def test_skill_discovery_rejects_configured_cursor_team_kit_root(self) -> None:
        temp, candidate, binary, _platform_key = self.runtime_candidate()
        self.addCleanup(temp.cleanup)
        config_path = candidate / ".noodle.toml"
        config = config_path.read_text(encoding="utf-8")
        addition = '  ".noodle/providers/cursor-pstack/cursor-team-kit/skills",\n'
        self.assertNotIn(addition, config)
        current = '  ".noodle/providers/skill-concerns/skills/control-noodle"\n'
        config_path.write_text(config.replace(current, addition + current), encoding="utf-8")
        with self.assertRaisesRegex(noodles.GateError, "must not expose the entire cursor-team-kit/skills root"):
            runtime_contract.skill_discovery_check(candidate, binary, error_cls=noodles.GateError)

    def test_skill_discovery_rejects_missing_poteto_playbook(self) -> None:
        temp, candidate, binary, _platform_key = self.runtime_candidate()
        self.addCleanup(temp.cleanup)
        output = write_skill_discovery_fixture(candidate, playbooks=("investigation.md", "feature.md"))
        with mock.patch.dict(os.environ, {"NOODLES_TEST_SKILLS_OUTPUT": output}, clear=False):
            with self.assertRaisesRegex(noodles.GateError, "missing pinned playbook bytes"):
                runtime_contract.skill_discovery_check(candidate, binary, error_cls=noodles.GateError)


CONTROL_URL = "http://127.0.0.1:3210"


class DaemonLeaseTests(unittest.TestCase):
    def lease_project(self) -> Path:
        temp = tempfile.TemporaryDirectory(prefix="noodles-lease-test-", ignore_cleanup_errors=True)
        self.addCleanup(temp.cleanup)
        project = Path(temp.name)
        (project / ".noodle").mkdir()
        return project

    def plant(self, project: Path, *, lease: str | None = None, loop_state: str | None = "running") -> None:
        if lease is not None:
            (project / daemon_lease.LOCK_RELATIVE).write_text(lease, encoding="utf-8")
        if loop_state is not None:
            (project / daemon_lease.STATUS_RELATIVE).write_text(
                json.dumps({"loop_state": loop_state, "mode": "supervised", "max_concurrency": 4}), encoding="utf-8"
            )

    def child(self, pid: int, returncode: object = None) -> mock.Mock:
        return mock.Mock(pid=pid, poll=mock.Mock(return_value=returncode))

    def dead_pid(self) -> int:
        spare = subprocess.Popen([sys.executable, "-c", "raise SystemExit(0)"])
        spare.wait(timeout=30)
        return spare.pid

    def defect(self, project: Path, child_pid: int, *, owners: list[int], snapshot: tuple[object, str] = ({"pending_reviews": []}, "")) -> str:
        with mock.patch.object(daemon_lease, "listener_pids", return_value=owners), \
             mock.patch.object(daemon_lease, "read_snapshot", return_value=snapshot):
            diagnostic, _receipt = daemon_lease.admission_defect(project, CONTROL_URL, child_pid)
        return diagnostic

    def test_admission_receipt_binds_child_listener_snapshot_and_status(self) -> None:
        project = self.lease_project()
        self.plant(project, lease=f"{os.getpid()}\n")
        with mock.patch.object(daemon_lease, "listener_pids", return_value=[os.getpid()]), \
             mock.patch.object(daemon_lease, "read_snapshot", return_value=({"pending_reviews": []}, "")):
            receipt = daemon_lease.admit_started_daemon(
                project, CONTROL_URL, self.child(os.getpid()), error_cls=noodles.GateError, timeout=1.0, poll_interval=0.01
            )
        self.assertEqual(receipt["lease_pid"], os.getpid())
        self.assertEqual(receipt["child_pid"], os.getpid())
        self.assertEqual(receipt["listener_pids"], [os.getpid()])
        self.assertEqual(receipt["control_host"], "127.0.0.1")
        self.assertEqual(receipt["control_port"], 3210)
        self.assertEqual(receipt["loop_state"], "running")
        self.assertEqual(receipt["snapshot_keys"], ["pending_reviews"])
        self.assertTrue(receipt["admitted"])
        self.assertEqual(receipt["lease_path"], str(project / daemon_lease.LOCK_RELATIVE))

    def test_planted_stale_status_json_without_lease_fails_closed(self) -> None:
        project = self.lease_project()
        self.plant(project, loop_state="running")
        with self.assertRaises(noodles.GateError) as raised:
            daemon_lease.reject_existing_lease(project, error_cls=noodles.GateError)
        self.assertIn("noodles-start status-ghost:", str(raised.exception))
        self.assertIn("loop_state='running'", str(raised.exception))

    def test_planted_dead_pid_lease_fails_closed(self) -> None:
        project = self.lease_project()
        dead = self.dead_pid()
        self.plant(project, lease=f"{dead}\n", loop_state="running")
        with self.assertRaises(noodles.GateError) as raised:
            daemon_lease.reject_existing_lease(project, error_cls=noodles.GateError)
        self.assertIn("noodles-start lease-dead-pid:", str(raised.exception))
        self.assertIn(str(dead), str(raised.exception))

    def test_planted_wrapper_only_lease_fails_closed(self) -> None:
        project = self.lease_project()
        self.plant(project, lease=f"{os.getpid()}\n")
        diagnostic = self.defect(project, os.getpid() + 1, owners=[os.getpid()])
        self.assertIn("noodles-start lease-foreign-pid:", diagnostic)
        self.assertIn(f"spawned Noodle child pid {os.getpid() + 1}", diagnostic)

    def test_planted_child_without_listener_fails_closed(self) -> None:
        project = self.lease_project()
        self.plant(project, lease=f"{os.getpid()}\n")
        diagnostic = self.defect(project, os.getpid(), owners=[])
        self.assertIn("noodles-start listener-absent:", diagnostic)
        self.assertIn("127.0.0.1:3210", diagnostic)

    def test_planted_unrelated_port_listener_fails_closed(self) -> None:
        project = self.lease_project()
        self.plant(project, lease=f"{os.getpid()}\n")
        diagnostic = self.defect(project, os.getpid(), owners=[os.getpid() + 7])
        self.assertIn("noodles-start listener-foreign:", diagnostic)
        self.assertIn(str(os.getpid() + 7), diagnostic)

    def test_planted_unreadable_snapshot_fails_closed(self) -> None:
        project = self.lease_project()
        self.plant(project, lease=f"{os.getpid()}\n")
        diagnostic = self.defect(project, os.getpid(), owners=[os.getpid()], snapshot=(None, "connection refused"))
        self.assertIn("noodles-start snapshot-unreadable:", diagnostic)

    def test_planted_inconsistent_runtime_status_fails_closed(self) -> None:
        project = self.lease_project()
        self.plant(project, lease=f"{os.getpid()}\n", loop_state="stopped")
        diagnostic = self.defect(project, os.getpid(), owners=[os.getpid()])
        self.assertIn("noodles-start status-inconsistent:", diagnostic)

    def test_every_planted_fake_alive_state_reports_a_distinct_diagnostic(self) -> None:
        project = self.lease_project()
        dead = self.dead_pid()
        codes: list[str] = []
        for planted in ("stale-status", "dead-pid", "wrapper-only", "child-without-listener", "unrelated-port-listener"):
            fresh = self.lease_project()
            if planted == "stale-status":
                self.plant(fresh, loop_state="running")
                with self.assertRaises(noodles.GateError) as raised:
                    daemon_lease.reject_existing_lease(fresh, error_cls=noodles.GateError)
                diagnostic = str(raised.exception)
            elif planted == "dead-pid":
                self.plant(fresh, lease=f"{dead}\n")
                with self.assertRaises(noodles.GateError) as raised:
                    daemon_lease.reject_existing_lease(fresh, error_cls=noodles.GateError)
                diagnostic = str(raised.exception)
            elif planted == "wrapper-only":
                self.plant(fresh, lease=f"{os.getpid()}\n")
                diagnostic = self.defect(fresh, os.getpid() + 1, owners=[os.getpid()])
            elif planted == "child-without-listener":
                self.plant(fresh, lease=f"{os.getpid()}\n")
                diagnostic = self.defect(fresh, os.getpid(), owners=[])
            else:
                self.plant(fresh, lease=f"{os.getpid()}\n")
                diagnostic = self.defect(fresh, os.getpid(), owners=[os.getpid() + 7])
            codes.append(diagnostic.split(":")[0])
        self.assertEqual(len(set(codes)), 5, codes)
        self.assertTrue(all(code.startswith("noodles-start ") for code in codes), codes)
        self.assertTrue((project / ".noodle").is_dir())

    def test_second_concurrent_start_fails_closed_without_spawning_a_second_child(self) -> None:
        project = self.lease_project()
        self.plant(project, lease=f"{os.getpid()}\n")
        policy = {"repository": "ed3c/noodles", "default_branch": "main", "required_check": "verify"}
        with mock.patch.object(noodles, "control_checkout_admission", return_value={"branch": "main"}), \
             mock.patch.object(noodles, "verify_repository", return_value={"ok": True, "errors": []}), \
             mock.patch.object(noodles, "runtime_check", return_value={"binary_path": "/tmp/noodle"}), \
             mock.patch.object(noodles, "provider_sync"), mock.patch.object(noodles, "skill_discovery_check"), \
             mock.patch.object(noodles.codex_isolation, "codex_surface_canary"), \
             mock.patch.object(noodles, "protection_policy", return_value=policy), \
             mock.patch.object(noodles, "protection_readback"), \
             mock.patch.object(noodles.runtime_contract, "noodle_project_root", return_value=project), \
             mock.patch.object(noodles.subprocess, "Popen") as popen:
            with self.assertRaisesRegex(noodles.GateError, "noodles-start lease-held:"):
                noodles.start_unattended(CANDIDATE_ROOT, CONTROL_URL, 0.25)
        popen.assert_not_called()

    def test_failed_startup_terminates_only_its_own_child_and_never_calls_reset(self) -> None:
        project = self.lease_project()
        evidence = project / ".noodle/loop-events.ndjson"
        evidence.write_text("planted runtime evidence\n", encoding="utf-8")
        decoy = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.addCleanup(decoy.wait)
        self.addCleanup(decoy.kill)
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        self.addCleanup(child.poll)
        policy = {"repository": "ed3c/noodles", "default_branch": "main", "required_check": "verify"}
        with mock.patch.object(noodles, "control_checkout_admission", return_value={"branch": "main"}), \
             mock.patch.object(noodles, "verify_repository", return_value={"ok": True, "errors": []}), \
             mock.patch.object(noodles, "runtime_check", return_value={"binary_path": "/tmp/noodle"}), \
             mock.patch.object(noodles, "provider_sync"), mock.patch.object(noodles, "skill_discovery_check"), \
             mock.patch.object(noodles.codex_isolation, "codex_surface_canary"), \
             mock.patch.object(noodles, "protection_policy", return_value=policy), \
             mock.patch.object(noodles, "protection_readback"), \
             mock.patch.object(noodles.runtime_contract, "noodle_project_root", return_value=project), \
             mock.patch.object(daemon_lease, "listener_pids", return_value=[]), \
             mock.patch.object(noodles.subprocess, "Popen", return_value=child) as popen, \
             mock.patch.object(noodles, "repair_pending_reviews") as repair, \
             mock.patch.object(noodles, "reconcile_once") as reconcile:
            with self.assertRaisesRegex(noodles.GateError, "noodles-start lease-absent:"):
                noodles.start_unattended(CANDIDATE_ROOT, CONTROL_URL, 0.25, admission_timeout=0.4)
        popen.assert_called_once()
        self.assertNotIn("reset", [str(item) for call in popen.call_args_list for item in (call.args[0] if call.args else [])])
        repair.assert_not_called()
        reconcile.assert_not_called()
        self.assertIsNotNone(child.wait(timeout=10))
        self.assertIsNone(decoy.poll())
        self.assertEqual(evidence.read_text(encoding="utf-8"), "planted runtime evidence\n")

    def test_start_source_never_invokes_noodle_reset(self) -> None:
        source = (CANDIDATE_ROOT / "daemon_lease.py").read_text(encoding="utf-8")
        self.assertNotIn("reset", source)
        self.assertIn("terminate", source)

    def test_listener_pid_parser_reads_lsof_pid_output(self) -> None:
        with mock.patch.object(daemon_lease.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "20776\n20776\n881\n", "")):
            self.assertEqual(daemon_lease.listener_pids("127.0.0.1", 3210), [881, 20776])
        with mock.patch.object(daemon_lease.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "")):
            self.assertEqual(daemon_lease.listener_pids("127.0.0.1", 3210), [])
        with mock.patch.object(daemon_lease.subprocess, "run", side_effect=FileNotFoundError("lsof")):
            with self.assertRaisesRegex(RuntimeError, "noodles-start listener-probe-missing:"):
                daemon_lease.listener_pids("127.0.0.1", 3210)

    def test_bounded_admission_times_out_with_the_last_observed_defect(self) -> None:
        project = self.lease_project()
        with mock.patch.object(daemon_lease, "listener_pids", return_value=[]):
            with self.assertRaises(noodles.GateError) as raised:
                daemon_lease.admit_started_daemon(
                    project, CONTROL_URL, self.child(os.getpid()), error_cls=noodles.GateError, timeout=0.2, poll_interval=0.01
                )
        self.assertIn("noodles-start admission-timeout:", str(raised.exception))
        self.assertIn("noodles-start lease-absent:", str(raised.exception))

    def test_child_exit_before_admission_fails_closed_as_wrapper_without_child(self) -> None:
        project = self.lease_project()
        with self.assertRaises(noodles.GateError) as raised:
            daemon_lease.admit_started_daemon(
                project, CONTROL_URL, self.child(os.getpid(), returncode=1), error_cls=noodles.GateError, timeout=0.2, poll_interval=0.01
            )
        self.assertIn("noodles-start lease-child-exited:", str(raised.exception))


class LintGateTests(unittest.TestCase):
    """ed3c/noodles#413 - the syntax coordinate's refusal surface, judged in both directions.

    The gate has two halves that fail differently and are therefore controlled separately: ruff run
    with the TRUSTED config over the candidate's sources, and the justified-suppression rule that
    ruff cannot express (PGH004 refuses a code-less directive; nothing in ruff can ask whether a
    reason was written next to it).

    The trusted-policy leg is the one that matters and the one a fixture can get wrong: it is not
    enough to show that a violation reds, because a gate that read the candidate's config would red
    on the same input. The control has to show the SAME candidate tree judged from two different
    policy roots and disagreeing - trusted-side red, candidate-side green - which is exactly the
    authority asymmetry the atom claims and the only shape that could distinguish the two readings.

    Ceiling, measured rather than assumed: the issue's wording for the escape hatch is a candidate
    carrying `ignore = ["ALL"]`. On the pinned ruff 0.15.2 that key does not expand `ALL` and
    suppresses nothing, so a fixture built on it alone would be a control that controls nothing - it
    would red from either policy root and prove neither reading. The fixture therefore carries that
    literal AND `select = []`, which is the working off-switch, so the candidate-side leg is really
    green and the disagreement is real."""

    SUFFIXED_BLIND_EXCEPT = "def probe() -> None:\n    try:\n        pass\n    except Exception as exc:{suffix}\n        print(exc)\n"
    CLEAN = "def probe() -> None:\n    print('nothing to refuse here')\n"
    ESCAPE_HATCH_POLICY = '[lint]\nselect = []\nignore = ["ALL"]\n'
    REASON = "the listener thread has no other channel back to the assertion"

    def planted(self, source: str, *, candidate_policy: str | None = None) -> tuple[Path, Path, set[str]]:
        """A trusted root carrying THIS repository's real lint policy, and a separate candidate root."""
        temp = tempfile.TemporaryDirectory(prefix="noodles-lint-test-", ignore_cleanup_errors=True)
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        trusted, candidate = base / "trusted", base / "candidate"
        for root in (trusted, candidate):
            (root / "policy").mkdir(parents=True)
        landed = (CANDIDATE_ROOT / noodles.LINT_POLICY_PATH).read_text(encoding="utf-8")
        (trusted / noodles.LINT_POLICY_PATH).write_text(landed, encoding="utf-8")
        (candidate / noodles.LINT_POLICY_PATH).write_text(candidate_policy or landed, encoding="utf-8")
        (candidate / "probe.py").write_text(source, encoding="utf-8")
        return trusted, candidate, {noodles.LINT_POLICY_PATH, "probe.py"}

    def test_a_planted_blind_except_reds_and_the_inverse_edit_restores_green(self) -> None:
        trusted, candidate, paths = self.planted(self.SUFFIXED_BLIND_EXCEPT.format(suffix=""))
        errors = noodles.lint_gate_errors(candidate, trusted, paths)
        self.assertTrue(any("BLE001" in error for error in errors), errors)
        (candidate / "probe.py").write_text(self.CLEAN, encoding="utf-8")
        self.assertEqual(noodles.lint_gate_errors(candidate, trusted, paths), [])

    def test_the_candidate_cannot_switch_off_the_policy_that_judges_it(self) -> None:
        trusted, candidate, paths = self.planted(
            self.SUFFIXED_BLIND_EXCEPT.format(suffix=""), candidate_policy=self.ESCAPE_HATCH_POLICY
        )
        judged_by_trusted = noodles.lint_gate_errors(candidate, trusted, paths)
        judged_by_candidate = noodles.lint_gate_errors(candidate, candidate, paths)
        self.assertTrue(any("BLE001" in error for error in judged_by_trusted), judged_by_trusted)
        self.assertEqual(judged_by_candidate, [])

    def test_a_bare_or_reasonless_suppression_is_refused_and_a_justified_one_passes(self) -> None:
        trusted, candidate, paths = self.planted(self.SUFFIXED_BLIND_EXCEPT.format(suffix=""))
        for suffix, expected in (
            ("  # noqa", "unjustified"),
            ("  # noqa: BLE001", "unjustified"),
            ("  # constraint: x # noqa: BLE001", "unjustified"),
            (f"  # constraint: {self.REASON} # noqa: BLE001", None),
        ):
            with self.subTest(suffix=suffix.strip()):
                (candidate / "probe.py").write_text(self.SUFFIXED_BLIND_EXCEPT.format(suffix=suffix), encoding="utf-8")
                errors = noodles.lint_gate_errors(candidate, trusted, paths)
                if expected is None:
                    self.assertEqual(errors, [])
                else:
                    self.assertTrue(any(expected in error for error in errors), errors)

    def test_a_blanket_suppression_is_also_refused_by_the_policy_itself(self) -> None:
        """The suppression discipline has two independent carriers and neither is the other's proof:
        the reason rule above is this repository's, PGH004 is ruff's. A bare directive trips both, so
        the ruff half is asserted where the reason half cannot reach it - inside a tagged comment
        that carries a real reason and still names no rule."""
        trusted, candidate, paths = self.planted(
            self.SUFFIXED_BLIND_EXCEPT.format(suffix=f"  # constraint: {self.REASON} # noqa")
        )
        errors = noodles.lint_gate_errors(candidate, trusted, paths)
        self.assertTrue(any("PGH004" in error for error in errors), errors)

    def test_prose_that_merely_names_the_directive_is_not_read_as_one(self) -> None:
        """The scan reads COMMENT tokens, so a docstring quoting the directive is prose, not a
        suppression - the fail-open shape a raw line scan would have."""
        trusted, candidate, paths = self.planted('def probe() -> None:\n    """A docstring mentioning # noqa on purpose."""\n')
        self.assertEqual(noodles.lint_gate_errors(candidate, trusted, paths), [])

    def test_every_absence_around_the_tool_is_its_own_refusal(self) -> None:
        """Four ways this gate can fail to produce evidence, each named rather than passed: no
        trusted policy, a ruff that will not execute, a ruff that errors out, and a ruff that reports
        red while emitting nothing parsable - the shape a version-pin refusal takes."""
        trusted, candidate, paths = self.planted(self.CLEAN)
        (trusted / noodles.LINT_POLICY_PATH).unlink()
        self.assertTrue(any("trusted lint policy missing" in error for error in noodles.lint_gate_errors(candidate, trusted, paths)))

        trusted, candidate, paths = self.planted(self.CLEAN)
        with mock.patch.object(noodles, "run", side_effect=FileNotFoundError("ruff")):
            self.assertTrue(any("cannot execute the ruff pinned by" in error for error in noodles.lint_gate_errors(candidate, trusted, paths)))
        with mock.patch.object(noodles, "run", return_value=subprocess.CompletedProcess([], 2, "", "unknown option")):
            self.assertTrue(any("could not run ruff pinned by" in error for error in noodles.lint_gate_errors(candidate, trusted, paths)))
        with mock.patch.object(noodles, "run", return_value=subprocess.CompletedProcess([], 1, "", "required-version mismatch")):
            self.assertTrue(any("must not read as green" in error for error in noodles.lint_gate_errors(candidate, trusted, paths)))

    def test_the_landed_policy_selects_explicit_groups_rather_than_everything(self) -> None:
        """`ALL` grows on every ruff upgrade, which is the one selection shape the atom refuses."""
        policy = tomllib.loads((CANDIDATE_ROOT / noodles.LINT_POLICY_PATH).read_text(encoding="utf-8"))
        self.assertNotIn("ALL", policy["lint"]["select"])
        self.assertTrue(policy["required-version"].startswith("=="), policy["required-version"])


class TypeGateTests(unittest.TestCase):
    """ed3c/noodles#415 - the type coordinate, controlled in the three directions it can be wrong.

    The baseline is the whole mechanism, so it gets both legs: a diagnostic the trusted baseline
    freezes must NOT red, and one more of the same rule in the same file MUST. A fixture that only
    planted a fresh violation would pass against a gate with no baseline at all and would prove
    nothing about adoption.

    The trusted-policy leg repeats the syntax gate's control and for the same reason: showing that a
    violation reds is not enough, because a gate reading the candidate's own config would red on the
    same input. Only the SAME candidate tree judged from two policy roots and disagreeing separates
    the two readings, and the escape hatch has to be one that really works or the control controls
    nothing - the repair the syntax gate's `ignore = ["ALL"]` needed. `ignore: ["**"]` is asserted
    green from the candidate side in the same call that asserts red from the trusted side, so its
    working-ness is measured here rather than assumed.

    The leg that no amount of red/green on this fixture can supply is
    `test_the_trusted_policy_governs_the_run_rather_than_decorating_it`: a gate that read NO config at
    all would also pass every test in this class, because basedpyright's default mode is the one the
    policy asks for."""

    UNTYPED = "def widen(payload: object) -> int:\n    return payload.anything\n"
    CLEAN = "def probe() -> None:\n    print('nothing to refuse here')\n"
    ESCAPE_HATCH_POLICY = '{"include": ["."], "ignore": ["**"]}'
    REASON = "the provider payload is a JSON object this seam cannot narrow"

    def planted(self, source: str, *, candidate_policy: str | None = None, baseline: dict[str, dict[str, int]] | None = None) -> tuple[Path, Path, set[str]]:
        """A trusted root carrying THIS repository's real type policy, and a separate candidate root."""
        temp = tempfile.TemporaryDirectory(prefix="noodles-type-test-", ignore_cleanup_errors=True)
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        trusted, candidate = base / "trusted", base / "candidate"
        for root in (trusted, candidate):
            (root / "policy").mkdir(parents=True)
        landed = (CANDIDATE_ROOT / noodles.TYPE_POLICY_PATH).read_text(encoding="utf-8")
        (trusted / noodles.TYPE_POLICY_PATH).write_text(landed, encoding="utf-8")
        (candidate / noodles.TYPE_POLICY_PATH).write_text(candidate_policy or landed, encoding="utf-8")
        pin = json.loads((CANDIDATE_ROOT / noodles.TYPE_BASELINE_PATH).read_text(encoding="utf-8"))["tool"]
        frozen = {"tool": pin, "diagnostics": baseline or {}}
        (trusted / noodles.TYPE_BASELINE_PATH).write_text(json.dumps(frozen), encoding="utf-8")
        (candidate / noodles.TYPE_BASELINE_PATH).write_text(json.dumps(frozen), encoding="utf-8")
        (candidate / "probe.py").write_text(source, encoding="utf-8")
        return trusted, candidate, {noodles.TYPE_POLICY_PATH, noodles.TYPE_BASELINE_PATH, "probe.py"}

    def test_a_new_diagnostic_reds_and_the_inverse_edit_restores_green(self) -> None:
        trusted, candidate, paths = self.planted(self.UNTYPED)
        errors = noodles.type_gate_errors(candidate, trusted, paths)
        self.assertTrue(any(error.startswith("type probe.py:") for error in errors), errors)
        (candidate / "probe.py").write_text(self.CLEAN, encoding="utf-8")
        self.assertEqual(noodles.type_gate_errors(candidate, trusted, paths), [])

    def test_the_baseline_admits_its_own_frozen_count_and_refuses_one_more(self) -> None:
        """Burn-down safety and the ratchet are the same number read in two directions: the freeze is
        a ceiling, so measuring under it is green and measuring over it is the refusal."""
        trusted, candidate, paths = self.planted(self.UNTYPED)
        measured = noodles.type_gate_errors(candidate, trusted, paths)
        rules = {error.split(": ", 1)[1].split(" measures ")[0]: int(error.split(" measures ")[1].split(" ")[0]) for error in measured}
        self.assertTrue(rules, measured)
        trusted, candidate, paths = self.planted(self.UNTYPED, baseline={"probe.py": rules})
        self.assertEqual(noodles.type_gate_errors(candidate, trusted, paths), [])
        (candidate / "probe.py").write_text(self.UNTYPED + "\n\n" + self.UNTYPED.replace("widen", "widen_again"), encoding="utf-8")
        self.assertTrue(any("where the trusted baseline freezes" in error for error in noodles.type_gate_errors(candidate, trusted, paths)))
        (candidate / "probe.py").write_text(self.CLEAN, encoding="utf-8")
        self.assertEqual(noodles.type_gate_errors(candidate, trusted, paths), [], "a fixed diagnostic must stay green under a baseline that still names it")

    def test_the_candidate_cannot_switch_off_the_policy_that_judges_it(self) -> None:
        trusted, candidate, paths = self.planted(self.UNTYPED, candidate_policy=self.ESCAPE_HATCH_POLICY)
        judged_by_trusted = noodles.type_gate_errors(candidate, trusted, paths)
        judged_by_candidate = noodles.type_gate_errors(candidate, candidate, paths)
        self.assertTrue(any(error.startswith("type probe.py:") for error in judged_by_trusted), judged_by_trusted)
        self.assertEqual(judged_by_candidate, [])

    def test_a_bare_or_reasonless_type_suppression_is_refused_and_a_justified_one_passes(self) -> None:
        trusted, candidate, paths = self.planted(self.CLEAN)
        for suffix, expected in (
            ("  # type: ignore", "unscoped"),
            ("  # pyright: ignore", "unjustified"),
            ("  # pyright: ignore[reportAny]", "unjustified"),
            ("  # constraint: x # pyright: ignore[reportAny]", "unjustified"),
            (f"  # constraint: {self.REASON} # pyright: ignore[reportAny]", None),
        ):
            with self.subTest(suffix=suffix.strip()):
                (candidate / "probe.py").write_text(f"def probe() -> None:\n    print('nothing to refuse here'){suffix}\n", encoding="utf-8")
                errors = noodles.type_gate_errors(candidate, trusted, paths)
                if expected is None:
                    self.assertEqual([error for error in errors if "suppression" in error], [])
                else:
                    self.assertTrue(any(expected in error for error in errors), errors)

    def test_prose_that_merely_names_a_directive_is_not_read_as_one(self) -> None:
        """The scan reads COMMENT tokens, so a docstring quoting a directive is prose, not a
        suppression - the fail-open shape a raw line scan would have."""
        trusted, candidate, paths = self.planted('def probe() -> None:\n    """A docstring naming # type: ignore on purpose."""\n')
        self.assertEqual([error for error in noodles.type_gate_errors(candidate, trusted, paths) if "suppression" in error], [])

    def test_every_absence_around_the_tool_is_its_own_refusal(self) -> None:
        """Five ways this gate can fail to produce evidence, each named rather than passed: no trusted
        config or baseline, an unreadable one, a basedpyright that will not execute, one that is not
        the pinned version, and one that reports without a readable report."""
        trusted, candidate, paths = self.planted(self.CLEAN)
        (trusted / noodles.TYPE_BASELINE_PATH).unlink()
        self.assertTrue(any("trusted type policy missing" in error for error in noodles.type_gate_errors(candidate, trusted, paths)))

        trusted, candidate, paths = self.planted(self.CLEAN)
        (trusted / noodles.TYPE_BASELINE_PATH).write_text("{not json", encoding="utf-8")
        self.assertTrue(any("trusted type policy unreadable" in error for error in noodles.type_gate_errors(candidate, trusted, paths)))

        trusted, candidate, paths = self.planted(self.CLEAN)
        with mock.patch.object(noodles, "run", side_effect=FileNotFoundError("basedpyright")):
            self.assertTrue(any("cannot execute the basedpyright pinned by" in error for error in noodles.type_gate_errors(candidate, trusted, paths)))
        pin = json.loads((CANDIDATE_ROOT / noodles.TYPE_BASELINE_PATH).read_text(encoding="utf-8"))["tool"]["version"]
        # constraint: the second reported version is the prefix-extension control: a substring check
        # constraint: reads pin 1.39.1 as satisfied by an installed 1.39.10, which this tool's own
        # constraint: version series really does contain, so the pin has to compare whole lines.
        for reported in ("basedpyright 0.0.0\n", f"basedpyright {pin}0\n"):
            with self.subTest(reported=reported.strip()), mock.patch.object(noodles, "run", return_value=subprocess.CompletedProcess([], 0, reported, "")):
                self.assertTrue(any("an unpinned checker is a green whose meaning moves" in error for error in noodles.type_gate_errors(candidate, trusted, paths)))
        pinned = subprocess.CompletedProcess([], 0, f"basedpyright {pin}\n", "")
        with mock.patch.object(noodles, "run", side_effect=[pinned, subprocess.CompletedProcess([], 1, "", "node crashed")]):
            self.assertTrue(any("must not read as green" in error for error in noodles.type_gate_errors(candidate, trusted, paths)))

    def test_the_trusted_policy_governs_the_run_rather_than_decorating_it(self) -> None:
        """The control for the failure every other test here is blind to: basedpyright's DEFAULT mode
        is also `recommended`, so a gate that never read its config emits nearly the same diagnostics
        as one that did. Measured on 1.39.10: given a DIRECTORY, `--project` discovers
        `pyrightconfig.json` and silently ignores `basedpyrightconfig.json`, which is exactly how this
        gate ran until the argument named the file. One rule turned off in the trusted policy is the
        discriminator - if the diagnostic survives, the policy is decoration."""
        trusted, candidate, paths = self.planted(self.UNTYPED)
        rules = {error.split(": ", 1)[1].split(" measures ")[0] for error in noodles.type_gate_errors(candidate, trusted, paths)}
        self.assertIn("reportUnknownMemberType", rules)
        silenced = json.loads((CANDIDATE_ROOT / noodles.TYPE_POLICY_PATH).read_text(encoding="utf-8")) | {"reportUnknownMemberType": "none"}
        (trusted / noodles.TYPE_POLICY_PATH).write_text(json.dumps(silenced), encoding="utf-8")
        after = {error.split(": ", 1)[1].split(" measures ")[0] for error in noodles.type_gate_errors(candidate, trusted, paths)}
        self.assertNotIn("reportUnknownMemberType", after)
        self.assertTrue(after, "the policy must silence one rule, not the whole run")

    def test_the_landed_baseline_is_what_this_tree_actually_measures(self) -> None:
        """The one control that keeps the committed baseline honest: it is asserted against the live
        tree through the gate's own reader, so a hand-edited freeze or a drifted tool reds here rather
        than silently widening what a green means."""
        paths = {relative for _, relative in noodles.tracked_entries(CANDIDATE_ROOT)}
        self.assertEqual(noodles.type_gate_errors(CANDIDATE_ROOT, CANDIDATE_ROOT, paths), [])


if __name__ == "__main__":
    unittest.main()

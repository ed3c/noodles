from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from collections.abc import Callable
from pathlib import Path
from typing import Any

import runtime_contract
import skill_contract
import noodles
from tests.support import CANDIDATE_ROOT, ENGINE_ROOT, cmd, copy_tracked

TASK_PROFILES = skill_contract.task_profiles(ENGINE_ROOT)
SCHEDULE_MODEL = TASK_PROFILES["schedule"]["model"]
EXECUTE_MODEL = TASK_PROFILES["execute"]["model"]
SCHEDULE_SKILL = ".agents/skills/schedule/SKILL.md"
UNRELATED_SECTION = "## Prohibitions"


def sole(found: list[str], what: str) -> str:
    # constraint: ed3c/noodles#277 - planted negatives relocate the rule's EXACT shipped bytes, so
    # constraint: they are located through the same shapes the gate parses rather than restated here;
    # constraint: a restated sentence would be the phrase lock this atom retires, moved into a test.
    assert len(found) == 1, f"expected exactly one {what}, found {len(found)}"
    return found[0]


def schedule_fences(content: str) -> list[str]:
    return [match[0] for match in skill_contract._FENCE_RE.finditer(content)]


def schedule_pointer_line(content: str) -> str:
    pointer = f"`{skill_contract.SCHEDULE_TASK_MODEL_POINTER}`"
    return sole([line for line in content.splitlines() if pointer in line], "task-model pointer line")


def schedule_diagnostic_bullet(content: str) -> str:
    matched = [line for line in content.splitlines() if skill_contract._DIAGNOSTIC_BULLET_RE.match(line.strip())]
    return sole(matched, "diagnostic routing bullet")


def schedule_summary_fence(content: str) -> str:
    argv = list(skill_contract.SCHEDULE_SUMMARY_ENTRYPOINT)
    carrying = [fence for fence in schedule_fences(content) if any(line.split() == argv for line in fence.splitlines())]
    return sole(carrying, "summary entrypoint fence")


def schedule_summary_template(content: str) -> str:
    keys = [line.partition(":")[0] for line in skill_contract.cycle_summary_lines(skill_contract._SUMMARY_PROBE_RECEIPT)]
    head = keys[:-1]
    shaped = [
        fence
        for fence in schedule_fences(content)
        if [line.partition(":")[0] for line in fence.splitlines()[1 : 1 + len(head)]] == head
    ]
    return sole(shaped, "summary template fence")


def move_to_unrelated_section(content: str, chunk: str) -> str:
    assert chunk in content and UNRELATED_SECTION in content
    return content.replace(chunk, "", 1).replace(UNRELATED_SECTION, f"{UNRELATED_SECTION}\n\n{chunk}\n", 1)


class ScheduleContractTests(unittest.TestCase):
    def mutated_copy(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temp = tempfile.TemporaryDirectory(prefix="noodles-schedule-policy-")
        root = Path(temp.name) / "repo"
        copy_tracked(CANDIDATE_ROOT, root)
        return temp, root

    _carrier_root: Path | None = None

    @classmethod
    def carrier_root(cls) -> Path:
        # constraint: ed3c/noodles#313 - .agents/bin/codex resolves its repository root from its own
        # constraint: __file__, never from cwd, so invoking the TRACKED wrapper mkdirs
        # constraint: .noodle/codex-isolation/{home,codex-home} into the live checkout no matter what
        # constraint: cwd it is given. One copied tree per class puts that runtime state in a
        # constraint: temporary directory, which is where the zero-residue clause requires it.
        if cls._carrier_root is None:
            temp = tempfile.TemporaryDirectory(prefix="noodles-codex-carrier-root-")
            cls.addClassCleanup(temp.cleanup)
            root = Path(temp.name) / "repo"
            copy_tracked(CANDIDATE_ROOT, root)
            cls._carrier_root = root
        return cls._carrier_root

    def run_carrier(self, argv: list[str], root: Path | None = None) -> subprocess.CompletedProcess[str]:
        root = self.carrier_root() if root is None else root
        with tempfile.TemporaryDirectory(prefix="noodles-codex-carrier-") as temp_name:
            fake_codex = Path(temp_name) / "codex"
            fake_codex.write_text(
                f"#!{sys.executable}\n"
                "import json\n"
                "import sys\n"
                "print(json.dumps(sys.argv[1:]))\n",
                encoding="utf-8",
            )
            fake_codex.chmod(0o755)
            env = dict(os.environ)
            env["PATH"] = temp_name + os.pathsep + env.get("PATH", "")
            return subprocess.run(
                [str(root / ".agents/bin/codex"), *argv],
                cwd=root,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

    def local_publish(self, payload: dict[str, object], current: dict[str, object] | None = None) -> dict[str, object]:
        with tempfile.TemporaryDirectory(prefix="noodles-local-publish-") as temp_name:
            root = Path(temp_name)
            runtime = root / ".noodle"
            runtime.mkdir()
            policy_dir = root / "policy"
            policy_dir.mkdir()
            (policy_dir / "fitness.json").write_text(
                (CANDIDATE_ROOT / "policy/fitness.json").read_text(),
                encoding="utf-8",
            )
            if current is not None:
                (runtime / "orders.json").write_text(json.dumps(current), encoding="utf-8")
            candidate_path = runtime / "orders-next.candidate.json"
            candidate_path.write_text(json.dumps(payload), encoding="utf-8")
            try:
                destination = skill_contract.publish_schedule_output(root, candidate_path)
            except ValueError as exc:
                return {
                    "accepted": False,
                    "error": str(exc),
                    "candidate_exists": candidate_path.exists(),
                    "published_exists": (runtime / "orders-next.json").exists(),
                }
            return {
                "accepted": True,
                "destination": str(destination),
                "candidate_exists": candidate_path.exists(),
                "published_exists": (runtime / "orders-next.json").exists(),
            }

    def runtime_promote(
        self, payload: dict[str, object], current: dict[str, object] | None = None
    ) -> dict[str, object]:
        binary = runtime_contract.resolve_locked_runtime_binary(CANDIDATE_ROOT, error_cls=AssertionError)
        with tempfile.TemporaryDirectory(prefix="noodles-runtime-promote-") as temp_name:
            root = Path(temp_name)
            init = subprocess.run(
                [str(binary), "--project-dir", str(root), "start", "--once"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(init.returncode, 0, init.stderr or init.stdout)
            runtime = root / ".noodle"
            execute_skill = root / ".agents/skills/execute"
            execute_skill.mkdir(parents=True)
            shutil.copy2(CANDIDATE_ROOT / ".agents/skills/execute/SKILL.md", execute_skill / "SKILL.md")
            if current is not None:
                # constraint: plant a pre-existing active orders.json in the runtime's promoted shape
                # constraint: so the direct-write re-emission control observes real promotion overwrite.
                (runtime / "orders.json").write_text(json.dumps(current), encoding="utf-8")
            (runtime / "orders-next.json").write_text(json.dumps(payload), encoding="utf-8")
            result = subprocess.run(
                [str(binary), "--project-dir", str(root), "start", "--once"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            bad_path = runtime / "orders-next.json.bad"
            orders_path = runtime / "orders.json"
            orders = json.loads(orders_path.read_text()) if orders_path.exists() else None
            return {
                "accepted": not bad_path.exists(),
                "output": (result.stdout or "") + (result.stderr or ""),
                "bad_exists": bad_path.exists(),
                "orders_exists": orders_path.exists(),
                "orders": orders,
            }

    def test_schedule_output_accepts_runtime_compatible_action_needed_array(self) -> None:
        proposed = {"orders": [], "action_needed": ["needs-human", ""]}
        self.assertEqual(skill_contract.validate_schedule_output({"orders": []}, proposed, TASK_PROFILES), [])

    def drifted_copy(self, mutate) -> Path:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        path = root / "policy/fitness.json"
        policy = json.loads(path.read_text())
        mutate(policy)
        path.write_text(json.dumps(policy))
        cmd(["git", "add", "policy/fitness.json"], root)
        cmd(["git", "commit", "-q", "-m", "planted task profile drift"], root)
        return root

    def test_codex_task_model_map_is_exact_and_drift_is_rejected(self) -> None:
        def plant(policy: dict) -> None:
            policy["required_codex_task_profiles"]["execute"]["model"] = "gpt-5.6-pro"

        root = self.drifted_copy(plant)
        result = noodles.verify_repository(root, root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("required_codex_task_profiles must be exactly" in item for item in result["errors"]))
        carrier = self.run_carrier(["exec", "--model", EXECUTE_MODEL], root=root)
        self.assertEqual(carrier.returncode, 2, carrier.stdout)
        self.assertIn("is not an exact admitted task model", carrier.stderr)

    def test_carrier_fails_closed_when_the_single_task_profile_source_is_unusable(self) -> None:
        for label, plant in (
            ("missing", lambda policy: policy.pop("required_codex_task_profiles")),
            ("wrong shape", lambda policy: policy.__setitem__("required_codex_task_profiles", {"execute": {"model": ""}})),
        ):
            with self.subTest(case=label):
                root = self.drifted_copy(plant)
                carrier = self.run_carrier(["exec", "--model", EXECUTE_MODEL], root=root)
                self.assertEqual(carrier.returncode, 2, carrier.stdout)
                self.assertIn("exact non-empty schedule/execute task profiles", carrier.stderr)
                self.assertEqual(carrier.stdout, "")

    def test_codex_carrier_injects_exact_effort_for_each_task_model(self) -> None:
        for task, profile in TASK_PROFILES.items():
            with self.subTest(task=task):
                result = self.run_carrier([
                    "exec",
                    "--model",
                    profile["model"],
                    "-c",
                    'approval_policy="never"',
                ])
                self.assertEqual(result.returncode, 0, result.stderr)
                argv = json.loads(result.stdout)
                self.assertEqual(
                    argv[:3],
                    ["exec", "-c", f'model_reasoning_effort="{profile["reasoning_effort"]}"'],
                )
                self.assertEqual(
                    argv[3:],
                    ["--model", profile["model"], "-c", 'approval_policy="never"'],
                )

    def test_codex_carrier_stops_option_parsing_at_delimiter(self) -> None:
        argv = ["exec", "--model", EXECUTE_MODEL, "--", "-mgpt-5.6-pro", '-cmodel_reasoning_effort="max"']
        result = self.run_carrier(argv)
        self.assertEqual(result.returncode, 0, result.stderr)
        effort = TASK_PROFILES["execute"]["reasoning_effort"]
        self.assertEqual(json.loads(result.stdout), ["exec", "-c", f'model_reasoning_effort="{effort}"', *argv[1:]])

    def test_codex_carrier_rejects_unadmitted_or_ambiguous_model_before_spawn(self) -> None:
        cases = (
            ("missing", ["exec"]),
            ("empty", ["exec", "--model="]),
            ("duplicate", ["exec", "--model", EXECUTE_MODEL, f"--model={SCHEDULE_MODEL}"]),
            ("mixed duplicate", ["exec", "--model", EXECUTE_MODEL, "-m", "gpt-5.6-pro"]),
            ("compact placeholder", ["exec", "-mgpt-5.6-pro"]),
            ("moving alias", ["exec", "--model", "gpt-5.6"]),
            ("placeholder", ["exec", "--model", "gpt-5.6-pro"]),
            ("retired", ["exec", "--model", "gpt-5.4"]),
            ("unknown", ["exec", "--model", "claude-opus-4-1"]),
        )
        for label, argv in cases:
            with self.subTest(case=label):
                result = self.run_carrier(argv)
                self.assertEqual(result.returncode, 2)
                self.assertIn("codex task carrier rejected launch", result.stderr)
                self.assertEqual(result.stdout, "")

    def test_codex_carrier_rejects_reasoning_override_before_spawn(self) -> None:
        for override in (
            ["-c", 'model_reasoning_effort="max"'],
            ['-c=model_reasoning_effort="max"'],
            ['-cmodel_reasoning_effort="max"'],
            ['--config=model_reasoning_effort="max"'],
        ):
            with self.subTest(override=override):
                result = self.run_carrier(["exec", "--model", EXECUTE_MODEL, *override])
                self.assertEqual(result.returncode, 2)
                self.assertIn("must come only from the task profile", result.stderr)
                self.assertEqual(result.stdout, "")

    def schedule_skill_verify(self, mutate: Callable[[str], str]) -> dict[str, Any]:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        path = root / SCHEDULE_SKILL
        content = path.read_text()
        mutated = mutate(content)
        self.assertNotEqual(mutated, content)
        path.write_text(mutated)
        return noodles.verify_repository(root, CANDIDATE_ROOT)

    def test_reworded_but_structurally_intact_schedule_skill_passes(self) -> None:
        """ed3c/noodles#277 positive control: every one of the four retired sentence locks is reworded
        and the Skill still verifies, because each remaining contract is decided by structure the
        document owns - the resolvable policy pointer inside the order-construction section, the
        fenced summary argv, the fenced template whose keys `cycle_summary_lines` emits, and the
        parsed signal/action/why bullet - never by the sentence that carries it."""
        def reword(content: str) -> str:
            content = content.replace(
                schedule_pointer_line(content),
                "Set the model of the order's single `execute` stage from "
                "`required_codex_task_profiles.execute.model`; no other source is admitted.",
                1,
            )
            content = content.replace(
                schedule_summary_template(content),
                "```text\n"
                "frontier: <the receipt's frontier, compact JSON>\n"
                "winners: <the receipt's winners, compact JSON>\n"
                "max_useful_workers: <the receipt's max_useful_workers>\n"
                "<subject>: <status> - <that status's meaning, copied from the receipt>\n"
                "```",
                1,
            )
            return content.replace(
                schedule_diagnostic_bullet(content),
                "- signal: repeated empty proposals while ready schedulable issues remain; "
                "action: copy the receipt, then walk the diagnostic in order (claim branches vs issue "
                "states -> claimed components vs ready pool -> receipt status definitions) and publish "
                "it as data; why: a re-derived story once cost hours.",
                1,
            )

        result = self.schedule_skill_verify(reword)
        self.assertTrue(result["ok"], result["errors"])

    def test_relocated_schedule_contracts_fail_with_distinct_diagnostics(self) -> None:
        """ed3c/noodles#277 planted negatives for the four retired sentence locks. Each rule's exact
        bytes are relocated four ways - into an HTML comment, across the fence/prose boundary that
        decides whether it is instruction or example, into an unrelated section, and duplicated - and
        each relocation must red with the diagnostic that names the rule it broke. `SCHEDULE_SUMMARY`
        crosses that boundary the other way (out of its fence into prose) because its carrier is a
        fenced argv, and its unrelated-section move reds through the co-location it owns: the section
        that carries the summary gate is the section the template and the diagnostic bullet live in."""
        rules = {
            "task-model routing": (schedule_pointer_line, "line"),
            "receipt-verbatim summary": (schedule_summary_template, "fence"),
            "deterministic summary gate": (schedule_summary_fence, "fence"),
            "starvation diagnostic routing": (schedule_diagnostic_bullet, "line"),
        }
        expected_unrelated = {
            "task-model routing": "not owned by the single section that constructs the order",
            "receipt-verbatim summary": "missing receipt-verbatim summary contract",
            # ponytail: the fence relocation doesn't red on its own name - moving it changes
            # ponytail: summary_owner, which orphans the template that already lived in the old
            # ponytail: section, so the diagnostic an operator sees names the template, not the fence.
            "deterministic summary gate": "missing receipt-verbatim summary contract",
            "starvation diagnostic routing": "missing starvation diagnostic routing contract",
        }
        for label, (locate, carrier) in rules.items():
            relocations = {
                "html comment": lambda chunk: f"<!--\n{chunk}\n-->",
                "fence boundary": (
                    (lambda chunk: "\n".join(chunk.splitlines()[1:-1]))
                    if carrier == "fence"
                    else (lambda chunk: f"```text\n{chunk}\n```")
                ),
                "duplicated": lambda chunk: f"{chunk}\n\n{chunk}",
            }
            for case, rewrite in relocations.items():
                with self.subTest(rule=label, case=case):
                    result = self.schedule_skill_verify(
                        lambda content: content.replace(locate(content), rewrite(locate(content)), 1)
                    )
                    self.assertFalse(result["ok"], case)
                    self.assertTrue(any(label in item for item in result["errors"]), result["errors"])
            with self.subTest(rule=label, case="unrelated section"):
                result = self.schedule_skill_verify(
                    lambda content: move_to_unrelated_section(content, locate(content))
                )
                self.assertFalse(result["ok"])
                self.assertTrue(
                    any(expected_unrelated[label] in item for item in result["errors"]), result["errors"]
                )

    def test_relocating_a_rule_together_with_its_anchor_is_the_documented_residual_limit(self) -> None:
        """ed3c/noodles#277 residual limit, named not hidden: every co-location check above proves
        mutual co-location between a rule's bytes and the anchor it is checked against, not a fixed
        section identity. Moving the rule sentence ALONE into `## Prohibitions` reds (proven above);
        moving the rule together with the anchor it is checked against - `order_id` for task-model
        routing, the summary entrypoint fence for the template and diagnostic bullet - carries the
        anchor along and still verifies. This is the exact boundary
        `schedule_task_model_routing_errors` and `schedule_starvation_routing_errors` name in their
        own Non-claim: defeating it this way relocates the real contract, not just its wording."""
        def move_together(content: str, *chunks: str) -> str:
            payload = "\n\n".join(chunks)
            for chunk in chunks:
                content = content.replace(chunk, "", 1)
            return content.replace(UNRELATED_SECTION, f"{UNRELATED_SECTION}\n\n{payload}\n", 1)

        def order_id_line(content: str) -> str:
            return sole([line for line in content.splitlines() if "`order_id`" in line], "order_id line")

        result = self.schedule_skill_verify(
            lambda c: move_together(c, order_id_line(c), schedule_pointer_line(c))
        )
        self.assertTrue(result["ok"], result["errors"])

        result = self.schedule_skill_verify(
            lambda c: move_together(
                c, schedule_summary_fence(c), schedule_summary_template(c), schedule_diagnostic_bullet(c)
            )
        )
        self.assertTrue(result["ok"], result["errors"])

    def test_summary_probe_fixture_going_stale_reds_instead_of_crashing_verify(self) -> None:
        """ed3c/noodles#277 - `schedule_summary_template_errors` computes its required keys by calling
        `cycle_summary_lines(_SUMMARY_PROBE_RECEIPT)`, so if the emitter starts reading a receipt key
        the fixture does not carry, that call raises `KeyError`. This proves the caught path: a
        stale fixture reds `validate_backlog_scheduler` with a diagnostic naming the missing key,
        it does not propagate an uncaught exception out of `./noodles verify`."""
        section = "\n".join(skill_contract._sections(skill_contract._quotable(
            (CANDIDATE_ROOT / SCHEDULE_SKILL).read_text()
        )))
        stale_receipt = {"frontier": []}
        with self.assertRaises(KeyError):
            skill_contract.cycle_summary_lines(stale_receipt)
        with unittest.mock.patch.object(skill_contract, "_SUMMARY_PROBE_RECEIPT", stale_receipt):
            errors = skill_contract.schedule_summary_template_errors("schedule", section)
        self.assertTrue(errors)
        self.assertTrue(any("summary probe fixture is stale" in item and "winners" in item for item in errors), errors)

    def test_schedule_contracts_reject_kept_words_with_dropped_structure(self) -> None:
        """ed3c/noodles#277 - the two shape halves relocation does not exercise. The summary template
        is compared against what `cycle_summary_lines` really emits, so a key the emitter never emits
        and a per-subject line that drops the `<status> - <meaning>` separator both red; the
        diagnostic bullet must chain an ordered walk, so an action with no `->` steps reds."""
        def retemplate(content: str, old: str, new: str) -> str:
            template = schedule_summary_template(content)
            return content.replace(template, template.replace(old, new, 1), 1)

        cases = (
            ("emitter key renamed", lambda c: retemplate(c, "winners:", "winner_list:"), "missing receipt-verbatim summary contract"),
            ("status separator dropped", lambda c: retemplate(c, "<status> - ", "<status> "), "drops the per-subject"),
            (
                "diagnostic order dropped",
                lambda c: c.replace(schedule_diagnostic_bullet(c), schedule_diagnostic_bullet(c).replace("->", "then"), 1),
                "names no ordered diagnostic",
            ),
        )
        for case, mutate, expected in cases:
            with self.subTest(case=case):
                result = self.schedule_skill_verify(mutate)
                self.assertFalse(result["ok"])
                self.assertTrue(any(expected in item for item in result["errors"]), result["errors"])

    def test_orphan_policy_key_is_rejected_by_its_own_name(self) -> None:
        """ed3c/noodles#277 planted negative for `validate_policy_key_consumption`: the gate that
        would have caught the six orphan workflow phrase lists ed3c/noodles#84 removed. The probe key
        is assembled at runtime because this test file is itself tracked `.py` source - a literal here
        would be its own consumer and the gate would never see an orphan."""
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        orphan = "orphan_" + "fitness" + "_key_probe"
        path = root / "policy/fitness.json"
        policy = json.loads(path.read_text())
        self.assertNotIn(orphan, policy)
        policy[orphan] = ["read by nobody"]
        path.write_text(json.dumps(policy, indent=2) + "\n")
        result = noodles.verify_repository(root, CANDIDATE_ROOT)
        self.assertFalse(result["ok"])
        self.assertTrue(
            any(orphan in item and "zero tracked .py sources" in item for item in result["errors"]),
            result["errors"],
        )

    def test_orphan_named_only_in_a_retirement_comment_is_the_documented_residual_limit(self) -> None:
        """ed3c/noodles#277 residual limit, named not hidden: `validate_policy_key_consumption` is
        literal-name matching (its own Non-claim says so), so a key this repo's own `# constraint:`
        retirement-comment convention names - to say the key is dead - still counts as consumed. This
        reproduces the exact shape ed3c/noodles#84's own history left behind: `required_agent_phrases`
        stayed "consumed" by a docstring describing its removal for as long as that docstring existed,
        right up until the key itself was deleted from policy/fitness.json."""
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        orphan = "orphan_" + "retirement_comment_probe"
        path = root / "policy/fitness.json"
        policy = json.loads(path.read_text())
        self.assertNotIn(orphan, policy)
        policy[orphan] = ["read by nobody"]
        path.write_text(json.dumps(policy, indent=2) + "\n")
        skill_path = root / "skill_contract.py"
        skill_path.write_text(
            f"# constraint: {orphan} is retired, no reader consumes it.\n" + skill_path.read_text()
        )
        result = noodles.verify_repository(root, CANDIDATE_ROOT)
        self.assertTrue(result["ok"], result["errors"])

    def test_retired_phrase_locks_leave_no_source_residue(self) -> None:
        """ed3c/noodles#277 readback: the retired policy key and the five retired phrase constants
        appear nowhere outside `# constraint:` comments, which is what makes the deletion a deletion
        rather than a rename."""
        self.assertNotIn("required_agent_phrases", json.loads((CANDIDATE_ROOT / "policy/fitness.json").read_text()))
        source = "\n".join(
            line
            for line in (CANDIDATE_ROOT / "skill_contract.py").read_text().splitlines()
            if not line.strip().startswith("#")
        )
        for retired in (
            "SCHEDULE_OWNERSHIP_PHRASE",
            "SCHEDULE_TASK_MODEL_PHRASE",
            "SCHEDULE_RECEIPT_VERBATIM_PHRASE",
            "SCHEDULE_SUMMARY_COMMAND",
            "SCHEDULE_STARVATION_DIAGNOSTIC_PHRASE",
            "required_agent_phrases",
        ):
            with self.subTest(retired=retired):
                self.assertNotIn(retired, source)

    def test_schedule_output_rejects_unknown_top_level_field(self) -> None:
        proposed = {"orders": [], "rationale": "top-level drift"}
        self.assertEqual(
            skill_contract.validate_schedule_output({"orders": []}, proposed, TASK_PROFILES),
            ["scheduler output has unknown field 'rationale'; allowed fields: action_needed, orders"],
        )

    def test_schedule_output_rejects_non_array_action_needed(self) -> None:
        proposed = {"orders": [], "action_needed": "ed3c/noodles#43"}
        self.assertEqual(
            skill_contract.validate_schedule_output({"orders": []}, proposed, TASK_PROFILES),
            ["scheduler output action_needed must be an array of strings"],
        )

    def test_schedule_output_rejects_unknown_order_field(self) -> None:
        proposed = {
            "orders": [{
                "id": "ed3c/noodles#43",
                "stages": [{"do": "execute", "model": EXECUTE_MODEL, "prompt": "next"}],
                "bogus": 1,
            }]
        }
        self.assertEqual(
            skill_contract.validate_schedule_output({"orders": []}, proposed, TASK_PROFILES),
            ["scheduler output order[0] has unknown field 'bogus'; allowed fields: id, plan, rationale, stages, title"],
        )

    def test_schedule_output_rejects_unknown_stage_field(self) -> None:
        proposed = {
            "orders": [{
                "id": "ed3c/noodles#43",
                "stages": [{"do": "execute", "model": EXECUTE_MODEL, "prompt": "next", "bogus": 1}],
            }]
        }
        self.assertEqual(
            skill_contract.validate_schedule_output({"orders": []}, proposed, TASK_PROFILES),
            [
                "scheduler output order 'ed3c/noodles#43' stage[0] has unknown field 'bogus'; "
                "allowed fields: do, extra, extra_prompt, group, model, prompt, runtime, with"
            ],
        )

    def test_planted_negative_execute_models_fail_before_publish_and_preserve_candidate(self) -> None:
        cases = (
            ("missing", None, f"requires explicit model '{EXECUTE_MODEL}' for execute"),
            ("unsupported alias", "gpt-5.6", "found 'gpt-5.6'"),
            ("rejected placeholder", "gpt-5.6-pro", "found 'gpt-5.6-pro'"),
            ("unrelated model", "claude-opus-4-1", "found 'claude-opus-4-1'"),
            ("schedule/execute mismatch", SCHEDULE_MODEL, f"found '{SCHEDULE_MODEL}'"),
        )
        for label, model, fragment in cases:
            with self.subTest(case=label):
                stage = {"do": "execute", "prompt": "next"}
                if model is not None:
                    stage["model"] = model
                result = self.local_publish({
                    "orders": [{"id": "ed3c/noodles#70", "stages": [stage]}]
                })
                self.assertFalse(result["accepted"])
                self.assertIn(fragment, str(result["error"]))
                self.assertTrue(result["candidate_exists"])
                self.assertFalse(result["published_exists"])

    @unittest.skipIf(
        os.getenv("NOODLES_OFFLINE_TESTS") == "1" or os.getenv("GITHUB_ACTIONS") == "true",
        "pinned Noodle runtime is intentionally unavailable in hosted/offline CI; live control runs before handoff",
    )
    def test_schedule_publish_matches_runtime_promotion_path_for_compact_payloads(self) -> None:
        cases = (
            (
                "positive compact order",
                {"orders": [{"id": "ed3c/noodles#44", "stages": [{"do": "execute", "model": EXECUTE_MODEL, "prompt": "next"}]}]},
                True,
                None,
            ),
            (
                "runtime-compatible action_needed",
                {"orders": [], "action_needed": ["needs-human"]},
                True,
                None,
            ),
            (
                "top-level rationale",
                {"orders": [], "rationale": "drift"},
                False,
                "rationale",
            ),
            (
                "misspelled top-level field",
                {"orders": [], "actionNeed": "needs-human"},
                False,
                "actionNeed",
            ),
            (
                "wrong action_needed type",
                {"orders": [], "action_needed": "ed3c/noodles#43"},
                False,
                "action_needed",
            ),
            (
                "unknown order field",
                {"orders": [{"id": "ed3c/noodles#44", "stages": [{"do": "execute", "model": EXECUTE_MODEL, "prompt": "next"}], "bogus": 1}]},
                False,
                "bogus",
            ),
            (
                "unknown stage field",
                {"orders": [{"id": "ed3c/noodles#44", "stages": [{"do": "execute", "model": EXECUTE_MODEL, "prompt": "next", "bogus": 1}]}]},
                False,
                "bogus",
            ),
        )
        for label, payload, accepted, fragment in cases:
            with self.subTest(case=label):
                local = self.local_publish(payload)
                runtime = self.runtime_promote(payload)
                self.assertEqual(local["accepted"], accepted)
                self.assertEqual(runtime["accepted"], accepted)
                self.assertEqual(local["accepted"], runtime["accepted"])
                if accepted:
                    self.assertFalse(local["candidate_exists"])
                    self.assertTrue(local["published_exists"])
                    self.assertFalse(runtime["bad_exists"])
                    self.assertTrue(runtime["orders_exists"])
                    if payload["orders"]:
                        promoted = next(
                            order for order in runtime["orders"]["orders"]
                            if order["id"] == payload["orders"][0]["id"]
                        )
                        self.assertEqual(promoted["stages"][0]["model"], TASK_PROFILES["execute"]["model"])
                else:
                    self.assertTrue(local["candidate_exists"])
                    self.assertFalse(local["published_exists"])
                    self.assertTrue(runtime["bad_exists"])
                    self.assertIn(fragment, str(local["error"]))
                    self.assertIn(fragment, str(runtime["output"]))

    @unittest.skipIf(
        os.getenv("NOODLES_OFFLINE_TESTS") == "1" or os.getenv("GITHUB_ACTIONS") == "true",
        "pinned Noodle runtime is intentionally unavailable in hosted/offline CI; live control runs before handoff",
    )
    def test_pinned_runtime_promotion_seam_covers_schema_not_semantic_authority(self) -> None:
        # constraint: ed3c/noodles#65 - physically admit the smallest upstream-owned promotion seam.
        # constraint: a direct write to orders-next.json bypasses `skill_contract.py publish`; the pinned
        # constraint: runtime's build.promote_orders_next only re-validates the compact-orders SCHEMA, so
        # constraint: the semantic-authority rules the local gate owns are NOT upstream-enforced.
        def order(oid: str) -> dict[str, object]:
            return {"orders": [{"id": oid, "stages": [{"do": "execute", "model": EXECUTE_MODEL, "prompt": "next"}]}]}

        # constraint: positive control - the seam exists and promotes a schema-valid direct write.
        self.assertTrue(self.runtime_promote(order("ed3c/noodles#44"))["accepted"])

        # constraint: positive control - the seam fails closed on schema drift only (quarantine to .bad).
        drift = self.runtime_promote({**order("ed3c/noodles#44"), "bogus": 1})
        self.assertFalse(drift["accepted"])
        self.assertTrue(drift["bad_exists"])
        self.assertIn("unknown field", str(drift["output"]))

        # constraint: planted-negative controls - the semantic-authority subjects that the local publish
        # constraint: gate rejects promote THROUGH a direct write; the upstream seam owns no semantic authority.
        active_current = {
            "orders": [{
                "id": "ed3c/noodles#70",
                "status": "active",
                "stages": [{
                    "task_key": "execute", "skill": "execute", "provider": "claude",
                    "model": EXECUTE_MODEL, "prompt": "active", "status": "active",
                }],
            }]
        }
        negatives = (
            ("self_schedule", order("schedule"), None, "schedule", True),
            ("foreign_repo", order("someone-else/other#5"), None, "someone-else/other#5", False),
            ("duplicate_subject", {"orders": order("ed3c/noodles#44")["orders"] * 2}, None, "ed3c/noodles#44", False),
            ("active_reemission", order("ed3c/noodles#70"), active_current, "ed3c/noodles#70", True),
        )
        for label, payload, current, promoted_id, local_rejects in negatives:
            with self.subTest(case=label):
                result = self.runtime_promote(payload, current=current)
                self.assertTrue(result["accepted"], f"{label}: upstream unexpectedly quarantined a bypass")
                self.assertFalse(result["bad_exists"])
                orders = (result["orders"] or {}).get("orders", [])
                ids = [str(o.get("id")) for o in orders]
                self.assertIn(promoted_id, ids)
                # constraint: id membership alone does not discriminate a real bypass promotion from
                # constraint: an id that would show up in orders.json anyway -- #70 already exists in
                # constraint: the planted current file before promotion runs, and Noodle auto-injects
                # constraint: its own "schedule" bookkeeping order whenever no order already claims that
                # constraint: id, so both would satisfy assertIn even if the upstream had refused the
                # constraint: bypass. Assert the promoted stage actually carries THIS payload's own
                # constraint: content (execute/EXECUTE_MODEL/"next"), not the pre-existing or
                # constraint: Noodle-owned stage shape, so a refused bypass turns this control red.
                match = next((order for order in orders if str(order.get("id")) == promoted_id), None)
                self.assertIsNotNone(match, f"{label}: promoted order for {promoted_id!r} not found")
                stage = match["stages"][0]
                self.assertEqual(stage.get("task_key"), "execute", f"{label}: {stage}")
                self.assertEqual(stage.get("model"), EXECUTE_MODEL, f"{label}: {stage}")
                self.assertEqual(stage.get("prompt"), "next", f"{label}: {stage}")
                if local_rejects:
                    # constraint: the offline candidate gate (publish_schedule_output) refuses the same subject.
                    local = self.local_publish(payload, current=current)
                    self.assertFalse(local["accepted"], f"{label}: local gate unexpectedly accepted a bypass")


class ConcurrencyProofLockTests(unittest.TestCase):
    """ed3c/noodles#100 - declared concurrency is admitted by evidence, never by the number.

    The invariant this gate exists to enforce is: a repository that declares `max_concurrency > 1`
    carries a lock naming, per N-independent invariant, the landed subject, its provider receipt, and
    the planted-negative controls that keep the invariant alive in the tracked suite. It deliberately
    does not bound the number: bounding it would be the numeric stop-loss the Chef decision refused."""

    PROOF = skill_contract.CONCURRENCY_PROOF_PATH

    def mutated_copy(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temp = tempfile.TemporaryDirectory(prefix="noodles-concurrency-proof-")
        root = Path(temp.name) / "repo"
        copy_tracked(CANDIDATE_ROOT, root)
        return temp, root

    def commit(self, root: Path) -> None:
        cmd(["git", "add", "-A"], root)
        cmd(["git", "commit", "-q", "-m", "planted"], root)

    def set_concurrency(self, root: Path, value: int) -> None:
        path = root / ".noodle.toml"
        text = path.read_text(encoding="utf-8")
        replaced = text.replace("max_concurrency = 4", f"max_concurrency = {value}", 1)
        self.assertNotEqual(replaced, text, "fixture drift: .noodle.toml no longer declares max_concurrency = 4")
        path.write_text(replaced, encoding="utf-8")

    def proof_errors(self, root: Path) -> list[str]:
        return [item for item in noodles.verify_repository(root, CANDIDATE_ROOT)["errors"] if self.PROOF in item]

    def declared_concurrency(self, root: Path) -> int:
        import tomllib

        return int(tomllib.loads((root / ".noodle.toml").read_text(encoding="utf-8"))["concurrency"]["max_concurrency"])

    def test_shipped_lock_admits_the_declared_concurrency_and_names_only_real_controls(self) -> None:
        # constraint: the positive is only meaningful while the repository actually declares more than
        # constraint: one lane; at max_concurrency = 1 the gate returns early and proves nothing.
        self.assertGreater(self.declared_concurrency(CANDIDATE_ROOT), 1)
        config = json.loads(json.dumps({"concurrency": {"max_concurrency": self.declared_concurrency(CANDIDATE_ROOT)}}))
        self.assertEqual(skill_contract.validate_concurrency_proof(CANDIDATE_ROOT, config), [])
        lock = json.loads((CANDIDATE_ROOT / self.PROOF).read_text(encoding="utf-8"))
        residuals = " ".join(lock["known_residuals"])
        self.assertIn("primary checkout", residuals)
        self.assertIn("outside the admitted entrypoints", residuals)
        named = [item for entry in lock["invariants"] for item in entry["planted_negatives"]]
        self.assertTrue(named)
        for identifier in named:
            self.assertTrue(skill_contract.tracked_test_exists(CANDIDATE_ROOT, identifier), identifier)

    def test_a_control_inherited_from_a_same_file_fixture_base_still_resolves(self) -> None:
        # constraint: ed3c/noodles#100 - this repo already shares fixtures by inheritance
        # constraint: (tests/test_supervised_ceremony.py's ControlCheckoutFixture); resolution must
        # constraint: not read a control as absent just because it lives on a base class rather than
        # constraint: being redeclared on the named subclass.
        temp, root = self.mutated_copy()
        with temp:
            fixture = root / "tests" / "test_inherited_control_fixture.py"
            fixture.write_text(
                "import unittest\n\n"
                "class BaseFixture(unittest.TestCase):\n"
                "    def test_defined_only_on_the_base(self) -> None:\n"
                "        pass\n\n"
                "class SubclassTests(BaseFixture):\n"
                "    pass\n",
                encoding="utf-8",
            )
            self.assertTrue(
                skill_contract.tracked_test_exists(
                    root, "tests.test_inherited_control_fixture.SubclassTests.test_defined_only_on_the_base"
                )
            )
            self.assertFalse(
                skill_contract.tracked_test_exists(
                    root, "tests.test_inherited_control_fixture.SubclassTests.test_never_declared_anywhere"
                )
            )

    def test_planted_negative_missing_lock_with_declared_concurrency_fails_verify(self) -> None:
        temp, root = self.mutated_copy()
        with temp:
            cmd(["git", "rm", "-q", self.PROOF], root)
            self.commit(root)
            errors = self.proof_errors(root)
            self.assertTrue(any("is absent" in item for item in errors), errors)

    def test_planted_negative_lock_naming_a_nonexistent_control_fails_verify(self) -> None:
        temp, root = self.mutated_copy()
        with temp:
            path = root / self.PROOF
            lock = json.loads(path.read_text(encoding="utf-8"))
            lock["invariants"][0]["planted_negatives"][0] = "tests.test_noodles.DaemonLeaseTests.test_planted_never_written"
            path.write_text(json.dumps(lock), encoding="utf-8")
            self.commit(root)
            errors = self.proof_errors(root)
            self.assertTrue(any("absent from the tracked suite" in item for item in errors), errors)

    def test_single_lane_with_no_lock_passes(self) -> None:
        temp, root = self.mutated_copy()
        with temp:
            self.set_concurrency(root, 1)
            cmd(["git", "rm", "-q", self.PROOF], root)
            self.commit(root)
            self.assertEqual(self.proof_errors(root), [])

    def test_the_declared_number_is_never_bounded_above(self) -> None:
        # constraint: ed3c/noodles#100 - the evidence ceiling replaces the numeric stop-loss, so an
        # constraint: absurd N passes exactly as four does while the lock stands. A future numeric cap
        # constraint: smuggled into this gate turns this control red.
        temp, root = self.mutated_copy()
        with temp:
            self.set_concurrency(root, 4096)
            self.commit(root)
            self.assertEqual(self.proof_errors(root), [])


if __name__ == "__main__":
    unittest.main()

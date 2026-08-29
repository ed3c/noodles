from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import runtime_contract
import skill_contract
import noodles
from tests.support import CANDIDATE_ROOT, ENGINE_ROOT, cmd, copy_tracked

TASK_PROFILES = json.loads((ENGINE_ROOT / "policy/fitness.json").read_text())["required_codex_task_profiles"]


class ScheduleContractTests(unittest.TestCase):
    def mutated_copy(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temp = tempfile.TemporaryDirectory(prefix="noodles-schedule-policy-")
        root = Path(temp.name) / "repo"
        copy_tracked(CANDIDATE_ROOT, root)
        return temp, root

    def run_carrier(self, argv: list[str]) -> subprocess.CompletedProcess[str]:
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
                [str(CANDIDATE_ROOT / ".agents/bin/codex"), *argv],
                cwd=CANDIDATE_ROOT,
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

    def runtime_promote(self, payload: dict[str, object]) -> dict[str, object]:
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

    def test_codex_task_model_map_is_exact_and_drift_is_rejected(self) -> None:
        self.assertEqual(
            TASK_PROFILES,
            {
                "schedule": {"model": "gpt-5.6-luna", "reasoning_effort": "max"},
                "execute": {"model": "gpt-5.6-sol", "reasoning_effort": "high"},
            },
        )
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        path = root / "policy/fitness.json"
        policy = json.loads(path.read_text())
        policy["required_codex_task_profiles"]["execute"]["model"] = "gpt-5.6-pro"
        path.write_text(json.dumps(policy))
        cmd(["git", "add", "policy/fitness.json"], root)
        cmd(["git", "commit", "-q", "-m", "model drift"], root)
        result = noodles.verify_repository(root, root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("required_codex_task_profiles must be exactly" in item for item in result["errors"]))

    def test_codex_carrier_injects_exact_effort_for_each_task_model(self) -> None:
        cases = (
            ("gpt-5.6-luna", "max"),
            ("gpt-5.6-sol", "high"),
        )
        for model, effort in cases:
            with self.subTest(model=model):
                result = self.run_carrier([
                    "exec",
                    "--model",
                    model,
                    "-c",
                    'approval_policy="never"',
                ])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    json.loads(result.stdout),
                    [
                        "exec",
                        "-c",
                        f'model_reasoning_effort="{effort}"',
                        "--model",
                        model,
                        "-c",
                        'approval_policy="never"',
                    ],
                )

    def test_codex_carrier_stops_option_parsing_at_delimiter(self) -> None:
        argv = ["exec", "--model", "gpt-5.6-sol", "--", "-mgpt-5.6-pro", '-cmodel_reasoning_effort="max"']
        result = self.run_carrier(argv)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), ["exec", "-c", 'model_reasoning_effort="high"', *argv[1:]])

    def test_codex_carrier_rejects_unadmitted_or_ambiguous_model_before_spawn(self) -> None:
        cases = (
            ("missing", ["exec"]),
            ("empty", ["exec", "--model="]),
            ("duplicate", ["exec", "--model", "gpt-5.6-sol", "--model=gpt-5.6-luna"]),
            ("mixed duplicate", ["exec", "--model", "gpt-5.6-sol", "-m", "gpt-5.6-pro"]),
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
                result = self.run_carrier(["exec", "--model", "gpt-5.6-sol", *override])
                self.assertEqual(result.returncode, 2)
                self.assertIn("must come only from the task profile", result.stderr)
                self.assertEqual(result.stdout, "")

    def test_schedule_skill_without_task_model_routing_contract_is_rejected(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        path = root / ".agents/skills/schedule/SKILL.md"
        content = path.read_text()
        self.assertIn(skill_contract.SCHEDULE_TASK_MODEL_PHRASE, content)
        path.write_text(content.replace(skill_contract.SCHEDULE_TASK_MODEL_PHRASE, "Choose a model ad hoc.", 1))
        result = noodles.verify_repository(root, CANDIDATE_ROOT)
        self.assertFalse(result["ok"])
        self.assertTrue(any("task-model routing" in item for item in result["errors"]))

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
                "stages": [{"do": "execute", "model": "gpt-5.6-sol", "prompt": "next"}],
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
                "stages": [{"do": "execute", "model": "gpt-5.6-sol", "prompt": "next", "bogus": 1}],
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
            ("missing", None, "requires explicit model 'gpt-5.6-sol' for execute"),
            ("unsupported alias", "gpt-5.6", "found 'gpt-5.6'"),
            ("rejected placeholder", "gpt-5.6-pro", "found 'gpt-5.6-pro'"),
            ("unrelated model", "claude-opus-4-1", "found 'claude-opus-4-1'"),
            ("schedule/execute mismatch", "gpt-5.6-luna", "found 'gpt-5.6-luna'"),
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
                {"orders": [{"id": "ed3c/noodles#44", "stages": [{"do": "execute", "model": "gpt-5.6-sol", "prompt": "next"}]}]},
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
                {"orders": [{"id": "ed3c/noodles#44", "stages": [{"do": "execute", "model": "gpt-5.6-sol", "prompt": "next"}], "bogus": 1}]},
                False,
                "bogus",
            ),
            (
                "unknown stage field",
                {"orders": [{"id": "ed3c/noodles#44", "stages": [{"do": "execute", "model": "gpt-5.6-sol", "prompt": "next", "bogus": 1}]}]},
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


if __name__ == "__main__":
    unittest.main()

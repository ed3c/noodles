from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
            (policy_dir / "github.json").write_text(
                (CANDIDATE_ROOT / "policy/github.json").read_text(),
                encoding="utf-8",
            )
            cmd(["git", "init", "-q", "-b", "main"], root)
            cmd(["git", "remote", "add", "origin", "git@github.com:ed3c/noodles.git"], root)
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
        self.assertEqual(skill_contract.validate_schedule_output({"orders": []}, proposed, TASK_PROFILES, "ed3c/noodles"), [])

    def test_target_local_repository_receipt_reads_exact_self_policy(self) -> None:
        receipt = runtime_contract.target_local_repository_admission(
            CANDIDATE_ROOT,
            json.loads((CANDIDATE_ROOT / "policy/github.json").read_text()),
            error_cls=AssertionError,
        )
        self.assertEqual(receipt.origin_repository, "ed3c/noodles")
        self.assertEqual(receipt.repository, "ed3c/noodles")
        self.assertEqual(receipt.cross_repository_status, "TARGET_LOCAL_ONLY")
        self.assertEqual(
            receipt.authority_payload(),
            {
                "origin_repository": "ed3c/noodles",
                "repository": "ed3c/noodles",
                "default_branch": "main",
                "required_check": "verify",
                "merge_method": "merge",
                "require_branch_protection": True,
                "cross_repository_status": "TARGET_LOCAL_ONLY",
            },
        )
        self.assertNotIn("root", receipt.authority_payload())
        verified = noodles.verify_repository(CANDIDATE_ROOT, ENGINE_ROOT)
        self.assertEqual(verified["target"], receipt.authority_payload())

    def test_verify_receipt_reads_back_complete_exact_head_target_authority(self) -> None:
        head = cmd(["git", "rev-parse", "HEAD"], CANDIDATE_ROOT)
        event = {
            "repository": {"full_name": "ed3c/noodles"},
            "pull_request": {
                "number": 14,
                "head": {"sha": head},
                "base": {"ref": "main"},
                "draft": False,
                "body": "Refs ed3c/noodles#14",
            },
        }
        issue = {
            "state": "open",
            "body": (
                "<!-- noodles-role: repository-mutating-atom -->\n"
                "<!-- noodles-target: ed3c/noodles -->\n"
                "<!-- noodles-subject: ed3c/noodles#14 -->\n"
                "<!-- noodles-state: awaiting_land -->\n"
                "<!-- noodles-feature: verification-skill-oracle -->\n"
                "<!-- noodles-depends-on: ed3c/noodles#3, ed3c/noodles#4 -->\n"
            ),
        }
        authority = noodles.target_local_repository(CANDIDATE_ROOT).authority_payload()
        with tempfile.TemporaryDirectory(prefix="noodles-verify-authority-") as temp_name:
            event_path = Path(temp_name) / "event.json"
            receipt_path = Path(temp_name) / "receipt.json"
            event_path.write_text(json.dumps(event), encoding="utf-8")
            with mock.patch.object(noodles, "issue_read", return_value=issue), mock.patch.object(
                noodles,
                "verify_repository",
                return_value={"ok": True, "errors": [], "metrics": {}, "target": authority},
            ):
                receipt = noodles.verify_pull_request(
                    CANDIDATE_ROOT,
                    event_path,
                    CANDIDATE_ROOT,
                    receipt_path,
                )
            self.assertEqual(receipt["target_authority"], authority)
            self.assertEqual(json.loads(receipt_path.read_text())["target_authority"], authority)

    def test_verify_rejects_subject_mismatch_before_issue_read_or_receipt(self) -> None:
        head = cmd(["git", "rev-parse", "HEAD"], CANDIDATE_ROOT)
        event = {
            "repository": {"full_name": "ed3c/noodles"},
            "pull_request": {
                "number": 14,
                "head": {"sha": head},
                "base": {"ref": "main"},
                "draft": False,
                "body": "Refs ed3c/foreign#14",
            },
        }
        with tempfile.TemporaryDirectory(prefix="noodles-verify-subject-") as temp_name:
            event_path = Path(temp_name) / "event.json"
            receipt_path = Path(temp_name) / "receipt.json"
            event_path.write_text(json.dumps(event), encoding="utf-8")
            with mock.patch.object(noodles, "issue_read") as issue_read, mock.patch.object(
                noodles,
                "verify_repository",
            ) as repository_gate:
                with self.assertRaisesRegex(noodles.GateError, "verify Issue subject repository"):
                    noodles.verify_pull_request(
                        CANDIDATE_ROOT,
                        event_path,
                        CANDIDATE_ROOT,
                        receipt_path,
                    )
            issue_read.assert_not_called()
            repository_gate.assert_not_called()
            self.assertFalse(receipt_path.exists())

    def test_handoff_rejects_subject_mismatch_before_issue_or_control_mutation(self) -> None:
        with mock.patch.object(noodles, "issue_read") as issue_read, mock.patch.object(
            noodles,
            "issue_set_state",
        ) as issue_mutation, mock.patch.object(noodles, "emit_blocking_handoff") as control_mutation:
            with self.assertRaisesRegex(noodles.GateError, "handoff subject repository"):
                noodles.execute_handoff(CANDIDATE_ROOT, "ed3c/foreign#14", 14, {})
        issue_read.assert_not_called()
        issue_mutation.assert_not_called()
        control_mutation.assert_not_called()

    def test_land_rejects_target_policy_drift_before_provider_mutation(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        authority = noodles.target_local_repository(root).authority_payload()
        head = "a" * 40
        event = {
            "repository": {"full_name": "ed3c/noodles"},
            "workflow_run": {
                "id": 1414,
                "name": "verify",
                "conclusion": "success",
                "head_sha": head,
                "pull_requests": [{"number": 14}],
            },
        }
        receipt = {
            "repository": "ed3c/noodles",
            "pr_number": 14,
            "head_sha": head,
            "target_authority": authority,
        }
        policy_path = root / "policy/github.json"
        policy = json.loads(policy_path.read_text())
        policy["required_check"] = "verify-policy-drift"
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        with tempfile.TemporaryDirectory(prefix="noodles-land-authority-") as temp_name:
            event_path = Path(temp_name) / "event.json"
            receipt_path = Path(temp_name) / "receipt.json"
            event_path.write_text(json.dumps(event), encoding="utf-8")
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            with mock.patch.object(noodles, "gh_api") as provider_mutation, mock.patch.object(
                noodles.github_protection,
                "workflow_boundary_readback",
            ) as workflow_readback:
                with self.assertRaisesRegex(noodles.GateError, "target_authority"):
                    noodles.land_pull_request(root, event_path, receipt_path)
        workflow_readback.assert_not_called()
        merge_puts = [
            call
            for call in provider_mutation.call_args_list
            if call.kwargs.get("method") == "PUT" and str(call.args[0]).endswith("/merge")
        ]
        issue_patches = [
            call
            for call in provider_mutation.call_args_list
            if call.kwargs.get("method") == "PATCH" and "/issues/" in str(call.args[0])
        ]
        self.assertEqual(merge_puts, [])
        self.assertEqual(issue_patches, [])

    def test_target_local_repository_receipt_rejects_policy_authority_drift(self) -> None:
        base = json.loads((CANDIDATE_ROOT / "policy/github.json").read_text())
        cases = (
            ("repository", "ed3c/foreign", "local origin repository"),
            ("unexpected", "value", "fields drifted"),
            ("merge_method", "squash", "merge_method"),
            ("require_branch_protection", False, "require_branch_protection"),
            ("cross_repository_status", "HOLD_UNTIL_TARGET_INSTALLATION_AND_TOKEN_READBACK", "cross_repository_status"),
        )
        for field, value, diagnostic in cases:
            with self.subTest(field=field):
                policy = dict(base)
                policy[field] = value
                with self.assertRaisesRegex(AssertionError, diagnostic):
                    runtime_contract.target_local_repository_admission(
                        CANDIDATE_ROOT,
                        policy,
                        error_cls=AssertionError,
                    )

    def test_local_origin_never_substitutes_for_target_identity(self) -> None:
        temp = tempfile.TemporaryDirectory(prefix="noodles-local-origin-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / "repo"
        copy_tracked(CANDIDATE_ROOT, root)
        cmd(["git", "remote", "set-url", "origin", str(Path(temp.name) / "provider.git")], root)
        policy = json.loads((root / "policy/github.json").read_text())
        with self.assertRaisesRegex(AssertionError, "cannot derive GitHub repository"):
            runtime_contract.target_local_repository_admission(root, policy, error_cls=AssertionError)

    def test_foreign_schedule_candidate_fails_before_promotion(self) -> None:
        result = self.local_publish({
            "orders": [{
                "id": "ed3c/foreign#70",
                "stages": [{"do": "execute", "model": "gpt-5.6-sol", "prompt": "foreign"}],
            }]
        })
        self.assertFalse(result["accepted"])
        self.assertIn("target-local repository 'ed3c/noodles'", str(result["error"]))
        self.assertTrue(result["candidate_exists"])
        self.assertFalse(result["published_exists"])

    def test_codex_task_model_map_is_exact_and_drift_is_rejected(self) -> None:
        self.assertEqual(
            TASK_PROFILES,
            {
                "schedule": {"model": "gpt-5.6-luna", "reasoning_effort": "high"},
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
            ("gpt-5.6-luna", ("high",)),
            ("gpt-5.6-sol", ("high",)),
        )
        for model, admitted_efforts in cases:
            with self.subTest(model=model):
                result = self.run_carrier([
                    "exec",
                    "--model",
                    model,
                    "-c",
                    'approval_policy="never"',
                ])
                self.assertEqual(result.returncode, 0, result.stderr)
                argv = json.loads(result.stdout)
                self.assertIn(
                    argv[:3],
                    [["exec", "-c", f'model_reasoning_effort="{effort}"'] for effort in admitted_efforts],
                )
                self.assertEqual(
                    argv[3:],
                    ["--model", model, "-c", 'approval_policy="never"'],
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
            skill_contract.validate_schedule_output({"orders": []}, proposed, TASK_PROFILES, "ed3c/noodles"),
            ["scheduler output has unknown field 'rationale'; allowed fields: action_needed, orders"],
        )

    def test_schedule_output_rejects_non_array_action_needed(self) -> None:
        proposed = {"orders": [], "action_needed": "ed3c/noodles#43"}
        self.assertEqual(
            skill_contract.validate_schedule_output({"orders": []}, proposed, TASK_PROFILES, "ed3c/noodles"),
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
            skill_contract.validate_schedule_output({"orders": []}, proposed, TASK_PROFILES, "ed3c/noodles"),
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
            skill_contract.validate_schedule_output({"orders": []}, proposed, TASK_PROFILES, "ed3c/noodles"),
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

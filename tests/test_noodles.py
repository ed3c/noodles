from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import tomllib
import unittest
from pathlib import Path
from unittest import mock

import noodles
import runtime_contract
import skill_contract
from tests.support import (
    CANDIDATE_ROOT,
    ENGINE_ROOT,
    cmd,
    copy_tracked,
    cursor_pstack_fixture,
    handoff_fixture,
    provider_fixture,
    runtime_release_reader,
    assert_valid_start_entrypoint_receipt,
    script_mode_gateerror_identity,
    start_entrypoint_with_delayed_listener,
    tree_digest,
    validate_script_mode_gateerror_identity,
    write_noodle_stub,
    write_skill_discovery_fixture,
)
TASK_PROFILES = json.loads((ENGINE_ROOT / "policy/fitness.json").read_text())["required_codex_task_profiles"]

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
            }
        )
        return metrics

    def verify_with_metrics(self, *, overrides: dict[str, object], root: Path = CANDIDATE_ROOT) -> dict:
        metrics = self.passing_metrics()
        metrics.update(overrides)
        with mock.patch.object(noodles, "repository_metrics", return_value=metrics):
            return noodles.verify_repository(root, ENGINE_ROOT)

    def mutated_copy(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temp = tempfile.TemporaryDirectory(prefix="noodles-test-")
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
        expected = {"schedule": {"model": "gpt-5.6-luna", "reasoning_effort": "max"}, "execute": {"model": "gpt-5.6-sol", "reasoning_effort": "high"}}
        self.assertEqual(TASK_PROFILES, expected)
        self.assertEqual(config["routing"]["defaults"]["model"], expected["schedule"]["model"])
        self.assertEqual(config["agents"]["codex"]["path"], ".agents/bin")
        result = self.verify()
        self.assertTrue(result["ok"], result["errors"])

    def test_runtime_lock_pins_expected_release(self) -> None:
        payload = json.loads((CANDIDATE_ROOT / "policy/runtime.lock.json").read_text())
        self.assertEqual(
            payload["runtime"],
            {
                "repository": "poteto/noodle",
                "release": "v0.1.5",
                "commit": "eaa1d5cce36f73e33e81d4855bb2fc47e33d0b24",
                "command": "noodle",
                "platforms": {
                    "darwin_arm64": {
                        "asset_name": "noodle_darwin_arm64.tar.gz",
                        "asset_sha256": "d83f367b0afd933a6322b7fcf01888ff098f4df3c2c6ac058355cb652c078765",
                        "binary_sha256": "56dfc5bbc05a45c41783715d01c24edab79a8e94f0ba777066325b9302a3f375",
                    }
                },
            },
        )

    def test_provider_lock_pins_expected_external_skills(self) -> None:
        payload = json.loads((CANDIDATE_ROOT / "policy/providers.lock.json").read_text())
        self.assertEqual(
            payload["providers"],
            [
                {
                    "name": "cursor-pstack",
                    "source": "https://github.com/cursor/plugins.git",
                    "commit": "68836ddaf5697224520f1847d90cdb90ca8babaa",
                    "subpath": "pstack/skills",
                    "destination": ".noodle/providers/cursor-pstack",
                    "license_path": "pstack/LICENSE",
                    "enabled": True,
                    "authority": "P",
                    "purpose": "Engineering lifecycle routing; never a correctness authority.",
                },
                {
                    "name": "skill-concerns",
                    "source": "https://github.com/ed3c/skill-concerns.git",
                    "commit": "c91dbd04d1997b2e0f77907c9c2a40f55b787107",
                    "subpath": "skills/control-noodle",
                    "destination": ".noodle/providers/skill-concerns",
                    "license_path": "LICENSE",
                    "admission": {
                        "path": "admissions/control-noodle.json",
                        "sha256": "4e20f09502ba16db920a89b945ebbb9ac206946a7906ceea92090ecb2c93e42d",
                        "skill": "control-noodle",
                        "skill_tree_sha256": "969111ff62cc68a1df82e036f2fe892e4ab9a850bbf2020f0f4253f6db866581",
                        "subject_files": {
                            "skills/control-noodle/SKILL.md": "efa5a1d2e9166af47f9078bdc5924fb6520ae0171a0a068472f7abab02b00a1a",
                        },
                    },
                    "enabled": True,
                    "authority": "P",
                    "purpose": "Replaceable engineering knowledge; never a correctness authority.",
                },
                {
                    "name": "skills-shared-compat",
                    "source": "https://github.com/ed3c/skills-shared.git",
                    "commit": "52b29b38ded9eaacbf7fb1bfa8ccf69ab37870b9",
                    "subpath": ".",
                    "destination": ".noodle/providers/skills-shared-compat",
                    "license_path": "LICENSE",
                    "enabled": False,
                    "authority": "P",
                    "purpose": "Explicitly disabled compatibility source; not a Golden Path dependency.",
                },
            ],
        )

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

    def test_execute_skill_without_required_p_contract_is_rejected(self) -> None:
        cases = (
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
            (
                skill_contract.EXECUTE_UNSUPPORTED_PHRASE,
                "Unsupported routes may proceed best-effort.",
                "unsupported route refusal",
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

    def test_schedule_skill_without_self_order_ownership_contract_is_rejected(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        path = root / ".agents/skills/schedule/SKILL.md"
        content = path.read_text()
        ownership = "Noodle alone injects and owns the transient `schedule` order."
        self.assertIn(ownership, content)
        path.write_text(content.replace(ownership, "The scheduler may preserve its own order.", 1))
        result = self.verify(root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("self-order ownership" in item for item in result["errors"]))

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
                "stages": [{"do": "execute", "model": "gpt-5.6-sol", "prompt": "next"}],
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
        with tempfile.TemporaryDirectory(prefix="noodles-schedule-negative-") as temp_name:
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
        with tempfile.TemporaryDirectory(prefix="noodles-schedule-contract-") as temp_name:
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

    def test_invalid_migration_promotion_is_rejected(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        path = root / "migrations/skills-shared/ledger.json"
        payload = json.loads(path.read_text())
        payload["capabilities"][6]["disposition"] = "MIGRATE"
        path.write_text(json.dumps(payload))
        self.commit(root)
        result = self.verify(root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("MIGRATE requires physical evidence" in item for item in result["errors"]))

    def test_untrusted_workflow_boundary_is_rejected(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        path = root / ".github/workflows/verify.yml"
        path.write_text(path.read_text().replace("pull_request_target:", "pull_request:"))
        self.commit(root)
        result = self.verify(root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("trusted boundary" in item for item in result["errors"]))

    def test_trusted_verify_requires_candidate_job_dependency(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        path = root / ".github/workflows/verify.yml"
        workflow = path.read_text()
        dependency = "    needs: candidate-self-tests\n"
        self.assertIn(dependency, workflow)
        path.write_text(workflow.replace(dependency, "", 1))
        self.commit(root)
        result = self.verify(root)
        self.assertFalse(result["ok"])
        self.assertIn("trusted verify job must depend only on candidate-self-tests", result["errors"])

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
                "architecture warning tracked_files=36 exceeds 35",
            ),
            ("root_surfaces", "max_root_surfaces", "max", policy["max_root_surfaces"] + 1, policy["max_root_surfaces"], "architecture warning root_surfaces=10 exceeds 9"),
        )
        for metric_key, policy_key, direction, planted_value, threshold, warning in cases:
            with self.subTest(metric=metric_key):
                result = self.verify_with_metrics(overrides={metric_key: planted_value})
                self.assertTrue(result["ok"], result.get("errors"))
                self.assertEqual(result.get("errors"), [])
                self.assertEqual(result.get("warnings"), [warning])
                self.assertEqual(len(result.get("warning_readback", [])), len(skill_contract.REPORT_ONLY_FITNESS_LIMITS))
                warning_entries = [item for item in result["warning_readback"] if item["status"] == "warning"]
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
                    {item["metric"] for item in result["warning_readback"] if item["status"] == "ok"},
                    set(skill_contract.REPORT_ONLY_FITNESS_LIMITS) - {metric_key},
                )
                self.assertEqual(result["metrics"][metric_key], planted_value)
                self.assertFalse(any(f"fitness {metric_key}=" in item for item in result.get("errors", [])))

    def test_enabled_provider_count_still_fails_closed(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        path = root / "policy/providers.lock.json"
        payload = json.loads(path.read_text())
        payload["providers"][2]["enabled"] = True
        path.write_text(json.dumps(payload))
        self.commit(root)
        with mock.patch.object(noodles, "repository_metrics", return_value=self.baseline_metrics()):
            result = self.verify(root)
        self.assertFalse(result["ok"])
        self.assertIn("enabled providers 3 exceed limit 2", result["errors"])

    def test_workflow_count_still_fails_closed(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        extra = root / ".github/workflows/extra.yml"
        extra.write_text("name: extra\non: workflow_dispatch\njobs: {}\n")
        self.commit(root)
        with mock.patch.object(noodles, "repository_metrics", return_value=self.baseline_metrics()):
            result = self.verify(root)
        self.assertFalse(result["ok"])
        self.assertIn("workflow count must equal 2, got 3", result["errors"])

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
             mock.patch.object(noodles, "skill_discovery_check"), \
             mock.patch.object(noodles, "protection_policy", return_value=policy), \
             mock.patch.object(noodles, "protection_readback"), \
             mock.patch.object(noodles.subprocess, "Popen", return_value=process), \
             mock.patch.object(noodles, "repair_pending_reviews") as repair, \
             mock.patch.object(noodles, "reconcile_once") as reconcile, \
             mock.patch.object(time, "sleep") as sleep:
            result = noodles.start_unattended(CANDIDATE_ROOT, "http://noodle.test", 0.25)

        self.assertEqual(result, 0)
        repair.assert_called_once_with(CANDIDATE_ROOT, "http://noodle.test")
        reconcile.assert_called_once_with(CANDIDATE_ROOT, "http://noodle.test")
        sleep.assert_called_once_with(0.25)
        process.terminate.assert_not_called()

    def test_wrapper_does_not_swallow_non_gate_exceptions(self) -> None:
        process = mock.Mock(returncode=0)
        process.poll.side_effect = [None, None]
        policy = {"repository": "ed3c/noodles", "default_branch": "main", "required_check": "verify"}
        with mock.patch.object(noodles, "control_checkout_admission", return_value={"branch": "main"}), mock.patch.object(noodles, "verify_repository", return_value={"ok": True, "errors": []}), mock.patch.object(noodles, "runtime_check", return_value={"binary_path": "/tmp/noodle"}), mock.patch.object(noodles, "provider_sync"), mock.patch.object(noodles, "skill_discovery_check"), mock.patch.object(noodles, "protection_policy", return_value=policy), mock.patch.object(noodles, "protection_readback"), mock.patch.object(noodles.subprocess, "Popen", return_value=process), mock.patch.object(noodles, "repair_pending_reviews", side_effect=RuntimeError("boom")):
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
        temp = tempfile.TemporaryDirectory(prefix="noodles-runtime-test-")
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
if __name__ == "__main__":
    unittest.main()

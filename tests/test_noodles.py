from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import tomllib
import unittest
from unittest import mock
from pathlib import Path

import noodles
import runtime_contract
import skill_contract

ENGINE_ROOT = Path(noodles.__file__).resolve().parent
CANDIDATE_ROOT = Path(os.getenv("NOODLES_CANDIDATE_ROOT", ENGINE_ROOT)).resolve()


def cmd(argv: list[str], cwd: Path) -> str:
    result = subprocess.run(argv, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        raise AssertionError(f"command failed {argv}: {result.stderr or result.stdout}")
    return result.stdout.strip()


def initialize_repo(root: Path) -> None:
    cmd(["git", "init", "-q", "-b", "main"], root)
    cmd(["git", "config", "user.name", "tests"], root)
    cmd(["git", "config", "user.email", "tests@example.invalid"], root)
    cmd(["git", "add", "-A"], root)
    cmd(["git", "commit", "-q", "--allow-empty", "-m", "fixture"], root)


def copy_tracked(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True)
    tracked = cmd(["git", "ls-files"], source).splitlines()
    for relative in tracked:
        src = source / relative
        dst = destination / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst, follow_symlinks=False)
    initialize_repo(destination)


def write_noodle_stub(path: Path, version: str) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import os\n"
        "import sys\n"
        "args = sys.argv[1:]\n"
        f"if args == ['--version']:\n    print({version!r})\n"
        "elif len(args) >= 4 and args[0] == '--project-dir' and args[2:] == ['skills', 'list']:\n"
        "    print(os.environ.get('NOODLES_TEST_SKILLS_OUTPUT', ''), end='')\n"
        "else:\n"
        "    raise SystemExit(f'unexpected args: {args}')\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def write_handoff_noodle_stub(path: Path, version: str, blocking: bool = True) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import pathlib\n"
        "import sys\n"
        "args = sys.argv[1:]\n"
        f"if args == ['--version']:\n    print({version!r})\n"
        "elif len(args) == 9 and args[0] == '--project-dir' and args[2:5] == ['event', 'emit', 'stage_message']:\n"
        "    root = pathlib.Path(args[1])\n"
        "    session = args[6]\n"
        "    payload = json.loads(args[8])\n"
        f"    payload['blocking'] = {blocking!r}\n"
        "    event = {'type': 'stage_message', 'payload': payload, 'timestamp': '2026-08-29T00:00:00Z', 'session_id': session}\n"
        "    target = root / '.noodle' / 'sessions' / session / 'events.ndjson'\n"
        "    with target.open('a', encoding='utf-8') as handle:\n"
        "        handle.write(json.dumps(event) + '\\n')\n"
        "else:\n"
        "    raise SystemExit(f'unexpected args: {args}')\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def handoff_fixture(
    source: Path,
    subject: str = "ed3c/noodles#33",
    *,
    blocking: bool = True,
) -> tuple[tempfile.TemporaryDirectory[str], Path, Path, str]:
    temp = tempfile.TemporaryDirectory(prefix="noodles-handoff-test-")
    root = Path(temp.name) / "repo"
    copy_tracked(source, root)
    cmd(["git", "remote", "add", "origin", "git@github.com:ed3c/noodles.git"], root)
    binary = Path(temp.name) / "noodle"
    write_handoff_noodle_stub(binary, "v0.1.5", blocking)
    lock_path = root / "policy/runtime.lock.json"
    lock = json.loads(lock_path.read_text())
    lock["runtime"]["command"] = str(binary)
    lock["runtime"]["platforms"]["darwin_arm64"]["binary_sha256"] = runtime_contract.sha256_file(binary)
    lock_path.write_text(json.dumps(lock))
    session_id = "ed3c-noodles-33-0-execute-fixture"
    session = root / ".noodle" / "sessions" / session_id
    session.mkdir(parents=True)
    (session / "spawn.json").write_text(json.dumps({"worktree_path": str(root)}))
    (session / "events.ndjson").write_text(json.dumps({
        "type": "action",
        "payload": {"message": f"[order:{subject}] fixture"},
        "timestamp": "2026-08-29T00:00:00Z",
        "session_id": session_id,
    }) + "\n")
    return temp, root, binary, session_id


def provider_fixture(subpath: str = "skills/engineering", license_path: str = "LICENSE") -> tuple[tempfile.TemporaryDirectory[str], Path]:
    temp = tempfile.TemporaryDirectory(prefix="noodles-provider-test-")
    base = Path(temp.name)
    candidate = base / "candidate"
    copy_tracked(CANDIDATE_ROOT, candidate)
    source = base / "source"
    source.mkdir()
    initialize_repo(source)
    (source / "LICENSE").write_text("MIT\n")
    (source / "skills/engineering/example").mkdir(parents=True)
    (source / "skills/engineering/example/SKILL.md").write_text("# Example\n")
    cmd(["git", "add", "-A"], source)
    cmd(["git", "commit", "-q", "-m", "provider"], source)
    commit = cmd(["git", "rev-parse", "HEAD"], source)
    lock_path = candidate / "policy/providers.lock.json"
    lock = json.loads(lock_path.read_text())
    lock["providers"] = [
        {
            "name": "fixture",
            "source": str(source),
            "commit": commit,
            "subpath": subpath,
            "destination": ".noodle/providers/fixture",
            "license_path": license_path,
            "enabled": True,
            "authority": "P",
        }
    ]
    lock_path.write_text(json.dumps(lock))
    return temp, candidate


def runtime_release_reader(release: str, commit: str, asset_name: str, asset_sha256: str):
    def read(endpoint: str) -> dict:
        if endpoint == f"repos/poteto/noodle/releases/tags/{release}":
            return {
                "tag_name": release,
                "assets": [{"name": asset_name, "digest": f"sha256:{asset_sha256}"}],
            }
        if endpoint == f"repos/poteto/noodle/git/ref/tags/{release}":
            return {"object": {"type": "commit", "sha": commit}}
        raise AssertionError(f"unexpected endpoint {endpoint}")

    return read


def protection_fixture() -> dict:
    return {
        "url": "https://api.github.com/repos/ed3c/noodles/branches/main/protection",
        "required_status_checks": {
            "strict": True,
            "contexts": ["verify"],
            "checks": [{"context": "verify", "app_id": 15368}],
        },
        "required_pull_request_reviews": {
            "dismiss_stale_reviews": False,
            "require_code_owner_reviews": False,
            "require_last_push_approval": False,
            "required_approving_review_count": 0,
        },
        "enforce_admins": {"enabled": True},
        "allow_force_pushes": {"enabled": False},
        "allow_deletions": {"enabled": False},
    }


class RepositoryGateTests(unittest.TestCase):
    def verify(self, root: Path = CANDIDATE_ROOT) -> dict:
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

    def test_auto_mode_is_rejected(self) -> None:
        temp, root = self.mutated_copy()
        self.addCleanup(temp.cleanup)
        path = root / ".noodle.toml"
        path.write_text(path.read_text().replace('mode = "supervised"', 'mode = "auto"'))
        self.commit(root)
        result = self.verify(root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("mode must be" in item for item in result["errors"]))

    def test_codex_routing_model_is_admitted(self) -> None:
        with (CANDIDATE_ROOT / ".noodle.toml").open("rb") as handle:
            config = tomllib.load(handle)
        self.assertEqual(config["routing"]["defaults"]["model"], "gpt-5.4")
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
                    "name": "matt-engineering",
                    "source": "https://github.com/mattpocock/skills.git",
                    "commit": "6654f6b60cd9d5be8b54c6fafe44346dabeb3b76",
                    "subpath": "skills/engineering",
                    "destination": ".noodle/providers/matt-engineering",
                    "license_path": "LICENSE",
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
        admitted = 'model = "gpt-5.4"'
        self.assertIn(admitted, config)
        path.write_text(config.replace(admitted, 'model = "gpt-5.6-pro"', 1))
        self.commit(root)
        result = self.verify(root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("routing model must be" in item for item in result["errors"]))

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
                "stages": [{"do": "execute", "prompt": "next"}],
            }]
        }
        self.assertEqual(skill_contract.validate_schedule_output(current, proposed), [])

    def test_planted_negative_schedule_self_order_fixture_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="noodles-schedule-negative-") as temp_name:
            root = Path(temp_name)
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
        errors = skill_contract.validate_schedule_output(current, proposed)
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
        self.assertTrue(any("verify missing" in item for item in result["errors"]))

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
        self.assertTrue(any("verify forbids" in item for item in result["errors"]))

    def test_metrics_stay_inside_budget(self) -> None:
        metrics = noodles.repository_metrics(CANDIDATE_ROOT)
        policy = json.loads((ENGINE_ROOT / "policy/fitness.json").read_text())
        self.assertLessEqual(metrics["tracked_files"], policy["max_tracked_files"])
        self.assertLessEqual(metrics["max_file_lines"], policy["max_file_lines"])
        self.assertGreaterEqual(metrics["test_to_executable_ratio"], policy["min_test_to_executable_ratio"])


class ContractParserTests(unittest.TestCase):
    BODY = """<!-- noodles-role: repository-mutating-atom -->
<!-- noodles-target: ed3c/noodles -->
<!-- noodles-subject: ed3c/noodles#7 -->
<!-- noodles-state: ready -->
"""

    def test_issue_contract_positive(self) -> None:
        parsed = noodles.parse_issue_contract(self.BODY, "ed3c/noodles#7")
        self.assertEqual(parsed["state"], "ready")

    def test_issue_contract_rejects_target_drift(self) -> None:
        with self.assertRaises(noodles.GateError):
            noodles.parse_issue_contract(self.BODY.replace("noodles-target: ed3c/noodles", "noodles-target: ed3c/other"))

    def test_pr_reference_is_exact_and_non_closing(self) -> None:
        self.assertEqual(noodles.parse_pr_reference("Refs ed3c/noodles#7\n"), "ed3c/noodles#7")
        with self.assertRaises(noodles.GateError):
            noodles.parse_pr_reference("Claim\nRefs ed3c/noodles#7\n")
        with self.assertRaises(noodles.GateError):
            noodles.parse_pr_reference("Refs ed3c/noodles#7\nRefs ed3c/noodles#8\n")
        with self.assertRaises(noodles.GateError):
            noodles.parse_pr_reference("Closes #7\nRefs ed3c/noodles#7\n")

    def test_state_marker_replacement_is_single(self) -> None:
        changed = noodles.replace_marker(self.BODY, "state", "awaiting_land")
        self.assertEqual(noodles.parse_issue_contract(changed)["state"], "awaiting_land")


class ExecuteHandoffTests(unittest.TestCase):
    SUBJECT = "ed3c/noodles#33"

    def setUp(self) -> None:
        self.temp, self.root, self.binary, self.session_id = handoff_fixture(CANDIDATE_ROOT)
        self.addCleanup(self.temp.cleanup)
        self.head = cmd(["git", "rev-parse", "HEAD"], self.root)

    def pr(self, **overrides: object) -> dict:
        payload = {
            "state": "open",
            "draft": False,
            "body": f"Refs {self.SUBJECT}",
            "head": {"sha": self.head},
            "base": {"ref": "main"},
        }
        payload.update(overrides)
        return payload

    def test_positive_handoff_emits_one_blocking_message_for_exact_session(self) -> None:
        pr = self.pr()
        with mock.patch.dict(os.environ, {"NOODLE_SESSION_ID": self.session_id}, clear=False), \
             mock.patch.object(noodles, "issue_set_state"):
            receipt = noodles.execute_handoff(self.root, self.SUBJECT, 44, pr)

        self.assertEqual(receipt["session_id"], self.session_id)
        self.assertEqual(receipt["head"], self.head)
        events_path = self.root / ".noodle" / "sessions" / self.session_id / "events.ndjson"
        events = [json.loads(line) for line in events_path.read_text().splitlines()]
        handoffs = [item for item in events if item["type"] == "stage_message"]
        self.assertEqual(len(handoffs), 1)
        self.assertIs(handoffs[0]["payload"]["blocking"], True)
        self.assertIn(self.SUBJECT, handoffs[0]["payload"]["message"])

        with mock.patch.dict(os.environ, {"NOODLE_SESSION_ID": self.session_id}, clear=False), \
             mock.patch.object(noodles, "issue_set_state"):
            noodles.execute_handoff(self.root, self.SUBJECT, 44, pr)
        events = [json.loads(line) for line in events_path.read_text().splitlines()]
        self.assertEqual(sum(item["type"] == "stage_message" for item in events), 1)

    def test_wrong_session_id_fails_before_emission(self) -> None:
        with mock.patch.dict(os.environ, {"NOODLE_SESSION_ID": "wrong-session"}, clear=False), \
             mock.patch.object(noodles, "issue_set_state") as set_state:
            with self.assertRaisesRegex(noodles.GateError, "session"):
                noodles.execute_handoff(self.root, self.SUBJECT, 44, self.pr())
        set_state.assert_not_called()

    def test_non_blocking_runtime_event_fails_direct_readback(self) -> None:
        self.temp.cleanup()
        self.temp, self.root, self.binary, self.session_id = handoff_fixture(CANDIDATE_ROOT, blocking=False)
        self.addCleanup(self.temp.cleanup)
        self.head = cmd(["git", "rev-parse", "HEAD"], self.root)
        with mock.patch.dict(os.environ, {"NOODLE_SESSION_ID": self.session_id}, clear=False), \
             mock.patch.object(noodles, "issue_set_state"):
            with self.assertRaisesRegex(noodles.GateError, "blocking"):
                noodles.execute_handoff(self.root, self.SUBJECT, 44, self.pr())

    def test_wrong_pr_body_or_head_fails_closed(self) -> None:
        with mock.patch.dict(os.environ, {"NOODLE_SESSION_ID": self.session_id}, clear=False), \
             mock.patch.object(noodles, "issue_set_state"):
            with self.assertRaises(noodles.GateError):
                noodles.execute_handoff(self.root, self.SUBJECT, 44, self.pr(body="Claim\nRefs ed3c/noodles#33"))
            with self.assertRaisesRegex(noodles.GateError, "head"):
                noodles.execute_handoff(self.root, self.SUBJECT, 44, self.pr(head={"sha": "f" * 40}))

    def test_missing_pr_fails_before_issue_or_session_mutation(self) -> None:
        with mock.patch.object(noodles, "gh_api", side_effect=noodles.GateError("missing PR")), \
             mock.patch.object(noodles, "issue_set_state") as set_state:
            self.assertEqual(noodles.main(["--root", str(self.root), "issue", "handoff", self.SUBJECT, "--pr", "404"]), 1)
        set_state.assert_not_called()


class ReconcileTests(unittest.TestCase):
    def test_provider_landed_sends_exact_merge_control_and_accepts_status_ack(self) -> None:
        calls: list[tuple[str, object]] = []

        def fake_http(url: str, *, payload: object | None = None) -> dict:
            calls.append((url, payload))
            if payload is None:
                return {"pending_reviews": [{"order_id": "ed3c/noodles#33"}]}
            return {"id": payload["id"], "action": "merge", "status": "ok"}

        with mock.patch.object(noodles, "http_json", side_effect=fake_http), \
             mock.patch.object(noodles, "provider_landed", return_value=(44, "a" * 40, "b" * 40)), \
             mock.patch.object(noodles, "git", return_value=""):
            completed = noodles.reconcile_once(CANDIDATE_ROOT, "http://noodle.test")

        self.assertEqual(completed, ["ed3c/noodles#33"])
        self.assertEqual(calls[1][1]["action"], "merge")
        self.assertEqual(calls[1][1]["order_id"], "ed3c/noodles#33")

    def test_machine_merge_rejects_control_ack_drift(self) -> None:
        responses = [
            {"pending_reviews": [{"order_id": "ed3c/noodles#33"}]},
            {"id": "wrong", "action": "merge", "status": "ok"},
        ]
        with mock.patch.object(noodles, "http_json", side_effect=responses), \
             mock.patch.object(noodles, "provider_landed", return_value=(44, "a" * 40, "b" * 40)), \
             mock.patch.object(noodles, "git", return_value=""):
            with self.assertRaisesRegex(noodles.GateError, "rejected machine reconciliation"):
                noodles.reconcile_once(CANDIDATE_ROOT, "http://noodle.test")

    def test_preland_reconcile_sends_no_control(self) -> None:
        calls: list[tuple[str, object]] = []

        def fake_http(url: str, *, payload: object | None = None) -> dict:
            calls.append((url, payload))
            return {"pending_reviews": [{"order_id": "ed3c/noodles#33"}]}

        with mock.patch.object(noodles, "http_json", side_effect=fake_http), \
             mock.patch.object(noodles, "provider_landed", side_effect=noodles.GateError("not landed")):
            completed = noodles.reconcile_once(CANDIDATE_ROOT, "http://noodle.test")

        self.assertEqual(completed, [])
        self.assertEqual(calls, [("http://noodle.test/api/snapshot", None)])


class StartUnattendedTests(unittest.TestCase):
    def test_wrapper_polls_reconcile_and_sleeps_before_clean_exit(self) -> None:
        process = mock.Mock(returncode=0)
        process.poll.side_effect = [None, 0, 0]
        policy = {
            "repository": "ed3c/noodles",
            "default_branch": "main",
            "required_check": "verify",
        }

        with mock.patch.object(noodles, "verify_repository", return_value={"ok": True, "errors": []}), \
             mock.patch.object(noodles, "runtime_check", return_value={"binary_path": "/tmp/noodle"}), \
             mock.patch.object(noodles, "provider_sync"), \
             mock.patch.object(noodles, "skill_discovery_check"), \
             mock.patch.object(noodles, "protection_policy", return_value=policy), \
             mock.patch.object(noodles, "protection_readback"), \
             mock.patch.object(noodles.subprocess, "Popen", return_value=process), \
             mock.patch.object(noodles, "reconcile_once") as reconcile, \
             mock.patch.object(time, "sleep") as sleep:
            result = noodles.start_unattended(CANDIDATE_ROOT, "http://noodle.test", 0.25)

        self.assertEqual(result, 0)
        reconcile.assert_called_once_with(CANDIDATE_ROOT, "http://noodle.test")
        sleep.assert_called_once_with(0.25)
        process.terminate.assert_not_called()


class ProviderPhysicalTests(unittest.TestCase):
    def test_exact_detached_checkout_and_readback(self) -> None:
        temp, candidate = provider_fixture()
        self.addCleanup(temp.cleanup)
        old = os.environ.get("NOODLES_TEST_ALLOW_LOCAL_PROVIDER")
        os.environ["NOODLES_TEST_ALLOW_LOCAL_PROVIDER"] = "1"
        try:
            receipts = noodles.provider_sync(candidate)
            self.assertEqual(receipts[0]["commit"], json.loads((candidate / "policy/providers.lock.json").read_text())["providers"][0]["commit"])
            self.assertEqual(receipts[0]["skill_count"], 1)
            self.assertEqual(receipts[0]["skill_path"], "skills/engineering")
            self.assertEqual(receipts[0]["license_path"], "LICENSE")
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
        temp, candidate = provider_fixture(subpath="skills/missing")
        self.addCleanup(temp.cleanup)
        with mock.patch.dict(os.environ, {"NOODLES_TEST_ALLOW_LOCAL_PROVIDER": "1"}, clear=False):
            with self.assertRaisesRegex(noodles.GateError, "has no SKILL.md"):
                noodles.provider_sync(candidate)

    def test_provider_check_rejects_missing_locked_license_path(self) -> None:
        temp, candidate = provider_fixture(license_path="NOTICE")
        self.addCleanup(temp.cleanup)
        with mock.patch.dict(os.environ, {"NOODLES_TEST_ALLOW_LOCAL_PROVIDER": "1"}, clear=False):
            with self.assertRaisesRegex(noodles.GateError, "license path missing"):
                noodles.provider_sync(candidate)


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
        project_skill = (candidate / ".agents/skills/execute").resolve()
        cursor_skill = (candidate / ".noodle/providers/cursor-pstack/pstack/skills/architect").resolve()
        matt_skill = (candidate / ".noodle/providers/matt-engineering/skills/engineering/ask-matt").resolve()
        cursor_skill.mkdir(parents=True)
        matt_skill.mkdir(parents=True)
        (cursor_skill / "SKILL.md").write_text("# Architect\n")
        (matt_skill / "SKILL.md").write_text("# Ask Matt\n")
        output = (
            f"execute\t{project_skill.parent}\ttrue\t{project_skill / 'SKILL.md'}\n"
            f"architect\t{cursor_skill.parent}\ttrue\t{cursor_skill / 'SKILL.md'}\n"
            f"ask-matt\t{matt_skill.parent}\ttrue\t{matt_skill / 'SKILL.md'}\n"
        )
        with mock.patch.dict(os.environ, {"NOODLES_TEST_SKILLS_OUTPUT": output}, clear=False):
            receipt = runtime_contract.skill_discovery_check(candidate, binary, error_cls=noodles.GateError)
        self.assertEqual(receipt["total_skills"], 3)
        self.assertEqual(receipt["skills_by_path"][str(project_skill.parent)], 1)
        self.assertTrue((candidate / ".noodle/receipts/runtime/skills.json").exists())

    def test_skill_discovery_rejects_missing_configured_path(self) -> None:
        temp, candidate, binary, _platform_key = self.runtime_candidate()
        self.addCleanup(temp.cleanup)
        project_skill = (candidate / ".agents/skills/execute").resolve()
        output = f"execute\t{project_skill.parent}\ttrue\t{project_skill / 'SKILL.md'}\n"
        with mock.patch.dict(os.environ, {"NOODLES_TEST_SKILLS_OUTPUT": output}, clear=False):
            with self.assertRaisesRegex(noodles.GateError, "missing configured paths"):
                runtime_contract.skill_discovery_check(candidate, binary, error_cls=noodles.GateError)


if __name__ == "__main__":
    unittest.main()

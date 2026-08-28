from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import noodles

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
        self.assertEqual(noodles.parse_pr_reference("Claim\nRefs ed3c/noodles#7\n"), "ed3c/noodles#7")
        with self.assertRaises(noodles.GateError):
            noodles.parse_pr_reference("Refs ed3c/noodles#7\nRefs ed3c/noodles#8\n")
        with self.assertRaises(noodles.GateError):
            noodles.parse_pr_reference("Closes #7\nRefs ed3c/noodles#7\n")

    def test_state_marker_replacement_is_single(self) -> None:
        changed = noodles.replace_marker(self.BODY, "state", "awaiting_land")
        self.assertEqual(noodles.parse_issue_contract(changed)["state"], "awaiting_land")


class ProviderPhysicalTests(unittest.TestCase):
    def test_exact_detached_checkout_and_readback(self) -> None:
        with tempfile.TemporaryDirectory(prefix="noodles-provider-test-") as temp_name:
            temp = Path(temp_name)
            candidate = temp / "candidate"
            copy_tracked(CANDIDATE_ROOT, candidate)
            source = temp / "source"
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
                    "subpath": "skills/engineering",
                    "destination": ".noodle/providers/fixture",
                    "license_path": "LICENSE",
                    "enabled": True,
                    "authority": "P"
                }
            ]
            lock_path.write_text(json.dumps(lock))
            old = os.environ.get("NOODLES_TEST_ALLOW_LOCAL_PROVIDER")
            os.environ["NOODLES_TEST_ALLOW_LOCAL_PROVIDER"] = "1"
            try:
                receipts = noodles.provider_sync(candidate)
                self.assertEqual(receipts[0]["commit"], commit)
                self.assertEqual(receipts[0]["skill_count"], 1)
                self.assertEqual(noodles.provider_check(candidate)[0]["commit"], commit)
                (candidate / ".noodle/providers/fixture/LICENSE").write_text("tampered\n")
                with self.assertRaises(noodles.GateError):
                    noodles.provider_check(candidate)
            finally:
                if old is None:
                    os.environ.pop("NOODLES_TEST_ALLOW_LOCAL_PROVIDER", None)
                else:
                    os.environ["NOODLES_TEST_ALLOW_LOCAL_PROVIDER"] = old


if __name__ == "__main__":
    unittest.main()

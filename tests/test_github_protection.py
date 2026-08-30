from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import github_protection
import noodles
from tests.support import CANDIDATE_ROOT

ENGINE_ROOT = Path(noodles.__file__).resolve().parent


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


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probe_script(argv: list[str]) -> str:
    return (
        "import json\n"
        "import os\n"
        "import shutil\n"
        "import subprocess\n"
        f"argv = {argv!r}\n"
        "result = subprocess.run(['gh', *argv], text=True, capture_output=True, check=False)\n"
        "payload = {\n"
        "    'gh': {\n"
        "        'returncode': result.returncode,\n"
        "        'stdout': result.stdout,\n"
        "        'stderr': result.stderr,\n"
        "    },\n"
        "    'gh_path': shutil.which('gh'),\n"
        "    'env': {\n"
        "        'GH_TOKEN': os.environ.get('GH_TOKEN'),\n"
        "        'GITHUB_TOKEN': os.environ.get('GITHUB_TOKEN'),\n"
        "        'HOME': os.environ.get('HOME'),\n"
        "        'XDG_CONFIG_HOME': os.environ.get('XDG_CONFIG_HOME'),\n"
        "        'XDG_CACHE_HOME': os.environ.get('XDG_CACHE_HOME'),\n"
        "        'GH_CONFIG_DIR': os.environ.get('GH_CONFIG_DIR'),\n"
        "        'PATH': os.environ.get('PATH'),\n"
        "    },\n"
        "}\n"
        "print(json.dumps(payload, sort_keys=True))\n"
        "raise SystemExit(0 if result.returncode == 0 else result.returncode)\n"
    )


class ProtectionContractTests(unittest.TestCase):
    def real_gh_path(self) -> Path:
        gh_path = shutil.which("gh")
        self.assertIsNotNone(gh_path)
        return Path(str(gh_path)).resolve()
    def workflow_boundary(self, mutate) -> tuple[list[str], dict]:
        with tempfile.TemporaryDirectory(prefix="noodles-gh-protect-") as temp_name:
            root = Path(temp_name)
            workflow_dir = root / ".github/workflows"
            workflow_dir.mkdir(parents=True)
            verify_path = workflow_dir / "verify.yml"
            land_path = workflow_dir / "land.yml"
            shutil.copy2(ENGINE_ROOT / ".github/workflows/verify.yml", verify_path)
            shutil.copy2(ENGINE_ROOT / ".github/workflows/land.yml", land_path)
            mutate(verify_path, land_path)
            return github_protection.workflow_boundary_readback(root, sha256_file)

    def assert_model_eval_rejected_before_spawn(
        self,
        command: list[str],
        *,
        required_tools: list[str] | None = None,
        pattern: str,
        error_cls: type[Exception] = AssertionError,
    ) -> None:
        with mock.patch.object(github_protection.subprocess, "run", side_effect=RuntimeError("unexpected spawn")) as run_mock:
            with self.assertRaisesRegex(error_cls, pattern):
                github_protection.run_bounded_gh_admission_eval(
                    CANDIDATE_ROOT,
                    command,
                    required_tools=required_tools or [],
                    error_cls=error_cls,
                )
        run_mock.assert_not_called()

    def test_required_separate_token_cannot_fallback(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"NOODLES_REQUIRE_PROTECTION_READ_TOKEN": "1", "NOODLES_GITHUB_PROTECTION_TOKEN": "", "GH_TOKEN": "default"},
            clear=False,
        ):
            with self.assertRaisesRegex(noodles.GateError, "NOODLES_GITHUB_PROTECTION_TOKEN is missing"):
                github_protection.protection_token_boundary(noodles.GateError)

    def test_protection_read_token_must_differ_from_gh_token(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "NOODLES_REQUIRE_PROTECTION_READ_TOKEN": "1",
                "NOODLES_GITHUB_PROTECTION_TOKEN": "shared",
                "GH_TOKEN": "shared",
            },
            clear=False,
        ):
            with self.assertRaisesRegex(noodles.GateError, "must be separate from GH_TOKEN"):
                github_protection.protection_token_boundary(noodles.GateError)

    def test_protection_audit_emits_digest_and_token_boundary(self) -> None:
        headers = {
            "etag": "W/\"etag\"",
            "x-github-request-id": "REQ123",
            "x-accepted-github-permissions": "administration=read",
            "x-accepted-oauth-scopes": "",
            "x-oauth-scopes": "",
        }

        def fake_gh_api_response(endpoint: str, **kwargs: object) -> tuple[dict[str, str], dict]:
            self.assertEqual(endpoint, "repos/ed3c/noodles/branches/main/protection")
            self.assertEqual(kwargs["token"], "app-token")
            self.assertTrue(kwargs["include_headers"])
            return headers, protection_fixture()

        with mock.patch.dict(
            os.environ,
            {
                "NOODLES_REQUIRE_PROTECTION_READ_TOKEN": "1",
                "NOODLES_GITHUB_PROTECTION_TOKEN": "app-token",
                "GH_TOKEN": "default-token",
            },
            clear=False,
        ):
            audit = github_protection.protection_audit(
                fake_gh_api_response,
                noodles.GateError,
                "ed3c/noodles",
                "main",
                "verify",
            )
        expected_digest = hashlib.sha256(
            json.dumps(protection_fixture(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        self.assertEqual(audit["provider_response"]["sha256"], expected_digest)
        self.assertEqual(audit["token_boundary"]["source"], "NOODLES_GITHUB_PROTECTION_TOKEN")
        self.assertTrue(audit["token_boundary"]["separate_from_gh_token"])
        self.assertEqual(audit["provider_response"]["accepted_github_permissions"], "administration=read")

    def test_workflow_boundary_rejects_candidate_secret_exposure(self) -> None:
        def mutate(verify_path: Path, _land_path: Path) -> None:
            verify_path.write_text(
                verify_path.read_text(encoding="utf-8").replace(
                    "      contents: read\n",
                    "      contents: read\n      issues: write\n      env:\n        GH_TOKEN: ${{ github.token }}\n",
                    1,
                ),
                encoding="utf-8",
            )
        errors, evidence = self.workflow_boundary(mutate)
        self.assertIn("candidate-self-tests job permissions must stay contents: read", errors)
        self.assertTrue(evidence["candidate_self_tests_secret_free"])
    def test_workflow_boundary_rejects_phrase_moved_to_comment(self) -> None:
        def mutate(verify_path: Path, _land_path: Path) -> None:
            verify_path.write_text(
                verify_path.read_text(encoding="utf-8").replace(
                    "          persist-credentials: false\n",
                    "          # persist-credentials: false\n",
                    1,
                ),
                encoding="utf-8",
            )
        errors, _evidence = self.workflow_boundary(mutate)
        self.assertIn("candidate-self-tests checkout must disable persisted credentials", errors)
    def test_workflow_boundary_rejects_phrase_moved_to_unrelated_job(self) -> None:
        def mutate(verify_path: Path, _land_path: Path) -> None:
            workflow = verify_path.read_text(encoding="utf-8")
            workflow = workflow.replace(
                '          python3 .trusted/noodles.py github verify-pr\n          --event "$GITHUB_EVENT_PATH"\n          --candidate "$GITHUB_WORKSPACE/.candidate"\n          --receipt "$GITHUB_WORKSPACE/noodles-receipt.json"\n',
                "          echo drift\n",
                1,
            )
            workflow += (
                "\n  shadow:\n"
                "    runs-on: ubuntu-latest\n"
                "    steps:\n"
                "      - name: Detached trusted receipt phrase\n"
                "        run: >-\n"
                "          python3 .trusted/noodles.py github verify-pr\n"
                "          --event \"$GITHUB_EVENT_PATH\"\n"
                "          --candidate \"$GITHUB_WORKSPACE/.candidate\"\n"
                "          --receipt \"$GITHUB_WORKSPACE/noodles-receipt.json\"\n"
            )
            verify_path.write_text(workflow, encoding="utf-8")
        errors, _evidence = self.workflow_boundary(mutate)
        self.assertIn("trusted verify receipt step must execute noodles.py github verify-pr against the exact candidate checkout", errors)
    def test_workflow_boundary_rejects_disabled_required_step(self) -> None:
        def mutate(verify_path: Path, _land_path: Path) -> None:
            verify_path.write_text(
                verify_path.read_text(encoding="utf-8").replace(
                    "      - name: Produce exact-head trusted receipt\n",
                    "      - name: Produce exact-head trusted receipt\n        if: ${{ false }}\n",
                    1,
                ),
                encoding="utf-8",
            )
        errors, _evidence = self.workflow_boundary(mutate)
        self.assertIn("trusted verify exact-head receipt step must stay enabled", errors)
    def test_workflow_boundary_rejects_wrong_permission_scope_with_phrase_preserved(self) -> None:
        def mutate(_verify_path: Path, land_path: Path) -> None:
            workflow = land_path.read_text(encoding="utf-8")
            workflow = workflow.replace("          permission-administration: read\n", "          permission-administration: write\n", 1)
            workflow = workflow.replace("    runs-on: ubuntu-latest\n", "    runs-on: ubuntu-latest\n    env:\n      permission-administration: read\n", 1)
            land_path.write_text(workflow, encoding="utf-8")
        errors, _evidence = self.workflow_boundary(mutate)
        self.assertIn("land workflow app token must be scoped to Administration: read", errors)

    def test_workflow_boundary_rejects_missing_repo_scope(self) -> None:
        def mutate(_verify_path: Path, land_path: Path) -> None:
            land_path.write_text(
                land_path.read_text(encoding="utf-8").replace(
                    "          repositories: ${{ github.event.repository.name }}\n",
                    "",
                    1,
                ),
                encoding="utf-8",
            )
        errors, evidence = self.workflow_boundary(mutate)
        self.assertIn("land workflow app token must be scoped to the current repository", errors)
        self.assertTrue(evidence["candidate_self_tests_secret_free"])

    def test_workflow_run_readback_rejects_subject_drift(self) -> None:
        def fake_gh_api(_endpoint: str) -> dict:
            return {"id": 7}

        with self.assertRaisesRegex(noodles.GateError, "workflow run readback failed"):
            github_protection.workflow_run_readback(fake_gh_api, noodles.GateError, "ed3c/noodles", 9)

    def test_failed_required_workflow_run_readback_selects_latest_failed_run(self) -> None:
        head = "a" * 40
        payloads = {
            f"repos/ed3c/noodles/actions/runs?head_sha={head}&per_page=100": {
                "workflow_runs": [
                    {
                        "id": 7,
                        "name": "verify",
                        "path": ".github/workflows/verify.yml",
                        "event": "pull_request_target",
                        "status": "completed",
                        "conclusion": "failure",
                        "head_sha": head,
                        "workflow_id": 11,
                        "run_attempt": 1,
                        "pull_requests": [{"number": 44}],
                    },
                    {
                        "id": 9,
                        "name": "verify",
                        "path": ".github/workflows/verify.yml",
                        "event": "pull_request_target",
                        "status": "completed",
                        "conclusion": "failure",
                        "head_sha": head,
                        "workflow_id": 11,
                        "run_attempt": 1,
                        "pull_requests": [{"number": 44}],
                    },
                ]
            },
            "repos/ed3c/noodles/actions/runs/9": {
                "id": 9,
                "name": "verify",
                "path": ".github/workflows/verify.yml",
                "event": "pull_request_target",
                "status": "completed",
                "conclusion": "failure",
                "head_sha": head,
                "workflow_id": 11,
                "run_attempt": 1,
                "pull_requests": [{"number": 44}],
            },
            "repos/ed3c/noodles": {
                "full_name": "ed3c/noodles",
                "default_branch": "main",
            },
            "repos/ed3c/noodles/actions/workflows/verify.yml": {
                "id": 11,
                "name": "verify",
                "path": ".github/workflows/verify.yml",
                "state": "active",
            },
        }

        source = github_protection.failed_required_workflow_run_readback(
            lambda endpoint: payloads[endpoint],
            noodles.GateError,
            "ed3c/noodles",
            head,
            name="verify",
            path=".github/workflows/verify.yml",
            event="pull_request_target",
            default_branch="main",
            pr_number=44,
        )

        self.assertEqual(source["run"]["id"], 9)
        self.assertEqual(source["run"]["conclusion"], "failure")
        self.assertEqual(source["run"]["run_attempt"], 1)
        self.assertEqual(source["run"]["pull_request_numbers"], [44])
        with self.assertRaisesRegex(noodles.GateError, "no completed failed workflow run"):
            github_protection.failed_required_workflow_run_readback(
                lambda endpoint: payloads[endpoint],
                noodles.GateError,
                "ed3c/noodles",
                head,
                name="verify",
                path=".github/workflows/verify.yml",
                event="pull_request_target",
                default_branch="main",
                pr_number=45,
            )

    def test_failed_required_workflow_run_readback_rejects_direct_head_drift(self) -> None:
        head = "a" * 40
        drifted = "b" * 40
        payloads = {
            f"repos/ed3c/noodles/actions/runs?head_sha={head}&per_page=100": {
                "workflow_runs": [{
                    "id": 9,
                    "name": "verify",
                    "path": ".github/workflows/verify.yml",
                    "event": "pull_request_target",
                    "status": "completed",
                    "conclusion": "failure",
                    "head_sha": head,
                    "workflow_id": 11,
                    "run_attempt": 1,
                    "pull_requests": [{"number": 44}],
                }]
            },
            "repos/ed3c/noodles/actions/runs/9": {
                "id": 9,
                "name": "verify",
                "path": ".github/workflows/verify.yml",
                "event": "pull_request_target",
                "status": "completed",
                "conclusion": "failure",
                "head_sha": drifted,
                "workflow_id": 11,
                "run_attempt": 1,
                "pull_requests": [{"number": 44}],
            },
            "repos/ed3c/noodles": {"full_name": "ed3c/noodles", "default_branch": "main"},
            "repos/ed3c/noodles/actions/workflows/verify.yml": {
                "id": 11,
                "name": "verify",
                "path": ".github/workflows/verify.yml",
                "state": "active",
            },
        }

        with self.assertRaisesRegex(noodles.GateError, "head"):
            github_protection.failed_required_workflow_run_readback(
                lambda endpoint: payloads[endpoint],
                noodles.GateError,
                "ed3c/noodles",
                head,
                name="verify",
                path=".github/workflows/verify.yml",
                event="pull_request_target",
                default_branch="main",
            )

    def test_failed_workflow_job_readback_rejects_missing_failure(self) -> None:
        def fake_gh_api(_endpoint: str) -> dict:
            return {
                "jobs": [
                    {"id": 1, "name": "candidate-self-tests", "status": "completed", "conclusion": "success"},
                    {"id": 2, "name": "verify", "status": "completed", "conclusion": "skipped"},
                ]
            }

        with self.assertRaisesRegex(noodles.GateError, "no completed failed jobs"):
            github_protection.failed_workflow_job_readback(fake_gh_api, noodles.GateError, "ed3c/noodles", 7)

    def test_pull_request_target_source_accepts_candidate_head_branch(self) -> None:
        payloads = {
            "repos/ed3c/noodles/actions/runs/33234782723": {
                "id": 33234782723,
                "name": "verify",
                "path": ".github/workflows/verify.yml",
                "event": "pull_request_target",
                "head_branch": "ed3c-noodles-3-0-task",
                "head_sha": "6c7a4d70d676f5da4acc72a3b90cdac043716e31",
                "workflow_id": 344826945,
                "run_attempt": 1,
                "pull_requests": [{"number": 3}],
            },
            "repos/ed3c/noodles": {
                "full_name": "ed3c/noodles",
                "default_branch": "main",
            },
            "repos/ed3c/noodles/actions/workflows/verify.yml": {
                "id": 344826945,
                "name": "verify",
                "path": ".github/workflows/verify.yml",
                "state": "active",
            },
        }

        source = github_protection.trusted_workflow_run_readback(
            lambda endpoint: payloads[endpoint],
            noodles.GateError,
            "ed3c/noodles",
            33234782723,
            name="verify",
            path=".github/workflows/verify.yml",
            event="pull_request_target",
            default_branch="main",
        )

        self.assertEqual(source["run"]["head_branch"], "ed3c-noodles-3-0-task")
        self.assertEqual(source["workflow"]["id"], 344826945)
        self.assertEqual(source["provider_default_branch"], "main")

    def test_trusted_workflow_source_rejects_wrong_event(self) -> None:
        def fake_gh_api(endpoint: str) -> dict:
            if endpoint.endswith("/actions/runs/7"):
                return {
                    "id": 7,
                    "name": "verify",
                    "path": ".github/workflows/verify.yml",
                    "event": "pull_request",
                    "workflow_id": 11,
                    "run_attempt": 1,
                    "pull_requests": [{"number": 44}],
                }
            if endpoint == "repos/ed3c/noodles":
                return {"full_name": "ed3c/noodles", "default_branch": "main"}
            return {"id": 11, "name": "verify", "path": ".github/workflows/verify.yml", "state": "active"}

        with self.assertRaisesRegex(noodles.GateError, "event must be pull_request_target"):
            github_protection.trusted_workflow_run_readback(
                fake_gh_api,
                noodles.GateError,
                "ed3c/noodles",
                7,
                name="verify",
                path=".github/workflows/verify.yml",
                event="pull_request_target",
                default_branch="main",
            )

    def test_trusted_workflow_source_rejects_wrong_run_path(self) -> None:
        def fake_gh_api(endpoint: str) -> dict:
            if endpoint.endswith("/actions/runs/7"):
                return {
                    "id": 7,
                    "name": "verify",
                    "path": ".github/workflows/candidate.yml",
                    "event": "pull_request_target",
                    "workflow_id": 11,
                    "run_attempt": 1,
                    "pull_requests": [{"number": 44}],
                }
            if endpoint == "repos/ed3c/noodles":
                return {"full_name": "ed3c/noodles", "default_branch": "main"}
            return {"id": 11, "name": "verify", "path": ".github/workflows/verify.yml", "state": "active"}

        with self.assertRaisesRegex(noodles.GateError, "workflow run identity mismatch"):
            github_protection.trusted_workflow_run_readback(
                fake_gh_api,
                noodles.GateError,
                "ed3c/noodles",
                7,
                name="verify",
                path=".github/workflows/verify.yml",
                event="pull_request_target",
                default_branch="main",
            )

    def test_trusted_workflow_source_rejects_wrong_immutable_id(self) -> None:
        def fake_gh_api(endpoint: str) -> dict:
            if endpoint.endswith("/actions/runs/7"):
                return {
                    "id": 7,
                    "name": "verify",
                    "path": ".github/workflows/verify.yml",
                    "event": "pull_request_target",
                    "workflow_id": 99,
                    "run_attempt": 1,
                    "pull_requests": [{"number": 44}],
                }
            if endpoint == "repos/ed3c/noodles":
                return {"full_name": "ed3c/noodles", "default_branch": "main"}
            return {"id": 11, "name": "verify", "path": ".github/workflows/verify.yml", "state": "active"}

        with self.assertRaisesRegex(noodles.GateError, "immutable workflow id mismatch"):
            github_protection.trusted_workflow_run_readback(
                fake_gh_api,
                noodles.GateError,
                "ed3c/noodles",
                7,
                name="verify",
                path=".github/workflows/verify.yml",
                event="pull_request_target",
                default_branch="main",
            )

    def test_trusted_workflow_source_rejects_provider_default_branch_drift(self) -> None:
        def fake_gh_api(endpoint: str) -> dict:
            if endpoint.endswith("/actions/runs/7"):
                return {
                    "id": 7,
                    "name": "verify",
                    "path": ".github/workflows/verify.yml",
                    "event": "pull_request_target",
                    "workflow_id": 11,
                    "run_attempt": 1,
                    "pull_requests": [{"number": 44}],
                }
            if endpoint == "repos/ed3c/noodles":
                return {"full_name": "ed3c/noodles", "default_branch": "candidate"}
            return {"id": 11, "name": "verify", "path": ".github/workflows/verify.yml", "state": "active"}

        with self.assertRaisesRegex(noodles.GateError, "provider default branch identity mismatch"):
            github_protection.trusted_workflow_run_readback(
                fake_gh_api,
                noodles.GateError,
                "ed3c/noodles",
                7,
                name="verify",
                path=".github/workflows/verify.yml",
                event="pull_request_target",
                default_branch="main",
            )

    def test_trusted_workflow_source_rejects_wrong_provider_workflow_identity(self) -> None:
        def fake_gh_api(endpoint: str) -> dict:
            if endpoint.endswith("/actions/runs/7"):
                return {
                    "id": 7,
                    "name": "verify",
                    "path": ".github/workflows/verify.yml",
                    "event": "pull_request_target",
                    "workflow_id": 11,
                    "run_attempt": 1,
                    "pull_requests": [{"number": 44}],
                }
            if endpoint == "repos/ed3c/noodles":
                return {"full_name": "ed3c/noodles", "default_branch": "main"}
            return {"id": 11, "name": "verify", "path": ".github/workflows/candidate.yml", "state": "active"}

        with self.assertRaisesRegex(noodles.GateError, "provider workflow identity mismatch"):
            github_protection.trusted_workflow_run_readback(
                fake_gh_api,
                noodles.GateError,
                "ed3c/noodles",
                7,
                name="verify",
                path=".github/workflows/verify.yml",
                event="pull_request_target",
                default_branch="main",
            )

    def run_model_eval_probe(self, gh_argv: list[str]) -> dict[str, object]:
        with mock.patch.dict(
            os.environ,
            {"GH_TOKEN": "parent-gh-token", "GITHUB_TOKEN": "parent-github-token"},
            clear=False,
        ):
            return github_protection.run_bounded_gh_admission_eval(
                CANDIDATE_ROOT,
                ["python3", "-c", probe_script(gh_argv)],
                required_tools=["python3"],
                error_cls=AssertionError,
            )

    def test_model_eval_positive_fixture_path_is_private_and_parent_surface_is_unchanged(self) -> None:
        receipt = self.run_model_eval_probe(list(github_protection.MODEL_EVAL_GH_FIXTURE_ARGV))
        self.assertEqual(receipt["child"]["returncode"], 0)
        self.assertTrue(receipt["parent_unchanged"])
        self.assertTrue(receipt["temp_root_removed"])
        self.assertEqual(
            receipt["parent_before"]["github_env"],
            {"GH_TOKEN": "parent-gh-token", "GITHUB_TOKEN": "parent-github-token"},
        )
        self.assertEqual(receipt["parent_before"], receipt["parent_after"])
        self.assertEqual(
            receipt["fixture_sha256"],
            hashlib.sha256(github_protection.MODEL_EVAL_GH_FIXTURE_BYTES).hexdigest(),
        )
        child = json.loads(receipt["child"]["stdout"])
        self.assertEqual(child["gh"]["returncode"], 0)
        self.assertEqual(json.loads(child["gh"]["stdout"]), github_protection.MODEL_EVAL_GH_ISSUE_FIXTURE)
        self.assertEqual(child["env"]["GH_TOKEN"], None)
        self.assertEqual(child["env"]["GITHUB_TOKEN"], None)
        self.assertEqual(child["gh_path"], os.path.join(receipt["child_surface"]["path_entries"][0], "gh"))
        self.assertEqual(child["env"]["HOME"], receipt["child_surface"]["HOME"])
        self.assertEqual(child["env"]["XDG_CONFIG_HOME"], receipt["child_surface"]["XDG_CONFIG_HOME"])
        self.assertEqual(child["env"]["XDG_CACHE_HOME"], receipt["child_surface"]["XDG_CACHE_HOME"])
        self.assertEqual(child["env"]["GH_CONFIG_DIR"], receipt["child_surface"]["GH_CONFIG_DIR"])
        self.assertEqual(child["env"]["PATH"], receipt["child_surface"]["PATH"])
        self.assertEqual(
            receipt["child_surface"]["github_env"],
            {key: None for key in github_protection.MODEL_EVAL_GITHUB_ENV_KEYS},
        )
        self.assertEqual(len(receipt["child_surface"]["path_entries"]), 2)

    def test_model_eval_direct_gh_fixture_command_preserves_frozen_shim_read_path(self) -> None:
        receipt = github_protection.run_bounded_gh_admission_eval(
            CANDIDATE_ROOT,
            ["gh", *github_protection.MODEL_EVAL_GH_FIXTURE_ARGV],
            error_cls=AssertionError,
        )
        self.assertEqual(receipt["command"][0], "gh")
        self.assertEqual(receipt["child"]["returncode"], 0)
        self.assertEqual(json.loads(receipt["child"]["stdout"]), github_protection.MODEL_EVAL_GH_ISSUE_FIXTURE)
        self.assertEqual(receipt["child_surface"]["path_entries"], [receipt["child_surface"]["path_entries"][0]])
        self.assertTrue(receipt["child_surface"]["path_entries"][0].endswith("/bin"))
        self.assertTrue(receipt["parent_unchanged"])
        self.assertTrue(receipt["temp_root_removed"])

    def test_model_eval_fixture_path_supports_non_python_carrier(self) -> None:
        with mock.patch.dict(os.environ, {"GH_TOKEN": "parent-gh-token"}, clear=False):
            receipt = github_protection.run_bounded_gh_admission_eval(
                CANDIDATE_ROOT,
                ["sh", "-c", "gh issue view 70 --repo ed3c/noodles --json body,number,state,title,url"],
                required_tools=["sh"],
                error_cls=AssertionError,
            )
        self.assertEqual(receipt["child"]["returncode"], 0)
        self.assertEqual(json.loads(receipt["child"]["stdout"]), github_protection.MODEL_EVAL_GH_ISSUE_FIXTURE)
        self.assertTrue(receipt["parent_unchanged"])
        self.assertTrue(receipt["temp_root_removed"])

    def test_model_eval_planted_negative_controls_fail_closed_before_real_gh_contact(self) -> None:
        cases = [
            (["api", "--method", "PATCH", "repos/ed3c/noodles/issues/70", "-f", "body=nope"], "gh eval shim denied gh api surface"),
            (["issue", "edit", "70", "--repo", "ed3c/noodles", "--title", "nope"], "gh eval shim denied gh issue mutation surface"),
            (["pr", "create", "--title", "nope", "--body", "nope"], "gh eval shim denied gh pr mutation surface"),
            (["pr", "merge", "1"], "gh eval shim denied gh pr mutation surface"),
            (["pr", "close", "1"], "gh eval shim denied gh pr mutation surface"),
            (["issue", "view", "70", "--repo", "ed3c/noodles", "--json", "body"], "gh eval shim denied unexpected gh issue view argv"),
            (["auth", "status"], "gh eval shim denied unexpected argv"),
        ]
        for argv, pattern in cases:
            with self.subTest(argv=argv):
                receipt = self.run_model_eval_probe(argv)
                self.assertNotEqual(receipt["child"]["returncode"], 0)
                child = json.loads(receipt["child"]["stdout"])
                self.assertNotEqual(child["gh"]["returncode"], 0)
                self.assertIn(pattern, child["gh"]["stderr"])
                self.assertTrue(receipt["parent_unchanged"])
                self.assertTrue(receipt["temp_root_removed"])

    def test_model_eval_direct_gh_api_is_rejected_before_subprocess_spawn(self) -> None:
        self.assert_model_eval_rejected_before_spawn(
            [
                "gh",
                "api",
                "--method",
                "PATCH",
                "repos/ed3c/noodles/issues/70",
                "-f",
                "body=nope",
            ],
            pattern="unsupported gh eval argv before subprocess spawn/provider contact",
        )

    def test_model_eval_rejects_tool_gh_before_subprocess_spawn(self) -> None:
        self.assert_model_eval_rejected_before_spawn(
            ["python3", "-c", "print('ok')"],
            required_tools=["gh"],
            pattern=r"unsupported real-gh executable route via --tool\[0\]: gh -> ",
        )

    def test_model_eval_rejects_real_gh_path_and_symlink_before_subprocess_spawn(self) -> None:
        real_gh = self.real_gh_path()
        self.assert_model_eval_rejected_before_spawn(
            [str(real_gh), "api", "--method", "PATCH", "repos/ed3c/noodles/issues/70"],
            pattern=f"unsupported real-gh executable route via child command\\[0\\]: {re.escape(str(real_gh))} -> {re.escape(str(real_gh))}",
        )
        with tempfile.TemporaryDirectory(prefix="noodles-gh-link-") as temp_name:
            symlink = Path(temp_name) / "gh-link"
            symlink.symlink_to(real_gh)
            self.assert_model_eval_rejected_before_spawn(
                [str(symlink), "api", "--method", "PATCH", "repos/ed3c/noodles/issues/70"],
                pattern=f"unsupported real-gh executable route via child command\\[0\\]: {re.escape(str(symlink))} -> {re.escape(str(real_gh))}",
            )

    def test_model_eval_cli_entrypoint_runs_same_boundary_contract(self) -> None:
        stdout = io.StringIO()
        with mock.patch.dict(os.environ, {"GH_TOKEN": "parent-gh-token"}, clear=False), \
             mock.patch("sys.stdout", stdout):
            result = noodles.main(
                [
                    "--root",
                    str(CANDIDATE_ROOT),
                    "eval",
                    "gh-boundary",
                    "--tool",
                    "python3",
                    "--",
                    "python3",
                    "-c",
                    probe_script(list(github_protection.MODEL_EVAL_GH_FIXTURE_ARGV)),
                ]
            )
        self.assertEqual(result, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["child"]["returncode"], 0)
        self.assertTrue(payload["parent_unchanged"])

    def test_model_eval_cli_entrypoint_rejects_direct_gh_api_before_spawn(self) -> None:
        stderr = io.StringIO()
        with mock.patch.object(github_protection.subprocess, "run", side_effect=RuntimeError("unexpected spawn")) as run_mock, \
             mock.patch("sys.stderr", stderr):
            result = noodles.main(
                [
                    "--root",
                    str(CANDIDATE_ROOT),
                    "eval",
                    "gh-boundary",
                    "--",
                    "gh",
                    "api",
                    "--method",
                    "PATCH",
                    "repos/ed3c/noodles/issues/70",
                    "-f",
                    "body=nope",
                ]
            )
        self.assertEqual(result, 1)
        self.assertIn("unsupported gh eval argv before subprocess spawn/provider contact", stderr.getvalue())
        run_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()

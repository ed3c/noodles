from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import github_protection
import noodles

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


class ProtectionContractTests(unittest.TestCase):
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
        with tempfile.TemporaryDirectory(prefix="noodles-gh-protect-") as temp_name:
            root = Path(temp_name)
            verify_dir = root / ".github/workflows"
            verify_dir.mkdir(parents=True)
            shutil.copy2(ENGINE_ROOT / ".github/workflows/verify.yml", verify_dir / "verify.yml")
            shutil.copy2(ENGINE_ROOT / ".github/workflows/land.yml", verify_dir / "land.yml")
            verify_path = verify_dir / "verify.yml"
            verify_path.write_text(
                verify_path.read_text(encoding="utf-8").replace(
                    "      contents: read\n",
                    "      contents: read\n      issues: write\n      env:\n        GH_TOKEN: ${{ github.token }}\n",
                    1,
                ),
                encoding="utf-8",
            )
            errors, evidence = github_protection.workflow_boundary_readback(root, sha256_file)
        self.assertTrue(any("candidate self-tests must not receive trusted token material: GH_TOKEN" in item for item in errors))
        self.assertFalse(evidence["candidate_self_tests_secret_free"])

    def test_workflow_boundary_rejects_missing_repo_scope(self) -> None:
        with tempfile.TemporaryDirectory(prefix="noodles-gh-protect-") as temp_name:
            root = Path(temp_name)
            verify_dir = root / ".github/workflows"
            verify_dir.mkdir(parents=True)
            shutil.copy2(ENGINE_ROOT / ".github/workflows/verify.yml", verify_dir / "verify.yml")
            shutil.copy2(ENGINE_ROOT / ".github/workflows/land.yml", verify_dir / "land.yml")
            land_path = verify_dir / "land.yml"
            land_path.write_text(
                land_path.read_text(encoding="utf-8").replace(
                    "          repositories: ${{ github.event.repository.name }}\n",
                    "",
                    1,
                ),
                encoding="utf-8",
            )
            errors, evidence = github_protection.workflow_boundary_readback(root, sha256_file)
        self.assertIn("land workflow app token must be scoped to the current repository", errors)
        self.assertTrue(evidence["candidate_self_tests_secret_free"])

    def test_workflow_run_readback_rejects_subject_drift(self) -> None:
        def fake_gh_api(_endpoint: str) -> dict:
            return {"id": 7}

        with self.assertRaisesRegex(noodles.GateError, "workflow run readback failed"):
            github_protection.workflow_run_readback(fake_gh_api, noodles.GateError, "ed3c/noodles", 9)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from pathlib import Path
import unittest


ENGINE_ROOT = Path(__file__).parents[1]
WORKFLOW = ENGINE_ROOT / ".github/workflows/land.yml"


class ProtectionApplyWorkflowTests(unittest.TestCase):
    def workflow(self) -> str:
        return WORKFLOW.read_text(encoding="utf-8")

    def test_trusted_issue_label_trigger_is_exactly_owner_issue_and_label_bound(self) -> None:
        workflow = self.workflow()
        self.assertIn("\n  issues:\n    types: [labeled]\n", workflow)
        self.assertEqual(workflow.count("\n  issues:\n"), 1)
        for required in (
            "github.actor == github.repository_owner",
            "github.event.issue.number == 389",
            "github.event.issue.state == 'open'",
            "github.event.label.name == 'protection-apply'",
        ):
            with self.subTest(required=required):
                self.assertIn(required, workflow)
        for forbidden in ("pull_request:", "pull_request_target:", "workflow_dispatch:"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, workflow)
        self.assertIn("\n  land:\n    if: ${{ github.event.workflow_run.conclusion == 'success' }}\n", workflow)
        self.assertIn("\n  protection-apply:\n    if: >-\n", workflow)

    def test_token_is_repository_scoped_admin_write_and_confined_to_apply_step(self) -> None:
        workflow = self.workflow()
        self.assertEqual(workflow.count("permission-administration: write"), 1)
        self.assertEqual(workflow.count("${{ steps.protection-token.outputs.token }}"), 1)
        self.assertIn("repositories: ${{ github.event.repository.name }}", workflow)
        self.assertEqual(workflow.count("\n    permissions:\n      contents: read\n"), 1)
        protection_job = workflow.split("\n  protection-apply:\n", 1)[1]
        for forbidden in ("contents: write", "issues: write", "pull-requests: write", "checks: write"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, protection_job)

    def test_apply_runs_only_trusted_default_branch_bytes_and_exact_command(self) -> None:
        workflow = self.workflow()
        protection_job = workflow.split("\n  protection-apply:\n", 1)[1]
        self.assertIn("ref: ${{ github.event.repository.default_branch }}", protection_job)
        self.assertIn("persist-credentials: false", protection_job)
        self.assertEqual(
            protection_job.count('run: python3 noodles.py github protect apply --repository "$GITHUB_REPOSITORY"'),
            1,
        )
        self.assertNotIn("NOODLES_GITHUB_PROTECTION_TOKEN", protection_job)


if __name__ == "__main__":
    unittest.main()

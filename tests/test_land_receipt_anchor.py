"""Land-time physical-receipt anchor: one idempotent N-class comment per merged PR.

The anchor's load-bearing values (merge commit SHA, merged-at) are provider truth the land path has
already read back, so the machine emits them one-per-land instead of a manual bulk backfill that trips
GitHub's secondary content-creation limit. These controls pin that the anchor is posted exactly once,
never duplicated, never emitted when the merge was refused, and never read by an admission path."""
from __future__ import annotations

import ast
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import noodles
from tests.support import CANDIDATE_ROOT

ENGINE_ROOT = Path(noodles.__file__).resolve().parent
ANCHOR_MARKER = "physical-receipt-anchor"
REPOSITORY = "ed3c/noodles"
PR_NUMBER = 4242
ISSUE_NUMBER = 900246
SUBJECT = f"{REPOSITORY}#{ISSUE_NUMBER}"
HEAD_SHA = "a" * 40
TREE_SHA = "b" * 40
MERGE_SHA = "c" * 40
MERGED_AT = "2026-08-31T04:05:06Z"


def issue_body(state: str = "awaiting_land") -> str:
    return (
        "<!-- noodles-role: repository-mutating-atom -->\n"
        f"<!-- noodles-target: {REPOSITORY} -->\n"
        f"<!-- noodles-subject: {SUBJECT} -->\n"
        f"<!-- noodles-state: {state} -->\n"
        "<!-- noodles-depends-on: none -->\n"
    )


class LandApi:
    """The provider surface land_pull_request actually calls, with the merge as real mutable state."""

    def __init__(self, *, merge_allowed: bool = True, merged_at: str | None = MERGED_AT, comments: list | None = None) -> None:
        self.merge_allowed = merge_allowed
        self.merged_at = merged_at
        self.comments = list(comments or [])
        self.posts: list[tuple[str, object]] = []
        self.merged = False
        self.issue = {"state": "open", "body": issue_body()}

    def pull(self) -> dict:
        return {
            "number": PR_NUMBER,
            "state": "closed" if self.merged else "open",
            "draft": False,
            "merged": self.merged,
            "merge_commit_sha": MERGE_SHA if self.merged else None,
            "merged_at": self.merged_at if self.merged else None,
            "body": f"Refs {SUBJECT}",
            "head": {"sha": HEAD_SHA},
            "base": {"ref": "main"},
        }

    def __call__(self, endpoint: str, *, method: str = "GET", payload: object | None = None, token: str | None = None) -> object:
        if endpoint == f"repos/{REPOSITORY}/pulls/{PR_NUMBER}/merge" and method == "PUT":
            if not self.merge_allowed:
                return {"merged": False, "message": "Head branch was modified. Review and try the merge again."}
            self.merged = True
            return {"merged": True, "sha": MERGE_SHA}
        if endpoint == f"repos/{REPOSITORY}/pulls/{PR_NUMBER}":
            return self.pull()
        if endpoint == f"repos/{REPOSITORY}/git/commits/{HEAD_SHA}":
            return {"tree": {"sha": TREE_SHA}}
        if endpoint == f"repos/{REPOSITORY}/git/commits/{MERGE_SHA}":
            return {"parents": [{"sha": HEAD_SHA}, {"sha": "d" * 40}]}
        if endpoint == f"repos/{REPOSITORY}/branches/main":
            return {"commit": {"sha": MERGE_SHA}}
        if endpoint == f"repos/{REPOSITORY}/issues/{PR_NUMBER}/comments?per_page=100":
            return list(self.comments)
        if endpoint == f"repos/{REPOSITORY}/issues/{PR_NUMBER}/comments" and method == "POST":
            self.posts.append((endpoint, payload))
            self.comments.append({"body": (payload or {}).get("body", "")})
            return {"id": 1}
        if endpoint == f"repos/{REPOSITORY}/issues/{ISSUE_NUMBER}":
            if method == "PATCH":
                self.issue.update(payload or {})
                return dict(self.issue)
            return dict(self.issue)
        raise AssertionError(f"unexpected gh api call: {method} {endpoint}")

    def anchors(self) -> list[str]:
        return [str((payload or {}).get("body", "")) for _endpoint, payload in self.posts]


class LandReceiptAnchorTests(unittest.TestCase):
    def land(self, api: LandApi) -> dict:
        with tempfile.TemporaryDirectory(prefix="noodles-land-anchor-") as name:
            work = Path(name)
            event_path = work / "event.json"
            receipt_path = work / "receipt.json"
            event_path.write_text(json.dumps({
                "repository": {"full_name": REPOSITORY},
                "workflow_run": {
                    "name": "verify",
                    "conclusion": "success",
                    "id": 777,
                    "head_sha": HEAD_SHA,
                    "pull_requests": [{"number": PR_NUMBER}],
                },
            }), encoding="utf-8")
            receipt_path.write_text(json.dumps({
                "repository": REPOSITORY,
                "pr_number": PR_NUMBER,
                "head_sha": HEAD_SHA,
                "tree_sha": TREE_SHA,
                "issue_subject": SUBJECT,
            }), encoding="utf-8")
            trusted = {"run": {"id": 777}, "workflow": {"path": ".github/workflows/verify.yml"}, "provider_default_branch": "main"}
            with (
                mock.patch.object(noodles, "gh_api", side_effect=api),
                mock.patch.object(noodles.github_protection, "trusted_workflow_run_readback", return_value=trusted),
                mock.patch.object(noodles.github_protection, "protection_audit", return_value={"required_check": "verify"}),
            ):
                return noodles.land_pull_request(ENGINE_ROOT, event_path, receipt_path)

    def test_land_posts_one_anchor_carrying_the_merge_readback_values(self) -> None:
        api = LandApi()
        result = self.land(api)
        self.assertEqual(result["merge_sha"], MERGE_SHA)
        self.assertTrue(result["issue_closed"])
        self.assertEqual(result["receipt_anchor"], "posted")
        self.assertEqual(
            api.anchors(),
            [f"physical-receipt-anchor: pr={PR_NUMBER} merge-commit={MERGE_SHA} merged-at={MERGED_AT}"],
        )

    def test_planted_pre_existing_anchor_produces_no_duplicate(self) -> None:
        # constraint: the backfill overlap and the workflow re-run look identical from here - an anchor
        # constraint: already on the PR, whatever posted it, must make the step a no-op.
        backfilled = f"physical-receipt-anchor: pr={PR_NUMBER} merge-commit={MERGE_SHA} merged-at={MERGED_AT} drive-index=https://example.invalid/index"
        api = LandApi(comments=[{"body": "unrelated review chatter"}, {"body": backfilled}])
        result = self.land(api)
        self.assertEqual(result["receipt_anchor"], "existing")
        self.assertEqual(api.anchors(), [])
        self.assertEqual([c["body"] for c in api.comments].count(backfilled), 1)

    def test_planted_negative_refused_merge_posts_no_anchor(self) -> None:
        api = LandApi(merge_allowed=False)
        with self.assertRaisesRegex(noodles.GateError, "GitHub merge failed"):
            self.land(api)
        self.assertEqual(api.anchors(), [])
        self.assertFalse(api.merged)
        self.assertEqual(api.issue["state"], "open")
        self.assertIn("<!-- noodles-state: awaiting_land -->", api.issue["body"])

    def test_planted_negative_merge_readback_without_a_timestamp_fails_before_any_anchor(self) -> None:
        api = LandApi(merged_at=None)
        with self.assertRaisesRegex(noodles.GateError, "no merged_at timestamp"):
            self.land(api)
        self.assertEqual(api.anchors(), [])

    def test_anchor_is_n_class_no_admission_path_reads_it(self) -> None:
        """Mechanical N-class proof, read off the exact candidate tree rather than the engine import."""
        tracked = subprocess.run(
            ["git", "ls-files", "-z"], cwd=str(CANDIDATE_ROOT), text=True, capture_output=True, check=False
        )
        self.assertEqual(tracked.returncode, 0, tracked.stderr)
        executable_hits = set()
        for relative in [entry for entry in tracked.stdout.split("\0") if entry]:
            if not (relative.endswith((".py", ".yml", ".yaml")) or relative == "noodles"):
                continue
            if ANCHOR_MARKER in (CANDIDATE_ROOT / relative).read_text(encoding="utf-8", errors="ignore"):
                executable_hits.add(relative)
        self.assertEqual(executable_hits, {"noodles.py", "tests/test_land_receipt_anchor.py"})

        source = (CANDIDATE_ROOT / "noodles.py").read_text(encoding="utf-8")
        self.assertEqual(source.count(ANCHOR_MARKER), 1, "the marker literal must live in exactly one constant")
        readers = {
            node.name
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.FunctionDef) and "RECEIPT_ANCHOR_PREFIX" in (ast.get_source_segment(source, node) or "")
        }
        self.assertEqual(readers, {"post_receipt_anchor"})


if __name__ == "__main__":
    unittest.main()

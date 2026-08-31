from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import github_protection
import noodles

ENGINE_ROOT = Path(noodles.__file__).resolve().parent
GIT_IDENTITY = ["-c", "user.name=noodles-test", "-c", "user.email=noodles-test@example.com", "-c", "commit.gpgsign=false"]
# constraint: immutable provider heads for the live control - ed3c/noodles#233 is the head whose trusted
# constraint: verify completed FAILURE (run 33379233268) and starved the queue; ed3c/noodles#244 is a head
# constraint: whose trusted verify completed SUCCESS (run 33382234390). Both runs are terminal, so neither
# constraint: conclusion can drift under the control.
LIVE_VERIFY_FAILURE_HEAD = "0ff2a643e5b2dcda18b83b9cc61adb8a5b191220"
LIVE_VERIFY_SUCCESS_HEAD = "3383626f1303abd05914026676ca7774de0e7452"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def issue_body(number: int, state: str = "awaiting_land") -> str:
    return (
        "<!-- noodles-role: repository-mutating-atom -->\n"
        "<!-- noodles-target: ed3c/noodles -->\n"
        f"<!-- noodles-subject: ed3c/noodles#{number} -->\n"
        f"<!-- noodles-state: {state} -->\n"
        "<!-- noodles-depends-on: none -->\n"
    )


def pr_fixture(number: int, subject_number: int, sha: str, ref: str, created_at: str, draft: bool = False) -> dict:
    return {
        "number": number,
        "state": "open",
        "draft": draft,
        "created_at": created_at,
        "body": f"Refs ed3c/noodles#{subject_number}",
        "base": {"ref": "main"},
        "head": {"ref": ref, "sha": sha, "repo": {"full_name": "ed3c/noodles"}},
    }


def seed_train_remote(base: Path, *, conflict: bool) -> dict[str, str]:
    """One landed sibling advanced main past the candidate branch; conflict=True makes both edit a.txt."""
    origin = base / "origin.git"
    noodles.run(["git", "init", "--bare", "--quiet", "--initial-branch", "main", str(origin)])
    seed = base / "seed"
    seed.mkdir()

    def g(*args: str) -> str:
        return noodles.run(["git", *GIT_IDENTITY, *args], cwd=seed).stdout.strip()

    noodles.run(["git", "init", "--quiet", "--initial-branch", "main"], cwd=seed)
    (seed / "a.txt").write_text("base\n", encoding="utf-8")
    g("add", ".")
    g("commit", "--quiet", "-m", "shared base")
    g("checkout", "--quiet", "-b", "candidate")
    if conflict:
        (seed / "a.txt").write_text("candidate\n", encoding="utf-8")
    else:
        (seed / "b.txt").write_text("candidate\n", encoding="utf-8")
    g("add", ".")
    g("commit", "--quiet", "-m", "candidate work")
    head_sha = g("rev-parse", "HEAD")
    g("checkout", "--quiet", "main")
    if conflict:
        (seed / "a.txt").write_text("landed\n", encoding="utf-8")
    else:
        (seed / "c.txt").write_text("landed\n", encoding="utf-8")
    g("add", ".")
    g("commit", "--quiet", "-m", "first sibling landed")
    main_sha = g("rev-parse", "HEAD")
    g("push", "--quiet", str(origin), "main", "candidate")
    return {"origin": str(origin), "head": head_sha, "main": main_sha}


def verify_run(sha: str, status: str, conclusion: str | None, *, run_id: int = 1) -> dict:
    # constraint: id/run_attempt/pull_requests are the fields `workflow_runs_for_head` (the shared,
    # constraint: already-owned runs-API normalizer) requires present before a run survives its filter.
    return {
        "id": run_id,
        "run_attempt": 1,
        "pull_requests": [],
        "name": "verify",
        "path": ".github/workflows/verify.yml",
        "event": "pull_request_target",
        "head_sha": sha,
        "status": status,
        "conclusion": conclusion,
    }


def train_api(
    pulls: list[dict],
    issues: dict[int, dict],
    behind: dict[str, int],
    comments: dict[int, list],
    posts: list,
    runs: dict[str, list] | None = None,
) -> object:
    def fake(endpoint: str, *, method: str = "GET", payload: object | None = None, token: str | None = None) -> object:
        if endpoint.startswith("repos/ed3c/noodles/pulls?"):
            return pulls
        if endpoint.startswith("repos/ed3c/noodles/actions/runs?head_sha="):
            sha = endpoint.split("head_sha=", 1)[1].split("&", 1)[0]
            return {"workflow_runs": (runs or {}).get(sha, [])}
        if endpoint.startswith("repos/ed3c/noodles/compare/main..."):
            return {"behind_by": behind[endpoint.rsplit("...", 1)[1]]}
        if endpoint.startswith("repos/ed3c/noodles/issues/") and endpoint.endswith("/comments?per_page=100"):
            return comments.get(int(endpoint.split("/")[4]), [])
        if method == "POST" and endpoint.endswith("/comments"):
            posts.append((endpoint, payload))
            return {"id": 1}
        if endpoint.startswith("repos/ed3c/noodles/issues/"):
            return issues[int(endpoint.rsplit("/", 1)[1])]
        raise AssertionError(f"unexpected gh api call: {method} {endpoint}")

    return fake


class LandingTrainSelectionTests(unittest.TestCase):
    def test_selects_oldest_eligible_pr_in_creation_order(self) -> None:
        sha_old = "a" * 40
        sha_new = "b" * 40
        sha_fresh = "c" * 40
        sha_draft = "d" * 40
        sha_ready = "e" * 40
        pulls = [
            pr_fixture(9, 909, sha_new, "newer", "2026-08-30T02:00:00Z"),
            pr_fixture(7, 707, sha_old, "older", "2026-08-30T01:00:00Z"),
            pr_fixture(3, 303, sha_fresh, "fresh", "2026-08-30T00:00:00Z"),
            pr_fixture(2, 202, sha_draft, "draft", "2026-08-29T00:00:00Z", draft=True),
            pr_fixture(5, 505, sha_ready, "ready", "2026-08-30T00:30:00Z"),
        ]
        issues = {
            909: {"state": "open", "body": issue_body(909)},
            707: {"state": "open", "body": issue_body(707)},
            303: {"state": "open", "body": issue_body(303)},
            505: {"state": "open", "body": issue_body(505, state="ready")},
        }
        behind = {sha_old: 1, sha_new: 1, sha_fresh: 0}
        with mock.patch.object(noodles, "gh_api", side_effect=train_api(pulls, issues, behind, {}, [])):
            selected = noodles.train_select("ed3c/noodles", "main", pulls, "verify")
        self.assertIsNotNone(selected)
        self.assertEqual(selected["number"], 7)

    def test_planted_negative_failed_back_head_is_not_reselected(self) -> None:
        sha_stuck = "a" * 40
        sha_next = "b" * 40
        pulls = [
            pr_fixture(4, 404, sha_stuck, "stuck", "2026-08-30T00:00:00Z"),
            pr_fixture(6, 606, sha_next, "next", "2026-08-30T01:00:00Z"),
        ]
        issues = {
            404: {"state": "open", "body": issue_body(404)},
            606: {"state": "open", "body": issue_body(606)},
        }
        behind = {sha_stuck: 1, sha_next: 1}
        comments = {4: [{"body": noodles.train_failback_marker(sha_stuck) + "\nLanding train fail-back"}]}
        with mock.patch.object(noodles, "gh_api", side_effect=train_api(pulls, issues, behind, comments, [])):
            selected = noodles.train_select("ed3c/noodles", "main", pulls, "verify")
        self.assertIsNotNone(selected)
        self.assertEqual(selected["number"], 6)

    def starving_queue(self, stuck_sha: str, runs: dict[str, list]) -> dict | None:
        """Queue shaped like the observed starvation: an older behind candidate ahead of a newer behind one."""
        sha_next = "b" * 40
        pulls = [
            pr_fixture(4, 404, stuck_sha, "stuck", "2026-08-30T00:00:00Z"),
            pr_fixture(6, 606, sha_next, "next", "2026-08-30T01:00:00Z"),
        ]
        issues = {
            404: {"state": "open", "body": issue_body(404)},
            606: {"state": "open", "body": issue_body(606)},
        }
        behind = {stuck_sha: 1, sha_next: 1}
        api = train_api(pulls, issues, behind, {}, [], runs)
        with mock.patch.object(noodles, "gh_api", side_effect=api):
            return noodles.train_select("ed3c/noodles", "main", pulls, "verify")

    def test_completed_verify_failure_at_the_current_head_yields_to_the_newer_behind_candidate(self) -> None:
        sha_stuck = "a" * 40
        selected = self.starving_queue(sha_stuck, {sha_stuck: [verify_run(sha_stuck, "completed", "failure")]})
        self.assertIsNotNone(selected)
        self.assertEqual(selected["number"], 6)

    def test_owner_repush_to_a_new_head_makes_the_same_pr_selectable_again(self) -> None:
        old_head = "a" * 40
        new_head = "9" * 40
        starved = self.starving_queue(old_head, {old_head: [verify_run(old_head, "completed", "failure")]})
        self.assertEqual(starved["number"], 6)
        # constraint: the rule is stateless - the failure is pinned to the exact head, so the owner's new head clears it with no marker to retract.
        repushed = self.starving_queue(new_head, {old_head: [verify_run(old_head, "completed", "failure")]})
        self.assertIsNotNone(repushed)
        self.assertEqual(repushed["number"], 4)

    def test_planted_negative_completed_verify_success_head_is_not_skipped(self) -> None:
        sha_stuck = "a" * 40
        selected = self.starving_queue(sha_stuck, {sha_stuck: [verify_run(sha_stuck, "completed", "success")]})
        self.assertIsNotNone(selected)
        self.assertEqual(selected["number"], 4)

    def test_planted_negative_incomplete_or_absent_verify_head_is_not_skipped(self) -> None:
        sha_stuck = "a" * 40
        for label, runs in (
            ("in_progress", [verify_run(sha_stuck, "in_progress", None)]),
            ("queued", [verify_run(sha_stuck, "queued", None)]),
            ("absent", []),
            ("another workflow failed", [dict(verify_run(sha_stuck, "completed", "failure"), name="land", path=".github/workflows/land.yml")]),
        ):
            with self.subTest(case=label):
                selected = self.starving_queue(sha_stuck, {sha_stuck: runs})
                self.assertIsNotNone(selected)
                self.assertEqual(selected["number"], 4)

    @unittest.skipIf(
        os.getenv("NOODLES_OFFLINE_TESTS") == "1" or os.getenv("GITHUB_ACTIONS") == "true",
        "provider runs API is intentionally unreachable in hosted/offline CI; live control runs before handoff",
    )
    def test_live_control_real_completed_verify_runs_discriminate_failure_from_success(self) -> None:
        # constraint: ed3c/noodles#65 pattern - the shape this rule reads is provider truth, so the predicate
        # constraint: is exercised against the actual runs API for a real red head and a real green head, not
        # constraint: only against fixtures this test wrote itself.
        self.assertTrue(noodles.train_verify_failed_head("ed3c/noodles", LIVE_VERIFY_FAILURE_HEAD, "verify"))
        self.assertFalse(noodles.train_verify_failed_head("ed3c/noodles", LIVE_VERIFY_SUCCESS_HEAD, "verify"))
        self.assertFalse(noodles.train_verify_failed_head("ed3c/noodles", "0" * 40, "verify"))


class LandingTrainRebaseTests(unittest.TestCase):
    def test_planted_control_sibling_behind_new_main_is_rebased_and_pushed_with_lease(self) -> None:
        with tempfile.TemporaryDirectory(prefix="noodles-train-test-") as temp_name:
            base = Path(temp_name)
            fixture = seed_train_remote(base, conflict=False)
            pulls = [pr_fixture(2, 500, fixture["head"], "candidate", "2026-08-30T00:00:00Z")]
            issues = {500: {"state": "open", "body": issue_body(500)}}
            posts: list = []
            api = train_api(pulls, issues, {fixture["head"]: 1}, {}, posts)
            with mock.patch.object(noodles, "gh_api", side_effect=api):
                result = noodles.landing_train(ENGINE_ROOT, remote_url=fixture["origin"])
            self.assertEqual(result["action"], "rebased")
            self.assertEqual(result["old_head"], fixture["head"])
            self.assertEqual(result["base_sha"], fixture["main"])
            self.assertEqual(posts, [])
            remote_head = noodles.run(["git", "-C", fixture["origin"], "rev-parse", "refs/heads/candidate"]).stdout.strip()
            self.assertEqual(remote_head, result["new_head"])
            parent = noodles.run(["git", "-C", fixture["origin"], "rev-parse", f"{remote_head}^"]).stdout.strip()
            self.assertEqual(parent, fixture["main"])
            tree = noodles.run(["git", "-C", fixture["origin"], "ls-tree", "--name-only", remote_head]).stdout.split()
            self.assertEqual(sorted(tree), ["a.txt", "b.txt", "c.txt"])

    def test_planted_conflict_control_fails_back_naming_paths_and_never_pushes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="noodles-train-test-") as temp_name:
            base = Path(temp_name)
            fixture = seed_train_remote(base, conflict=True)
            pulls = [pr_fixture(3, 501, fixture["head"], "candidate", "2026-08-30T00:00:00Z")]
            issues = {501: {"state": "open", "body": issue_body(501)}}
            posts: list = []
            api = train_api(pulls, issues, {fixture["head"]: 1}, {}, posts)
            with mock.patch.object(noodles, "gh_api", side_effect=api):
                result = noodles.landing_train(ENGINE_ROOT, remote_url=fixture["origin"])
            self.assertEqual(result["action"], "failback")
            self.assertEqual(result["conflicts"], ["a.txt"])
            remote_head = noodles.run(["git", "-C", fixture["origin"], "rev-parse", "refs/heads/candidate"]).stdout.strip()
            self.assertEqual(remote_head, fixture["head"])
            self.assertEqual(len(posts), 1)
            endpoint, payload = posts[0]
            self.assertEqual(endpoint, "repos/ed3c/noodles/issues/3/comments")
            self.assertIn(noodles.train_failback_marker(fixture["head"]), payload["body"])
            self.assertIn("a.txt", payload["body"])
            self.assertIn("never auto-resolves", payload["body"])

    def test_planted_negative_absent_push_token_fails_closed_before_touching_the_remote(self) -> None:
        with tempfile.TemporaryDirectory(prefix="noodles-train-test-") as temp_name:
            base = Path(temp_name)
            fixture = seed_train_remote(base, conflict=False)
            pulls = [pr_fixture(8, 502, fixture["head"], "candidate", "2026-08-30T00:00:00Z")]
            issues = {502: {"state": "open", "body": issue_body(502)}}
            posts: list = []
            api = train_api(pulls, issues, {fixture["head"]: 1}, {}, posts)
            with mock.patch.dict(noodles.os.environ, {"NOODLES_TRAIN_PUSH_TOKEN": ""}), mock.patch.object(noodles, "gh_api", side_effect=api):
                with self.assertRaisesRegex(noodles.GateError, "landing train push token absent"):
                    noodles.landing_train(ENGINE_ROOT)
            remote_head = noodles.run(["git", "-C", fixture["origin"], "rev-parse", "refs/heads/candidate"]).stdout.strip()
            self.assertEqual(remote_head, fixture["head"])
            self.assertEqual(posts, [])

    def test_head_drift_between_selection_and_fetch_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="noodles-train-test-") as temp_name:
            base = Path(temp_name)
            fixture = seed_train_remote(base, conflict=False)
            with self.assertRaisesRegex(noodles.GateError, "landing train head drifted"):
                noodles.train_rebase(base / "work", fixture["origin"], "main", "candidate", "f" * 40)
            remote_head = noodles.run(["git", "-C", fixture["origin"], "rev-parse", "refs/heads/candidate"]).stdout.strip()
            self.assertEqual(remote_head, fixture["head"])


class LandingTrainBoundaryTests(unittest.TestCase):
    def workflow_boundary(self, mutate) -> tuple[list[str], dict]:
        with tempfile.TemporaryDirectory(prefix="noodles-train-boundary-") as temp_name:
            root = Path(temp_name)
            workflow_dir = root / ".github/workflows"
            workflow_dir.mkdir(parents=True)
            shutil.copy2(ENGINE_ROOT / ".github/workflows/verify.yml", workflow_dir / "verify.yml")
            land_path = workflow_dir / "land.yml"
            shutil.copy2(ENGINE_ROOT / ".github/workflows/land.yml", land_path)
            mutate(land_path)
            return github_protection.workflow_boundary_readback(root, sha256_file)

    def test_shipped_workflows_pass_and_confine_train_push_token(self) -> None:
        errors, evidence = self.workflow_boundary(lambda _land_path: None)
        self.assertEqual(errors, [])
        self.assertTrue(evidence["land_job_confines_train_push_token"])

    def test_boundary_rejects_removed_train_step(self) -> None:
        def mutate(land_path: Path) -> None:
            workflow = land_path.read_text(encoding="utf-8")
            step = (
                "      - name: Landing train mechanical rebase\n"
                "        env:\n"
                "          GH_TOKEN: ${{ github.token }}\n"
                "          NOODLES_TRAIN_PUSH_TOKEN: ${{ steps.train-token.outputs.token }}\n"
                "        run: python3 noodles.py github train\n"
            )
            self.assertIn(step, workflow)
            land_path.write_text(workflow.replace(step, "", 1), encoding="utf-8")

        errors, evidence = self.workflow_boundary(mutate)
        self.assertIn("land job missing landing-train rebase step", errors)
        self.assertFalse(evidence["land_job_confines_train_push_token"])

    def test_boundary_rejects_disabled_train_step(self) -> None:
        def mutate(land_path: Path) -> None:
            land_path.write_text(
                land_path.read_text(encoding="utf-8").replace(
                    "      - name: Landing train mechanical rebase\n",
                    "      - name: Landing train mechanical rebase\n        if: ${{ false }}\n",
                    1,
                ),
                encoding="utf-8",
            )

        errors, _evidence = self.workflow_boundary(mutate)
        self.assertIn("land landing-train rebase step must stay enabled", errors)

    def test_boundary_rejects_train_push_token_leaking_to_another_step(self) -> None:
        def mutate(land_path: Path) -> None:
            land_path.write_text(
                land_path.read_text(encoding="utf-8").replace(
                    "          NOODLES_REQUIRE_PROTECTION_READ_TOKEN: '1'\n",
                    "          NOODLES_REQUIRE_PROTECTION_READ_TOKEN: '1'\n          NOODLES_TRAIN_PUSH_TOKEN: ${{ steps.train-token.outputs.token }}\n",
                    1,
                ),
                encoding="utf-8",
            )

        errors, _evidence = self.workflow_boundary(mutate)
        self.assertIn("land workflow must pass the train push token only to the landing-train step", errors)

    def test_boundary_rejects_widened_train_token_scope(self) -> None:
        def mutate(land_path: Path) -> None:
            land_path.write_text(
                land_path.read_text(encoding="utf-8").replace(
                    "          permission-contents: write\n",
                    "          permission-contents: read\n          permission-administration: write\n",
                    1,
                ),
                encoding="utf-8",
            )

        errors, _evidence = self.workflow_boundary(mutate)
        self.assertIn("landing-train push token must be scoped to Contents: write", errors)


if __name__ == "__main__":
    unittest.main()

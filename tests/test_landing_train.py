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
GIT_IDENTITY = ["-c", "user.name=noodles-test", "-c", "user.email=noodles-test@example.com", "-c", "commit.gpgsign=false"]
# constraint: immutable provider heads for the live control - ed3c/noodles#233 is the head whose trusted
# constraint: verify completed FAILURE (run 33379233268) and starved the queue; ed3c/noodles#244 is a head
# constraint: whose trusted verify completed SUCCESS (run 33382234390). Both runs are terminal, so neither
# constraint: conclusion can drift under the control.
LIVE_VERIFY_FAILURE_HEAD = "0ff2a643e5b2dcda18b83b9cc61adb8a5b191220"
LIVE_VERIFY_SUCCESS_HEAD = "3383626f1303abd05914026676ca7774de0e7452"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def issue_body(number: int, state: str = "awaiting_land", depends: str = "none") -> str:
    return (
        "<!-- noodles-role: repository-mutating-atom -->\n"
        "<!-- noodles-target: ed3c/noodles -->\n"
        f"<!-- noodles-subject: ed3c/noodles#{number} -->\n"
        f"<!-- noodles-state: {state} -->\n"
        f"<!-- noodles-depends-on: {depends} -->\n"
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


def seed_dependency_chain(base: Path, refs: list[str]) -> dict[str, str]:
    """One predecessor landed on `main` past every successor branch cut from the shared base.

    This is the physical shape the nudge exists for: the merge that closes the predecessor is the same
    merge that leaves every open successor head behind, so `behind_by` is never asserted as a literal in
    these controls - it is measured from this remote."""
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
    heads: dict[str, str] = {}
    for ref in refs:
        g("checkout", "--quiet", "-B", ref, "main")
        (seed / f"{ref}.txt").write_text(f"{ref}\n", encoding="utf-8")
        g("add", ".")
        g("commit", "--quiet", "-m", f"{ref} work")
        heads[ref] = g("rev-parse", "HEAD")
    g("checkout", "--quiet", "main")
    (seed / "predecessor.txt").write_text("landed\n", encoding="utf-8")
    g("add", ".")
    g("commit", "--quiet", "-m", "predecessor landed and closed its issue")
    heads["main"] = g("rev-parse", "HEAD")
    g("push", "--quiet", str(origin), "main", *refs)
    return {"origin": str(origin), **heads}


def remote_head(origin: str, ref: str) -> str:
    return noodles.run(["git", "-C", origin, "rev-parse", f"refs/heads/{ref}"]).stdout.strip()


def measured_behind(origin: str, head_sha: str) -> int:
    """`behind_by` exactly as the provider defines it: default-branch commits this head does not carry."""
    return int(noodles.run(["git", "-C", origin, "rev-list", "--count", f"{head_sha}..refs/heads/main"]).stdout.strip())


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
        if endpoint.startswith("repos/ed3c/noodles/issues?state=open"):
            return [dict(issue, number=number) for number, issue in sorted(issues.items())]
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


class RaceLandApi:
    """The land-path provider surface with `main` as real mutable state.

    A merge is admitted only when the PR's own base still is the current default-branch tip, which is
    what GitHub's strict required-status-checks setting enforces on the real provider. The refusal is
    therefore derived from the observed race, not hardcoded per pull request."""

    def __init__(self, base_sha: str, pulls: dict[int, dict], issues: dict[int, dict]) -> None:
        self.main = base_sha
        self.pulls = pulls
        self.issues = issues
        self.merges: list[int] = []
        self.comments: dict[int, list] = {}

    def merge_sha(self, pr_number: int) -> str:
        return f"{pr_number:040x}"

    def __call__(self, endpoint: str, *, method: str = "GET", payload: object | None = None, token: str | None = None) -> object:
        repo = "repos/ed3c/noodles"
        if endpoint.endswith("/merge") and method == "PUT":
            number = int(endpoint.split("/")[-2])
            pr = self.pulls[number]
            if pr["base"]["sha"] != self.main:
                return {"merged": False, "message": "Required status check is expecting head sha to be reported."}
            merge_sha = self.merge_sha(number)
            self.merges.append(number)
            self.main = merge_sha
            pr.update({"state": "closed", "merged": True, "merge_commit_sha": merge_sha, "merged_at": "2026-09-01T00:00:00Z"})
            return {"merged": True, "sha": merge_sha}
        if endpoint.startswith(f"{repo}/pulls/"):
            return self.pulls[int(endpoint.rsplit("/", 1)[1])]
        if endpoint.startswith(f"{repo}/git/commits/"):
            sha = endpoint.rsplit("/", 1)[1]
            merged = [number for number in self.merges if self.merge_sha(number) == sha]
            if merged:
                return {"parents": [{"sha": self.pulls[merged[0]]["head"]["sha"]}, {"sha": self.pulls[merged[0]]["base"]["sha"]}]}
            return {"tree": {"sha": f"tree-{sha}"}}
        if endpoint == f"{repo}/branches/main":
            return {"commit": {"sha": self.main}}
        if endpoint.startswith(f"{repo}/issues/") and endpoint.endswith("/comments?per_page=100"):
            return self.comments.get(int(endpoint.split("/")[4]), [])
        if method == "POST" and endpoint.endswith("/comments"):
            self.comments.setdefault(int(endpoint.split("/")[4]), []).append({"body": (payload or {}).get("body", "")})
            return {"id": 1}
        if endpoint.startswith(f"{repo}/issues/"):
            number = int(endpoint.rsplit("/", 1)[1])
            if method == "PATCH":
                self.issues[number].update(payload or {})
            return dict(self.issues[number])
        raise AssertionError(f"unexpected gh api call: {method} {endpoint}")


class LandingRaceTests(unittest.TestCase):
    """ed3c/noodles#99 regression control for the landing race, invariant I4's other half.

    The invariant the land gate exists to enforce is: a merge lands the exact verified head onto the
    exact base that head was verified against. Two green lanes cut from one base are both verified, so
    after the first lands the second's verification no longer describes the current default branch; the
    second must fail closed and route to the ff-only repair path, never merge its stale base."""

    BASE = "0" * 40
    HEAD_A = "a" * 40
    HEAD_B = "b" * 40

    def fixture(self) -> RaceLandApi:
        pulls = {
            11: dict(pr_fixture(11, 111, self.HEAD_A, "lane-a", "2026-09-01T00:00:00Z"), merged=False),
            12: dict(pr_fixture(12, 222, self.HEAD_B, "lane-b", "2026-09-01T00:30:00Z"), merged=False),
        }
        for number in pulls:
            pulls[number]["base"] = {"ref": "main", "sha": self.BASE}
        issues = {111: {"state": "open", "body": issue_body(111)}, 222: {"state": "open", "body": issue_body(222)}}
        return RaceLandApi(self.BASE, pulls, issues)

    def land(self, api: RaceLandApi, pr_number: int, issue_number: int, head_sha: str) -> dict:
        with tempfile.TemporaryDirectory(prefix="noodles-landing-race-", ignore_cleanup_errors=True) as name:
            work = Path(name)
            event_path = work / "event.json"
            receipt_path = work / "receipt.json"
            event_path.write_text(json.dumps({
                "repository": {"full_name": "ed3c/noodles"},
                "workflow_run": {
                    "name": "verify",
                    "conclusion": "success",
                    "id": 700 + pr_number,
                    "head_sha": head_sha,
                    "pull_requests": [{"number": pr_number}],
                },
            }), encoding="utf-8")
            receipt_path.write_text(json.dumps({
                "repository": "ed3c/noodles",
                "pr_number": pr_number,
                "head_sha": head_sha,
                "tree_sha": f"tree-{head_sha}",
                "issue_subject": f"ed3c/noodles#{issue_number}",
            }), encoding="utf-8")
            trusted = {"run": {"id": 700 + pr_number}, "workflow": {"path": ".github/workflows/verify.yml"}, "provider_default_branch": "main"}
            with (
                # constraint: ed3c/noodles#433 - the land entry hands the job to the pinned lander and
                # constraint: exports the pin it read back; land_pull_request refuses without it. Here
                # constraint: the engine tree IS the landing bytes, so its own HEAD is the honest pin.
                mock.patch.dict(os.environ, {noodles.LANDER_PIN_ENV: noodles.git(ENGINE_ROOT, "rev-parse", "HEAD")}, clear=False),
                mock.patch.object(noodles, "gh_api", side_effect=api),
                mock.patch.object(noodles.github_protection, "trusted_workflow_run_readback", return_value=trusted),
                mock.patch.object(noodles.github_protection, "protection_audit", return_value={"required_check": "verify"}),
            ):
                return noodles.land_pull_request(ENGINE_ROOT, event_path, receipt_path)

    def test_second_green_lane_over_a_landed_base_fails_closed_to_the_ff_only_repair_path(self) -> None:
        api = self.fixture()
        first = self.land(api, 11, 111, self.HEAD_A)
        self.assertEqual(first["merge_sha"], api.merge_sha(11))
        self.assertEqual(api.main, api.merge_sha(11))
        self.assertEqual(api.issues[111]["state"], "closed")

        with self.assertRaisesRegex(noodles.GateError, "GitHub merge failed"):
            self.land(api, 12, 222, self.HEAD_B)
        self.assertEqual(api.merges, [11])
        self.assertEqual(api.main, api.merge_sha(11))
        self.assertEqual(api.issues[222]["state"], "open")
        self.assertIn("<!-- noodles-state: awaiting_land -->", api.issues[222]["body"])

        pulls = [api.pulls[12]]
        issues = {222: api.issues[222]}
        with mock.patch.object(noodles, "gh_api", side_effect=train_api(pulls, issues, {self.HEAD_B: 1}, {}, [])):
            selected = noodles.train_select("ed3c/noodles", "main", pulls, "verify")
        self.assertIsNotNone(selected)
        self.assertEqual(selected["number"], 12)

    def test_planted_negative_an_up_to_date_second_lane_still_lands(self) -> None:
        # constraint: the refusal above must come from the stale base, not from "a second land in this
        # constraint: process"; rebasing lane B onto the landed tip makes the same call succeed.
        api = self.fixture()
        self.land(api, 11, 111, self.HEAD_A)
        api.pulls[12]["base"] = {"ref": "main", "sha": api.main}
        second = self.land(api, 12, 222, self.HEAD_B)
        self.assertEqual(second["merge_sha"], api.merge_sha(12))
        self.assertEqual(api.merges, [11, 12])
        self.assertEqual(api.issues[222]["state"], "closed")

    def test_planted_negative_non_strict_branch_protection_fails_the_land_audit_closed(self) -> None:
        # constraint: ed3c/noodles#99 - the fake above refuses a stale base because the real provider
        # constraint: does, and it only does so while branch protection requires strict up-to-date
        # constraint: checks. land_pull_request re-audits that on every land, so this control pins the
        # constraint: audit as the carrier instead of leaving the race refusal an assumption.
        from tests.test_github_protection import protection_fixture

        stale_allowed = protection_fixture()
        stale_allowed["required_status_checks"]["strict"] = False
        environment = {
            "NOODLES_REQUIRE_PROTECTION_READ_TOKEN": "1",
            "NOODLES_GITHUB_PROTECTION_TOKEN": "app-token",
            "GH_TOKEN": "default-token",
        }
        with mock.patch.dict(os.environ, environment, clear=False):
            audit = github_protection.protection_audit(
                lambda endpoint, **kwargs: ({}, protection_fixture()), noodles.GateError, "ed3c/noodles", "main", "verify"
            )
            self.assertEqual(audit["branch"], "main")
            with self.assertRaisesRegex(noodles.GateError, "strict up-to-date status checks"):
                github_protection.protection_audit(
                    lambda endpoint, **kwargs: ({}, stale_allowed), noodles.GateError, "ed3c/noodles", "main", "verify"
                )


class LandingTrainRebaseTests(unittest.TestCase):
    def test_planted_control_sibling_behind_new_main_is_rebased_and_pushed_with_lease(self) -> None:
        with tempfile.TemporaryDirectory(prefix="noodles-train-test-", ignore_cleanup_errors=True) as temp_name:
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
        with tempfile.TemporaryDirectory(prefix="noodles-train-test-", ignore_cleanup_errors=True) as temp_name:
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
        with tempfile.TemporaryDirectory(prefix="noodles-train-test-", ignore_cleanup_errors=True) as temp_name:
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
        with tempfile.TemporaryDirectory(prefix="noodles-train-test-", ignore_cleanup_errors=True) as temp_name:
            base = Path(temp_name)
            fixture = seed_train_remote(base, conflict=False)
            with self.assertRaisesRegex(noodles.GateError, "landing train head drifted"):
                noodles.train_rebase(base / "work", fixture["origin"], "main", "candidate", "f" * 40)
            remote_head = noodles.run(["git", "-C", fixture["origin"], "rev-parse", "refs/heads/candidate"]).stdout.strip()
            self.assertEqual(remote_head, fixture["head"])


class LandingTrainBoundaryTests(unittest.TestCase):
    def workflow_boundary(self, mutate) -> tuple[list[str], dict]:
        with tempfile.TemporaryDirectory(prefix="noodles-train-boundary-", ignore_cleanup_errors=True) as temp_name:
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
                "          NOODLES_LAND_RECEIPT: ${{ github.workspace }}/receipt/noodles-receipt.json\n"
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

    def test_boundary_rejects_a_train_step_that_drops_the_land_receipt(self) -> None:
        # constraint: ed3c/noodles#332 - the closure subject the nudge keys on reaches the train only
        # constraint: through this argument, so silently dropping it would park every dependency-red head
        # constraint: again while the step still looks present and enabled.
        def mutate(land_path: Path) -> None:
            land_path.write_text(
                land_path.read_text(encoding="utf-8").replace(
                    "          NOODLES_LAND_RECEIPT: ${{ github.workspace }}/receipt/noodles-receipt.json\n", "", 1
                ),
                encoding="utf-8",
            )

        errors, _evidence = self.workflow_boundary(mutate)
        self.assertIn(
            "landing-train rebase step must receive the exact land receipt whose issue_subject names the closure to nudge dependents of",
            errors,
        )

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


class LandingTrainNudgeTests(unittest.TestCase):
    """ed3c/noodles#332 - the predecessor closure re-admits exactly the heads it unblocked.

    Every control below runs against a real git remote, and `behind_by` is measured from that remote
    rather than declared, so the boundedness claim ("a nudged head is no longer behind, therefore the
    same closure event cannot push it twice") is read off the same physical fact the provider reports."""

    CLOSED = "ed3c/noodles#620"

    def nudge(
        self,
        fixture: dict[str, str],
        refs: dict[str, tuple[int, int, str]],
        *,
        closed_subject: str | None,
        red: bool = True,
        heads: dict[str, str] | None = None,
        recorder: list[str] | None = None,
    ) -> dict:
        """Run one train over `refs` (branch -> pr number, issue number, declared dependency)."""
        heads = heads or {ref: fixture[ref] for ref in refs}
        pulls = [
            pr_fixture(pr_number, issue_number, heads[ref], ref, f"2026-09-01T0{index}:00:00Z")
            for index, (ref, (pr_number, issue_number, _depends)) in enumerate(refs.items())
        ]
        issues = {
            issue_number: {"state": "open", "body": issue_body(issue_number, depends=depends)}
            for _ref, (_pr_number, issue_number, depends) in refs.items()
        }
        behind = {heads[ref]: measured_behind(fixture["origin"], heads[ref]) for ref in refs}
        runs = {heads[ref]: [verify_run(heads[ref], "completed", "failure")] for ref in refs} if red else {}
        api = train_api(pulls, issues, behind, {}, [], runs)

        def recorded(endpoint: str, **kwargs: object) -> object:
            if recorder is not None:
                recorder.append(endpoint)
            return api(endpoint, **kwargs)

        with mock.patch.object(noodles, "gh_api", side_effect=recorded):
            return noodles.landing_train(ENGINE_ROOT, remote_url=fixture["origin"], closed_subject=closed_subject)

    def test_chain_control_a_declared_dependent_is_nudged_once_onto_the_closing_merge(self) -> None:
        with tempfile.TemporaryDirectory(prefix="noodles-train-nudge-", ignore_cleanup_errors=True) as temp_name:
            fixture = seed_dependency_chain(Path(temp_name), ["successor"])
            self.assertEqual(measured_behind(fixture["origin"], fixture["successor"]), 1)
            result = self.nudge(fixture, {"successor": (21, 621, self.CLOSED)}, closed_subject=self.CLOSED)
            self.assertEqual(len(result["nudged"]), 1)
            nudge = result["nudged"][0]
            self.assertEqual((nudge["action"], nudge["pr_number"], nudge["nudged_for"]), ("rebased", 21, self.CLOSED))
            self.assertEqual(nudge["old_head"], fixture["successor"])
            pushed = remote_head(fixture["origin"], "successor")
            self.assertEqual(pushed, nudge["new_head"])
            self.assertNotEqual(pushed, fixture["successor"])
            # constraint: the fresh head is a real head on the closing merge - this is what re-arms verify.
            parent = noodles.run(["git", "-C", fixture["origin"], "rev-parse", f"{pushed}^"]).stdout.strip()
            self.assertEqual(parent, fixture["main"])
            self.assertEqual(measured_behind(fixture["origin"], pushed), 0)
            # constraint: the ordinary selection is withheld from a PR this run already pushed, because the
            # constraint: listing that feeds it still names the pre-nudge head and would fail head-drift closed.
            self.assertEqual(result["action"], "idle")

    def test_planted_negative_a_red_head_declaring_another_predecessor_is_left_parked(self) -> None:
        with tempfile.TemporaryDirectory(prefix="noodles-train-nudge-", ignore_cleanup_errors=True) as temp_name:
            fixture = seed_dependency_chain(Path(temp_name), ["successor"])
            result = self.nudge(fixture, {"successor": (21, 621, "ed3c/noodles#999")}, closed_subject=self.CLOSED)
            self.assertEqual(result["nudged"], [])
            self.assertEqual(result["action"], "idle")
            self.assertEqual(remote_head(fixture["origin"], "successor"), fixture["successor"])

    def test_planted_negative_a_dependency_free_red_head_is_left_parked(self) -> None:
        with tempfile.TemporaryDirectory(prefix="noodles-train-nudge-", ignore_cleanup_errors=True) as temp_name:
            fixture = seed_dependency_chain(Path(temp_name), ["successor"])
            result = self.nudge(fixture, {"successor": (21, 621, "none")}, closed_subject=self.CLOSED)
            self.assertEqual(result["nudged"], [])
            self.assertEqual(result["action"], "idle")
            self.assertEqual(remote_head(fixture["origin"], "successor"), fixture["successor"])

    def test_cardinality_two_declared_dependents_get_one_nudge_each_and_a_replay_gets_none(self) -> None:
        with tempfile.TemporaryDirectory(prefix="noodles-train-nudge-", ignore_cleanup_errors=True) as temp_name:
            fixture = seed_dependency_chain(Path(temp_name), ["first", "second"])
            refs = {"first": (21, 621, self.CLOSED), "second": (22, 622, self.CLOSED)}
            result = self.nudge(fixture, refs, closed_subject=self.CLOSED)
            self.assertEqual([nudge["action"] for nudge in result["nudged"]], ["rebased", "rebased"])
            self.assertEqual(sorted(nudge["pr_number"] for nudge in result["nudged"]), [21, 22])
            fresh = {ref: remote_head(fixture["origin"], ref) for ref in refs}
            for ref, head in fresh.items():
                self.assertNotEqual(head, fixture[ref])
            # constraint: replaying the same closure event over the heads it produced. Nothing is asserted
            # constraint: about a marker or a counter: the measured behind_by is what stops the second push.
            self.assertEqual({measured_behind(fixture["origin"], head) for head in fresh.values()}, {0})
            replay = self.nudge(fixture, refs, closed_subject=self.CLOSED, heads=fresh)
            self.assertEqual(replay["nudged"], [])
            self.assertEqual({ref: remote_head(fixture["origin"], ref) for ref in refs}, fresh)

    def test_a_nudged_head_that_fails_verify_again_is_not_nudged_again_by_the_same_closure(self) -> None:
        with tempfile.TemporaryDirectory(prefix="noodles-train-nudge-", ignore_cleanup_errors=True) as temp_name:
            fixture = seed_dependency_chain(Path(temp_name), ["successor"])
            refs = {"successor": (21, 621, self.CLOSED)}
            first = self.nudge(fixture, refs, closed_subject=self.CLOSED)
            fresh = remote_head(fixture["origin"], "successor")
            self.assertEqual(first["nudged"][0]["new_head"], fresh)
            # constraint: the fresh head is red too - the nudge is one bounded action, not a retry loop.
            again = self.nudge(fixture, refs, closed_subject=self.CLOSED, heads={"successor": fresh}, red=True)
            self.assertEqual(again["nudged"], [])
            self.assertEqual(again["action"], "idle")
            self.assertEqual(remote_head(fixture["origin"], "successor"), fresh)

    def test_the_train_entry_point_carries_the_land_receipt_subject_and_fails_closed_without_one(self) -> None:
        # constraint: the closure identity crosses one process boundary, so both directions of that
        # constraint: crossing are held here: a receipt naming a subject reaches landing_train as that
        # constraint: exact subject, and a receipt naming none is a FATAL, never a silent no-nudge train.
        with tempfile.TemporaryDirectory(prefix="noodles-train-cli-", ignore_cleanup_errors=True) as temp_name:
            receipt = Path(temp_name) / "noodles-receipt.json"
            receipt.write_text(json.dumps({"issue_subject": self.CLOSED}), encoding="utf-8")
            environment = {"NOODLES_LAND_RECEIPT": str(receipt)}
            with mock.patch.dict(noodles.os.environ, environment), mock.patch.object(noodles, "landing_train", return_value={"action": "idle"}) as train:
                self.assertEqual(noodles.main(["github", "train"]), 0)
            self.assertEqual(train.call_args.kwargs["closed_subject"], self.CLOSED)

            receipt.write_text(json.dumps({"pr_number": 21}), encoding="utf-8")
            with mock.patch.dict(noodles.os.environ, environment), mock.patch.object(noodles, "landing_train", return_value={"action": "idle"}) as train:
                self.assertEqual(noodles.main(["github", "train"]), 1)
            train.assert_not_called()

            # constraint: no receipt in the environment is a train run outside the land job, not a defect.
            with mock.patch.dict(noodles.os.environ, {"NOODLES_LAND_RECEIPT": ""}), mock.patch.object(noodles, "landing_train", return_value={"action": "idle"}) as train:
                self.assertEqual(noodles.main(["github", "train"]), 0)
            self.assertIsNone(train.call_args.kwargs["closed_subject"])

    def test_a_green_dependent_this_run_nudged_is_withheld_from_its_own_ordinary_selection(self) -> None:
        # constraint: a declared dependent need not be red - a behind, green one is nudgeable and also
        # constraint: ordinarily selectable. The listing that feeds the selection still names its pre-nudge
        # constraint: head, so without the withhold the same run rebases it twice and the second attempt
        # constraint: fails the whole train closed on head drift.
        with tempfile.TemporaryDirectory(prefix="noodles-train-nudge-", ignore_cleanup_errors=True) as temp_name:
            fixture = seed_dependency_chain(Path(temp_name), ["successor"])
            result = self.nudge(fixture, {"successor": (21, 621, self.CLOSED)}, closed_subject=self.CLOSED, red=False)
            self.assertEqual([nudge["action"] for nudge in result["nudged"]], ["rebased"])
            self.assertEqual(result["action"], "idle")
            self.assertEqual(remote_head(fixture["origin"], "successor"), result["nudged"][0]["new_head"])

    def test_a_closure_with_no_declared_dependent_costs_exactly_one_listing_and_nothing_else(self) -> None:
        with tempfile.TemporaryDirectory(prefix="noodles-train-nudge-", ignore_cleanup_errors=True) as temp_name:
            fixture = seed_dependency_chain(Path(temp_name), ["successor"])
            refs = {"successor": (21, 621, "none")}
            without: list[str] = []
            self.nudge(fixture, refs, closed_subject=None, recorder=without)
            with_closure: list[str] = []
            self.nudge(fixture, refs, closed_subject=self.CLOSED, recorder=with_closure)
            listings = [call for call in with_closure if call.startswith("repos/ed3c/noodles/issues?state=open")]
            self.assertEqual(len(listings), 1)
            self.assertEqual([call for call in with_closure if call not in listings], without)


if __name__ == "__main__":
    unittest.main()

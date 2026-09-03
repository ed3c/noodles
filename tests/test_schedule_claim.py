from __future__ import annotations

import json
import contextlib
import dataclasses
import hashlib
import io
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

import issue_contract
import noodles
import schedule_domain
import skill_contract
from tests.support import CANDIDATE_ROOT, ISSUE_REQUIREMENT_MARKER, complete_issue_sections, copy_tracked

REPOSITORY = "ed3c/noodles"
HEAD = "a" * 40
EXECUTE_MODEL = skill_contract.task_profiles(CANDIDATE_ROOT)["execute"]["model"]


def issue_body(number: int, *, state: str = "ready", depends_on: str = "none", write_boundary: str = "none") -> str:
    subject = f"{REPOSITORY}#{number}"
    return (
        "<!-- noodles-role: repository-mutating-atom -->\n"
        f"<!-- noodles-target: {REPOSITORY} -->\n"
        f"<!-- noodles-subject: {subject} -->\n"
        f"<!-- noodles-state: {state} -->\n"
        f"<!-- noodles-depends-on: {depends_on} -->\n"
        f"<!-- noodles-write-boundary: {write_boundary} -->\n"
        "<!-- noodles-executor: gha-runtime -->\n"
        "<!-- noodles-runtime: shell -->\n"
        "<!-- noodles-evidence: github-only-v1 -->\n"
        f"{ISSUE_REQUIREMENT_MARKER}\n\n"
        + complete_issue_sections("Schedule one exact atom.", "- No scheduler is implemented.")
    )


def issue(
    number: int,
    *,
    state: str = "ready",
    depends_on: str = "none",
    provider_state: str = "open",
    p0: bool = True,
    write_boundary: str = "none",
) -> dict:
    return {
        "number": number,
        "state": provider_state,
        "body": issue_body(number, state=state, depends_on=depends_on, write_boundary=write_boundary),
        "title": f"[PARALLEL-P0] issue {number}" if p0 else f"issue {number}",
        "html_url": f"https://github.test/{REPOSITORY}/issues/{number}",
    }


def pull(number: int, *, body: str, head_ref: str) -> dict:
    return {"number": number, "state": "open", "body": body, "head": {"ref": head_ref}}


class FakeProvider:
    def __init__(
        self,
        open_issues: list[dict],
        read_issues: dict[int, dict] | None = None,
        pulls: list[dict] | None = None,
    ) -> None:
        self.open_issues = open_issues
        self.read_issues = read_issues or {int(item["number"]): item for item in open_issues}
        self.pulls = list(pulls or [])
        self.refs: dict[str, str] = {}
        self.posts = 0
        self.issue_pages: list[int] = []
        self.pull_pages: list[int] = []
        self.lock = threading.Lock()

    def api(self, endpoint: str, *, method: str = "GET", payload: object | None = None, token: str | None = None) -> object:
        pull_prefix = f"repos/{REPOSITORY}/pulls?state=open&per_page=100&page="
        if endpoint.startswith(pull_prefix):
            page = int(endpoint.removeprefix(pull_prefix))
            self.pull_pages.append(page)
            start = (page - 1) * 100
            return self.pulls[start:start + 100]
        issue_prefix = f"repos/{REPOSITORY}/issues?state=open&sort=created&direction=asc&per_page=100&page="
        if endpoint.startswith(issue_prefix):
            page = int(endpoint.removeprefix(issue_prefix))
            self.issue_pages.append(page)
            start = (page - 1) * 100
            return self.open_issues[start:start + 100]
        if endpoint.startswith(f"repos/{REPOSITORY}/issues/"):
            number = int(endpoint.rsplit("/", 1)[1])
            return self.read_issues[number]
        if endpoint.startswith(f"repos/{REPOSITORY}/git/matching-refs/heads/"):
            prefix = endpoint.partition("/git/matching-refs/heads/")[2]
            return [
                {"ref": ref, "object": {"sha": sha}}
                for ref, sha in sorted(self.refs.items())
                if ref.removeprefix("refs/heads/").startswith(prefix)
            ]
        if endpoint == f"repos/{REPOSITORY}/git/ref/heads/main":
            return {"ref": "refs/heads/main", "object": {"sha": HEAD}}
        if endpoint == f"repos/{REPOSITORY}/git/refs" and method == "POST":
            assert isinstance(payload, dict)
            ref = str(payload["ref"])
            sha = str(payload["sha"])
            with self.lock:
                self.posts += 1
                if ref in self.refs:
                    raise noodles.GateError("provider rejected duplicate ref")
                self.refs[ref] = sha
            return {"ref": ref, "object": {"sha": sha}}
        raise AssertionError(f"unexpected provider call: {method} {endpoint}")


class ScheduleDomainTests(unittest.TestCase):
    def item(
        self,
        repository: str,
        number: int,
        *,
        schedulable: bool = True,
        claimed: bool = False,
        dependencies: tuple[str, ...] = (),
        malformed: bool = False,
    ) -> schedule_domain.ScheduleIssue:
        return schedule_domain.ScheduleIssue(
            subject=f"{repository}#{number}",
            repository=repository,
            number=number,
            dependencies=dependencies,
            p0=True,
            schedulable=schedulable,
            claimed=claimed,
            malformed=malformed,
        )

    def test_dependency_components_partition_and_select_oldest(self) -> None:
        decision = schedule_domain.schedule_decision((
            self.item("ed3c/noodles", 90),
            self.item("ed3c/noodles", 82),
            self.item("ed3c/other", 4),
            self.item("ed3c/other", 3, schedulable=False),
        ))
        self.assertEqual(decision.frontier, ("ed3c/noodles#82", "ed3c/noodles#90", "ed3c/other#4"))
        self.assertEqual(decision.components, (("ed3c/noodles#82",), ("ed3c/noodles#90",), ("ed3c/other#4",)))
        self.assertEqual(decision.winners, ("ed3c/noodles#82", "ed3c/noodles#90", "ed3c/other#4"))
        self.assertEqual(decision.max_useful_workers, 3)

    def test_dependency_edges_join_issues_into_one_component(self) -> None:
        decision = schedule_domain.schedule_decision((
            self.item(REPOSITORY, 81),
            self.item(REPOSITORY, 82, dependencies=(f"{REPOSITORY}#81",)),
            self.item(REPOSITORY, 90),
        ))
        self.assertEqual(decision.components, ((f"{REPOSITORY}#81", f"{REPOSITORY}#82"), (f"{REPOSITORY}#90",)))
        self.assertEqual(decision.winners, (f"{REPOSITORY}#81", f"{REPOSITORY}#90"))
        self.assertEqual(decision.max_useful_workers, 2)

    def test_claimed_issue_excludes_only_its_dependency_component(self) -> None:
        decision = schedule_domain.schedule_decision((
            self.item(REPOSITORY, 81, schedulable=False, claimed=True),
            self.item(REPOSITORY, 82),
            self.item(REPOSITORY, 90),
        ))
        self.assertEqual(decision.frontier, (f"{REPOSITORY}#82", f"{REPOSITORY}#90"))
        self.assertEqual(decision.winners, (f"{REPOSITORY}#82", f"{REPOSITORY}#90"))
        self.assertEqual(decision.max_useful_workers, 2)

    def test_dependent_of_a_claimed_issue_stays_excluded(self) -> None:
        decision = schedule_domain.schedule_decision((
            self.item(REPOSITORY, 81, schedulable=False, claimed=True),
            self.item(REPOSITORY, 82, dependencies=(f"{REPOSITORY}#81",)),
            self.item(REPOSITORY, 90),
        ))
        self.assertEqual(decision.frontier, (f"{REPOSITORY}#90",))
        self.assertEqual(decision.winners, (f"{REPOSITORY}#90",))
        self.assertEqual(decision.max_useful_workers, 1)

    def test_malformed_live_claim_fails_the_repository_closed(self) -> None:
        decision = schedule_domain.schedule_decision((
            self.item(REPOSITORY, 81, schedulable=False, claimed=True, malformed=True),
            self.item(REPOSITORY, 82),
            self.item("ed3c/other", 4),
        ))
        self.assertEqual(decision.frontier, ("ed3c/other#4",))
        self.assertEqual(decision.max_useful_workers, 1)


class ProviderClaimTests(unittest.TestCase):
    def test_two_claimers_create_one_exact_provider_ref(self) -> None:
        provider = FakeProvider([])
        branch = noodles.execute_branch(f"{REPOSITORY}#82")
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: noodles.claim_execute_branch(REPOSITORY, branch, HEAD), range(2)))
        self.assertEqual(provider.posts, 2)
        self.assertEqual([item["status"] for item in results].count("claimed"), 1)
        self.assertEqual([item["status"] for item in results].count("claimed_elsewhere"), 1)
        self.assertEqual(provider.refs, {f"refs/heads/{branch}": HEAD})

    def test_non_conflict_provider_failure_is_not_a_clean_skip(self) -> None:
        def failed(endpoint: str, *, method: str = "GET", payload: object | None = None, token: str | None = None) -> object:
            if method == "POST":
                raise noodles.GateError("provider unavailable")
            return []

        with mock.patch.object(noodles, "gh_api", side_effect=failed):
            with self.assertRaisesRegex(noodles.GateError, "provider unavailable"):
                noodles.claim_execute_branch(REPOSITORY, noodles.execute_branch(f"{REPOSITORY}#82"), HEAD)


class SchedulePublishTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="noodles-schedule-claim-", ignore_cleanup_errors=True)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        copy_tracked(CANDIDATE_ROOT, self.root)

    def write_candidate(self, subjects: list[str]) -> Path:
        candidate = self.root / ".noodle/orders-next.candidate.json"
        candidate.parent.mkdir(exist_ok=True)
        candidate.write_text(json.dumps({
            "orders": [
                {
                    "id": subject,
                    "stages": [{"do": "execute", "model": EXECUTE_MODEL, "prompt": "next"}],
                }
                for subject in subjects
            ]
        }))
        return candidate

    def published_orders(self) -> list[dict]:
        return json.loads((self.root / ".noodle/orders-next.json").read_text())["orders"]

    def test_independent_frontier_issues_both_claim_and_publish(self) -> None:
        provider = FakeProvider([issue(90), issue(82)])
        candidate = self.write_candidate([f"{REPOSITORY}#90", f"{REPOSITORY}#82"])
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            brief = noodles.schedule_publish(self.root, candidate)
        self.assertEqual(provider.posts, 2)
        self.assertEqual(
            sorted(item["id"] for item in self.published_orders()),
            [f"{REPOSITORY}#82", f"{REPOSITORY}#90"],
        )
        self.assertEqual(brief["max_useful_workers"], 2)
        self.assertEqual(json.loads((self.root / ".noodle/schedule-cycle.json").read_text()), brief)
        self.assertEqual(
            {item["subject"]: item["status"] for item in brief["claims"]},
            {f"{REPOSITORY}#82": "claimed", f"{REPOSITORY}#90": "claimed"},
        )

    def test_overlapping_write_boundaries_admit_only_the_first(self) -> None:
        provider = FakeProvider([
            issue(82, write_boundary="schedule_domain.py"),
            issue(90, write_boundary="schedule_domain.py"),
        ])
        candidate = self.write_candidate([f"{REPOSITORY}#82", f"{REPOSITORY}#90"])
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            brief = noodles.schedule_publish(self.root, candidate)
        self.assertEqual(provider.posts, 1)
        self.assertEqual([item["id"] for item in self.published_orders()], [f"{REPOSITORY}#82"])
        claims = {item["subject"]: item for item in brief["claims"]}
        self.assertEqual(claims[f"{REPOSITORY}#82"]["status"], "claimed")
        rejected = claims[f"{REPOSITORY}#90"]
        self.assertEqual(rejected["status"], "boundary_conflict")
        self.assertEqual(rejected["conflict_with"], f"{REPOSITORY}#82")
        self.assertEqual(rejected["prefix"], "schedule_domain.py")
        self.assertEqual(rejected["meaning"], skill_contract.SCHEDULE_CLAIM_STATUS_MEANINGS["boundary_conflict"])

    def test_disjoint_write_boundaries_both_admit(self) -> None:
        provider = FakeProvider([
            issue(82, write_boundary="schedule_domain.py"),
            issue(90, write_boundary="daemon_lease.py"),
        ])
        candidate = self.write_candidate([f"{REPOSITORY}#82", f"{REPOSITORY}#90"])
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            brief = noodles.schedule_publish(self.root, candidate)
        self.assertEqual(provider.posts, 2)
        self.assertEqual(
            sorted(item["id"] for item in self.published_orders()),
            [f"{REPOSITORY}#82", f"{REPOSITORY}#90"],
        )
        self.assertEqual(
            {item["subject"]: item["status"] for item in brief["claims"]},
            {f"{REPOSITORY}#82": "claimed", f"{REPOSITORY}#90": "claimed"},
        )

    def test_nested_prefix_boundaries_intersect_and_reject(self) -> None:
        provider = FakeProvider([
            issue(82, write_boundary="docs"),
            issue(90, write_boundary="docs/design/plan.md"),
        ])
        candidate = self.write_candidate([f"{REPOSITORY}#82", f"{REPOSITORY}#90"])
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            brief = noodles.schedule_publish(self.root, candidate)
        self.assertEqual(provider.posts, 1)
        rejected = {item["subject"]: item for item in brief["claims"]}[f"{REPOSITORY}#90"]
        self.assertEqual(rejected["status"], "boundary_conflict")
        self.assertEqual(rejected["conflict_with"], f"{REPOSITORY}#82")
        self.assertEqual(rejected["prefix"], "docs/design/plan.md")

    def claim(self, provider: FakeProvider, number: int) -> None:
        provider.refs[f"refs/heads/{noodles.execute_branch(f'{REPOSITORY}#{number}')}"] = HEAD

    def test_write_boundary_widened_after_claim_into_live_conflict_is_named_distinctly(self) -> None:
        # constraint: ed3c/noodles#296 - the live case. #85 was claimed while its marker declared
        # constraint: `none`, then corrected itself to real paths that already intersect the
        # constraint: concurrently claimed #81. `boundary_admission_conflict` runs inside the claim
        # constraint: cycle and never runs again for an Issue past claim, so nothing re-validated
        # constraint: the widening. This receipt entry is the re-check binding to the marker's
        # constraint: CURRENT bytes; without it the widening is invisible to #81's lane.
        widened = issue(85, state="in_progress", write_boundary="noodles.py")
        active = issue(81, state="in_progress", write_boundary="noodles.py")
        candidate_issue = issue(82, write_boundary="daemon_lease.py")
        provider = FakeProvider([active, candidate_issue, widened])
        self.claim(provider, 81)
        self.claim(provider, 85)
        candidate = self.write_candidate([f"{REPOSITORY}#82"])
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            brief = noodles.schedule_publish(self.root, candidate)
        claims = {item["subject"]: item for item in brief["claims"]}
        widening = claims[f"{REPOSITORY}#85"]
        self.assertEqual(widening["status"], "claimed_boundary_widened")
        self.assertEqual(widening["conflict_with"], f"{REPOSITORY}#81")
        self.assertEqual(widening["prefix"], "noodles.py")
        self.assertEqual(
            widening["meaning"], skill_contract.SCHEDULE_CLAIM_STATUS_MEANINGS["claimed_boundary_widened"]
        )
        # constraint: ed3c/noodles#296 non-claim - a candidate genuinely disjoint from every live
        # constraint: claim is still admitted; an unsound pair among the claims does not make this
        # constraint: candidate's own disjointness false.
        self.assertEqual(claims[f"{REPOSITORY}#82"]["status"], "claimed")

    def test_widening_state_is_visibly_distinct_from_admission_refusal_and_from_blocked(self) -> None:
        # constraint: ed3c/noodles#296 - one cycle carrying all three shapes at once: the widened
        # constraint: live claim, a candidate refused at admission over the same prefix, and an
        # constraint: ordinary blocked Issue. A reader must tell them apart from the receipt alone,
        # constraint: which is why the widening does not reuse the `boundary_conflict` status.
        widened = issue(85, state="in_progress", write_boundary="noodles.py")
        active = issue(81, state="in_progress", write_boundary="noodles.py")
        blocked = issue(95)
        blocked["body"] = blocked["body"].replace(
            "<!-- noodles-state: ready -->",
            "<!-- noodles-state: blocked -->\n<!-- noodles-blocker: ops: waiting on a human decision -->",
        )
        candidate_issue = issue(90, write_boundary="noodles.py")
        provider = FakeProvider([active, widened, candidate_issue, blocked])
        self.claim(provider, 81)
        self.claim(provider, 85)
        candidate = self.write_candidate([f"{REPOSITORY}#90"])
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            brief = noodles.schedule_publish(self.root, candidate)
        statuses = {item["subject"]: item["status"] for item in brief["claims"]}
        self.assertEqual(statuses[f"{REPOSITORY}#85"], "claimed_boundary_widened")
        self.assertEqual(statuses[f"{REPOSITORY}#90"], "boundary_conflict")
        self.assertNotIn(f"{REPOSITORY}#95", statuses)
        self.assertNotEqual(
            skill_contract.SCHEDULE_CLAIM_STATUS_MEANINGS["claimed_boundary_widened"],
            skill_contract.SCHEDULE_CLAIM_STATUS_MEANINGS["boundary_conflict"],
        )
        self.assertNotIn("blocked", skill_contract.SCHEDULE_CLAIM_STATUS_MEANINGS)
        self.assertEqual(provider.posts, 0)

    def test_planted_negative_widening_that_stays_disjoint_passes_without_friction(self) -> None:
        # constraint: ed3c/noodles#296 - the re-check must not tax an honest correction: a claimed
        # constraint: Issue that widens its marker onto paths no live claim touches produces nothing.
        widened = issue(85, state="in_progress", write_boundary="daemon_lease.py")
        active = issue(81, state="in_progress", write_boundary="noodles.py")
        candidate_issue = issue(82, write_boundary="docs")
        provider = FakeProvider([active, candidate_issue, widened])
        self.claim(provider, 81)
        self.claim(provider, 85)
        candidate = self.write_candidate([f"{REPOSITORY}#82"])
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            brief = noodles.schedule_publish(self.root, candidate)
        self.assertEqual([item for item in brief["claims"] if item["status"] == "claimed_boundary_widened"], [])
        self.assertEqual({item["subject"]: item["status"] for item in brief["claims"]}, {f"{REPOSITORY}#82": "claimed"})
        self.assertEqual(provider.posts, 1)

    def test_missing_write_boundary_fails_closed_before_provider_ref(self) -> None:
        undeclared = issue(82)
        undeclared["body"] = undeclared["body"].replace("<!-- noodles-write-boundary: none -->\n", "")
        provider = FakeProvider([undeclared])
        candidate = self.write_candidate([f"{REPOSITORY}#82"])
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            brief = noodles.schedule_publish(self.root, candidate)
        self.assertEqual(provider.posts, 0)
        self.assertEqual(self.published_orders(), [])
        claim = brief["claims"][0]
        self.assertEqual(claim["status"], "boundary_undeclared")
        self.assertEqual(claim["meaning"], skill_contract.SCHEDULE_CLAIM_STATUS_MEANINGS["boundary_undeclared"])

    def test_active_lane_boundary_blocks_overlapping_candidate(self) -> None:
        active = issue(81, state="in_progress", write_boundary="schedule_domain.py")
        candidate_issue = issue(82, write_boundary="schedule_domain.py")
        provider = FakeProvider([active, candidate_issue])
        provider.refs[f"refs/heads/{noodles.execute_branch(f'{REPOSITORY}#81')}"] = HEAD
        candidate = self.write_candidate([f"{REPOSITORY}#82"])
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            brief = noodles.schedule_publish(self.root, candidate)
        self.assertEqual(provider.posts, 0)
        self.assertEqual(self.published_orders(), [])
        rejected = brief["claims"][0]
        self.assertEqual(rejected["status"], "boundary_conflict")
        self.assertEqual(rejected["conflict_with"], f"{REPOSITORY}#81")
        self.assertEqual(rejected["prefix"], "schedule_domain.py")

    def test_active_lane_undeclared_boundary_blocks_disjoint_candidate(self) -> None:
        # constraint: ed3c/noodles#98 - an active lane's own undeclared boundary
        # constraint: could write anywhere, so it must block a candidate even when
        # constraint: the candidate's declared prefix does not textually intersect
        # constraint: anything the active lane declared (it declared nothing).
        active = issue(81, state="in_progress")
        active["body"] = active["body"].replace("<!-- noodles-write-boundary: none -->\n", "")
        candidate_issue = issue(82, write_boundary="daemon_lease.py")
        provider = FakeProvider([active, candidate_issue])
        provider.refs[f"refs/heads/{noodles.execute_branch(f'{REPOSITORY}#81')}"] = HEAD
        candidate = self.write_candidate([f"{REPOSITORY}#82"])
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            brief = noodles.schedule_publish(self.root, candidate)
        self.assertEqual(provider.posts, 0)
        self.assertEqual(self.published_orders(), [])
        rejected = brief["claims"][0]
        self.assertEqual(rejected["status"], "boundary_conflict")
        self.assertEqual(rejected["conflict_with"], f"{REPOSITORY}#81")
        self.assertEqual(rejected["prefix"], issue_contract.NO_WRITE_BOUNDARY)

    def test_subject_with_an_open_pr_is_refused_and_routed_to_the_repair_owner(self) -> None:
        # constraint: ed3c/noodles#99 - I4. The open PR sits on its own branch, so the subject's exact
        # constraint: execute ref is free and #46's duplicate-active-branch control sees nothing; only
        # constraint: the PR body's exact `Refs` correlation catches this second attempt.
        provider = FakeProvider(
            [issue(82)],
            pulls=[pull(7, body=f"Refs {REPOSITORY}#82", head_ref="fix-82-second-attempt")],
        )
        candidate = self.write_candidate([f"{REPOSITORY}#82"])
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            brief = noodles.schedule_publish(self.root, candidate)
        self.assertEqual(provider.posts, 0)
        self.assertEqual(provider.refs, {})
        self.assertEqual(self.published_orders(), [])
        rejected = brief["claims"][0]
        self.assertEqual(rejected["status"], "open_pr_exists")
        self.assertEqual(rejected["pull_requests"], [f"{REPOSITORY}#7"])
        self.assertEqual(rejected["repair_owner"], noodles.OPEN_PR_REPAIR_OWNER)
        self.assertEqual(rejected["meaning"], skill_contract.SCHEDULE_CLAIM_STATUS_MEANINGS["open_pr_exists"])

    def test_open_pr_on_the_exact_lane_branch_is_refused_even_when_its_body_drifted(self) -> None:
        # constraint: ed3c/noodles#99 - the body correlation is unavailable when the PR body is not the
        # constraint: exact one-line `Refs`; the lane branch is the second, independent correlation.
        provider = FakeProvider(
            [issue(82)],
            pulls=[pull(9, body="WIP: no exact reference line", head_ref=noodles.execute_branch(f"{REPOSITORY}#82"))],
        )
        candidate = self.write_candidate([f"{REPOSITORY}#82"])
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            brief = noodles.schedule_publish(self.root, candidate)
        self.assertEqual(provider.posts, 0)
        self.assertEqual(self.published_orders(), [])
        self.assertEqual(brief["claims"][0]["status"], "open_pr_exists")
        self.assertEqual(brief["claims"][0]["pull_requests"], [f"{REPOSITORY}#9"])

    def test_open_pr_beyond_the_first_page_of_pull_requests_still_refuses_admission(self) -> None:
        # constraint: ed3c/noodles#99 - correlation must paginate the provider's open pull request
        # constraint: list the way open_issues already paginates issues; an unpaginated read would
        # constraint: silently stop matching past the first 100 open pull requests and admit a
        # constraint: duplicate lane whose real open PR sits on a later page.
        filler = [pull(100 + number, body=f"Refs {REPOSITORY}#{900 + number}", head_ref=f"filler-{number}") for number in range(100)]
        target = pull(9, body=f"Refs {REPOSITORY}#82", head_ref="fix-82-second-attempt")
        provider = FakeProvider([issue(82)], pulls=filler + [target])
        candidate = self.write_candidate([f"{REPOSITORY}#82"])
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            brief = noodles.schedule_publish(self.root, candidate)
        self.assertIn(2, provider.pull_pages)
        self.assertEqual(brief["claims"][0]["status"], "open_pr_exists")
        self.assertEqual(brief["claims"][0]["pull_requests"], [f"{REPOSITORY}#9"])

    def test_planted_negative_subject_with_no_open_pr_of_its_own_is_admitted(self) -> None:
        # constraint: ed3c/noodles#99 - the refusal must key on the exact subject, not on "any open PR
        # constraint: exists"; a sibling's in-flight PR must not starve an unrelated subject.
        provider = FakeProvider(
            [issue(82)],
            pulls=[pull(7, body=f"Refs {REPOSITORY}#90", head_ref=noodles.execute_branch(f"{REPOSITORY}#90"))],
        )
        candidate = self.write_candidate([f"{REPOSITORY}#82"])
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            brief = noodles.schedule_publish(self.root, candidate)
        self.assertEqual(provider.posts, 1)
        self.assertEqual([item["id"] for item in self.published_orders()], [f"{REPOSITORY}#82"])
        self.assertEqual(brief["claims"][0]["status"], "claimed")

    def test_unlanded_dependency_fails_closed_before_provider_ref_creation(self) -> None:
        predecessor = issue(81, state="ready")
        dependent = issue(82, depends_on=f"{REPOSITORY}#81")
        provider = FakeProvider([dependent], {81: predecessor, 82: dependent})
        candidate = self.write_candidate([f"{REPOSITORY}#82"])
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            brief = noodles.schedule_publish(self.root, candidate)
        self.assertEqual(provider.posts, 0)
        self.assertEqual(self.published_orders(), [])
        self.assertEqual(brief["max_useful_workers"], 0)

    def test_predecessor_drift_is_rechecked_immediately_before_claim(self) -> None:
        landed = issue(81, state="landed", provider_state="closed")
        open_predecessor = issue(81, state="ready")
        dependent = issue(82, depends_on=f"{REPOSITORY}#81")
        provider = FakeProvider([dependent], {81: landed, 82: dependent})
        predecessor_reads = 0
        original = provider.api

        def drift(endpoint: str, *, method: str = "GET", payload: object | None = None, token: str | None = None) -> object:
            nonlocal predecessor_reads
            if endpoint == f"repos/{REPOSITORY}/issues/81":
                predecessor_reads += 1
                return landed if predecessor_reads < 3 else open_predecessor
            return original(endpoint, method=method, payload=payload, token=token)

        candidate = self.write_candidate([f"{REPOSITORY}#82"])
        with mock.patch.object(noodles, "gh_api", side_effect=drift):
            brief = noodles.schedule_publish(self.root, candidate)
        self.assertEqual(predecessor_reads, 3)
        self.assertEqual(provider.posts, 0)
        self.assertNotIn(f"refs/heads/{noodles.execute_branch(f'{REPOSITORY}#82')}", provider.refs)
        self.assertEqual(self.published_orders(), [])
        self.assertEqual(brief["claims"][0]["status"], "dependency_changed")

    def test_absent_winner_is_named_not_in_winners_and_carries_its_meaning(self) -> None:
        predecessor = issue(81, state="ready")
        dependent = issue(82, depends_on=f"{REPOSITORY}#81")
        provider = FakeProvider([dependent], {81: predecessor, 82: dependent})
        candidate = self.write_candidate([f"{REPOSITORY}#82"])
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            brief = noodles.schedule_publish(self.root, candidate)
        self.assertEqual(brief["winners"], [])
        self.assertEqual(brief["claims"], [{
            "subject": f"{REPOSITORY}#82",
            "status": "not_in_winners",
            "meaning": skill_contract.SCHEDULE_CLAIM_STATUS_MEANINGS["not_in_winners"],
        }])
        self.assertEqual(skill_contract.validate_cycle_receipt(brief), [])
        with self.assertRaisesRegex(noodles.GateError, "undefined claim status: 'not_frontier'"):
            noodles.schedule_claim_outcome(f"{REPOSITORY}#82", "not_frontier")

    def test_foreign_repository_order_is_rejected_before_provider_call(self) -> None:
        # constraint: ed3c/noodles#65 - CONCURRENCY.PROMOTION_SEAM.001 attributes admitted-repository
        # constraint: (foreign) exclusion to noodles.schedule_publish; local_publish() in
        # constraint: test_schedule_contract.py only calls skill_contract.publish_schedule_output and
        # constraint: never reaches this check, so this is the only planted-negative proving the local
        # constraint: gate actually rejects a foreign-repo subject rather than the claim going unproven.
        provider = FakeProvider([])
        candidate = self.write_candidate(["someone-else/other#5"])
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            with self.assertRaisesRegex(
                noodles.GateError, r"schedule target repository is not admitted: someone-else/other"
            ):
                noodles.schedule_publish(self.root, candidate)
        self.assertEqual(provider.posts, 0)
        self.assertFalse((self.root / ".noodle/orders-next.json").exists())

    def test_duplicate_subject_order_is_rejected_before_provider_call(self) -> None:
        # constraint: ed3c/noodles#65 - same admission-boundary gap as above for duplicate-subject
        # constraint: exclusion, which also lives only in noodles.schedule_publish.
        provider = FakeProvider([])
        candidate = self.write_candidate([f"{REPOSITORY}#82", f"{REPOSITORY}#82"])
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            with self.assertRaisesRegex(
                noodles.GateError, rf"schedule candidate contains duplicate order: {REPOSITORY}#82"
            ):
                noodles.schedule_publish(self.root, candidate)
        self.assertEqual(provider.posts, 0)
        self.assertFalse((self.root / ".noodle/orders-next.json").exists())

    def test_planted_receipt_status_drift_fails_verify_closed(self) -> None:
        receipt_path = self.root / ".noodle/schedule-cycle.json"
        receipt_path.parent.mkdir(exist_ok=True)
        defined = skill_contract.SCHEDULE_CLAIM_STATUS_MEANINGS["not_in_winners"]
        base = {
            "schema_version": noodles.SCHEMA_VERSION,
            "frontier": [],
            "winners": [],
            "components": [],
            "max_useful_workers": 0,
            "claims": [],
            "destination": str(self.root / ".noodle/orders-next.json"),
        }
        plants = (
            ("retired status literal", {"status": "not_frontier", "meaning": defined}, "undefined status 'not_frontier'"),
            ("paraphrased meaning", {"status": "not_in_winners", "meaning": "already claimed"}, "must carry its exact meaning"),
        )
        for label, claim, diagnostic in plants:
            with self.subTest(plant=label):
                receipt_path.write_text(json.dumps(dict(base, claims=[{"subject": f"{REPOSITORY}#82", **claim}])))
                result = noodles.verify_repository(self.root, CANDIDATE_ROOT)
                self.assertFalse(result["ok"])
                self.assertTrue(any(diagnostic in item for item in result["errors"]), result["errors"])
        receipt_path.write_text(json.dumps(dict(base, claims=[{"subject": f"{REPOSITORY}#82", "status": "not_in_winners", "meaning": defined}])))
        self.assertEqual(
            [item for item in noodles.verify_repository(self.root, CANDIDATE_ROOT)["errors"] if "schedule cycle receipt" in item],
            [],
        )

    def test_cycle_summary_contradicting_the_receipt_fails_closed(self) -> None:
        provider = FakeProvider([issue(82)])
        candidate = self.write_candidate([f"{REPOSITORY}#82"])
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            brief = noodles.schedule_publish(self.root, candidate)
        quoted = "# cycle\n\n" + "\n".join(skill_contract.cycle_summary_lines(brief)) + "\n"
        self.assertIn(f"max_useful_workers: {brief['max_useful_workers']}", quoted)
        self.assertEqual(skill_contract.validate_cycle_summary(brief, quoted), [])
        contradiction = quoted.replace(f"{REPOSITORY}#82: claimed", f"{REPOSITORY}#82: not_in_winners", 1)
        self.assertNotEqual(contradiction, quoted)
        errors = skill_contract.validate_cycle_summary(brief, contradiction)
        self.assertTrue(any("does not quote the receipt verbatim" in item for item in errors), errors)
        summary_path = self.root / ".noodle/schedule-summary.md"
        with mock.patch.object(skill_contract.Path, "cwd", return_value=self.root), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as stderr:
            summary_path.write_text(quoted)
            self.assertEqual(skill_contract.main(["summary", str(summary_path)]), 0)
            summary_path.write_text(contradiction)
            self.assertEqual(skill_contract.main(["summary", str(summary_path)]), 1)
        self.assertIn("schedule summary FAIL", stderr.getvalue())

    def test_publish_cli_reports_the_cycle_worker_count(self) -> None:
        provider = FakeProvider([issue(82)])
        self.write_candidate([f"{REPOSITORY}#82"])
        stdout = io.StringIO()
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api), \
             mock.patch.object(skill_contract.Path, "cwd", return_value=self.root), \
             contextlib.redirect_stdout(stdout):
            self.assertEqual(skill_contract.main(["publish", ".noodle/orders-next.candidate.json"]), 0)
        self.assertIn("max_useful_workers=1", stdout.getvalue())
        self.assertEqual([item["id"] for item in self.published_orders()], [f"{REPOSITORY}#82"])

    def test_active_unrelated_sibling_no_longer_blocks_admission(self) -> None:
        active = issue(81, state="in_progress")
        provider = FakeProvider([active, issue(82)])
        provider.refs[f"refs/heads/{noodles.execute_branch(f'{REPOSITORY}#81')}"] = HEAD
        candidate = self.write_candidate([f"{REPOSITORY}#82"])
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            brief = noodles.schedule_publish(self.root, candidate)
        self.assertEqual(provider.posts, 1)
        self.assertEqual([item["id"] for item in self.published_orders()], [f"{REPOSITORY}#82"])
        self.assertEqual(brief["max_useful_workers"], 1)
        self.assertEqual(
            {item["subject"]: item["status"] for item in brief["claims"]},
            {f"{REPOSITORY}#82": "claimed"},
        )

    def test_active_dependency_predecessor_still_blocks_its_dependent(self) -> None:
        active = issue(81, state="in_progress")
        dependent = issue(82, depends_on=f"{REPOSITORY}#81")
        provider = FakeProvider([active, dependent], {81: active, 82: dependent})
        provider.refs[f"refs/heads/{noodles.execute_branch(f'{REPOSITORY}#81')}"] = HEAD
        candidate = self.write_candidate([f"{REPOSITORY}#82"])
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            brief = noodles.schedule_publish(self.root, candidate)
        self.assertEqual(provider.posts, 0)
        self.assertEqual(self.published_orders(), [])
        self.assertEqual(brief["max_useful_workers"], 0)

    def test_exact_active_ref_blocks_when_claimed_open_issue_is_malformed(self) -> None:
        malformed = issue(81)
        malformed["body"] = "missing exact contract"
        provider = FakeProvider([malformed, issue(82)])
        provider.refs[f"refs/heads/{noodles.execute_branch(f'{REPOSITORY}#81')}"] = HEAD
        candidate = self.write_candidate([f"{REPOSITORY}#82"])
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            brief = noodles.schedule_publish(self.root, candidate)
        self.assertEqual(provider.posts, 0)
        self.assertEqual(self.published_orders(), [])
        self.assertEqual(brief["max_useful_workers"], 0)

    def test_historical_ref_for_closed_issue_does_not_block_repository(self) -> None:
        provider = FakeProvider([issue(82)])
        provider.refs[f"refs/heads/{noodles.execute_branch(f'{REPOSITORY}#81')}"] = HEAD
        candidate = self.write_candidate([f"{REPOSITORY}#82"])
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            brief = noodles.schedule_publish(self.root, candidate)
        self.assertEqual(provider.posts, 1)
        self.assertEqual([item["id"] for item in self.published_orders()], [f"{REPOSITORY}#82"])
        self.assertEqual(brief["max_useful_workers"], 1)

    def test_unrelated_branch_names_do_not_block_the_repository(self) -> None:
        provider = FakeProvider([issue(82)])
        prefix = f"refs/heads/{REPOSITORY.replace('/', '-')}-"
        provider.refs.update({
            f"{prefix}82-1-execute": HEAD,
            f"{prefix}082-0-execute": HEAD,
            f"{prefix}82-0-execute-extra": HEAD,
            f"{prefix}feature": HEAD,
        })
        candidate = self.write_candidate([f"{REPOSITORY}#82"])
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            brief = noodles.schedule_publish(self.root, candidate)
        self.assertEqual(provider.posts, 1)
        self.assertEqual([item["id"] for item in self.published_orders()], [f"{REPOSITORY}#82"])
        self.assertEqual(brief["claims"][0]["status"], "claimed")

    def test_claim_rejection_is_clean_skip_with_no_local_order(self) -> None:
        provider = FakeProvider([issue(82)])
        original = provider.api

        def lose(endpoint: str, *, method: str = "GET", payload: object | None = None, token: str | None = None) -> object:
            if endpoint == f"repos/{REPOSITORY}/git/refs" and method == "POST":
                assert isinstance(payload, dict)
                provider.refs[str(payload["ref"])] = str(payload["sha"])
                provider.posts += 1
                raise noodles.GateError("provider rejected duplicate ref")
            return original(endpoint, method=method, payload=payload, token=token)

        candidate = self.write_candidate([f"{REPOSITORY}#82"])
        with mock.patch.object(noodles, "gh_api", side_effect=lose):
            brief = noodles.schedule_publish(self.root, candidate)
        self.assertEqual(provider.posts, 1)
        self.assertEqual(self.published_orders(), [])
        self.assertEqual(brief["claims"][0]["status"], "claimed_elsewhere")

    def test_noncanonical_candidate_subject_is_rejected_before_provider_writes(self) -> None:
        provider = FakeProvider([issue(82)])
        candidate = self.write_candidate([f" {REPOSITORY}#82 "])
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            with self.assertRaisesRegex(noodles.GateError, "order id is not canonical"):
                noodles.schedule_publish(self.root, candidate)
        self.assertEqual(provider.posts, 0)
        self.assertFalse((self.root / ".noodle/orders-next.json").exists())

    def test_complete_pagination_finds_p0_after_first_page(self) -> None:
        backlog = [issue(number, p0=False) for number in range(1, 101)] + [issue(101)]
        provider = FakeProvider(backlog)
        candidate = self.write_candidate([f"{REPOSITORY}#101"])
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            brief = noodles.schedule_publish(self.root, candidate)
        self.assertIn(2, provider.issue_pages)
        self.assertEqual(brief["frontier"], [f"{REPOSITORY}#101"])
        self.assertEqual([item["id"] for item in self.published_orders()], [f"{REPOSITORY}#101"])

    def test_two_schedule_publish_callers_create_one_ref_and_one_local_order(self) -> None:
        provider = FakeProvider([issue(82), issue(90)])
        second_root = Path(self.temp.name) / "repo-second"
        copy_tracked(CANDIDATE_ROOT, second_root)
        candidates = [
            self.write_candidate([f"{REPOSITORY}#82"]),
            second_root / ".noodle/orders-next.candidate.json",
        ]
        candidates[1].parent.mkdir(exist_ok=True)
        candidates[1].write_text(json.dumps({
            "orders": [{
                "id": f"{REPOSITORY}#82",
                "stages": [{"do": "execute", "model": EXECUTE_MODEL, "prompt": "next"}],
            }]
        }))
        create_barrier = threading.Barrier(2)
        original = provider.api

        def racing(endpoint: str, *, method: str = "GET", payload: object | None = None, token: str | None = None) -> object:
            if endpoint == f"repos/{REPOSITORY}/git/refs" and method == "POST":
                assert isinstance(payload, dict)
                self.assertEqual(payload["ref"], f"refs/heads/{noodles.execute_branch(f'{REPOSITORY}#82')}")
                create_barrier.wait(timeout=5)
            return original(endpoint, method=method, payload=payload, token=token)

        def publish(index: int) -> dict:
            root = self.root if index == 0 else second_root
            return noodles.schedule_publish(root, candidates[index])

        with mock.patch.object(noodles, "gh_api", side_effect=racing):
            with ThreadPoolExecutor(max_workers=2) as pool:
                briefs = list(pool.map(publish, range(2)))
        execute_refs = {
            ref for ref in provider.refs
            if ref.endswith("-0-execute")
        }
        self.assertEqual(execute_refs, {f"refs/heads/{noodles.execute_branch(f'{REPOSITORY}#82')}"})
        self.assertEqual(provider.posts, 2)
        self.assertCountEqual([brief["claims"][0]["status"] for brief in briefs], ["claimed", "claimed_elsewhere"])
        published = [
            json.loads((root / ".noodle/orders-next.json").read_text())["orders"]
            for root in (self.root, second_root)
        ]
        self.assertEqual(sum(bool(orders) for orders in published), 1)


# constraint: ed3c/noodles#290 - the live 2026-08-30 receipt, verbatim. `./noodles start` fail-closed on
# constraint: it for two days: today's validate_cycle_receipt correctly refuses the pre-#191 vocabulary,
# constraint: and nothing could ever regenerate it, because regeneration needs a schedule cycle and
# constraint: start refuses to run one while the stale receipt exists. The operator broke that loop by
# constraint: hand, archiving the bytes to .noodle/schedule-cycle.json.stale-vocab-20260830.
LIVE_STALE_CYCLE_RECEIPT = """{
  "claims": [
    {
      "status": "not_frontier",
      "subject": "ed3c/noodles#187"
    }
  ],
  "components": [],
  "destination": "/Users/neon/noodles/.noodle/orders-next.json",
  "frontier": [],
  "max_useful_workers": 0,
  "schema_version": 1
}
"""
LIVE_STALE_CYCLE_RECEIPT_SHA256 = "e9fcb989ec5b745566d51e4d881d5d9c6265320a64b0dc65ec0cf47a1ffa325d"
LIVE_STALE_CYCLE_RECEIPT_BYTES = 255


def valid_cycle_receipt() -> dict:
    status = "not_in_winners"
    return {
        "schema_version": 1,
        "frontier": [],
        "winners": [],
        "components": [],
        "max_useful_workers": 0,
        "destination": "/tmp/orders-next.json",
        "claims": [{
            "subject": "ed3c/noodles#187",
            "status": status,
            "meaning": skill_contract.SCHEDULE_CLAIM_STATUS_MEANINGS[status],
        }],
    }


def invalid_current_generation_receipt() -> dict:
    # constraint: ed3c/noodles#290 - current schema_version, current shape, one status the machine
    # constraint: never defined and never retired. This is the receipt retirement must NOT touch.
    receipt = valid_cycle_receipt()
    receipt["claims"][0]["status"] = "definitely_not_a_defined_status"
    receipt["claims"][0]["meaning"] = ""
    return receipt


class StaleCycleReceiptRetirementTests(unittest.TestCase):
    """ed3c/noodles#290 - a persisted receipt that outlived its status vocabulary wedged the host
    permanently. Retirement is archive-aside with a receipt, never a silent delete and never a silent
    accept, and it is scoped to receipts an earlier generation wrote."""

    def candidate(self, body: str) -> Path:
        temp = tempfile.TemporaryDirectory(prefix="noodles-stale-cycle-", ignore_cleanup_errors=True)
        self.addCleanup(temp.cleanup)
        root = Path(temp.name) / "repo"
        copy_tracked(CANDIDATE_ROOT, root)
        path = root / skill_contract.SCHEDULE_CYCLE_RECEIPT_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return root

    def receipt_path(self, root: Path) -> Path:
        return root / skill_contract.SCHEDULE_CYCLE_RECEIPT_PATH

    def archives(self, root: Path) -> list[Path]:
        return sorted(self.receipt_path(root).parent.glob(f"*{noodles.STALE_CYCLE_RECEIPT_SUFFIX}*"))

    def start(self, root: Path) -> None:
        """Drive the real `start_unattended` with only its pre-verification collaborator stubbed and a
        sentinel immediately after the gate, so what is asserted is start's own ordering."""
        with mock.patch.object(noodles, "control_checkout_admission", return_value={"branch": "main"}), \
                mock.patch.object(noodles, "runtime_check", side_effect=RuntimeError("reached-runtime-check")):
            noodles.start_unattended(root, "http://noodle.test", 0.25)

    def test_live_grounding_receipt_is_byte_intact_and_pre_191_vocabulary(self) -> None:
        payload = LIVE_STALE_CYCLE_RECEIPT.encode("utf-8")
        self.assertEqual(len(payload), LIVE_STALE_CYCLE_RECEIPT_BYTES)
        self.assertEqual(hashlib.sha256(payload).hexdigest(), LIVE_STALE_CYCLE_RECEIPT_SHA256)
        receipt = json.loads(LIVE_STALE_CYCLE_RECEIPT)
        self.assertEqual([claim["status"] for claim in receipt["claims"]], ["not_frontier"])
        self.assertNotIn("not_frontier", skill_contract.SCHEDULE_CLAIM_STATUS_MEANINGS)
        self.assertIn("not_frontier", skill_contract.RETIRED_SCHEDULE_CLAIM_STATUSES)
        self.assertNotIn("winners", receipt)
        self.assertNotEqual(skill_contract.validate_cycle_receipt(receipt), [])

    def test_stale_generation_receipt_is_retired_aside_and_start_proceeds(self) -> None:
        root = self.candidate(LIVE_STALE_CYCLE_RECEIPT)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaisesRegex(RuntimeError, "reached-runtime-check"):
                self.start(root)
        self.assertFalse(self.receipt_path(root).exists())
        archives = self.archives(root)
        self.assertEqual(len(archives), 1)
        self.assertEqual(archives[0].read_text(encoding="utf-8"), LIVE_STALE_CYCLE_RECEIPT)
        emitted = json.loads(stderr.getvalue().strip())["stale_cycle_receipt_retired"]
        self.assertEqual(emitted["sha256"], LIVE_STALE_CYCLE_RECEIPT_SHA256)
        self.assertEqual(emitted["bytes"], LIVE_STALE_CYCLE_RECEIPT_BYTES)
        self.assertEqual(emitted["archived_to"], str(archives[0]))
        self.assertIn("not_frontier", emitted["reason"])
        self.assertIn("retired vocabulary", emitted["reason"])
        self.assertTrue(emitted["validator_errors"])

    def test_planted_negative_invalid_current_generation_receipt_still_fails_closed(self) -> None:
        root = self.candidate(json.dumps(invalid_current_generation_receipt(), indent=2))
        before = self.receipt_path(root).read_bytes()
        with self.assertRaises(noodles.GateError) as raised:
            self.start(root)
        self.assertIn("repository verification failed", str(raised.exception))
        self.assertIn("definitely_not_a_defined_status", str(raised.exception))
        self.assertEqual(self.receipt_path(root).read_bytes(), before)
        self.assertEqual(self.archives(root), [])

    def test_positive_control_a_valid_current_receipt_is_never_touched(self) -> None:
        root = self.candidate(json.dumps(valid_cycle_receipt(), indent=2))
        before = self.receipt_path(root).read_bytes()
        with self.assertRaisesRegex(RuntimeError, "reached-runtime-check"):
            self.start(root)
        self.assertEqual(self.receipt_path(root).read_bytes(), before)
        self.assertEqual(self.archives(root), [])

    def test_retirement_never_dates_a_receipt_by_shape_alone(self) -> None:
        # constraint: ed3c/noodles#290 - every arm of the predicate, decided against the current
        # constraint: definitions. Only a retired status name or an older schema_version dates a
        # constraint: receipt; a broken shape does not, or retirement becomes laundering.
        dated = skill_contract.earlier_generation_cycle_receipt
        version = noodles.SCHEMA_VERSION
        self.assertIsNone(dated(valid_cycle_receipt(), schema_version=version))
        self.assertIsNone(dated(invalid_current_generation_receipt(), schema_version=version))
        self.assertIsNone(dated({"schema_version": version, "winners": "not-an-array"}, schema_version=version))
        self.assertIsNone(dated({"schema_version": version, "claims": [{"subject": "x"}]}, schema_version=version))
        self.assertIsNone(dated("not-an-object", schema_version=version))
        self.assertIn("predates", dated({"schema_version": version - 1}, schema_version=version) or "")
        self.assertIn("not_frontier", dated(json.loads(LIVE_STALE_CYCLE_RECEIPT), schema_version=version) or "")


class ClaimedBoundaryWideningTests(unittest.TestCase):
    """ed3c/noodles#296 - the re-check reads only the reservation set's CURRENT bytes.

    Driving these through `schedule_publish` would prove the same rule through a provider double;
    reading the rule directly is what lets a narrowing be shown as the same pair before and after,
    which no single cycle can express.
    """

    def test_intersecting_live_claims_report_the_earlier_claim_and_the_prefix(self) -> None:
        self.assertEqual(
            noodles.claimed_boundary_widening([
                (f"{REPOSITORY}#81", ("docs",)),
                (f"{REPOSITORY}#85", ("docs/design",)),
            ]),
            [(f"{REPOSITORY}#85", f"{REPOSITORY}#81", "docs/design")],
        )

    def test_narrowing_the_same_pair_is_never_refused(self) -> None:
        # constraint: ed3c/noodles#296 - the invariant binds to the marker's current bytes, so
        # constraint: there is no stored claim-time boundary for a narrowed marker to be judged
        # constraint: against: the pair that reported above simply stops reporting.
        self.assertEqual(
            noodles.claimed_boundary_widening([
                (f"{REPOSITORY}#81", ("docs",)),
                (f"{REPOSITORY}#85", ("noodles.py",)),
            ]),
            [],
        )

    def test_reserving_nothing_is_not_a_widening(self) -> None:
        self.assertEqual(
            noodles.claimed_boundary_widening([
                (f"{REPOSITORY}#81", ("docs",)),
                (f"{REPOSITORY}#85", ()),
            ]),
            [],
        )

    def test_planted_negative_an_undeclared_live_claim_is_not_reported_as_a_widening(self) -> None:
        # constraint: ed3c/noodles#296 - an undeclared boundary already blocks every overlapping
        # constraint: candidate closed at admission; pairing it against each sibling here would
        # constraint: manufacture a "widening" out of an Issue whose marker never changed.
        self.assertEqual(
            noodles.claimed_boundary_widening([
                (f"{REPOSITORY}#81", None),
                (f"{REPOSITORY}#85", ("noodles.py",)),
                (f"{REPOSITORY}#90", ("daemon_lease.py",)),
            ]),
            [],
        )

    def test_a_third_claim_is_judged_against_every_earlier_live_claim(self) -> None:
        self.assertEqual(
            noodles.claimed_boundary_widening([
                (f"{REPOSITORY}#81", ("docs",)),
                (f"{REPOSITORY}#85", ("noodles.py",)),
                (f"{REPOSITORY}#90", ("noodles.py",)),
            ]),
            [(f"{REPOSITORY}#90", f"{REPOSITORY}#85", "noodles.py")],
        )


class StruggleDetectorTests(unittest.TestCase):
    """ed3c/noodles#323 - retry counters bound attempts; these bound repetition.

    The burn this exists for is nineteen consecutive cycles with an identical signature and zero new
    evidence, which every record it left read as ordinary work. Both directions are asserted: the
    threshold fires on a repeated signature, and never on attempts that keep producing new evidence
    nor on a first failure."""

    SUBJECT = f"{REPOSITORY}#900"

    def attempt(
        self,
        *,
        controls: tuple[str, ...] = ("verify",),
        diagnostics: tuple[str, ...] = ("failure",),
        head: str = "a" * 40,
    ) -> schedule_domain.RepairAttempt:
        return schedule_domain.RepairAttempt(
            subject=self.SUBJECT, diagnostics=diagnostics, failing_controls=controls, head=head
        )

    def test_a_repeated_failure_keeps_its_signature_across_run_specific_volatiles(self) -> None:
        first = self.attempt(diagnostics=(
            "verify run #4812 at head 9c3f1ab2ee1 failed 2026-09-01T04:15:02Z after 91.4s",
            "/private/var/folders/kx/T/noodles-test-a1b2/repo: assertion failed",
        ))
        second = self.attempt(diagnostics=(
            "verify run #5107 at head 771abcd0f42 failed 2026-09-01T07:02:44Z after 88.1s",
            "/private/var/folders/kx/T/noodles-test-z9y8/repo: assertion failed",
        ))
        self.assertEqual(schedule_domain.attempt_signature(first), schedule_domain.attempt_signature(second))
        self.assertIn("assertion failed", schedule_domain.attempt_signature(first))

    def test_a_different_failure_and_a_different_failing_control_are_different_signatures(self) -> None:
        base = self.attempt()
        self.assertNotEqual(
            schedule_domain.attempt_signature(base),
            schedule_domain.attempt_signature(self.attempt(diagnostics=("a different failure",))),
        )
        self.assertNotEqual(
            schedule_domain.attempt_signature(base),
            schedule_domain.attempt_signature(self.attempt(controls=("verify", "trusted-preview"))),
        )

    def test_reordering_the_same_failures_is_not_new_evidence(self) -> None:
        self.assertEqual(
            schedule_domain.attempt_signature(self.attempt(diagnostics=("one", "two"), controls=("a", "b"))),
            schedule_domain.attempt_signature(self.attempt(diagnostics=("two", "one"), controls=("b", "a"))),
        )

    def test_the_threshold_of_same_signature_attempts_raises_a_named_struggle(self) -> None:
        history = [self.attempt() for _ in range(3)]
        self.assertIsNone(schedule_domain.struggle_verdict(history[:2], 3))
        verdict = schedule_domain.struggle_verdict(history, 3)
        assert verdict is not None
        self.assertEqual((verdict.subject, verdict.attempts, verdict.reason), (self.SUBJECT, 3, "same_signature"))
        self.assertEqual(verdict.signature, schedule_domain.attempt_signature(history[-1]))

    def test_a_single_failure_and_changing_signatures_never_raise_a_struggle(self) -> None:
        self.assertIsNone(schedule_domain.struggle_verdict([self.attempt()], 3))
        moving = [self.attempt(diagnostics=(f"failure {index}",), head=str(index) * 40) for index in range(6)]
        self.assertIsNone(schedule_domain.struggle_verdict(moving, 3))

    def test_new_evidence_resets_the_run_rather_than_only_delaying_it(self) -> None:
        history = [self.attempt(), self.attempt(), self.attempt(diagnostics=("something new",)), self.attempt()]
        self.assertIsNone(schedule_domain.struggle_verdict(history, 3))

    def test_a_revert_oscillation_raises_before_the_threshold_even_with_changing_signatures(self) -> None:
        history = [
            self.attempt(diagnostics=("first",), head="a" * 40),
            self.attempt(diagnostics=("second",), head="b" * 40),
            self.attempt(diagnostics=("third",), head="a" * 40),
        ]
        verdict = schedule_domain.struggle_verdict(history, 5)
        assert verdict is not None
        self.assertEqual(verdict.reason, "revert_oscillation")

    def test_a_threshold_below_two_and_a_mixed_subject_history_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least 2 attempts"):
            schedule_domain.struggle_verdict([self.attempt()], 1)
        other = schedule_domain.RepairAttempt(
            subject=f"{REPOSITORY}#901", diagnostics=("failure",), failing_controls=("verify",), head="a" * 40
        )
        with self.assertRaisesRegex(ValueError, "judged per subject"):
            schedule_domain.struggle_verdict([self.attempt(), other], 2)

    def test_the_declaration_round_trips_through_the_line_the_supervisor_reads(self) -> None:
        verdict = schedule_domain.struggle_verdict([self.attempt(), self.attempt()], 2)
        assert verdict is not None
        line = schedule_domain.struggle_declaration(verdict)
        self.assertEqual(
            schedule_domain.parse_struggle_declarations(f"noise\n{line}\nmore noise"),
            [{
                "subject": verdict.subject,
                "attempts": verdict.attempts,
                "reason": verdict.reason,
                "signature": verdict.signature,
            }],
        )
        self.assertEqual(schedule_domain.parse_struggle_declarations("nothing was declared here"), [])

    def test_the_repetition_bound_is_a_policy_value_and_not_a_code_literal(self) -> None:
        policy = json.loads((CANDIDATE_ROOT / "policy/fitness.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(policy["struggle_same_signature_attempts"], 2)
        for module in ("noodles.py", "schedule_domain.py"):
            source = (CANDIDATE_ROOT / module).read_text(encoding="utf-8")
            with self.subTest(module=module):
                self.assertNotIn("struggle_same_signature_attempts =", source)
                self.assertNotIn("STRUGGLE_SAME_SIGNATURE_ATTEMPTS", source)


# constraint: ed3c/noodles#407 - the six-mode fail-soft machine's fixtures live in this module rather
# constraint: than a new one because a new tests/ module importing schedule_domain adds one
# constraint: cross-surface import edge to `verify`, `carrier` and `docs`, whose standing counts are
# constraint: disclosed in AGENTS.md and policy/fitness.json - both outside this atom's declared
# constraint: write boundary, so a separate module could not be landed by this atom at all.
FAILSOFT_SOURCE = "provider-event-adapter"
FAILSOFT_OBSERVED_AT = "2026-09-03T11:41:00Z"


def provider_reading(
    *triggers: str, source: str = FAILSOFT_SOURCE, observed_at: str = FAILSOFT_OBSERVED_AT
) -> schedule_domain.ProviderReading:
    return schedule_domain.ProviderReading(triggers=triggers, source=source, observed_at=observed_at)


class ProviderModeTransitionTests(unittest.TestCase):
    """One fixture per transition class, each asserted in both directions.

    Every reading is planted through the machine's own testable seam rather than by degrading a real
    provider, which is what keeps the whole module side-effect free."""

    def assert_transition(self, current: str, trigger: str, expected: str) -> None:
        moved = schedule_domain.provider_mode_transition(current, provider_reading(trigger))
        self.assertIsNotNone(moved, f"{trigger} must move {current}")
        assert moved is not None
        self.assertEqual((moved.from_mode, moved.to_mode, moved.trigger), (current, expected, trigger))
        # constraint: the receipt must NAME the reading, not merely exist: source and instant both.
        self.assertIn(f"trigger {trigger}", moved.receipt)
        self.assertIn(f"source {FAILSOFT_SOURCE}", moved.receipt)
        self.assertIn(f"observed_at {FAILSOFT_OBSERVED_AT}", moved.receipt)
        self.assertEqual(schedule_domain.mode_transition_errors(moved), [])

    def test_claude_unavailable_enters_codex_only(self) -> None:
        self.assert_transition("NORMAL_HYBRID", "claude_unavailable", "CODEX_ONLY")

    def test_codex_write_quota_pressure_enters_read_only_drain(self) -> None:
        self.assert_transition("NORMAL_HYBRID", "codex_write_quota_pressure", "READ_ONLY_DRAIN")

    def test_all_execution_providers_unavailable_enters_admission_only(self) -> None:
        self.assert_transition("NORMAL_HYBRID", "execution_providers_unavailable", "ADMISSION_ONLY")

    def test_budget_exhausted_enters_paused_budget(self) -> None:
        self.assert_transition("NORMAL_HYBRID", "budget_exhausted", "PAUSED_BUDGET")

    def test_landing_authority_lost_enters_paused_authority(self) -> None:
        self.assert_transition("NORMAL_HYBRID", "landing_authority_lost", "PAUSED_AUTHORITY")

    def test_every_table_row_has_its_own_fixture_direction(self) -> None:
        """No transition class ships without a planted reading proving it fires."""
        for trigger, mode in schedule_domain.PROVIDER_TRANSITION_TABLE:
            with self.subTest(trigger=trigger):
                self.assert_transition("NORMAL_HYBRID", trigger, mode)

    def test_recovery_reading_reverses_each_transition_with_its_own_receipt(self) -> None:
        for _, mode in schedule_domain.PROVIDER_TRANSITION_TABLE:
            with self.subTest(mode=mode):
                recovered = schedule_domain.provider_mode_transition(mode, provider_reading())
                self.assertIsNotNone(recovered)
                assert recovered is not None
                self.assertEqual((recovered.from_mode, recovered.to_mode), (mode, "NORMAL_HYBRID"))
                self.assertEqual(recovered.trigger, schedule_domain.CLEAR_READING)
                self.assertIn(f"source {FAILSOFT_SOURCE}", recovered.receipt)
                self.assertEqual(schedule_domain.mode_transition_errors(recovered), [])

    def test_clear_reading_in_normal_hybrid_produces_no_transition(self) -> None:
        """The other direction of every recovery fixture: no move, so no receipt to emit."""
        self.assertIsNone(schedule_domain.provider_mode_transition("NORMAL_HYBRID", provider_reading()))

    def test_reading_that_repeats_the_current_mode_produces_no_transition(self) -> None:
        for trigger, mode in schedule_domain.PROVIDER_TRANSITION_TABLE:
            with self.subTest(trigger=trigger):
                self.assertIsNone(schedule_domain.provider_mode_transition(mode, provider_reading(trigger)))

    def test_unmeasured_trigger_is_refused_rather_than_read_as_clear(self) -> None:
        with self.assertRaises(ValueError) as caught:
            schedule_domain.provider_mode_transition("NORMAL_HYBRID", provider_reading("vibes_are_off"))
        self.assertIn("vibes_are_off", str(caught.exception))

    def test_unknown_current_mode_is_refused(self) -> None:
        with self.assertRaises(ValueError) as caught:
            schedule_domain.provider_mode_transition("BEST_EFFORT", provider_reading())
        self.assertIn("BEST_EFFORT", str(caught.exception))

    def test_table_covers_exactly_the_degraded_modes(self) -> None:
        """The modes are NORMAL_HYBRID plus one target per table row; no orphan mode, no orphan row."""
        targets = {mode for _, mode in schedule_domain.PROVIDER_TRANSITION_TABLE}
        self.assertEqual(targets | {"NORMAL_HYBRID"}, set(schedule_domain.PROVIDER_MODES))
        self.assertEqual(len(schedule_domain.PROVIDER_MODES), len(schedule_domain.PROVIDER_TRANSITION_TABLE) + 1)


class ProviderModeReceiptTests(unittest.TestCase):
    """A transition without a receipt is itself a validator error - planted."""

    def moved(self) -> schedule_domain.ModeTransition:
        moved = schedule_domain.provider_mode_transition("NORMAL_HYBRID", provider_reading("budget_exhausted"))
        assert moved is not None
        return moved

    def test_receiptless_transition_is_a_validator_error(self) -> None:
        errors = schedule_domain.mode_transition_errors(dataclasses.replace(self.moved(), receipt=""))
        self.assertTrue(errors)
        self.assertIn("carries no receipt", errors[0])

    def test_receipt_naming_a_different_move_is_a_validator_error(self) -> None:
        honest = self.moved()
        planted = dataclasses.replace(honest, receipt=honest.receipt.replace("to PAUSED_BUDGET", "to NORMAL_HYBRID"))
        errors = schedule_domain.mode_transition_errors(planted)
        self.assertTrue(errors)
        self.assertIn("but the transition is", errors[0])

    def test_honest_transition_passes_the_same_validator(self) -> None:
        self.assertEqual(schedule_domain.mode_transition_errors(self.moved()), [])


class ReadOnlyDrainVerbTests(unittest.TestCase):
    """Each direction asserted: the drain admits its enumerated verbs and refuses execution verbs."""

    def test_execution_verb_is_refused_with_the_mode_named(self) -> None:
        with self.assertRaises(ValueError) as caught:
            schedule_domain.admit_verb("READ_ONLY_DRAIN", "execute_handoff")
        message = str(caught.exception)
        self.assertIn("READ_ONLY_DRAIN", message)
        self.assertIn("execute_handoff", message)

    def test_classification_verb_is_admitted(self) -> None:
        self.assertEqual(schedule_domain.admit_verb("READ_ONLY_DRAIN", "classification"), "classification")

    def test_every_enumerated_drain_verb_is_admitted(self) -> None:
        for verb in sorted(schedule_domain.READ_ONLY_DRAIN_VERBS):
            with self.subTest(verb=verb):
                self.assertEqual(schedule_domain.admit_verb("READ_ONLY_DRAIN", verb), verb)

    def test_other_modes_carry_no_enumerated_verb_set(self) -> None:
        """Only READ_ONLY_DRAIN is enumerated by the ratified contract; nothing here invents more."""
        for mode in schedule_domain.PROVIDER_MODES:
            if mode == "READ_ONLY_DRAIN":
                continue
            with self.subTest(mode=mode):
                self.assertEqual(schedule_domain.admit_verb(mode, "execute_handoff"), "execute_handoff")

    def test_unknown_mode_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            schedule_domain.admit_verb("DRAINING", "classification")


class IdentityHardGateTests(unittest.TestCase):
    """No mode reachable by any transition admits an identity substitution."""

    def test_planted_substitution_under_paused_budget_is_a_validator_error(self) -> None:
        errors = schedule_domain.identity_substitution_errors("PAUSED_BUDGET", "github-app/noodles", "operator-pat")
        self.assertTrue(errors)
        self.assertIn("PAUSED_BUDGET", errors[0])
        self.assertIn("operator-pat", errors[0])

    def test_no_mode_admits_a_substitution(self) -> None:
        for mode in schedule_domain.PROVIDER_MODES:
            with self.subTest(mode=mode):
                self.assertTrue(schedule_domain.identity_substitution_errors(mode, "declared", "substituted"))

    def test_matching_identity_is_admitted_in_every_mode(self) -> None:
        """The planted control's other direction: the refusal fires on substitution, not on presence."""
        for mode in schedule_domain.PROVIDER_MODES:
            with self.subTest(mode=mode):
                self.assertEqual(schedule_domain.identity_substitution_errors(mode, "declared", "declared"), [])

    def test_every_mode_reachable_by_a_transition_is_covered(self) -> None:
        reachable = {"NORMAL_HYBRID"} | {mode for _, mode in schedule_domain.PROVIDER_TRANSITION_TABLE}
        self.assertEqual(reachable, set(schedule_domain.PROVIDER_MODES))


class BudgetDeferralClassificationTests(unittest.TestCase):
    """Terminal-classification duty: a budget deferral that classifies nothing is a validator error."""

    SUBJECTS = ("ed3c/noodles#407", "ed3c/noodles#408")
    RETRY = "core quota bucket refills"

    def classifications(self) -> tuple[schedule_domain.TerminalClassification, ...]:
        return schedule_domain.budget_deferral_classifications(
            provider_reading("budget_exhausted"), self.SUBJECTS, self.RETRY
        )

    def test_each_affected_subject_is_classified_deferred_budget_with_a_receipt(self) -> None:
        produced = self.classifications()
        self.assertEqual(tuple(item.subject for item in produced), self.SUBJECTS)
        for item in produced:
            with self.subTest(subject=item.subject):
                self.assertEqual(item.terminal_class, schedule_domain.DEFERRED_BUDGET)
                self.assertIn(f"budget_reading {FAILSOFT_SOURCE}@{FAILSOFT_OBSERVED_AT}", item.receipt)
                self.assertIn(f"retry {self.RETRY}", item.receipt)
        self.assertEqual(schedule_domain.budget_deferral_errors(self.SUBJECTS, produced), [])

    def test_deferral_that_classifies_nothing_is_a_validator_error(self) -> None:
        errors = schedule_domain.budget_deferral_errors(self.SUBJECTS, ())
        self.assertTrue(errors)
        self.assertIn("classified nothing", errors[0])

    def test_partial_classification_names_the_unclassified_subject(self) -> None:
        errors = schedule_domain.budget_deferral_errors(self.SUBJECTS, self.classifications()[:1])
        self.assertTrue(any("ed3c/noodles#408" in error for error in errors))

    def test_classification_under_another_class_is_refused(self) -> None:
        planted = tuple(dataclasses.replace(item, terminal_class="RESOLVED") for item in self.classifications())
        errors = schedule_domain.budget_deferral_errors(self.SUBJECTS, planted)
        self.assertTrue(any("as RESOLVED" in error for error in errors))

    def test_receipt_without_a_budget_reading_is_refused(self) -> None:
        planted = tuple(
            dataclasses.replace(
                item, receipt=item.receipt.replace(f"{FAILSOFT_SOURCE}@{FAILSOFT_OBSERVED_AT}", "")
            )
            for item in self.classifications()
        )
        errors = schedule_domain.budget_deferral_errors(self.SUBJECTS, planted)
        self.assertTrue(any("names no budget reading" in error for error in errors))

    def test_receipt_naming_another_subject_is_refused(self) -> None:
        planted = tuple(
            dataclasses.replace(item, receipt=item.receipt.replace(item.subject, "ed3c/noodles#999", 1))
            for item in self.classifications()
        )
        errors = schedule_domain.budget_deferral_errors(self.SUBJECTS, planted)
        self.assertTrue(any("names subject ed3c/noodles#999" in error for error in errors))

    def test_deferral_without_a_retry_condition_is_refused_at_production(self) -> None:
        with self.assertRaises(ValueError):
            schedule_domain.budget_deferral_classifications(provider_reading("budget_exhausted"), self.SUBJECTS, "  ")

    def test_no_affected_subjects_needs_no_classification(self) -> None:
        """A budget reading that defers nothing is not a failed duty; the duty is per deferred issue."""
        self.assertEqual(schedule_domain.budget_deferral_errors((), ()), [])


class FailSoftZeroWriteTests(unittest.TestCase):
    """The claim is 'zero provider writes, zero new write surface'. Reduced, not asserted in prose."""

    def test_the_whole_machine_writes_nothing_to_the_filesystem(self) -> None:
        with tempfile.TemporaryDirectory(prefix="noodles-407-zero-write-", ignore_cleanup_errors=True) as name:
            sandbox = Path(name)
            before = sorted(path.relative_to(sandbox) for path in sandbox.rglob("*"))
            cwd = Path.cwd()
            os.chdir(sandbox)
            try:
                for trigger, mode in schedule_domain.PROVIDER_TRANSITION_TABLE:
                    moved = schedule_domain.provider_mode_transition("NORMAL_HYBRID", provider_reading(trigger))
                    assert moved is not None
                    schedule_domain.mode_transition_errors(moved)
                    schedule_domain.provider_mode_transition(mode, provider_reading())
                    schedule_domain.identity_substitution_errors(mode, "declared", "substituted")
                schedule_domain.admit_verb("READ_ONLY_DRAIN", "classification")
                produced = schedule_domain.budget_deferral_classifications(
                    provider_reading("budget_exhausted"), ("ed3c/noodles#407",), "quota refills"
                )
                schedule_domain.budget_deferral_errors(("ed3c/noodles#407",), produced)
            finally:
                os.chdir(cwd)
            self.assertEqual(sorted(path.relative_to(sandbox) for path in sandbox.rglob("*")), before)

# constraint: ed3c/noodles#408 - the generation-closure predicate's fixtures share this module for the
# constraint: reason the #407 block above states: a new tests/ module importing schedule_domain moves
# constraint: cross-surface edge counts disclosed outside this atom's declared write boundary.
CLOSURE_RETRY = "the external dependency ships"


def admitted_issue(subject: str, terminal_class: str, **overrides: str) -> schedule_domain.AdmittedIssue:
    """One admitted issue carrying a receipted terminal class, with a retry condition whenever the
    class is one the generation may have to leave again."""
    return dataclasses.replace(
        schedule_domain.AdmittedIssue(
            subject=subject,
            terminal_class=terminal_class,
            receipt=f"NOODLES_TERMINAL_CLASS: subject {subject} class {terminal_class}",
            retry_condition="" if terminal_class == "RESOLVED" else CLOSURE_RETRY,
        ),
        **overrides,
    )


def closed_generation() -> schedule_domain.GenerationState:
    """A generation with one issue per terminal class and every liveness conjunct satisfied."""
    return schedule_domain.GenerationState(
        issues=tuple(
            admitted_issue(f"ed3c/noodles#{index}", name)
            for index, name in enumerate(schedule_domain.TERMINAL_CLASSES, start=1)
        )
    )


class EightClassClosureTests(unittest.TestCase):
    def test_generation_with_one_issue_per_class_is_closed(self) -> None:
        verdict = schedule_domain.generation_closure(closed_generation())
        self.assertEqual(verdict.blockers, ())
        self.assertTrue(verdict.closed)

    def test_the_fixture_covers_every_declared_terminal_class(self) -> None:
        covered = {item.terminal_class for item in closed_generation().issues}
        self.assertEqual(covered, set(schedule_domain.TERMINAL_CLASSES))

    def test_removing_any_one_receipt_flips_the_predicate_open_with_that_issue_named(self) -> None:
        base = closed_generation()
        for index, item in enumerate(base.issues):
            with self.subTest(terminal_class=item.terminal_class):
                planted = dataclasses.replace(
                    base,
                    issues=base.issues[:index] + (dataclasses.replace(item, receipt=""),) + base.issues[index + 1 :],
                )
                verdict = schedule_domain.generation_closure(planted)
                self.assertFalse(verdict.closed)
                self.assertTrue(any(item.subject in blocker for blocker in verdict.blockers))
                self.assertTrue(any(blocker.startswith("terminal_classification:") for blocker in verdict.blockers))

    def test_a_non_resolved_class_without_a_retry_condition_holds_closure_open(self) -> None:
        base = closed_generation()
        for index, item in enumerate(base.issues):
            if item.terminal_class == "RESOLVED":
                continue
            with self.subTest(terminal_class=item.terminal_class):
                planted = dataclasses.replace(
                    base,
                    issues=base.issues[:index]
                    + (dataclasses.replace(item, retry_condition=" "),)
                    + base.issues[index + 1 :],
                )
                verdict = schedule_domain.generation_closure(planted)
                self.assertFalse(verdict.closed)
                self.assertTrue(any("no named retry condition" in blocker for blocker in verdict.blockers))

    def test_an_unclassified_issue_holds_closure_open_and_is_named(self) -> None:
        state = schedule_domain.GenerationState(issues=(schedule_domain.AdmittedIssue("ed3c/noodles#500"),))
        verdict = schedule_domain.generation_closure(state)
        self.assertFalse(verdict.closed)
        self.assertEqual(verdict.blockers, ("terminal_classification: ed3c/noodles#500 carries no terminal class",))

    def test_an_empty_generation_is_closed(self) -> None:
        self.assertTrue(schedule_domain.generation_closure(schedule_domain.GenerationState()).closed)


class ClosureMasqueradeTests(unittest.TestCase):
    """BLOCKED_EXTERNAL can never satisfy the RESOLVED arm."""

    def test_external_blockage_presented_as_resolved_is_a_validator_error(self) -> None:
        planted = admitted_issue("ed3c/noodles#501", "RESOLVED", external_blocker="upstream poteto/noodle release")
        with self.assertRaises(ValueError) as caught:
            schedule_domain.generation_closure(schedule_domain.GenerationState(issues=(planted,)))
        message = str(caught.exception)
        self.assertIn("ed3c/noodles#501", message)
        self.assertIn("RESOLVED", message)

    def test_the_same_blockage_declared_honestly_is_admitted(self) -> None:
        """The planted control's other direction: the refusal fires on the LIE, not on the blocker."""
        honest = admitted_issue(
            "ed3c/noodles#501", "BLOCKED_EXTERNAL", external_blocker="upstream poteto/noodle release"
        )
        self.assertTrue(schedule_domain.generation_closure(schedule_domain.GenerationState(issues=(honest,))).closed)

    def test_an_undeclared_terminal_class_is_a_validator_error(self) -> None:
        planted = admitted_issue("ed3c/noodles#502", "PROBABLY_FINE")
        with self.assertRaises(ValueError) as caught:
            schedule_domain.generation_closure(schedule_domain.GenerationState(issues=(planted,)))
        self.assertIn("PROBABLY_FINE", str(caught.exception))

    def test_a_resolved_issue_with_no_blocker_is_admitted(self) -> None:
        self.assertEqual(
            schedule_domain.terminal_classification_errors((admitted_issue("ed3c/noodles#503", "RESOLVED"),)), []
        )


class ClosureLivenessConjunctTests(unittest.TestCase):
    """One fixture per liveness conjunct, each independently holding closure open with itself named."""

    def assert_conjunct(self, conjunct: str, **override: object) -> None:
        base = closed_generation()
        self.assertTrue(schedule_domain.generation_closure(base).closed, "the base fixture must be closed")
        verdict = schedule_domain.generation_closure(dataclasses.replace(base, **override))
        self.assertFalse(verdict.closed)
        self.assertTrue(
            any(blocker.startswith(f"{conjunct}:") for blocker in verdict.blockers),
            f"{conjunct} must name itself; got {verdict.blockers}",
        )

    def test_a_planted_active_lane_holds_closure_open(self) -> None:
        self.assert_conjunct("no_active_lanes", active_lanes=("lane-a",))

    def test_a_completed_unreconciled_lane_holds_closure_open(self) -> None:
        self.assert_conjunct("no_unreconciled_lanes", unreconciled_lanes=("lane-b",))

    def test_a_non_empty_landing_train_holds_closure_open(self) -> None:
        self.assert_conjunct("empty_landing_train", landing_train=("pr-77",))

    def test_an_unaccounted_finding_holds_closure_open(self) -> None:
        self.assert_conjunct("findings_accounted", unaccounted_findings=("finding-12",))

    def test_a_non_zero_sweeper_balance_holds_closure_open(self) -> None:
        self.assert_conjunct("sweeper_balance_zero", sweeper_balance=1)

    def test_a_negative_sweeper_balance_holds_closure_open(self) -> None:
        """Balance is a balance, not a count: an over-reconciled sweeper is as unreconciled as an
        under-reconciled one, and reading it as `> 0` would silently admit the negative half."""
        self.assert_conjunct("sweeper_balance_zero", sweeper_balance=-1)

    def test_an_uncommitted_ledger_holds_closure_open(self) -> None:
        self.assert_conjunct("ledgers_committed", uncommitted_ledgers=("evidence-ledger",))

    def test_every_declared_conjunct_has_a_fixture(self) -> None:
        """Seven conjuncts; the classification arm is covered by EightClassClosureTests above."""
        planted = {
            "no_active_lanes": {"active_lanes": ("lane-a",)},
            "no_unreconciled_lanes": {"unreconciled_lanes": ("lane-b",)},
            "empty_landing_train": {"landing_train": ("pr-77",)},
            "findings_accounted": {"unaccounted_findings": ("finding-12",)},
            "sweeper_balance_zero": {"sweeper_balance": 1},
            "ledgers_committed": {"uncommitted_ledgers": ("evidence-ledger",)},
        }
        self.assertEqual(set(planted) | {"terminal_classification"}, set(schedule_domain.CLOSURE_CONJUNCTS))
        for conjunct, override in planted.items():
            with self.subTest(conjunct=conjunct):
                self.assert_conjunct(conjunct, **override)

    def test_conjuncts_accumulate_rather_than_short_circuiting(self) -> None:
        """The output names EVERY blocker; a predicate that stops at the first one hides the rest."""
        verdict = schedule_domain.generation_closure(
            dataclasses.replace(closed_generation(), active_lanes=("lane-a",), sweeper_balance=3)
        )
        self.assertEqual(
            {blocker.split(":", 1)[0] for blocker in verdict.blockers},
            {"no_active_lanes", "sweeper_balance_zero"},
        )


class DeferredBudgetConsumerTests(unittest.TestCase):
    """ed3c/noodles#407's classification duty, asserted from the consumer side.

    The producer proves it emits DEFERRED_BUDGET receipts; this proves the predicate ACCEPTS them.
    A producer whose output no consumer reads is not a duty, it is a decoration."""

    def test_a_budget_deferral_classification_closes_its_issue(self) -> None:
        produced = schedule_domain.budget_deferral_classifications(
            provider_reading("budget_exhausted"), ("ed3c/noodles#407",), "core quota bucket refills"
        )
        state = schedule_domain.GenerationState(
            issues=tuple(
                schedule_domain.AdmittedIssue(
                    subject=item.subject,
                    terminal_class=item.terminal_class,
                    receipt=item.receipt,
                    retry_condition=item.retry_condition,
                )
                for item in produced
            )
        )
        self.assertTrue(schedule_domain.generation_closure(state).closed)

    def test_a_budget_deferral_that_classified_nothing_leaves_the_generation_open(self) -> None:
        state = schedule_domain.GenerationState(issues=(schedule_domain.AdmittedIssue("ed3c/noodles#407"),))
        verdict = schedule_domain.generation_closure(state)
        self.assertFalse(verdict.closed)
        self.assertTrue(any("ed3c/noodles#407" in blocker for blocker in verdict.blockers))
        self.assertTrue(schedule_domain.budget_deferral_errors(("ed3c/noodles#407",), ()))


class ClosureZeroWriteTests(unittest.TestCase):
    """"The predicate performs zero writes, asserted by its fixtures" - reduced physically."""

    def test_evaluating_the_predicate_writes_nothing_to_the_filesystem(self) -> None:
        with tempfile.TemporaryDirectory(prefix="noodles-408-zero-write-", ignore_cleanup_errors=True) as name:
            sandbox = Path(name)
            before = sorted(path.relative_to(sandbox) for path in sandbox.rglob("*"))
            cwd = Path.cwd()
            os.chdir(sandbox)
            try:
                schedule_domain.generation_closure(closed_generation())
                schedule_domain.generation_closure(
                    dataclasses.replace(closed_generation(), active_lanes=("lane-a",), sweeper_balance=2)
                )
                schedule_domain.terminal_classification_errors(closed_generation().issues)
            finally:
                os.chdir(cwd)
            self.assertEqual(sorted(path.relative_to(sandbox) for path in sandbox.rglob("*")), before)

# constraint: ed3c/noodles#410 - the mint's fixtures share this module for the reason the #407 block
# constraint: above states: a new tests/ module importing schedule_domain moves cross-surface edge
# constraint: counts disclosed outside this atom's declared write boundary.
class GenerationMintTests(unittest.TestCase):
    def test_successive_mints_are_unique_and_monotonic(self) -> None:
        mint = schedule_domain.GenerationMint()
        minted = [mint.mint(f"wave {index}") for index in range(1, 6)]
        identifiers = [item.identifier for item in minted]
        self.assertEqual(len(set(identifiers)), len(identifiers))
        self.assertEqual([item.ordinal for item in minted], [1, 2, 3, 4, 5])
        # constraint: monotonic in the identifier itself, not only in the registry: a ledger that
        # constraint: sorts by key must sort by generation without consulting the mint.
        self.assertEqual(identifiers, sorted(identifiers))

    def test_the_same_context_minted_twice_yields_two_distinct_identifiers(self) -> None:
        """Uniqueness is the mint's job, not the caller's: two waves named alike are still two waves."""
        mint = schedule_domain.GenerationMint()
        first, second = mint.mint("wave 27"), mint.mint("wave 27")
        self.assertNotEqual(first.identifier, second.identifier)
        self.assertLess(first.ordinal, second.ordinal)

    def test_each_mint_carries_a_receipt_naming_the_generation_context(self) -> None:
        minted = schedule_domain.GenerationMint().mint("scheduler fallback canary")
        self.assertIn("context scheduler fallback canary", minted.receipt)
        self.assertIn(f"id {minted.identifier}", minted.receipt)
        self.assertEqual(schedule_domain.mint_receipt_errors(minted), [])

    def test_a_receipt_naming_another_id_is_a_validator_error(self) -> None:
        minted = schedule_domain.GenerationMint().mint("wave 27")
        planted = dataclasses.replace(minted, receipt=minted.receipt.replace(minted.identifier, "g000099-forged", 1))
        errors = schedule_domain.mint_receipt_errors(planted)
        self.assertTrue(errors)
        self.assertIn("g000099-forged", errors[0])

    def test_a_receipt_naming_another_context_is_a_validator_error(self) -> None:
        """Id and ordinal can both match while the receipt claims a different generation - which is
        the forgery shape that survives an id-only check."""
        minted = schedule_domain.GenerationMint().mint("wave 27")
        planted = dataclasses.replace(minted, receipt=minted.receipt.replace("context wave 27", "context wave 99"))
        errors = schedule_domain.mint_receipt_errors(planted)
        self.assertTrue(errors)
        self.assertIn("wave 99", errors[0])

    def test_a_receiptless_mint_is_a_validator_error(self) -> None:
        minted = schedule_domain.GenerationMint().mint("wave 27")
        errors = schedule_domain.mint_receipt_errors(dataclasses.replace(minted, receipt=""))
        self.assertTrue(errors)
        self.assertIn("carries no receipt", errors[0])

    def test_an_unmintable_context_is_refused(self) -> None:
        for context in ("", "   ", "wave/27", "WAVE#27!"):
            with self.subTest(context=context):
                with self.assertRaises(ValueError):
                    schedule_domain.GenerationMint().mint(context)

    def test_the_registry_carries_every_minted_id_and_nothing_else(self) -> None:
        mint = schedule_domain.GenerationMint()
        minted = [mint.mint("wave 27"), mint.mint("wave 28")]
        self.assertEqual([item.identifier for item in mint.registry], sorted(item.identifier for item in minted))


class UnmintedIdentifierRefusalTests(unittest.TestCase):
    """Both directions: a never-minted id is refused by name, a minted id passes the same consumer."""

    def setUp(self) -> None:
        self.mint = schedule_domain.GenerationMint()
        self.minted = self.mint.mint("wave 27")

    def test_a_never_minted_identifier_is_a_validator_error_naming_the_id(self) -> None:
        errors = schedule_domain.minted_id_errors(self.mint, "wave-27-final-FINAL")
        self.assertTrue(errors)
        self.assertIn("wave-27-final-FINAL", errors[0])
        self.assertIn("never minted", errors[0])

    def test_a_minted_identifier_passes_the_same_consumer(self) -> None:
        self.assertEqual(schedule_domain.minted_id_errors(self.mint, self.minted.identifier), [])

    def test_an_identifier_minted_by_another_registry_is_refused(self) -> None:
        """Forgery is not only free-form text: a well-shaped id from a foreign mint is unminted here,
        which is exactly the case a syntax check would have waved through."""
        other = schedule_domain.GenerationMint()
        errors = schedule_domain.minted_id_errors(other, self.minted.identifier)
        self.assertTrue(errors)
        self.assertIn(self.minted.identifier, errors[0])
        self.assertEqual(schedule_domain.minted_id_errors(self.mint, self.minted.identifier), [])

    def test_an_absent_identifier_is_a_distinct_refusal_rather_than_a_silent_pass(self) -> None:
        with self.assertRaises(ValueError):
            schedule_domain.minted_id_errors(self.mint, "   ")


class MintZeroWriteTests(unittest.TestCase):
    """"Zero-write predicate on validation: checking an id performs no writes." """

    def test_validating_an_identifier_writes_nothing_to_the_filesystem(self) -> None:
        mint = schedule_domain.GenerationMint()
        minted = mint.mint("wave 27")
        with tempfile.TemporaryDirectory(prefix="noodles-410-zero-write-", ignore_cleanup_errors=True) as name:
            sandbox = Path(name)
            before = sorted(path.relative_to(sandbox) for path in sandbox.rglob("*"))
            cwd = Path.cwd()
            os.chdir(sandbox)
            try:
                schedule_domain.minted_id_errors(mint, minted.identifier)
                schedule_domain.minted_id_errors(mint, "never-minted")
                schedule_domain.mint_receipt_errors(minted)
            finally:
                os.chdir(cwd)
            self.assertEqual(sorted(path.relative_to(sandbox) for path in sandbox.rglob("*")), before)

# constraint: ed3c/noodles#393 - the declared-capacity controller's fixtures share this module for the
# constraint: reason the #407 block above states. The two memory readings below are the incident's
# constraint: REAL readings, carried from the issue's observer demonstration rather than invented.
# constraint: sysctl vm.swapusage, 2026-09-03 12:0x - total = 3072.00M used = 2029.88M free = 1042.12M
GREEN_SWAP_USED_MB = 2029.88
# constraint: sysctl vm.swapusage, 2026-09-03 11:41 - total = 4096.00M used = 2416.25M free = 1679.75M
RED_SWAP_USED_MB = 2416.25
DECLARED_CAPACITY = schedule_domain.DeclaredCapacity(
    swap_ceiling_mb=3072.00, swap_headroom_floor_mb=1024.00, landing_queue_target=2
)


def capacity_reading(*, swap_used_mb: float = GREEN_SWAP_USED_MB, depth: int = 0) -> schedule_domain.CapacityReading:
    return schedule_domain.CapacityReading(swap_used_mb=swap_used_mb, landing_queue_depth=depth)


class MemoryHeadroomAdmissionTests(unittest.TestCase):
    """Both directions, planted through the controller's seam rather than by exhausting the host."""

    def test_the_storm_reading_refuses_the_next_dispatch_slot_naming_signal_and_reading(self) -> None:
        refusal = schedule_domain.capacity_refusal(
            "dispatch-slot", capacity_reading(swap_used_mb=RED_SWAP_USED_MB), DECLARED_CAPACITY
        )
        self.assertIsNotNone(refusal)
        assert refusal is not None
        self.assertIn("signal host_memory_headroom", refusal)
        self.assertIn(f"swap_used={RED_SWAP_USED_MB:.2f}M", refusal)
        self.assertIn("floor=1024.00M", refusal)
        self.assertEqual(schedule_domain.refusal_reason_errors(refusal), [])

    def test_the_recovering_reading_admits_the_same_slot(self) -> None:
        self.assertIsNone(schedule_domain.capacity_refusal("dispatch-slot", capacity_reading(), DECLARED_CAPACITY))

    def test_the_same_gate_admits_and_refuses_a_full_suite_run(self) -> None:
        """The Goal gates two slots on one pair of signals; the slot is named so a receipt says which."""
        refusal = schedule_domain.capacity_refusal(
            "full-suite", capacity_reading(swap_used_mb=RED_SWAP_USED_MB), DECLARED_CAPACITY
        )
        assert refusal is not None
        self.assertIn("slot full-suite", refusal)
        self.assertIsNone(schedule_domain.capacity_refusal("full-suite", capacity_reading(), DECLARED_CAPACITY))

    def test_headroom_is_measured_against_the_declared_ceiling_not_the_observed_total(self) -> None:
        """The incident's own inversion: the storm reported MORE free swap (1679.75M) than the
        recovery (1042.12M), because the kernel grew total from 3072M to 4096M. A controller reading
        the observed total would have admitted straight into the near-shutdown."""
        self.assertGreater(4096.00 - RED_SWAP_USED_MB, 3072.00 - GREEN_SWAP_USED_MB)
        self.assertIsNotNone(
            schedule_domain.capacity_refusal(
                "dispatch-slot", capacity_reading(swap_used_mb=RED_SWAP_USED_MB), DECLARED_CAPACITY
            )
        )

    def test_headroom_exactly_at_the_floor_is_admitted(self) -> None:
        """The floor is a floor: at it, not below it. The recovery reading sits 18.12M above it."""
        at_floor = schedule_domain.CapacityReading(
            swap_used_mb=DECLARED_CAPACITY.swap_ceiling_mb - DECLARED_CAPACITY.swap_headroom_floor_mb,
            landing_queue_depth=0,
        )
        self.assertIsNone(schedule_domain.capacity_refusal("dispatch-slot", at_floor, DECLARED_CAPACITY))

    def test_an_unnamed_slot_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            schedule_domain.capacity_refusal("  ", capacity_reading(), DECLARED_CAPACITY)


class LandingQueueDepthTests(unittest.TestCase):
    """A planted queue at target depth defers new slot admission; below target, admission proceeds."""

    def test_a_queue_at_target_depth_defers_admission(self) -> None:
        refusal = schedule_domain.capacity_refusal("dispatch-slot", capacity_reading(depth=2), DECLARED_CAPACITY)
        self.assertIsNotNone(refusal)
        assert refusal is not None
        self.assertIn("signal landing_queue_depth", refusal)
        self.assertIn("depth=2", refusal)
        self.assertIn("target=2", refusal)
        self.assertEqual(schedule_domain.refusal_reason_errors(refusal), [])

    def test_a_queue_below_target_admits(self) -> None:
        self.assertIsNone(
            schedule_domain.capacity_refusal("dispatch-slot", capacity_reading(depth=1), DECLARED_CAPACITY)
        )

    def test_a_landing_that_drains_the_queue_reopens_admission(self) -> None:
        """The deferral is feedback, not a latch: the same controller admits once the queue drains."""
        self.assertIsNotNone(
            schedule_domain.capacity_refusal("dispatch-slot", capacity_reading(depth=3), DECLARED_CAPACITY)
        )
        self.assertIsNone(
            schedule_domain.capacity_refusal("dispatch-slot", capacity_reading(depth=1), DECLARED_CAPACITY)
        )

    def test_memory_is_checked_before_queue_depth(self) -> None:
        """A host with no headroom must not be admitted because its queue happens to be short."""
        refusal = schedule_domain.capacity_refusal(
            "dispatch-slot", capacity_reading(swap_used_mb=RED_SWAP_USED_MB, depth=0), DECLARED_CAPACITY
        )
        assert refusal is not None
        self.assertIn("signal host_memory_headroom", refusal)


class CapacityRefusalReasonTests(unittest.TestCase):
    """Planted negative: a refusal reason that names no signal/reading is a validator error."""

    def test_a_reason_naming_no_signal_is_a_validator_error(self) -> None:
        errors = schedule_domain.refusal_reason_errors("not right now")
        self.assertTrue(errors)
        self.assertIn("names no signal and no reading", errors[0])

    def test_a_reason_naming_an_undeclared_signal_is_a_validator_error(self) -> None:
        errors = schedule_domain.refusal_reason_errors(
            "NOODLES_CAPACITY_REFUSED: slot dispatch-slot signal operator_hunch reading depth=2"
        )
        self.assertTrue(errors)
        self.assertIn("operator_hunch", errors[0])

    def test_a_reason_naming_a_signal_but_no_measured_reading_is_a_validator_error(self) -> None:
        errors = schedule_domain.refusal_reason_errors(
            "NOODLES_CAPACITY_REFUSED: slot dispatch-slot signal landing_queue_depth reading too deep"
        )
        self.assertTrue(errors)
        self.assertIn("no measured reading", errors[0])

    def test_every_refusal_the_controller_emits_passes_its_own_validator(self) -> None:
        for planted in (capacity_reading(swap_used_mb=RED_SWAP_USED_MB), capacity_reading(depth=2)):
            with self.subTest(planted=planted):
                refusal = schedule_domain.capacity_refusal("dispatch-slot", planted, DECLARED_CAPACITY)
                assert refusal is not None
                self.assertEqual(schedule_domain.refusal_reason_errors(refusal), [])


class TopologicalOrderingTests(unittest.TestCase):
    """Two schedulable atoms where one is a chain tail: the shallower is selected first."""

    CHAIN = {"ed3c/noodles#407": (), "ed3c/noodles#408": ("ed3c/noodles#407",)}

    def test_the_shallower_atom_is_selected_first(self) -> None:
        self.assertEqual(schedule_domain.admission_order(self.CHAIN)[0], "ed3c/noodles#407")

    def test_depth_is_the_length_of_the_chain_beneath_a_subject(self) -> None:
        self.assertEqual(
            schedule_domain.topological_depth({"a": (), "b": ("a",), "c": ("b",), "d": ("a",)}),
            {"a": 0, "b": 1, "c": 2, "d": 1},
        )

    def test_a_deep_tail_is_offered_last_even_when_its_subject_sorts_first(self) -> None:
        """Depth beats the name, or the ordering key would be decorative."""
        self.assertEqual(schedule_domain.admission_order({"aaa": ("zzz",), "zzz": ()}), ("zzz", "aaa"))

    def test_a_dependency_outside_the_map_does_not_deepen_a_subject(self) -> None:
        """Already-landed or foreign dependencies are not chains this scheduler waits through."""
        self.assertEqual(schedule_domain.topological_depth({"a": ("landed/elsewhere#1",)}), {"a": 0})

    def test_a_dependency_cycle_is_refused_rather_than_ordered(self) -> None:
        with self.assertRaises(ValueError) as caught:
            schedule_domain.admission_order({"a": ("b",), "b": ("a",)})
        self.assertIn("cycle", str(caught.exception))

    def test_siblings_at_one_depth_keep_a_deterministic_order(self) -> None:
        self.assertEqual(schedule_domain.admission_order({"b": (), "a": (), "c": ("a",)}), ("a", "b", "c"))


class WriteBoundaryCollisionKeyTests(unittest.TestCase):
    """ed3c/noodles#393 operator amendment, 2026-09-03: the collision key binds at candidate
    production, so the rebase tax is never paid at landing."""

    SHARED = {"ed3c/noodles#407": ("tests",), "ed3c/noodles#408": ("tests", "docs")}
    DISJOINT = {"ed3c/noodles#407": ("schedule_domain.py",), "ed3c/noodles#408": ("noodles.py",)}

    def test_two_atoms_sharing_one_boundary_segment_are_serialized_with_the_overlap_named(self) -> None:
        order = schedule_domain.admission_order({"ed3c/noodles#407": (), "ed3c/noodles#408": ()})
        admitted, refusals = schedule_domain.codispatch_admission(order, self.SHARED)
        self.assertEqual(admitted, ("ed3c/noodles#407",))
        self.assertEqual(len(refusals), 1)
        self.assertIn("subject ed3c/noodles#408", refusals[0])
        self.assertIn("held behind ed3c/noodles#407", refusals[0])
        self.assertIn("on boundary tests", refusals[0])
        self.assertIsNotNone(schedule_domain.COLLISION_SERIALIZED_RE.search(refusals[0]))

    def test_disjoint_boundaries_co_dispatch(self) -> None:
        """The other direction: the key serializes collisions, it does not serialize everything."""
        order = schedule_domain.admission_order({"ed3c/noodles#407": (), "ed3c/noodles#408": ()})
        admitted, refusals = schedule_domain.codispatch_admission(order, self.DISJOINT)
        self.assertEqual(admitted, ("ed3c/noodles#407", "ed3c/noodles#408"))
        self.assertEqual(refusals, ())

    def test_overlap_is_judged_segment_wise_through_the_shared_exit(self) -> None:
        """`tests` must not collide with `tests2`. Asserted here because the whole value of routing
        through issue_contract.boundary_conflict is that this semantics cannot drift into a second
        predicate (the ed3c/noodles#272 shape)."""
        admitted, refusals = schedule_domain.codispatch_admission(("a", "b"), {"a": ("tests",), "b": ("tests2",)})
        self.assertEqual(admitted, ("a", "b"))
        self.assertEqual(refusals, ())

    def test_a_nested_prefix_still_collides(self) -> None:
        admitted, refusals = schedule_domain.codispatch_admission(
            ("a", "b"), {"a": ("tests",), "b": ("tests/support.py",)}
        )
        self.assertEqual(admitted, ("a",))
        self.assertIn("on boundary tests/support.py", refusals[0])

    def test_an_undeclared_boundary_fails_closed(self) -> None:
        """A lane that could write anywhere cannot be proven disjoint from anything."""
        admitted, refusals = schedule_domain.codispatch_admission(("a", "b"), {"a": ("noodles.py",), "b": None})
        self.assertEqual(admitted, ("a",))
        self.assertIn("undeclared", refusals[0])
        self.assertIn("subject b", refusals[0])

    def test_an_empty_boundary_reserves_nothing_and_always_co_dispatches(self) -> None:
        """`()` and `None` are deliberately different values: declared-nothing vs declared-nothing-yet."""
        admitted, refusals = schedule_domain.codispatch_admission(("a", "b"), {"a": ("tests",), "b": ()})
        self.assertEqual(admitted, ("a", "b"))
        self.assertEqual(refusals, ())

    def test_the_ordering_key_decides_who_keeps_the_slot(self) -> None:
        """A collision is resolved in admission order, so the shallower atom is not displaced by a
        deep tail that happens to be named first."""
        order = schedule_domain.admission_order({"aaa": ("zzz",), "zzz": ()})
        self.assertEqual(order, ("zzz", "aaa"))
        admitted, refusals = schedule_domain.codispatch_admission(order, {"aaa": ("tests",), "zzz": ("tests",)})
        self.assertEqual(admitted, ("zzz",))
        self.assertIn("subject aaa held behind zzz", refusals[0])

    def test_the_admitted_set_is_pairwise_disjoint(self) -> None:
        """The property the slot actually promises, asserted over a mixed planted set."""
        boundaries = {
            "a": ("tests",),
            "b": ("tests/support.py",),
            "c": ("noodles.py",),
            "d": ("noodles.py", "docs"),
            "e": ("schedule_domain.py",),
        }
        admitted, refusals = schedule_domain.codispatch_admission(sorted(boundaries), boundaries)
        self.assertEqual(admitted, ("a", "c", "e"))
        self.assertEqual(len(refusals), 2)
        for left in admitted:
            for right in admitted:
                if left < right:
                    with self.subTest(pair=(left, right)):
                        self.assertIsNone(issue_contract.boundary_conflict(boundaries[left], boundaries[right]))


class CapacityZeroWriteTests(unittest.TestCase):
    """The controller reads; queue depth is read, never written, and the landing surface is untouched."""

    def test_the_gate_writes_nothing_to_the_filesystem(self) -> None:
        with tempfile.TemporaryDirectory(prefix="noodles-393-zero-write-", ignore_cleanup_errors=True) as name:
            sandbox = Path(name)
            before = sorted(path.relative_to(sandbox) for path in sandbox.rglob("*"))
            cwd = Path.cwd()
            os.chdir(sandbox)
            try:
                for planted in (
                    capacity_reading(),
                    capacity_reading(swap_used_mb=RED_SWAP_USED_MB),
                    capacity_reading(depth=2),
                ):
                    refusal = schedule_domain.capacity_refusal("dispatch-slot", planted, DECLARED_CAPACITY)
                    schedule_domain.refusal_reason_errors(refusal or "")
                schedule_domain.admission_order({"a": (), "b": ("a",)})
            finally:
                os.chdir(cwd)
            self.assertEqual(sorted(path.relative_to(sandbox) for path in sandbox.rglob("*")), before)


if __name__ == "__main__":
    unittest.main()

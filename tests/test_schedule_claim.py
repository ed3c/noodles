from __future__ import annotations

import json
import contextlib
import hashlib
import io
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
        self.temp = tempfile.TemporaryDirectory(prefix="noodles-schedule-claim-")
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
        temp = tempfile.TemporaryDirectory(prefix="noodles-stale-cycle-")
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


if __name__ == "__main__":
    unittest.main()

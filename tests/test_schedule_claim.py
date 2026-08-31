from __future__ import annotations

import json
import contextlib
import io
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

import noodles
import schedule_domain
import skill_contract
from tests.support import CANDIDATE_ROOT, copy_tracked

REPOSITORY = "ed3c/noodles"
HEAD = "a" * 40


def issue_body(number: int, *, state: str = "ready", depends_on: str = "none") -> str:
    subject = f"{REPOSITORY}#{number}"
    return (
        "<!-- noodles-role: repository-mutating-atom -->\n"
        f"<!-- noodles-target: {REPOSITORY} -->\n"
        f"<!-- noodles-subject: {subject} -->\n"
        f"<!-- noodles-state: {state} -->\n"
        f"<!-- noodles-depends-on: {depends_on} -->\n\n"
        "## Goal\n\nSchedule one exact atom.\n\n"
        "## Physical acceptance\n\n- Provider controls pass.\n\n"
        "## Non-claims\n\n- No scheduler is implemented.\n"
    )


def issue(
    number: int,
    *,
    state: str = "ready",
    depends_on: str = "none",
    provider_state: str = "open",
    p0: bool = True,
) -> dict:
    return {
        "number": number,
        "state": provider_state,
        "body": issue_body(number, state=state, depends_on=depends_on),
        "title": f"[PARALLEL-P0] issue {number}" if p0 else f"issue {number}",
        "html_url": f"https://github.test/{REPOSITORY}/issues/{number}",
    }


class FakeProvider:
    def __init__(self, open_issues: list[dict], read_issues: dict[int, dict] | None = None) -> None:
        self.open_issues = open_issues
        self.read_issues = read_issues or {int(item["number"]): item for item in open_issues}
        self.refs: dict[str, str] = {}
        self.posts = 0
        self.issue_pages: list[int] = []
        self.lock = threading.Lock()

    def api(self, endpoint: str, *, method: str = "GET", payload: object | None = None, token: str | None = None) -> object:
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
                    "stages": [{"do": "execute", "model": "gpt-5.6-sol", "prompt": "next"}],
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
                "stages": [{"do": "execute", "model": "gpt-5.6-sol", "prompt": "next"}],
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


if __name__ == "__main__":
    unittest.main()

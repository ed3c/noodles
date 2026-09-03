"""Deterministic executor admission: every exact Issue is classified into one of the admitted executor
lanes from its own declared tokens before any claim, branch, checkout, or worktree exists. Duplicate,
malformed, missing, and unknown declarations each carry their own diagnostic; the durable control
corpus supplies both positive controls and every planted negative named in ed3c/noodles#187.

ed3c/noodles#450 admits the fourth value, `codex-cloud`, and pins the three #187 landed against it:
admitting a lane must move neither the lane nor the checkout any existing declaration routes to, and an
executor value that is still not in the enum must still be refused by name."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import issue_contract
import noodles
import skill_contract
from tests.support import (
    CANDIDATE_ROOT,
    ISSUE_REQUIREMENT_MARKER,
    complete_issue_sections,
    copy_tracked,
    load_ready_backlog_fixtures,
)

REPOSITORY = "ed3c/noodles"
HEAD = "c" * 40
EXECUTE_MODEL = skill_contract.task_profiles(CANDIDATE_ROOT)["execute"]["model"]


def controls() -> dict[str, object]:
    return {fixture.id: fixture for fixture in load_ready_backlog_fixtures(CANDIDATE_ROOT)}


def body(
    number: int,
    *,
    executor: str | None = "gha-runtime",
    runtime: str | None = "bun-ts",
    evidence: str | None = "github-only-v1",
    write_boundary: str = "none",
    extra: str = "",
) -> str:
    subject = f"{REPOSITORY}#{number}"
    markers = "".join(
        f"<!-- noodles-{name}: {value} -->\n"
        for name, value in (("executor", executor), ("runtime", runtime), ("evidence", evidence))
        if value is not None
    )
    return (
        "<!-- noodles-role: repository-mutating-atom -->\n"
        f"<!-- noodles-target: {REPOSITORY} -->\n"
        f"<!-- noodles-subject: {subject} -->\n"
        "<!-- noodles-state: ready -->\n"
        "<!-- noodles-depends-on: none -->\n"
        f"<!-- noodles-write-boundary: {write_boundary} -->\n"
        f"{ISSUE_REQUIREMENT_MARKER}\n"
        f"{markers}{extra}\n"
        + complete_issue_sections(
            "Classify one exact execution lane.",
            "- Admission does not prove implementation correctness.",
        )
    )


class CapabilityTableTests(unittest.TestCase):
    """The table is bounded data, not a policy DSL: two dimensions, each token naming exact lanes."""

    def test_table_is_two_bounded_dimensions_of_lane_tuples(self) -> None:
        self.assertEqual(sorted(issue_contract.CAPABILITY_TABLE), ["evidence", "runtime"])
        for dimension, rows in issue_contract.CAPABILITY_TABLE.items():
            for token, lanes in rows.items():
                with self.subTest(dimension=dimension, token=token):
                    self.assertTrue(lanes)
                    self.assertEqual(set(lanes) - set(issue_contract.EXECUTOR_LANES), set())

    def test_every_token_stays_admissible_on_the_local_lane(self) -> None:
        # constraint: ed3c/noodles#187 - the local lane is the physical superset, so a
        # constraint: hosted refusal can always name an admitted route instead of
        # constraint: leaving the issue with nowhere to run.
        for dimension, rows in issue_contract.CAPABILITY_TABLE.items():
            for token, lanes in rows.items():
                with self.subTest(dimension=dimension, token=token):
                    self.assertIn(issue_contract.LOCAL_LANE, lanes)


class MarkerDiagnosticTests(unittest.TestCase):
    """Duplicate, malformed, missing, and unknown are four distinct deterministic diagnostics."""

    def test_duplicate_marker_fails_closed(self) -> None:
        for marker in issue_contract.CAPABILITY_MARKERS:
            with self.subTest(marker=marker):
                duplicated = body(1, extra=f"<!-- noodles-{marker}: bun-ts -->\n")
                with self.assertRaisesRegex(noodles.GateError, f"expected one noodles-{marker} marker, found 2"):
                    noodles.parse_issue_contract(duplicated, f"{REPOSITORY}#1")

    def test_malformed_value_fails_closed_distinctly(self) -> None:
        cases = {"executor": "gha-runtime, local-noodle", "runtime": "bun ts", "evidence": "github-only-v1, drive-full-v1"}
        for marker, value in cases.items():
            with self.subTest(marker=marker):
                with self.assertRaisesRegex(noodles.GateError, f"malformed noodles-{marker}"):
                    noodles.parse_issue_contract(body(1, **{marker: value}), f"{REPOSITORY}#1")

    def test_unknown_value_fails_closed_naming_admitted_tokens(self) -> None:
        for marker in issue_contract.CAPABILITY_MARKERS:
            with self.subTest(marker=marker):
                with self.assertRaises(noodles.GateError) as raised:
                    noodles.parse_issue_contract(body(1, **{marker: "kitchen-sink"}), f"{REPOSITORY}#1")
                diagnostic = str(raised.exception)
                self.assertIn(f"unknown noodles-{marker} 'kitchen-sink'", diagnostic)
                self.assertIn("admitted tokens:", diagnostic)

    def test_missing_marker_is_undeclared_and_never_a_default_lane(self) -> None:
        for marker in issue_contract.CAPABILITY_MARKERS:
            with self.subTest(marker=marker):
                contract = noodles.parse_issue_contract(body(1, **{marker: None}), f"{REPOSITORY}#1")
                admission = contract["admission"]
                self.assertFalse(admission["admitted"])
                self.assertIsNone(admission["lane"])
                self.assertEqual(admission["status"], "executor_undeclared")
                self.assertIn(f"issue declares no noodles-{marker} marker", admission["reasons"])


class AdmissionControlTests(unittest.TestCase):
    """Both positive controls and every planted negative come from the durable fixture corpus."""

    def admission(self, fixture_id: str) -> dict[str, object]:
        fixture = controls()[fixture_id]
        return noodles.parse_issue_contract(fixture.body, fixture.subject)["admission"]

    def test_positive_control_bun_typescript_repository_admits_gha_runtime(self) -> None:
        fixture = controls()["executor-gha-runtime-bun-ts"]
        for command in ("bun install", "bun run lint", "bun run typecheck", "bun test", "bun run build", "CLI smoke"):
            self.assertIn(command, fixture.body)
        admission = self.admission("executor-gha-runtime-bun-ts")
        self.assertTrue(admission["admitted"])
        self.assertEqual(admission["lane"], "gha-runtime")
        self.assertEqual(admission["checkout"], issue_contract.EPHEMERAL_CHECKOUT)

    def test_positive_control_code_generation_over_same_runtime_admits_gha_agentic(self) -> None:
        admission = self.admission("executor-gha-agentic-bun-ts")
        self.assertTrue(admission["admitted"])
        self.assertEqual(admission["lane"], "gha-agentic")
        self.assertEqual(admission["checkout"], issue_contract.EPHEMERAL_CHECKOUT)

    def test_planted_negatives_refuse_hosted_and_name_local_noodle_as_the_only_route(self) -> None:
        planted = (
            "executor-refused-usb-device",
            "executor-refused-gui-simulator",
            "executor-refused-private-network",
            "executor-refused-persistent-daemon",
            "executor-refused-unsupported-runtime",
        )
        for fixture_id in planted:
            with self.subTest(fixture_id=fixture_id):
                admission = self.admission(fixture_id)
                self.assertFalse(admission["admitted"])
                self.assertEqual(admission["status"], "executor_refused")
                self.assertIsNone(admission["lane"])
                self.assertEqual(admission["admitted_lanes"], (issue_contract.LOCAL_LANE,))
                self.assertIn(f"admitted route: {issue_contract.LOCAL_LANE}", admission["reasons"])

    def test_host_only_evidence_policy_refuses_the_hosted_lane(self) -> None:
        refused = noodles.parse_issue_contract(body(1, evidence="drive-full-v1"), f"{REPOSITORY}#1")["admission"]
        self.assertEqual(refused["status"], "executor_refused")
        self.assertEqual(refused["admitted_lanes"], (issue_contract.LOCAL_LANE,))
        admission = self.admission("executor-local-drive-evidence")
        self.assertTrue(admission["admitted"])
        self.assertEqual(admission["lane"], issue_contract.LOCAL_LANE)
        self.assertEqual(admission["checkout"], issue_contract.MANAGED_WORKTREE)

    def test_contradictory_runtime_lane_without_a_runtime_is_refused(self) -> None:
        # constraint: ed3c/noodles#450 - this assertion used to pin the `none` row's admitted tuple
        # constraint: as a literal, which is the ed3c/noodles#285 shape: `pull_request_target` runs
        # constraint: the DEFAULT BRANCH's copy of this module against the candidate, so any
        # constraint: candidate that legitimately moved the row was compared against a tuple only
        # constraint: main held and no rerun or rebase could turn it green. Widened here to derive
        # constraint: the expectation from CAPABILITY_TABLE, the row's own owner, so the atom that
        # constraint: flips the row lands under this same acceptance. What is asserted stays the
        # constraint: property, not the membership: gha-runtime - the lane that exists to execute a
        # constraint: deterministic runtime - is the excluded one, and the local superset remains.
        admission = noodles.parse_issue_contract(body(1, runtime="none"), f"{REPOSITORY}#1")["admission"]
        self.assertEqual(admission["status"], "executor_refused")
        self.assertEqual(
            set(admission["admitted_lanes"]),
            set(issue_contract.CAPABILITY_TABLE["runtime"]["none"]),
        )
        self.assertNotIn("gha-runtime", admission["admitted_lanes"])
        self.assertIn(issue_contract.LOCAL_LANE, admission["admitted_lanes"])


class CodexCloudAdmissionTests(unittest.TestCase):
    """ed3c/noodles#450 - the fourth lane, and the three it must not disturb.

    The enum is the admission layer's vocabulary: a lane it cannot name is a lane the machine cannot
    route, gate, or measure. `codex-cloud` runs inference in the operator's subscription cloud and
    writes through the Codex App identity, so it supplies exactly what a sandboxed lane supplies -
    portable runtimes and github-only evidence - and none of the local-only capabilities."""

    def admission(self, **overrides: object) -> dict[str, object]:
        return noodles.parse_issue_contract(body(1, **overrides), f"{REPOSITORY}#1")["admission"]

    def test_regression_pin_the_three_landed_executor_values_route_unchanged(self) -> None:
        # constraint: ed3c/noodles#450 - lane and checkout ARE the routing answer, so admitting a
        # constraint: fourth value is proven inert by pinning both for one declaration each of the
        # constraint: three lanes ed3c/noodles#187 landed, including the checkout rule this atom
        # constraint: re-keyed from a hosted allowlist onto the local lane's absent worktree.
        for executor, runtime, checkout in (
            ("gha-agentic", "none", issue_contract.EPHEMERAL_CHECKOUT),
            ("gha-runtime", "bun-ts", issue_contract.EPHEMERAL_CHECKOUT),
            (issue_contract.LOCAL_LANE, "usb-device", issue_contract.MANAGED_WORKTREE),
        ):
            with self.subTest(executor=executor):
                admission = self.admission(executor=executor, runtime=runtime)
                self.assertTrue(admission["admitted"], admission)
                self.assertEqual(admission["lane"], executor)
                self.assertEqual(admission["checkout"], checkout)

    def test_positive_control_codex_cloud_routes_to_its_own_lane_on_an_ephemeral_checkout(self) -> None:
        # constraint: ed3c/noodles#450 - the portable runtime rows, which codex-cloud inherits by
        # constraint: construction. `none` is absent on purpose: that row's flip is the follow-up
        # constraint: half of the staged transition this atom widens acceptance for.
        for runtime in ("python", "bun-ts", "shell"):
            with self.subTest(runtime=runtime):
                admission = self.admission(executor=issue_contract.CODEX_CLOUD_LANE, runtime=runtime)
                self.assertTrue(admission["admitted"], admission)
                self.assertEqual(admission["lane"], issue_contract.CODEX_CLOUD_LANE)
                self.assertEqual(admission["status"], "admitted")
                # constraint: ed3c/noodles#450 - a managed worktree is a thing only the operator's
                # constraint: machine has; the cloud sandbox never gets one.
                self.assertEqual(admission["checkout"], issue_contract.EPHEMERAL_CHECKOUT)

    def test_planted_negative_codex_cloud_is_refused_every_host_only_capability(self) -> None:
        local_only = tuple(
            token
            for token, lanes in issue_contract.CAPABILITY_TABLE["runtime"].items()
            if lanes == (issue_contract.LOCAL_LANE,)
        )
        self.assertTrue(local_only)
        for runtime in local_only:
            with self.subTest(runtime=runtime):
                admission = self.admission(executor=issue_contract.CODEX_CLOUD_LANE, runtime=runtime)
                self.assertEqual(admission["status"], "executor_refused")
                self.assertIsNone(admission["lane"])
                self.assertEqual(admission["admitted_lanes"], (issue_contract.LOCAL_LANE,))
        refused = self.admission(executor=issue_contract.CODEX_CLOUD_LANE, evidence="drive-full-v1")
        self.assertEqual(refused["status"], "executor_refused")
        self.assertEqual(refused["admitted_lanes"], (issue_contract.LOCAL_LANE,))

    def test_planted_negative_an_unadmitted_executor_value_is_still_refused_by_name(self) -> None:
        # constraint: ed3c/noodles#450 - admitting one value must not soften the enum into a family:
        # constraint: a near miss on the new token is refused exactly as `kitchen-sink` is, and the
        # constraint: diagnostic names the whole admitted set so the author is never left guessing.
        for unadmitted in ("codex", "codex-cloud-preview", "chatgpt", "CODEX-CLOUD", "codex_cloud"):
            with self.subTest(value=unadmitted):
                with self.assertRaises(noodles.GateError) as raised:
                    noodles.parse_issue_contract(body(1, executor=unadmitted), f"{REPOSITORY}#1")
                diagnostic = str(raised.exception)
                self.assertIn(f"unknown noodles-executor {unadmitted!r}", diagnostic)
                self.assertIn(", ".join(issue_contract.EXECUTOR_LANES), diagnostic)


class FakeProvider:
    """Provider double for the claim path, including the local lane's handoff comment surface."""

    def __init__(self, issues: list[dict], pulls: list[dict] | None = None) -> None:
        self.issues = issues
        self.pulls = list(pulls or [])
        self.refs: dict[str, str] = {}
        self.comments: dict[int, list[dict]] = {}
        self.posts = 0
        self.comment_posts = 0

    def api(self, endpoint: str, *, method: str = "GET", payload: object | None = None, token: str | None = None) -> object:
        # constraint: ed3c/noodles#99 - admission reads the open pull request list for every candidate;
        # constraint: an empty list is the no-open-PR world these lane-routing controls are about.
        pull_prefix = f"repos/{REPOSITORY}/pulls?state=open&per_page=100&page="
        if endpoint.startswith(pull_prefix):
            page = int(endpoint.removeprefix(pull_prefix))
            return self.pulls[(page - 1) * 100:page * 100]
        issue_prefix = f"repos/{REPOSITORY}/issues?state=open&sort=created&direction=asc&per_page=100&page="
        if endpoint.startswith(issue_prefix):
            page = int(endpoint.removeprefix(issue_prefix))
            return self.issues[(page - 1) * 100:page * 100]
        comments_route = endpoint.split("?", 1)[0]
        if comments_route.endswith("/comments"):
            number = int(comments_route.rsplit("/", 2)[1])
            if method == "POST":
                assert isinstance(payload, dict)
                self.comment_posts += 1
                created = {"id": 5000 + self.comment_posts, "body": payload["body"]}
                self.comments.setdefault(number, []).append(created)
                return created
            return self.comments.get(number, [])
        if endpoint.startswith(f"repos/{REPOSITORY}/issues/"):
            number = int(endpoint.rsplit("/", 1)[1])
            return next(item for item in self.issues if item["number"] == number)
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
            self.posts += 1
            self.refs[str(payload["ref"])] = str(payload["sha"])
            return {"ref": payload["ref"], "object": {"sha": payload["sha"]}}
        raise AssertionError(f"unexpected provider call: {method} {endpoint}")


def provider_issue(number: int, **overrides: object) -> dict:
    return {
        "number": number,
        "state": "open",
        "body": body(number, **overrides),
        "title": f"[ROUTING-P0] issue {number}",
        "html_url": f"https://github.test/{REPOSITORY}/issues/{number}",
    }


class SchedulePublishAdmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory(prefix="noodles-executor-admission-", ignore_cleanup_errors=True)
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "repo"
        copy_tracked(CANDIDATE_ROOT, self.root)

    def publish(self, provider: FakeProvider, subjects: list[str]) -> dict:
        candidate = self.root / ".noodle/orders-next.candidate.json"
        candidate.parent.mkdir(exist_ok=True)
        candidate.write_text(json.dumps({
            "orders": [
                {"id": subject, "stages": [{"do": "execute", "model": EXECUTE_MODEL, "prompt": "next"}]}
                for subject in subjects
            ]
        }))
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            return noodles.schedule_publish(self.root, candidate)

    def claim(self, brief: dict, number: int) -> dict:
        return {item["subject"]: item for item in brief["claims"]}[f"{REPOSITORY}#{number}"]

    def test_hosted_lane_binds_the_run_to_one_ephemeral_branch_and_no_handoff(self) -> None:
        provider = FakeProvider([provider_issue(82)])
        brief = self.publish(provider, [f"{REPOSITORY}#82"])
        claim = self.claim(brief, 82)
        self.assertEqual(claim["status"], "claimed")
        self.assertEqual(claim["lane"], "gha-runtime")
        self.assertEqual(claim["checkout"], issue_contract.EPHEMERAL_CHECKOUT)
        self.assertEqual(claim["target"], REPOSITORY)
        self.assertEqual(claim["base_sha"], HEAD)
        self.assertEqual(claim["runtime"], "bun-ts")
        self.assertEqual(claim["evidence"], "github-only-v1")
        self.assertNotIn("handoff", claim)
        self.assertEqual(provider.comment_posts, 0)
        self.assertEqual(provider.refs, {f"refs/heads/{noodles.execute_branch(f'{REPOSITORY}#82')}": HEAD})

    def test_local_lane_emits_one_idempotent_provider_backed_handoff_task(self) -> None:
        provider = FakeProvider([provider_issue(82, executor="local-noodle", runtime="usb-device", write_boundary="docs")])
        brief = self.publish(provider, [f"{REPOSITORY}#82"])
        claim = self.claim(brief, 82)
        self.assertEqual(claim["checkout"], issue_contract.MANAGED_WORKTREE)
        handoff = claim["handoff"]
        self.assertEqual(handoff["status"], "emitted")
        self.assertEqual(handoff["capability"], "usb-device")
        self.assertEqual(handoff["target"], REPOSITORY)
        self.assertEqual(handoff["write_boundary"], ["docs"])
        self.assertEqual(provider.comment_posts, 1)
        emitted = provider.comments[82][0]["body"]
        self.assertIn(f"<!-- noodles-local-handoff: {handoff['issue_digest']} -->", emitted)
        self.assertIn("Noodle remains the sole owner of the persistent worktree lifecycle", emitted)

        # constraint: ed3c/noodles#187 - a second cycle over the same Issue digest reuses
        # constraint: the exact existing task instead of emitting a duplicate local claim.
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            reused = noodles.emit_local_handoff(
                f"{REPOSITORY}#82",
                noodles.issue_contract_payload(provider.issues[0], f"{REPOSITORY}#82"),
                ("docs",),
            )
        self.assertEqual(reused["status"], "reused")
        self.assertEqual(reused["id"], handoff["id"])
        self.assertEqual(provider.comment_posts, 1)

    def test_duplicate_provider_handoff_tasks_fail_closed(self) -> None:
        provider = FakeProvider([provider_issue(82, executor="local-noodle", runtime="usb-device")])
        contract = noodles.issue_contract_payload(provider.issues[0], f"{REPOSITORY}#82")
        marker = f"<!-- noodles-local-handoff: {contract['body_sha256']} -->"
        provider.comments[82] = [{"id": 1, "body": marker}, {"id": 2, "body": marker}]
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            with self.assertRaisesRegex(noodles.GateError, "duplicate local handoff tasks"):
                noodles.emit_local_handoff(f"{REPOSITORY}#82", contract, ())

    def test_refused_lane_leaves_no_provider_residue_and_publishes_its_reasons(self) -> None:
        provider = FakeProvider([provider_issue(82, runtime="gui-simulator")])
        brief = self.publish(provider, [f"{REPOSITORY}#82"])
        claim = self.claim(brief, 82)
        self.assertEqual(claim["status"], "executor_refused")
        self.assertEqual(claim["meaning"], skill_contract.SCHEDULE_CLAIM_STATUS_MEANINGS["executor_refused"])
        self.assertEqual(claim["admitted_lanes"], [issue_contract.LOCAL_LANE])
        self.assertIn(f"admitted route: {issue_contract.LOCAL_LANE}", claim["reasons"])
        self.assertEqual(provider.posts, 0)
        self.assertEqual(provider.refs, {})
        self.assertEqual(json.loads((self.root / ".noodle/orders-next.json").read_text())["orders"], [])

    def test_undeclared_executor_fails_closed_before_any_branch(self) -> None:
        provider = FakeProvider([provider_issue(82, executor=None)])
        brief = self.publish(provider, [f"{REPOSITORY}#82"])
        claim = self.claim(brief, 82)
        self.assertEqual(claim["status"], "executor_undeclared")
        self.assertEqual(claim["meaning"], skill_contract.SCHEDULE_CLAIM_STATUS_MEANINGS["executor_undeclared"])
        self.assertEqual(provider.posts, 0)

    def test_overlapping_write_boundaries_still_reject_the_second_admitted_lane(self) -> None:
        # constraint: ed3c/noodles#187 - executor admission runs before, and does not
        # constraint: replace, the landed ed3c/noodles#98 disjointness machinery.
        provider = FakeProvider([
            provider_issue(82, write_boundary="schedule_domain.py"),
            provider_issue(90, write_boundary="schedule_domain.py"),
        ])
        brief = self.publish(provider, [f"{REPOSITORY}#82", f"{REPOSITORY}#90"])
        self.assertEqual(self.claim(brief, 82)["status"], "claimed")
        rejected = self.claim(brief, 90)
        self.assertEqual(rejected["status"], "boundary_conflict")
        self.assertEqual(rejected["conflict_with"], f"{REPOSITORY}#82")
        self.assertEqual(provider.posts, 1)

    def test_direct_readback_publishes_the_chosen_executor_and_its_reasons(self) -> None:
        payload = noodles.issue_contract_payload(provider_issue(82, runtime="private-network"), f"{REPOSITORY}#82")
        self.assertEqual(payload["executor"], "gha-runtime")
        self.assertEqual(payload["runtime"], "private-network")
        self.assertEqual(payload["evidence"], "github-only-v1")
        self.assertEqual(payload["admission"]["admitted_lanes"], (issue_contract.LOCAL_LANE,))


if __name__ == "__main__":
    unittest.main()

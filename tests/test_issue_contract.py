from __future__ import annotations

import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import issue_contract
import noodles
from tests.support import (
    CANDIDATE_ROOT,
    ENGINE_ROOT,
    ISSUE_FEATURE_MARKER,
    READY_BACKLOG_FIXTURE,
    assert_candidate_preserves_or_migrates_ready_backlog,
    copy_tracked,
    load_ready_backlog_fixtures,
)

SUBJECT = "ed3c/noodles#82"
PREDECESSOR = "ed3c/noodles#81"


# constraint: ed3c/noodles#120 - one stable requirement heading that really exists in
# constraint: contracts/system-v1.md, so the fixture resolves through the same read path production
# constraint: uses rather than through a test-only registry.
REQUIREMENT = "REQUIREMENT.EVOLUTION.001"
COMPLETE_ACCEPTANCE = (
    "- Positive control: the exact contract admits this body.\n"
    "- Planted-negative control: each dropped obligation fails closed.\n"
    "- Direct source readback proves it.\n"
    "- Zero residue after the run.\n"
)


def issue_body(
    *,
    subject: str = SUBJECT,
    state: str = "ready",
    depends_on: str = "none",
    blocker: str | None = None,
    requirements: tuple[str, ...] = (REQUIREMENT,),
    trigger: str = "A syntactically valid ready subject can still be too incomplete to implement.",
    goal: str = "Derive schedulability from typed provider dependencies.",
    claim: str = "Ready becomes necessary but not sufficient for schedulability.",
    acceptance: str = COMPLETE_ACCEPTANCE,
    non_case: str = "none",
    non_claims: str = "- No scheduler is implemented here.",
) -> str:
    blocker_marker = f"<!-- noodles-blocker: {blocker} -->\n" if blocker is not None else ""
    requirement_markers = "".join(f"<!-- noodles-requirement: {item} -->\n" for item in requirements)
    sections = ""
    for heading, content in (
        ("Physical trigger", trigger),
        ("Goal", goal),
        ("Claim", claim),
        ("Physical acceptance", acceptance),
        ("Non-case", non_case),
        ("Non-claims", non_claims),
    ):
        if content:
            sections += f"\n## {heading}\n\n{content}\n"
    return (
        "<!-- noodles-role: repository-mutating-atom -->\n"
        "<!-- noodles-target: ed3c/noodles -->\n"
        f"<!-- noodles-subject: {subject} -->\n"
        f"<!-- noodles-state: {state} -->\n"
        f"{ISSUE_FEATURE_MARKER}\n"
        f"<!-- noodles-depends-on: {depends_on} -->\n"
        f"{requirement_markers}{blocker_marker}{sections}"
    )


def predecessor_body(state: str = "landed") -> str:
    return issue_body(subject=PREDECESSOR, state=state)


class ReadyBacklogFixtureGateTests(unittest.TestCase):
    def tightened_candidate(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temp = tempfile.TemporaryDirectory(prefix="noodles-tightening-")
        root = Path(temp.name) / "candidate"
        copy_tracked(CANDIDATE_ROOT, root)
        parser_path = root / "noodles.py"
        parser = parser_path.read_text(encoding="utf-8")
        seam = '    feature_value = one_marker(body, "feature", required=False)\n'
        tightening = (
            seam
            + '    if "<!-- noodles-priority: p0 -->" not in body:\n'
            + '        raise GateError("missing noodles-priority marker")\n'
        )
        self.assertEqual(parser.count(seam), 1)
        parser_path.write_text(parser.replace(seam, tightening), encoding="utf-8")
        helper_path = root / "tests/test_issue_contract.py"
        helper = helper_path.read_text(encoding="utf-8")
        helper_seam = '        f"{ISSUE_FEATURE_MARKER}\\n"\n'
        self.assertEqual(helper.count(helper_seam), 1)
        helper_path.write_text(
            helper.replace(helper_seam, helper_seam + '        "<!-- noodles-priority: p0 -->\\n"\n'),
            encoding="utf-8",
        )
        return temp, root

    def test_candidate_preserves_or_migrates_durable_ready_backlog_shapes(self) -> None:
        assert_candidate_preserves_or_migrates_ready_backlog(ENGINE_ROOT, CANDIDATE_ROOT)

    def test_durable_corpus_covers_observed_feature_dependency_cardinalities(self) -> None:
        fixtures = {fixture.id: fixture for fixture in load_ready_backlog_fixtures(CANDIDATE_ROOT)}
        expected = {
            "ready-feature-one-dependency": ("verification-skill-oracle", 1),
            "ready-feature-two-dependencies": ("verification-skill-oracle", 2),
            "ready-no-feature-three-dependencies": ("", 3),
        }
        for fixture_id, (feature, dependency_count) in expected.items():
            with self.subTest(fixture_id=fixture_id):
                fixture = fixtures[fixture_id]
                contract = noodles.parse_issue_contract(fixture.body, fixture.subject)
                self.assertEqual(contract["feature"], feature)
                self.assertEqual(len(contract["dependencies"]), dependency_count)

    def test_planted_tightening_fails_even_when_generated_helper_changes(self) -> None:
        temp, root = self.tightened_candidate()
        self.addCleanup(temp.cleanup)
        self.assertIn("noodles-priority: p0", (root / "tests/test_issue_contract.py").read_text(encoding="utf-8"))
        with self.assertRaises(AssertionError) as raised:
            assert_candidate_preserves_or_migrates_ready_backlog(ENGINE_ROOT, root)
        diagnostic = str(raised.exception)
        self.assertIn("migration obligation", diagnostic)
        self.assertIn("intake-normalizer seam ed3c/noodles#157", diagnostic)
        self.assertIn("ready-optional-feature-absent", diagnostic)
        self.assertIn("missing noodles-priority marker", diagnostic)

    def test_same_id_accepted_fixture_migration_recovers_planted_tightening(self) -> None:
        temp, root = self.tightened_candidate()
        self.addCleanup(temp.cleanup)
        fixture_path = root / READY_BACKLOG_FIXTURE
        corpus = json.loads(fixture_path.read_text(encoding="utf-8"))
        for fixture in corpus["fixtures"]:
            fixture["body"] = fixture["body"].replace(
                "<!-- noodles-state: ready -->\n",
                "<!-- noodles-state: ready -->\n<!-- noodles-priority: p0 -->\n",
                1,
            )
        fixture_path.write_text(json.dumps(corpus, indent=2) + "\n", encoding="utf-8")
        assert_candidate_preserves_or_migrates_ready_backlog(ENGINE_ROOT, root)


class DependencyMarkerTests(unittest.TestCase):
    """The marker is parsed exactly; every ambiguous form fails closed with a diagnostic."""

    def test_explicit_none_and_exact_subjects_parse(self) -> None:
        self.assertEqual(noodles.parse_issue_contract(issue_body(), SUBJECT)["dependencies"], [])
        self.assertEqual(
            noodles.parse_issue_contract(issue_body(depends_on=PREDECESSOR), SUBJECT)["dependencies"],
            [PREDECESSOR],
        )
        self.assertEqual(
            noodles.parse_issue_contract(issue_body(depends_on=f"{PREDECESSOR}, ed3c/noodles#61"), SUBJECT)["dependencies"],
            [PREDECESSOR, "ed3c/noodles#61"],
        )

    def test_missing_marker_is_undeclared_and_never_read_as_no_dependencies(self) -> None:
        body = issue_body().replace("<!-- noodles-depends-on: none -->\n", "")
        contract = noodles.parse_issue_contract(body, SUBJECT)
        self.assertIsNone(contract["dependencies"])
        derived = issue_contract.derive_schedulability(
            contract, "open", {}, issue_contract.sections(body), noodles.system_requirement_ids(CANDIDATE_ROOT)
        )
        self.assertFalse(derived["schedulable"])
        self.assertIn("noodles-depends-on", " ".join(derived["reasons"]))

    def test_landed_issue_without_the_marker_still_parses_for_landing_and_reconcile(self) -> None:
        body = issue_body(state="landed").replace("<!-- noodles-depends-on: none -->\n", "")
        self.assertEqual(noodles.parse_issue_contract(body, SUBJECT)["state"], "landed")

    def test_duplicate_marker_fails_closed(self) -> None:
        body = issue_body() + "<!-- noodles-depends-on: none -->\n"
        with self.assertRaisesRegex(noodles.GateError, "noodles-depends-on"):
            noodles.parse_issue_contract(body, SUBJECT)

    def test_duplicate_entry_fails_closed(self) -> None:
        with self.assertRaisesRegex(noodles.GateError, "duplicate"):
            noodles.parse_issue_contract(issue_body(depends_on=f"{PREDECESSOR}, {PREDECESSOR}"), SUBJECT)

    def test_self_dependency_fails_closed(self) -> None:
        with self.assertRaisesRegex(noodles.GateError, "own subject"):
            noodles.parse_issue_contract(issue_body(depends_on=SUBJECT), SUBJECT)

    def test_wrong_repository_dependency_fails_closed(self) -> None:
        with self.assertRaisesRegex(noodles.GateError, "outside the issue repository"):
            noodles.parse_issue_contract(issue_body(depends_on="ed3c/other#81"), SUBJECT)

    def test_ambiguous_dependency_prose_fails_closed(self) -> None:
        for raw in ("after ed3c/noodles#81 lands", "#81", "", "none, ed3c/noodles#81", "None", "ed3c/noodles#81 and #61"):
            with self.assertRaises(noodles.GateError):
                noodles.parse_issue_contract(issue_body(depends_on=raw), SUBJECT)


class WriteBoundaryMarkerTests(unittest.TestCase):
    """One typed write-boundary of exact path prefixes; prose and absolutes fail closed to None."""

    def test_explicit_none_reserves_nothing(self) -> None:
        self.assertEqual(issue_contract.parse_write_boundary("none"), ())
        self.assertEqual(issue_contract.parse_write_boundary("None"), ())

    def test_missing_marker_is_none(self) -> None:
        self.assertIsNone(issue_contract.parse_write_boundary(None))
        self.assertIsNone(issue_contract.parse_write_boundary("   "))

    def test_exact_prefixes_parse_and_deduplicate(self) -> None:
        self.assertEqual(issue_contract.parse_write_boundary("schedule_domain.py"), ("schedule_domain.py",))
        self.assertEqual(
            issue_contract.parse_write_boundary("noodles.py, tests/, tests"),
            ("noodles.py", "tests"),
        )

    def test_prose_and_absolute_and_escape_fail_closed_to_none(self) -> None:
        for raw in ("see the goal section", "/etc/passwd", "../outside", "docs/../secret", "a b/c"):
            with self.subTest(raw=raw):
                self.assertIsNone(issue_contract.parse_write_boundary(raw))

    def test_conflict_is_segment_wise_not_string_prefix(self) -> None:
        # constraint: ed3c/noodles#98 - tests and tests2 share a string prefix but
        # constraint: are disjoint path surfaces, so they must never intersect.
        self.assertIsNone(issue_contract.boundary_conflict(("tests",), ("tests2",)))
        self.assertEqual(issue_contract.boundary_conflict(("tests",), ("tests",)), "tests")
        self.assertEqual(issue_contract.boundary_conflict(("docs",), ("docs/design/x.md",)), "docs/design/x.md")
        self.assertIsNone(issue_contract.boundary_conflict(("docs",), ("policy",)))
        self.assertIsNone(issue_contract.boundary_conflict((), ("docs",)))

    def test_contract_carries_the_parsed_boundary(self) -> None:
        body = issue_body().replace(
            "<!-- noodles-depends-on: none -->\n",
            "<!-- noodles-depends-on: none -->\n<!-- noodles-write-boundary: schedule_domain.py -->\n",
        )
        self.assertEqual(noodles.parse_issue_contract(body, SUBJECT)["write_boundary"], ("schedule_domain.py",))
        self.assertIsNone(noodles.parse_issue_contract(issue_body(), SUBJECT)["write_boundary"])


class BlockerMarkerTests(unittest.TestCase):
    """`blocked` carries a real blocker owner/reason; dependency waiting is never stored as state."""

    def test_blocked_without_blocker_owner_fails_closed(self) -> None:
        with self.assertRaisesRegex(noodles.GateError, "noodles-blocker"):
            noodles.parse_issue_contract(issue_body(state="blocked"), SUBJECT)

    def test_blocked_with_explicit_owner_and_reason_parses(self) -> None:
        contract = noodles.parse_issue_contract(
            issue_body(state="blocked", blocker="ed3c: provider protection token is revoked"), SUBJECT
        )
        self.assertEqual(contract["blocker"], {"owner": "ed3c", "reason": "provider protection token is revoked"})

    def test_blocker_restating_dependency_waiting_fails_closed(self) -> None:
        for raw in ("ed3c: waiting on ed3c/noodles#81", "ed3c: depends on the predecessor", "ed3c: blocked by #81"):
            with self.assertRaisesRegex(noodles.GateError, "dependency"):
                noodles.parse_issue_contract(issue_body(state="blocked", blocker=raw), SUBJECT)

    def test_blocker_without_blocked_state_fails_closed(self) -> None:
        with self.assertRaisesRegex(noodles.GateError, "blocked"):
            noodles.parse_issue_contract(issue_body(blocker="ed3c: token revoked"), SUBJECT)

    def test_issue_set_state_refuses_blocked_without_blocker_before_mutation(self) -> None:
        with mock.patch.object(noodles, "issue_read", return_value={"state": "open", "body": issue_body()}), \
             mock.patch.object(noodles, "gh_api") as api:
            with self.assertRaisesRegex(noodles.GateError, "noodles-blocker"):
                noodles.issue_set_state(SUBJECT, "blocked")
        api.assert_not_called()


class SchedulabilityTests(unittest.TestCase):
    """Eligibility is derived from each predecessor's own provider readback, never from a mirrored marker."""

    def contract(self, **kwargs: str) -> dict:
        return noodles.parse_issue_contract(issue_body(**kwargs), SUBJECT)

    def derive(self, contract: dict, dependency_states: dict, provider_state: str = "open") -> dict:
        return issue_contract.derive_schedulability(
            contract,
            provider_state,
            dependency_states,
            issue_contract.sections(issue_body()),
            noodles.system_requirement_ids(CANDIDATE_ROOT),
        )

    def landed(self) -> dict:
        return {PREDECESSOR: {"subject": PREDECESSOR, "provider_state": "closed", "state": "landed", "error": None}}

    def test_landed_predecessor_makes_dependent_schedulable_without_a_manual_marker(self) -> None:
        derived = self.derive(self.contract(depends_on=PREDECESSOR), self.landed())
        self.assertEqual(derived, {"schedulable": True, "reasons": []})

    def test_open_predecessor_is_not_schedulable(self) -> None:
        states = {PREDECESSOR: {"subject": PREDECESSOR, "provider_state": "open", "state": "ready", "error": None}}
        derived = self.derive(self.contract(depends_on=PREDECESSOR), states)
        self.assertFalse(derived["schedulable"])
        self.assertIn(PREDECESSOR, derived["reasons"][0])

    def test_closed_but_not_landed_predecessor_is_not_schedulable(self) -> None:
        states = {PREDECESSOR: {"subject": PREDECESSOR, "provider_state": "closed", "state": "ready", "error": None}}
        self.assertFalse(self.derive(self.contract(depends_on=PREDECESSOR), states)["schedulable"])

    def test_provider_read_failure_never_reads_as_satisfied(self) -> None:
        states = {PREDECESSOR: {"subject": PREDECESSOR, "provider_state": None, "state": None, "error": "gh api 502"}}
        derived = self.derive(self.contract(depends_on=PREDECESSOR), states)
        self.assertFalse(derived["schedulable"])
        self.assertIn("gh api 502", derived["reasons"][0])

    def test_unread_dependency_never_reads_as_satisfied(self) -> None:
        derived = self.derive(self.contract(depends_on=PREDECESSOR), {})
        self.assertFalse(derived["schedulable"])
        self.assertIn("never read back", derived["reasons"][0])

    def test_closed_or_non_ready_issue_is_not_schedulable(self) -> None:
        self.assertFalse(self.derive(self.contract(), {}, provider_state="closed")["schedulable"])
        self.assertFalse(self.derive(self.contract(state="in_progress"), {})["schedulable"])

    def test_explicit_blocker_is_reported_as_its_own_reason(self) -> None:
        contract = self.contract(state="blocked", blocker="ed3c: provider protection token is revoked")
        derived = self.derive(contract, {})
        self.assertFalse(derived["schedulable"])
        self.assertIn("ed3c", " ".join(derived["reasons"]))

    def test_missing_typed_sections_are_not_schedulable(self) -> None:
        derived = issue_contract.derive_schedulability(
            self.contract(),
            "open",
            {},
            issue_contract.sections(issue_body(non_claims="")),
            noodles.system_requirement_ids(CANDIDATE_ROOT),
        )
        self.assertFalse(derived["schedulable"])
        self.assertIn("non claims", " ".join(derived["reasons"]))


# constraint: ed3c/noodles#69 is CLOSED and its body is immutable historical evidence; this is the
# constraint: exact fixture derived from it, kept byte-faithful so the control keeps measuring the
# constraint: real shape ed3c/noodles#120 was filed against rather than a convenient paraphrase.
ISSUE_69_BODY = (
    "<!-- noodles-role: repository-mutating-atom -->\n"
    "<!-- noodles-target: ed3c/noodles -->\n"
    "<!-- noodles-subject: ed3c/noodles#69 -->\n"
    "<!-- noodles-state: ready -->\n"
    "<!-- noodles-depends-on: none -->\n"
    "\n## Goal\n\n--help\n"
    "\n## Physical acceptance\n\n"
    "- Exact-subject positive and planted-negative controls pass.\n"
    "- Direct source/provider readback proves only the stated claim.\n"
    "- `./noodles verify` passes with zero tracked residue.\n"
    "\n## Non-claims\n\n- No adjacent capability is admitted by prose or inference.\n"
)


class RequirementBindingTests(unittest.TestCase):
    """ed3c/noodles#120 - the typed requirement marker: syntax, multiplicity, duplicates, ordering,
    and resolution against the specification's own `### ID` headings."""

    def known(self) -> frozenset[str]:
        return noodles.system_requirement_ids(CANDIDATE_ROOT)

    def derive(self, body: str, subject: str = SUBJECT) -> dict:
        return issue_contract.derive_schedulability(
            noodles.parse_issue_contract(body, subject), "open", {}, issue_contract.sections(body), self.known()
        )

    def test_identities_come_from_the_specification_headings_through_the_declared_route(self) -> None:
        route = noodles.load_json(CANDIDATE_ROOT / "policy/fitness.json")["agent_document_route"]
        source = noodles.requirement_definition_source(CANDIDATE_ROOT)
        self.assertEqual(source, CANDIDATE_ROOT / route[1])
        self.assertEqual(len(route), 3, "requirement resolution must not add a fourth document hop")
        known = self.known()
        self.assertIn(REQUIREMENT, known)
        self.assertEqual(
            known,
            frozenset(re.findall(r"(?m)^### ([A-Z][A-Z0-9_.-]+)$", source.read_text())),
        )

    def test_multiple_markers_keep_authored_order_and_are_bounded(self) -> None:
        extra = "COMPLEXITY.SUBTRACT.001"
        contract = noodles.parse_issue_contract(issue_body(requirements=(extra, REQUIREMENT)), SUBJECT)
        self.assertEqual(contract["requirements"], [extra, REQUIREMENT])
        self.assertEqual(contract["requirement_errors"], [])
        over = tuple(sorted(self.known())[: issue_contract.MAX_REQUIREMENTS + 1])
        contract = noodles.parse_issue_contract(issue_body(requirements=over), SUBJECT)
        self.assertTrue(any("at most" in reason for reason in contract["requirement_errors"]))

    def test_a_marker_printed_inside_a_section_is_documentation_not_a_declaration(self) -> None:
        body = issue_body() + "\n## Required typed surface\n\n<!-- noodles-requirement: REQUIREMENT.ID -->\n"
        contract = noodles.parse_issue_contract(body, SUBJECT)
        self.assertEqual(contract["requirements"], [REQUIREMENT])
        self.assertEqual(self.derive(body)["reasons"], [])

    def test_each_planted_requirement_defect_fails_with_its_own_reason(self) -> None:
        cases = (
            ("missing", issue_body(requirements=()), "declares no noodles-requirement marker"),
            ("unknown id", issue_body(requirements=("REQUIREMENT.NOT_A_HEADING.001",)), "resolves to no stable requirement heading"),
            ("duplicate", issue_body(requirements=(REQUIREMENT, REQUIREMENT)), "duplicate noodles-requirement entry"),
            ("malformed", issue_body(requirements=("requirement evolution 001",)), "malformed noodles-requirement"),
        )
        seen: list[str] = []
        for label, body, expected in cases:
            with self.subTest(plant=label):
                derived = self.derive(body)
                self.assertFalse(derived["schedulable"])
                matched = [reason for reason in derived["reasons"] if expected in reason]
                self.assertEqual(len(matched), 1, derived["reasons"])
                seen.append(matched[0])
        self.assertEqual(len(set(seen)), len(seen), "each plant must produce its own distinct reason")


class DeterministicCompletenessTests(unittest.TestCase):
    """ed3c/noodles#120 - `ready` is necessary but not sufficient; the gate reports only structure."""

    def known(self) -> frozenset[str]:
        return noodles.system_requirement_ids(CANDIDATE_ROOT)

    def derive(self, body: str, subject: str = SUBJECT) -> dict:
        return issue_contract.derive_schedulability(
            noodles.parse_issue_contract(body, subject), "open", {}, issue_contract.sections(body), self.known()
        )

    def test_a_structurally_complete_ready_issue_is_admitted(self) -> None:
        self.assertEqual(self.derive(issue_body()), {"schedulable": True, "reasons": []})

    def test_the_immutable_issue_69_body_is_ready_yet_not_schedulable(self) -> None:
        contract = noodles.parse_issue_contract(ISSUE_69_BODY, "ed3c/noodles#69")
        self.assertEqual(contract["state"], "ready")
        derived = self.derive(ISSUE_69_BODY, "ed3c/noodles#69")
        self.assertFalse(derived["schedulable"], "noodles-state: ready alone must not admit it")
        for expected in (
            "declares no noodles-requirement marker",
            "no '## claim' section",
            "no '## Physical trigger' section",
            "no '## Non-case' section",
        ):
            with self.subTest(missing=expected):
                self.assertEqual(len([r for r in derived["reasons"] if expected in r]), 1, derived["reasons"])
        # constraint: ed3c/noodles#120 - ed3c/noodles#69's acceptance really does name all four
        # constraint: obligations, so this control proves the completeness gate rejects it for the
        # constraint: obligations it actually lacks, not for a blanket "old issue" verdict.
        self.assertFalse([r for r in derived["reasons"] if "Physical acceptance" in r], derived["reasons"])

    def test_each_planted_completeness_defect_fails_with_its_own_reason(self) -> None:
        cases = (
            ("goal emptied", issue_body(goal=""), "no '## goal' section"),
            ("claim emptied", issue_body(claim=""), "no '## claim' section"),
            ("trigger emptied", issue_body(trigger=""), "no '## Physical trigger' section"),
            ("non-case emptied", issue_body(non_case=""), "no '## Non-case' section"),
            ("no positive control", issue_body(acceptance="- Planted-negative readback with zero residue."), "no positive control obligation"),
            ("no planted negative", issue_body(acceptance="- Positive control readback with zero residue."), "no planted-negative control obligation"),
            ("no readback", issue_body(acceptance="- Positive control and planted-negative control, zero residue."), "no direct readback obligation"),
            ("no residue", issue_body(acceptance="- Positive control and planted-negative control readback."), "no zero-residue readback obligation"),
        )
        seen: list[str] = []
        for label, body, expected in cases:
            with self.subTest(plant=label):
                derived = self.derive(body)
                self.assertFalse(derived["schedulable"])
                matched = [reason for reason in derived["reasons"] if expected in reason]
                self.assertEqual(len(matched), 1, derived["reasons"])
                seen.append(matched[0])
        self.assertEqual(len(set(seen)), len(seen), "each plant must produce its own distinct reason")

    def test_admitted_rationale_heading_and_explicit_none_non_case_are_accepted(self) -> None:
        complete = issue_body()
        reworded = complete.replace("## Physical trigger", "## Why this must land alone", 1)
        self.assertEqual(self.derive(reworded), {"schedulable": True, "reasons": []})
        self.assertIn(f"\n## Non-case\n\n{issue_contract.NON_CASE_NONE}\n", complete)

    def test_provider_readback_is_required_only_when_the_claim_takes_provider_authority(self) -> None:
        local = issue_body(claim="The local gate refuses an incomplete body.")
        self.assertEqual(self.derive(local), {"schedulable": True, "reasons": []})
        provider = issue_body(claim="The provider merge and closure readback admits the exact head.")
        derived = self.derive(provider)
        self.assertFalse(derived["schedulable"])
        self.assertTrue(any("no provider readback obligation" in reason for reason in derived["reasons"]))
        cured = issue_body(
            claim="The provider merge and closure readback admits the exact head.",
            acceptance=COMPLETE_ACCEPTANCE + "- Provider readback of the merge event.\n",
        )
        self.assertEqual(self.derive(cured), {"schedulable": True, "reasons": []})

    def test_awkward_but_structurally_complete_prose_is_not_rejected(self) -> None:
        awkward = issue_body(
            trigger="thing broke, badly, again",
            goal="make the thing not broke",
            claim="the thing shall be less broke, we think",
            acceptance="- positive control: it works. planted-negative control: it does not. readback. no residue.",
            non_case="nope",
            non_claims="- we claim nothing at all, really",
        )
        self.assertEqual(self.derive(awkward), {"schedulable": True, "reasons": []})

    def test_body_digest_drift_reevaluates_completeness_on_the_exact_new_bytes(self) -> None:
        complete = issue_body()
        drifted = issue_body(claim="")
        self.assertNotEqual(issue_contract.body_digest(complete), issue_contract.body_digest(drifted))
        self.assertTrue(self.derive(complete)["schedulable"])
        self.assertFalse(self.derive(drifted)["schedulable"])


class SectionAndDigestTests(unittest.TestCase):
    def test_sections_are_typed_by_normalized_heading(self) -> None:
        parsed = issue_contract.sections(issue_body())
        self.assertEqual(
            set(parsed),
            {"physical_trigger", "goal", "claim", "physical_acceptance", "non_case", "non_claims"},
        )
        self.assertIn("Derive schedulability", parsed["goal"])

    def test_body_digest_is_the_exact_provider_bytes(self) -> None:
        body = issue_body()
        self.assertEqual(issue_contract.body_digest(body), hashlib.sha256(body.encode("utf-8")).hexdigest())
        self.assertNotEqual(issue_contract.body_digest(body), issue_contract.body_digest(body + " "))


class ContractReadbackTests(unittest.TestCase):
    """One read-only command returns the typed contract; it never mutates the provider."""

    def gh(self, bodies: dict[str, str]):
        def fake(endpoint: str, *, method: str = "GET", payload: object | None = None, token: str | None = None) -> dict:
            if method != "GET":
                raise AssertionError(f"read-only contract attempted {method} {endpoint}")
            for subject, body in bodies.items():
                repo, _, number = subject.partition("#")
                if endpoint == f"repos/{repo}/issues/{number}":
                    state = "closed" if "noodles-state: landed" in body else "open"
                    return {"number": int(number), "state": state, "body": body, "html_url": f"https://github.test/{subject}"}
            raise noodles.GateError(f"provider read failed for {endpoint}")

        return fake

    def test_typed_contract_readback_is_complete_and_schedulable(self) -> None:
        body = issue_body(depends_on=PREDECESSOR)
        bodies = {SUBJECT: body, PREDECESSOR: predecessor_body()}
        with mock.patch.object(noodles, "gh_api", side_effect=self.gh(bodies)) as api:
            contract = noodles.issue_contract_readback(SUBJECT)
        self.assertTrue(all(call.kwargs.get("method", "GET") == "GET" for call in api.call_args_list))
        self.assertEqual(contract["subject"], SUBJECT)
        self.assertEqual(contract["target"], "ed3c/noodles")
        self.assertEqual(contract["dependencies"], [PREDECESSOR])
        self.assertEqual(contract["body_sha256"], issue_contract.body_digest(body))
        self.assertEqual(contract["provider_state"], "open")
        self.assertIn("Derive schedulability", contract["goal"])
        self.assertIn("Planted-negative", contract["physical_acceptance"])
        self.assertIn("No scheduler", contract["non_claims"])
        self.assertEqual(contract["dependency_states"][PREDECESSOR]["state"], "landed")
        self.assertTrue(contract["schedulable"])

    def test_body_digest_drift_is_visible_in_the_readback(self) -> None:
        bodies = {SUBJECT: issue_body(), PREDECESSOR: predecessor_body()}
        with mock.patch.object(noodles, "gh_api", side_effect=self.gh(bodies)):
            first = noodles.issue_contract_readback(SUBJECT)
        drifted = issue_body(goal="Goal text edited on the provider after scheduling.")
        with mock.patch.object(noodles, "gh_api", side_effect=self.gh({SUBJECT: drifted, PREDECESSOR: predecessor_body()})):
            second = noodles.issue_contract_readback(SUBJECT)
        self.assertNotEqual(first["body_sha256"], second["body_sha256"])
        self.assertEqual(second["body_sha256"], issue_contract.body_digest(drifted))

    def test_dependency_provider_read_failure_fails_closed_with_the_exact_diagnostic(self) -> None:
        with mock.patch.object(noodles, "gh_api", side_effect=self.gh({SUBJECT: issue_body(depends_on=PREDECESSOR)})):
            contract = noodles.issue_contract_readback(SUBJECT)
        self.assertFalse(contract["schedulable"])
        self.assertIn(PREDECESSOR, contract["dependency_states"])
        self.assertIn("provider read failed", " ".join(contract["reasons"]))

    def test_cli_prints_the_typed_contract(self) -> None:
        bodies = {SUBJECT: issue_body(depends_on=PREDECESSOR), PREDECESSOR: predecessor_body()}
        with mock.patch.object(noodles, "gh_api", side_effect=self.gh(bodies)), \
             mock.patch("sys.stdout") as stdout:
            self.assertEqual(noodles.main(["issue", "contract", SUBJECT]), 0)
        printed = json.loads("".join(call.args[0] for call in stdout.write.call_args_list if call.args))
        self.assertEqual(printed["subject"], SUBJECT)
        self.assertTrue(printed["schedulable"])


class BacklogAdapterTests(unittest.TestCase):
    """Backlog output carries the typed data the schedule skill needs, with no invented gh commands."""

    def gh(self, dependent_body: str, predecessor_state: str = "landed"):
        calls: list[str] = []

        def fake(endpoint: str, *, method: str = "GET", payload: object | None = None, token: str | None = None) -> object:
            calls.append(endpoint)
            if endpoint == "repos/ed3c/noodles/issues?state=open&per_page=100":
                return [
                    {"number": 82, "state": "open", "body": dependent_body, "title": "dependent", "html_url": "https://github.test/82"},
                    {"number": 90, "state": "open", "body": issue_body(subject="ed3c/noodles#90"), "title": "independent", "html_url": "https://github.test/90"},
                ]
            if endpoint == "repos/ed3c/noodles/issues/81":
                return {"number": 81, "state": "closed" if predecessor_state == "landed" else "open", "body": predecessor_body(predecessor_state)}
            raise noodles.GateError(f"unexpected endpoint {endpoint}")

        return fake, calls

    def sync(self, dependent_body: str, predecessor_state: str = "landed") -> tuple[list[dict], list[str]]:
        fake, calls = self.gh(dependent_body, predecessor_state)
        printed: list[str] = []
        with mock.patch.object(noodles, "gh_api", side_effect=fake), \
             mock.patch.dict("os.environ", {"NOODLES_REPOSITORIES": "ed3c/noodles"}, clear=False), \
             mock.patch("builtins.print", side_effect=lambda line, **_: printed.append(line)):
            self.assertEqual(noodles.adapter_sync(), 0)
        return [json.loads(line) for line in printed], calls

    def test_landed_predecessor_releases_the_dependent_without_a_marker_patch(self) -> None:
        items, calls = self.sync(issue_body(depends_on=PREDECESSOR))
        dependent = next(item for item in items if item["id"] == SUBJECT)
        self.assertEqual(dependent["status"], "ready")
        self.assertEqual(dependent["dependencies"], [PREDECESSOR])
        self.assertTrue(dependent["schedulable"])
        self.assertEqual(dependent["reasons"], [])
        self.assertEqual(dependent["target"], "ed3c/noodles")
        self.assertEqual(dependent["body_sha256"], issue_contract.body_digest(issue_body(depends_on=PREDECESSOR)))
        self.assertEqual(calls.count("repos/ed3c/noodles/issues/81"), 1)

    def test_open_predecessor_holds_the_dependent_with_an_exact_reason(self) -> None:
        items, _ = self.sync(issue_body(depends_on=PREDECESSOR), predecessor_state="ready")
        dependent = next(item for item in items if item["id"] == SUBJECT)
        self.assertFalse(dependent["schedulable"])
        self.assertIn(PREDECESSOR, " ".join(dependent["reasons"]))
        self.assertTrue(next(item for item in items if item["id"] == "ed3c/noodles#90")["schedulable"])


class IntakeNormalizerTests(unittest.TestCase):
    """A nonconforming open issue is cured mechanically at intake exactly once, and never by content generation."""

    def open_issue(self, number: int, body: str, title: str = "Intake atom") -> dict:
        return {
            "number": number,
            "state": "open",
            "title": title,
            "body": body,
            "html_url": f"https://github.test/{number}",
        }

    def sync(self, state: dict[int, dict]) -> tuple[list[dict], list[tuple[str, str, dict]]]:
        writes: list[tuple[str, str, dict]] = []

        def fake(endpoint: str, *, method: str = "GET", payload: dict | None = None, token: object | None = None) -> object:
            if method == "GET" and endpoint == "repos/ed3c/noodles/issues?state=open&per_page=100":
                return [dict(issue) for issue in state.values()]
            if method == "GET" and endpoint.startswith("repos/ed3c/noodles/issues/"):
                return dict(state[int(endpoint.rsplit("/", 1)[1])])
            if method == "PATCH" and endpoint.startswith("repos/ed3c/noodles/issues/"):
                writes.append((method, endpoint, dict(payload or {})))
                number = int(endpoint.rsplit("/", 1)[1])
                state[number]["body"] = (payload or {})["body"]
                return dict(state[number])
            if method == "POST" and endpoint.endswith("/comments"):
                writes.append((method, endpoint, dict(payload or {})))
                return {"id": len(writes)}
            raise noodles.GateError(f"unexpected endpoint {method} {endpoint}")

        printed: list[str] = []
        with mock.patch.object(noodles, "gh_api", side_effect=fake), \
             mock.patch.dict("os.environ", {"NOODLES_REPOSITORIES": "ed3c/noodles"}, clear=False), \
             mock.patch("builtins.print", side_effect=lambda line, **_: printed.append(line)):
            self.assertEqual(noodles.adapter_sync(), 0)
        return [json.loads(line) for line in printed], writes

    def test_conforming_issue_is_never_written(self) -> None:
        state = {82: self.open_issue(82, issue_body())}
        items, writes = self.sync(state)
        self.assertEqual(writes, [])
        self.assertEqual(items[0]["status"], "ready")
        self.assertTrue(items[0]["schedulable"])

    def test_marker_free_issue_is_normalized_exactly_once(self) -> None:
        original = "Implementation prose that nobody expressed as a contract.\n"
        state = {151: self.open_issue(151, original, title="Nonconforming atom")}
        items, writes = self.sync(state)
        self.assertEqual([write[0] for write in writes], ["PATCH", "POST"])
        normalized = state[151]["body"]
        self.assertTrue(normalized.endswith("\n" + original), normalized)
        contract = noodles.parse_issue_contract(normalized, "ed3c/noodles#151")
        self.assertEqual(contract["state"], "blocked")
        self.assertEqual(contract["blocker"]["owner"], "intake-normalizer")
        self.assertEqual(contract["dependencies"], [])
        self.assertEqual(items[0]["status"], "blocked")
        self.assertFalse(items[0]["schedulable"])
        for defect in ("noodles-role", "noodles-target", "noodles-subject", "noodles-state"):
            with self.subTest(defect=defect):
                self.assertIn(f"missing {defect} marker", contract["blocker"]["reason"])
                self.assertIn(f"missing {defect} marker", writes[1][2]["body"])
        self.assertIn("## Physical acceptance", writes[1][2]["body"])
        _, resync = self.sync(state)
        self.assertEqual(resync, [])

    def test_normalization_never_authors_the_missing_sections(self) -> None:
        state = {151: self.open_issue(151, "Only prose.\n")}
        self.sync(state)
        self.assertNotIn("## Goal", state[151]["body"])
        self.assertFalse(self.sync(state)[0][0]["schedulable"])

    def test_absent_dependency_marker_is_migrated_instead_of_blocked(self) -> None:
        original = issue_body().replace("<!-- noodles-depends-on: none -->\n", "")
        state = {82: self.open_issue(82, original)}
        items, writes = self.sync(state)
        self.assertEqual([write[0] for write in writes], ["PATCH"])
        self.assertTrue(state[82]["body"].endswith("\n" + original))
        self.assertEqual(items[0]["status"], "ready")
        self.assertTrue(items[0]["schedulable"])
        self.assertEqual(items[0]["dependencies"], [])
        self.assertEqual(self.sync(state)[1], [])

    def test_prose_dependency_declaration_is_converted_to_the_typed_marker(self) -> None:
        original = issue_body(goal=f"Land the parser.\n\nDepends on: {PREDECESSOR}").replace(
            "<!-- noodles-depends-on: none -->\n", ""
        )
        state = {
            82: self.open_issue(82, original),
            81: self.open_issue(81, predecessor_body()),
        }
        state[81]["state"] = "closed"
        items, _ = self.sync(state)
        dependent = next(item for item in items if item["id"] == SUBJECT)
        self.assertEqual(dependent["dependencies"], [PREDECESSOR])
        self.assertIn(f"<!-- noodles-depends-on: {PREDECESSOR} -->", state[82]["body"])

    def test_ambiguous_dependency_prose_is_never_guessed(self) -> None:
        original = issue_body(goal="Land the parser.\n\nDepends on: the parser rewrite").replace(
            "<!-- noodles-depends-on: none -->\n", ""
        )
        state = {82: self.open_issue(82, original)}
        items, writes = self.sync(state)
        self.assertEqual(writes, [])
        self.assertEqual(state[82]["body"], original)
        self.assertFalse(items[0]["schedulable"])
        self.assertIn("no noodles-depends-on marker", " ".join(items[0]["reasons"]))

    def test_uncurable_defect_stays_visible_without_overwriting_the_authored_state(self) -> None:
        offending = "docs/research/2026-08-29-note.md"
        original = issue_body(acceptance=f"- Evidence: {offending}\n")
        state = {82: self.open_issue(82, original)}
        items, writes = self.sync(state)
        self.assertEqual([write[0] for write in writes], ["PATCH", "POST"])
        self.assertIn("<!-- noodles-state: ready -->", state[82]["body"])
        self.assertNotIn("noodles-blocker", state[82]["body"])
        self.assertEqual(items[0]["status"], "blocked")
        self.assertIn(offending, items[0]["diagnostic"])
        self.assertIn(offending, writes[1][2]["body"])
        self.assertEqual(self.sync(state)[1], [])

    def test_issue_template_file_normalizes_into_a_schedulable_contract(self) -> None:
        text = (CANDIDATE_ROOT / ".github/ISSUE_TEMPLATE/repository-mutating-atom.md").read_text(encoding="utf-8")
        authored = text.split("\n---\n", 1)[1].lstrip("\n")
        self.assertIsNone(noodles.MARKER_PATTERNS["subject"].search(authored))
        state = {900: self.open_issue(900, authored, title="Template atom")}
        items, writes = self.sync(state)
        self.assertEqual([write[0] for write in writes], ["PATCH"])
        self.assertEqual(items[0]["status"], "ready")
        self.assertTrue(items[0]["schedulable"], items[0]["reasons"])
        self.assertEqual(items[0]["id"], "ed3c/noodles#900")


class DependencyDerivationTests(unittest.TestCase):
    """Only an explicit declaration line is converted; anything ambiguous refuses to derive."""

    def test_derivations(self) -> None:
        cases = {
            "no declaration at all\n": "none",
            "Depends on: none\n": "none",
            "- **Blocked by**: ed3c/noodles#81\n": "ed3c/noodles#81",
            "Depends on: #81, #90\n": "ed3c/noodles#81, ed3c/noodles#90",
            "Depends on: the parser rewrite\n": None,
            "Depends on: other/repo#3\n": None,
            f"Depends on: {SUBJECT}\n": None,
        }
        for body, expected in cases.items():
            with self.subTest(body=body):
                self.assertEqual(issue_contract.derive_dependencies(body, SUBJECT), expected)


if __name__ == "__main__":
    unittest.main()

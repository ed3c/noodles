"""Planted fixtures for closure disposition receipts: a not-planned retirement is a contract event
whose reasoning chain must survive it (ed3c/noodles#184).

The positive fixture is ed3c/noodles#151's verbatim closing comment, held in
`tests/fixtures/closure-disposition-receipt.json` so the control never depends on live provider state.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

import disposition_contract
import noodles
from tests.support import CANDIDATE_ROOT, ISSUE_DEPENDS_ON_MARKER

REPOSITORY = "ed3c/noodles"
FIXTURE_PATH = Path("tests/fixtures/closure-disposition-receipt.json")
RECEIPT = json.loads((CANDIDATE_ROOT / FIXTURE_PATH).read_text(encoding="utf-8"))["receipt"]
# constraint: the one line of the real receipt that carries each required element, dropped one at a time.
ELEMENT_LINE_KEY = {
    "payload_custody": "PAYLOAD CUSTODY",
    "reopen_condition": "FALSIFIABLE REOPEN CONDITION",
    "trade_off": "Trade-off record",
}


def issue_body(number: int, state: str = "ready", blocker: str | None = None) -> str:
    marker = f"<!-- noodles-blocker: {blocker} -->\n" if blocker else ""
    return (
        "<!-- noodles-role: repository-mutating-atom -->\n"
        f"<!-- noodles-target: {REPOSITORY} -->\n"
        f"<!-- noodles-subject: {REPOSITORY}#{number} -->\n"
        f"<!-- noodles-state: {state} -->\n"
        f"{marker}"
        f"{ISSUE_DEPENDS_ON_MARKER}\n\n"
        "## Goal\n\nOne retired atom.\n\n"
        "## Physical acceptance\n\n- Exact controls pass.\n\n"
        "## Non-claims\n\n- Nothing adjacent.\n"
    )


def receipt_without(element: str) -> str:
    key = ELEMENT_LINE_KEY[element]
    return "\n".join(line for line in RECEIPT.splitlines() if key not in line)


class ClosureProvider:
    """Stateful provider double for closed-issue listing, comment threads, and reopen mutations."""

    def __init__(self, issues: list[dict], comments: dict[int, list[str]] | None = None, *, flood: bool = False) -> None:
        self.issues = {int(item["number"]): dict(item) for item in issues}
        self.comments = {number: list(bodies) for number, bodies in (comments or {}).items()}
        self.posted: list[tuple[int, str]] = []
        self.patched: list[tuple[int, dict]] = []
        self.flood = flood

    def api(self, endpoint: str, *, method: str = "GET", payload: object | None = None, token: str | None = None) -> object:
        if endpoint.startswith(f"repos/{REPOSITORY}/issues?state=closed"):
            if self.flood:
                return [dict(self.issues[min(self.issues)]) for _ in range(disposition_contract.PAGE_SIZE)]
            page = int(endpoint.rpartition("page=")[2])
            return [dict(item) for item in self.issues.values()] if page == 1 else []
        if endpoint.startswith(f"repos/{REPOSITORY}/issues/") and endpoint.endswith("/comments?per_page=100"):
            number = int(endpoint.split("/issues/")[1].split("/")[0])
            return [{"body": body} for body in self.comments.get(number, [])]
        if endpoint.startswith(f"repos/{REPOSITORY}/issues/") and endpoint.endswith("/comments") and method == "POST":
            number = int(endpoint.split("/issues/")[1].split("/")[0])
            assert isinstance(payload, dict)
            self.posted.append((number, str(payload["body"])))
            self.comments.setdefault(number, []).append(str(payload["body"]))
            return {"id": 1}
        if endpoint.startswith(f"repos/{REPOSITORY}/issues/"):
            number = int(endpoint.rpartition("/")[2])
            if method == "PATCH":
                assert isinstance(payload, dict)
                self.patched.append((number, dict(payload)))
                self.issues[number].update({key: value for key, value in payload.items() if key in ("state", "state_reason", "body")})
            return dict(self.issues[number])
        raise AssertionError(f"unexpected provider call: {method} {endpoint}")


class ClosureDispositionTests(unittest.TestCase):
    def sweep(self, provider: ClosureProvider) -> list[dict]:
        with mock.patch.object(noodles, "gh_api", side_effect=provider.api):
            return disposition_contract.sweep_closure_dispositions(CANDIDATE_ROOT)

    def retired(self, number: int, **kwargs) -> dict:
        return {"number": number, "state": "closed", "state_reason": "not_planned", "body": issue_body(number, **kwargs)}

    def test_issue_151_actual_closing_receipt_sweeps_clean(self) -> None:
        self.assertEqual(disposition_contract.disposition_defects(RECEIPT), ())
        provider = ClosureProvider([self.retired(151, state="blocked", blocker="owner: brief needs decomposition")], {151: [RECEIPT]})
        self.assertEqual(self.sweep(provider), [{"subject": f"{REPOSITORY}#151", "action": "receipt_admitted", "defects": []}])
        self.assertEqual(provider.posted, [])
        self.assertEqual(provider.patched, [])

    def test_planted_bare_closure_is_flagged_and_reopened_as_blocked(self) -> None:
        provider = ClosureProvider([self.retired(182)], {182: ["Closing this, not worth the complexity."]})
        outcomes = self.sweep(provider)
        self.assertEqual(outcomes, [{
            "subject": f"{REPOSITORY}#182",
            "action": "reopened",
            "defects": ["payload_custody", "reopen_condition", "trade_off"],
            "blocked": True,
        }])
        self.assertEqual(len(provider.posted), 1)
        diagnostic = provider.posted[0][1]
        for element in ELEMENT_LINE_KEY:
            self.assertIn(f"`{element}`", diagnostic)
        self.assertIn(disposition_contract.POSITIVE_FIXTURE_SUBJECT, diagnostic)
        self.assertEqual(provider.issues[182]["state"], "open")
        body = provider.issues[182]["body"]
        self.assertEqual(noodles.one_marker(body, "state"), "blocked")
        contract = noodles.parse_issue_contract(body, expected_subject=f"{REPOSITORY}#182")
        self.assertEqual(contract["blocker"]["owner"], disposition_contract.BLOCKER_OWNER)

    def test_each_required_element_is_independently_load_bearing(self) -> None:
        for element in ELEMENT_LINE_KEY:
            with self.subTest(element=element):
                thread = receipt_without(element)
                self.assertEqual(disposition_contract.disposition_defects(thread), (element,))
                provider = ClosureProvider([self.retired(182)], {182: [thread]})
                self.assertEqual(self.sweep(provider)[0]["defects"], [element])
                self.assertIn(f"`{element}`", provider.posted[0][1])

    def test_completed_and_unmarked_closures_are_never_reopened(self) -> None:
        landed = {"number": 90, "state": "closed", "state_reason": "completed", "body": issue_body(90)}
        unmarked = {"number": 91, "state": "closed", "state_reason": "not_planned", "body": "No markers here.\n"}
        provider = ClosureProvider([landed, unmarked], {90: [], 91: []})
        self.assertEqual(self.sweep(provider), [{
            "subject": f"{REPOSITORY}#91",
            "action": "skipped",
            "reason": "issue bears no exact noodles-subject marker",
        }])
        self.assertEqual(provider.posted, [])
        self.assertEqual(provider.patched, [])

    def test_already_flagged_retirement_is_not_commented_twice(self) -> None:
        subject = f"{REPOSITORY}#182"
        prior = disposition_contract.disposition_diagnostic(subject, ("payload_custody", "reopen_condition", "trade_off"))
        provider = ClosureProvider([self.retired(182)], {182: ["bare", prior]})
        outcome = self.sweep(provider)[0]
        self.assertEqual(outcome["action"], "reopened")
        self.assertEqual(provider.posted, [])
        self.assertEqual(provider.issues[182]["state"], "open")
        # constraint: the diagnostic names every element, so it must never launder itself into a receipt.
        self.assertEqual(outcome["defects"], ["payload_custody", "reopen_condition", "trade_off"])
        self.assertEqual(disposition_contract.receipt_text([prior]), "")

    def test_page_walk_overrun_fails_closed_instead_of_reading_as_complete(self) -> None:
        provider = ClosureProvider([self.retired(182)], {182: ["bare"]}, flood=True)
        with self.assertRaises(noodles.GateError) as caught:
            self.sweep(provider)
        self.assertIn("exceeded", str(caught.exception))
        self.assertEqual(provider.posted, [])

    def test_reopen_that_does_not_read_back_open_fails_closed(self) -> None:
        provider = ClosureProvider([self.retired(182)], {182: ["bare"]})
        original = provider.api

        def stuck(endpoint: str, **kwargs):
            result = original(endpoint, **kwargs)
            if endpoint == f"repos/{REPOSITORY}/issues/182" and kwargs.get("method", "GET") == "GET":
                return {**result, "state": "closed"}
            return result

        with mock.patch.object(noodles, "gh_api", side_effect=stuck):
            with self.assertRaises(noodles.GateError) as caught:
                disposition_contract.sweep_closure_dispositions(CANDIDATE_ROOT)
        self.assertIn("reopen readback failed", str(caught.exception))

    def test_reconcile_reports_closure_dispositions_alongside_claims(self) -> None:
        with mock.patch.object(noodles, "reconcile_once", return_value=[]), \
             mock.patch.object(noodles, "sweep_dead_claims", return_value=[]), \
             mock.patch.object(noodles, "sweep_closure_dispositions", return_value=[{"subject": "x", "action": "reopened"}]) as sweep, \
             mock.patch.object(noodles.sys, "argv", ["noodles", "reconcile", "--control-url", "http://noodle.test"]):
            self.assertEqual(noodles.main(), 0)
        sweep.assert_called_once_with(CANDIDATE_ROOT)


if __name__ == "__main__":
    unittest.main()

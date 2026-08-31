"""Component-surface gate: every issue declares one owned component from the repo-owned map, and
trusted verification fails closed when the candidate's changed files vs merge base escape that
component's admitted surface. Planted positive and negative fixtures run against the exact
candidate component map so scope creep becomes a mechanical FAIL, not a prompt-layer plea."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import noodles
from tests.support import CANDIDATE_ROOT, load_ready_backlog_fixtures

HEAD_SHA = "a" * 40
SUBJECT = "ed3c/noodles#900007"


def issue_body(*, component: str | None = "verify", state: str = "ready") -> str:
    component_marker = f"<!-- noodles-component: {component} -->\n" if component is not None else ""
    return (
        "<!-- noodles-role: repository-mutating-atom -->\n"
        "<!-- noodles-target: ed3c/noodles -->\n"
        f"<!-- noodles-subject: {SUBJECT} -->\n"
        f"<!-- noodles-state: {state} -->\n"
        f"{component_marker}"
        "<!-- noodles-depends-on: none -->\n\n"
        "## Goal\n\nBound the mutation surface.\n\n"
        "## Physical acceptance\n\n- Planted controls fail closed.\n\n"
        "## Non-claims\n\n- No intra-component design quality is enforced.\n"
    )


class ComponentMarkerParseTests(unittest.TestCase):
    def test_parser_accepts_component_marker(self) -> None:
        contract = noodles.parse_issue_contract(issue_body(component="verify"), SUBJECT)
        self.assertEqual(contract["component"], "verify")

    def test_parser_defaults_absent_component_to_empty(self) -> None:
        contract = noodles.parse_issue_contract(issue_body(component=None), SUBJECT)
        self.assertEqual(contract["component"], "")

    def test_prose_mention_is_not_a_marker(self) -> None:
        body = issue_body(component=None).replace(
            "## Goal\n\n",
            "## Goal\n\nThe parser accepts a `noodles-component:` HTML comment marker.\n\n",
        )
        contract = noodles.parse_issue_contract(body, SUBJECT)
        self.assertEqual(contract["component"], "")

    def test_duplicate_component_markers_fail_closed(self) -> None:
        body = issue_body(component="verify") + "<!-- noodles-component: docs -->\n"
        with self.assertRaisesRegex(noodles.GateError, "expected one noodles-component marker"):
            noodles.parse_issue_contract(body, SUBJECT)

    def test_invalid_component_token_fails_closed(self) -> None:
        with self.assertRaisesRegex(noodles.GateError, "lowercase component token"):
            noodles.parse_issue_contract(issue_body(component="Verify Stuff"), SUBJECT)

    def test_durable_corpus_carries_a_component_declaring_ready_shape(self) -> None:
        fixtures = {fixture.id: fixture for fixture in load_ready_backlog_fixtures(CANDIDATE_ROOT)}
        fixture = fixtures["ready-component-declared"]
        contract = noodles.parse_issue_contract(fixture.body, fixture.subject)
        self.assertEqual(contract["state"], "ready")
        self.assertEqual(contract["component"], "verify")


class ComponentMapTests(unittest.TestCase):
    def test_candidate_component_map_is_valid_and_names_expected_components(self) -> None:
        components = noodles.component_map(CANDIDATE_ROOT)
        self.assertEqual(set(components), {"schedule", "verify", "carrier", "contract", "docs"})
        for name, globs in components.items():
            with self.subTest(component=name):
                self.assertTrue(globs)
                self.assertTrue(all(isinstance(glob, str) and glob for glob in globs))

    def test_missing_map_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(noodles.GateError, "cannot read JSON"):
                noodles.component_map(Path(temp))

    def test_wrong_schema_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / noodles.COMPONENT_MAP_PATH
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"schema_version": 2, "components": {"docs": ["*"]}}), encoding="utf-8")
            with self.assertRaisesRegex(noodles.GateError, "schema_version 1"):
                noodles.component_map(Path(temp))

    def test_empty_globs_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / noodles.COMPONENT_MAP_PATH
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"schema_version": 1, "components": {"docs": []}}), encoding="utf-8")
            with self.assertRaisesRegex(noodles.GateError, "non-empty list of path glob strings"):
                noodles.component_map(Path(temp))


class ComponentSurfaceGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.components = noodles.component_map(CANDIDATE_ROOT)

    def test_planted_positive_candidate_within_declared_surface_passes(self) -> None:
        errors = noodles.component_surface_errors(
            "docs", self.components, ["AGENTS.md", "contracts/system-v1.md", "docs/notes.md"]
        )
        self.assertEqual(errors, [])

    def test_planted_negative_candidate_touching_second_component_surface_fails(self) -> None:
        errors = noodles.component_surface_errors(
            "docs", self.components, ["docs/notes.md", "schedule_domain.py"]
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("mutation outside admitted component 'docs'", errors[0])
        self.assertIn("schedule_domain.py", errors[0])
        self.assertNotIn("docs/notes.md", errors[0])

    def test_missing_component_declaration_fails_closed(self) -> None:
        errors = noodles.component_surface_errors("", self.components, ["docs/notes.md"])
        self.assertEqual(len(errors), 1)
        self.assertIn("declares no noodles-component marker", errors[0])

    def test_undeclared_component_name_fails_closed_naming_admitted_components(self) -> None:
        errors = noodles.component_surface_errors("kitchen", self.components, ["docs/notes.md"])
        self.assertEqual(len(errors), 1)
        self.assertIn("'kitchen'", errors[0])
        self.assertIn("carrier, contract, docs, schedule, verify", errors[0])

    def test_contract_component_legitimately_spans_components(self) -> None:
        errors = noodles.component_surface_errors(
            "contract", self.components, ["noodles.py", "schedule_domain.py", "policy/components.json"]
        )
        self.assertEqual(errors, [])


class CompareReadbackTests(unittest.TestCase):
    def test_rename_contributes_both_paths(self) -> None:
        comparison = {
            "files": [
                {"filename": "docs/new.md", "previous_filename": "docs/old.md"},
                {"filename": "AGENTS.md"},
            ]
        }
        self.assertEqual(
            noodles.compare_changed_files(comparison), ["AGENTS.md", "docs/new.md", "docs/old.md"]
        )

    def test_missing_files_list_fails_closed(self) -> None:
        with self.assertRaisesRegex(noodles.GateError, "no files list"):
            noodles.compare_changed_files({"total_commits": 1})

    def test_unnamed_file_entry_fails_closed(self) -> None:
        with self.assertRaisesRegex(noodles.GateError, "without a filename"):
            noodles.compare_changed_files({"files": [{"status": "modified"}]})

    def test_truncation_ceiling_fails_closed(self) -> None:
        files = [{"filename": f"docs/{index}.md"} for index in range(noodles.COMPARE_FILES_CEILING)]
        with self.assertRaisesRegex(noodles.GateError, "not fully observable"):
            noodles.compare_changed_files({"files": files})


class VerifyPullRequestComponentGateTests(unittest.TestCase):
    """The trusted verify path consumes the marker, the trusted-root map, and merge-base readback."""

    def run_verify(self, body: str, changed_files: list[str]) -> tuple[Path, object]:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        event_path = base / "event.json"
        event_path.write_text(
            json.dumps(
                {
                    "pull_request": {
                        "number": 7,
                        "head": {"sha": HEAD_SHA},
                        "base": {"ref": "main"},
                        "draft": False,
                        "body": f"Refs {SUBJECT}",
                    },
                    "repository": {"full_name": "ed3c/noodles"},
                }
            ),
            encoding="utf-8",
        )
        receipt_path = base / "receipt.json"
        fake_repository = {"ok": True, "errors": [], "metrics": {}}

        def fake_git(root: Path, *args: str, check: bool = True) -> str:
            if args == ("rev-parse", "HEAD"):
                return HEAD_SHA
            if args == ("rev-parse", "HEAD^{tree}"):
                return "b" * 40
            raise AssertionError(f"unexpected git call: {args}")

        with mock.patch.object(noodles, "issue_read", return_value={"state": "open", "body": body}), \
                mock.patch.object(noodles, "merge_base_changed_files", return_value=changed_files) as compare, \
                mock.patch.object(noodles, "verify_repository", return_value=fake_repository), \
                mock.patch.object(noodles, "git", side_effect=fake_git):
            receipt = noodles.verify_pull_request(CANDIDATE_ROOT, event_path, base, receipt_path)
        self.assertEqual(compare.call_args, mock.call("ed3c/noodles", "main", HEAD_SHA))
        return receipt_path, receipt

    def test_within_surface_candidate_receives_component_surface_receipt(self) -> None:
        body = issue_body(component="docs", state="awaiting_land")
        receipt_path, receipt = self.run_verify(body, ["AGENTS.md", "contracts/system-v1.md", "docs/notes.md"])
        self.assertEqual(receipt["component"], "docs")
        self.assertIn("component-surface", receipt["gates"])
        written = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(written["component"], "docs")

    def test_outside_surface_candidate_fails_closed_naming_paths_and_component(self) -> None:
        body = issue_body(component="docs", state="awaiting_land")
        with self.assertRaises(noodles.GateError) as raised:
            self.run_verify(body, ["docs/notes.md", "schedule_domain.py"])
        diagnostic = str(raised.exception)
        self.assertIn("component-surface gate failed", diagnostic)
        self.assertIn("'docs'", diagnostic)
        self.assertIn("schedule_domain.py", diagnostic)

    def test_marker_less_issue_fails_closed_before_repository_verification(self) -> None:
        body = issue_body(component=None, state="awaiting_land")
        with self.assertRaises(noodles.GateError) as raised:
            self.run_verify(body, ["docs/notes.md"])
        self.assertIn("declares no noodles-component marker", str(raised.exception))


if __name__ == "__main__":
    unittest.main()

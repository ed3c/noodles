"""Component-surface gate: every issue declares one owned component from the repo-owned map, and
trusted verification fails closed when the candidate's changed files vs merge base escape that
component's admitted surface. Planted positive and negative fixtures run against the exact
candidate component map so scope creep becomes a mechanical FAIL, not a prompt-layer plea."""
from __future__ import annotations

import ast
import fnmatch
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import noodles
from tests.support import CANDIDATE_ROOT, ENGINE_ROOT, load_ready_backlog_fixtures

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


class ComponentImportEdgeGateTests(unittest.TestCase):
    """ed3c/noodles#257: the file glob bounds which files change, not what they start importing."""

    MODULES = ("issue_contract.py", "schedule_domain.py", "codex_isolation.py", "runtime_contract.py")

    def setUp(self) -> None:
        self.components = noodles.component_map(CANDIDATE_ROOT)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name) / "base"
        self.candidate = Path(temp.name) / "candidate"
        for root in (self.base, self.candidate):
            root.mkdir(parents=True)
            for module in self.MODULES:
                (root / module).write_text("VALUE = 1\n", encoding="utf-8")

    def plant(self, path: str, before: str | None, after: str | None) -> None:
        for root, text in ((self.base, before), (self.candidate, after)):
            target = root / path
            if text is None:
                target.unlink(missing_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")

    def errors(self, component: str, changed: list[str]) -> list[str]:
        return noodles.component_import_edge_errors(
            component, self.components, changed, self.base, self.candidate
        )

    def test_positive_new_import_inside_the_declared_surface_passes(self) -> None:
        self.plant("runtime_contract.py", "VALUE = 1\n", "import codex_isolation\nVALUE = 1\n")
        self.assertEqual(self.errors("carrier", ["runtime_contract.py"]), [])

    def test_planted_negative_new_import_outside_the_declared_surface_fails_closed(self) -> None:
        self.plant("runtime_contract.py", "VALUE = 1\n", "import schedule_domain\nVALUE = 1\n")
        errors = self.errors("carrier", ["runtime_contract.py"])
        self.assertEqual(len(errors), 1)
        self.assertIn("runtime_contract.py", errors[0])
        self.assertIn("schedule_domain", errors[0])
        self.assertIn("'carrier'", errors[0])

    def test_from_import_of_a_foreign_module_fails_closed(self) -> None:
        self.plant("runtime_contract.py", "VALUE = 1\n", "from schedule_domain import ScheduleIssue\n")
        self.assertEqual(len(self.errors("carrier", ["runtime_contract.py"])), 1)

    def test_edge_already_on_the_base_tree_is_grandfathered(self) -> None:
        source = "import schedule_domain\nVALUE = 1\n"
        self.plant("runtime_contract.py", source, source + "EXTRA = 2\n")
        self.assertEqual(self.errors("carrier", ["runtime_contract.py"]), [])

    def test_wave_eight_instance_is_admitted_by_the_dispositioned_carrier_surface(self) -> None:
        self.plant("runtime_contract.py", "VALUE = 1\n", "from issue_contract import SUBJECT_RE\n")
        self.assertEqual(self.errors("carrier", ["runtime_contract.py"]), [])

    def test_stdlib_import_is_not_a_component_edge(self) -> None:
        self.plant("runtime_contract.py", "VALUE = 1\n", "import json\nfrom pathlib import Path\n")
        self.assertEqual(self.errors("carrier", ["runtime_contract.py"]), [])

    def test_file_deleted_by_the_candidate_introduces_no_edge(self) -> None:
        self.plant("runtime_contract.py", "import schedule_domain\n", None)
        self.assertEqual(self.errors("carrier", ["runtime_contract.py"]), [])

    def test_non_python_changed_file_is_skipped(self) -> None:
        self.plant("policy/notes.md", "", "import schedule_domain\n")
        self.assertEqual(self.errors("carrier", ["policy/notes.md"]), [])

    def test_unparsable_candidate_fails_closed_rather_than_reading_zero_edges(self) -> None:
        self.plant("runtime_contract.py", "VALUE = 1\n", "def broken(:\n")
        with self.assertRaisesRegex(noodles.GateError, "cannot parse runtime_contract.py"):
            self.errors("carrier", ["runtime_contract.py"])

    def test_whole_repository_component_admits_every_edge(self) -> None:
        self.plant("runtime_contract.py", "VALUE = 1\n", "import schedule_domain\n")
        self.assertEqual(self.errors("contract", ["runtime_contract.py"]), [])


class ImportTargetReadbackTests(unittest.TestCase):
    def test_dotted_from_import_yields_module_and_member_paths(self) -> None:
        targets = noodles.python_import_targets("from tests.support import CANDIDATE_ROOT\n", "x.py")
        self.assertEqual(targets, {"tests.support", "tests.support.CANDIDATE_ROOT"})

    def test_relative_import_is_not_resolved(self) -> None:
        self.assertEqual(noodles.python_import_targets("from . import sibling\n", "x.py"), set())

    def test_repo_module_target_prefers_a_tree_that_provides_the_module(self) -> None:
        self.assertEqual(noodles.repo_module_target("issue_contract", CANDIDATE_ROOT), "issue_contract.py")
        self.assertEqual(noodles.repo_module_target("tests.support", CANDIDATE_ROOT), "tests/support.py")
        self.assertIsNone(noodles.repo_module_target("json", CANDIDATE_ROOT))

    def test_carrier_surface_declares_the_issue_contract_edge_it_actually_carries(self) -> None:
        """ed3c/noodles#257 disposition: runtime_contract.py imports issue_contract.SUBJECT_RE."""
        components = noodles.component_map(CANDIDATE_ROOT)
        self.assertIn("issue_contract.py", components["carrier"])
        self.assertIn(
            "issue_contract",
            noodles.python_import_targets(
                (CANDIDATE_ROOT / "runtime_contract.py").read_text(encoding="utf-8"), "runtime_contract.py"
            ),
        )


# constraint: ed3c/noodles#306 - the disclosure sentence in AGENTS.md is the ledger, so it is
# constraint: parsed rather than restated here; a fourth hand-synced copy of these four numbers is
# constraint: exactly the staleness the disclosure exists to prevent.
DISCLOSURE_SENTENCE_RE = re.compile(r"carry ((?:`[a-z]+` \d+(?:, )?)+) standing cross-surface edges")
DISCLOSED_PAIR_RE = re.compile(r"`([a-z]+)` (\d+)")


def disclosed_standing_edge_counts(root: Path) -> dict[str, int]:
    """The counts AGENTS.md discloses on `root`, or {} when that tree discloses nothing.

    Absence is its own answer rather than an empty comparison that passes: the caller asserts a
    disclosure exists before comparing, so a candidate that deletes the sentence reds with that as
    its diagnostic instead of silently measuring nothing."""
    text = (root / "AGENTS.md").read_text(encoding="utf-8")
    sentence = DISCLOSURE_SENTENCE_RE.search(text)
    if sentence is None:
        return {}
    return {name: int(count) for name, count in DISCLOSED_PAIR_RE.findall(sentence.group(1))}


def standing_cross_surface_edges(root: Path) -> dict[str, set[str]]:
    """Every `file -> target` import edge that leaves its own component's globs, per component.

    The same resolver `component_import_edge_errors` uses, over the whole tree rather than over one
    diff, which is the difference between the edges a candidate *introduces* and the edges that
    already stand."""
    edges: dict[str, set[str]] = {}
    for name, globs in noodles.component_map(root).items():
        if globs == ["*"]:
            continue
        crossing: set[str] = set()
        for path in sorted(p.relative_to(root).as_posix() for p in root.rglob("*.py") if ".git" not in p.parts):
            if not any(fnmatch.fnmatchcase(path, glob) for glob in globs):
                continue
            source = (root / path).read_text(encoding="utf-8")
            for dotted in sorted(noodles.python_import_targets(source, path)):
                target = noodles.repo_module_target(dotted, root)
                if target and target != path and not any(fnmatch.fnmatchcase(target, glob) for glob in globs):
                    crossing.add(f"{path} -> {target}")
        edges[name] = crossing
    return edges


class GrandfatheredImportDebtTests(unittest.TestCase):
    """ed3c/noodles#276: pre-existing cross-surface edges are grandfathered by
    component_import_edge_errors's own base-diff rule and are unmeasured by any gate. The counts are
    quoted in AGENTS.md and in #276's issue body; this recomputes them against the live tree with
    the gate's own resolver so drift breaks a test instead of only ever breaking a stale sentence
    nobody re-runs. A red here means: fix the drift (declare the coupling or file its disposition),
    or the count genuinely changed - either way, update the AGENTS.md sentence in the same commit.

    ed3c/noodles#306: that instruction was unfollowable while the expected counts were a literal in
    *this* file. `pull_request_target` runs the default branch's copy of this module against the
    candidate's tree, so a candidate that legitimately moved an edge computed new counts, was
    compared against a literal only `main` could hold, and could never merge to update it - the same
    deadlock #285 already cured for the sibling ratchet below. Both halves of the comparison now come
    from the candidate: the measurement from its tree, the disclosure from its AGENTS.md."""

    def test_standing_cross_surface_edge_counts_match_the_agents_md_disclosure(self) -> None:
        counts = {name: len(edges) for name, edges in standing_cross_surface_edges(CANDIDATE_ROOT).items()}
        disclosed = disclosed_standing_edge_counts(CANDIDATE_ROOT)
        self.assertTrue(disclosed, "AGENTS.md discloses no standing cross-surface edge counts to read")
        if counts != disclosed:
            base = standing_cross_surface_edges(ENGINE_ROOT)
            candidate = standing_cross_surface_edges(CANDIDATE_ROOT)
            moved = {
                name: sorted(f"+{edge}" for edge in candidate[name] - base.get(name, set()))
                + sorted(f"-{edge}" for edge in base.get(name, set()) - candidate[name])
                for name in sorted(candidate)
                if counts.get(name) != disclosed.get(name)
            }
            self.fail(f"measured {counts} but AGENTS.md discloses {disclosed}; edges that moved: {moved}")

    def test_a_stale_disclosed_count_is_a_red_rather_than_prose_nobody_reruns(self) -> None:
        """Planted negative for the reader itself: one wrong digit in the AGENTS.md sentence and the
        parse no longer matches the tree it claims to describe."""
        text = (CANDIDATE_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        live = disclosed_standing_edge_counts(CANDIDATE_ROOT)
        self.assertTrue(live)
        stale = DISCLOSURE_SENTENCE_RE.sub(
            lambda match: match.group(0).replace(f"`carrier` {live['carrier']}", f"`carrier` {live['carrier'] + 1}"),
            text,
            count=1,
        )
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "AGENTS.md").write_text(stale, encoding="utf-8")
            self.assertEqual(disclosed_standing_edge_counts(root)["carrier"], live["carrier"] + 1)

    def test_a_tree_with_no_disclosure_sentence_reads_as_absent_not_as_zero(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "AGENTS.md").write_text("no disclosure here\n", encoding="utf-8")
            self.assertEqual(disclosed_standing_edge_counts(root), {})

    def test_an_undeclared_new_cross_surface_edge_moves_the_measured_count(self) -> None:
        """The property #276 disclosed: an added import that leaves its component's globs shows up in
        the measurement, so a candidate carrying one and not disclosing it reds above."""
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "policy").mkdir()
            (root / "policy" / "components.json").write_text(
                json.dumps({"schema_version": 1, "components": {"docs": ["tests/*"], "carrier": ["noodles.py"]}}),
                encoding="utf-8",
            )
            (root / "noodles.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests" / "test_x.py").write_text("import os\n", encoding="utf-8")
            self.assertEqual(standing_cross_surface_edges(root)["docs"], set())
            (root / "tests" / "test_x.py").write_text("import noodles\n", encoding="utf-8")
            self.assertEqual(standing_cross_surface_edges(root)["docs"], {"tests/test_x.py -> noodles.py"})


def mutate_definition(source: str, name: str) -> str:
    """The candidate tree of ed3c/noodles#189: one top-level definition's own bytes change, nothing
    else in the file moves, and the file-level glob still matches every component that lists it."""
    lines = source.splitlines()
    node = next(item for item in ast.parse(source).body if getattr(item, "name", "") == name)
    lines.insert(node.body[0].lineno - 1, "    # planted ed3c/noodles#268 crossing")
    return "\n".join(lines) + "\n"


class ComponentOwnerMapTests(unittest.TestCase):
    """ed3c/noodles#268: the hand-kept map that gives multi-component files a definition-level owner."""

    def setUp(self) -> None:
        self.components = noodles.component_map(CANDIDATE_ROOT)
        self.owners = noodles.component_owner_map(CANDIDATE_ROOT)

    def test_shipped_map_owns_only_files_more_than_one_component_admits(self) -> None:
        for path in self.owners:
            with self.subTest(path=path):
                admitting = [
                    name
                    for name, globs in self.components.items()
                    if any(fnmatch.fnmatchcase(path, glob) for glob in globs)
                ]
                self.assertGreater(len(admitting), 1, f"{path} needs no ownership entry: {admitting}")

    def test_shipped_map_names_real_components_and_real_definitions(self) -> None:
        for path, definitions in self.owners.items():
            present = noodles.top_level_definitions((CANDIDATE_ROOT / path).read_text(encoding="utf-8"), path)
            for name, owning in definitions.items():
                with self.subTest(definition=f"{path}:{name}"):
                    self.assertIn(name, present)
                    self.assertTrue(set(owning) <= set(self.components), owning)

    def test_noodles_py_unowned_definition_count_matches_the_agents_md_disclosure(self) -> None:
        """ed3c/noodles#278: nothing else reds when this count grows, so AGENTS.md's "139 total, 18
        owned, 121 unowned" would otherwise silently go stale. If this breaks because you legitimately
        added or renamed a top-level definition, update the floor here AND the sentence in AGENTS.md
        that quotes the current true count in the same commit. (It already caught this drift twice:
        132→136 from landing-train traffic on main adding findings-register functions, then 136→139
        from ed3c/noodles#120's own declared_markers/requirement_definition_source/
        system_requirement_ids - see GrandfatheredImportDebtTests for the same pattern.)

        ed3c/noodles#285: a strict `==` here deadlocks any candidate that legitimately adds a
        top-level definition - trusted-preview always runs *this* file (main's copy) against the
        candidate's data, so the candidate can never make its own trusted-preview pass no matter what
        it changes, and never merges to update the literal. A monotonic floor still catches the
        regression this ratchet exists for (an accidental deletion shrinking the count) while
        admitting legitimate growth. ed3c/noodles#278 owns building the fully self-computed version of
        this ratchet (and the separate `contract` glob "*" bypass); this floor is the narrower, urgent
        unblock only."""
        source = (CANDIDATE_ROOT / "noodles.py").read_text(encoding="utf-8")
        defs = noodles.top_level_definitions(source, "noodles.py")
        owned = self.owners.get("noodles.py", {})
        self.assertGreaterEqual(len(defs), 139)
        self.assertEqual(len(owned), 18)

    def test_absent_map_is_inert_rather_than_red(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(noodles.component_owner_map(Path(temp)), {})

    def test_wrong_schema_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / noodles.COMPONENT_OWNER_MAP_PATH
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"schema_version": 2, "owners": {"a.py": {"f": ["docs"]}}}), encoding="utf-8")
            with self.assertRaisesRegex(noodles.GateError, "schema_version 1"):
                noodles.component_owner_map(Path(temp))

    def test_empty_owner_list_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / noodles.COMPONENT_OWNER_MAP_PATH
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"schema_version": 1, "owners": {"a.py": {"f": []}}}), encoding="utf-8")
            with self.assertRaisesRegex(noodles.GateError, "a.py:f must list at least one"):
                noodles.component_owner_map(Path(temp))


class ComponentOwnerGateTests(unittest.TestCase):
    """The ed3c/noodles#189 crossing, replayed against the real map and the real noodles.py."""

    def setUp(self) -> None:
        self.components = noodles.component_map(CANDIDATE_ROOT)
        self.owners = noodles.component_owner_map(CANDIDATE_ROOT)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.candidate = Path(temp.name)
        self.source = (CANDIDATE_ROOT / "noodles.py").read_text(encoding="utf-8")

    def plant(self, definition: str) -> None:
        (self.candidate / "noodles.py").write_text(mutate_definition(self.source, definition), encoding="utf-8")

    def errors(self, component: str, changed: list[str] | None = None) -> list[str]:
        return noodles.component_owner_errors(
            component, self.components, changed or ["noodles.py"], self.owners, CANDIDATE_ROOT, self.candidate
        )

    def test_planted_negative_verify_atom_touching_schedule_dispatch_fails_closed(self) -> None:
        self.plant("schedule_publish")
        errors = self.errors("verify")
        self.assertEqual(len(errors), 1)
        self.assertIn("noodles.py:schedule_publish", errors[0])
        self.assertIn("owned by schedule", errors[0])
        self.assertIn("declares 'verify'", errors[0])

    def test_positive_control_same_change_under_the_owning_component_passes(self) -> None:
        self.plant("schedule_publish")
        self.assertEqual(self.errors("schedule"), [])

    def test_positive_control_verify_owned_definition_under_a_verify_atom_passes(self) -> None:
        self.plant("component_surface_errors")
        self.assertEqual(self.errors("verify"), [])

    def test_unowned_definition_is_not_judged_and_owned_neighbours_stay_silent(self) -> None:
        self.plant("verify_pull_request")
        for component in ("verify", "carrier", "schedule"):
            with self.subTest(component=component):
                self.assertEqual(self.errors(component), [])

    def test_whole_repository_component_admits_every_definition(self) -> None:
        self.plant("schedule_publish")
        self.assertEqual(self.errors("contract"), [])

    def test_file_without_an_ownership_entry_is_not_judged(self) -> None:
        self.plant("schedule_publish")
        self.assertEqual(self.errors("verify", ["feature_contract.py"]), [])

    def test_file_absent_from_the_candidate_is_a_file_level_event_not_a_crossing(self) -> None:
        self.assertEqual(self.errors("verify"), [])

    def test_deleting_an_owned_definition_is_a_crossing(self) -> None:
        node = next(item for item in ast.parse(self.source).body if getattr(item, "name", "") == "schedule_publish")
        truncated = "\n".join(self.source.splitlines()[: node.lineno - 1]) + "\n"
        (self.candidate / "noodles.py").write_text(truncated, encoding="utf-8")
        errors = self.errors("verify")
        self.assertTrue(any("noodles.py:schedule_publish" in error for error in errors), errors)


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

    def run_verify(
        self, body: str, changed_files: list[str], candidate_files: dict[str, str] | None = None
    ) -> tuple[Path, object]:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        for relative, text in (candidate_files or {}).items():
            (base / relative).write_text(text, encoding="utf-8")
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

    def test_new_import_inside_the_declared_surface_receives_an_import_edge_receipt(self) -> None:
        body = issue_body(component="verify", state="awaiting_land")
        _, receipt = self.run_verify(
            body, ["feature_contract.py"], {"feature_contract.py": "import github_protection\n"}
        )
        self.assertIn("component-import-edges", receipt["gates"])

    def test_new_import_outside_the_declared_surface_fails_closed_naming_file_import_component(self) -> None:
        body = issue_body(component="verify", state="awaiting_land")
        with self.assertRaises(noodles.GateError) as raised:
            self.run_verify(
                body, ["feature_contract.py"], {"feature_contract.py": "import schedule_domain\n"}
            )
        diagnostic = str(raised.exception)
        self.assertIn("component-import-edge gate failed", diagnostic)
        self.assertIn("feature_contract.py", diagnostic)
        self.assertIn("schedule_domain", diagnostic)
        self.assertIn("'verify'", diagnostic)

    def test_same_file_crossing_fails_closed_naming_file_definition_and_components(self) -> None:
        body = issue_body(component="verify", state="awaiting_land")
        planted = mutate_definition((CANDIDATE_ROOT / "noodles.py").read_text(encoding="utf-8"), "schedule_publish")
        with self.assertRaises(noodles.GateError) as raised:
            self.run_verify(body, ["noodles.py"], {"noodles.py": planted})
        diagnostic = str(raised.exception)
        self.assertIn("component-ownership gate failed", diagnostic)
        self.assertIn("noodles.py:schedule_publish", diagnostic)
        self.assertIn("owned by schedule", diagnostic)
        self.assertIn("declares 'verify'", diagnostic)

    def test_same_file_change_under_the_owning_component_receives_an_ownership_receipt(self) -> None:
        body = issue_body(component="schedule", state="awaiting_land")
        planted = mutate_definition((CANDIDATE_ROOT / "noodles.py").read_text(encoding="utf-8"), "schedule_publish")
        _, receipt = self.run_verify(body, ["noodles.py"], {"noodles.py": planted})
        self.assertIn("component-ownership", receipt["gates"])


if __name__ == "__main__":
    unittest.main()

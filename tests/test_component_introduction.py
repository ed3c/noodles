"""Component-introduction gate: a candidate that declares a NEW pinned dependency or a new
top-level module must be driven by an Issue answering both entropy gate questions in a
machine-detectable section. Planted controls prove the two directions that matter: a dependency
addition without the section fails closed naming both unanswered questions, and a version bump of
an already-pinned entry passes without any section at all."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import noodles
from tests.support import CANDIDATE_ROOT

HEAD_SHA = "c" * 40
SUBJECT = "ed3c/noodles#900185"

ANSWERED_SECTION = (
    "## Component introduction\n\n"
    "which invalid state does this make impossible?\n"
    "A candidate can no longer vendor an unpinned helper library into the Golden Path.\n\n"
    "why can't strengthening the nearest existing contract close the same failure?\n"
    "The provider lock validates the shape of entries that exist; it cannot object to a new one.\n"
)


# constraint: ed3c/noodles#278 - these fixtures declared `contract` for convenience, which is exactly
# constraint: the whole-repository bypass contract_component_bypass_errors now refuses: their single
# constraint: changed file (policy/providers.lock.json) already fits every ordinary component. The
# constraint: introduction gate under test is unrelated to that choice, so they declare an ordinary one.
def issue_body(*, section: str = "", component: str = "carrier") -> str:
    return (
        "<!-- noodles-role: repository-mutating-atom -->\n"
        "<!-- noodles-target: ed3c/noodles -->\n"
        f"<!-- noodles-subject: {SUBJECT} -->\n"
        "<!-- noodles-state: awaiting_land -->\n"
        f"<!-- noodles-component: {component} -->\n"
        "<!-- noodles-depends-on: none -->\n\n"
        "## Goal\n\nBind component introduction to the two gate questions.\n\n"
        f"{section}\n"
        "## Non-claims\n\n- The gate does not score the answers.\n"
    )


def lock_tree(temp: Path, locks: dict[str, object], modules: tuple[str, ...] = ()) -> Path:
    root = temp
    (root / "policy").mkdir(parents=True, exist_ok=True)
    for name, payload in locks.items():
        (root / "policy" / name).write_text(json.dumps(payload), encoding="utf-8")
    for module in modules:
        (root / module).write_text("", encoding="utf-8")
    return root


BASE_PROVIDERS = {
    "schema_version": 1,
    "providers": [{"name": "cursor-pstack", "commit": "a" * 40, "enabled": True}],
}


class PinnedEntryIdentityTests(unittest.TestCase):
    def test_repository_locks_expose_every_pinned_unit_by_container_path(self) -> None:
        entries = noodles.pinned_entries(CANDIDATE_ROOT)
        self.assertIn("providers.lock.json.providers[cursor-pstack]", entries)
        self.assertIn("parser.lock.json.parser.grammar", entries)
        self.assertIn("retrieval.lock.json.retrieval.embedder", entries)
        self.assertIn("runtime.lock.json.runtime.platforms.darwin_arm64", entries)

    def test_tree_without_policy_locks_has_no_pinned_units(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(noodles.pinned_entries(Path(temp)), set())


class IntroductionDetectorTests(unittest.TestCase):
    def build(self, locks: dict[str, object], modules: tuple[str, ...] = ()) -> Path:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        return lock_tree(Path(temp.name), locks, modules)

    def test_identical_trees_introduce_nothing(self) -> None:
        base = self.build({"providers.lock.json": BASE_PROVIDERS})
        candidate = self.build({"providers.lock.json": BASE_PROVIDERS})
        self.assertEqual(noodles.introduced_components(base, candidate), [])

    def test_planted_positive_control_version_bump_of_existing_entry_is_not_an_introduction(self) -> None:
        base = self.build(
            {"parser.lock.json": {"schema_version": 1, "parser": {"library": {"version": "0.26.0", "commit": "a" * 40}}}}
        )
        candidate = self.build(
            {"parser.lock.json": {"schema_version": 1, "parser": {"library": {"version": "0.27.1", "commit": "b" * 40}}}}
        )
        self.assertEqual(noodles.introduced_components(base, candidate), [])

    def test_planted_negative_control_new_lock_entry_is_an_introduction(self) -> None:
        base = self.build({"providers.lock.json": BASE_PROVIDERS})
        candidate = self.build(
            {
                "providers.lock.json": {
                    "schema_version": 1,
                    "providers": BASE_PROVIDERS["providers"] + [{"name": "act", "commit": "b" * 40, "enabled": True}],
                }
            }
        )
        self.assertEqual(
            noodles.introduced_components(base, candidate),
            ["pinned lock entry providers.lock.json.providers[act]"],
        )

    def test_new_lock_file_is_an_introduction(self) -> None:
        base = self.build({"providers.lock.json": BASE_PROVIDERS})
        candidate = self.build(
            {
                "providers.lock.json": BASE_PROVIDERS,
                "gittown.lock.json": {"schema_version": 1, "gittown": {"version": "16.0.0"}},
            }
        )
        self.assertEqual(
            noodles.introduced_components(base, candidate),
            ["pinned lock entry gittown.lock.json.gittown"],
        )

    def test_new_top_level_module_is_an_introduction(self) -> None:
        base = self.build({"providers.lock.json": BASE_PROVIDERS}, modules=("noodles.py",))
        candidate = self.build({"providers.lock.json": BASE_PROVIDERS}, modules=("noodles.py", "execution_slot.py"))
        self.assertEqual(noodles.introduced_components(base, candidate), ["top-level module execution_slot.py"])

    def test_deleting_a_component_is_never_an_introduction(self) -> None:
        base = self.build({"providers.lock.json": BASE_PROVIDERS}, modules=("noodles.py", "legacy.py"))
        candidate = self.build({"providers.lock.json": {"schema_version": 1, "providers": []}}, modules=("noodles.py",))
        self.assertEqual(noodles.introduced_components(base, candidate), [])

    def test_repository_head_introduces_nothing_against_itself(self) -> None:
        self.assertEqual(noodles.introduced_components(CANDIDATE_ROOT, CANDIDATE_ROOT), [])


class GateQuestionSectionTests(unittest.TestCase):
    def test_missing_section_leaves_both_questions_unanswered(self) -> None:
        self.assertEqual(
            noodles.component_introduction_missing_answers(issue_body()),
            list(noodles.COMPONENT_INTRODUCTION_QUESTIONS),
        )

    def test_answered_section_leaves_nothing_unanswered(self) -> None:
        self.assertEqual(noodles.component_introduction_missing_answers(issue_body(section=ANSWERED_SECTION)), [])

    def test_question_without_an_answer_below_it_stays_unanswered(self) -> None:
        section = ANSWERED_SECTION.replace(
            "The provider lock validates the shape of entries that exist; it cannot object to a new one.\n", ""
        )
        self.assertEqual(
            noodles.component_introduction_missing_answers(issue_body(section=section)),
            [noodles.COMPONENT_INTRODUCTION_QUESTIONS[1]],
        )

    def test_questions_quoted_outside_the_section_do_not_count(self) -> None:
        body = issue_body().replace("## Goal\n", "## Goal\n\n" + "\n".join(noodles.COMPONENT_INTRODUCTION_QUESTIONS) + "\nyes.\n")
        self.assertEqual(
            noodles.component_introduction_missing_answers(body),
            list(noodles.COMPONENT_INTRODUCTION_QUESTIONS),
        )

    def test_non_introducing_candidate_never_needs_the_section(self) -> None:
        self.assertEqual(noodles.component_introduction_errors([], issue_body()), [])

    def test_diagnostic_names_the_introduction_and_both_unanswered_questions(self) -> None:
        errors = noodles.component_introduction_errors(
            ["pinned lock entry providers.lock.json.providers[act]"], issue_body()
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("providers.lock.json.providers[act]", errors[0])
        for question in noodles.COMPONENT_INTRODUCTION_QUESTIONS:
            self.assertIn(question, errors[0])


class VerifyPullRequestIntroductionGateTests(unittest.TestCase):
    """The trusted verify path compares the candidate tree with the trusted default-branch tree."""

    def run_verify(self, body: str, candidate_root: Path) -> dict[str, object]:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        event_path = base / "event.json"
        event_path.write_text(
            json.dumps(
                {
                    "pull_request": {
                        "number": 11,
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

        def fake_git(root: Path, *args: str, check: bool = True) -> str:
            if args == ("rev-parse", "HEAD"):
                return HEAD_SHA
            if args == ("rev-parse", "HEAD^{tree}"):
                return "d" * 40
            raise AssertionError(f"unexpected git call: {args}")

        with mock.patch.object(noodles, "issue_read", return_value={"state": "open", "body": body}), \
                mock.patch.object(noodles, "merge_base_changed_files", return_value=["policy/providers.lock.json"]), \
                mock.patch.object(noodles, "verify_repository", return_value={"ok": True, "errors": [], "metrics": {}}), \
                mock.patch.object(noodles, "git", side_effect=fake_git):
            return noodles.verify_pull_request(CANDIDATE_ROOT, event_path, candidate_root, base / "receipt.json")

    def dependency_adding_candidate(self) -> Path:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        candidate = Path(temp.name) / "candidate"
        shutil.copytree(CANDIDATE_ROOT / "policy", candidate / "policy")
        lock_path = candidate / "policy/providers.lock.json"
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
        payload["providers"].append({"name": "act", "commit": "e" * 40, "enabled": False})
        lock_path.write_text(json.dumps(payload), encoding="utf-8")
        return candidate

    def test_dependency_adding_candidate_without_the_section_fails_closed(self) -> None:
        with self.assertRaises(noodles.GateError) as raised:
            self.run_verify(issue_body(), self.dependency_adding_candidate())
        diagnostic = str(raised.exception)
        self.assertIn("component-introduction gate failed", diagnostic)
        self.assertIn("providers.lock.json.providers[act]", diagnostic)
        for question in noodles.COMPONENT_INTRODUCTION_QUESTIONS:
            self.assertIn(question, diagnostic)

    def test_same_candidate_with_the_section_passes_and_binds_the_introduction_to_the_receipt(self) -> None:
        receipt = self.run_verify(issue_body(section=ANSWERED_SECTION), self.dependency_adding_candidate())
        self.assertEqual(receipt["introduces"], ["pinned lock entry providers.lock.json.providers[act]"])
        self.assertIn("component-introduction", receipt["gates"])

    def test_version_bumping_candidate_passes_without_the_section(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        candidate = Path(temp.name) / "candidate"
        shutil.copytree(CANDIDATE_ROOT / "policy", candidate / "policy")
        lock_path = candidate / "policy/parser.lock.json"
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
        payload["parser"]["library"]["version"] = "0.99.0"
        payload["parser"]["library"]["commit"] = "f" * 40
        lock_path.write_text(json.dumps(payload), encoding="utf-8")
        receipt = self.run_verify(issue_body(), candidate)
        self.assertEqual(receipt["introduces"], [])
        self.assertIn("component-introduction", receipt["gates"])


class SpecificationBindingTests(unittest.TestCase):
    def test_specification_owns_the_two_question_requirement(self) -> None:
        spec = (CANDIDATE_ROOT / "contracts/system-v1.md").read_text(encoding="utf-8")
        self.assertEqual(spec.count("### VERIFICATION.COMPONENT_INTRODUCTION.001"), 1)
        for phrase in noodles.COMPONENT_INTRODUCTION_QUESTIONS + (
            "## Component introduction",
            "noodles.introduced_components",
            "version bump of an existing entry is out of scope",
        ):
            self.assertIn(phrase, spec)

    def test_local_verify_reports_the_same_classification(self) -> None:
        result = noodles.verify_repository(CANDIDATE_ROOT, CANDIDATE_ROOT)
        self.assertEqual(result["introduces"], [])


if __name__ == "__main__":
    unittest.main()

"""ed3c/noodles#315 - the trusted suite may not memorize the candidate's CURRENT state.

`pull_request_target` runs the DEFAULT BRANCH's copy of every module under `tests/` against the
candidate tree as data (`.github/workflows/verify.yml`, `PYTHONPATH=.trusted` with
`NOODLES_CANDIDATE_ROOT=.candidate`). A trusted assertion that pins a strict literal of a value the
candidate legally owns is therefore not merely wrong when it drifts - it deadlocks: the candidate
moves the value, `main`'s copy of the test still holds the old literal, the candidate cannot edit
trusted code from inside its own PR, and no rerun and no rebase can turn that red green. That shape
has now been paid for four times (ed3c/noodles#285 unowned-definition count, #306 cross-surface edge
counts, #304/#301 the provider entry list, #311 the workflow declaration), each time by an
out-of-band trusted-side atom no refusal named.

This module is both halves of the class cure the issue asks for, sharing ONE detection rule so the
sweep and the guard cannot disagree about what the pattern is:

* `sweep(root)` enumerates the instances,
* `policy/trusted-literals.json` carries each instance's committed disposition,
* `ledger_errors(root)` reds on an instance with no disposition, a disposition with no instance,
  and a disposition with no written reason.

Both halves read the CANDIDATE's tree: the findings from its `tests/`, the dispositions from its
`policy/`. That is what keeps the guard itself out of the deadlock it exists to refuse - a candidate
that legitimately adds an invariant-shaped literal adds its row in the same commit.

Ceiling, stated rather than implied: the rule flags a strict-equal assertion whose measured side is
reachable from the `CANDIDATE_ROOT` anchor and whose other side is a literal carrying content. It
does not flag a literal that is the empty or false value of its type (`[]`, `{}`, `''`, `0`,
`False`, `None`), because "assert nothing came back" is an invariant a candidate never legally
moves; it cannot see a value laundered through a module this rule does not parse; and it judges
syntax, never meaning - which is exactly why every finding needs a human-written disposition rather
than an automatic verdict.
"""
from __future__ import annotations

import ast
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from tests.support import CANDIDATE_ROOT, runtime_lock_shape_errors

LEDGER_PATH = "policy/trusted-literals.json"
FINDINGS_REGISTER_PATH = "docs/findings/register.json"
TRUSTED_SUITE_GLOB = "tests/**/*.py"
ANCHOR = "CANDIDATE_ROOT"
DIAGNOSTIC = (
    "trusted test pins a literal of candidate-current state; convert it to a candidate-owned "
    "disclosure the trusted side judges for shape/derivation/consistency, or record its disposition "
    f"in {LEDGER_PATH}"
)
STRICT_EQUAL = frozenset(
    {
        "assertEqual",
        "assertDictEqual",
        "assertListEqual",
        "assertSetEqual",
        "assertTupleEqual",
        "assertSequenceEqual",
        "assertCountEqual",
    }
)
RECEIVERS = frozenset({"self", "cls"})
DISPOSITIONS = frozenset({"invariant", "deferred"})
OWNER_PREFIXES = ("ed3c/noodles#", "finding-")


def _handles(node: ast.AST) -> set[str]:
    """Every name this expression reads, by bare identifier and by attribute tail.

    `self.owners` contributes `owners` so a value a `setUp` derives from the anchor stays tracked in
    the test method that asserts on it - the exact laundering that hid the ed3c/noodles#285 sibling
    (`assertEqual(len(owned), 18)`, register finding 7) from a function-local scan."""
    found: set[str] = set()
    for item in ast.walk(node):
        if isinstance(item, ast.Name):
            found.add(item.id)
        elif isinstance(item, ast.Attribute):
            found.add(item.attr)
    return found - RECEIVERS


def _bindings(scope: ast.AST) -> list[tuple[ast.expr, list[ast.expr]]]:
    """(value, targets) for every binding form that can carry taint out of an expression."""
    out: list[tuple[ast.expr, list[ast.expr]]] = []
    for node in ast.walk(scope):
        if isinstance(node, ast.Assign):
            out.append((node.value, list(node.targets)))
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)) and node.value is not None:
            out.append((node.value, [node.target]))
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            out.append((node.iter, [node.target]))
        elif isinstance(node, ast.comprehension):
            out.append((node.iter, [node.target]))
        elif isinstance(node, ast.withitem) and node.optional_vars is not None:
            out.append((node.context_expr, [node.optional_vars]))
    return out


def _tree_handles(scope: ast.AST) -> set[str]:
    """Handles this scope uses as a filesystem root (`handle / "something"`).

    A name that denotes a TREE is not the candidate's current state, even when the candidate tree is
    what it was copied from: `handoff_fixture(CANDIDATE_ROOT, ...)` and `copy_tracked` hand back an
    independent fixture, and an assertion about how production behaves on a fixture is not a
    memorized value. Without this cut the anchor's closure reaches every fixture in the suite and the
    rule flags a hundred assertions nobody would ever read - a guard nobody reads is prose.

    Ceiling: this is the path-join shape, so a numeric `a / b` would also stop taint at `a`. That is
    fail-open, and no instance in the swept suite takes that shape."""
    found: set[str] = set()
    for node in ast.walk(scope):
        if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)):
            continue
        if isinstance(node.right, ast.Constant) and not isinstance(node.right.value, str):
            continue
        found |= _handles(node.left)
    return found


def _spread(scope: ast.AST, tainted: set[str]) -> set[str]:
    """Close `tainted` over the bindings in `scope`; order-independent, so a fixed point is reached
    whether the anchor is read before or after the name that carries it."""
    bindings = _bindings(scope)
    trees = _tree_handles(scope) - {ANCHOR}
    while True:
        grown = set(tainted)
        for value, targets in bindings:
            if _handles(value) & grown:
                for target in targets:
                    grown |= _handles(target)
        grown -= trees
        if grown == tainted:
            return tainted
        tainted = grown


def _constants(tree: ast.Module) -> dict[str, ast.expr]:
    """Every `NAME = <expression>` binding at module or class scope, keyed by its bare name.

    Class attributes are keyed the same way as module names because the assertion reads them as
    `self.NAME`; the pre-cure ed3c/noodles#306 literal lived in exactly that position."""
    found: dict[str, ast.expr] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            pairs = [(target, node.value) for target in node.targets]
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            pairs = [(node.target, node.value)]
        else:
            continue
        for target, value in pairs:
            if isinstance(target, ast.Name):
                found[target.id] = value
    return found


def _content_literal(node: ast.expr, constants: dict[str, ast.expr]) -> str | None:
    """The literal `node` denotes - directly or through one constant binding - when it carries
    content, else None. The empty or false value of a type is not a memorized current state."""
    resolved = node
    if isinstance(node, ast.Name) and node.id in constants:
        resolved = constants[node.id]
    elif isinstance(node, ast.Attribute) and node.attr in constants:
        resolved = constants[node.attr]
    try:
        value = ast.literal_eval(resolved)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return None
    if value is None or value is False or value == 0 or (not isinstance(value, (int, float)) and not value):
        return None
    return ast.unparse(resolved)


def _scopes(tree: ast.Module) -> list[tuple[str, ast.AST, set[str]]]:
    """(qualified name, scope node, seed taint) for every function the trusted suite defines.

    A class seeds its methods with the handles it binds DIRECTLY from the anchor - one hop, not the
    class-wide closure - which is how `setUp` state reaches the method that asserts on it. One hop is
    the deliberate line: the closure over a whole class walks out of the candidate tree and into
    every temporary fixture copied from it, and a rule that flags assertions about fixture behaviour
    stops being a rule anyone reads."""
    out: list[tuple[str, ast.AST, set[str]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        seed: set[str] = set()
        for value, targets in _bindings(node):
            if ANCHOR in _handles(value):
                for target in targets:
                    seed |= _handles(target)
        seed -= {ANCHOR} | _tree_handles(node)
        for child in ast.walk(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.append((f"{node.name}.{child.name}", child, seed))
    claimed = {scope for _, scope, _ in out}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node not in claimed:
            out.append((node.name, node, set()))
    return out


def current_state_literals(source: str, relative: str) -> list[dict[str, Any]]:
    """The detection rule itself, over one trusted-suite module's bytes."""
    tree = ast.parse(source, relative)
    constants = _constants(tree)
    findings: list[dict[str, Any]] = []
    for qualified, scope, seed in _scopes(tree):
        tainted = _spread(scope, {ANCHOR} | seed)
        for node in ast.walk(scope):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in STRICT_EQUAL):
                continue
            args = [argument for argument in node.args if not isinstance(argument, ast.Starred)][:2]
            if len(args) != 2:
                continue
            for measured, other in ((0, 1), (1, 0)):
                if not _handles(args[measured]) & tainted or _handles(args[other]) & tainted:
                    continue
                literal = _content_literal(args[other], constants)
                if literal is None:
                    continue
                findings.append(
                    {
                        "path": relative,
                        "test": qualified,
                        "literal": literal,
                        "line": node.lineno,
                        "measured": ast.unparse(args[measured]),
                    }
                )
                break
    return findings


def sweep(root: Path) -> list[dict[str, Any]]:
    """Every instance of the pattern in `root`'s trusted suite, sorted for a stable readback."""
    findings: list[dict[str, Any]] = []
    for path in sorted(root.glob(TRUSTED_SUITE_GLOB)):
        relative = path.relative_to(root).as_posix()
        findings.extend(current_state_literals(path.read_text(encoding="utf-8"), relative))
    return sorted(findings, key=lambda item: (item["path"], item["test"], item["literal"]))


def _key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (str(item.get("path")), str(item.get("test")), str(item.get("literal")))


def _register_ids(root: Path) -> set[str]:
    """The findings-register ids this tree carries, so a deferred row names a destination that
    exists rather than a plausible-looking string. A subject owner (`ed3c/noodles#N`) is not checked
    here: resolving it needs the provider, and a local gate that silently passes when the network is
    absent would be worse than one that does not claim to check."""
    try:
        payload = json.loads((root / FINDINGS_REGISTER_PATH).read_text(encoding="utf-8"))
        return {f"finding-{entry['id']}" for entry in payload["entries"]}
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return set()


def ledger_errors(root: Path) -> list[str]:
    """Judge the candidate's committed dispositions against the candidate's own trusted suite.

    Three refusals, each naming what a reader must do: an instance with no disposition, a
    disposition naming no instance (the exemption rotted past the code it excused), and a
    disposition carrying no written reason."""
    path = root / LEDGER_PATH
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{LEDGER_PATH} is unreadable: {exc}"]
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "converted", "dispositions"} or payload["schema_version"] != 1:
        return [f"{LEDGER_PATH} must contain exactly schema_version 1, a converted array and a dispositions array"]
    dispositions = payload["dispositions"]
    converted = payload["converted"]
    if not isinstance(dispositions, list) or not isinstance(converted, list):
        return [f"{LEDGER_PATH} converted and dispositions must both be arrays"]
    errors: list[str] = []
    findings = sweep(root)
    register_ids = _register_ids(root)
    by_key = {_key(item): item for item in findings}
    recorded: set[tuple[str, str, str]] = set()
    for index, row in enumerate(dispositions, start=1):
        label = f"{LEDGER_PATH} disposition {index}"
        if not isinstance(row, dict) or set(row) < {"path", "test", "literal", "disposition", "reason"}:
            errors.append(f"{label} needs path, test, literal, disposition and reason")
            continue
        if row["disposition"] not in DISPOSITIONS:
            errors.append(f"{label} disposition {row['disposition']!r} is not one of {sorted(DISPOSITIONS)}")
        if not isinstance(row["reason"], str) or not row["reason"].strip():
            errors.append(f"{label} carries no written reason for {row['path']}::{row['test']}")
        if row["disposition"] == "deferred":
            owner = str(row.get("owner", ""))
            if not owner.startswith(OWNER_PREFIXES):
                errors.append(f"{label} is deferred but names no owner among {OWNER_PREFIXES}")
            elif owner.startswith("finding-") and owner not in register_ids:
                errors.append(f"{label} defers to {owner}, which {FINDINGS_REGISTER_PATH} does not carry")
        key = _key(row)
        if key in recorded:
            errors.append(f"{label} repeats {key[0]}::{key[1]} literal {key[2]}")
        recorded.add(key)
        if key not in by_key:
            errors.append(f"{label} names no live instance: {key[0]}::{key[1]} no longer asserts {key[2]}; delete the stale exemption")
    for key in sorted(set(by_key) - recorded):
        errors.append(f"{key[0]}:{by_key[key]['line']} {key[1]} asserts {key[2]} against {by_key[key]['measured']}: {DIAGNOSTIC}")
    for index, row in enumerate(converted, start=1):
        label = f"{LEDGER_PATH} converted {index}"
        if not isinstance(row, dict) or set(row) < {"path", "test", "was", "now"}:
            errors.append(f"{label} needs path, test, was and now")
            continue
        if _key({"path": row["path"], "test": row["test"], "literal": row["was"]}) in by_key:
            errors.append(f"{label} records {row['path']}::{row['test']} as converted but the literal {row['was']} is back")
    return errors


class TrustedLiteralSweepTests(unittest.TestCase):
    """The sweep half: every live instance carries a committed disposition, and no disposition
    outlives the assertion it excuses."""

    def test_the_committed_sweep_disposes_of_every_instance_in_the_trusted_suite(self) -> None:
        self.assertEqual(ledger_errors(CANDIDATE_ROOT), [])

    def test_the_sweep_finds_the_instances_it_dispositions(self) -> None:
        """Positive control for the reader: an empty finding set would make the ledger check pass
        vacuously, so the sweep must actually see the trusted suite it claims to have swept."""
        findings = sweep(CANDIDATE_ROOT)
        self.assertTrue(findings, "the sweep found nothing at all, which no tree with tests produces")
        self.assertTrue(all(item["path"].startswith("tests/") for item in findings))


class TrustedLiteralGuardTests(unittest.TestCase):
    """The guard half, on fixture trees: a NEW current-state literal reds, an invariant-shaped
    assertion does not."""

    def fixture(self, module: str, ledger: dict[str, Any]) -> Path:
        temp = tempfile.TemporaryDirectory(prefix="noodles-trusted-literal-", ignore_cleanup_errors=True)
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "tests").mkdir()
        (root / "tests" / "test_planted.py").write_text(module, encoding="utf-8")
        (root / "policy").mkdir()
        (root / LEDGER_PATH).write_text(json.dumps(ledger) + "\n", encoding="utf-8")
        (root / "docs" / "findings").mkdir(parents=True)
        (root / FINDINGS_REGISTER_PATH).write_text(json.dumps({"schema_version": 1, "entries": [{"id": 9}]}) + "\n", encoding="utf-8")
        return root

    def empty_ledger(self) -> dict[str, Any]:
        return {"schema_version": 1, "converted": [], "dispositions": []}

    def test_planted_control_a_new_current_state_literal_reds_naming_the_pattern(self) -> None:
        root = self.fixture(
            "from tests.support import CANDIDATE_ROOT\n"
            "class PlantedTests:\n"
            "    def test_count(self):\n"
            "        owners = load(CANDIDATE_ROOT / 'policy/component-owners.json')\n"
            "        self.assertEqual(len(owners), 18)\n",
            self.empty_ledger(),
        )
        errors = ledger_errors(root)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("PlantedTests.test_count", errors[0])
        self.assertIn("18", errors[0])
        self.assertIn("literal of candidate-current state", errors[0])

    def test_planted_control_the_literal_reached_through_setup_state_is_still_caught(self) -> None:
        """The laundering that hid register finding 7's instance from a function-local scan."""
        root = self.fixture(
            "from tests.support import CANDIDATE_ROOT\n"
            "class PlantedTests:\n"
            "    def setUp(self):\n"
            "        self.owners = load(CANDIDATE_ROOT / 'policy/component-owners.json')\n"
            "    def test_count(self):\n"
            "        self.assertEqual(len(self.owners), 18)\n",
            self.empty_ledger(),
        )
        self.assertEqual(len(ledger_errors(root)), 1)

    def test_planted_control_the_literal_hidden_in_a_class_attribute_is_still_caught(self) -> None:
        """The pre-cure ed3c/noodles#306 shape: the number lived in a class attribute, not inline."""
        root = self.fixture(
            "from tests.support import CANDIDATE_ROOT\n"
            "class PlantedTests:\n"
            "    DISCLOSED = {'carrier': 38, 'docs': 84}\n"
            "    def test_counts(self):\n"
            "        counts = measure(CANDIDATE_ROOT)\n"
            "        self.assertEqual(counts, self.DISCLOSED)\n",
            self.empty_ledger(),
        )
        self.assertEqual(len(ledger_errors(root)), 1)

    def test_planted_negative_control_invariant_shaped_assertions_pass_untouched(self) -> None:
        """Bounds, absence, and consistency between two candidate-disclosed values are exactly what
        trusted code is for, so none of them may be flagged.

        A size literal (`assertEqual(len(digest), 64)`) is deliberately NOT in this control: the rule
        does flag it, because syntax cannot tell a universal size from a memorized one, and it earns
        a written `invariant` row instead. Stating that here keeps the control honest about what it
        proves."""
        root = self.fixture(
            "from tests.support import CANDIDATE_ROOT\n"
            "class InvariantTests:\n"
            "    def test_shapes(self):\n"
            "        report = measure(CANDIDATE_ROOT)\n"
            "        self.assertEqual(errors_of(CANDIDATE_ROOT), [])\n"
            "        self.assertGreaterEqual(report['count'], 1)\n"
            "        self.assertEqual(report['count'], disclosed(CANDIDATE_ROOT))\n"
            "        self.assertEqual(sorted(report['names']), sorted(report['names']))\n",
            self.empty_ledger(),
        )
        self.assertEqual(sweep(root), [])
        self.assertEqual(ledger_errors(root), [])

    def test_planted_negative_control_a_tree_the_anchor_never_reaches_is_never_scanned(self) -> None:
        """A trusted module that does not read the candidate at all cannot pin candidate state, and
        the literals it does hold - fixture bytes, diagnostic strings - stay untouched."""
        root = self.fixture(
            "class FixtureTests:\n"
            "    def test_bytes(self):\n"
            "        self.assertEqual(parse('a: 1'), {'a': 1})\n"
            "        self.assertEqual(diagnostic(), 'custody_unadmitted')\n",
            self.empty_ledger(),
        )
        self.assertEqual(sweep(root), [])

    def test_a_stale_exemption_reds_rather_than_outliving_the_code_it_excused(self) -> None:
        ledger = self.empty_ledger()
        ledger["dispositions"] = [
            {"path": "tests/test_planted.py", "test": "GoneTests.test_gone", "literal": "18", "disposition": "invariant", "reason": "why"}
        ]
        root = self.fixture("class OtherTests:\n    pass\n", ledger)
        errors = ledger_errors(root)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("delete the stale exemption", errors[0])

    def test_an_exemption_without_a_written_reason_reds(self) -> None:
        module = (
            "from tests.support import CANDIDATE_ROOT\n"
            "class PlantedTests:\n"
            "    def test_count(self):\n"
            "        self.assertEqual(len(load(CANDIDATE_ROOT)), 18)\n"
        )
        ledger = self.empty_ledger()
        ledger["dispositions"] = [
            {"path": "tests/test_planted.py", "test": "PlantedTests.test_count", "literal": "18", "disposition": "invariant", "reason": "  "}
        ]
        root = self.fixture(module, ledger)
        errors = ledger_errors(root)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("carries no written reason", errors[0])

    def test_a_deferred_disposition_must_name_an_owner_that_a_process_re_reads(self) -> None:
        module = (
            "from tests.support import CANDIDATE_ROOT\n"
            "class PlantedTests:\n"
            "    def test_count(self):\n"
            "        self.assertEqual(len(load(CANDIDATE_ROOT)), 18)\n"
        )
        ledger = self.empty_ledger()
        row = {"path": "tests/test_planted.py", "test": "PlantedTests.test_count", "literal": "18", "disposition": "deferred", "reason": "why"}
        root = self.fixture(module, {**ledger, "dispositions": [row]})
        self.assertIn("names no owner", " ".join(ledger_errors(root)))
        owned = self.fixture(module, {**ledger, "dispositions": [{**row, "owner": "finding-9"}]})
        self.assertEqual(ledger_errors(owned), [])

    def test_a_converted_instance_that_comes_back_reds(self) -> None:
        """The sweep's converted column is a regression guard, not a changelog: re-introducing the
        literal it removed reds on the row that says it was removed."""
        module = (
            "from tests.support import CANDIDATE_ROOT\n"
            "class PlantedTests:\n"
            "    def test_release(self):\n"
            "        self.assertEqual(load(CANDIDATE_ROOT)['release'], 'v0.1.5')\n"
        )
        ledger = self.empty_ledger()
        ledger["converted"] = [
            {"path": "tests/test_planted.py", "test": "PlantedTests.test_release", "was": "'v0.1.5'", "now": "shape and derivation"}
        ]
        ledger["dispositions"] = [
            {
                "path": "tests/test_planted.py",
                "test": "PlantedTests.test_release",
                "literal": "'v0.1.5'",
                "disposition": "invariant",
                "reason": "planted",
            }
        ]
        root = self.fixture(module, ledger)
        self.assertIn("is back", " ".join(ledger_errors(root)))


class ConvertedValueDeadlockTests(unittest.TestCase):
    """End-to-end control for the conversion this atom landed: ONE trusted reader judges a fixture
    PAIR that differs only in the value a candidate legally moves, and both are green.

    That is the whole difference between a memorized literal and a disclosure. Under the literal,
    the second tree is unmergeable by construction - `main`'s copy of the test holds the first
    tree's number. Under the conversion, the trusted side judges shape, derivation and internal
    consistency, so the candidate carries its own number and no trusted-side edit is needed."""

    BASE = {
        "schema_version": 1,
        "runtime": {
            "repository": "poteto/noodle",
            "release": "v0.1.5",
            "commit": "e" * 40,
            "command": "noodle",
            "platforms": {"darwin_arm64": {"asset_name": "noodle_darwin_arm64.tar.gz", "asset_sha256": "a" * 64, "binary_sha256": "b" * 64}},
        },
    }

    def tree(self, lock: dict[str, Any]) -> Path:
        temp = tempfile.TemporaryDirectory(prefix="noodles-runtime-lock-", ignore_cleanup_errors=True)
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "policy").mkdir()
        (root / "policy/runtime.lock.json").write_text(json.dumps(lock) + "\n", encoding="utf-8")
        return root

    def moved(self) -> dict[str, Any]:
        """A legal release bump: new release, new commit, new digests, same shape."""
        runtime = {**self.BASE["runtime"], "release": "v0.2.0", "commit": "f" * 40}
        runtime["platforms"] = {"darwin_arm64": {"asset_name": "noodle_darwin_arm64.tar.gz", "asset_sha256": "c" * 64, "binary_sha256": "d" * 64}}
        return {**self.BASE, "runtime": runtime}

    def test_the_same_trusted_reader_admits_both_halves_of_the_fixture_pair(self) -> None:
        self.assertEqual(runtime_lock_shape_errors(self.tree(self.BASE)), [])
        self.assertEqual(runtime_lock_shape_errors(self.tree(self.moved())), [])

    def test_the_reader_still_refuses_the_shapes_the_literal_used_to_catch(self) -> None:
        unpinned = {**self.BASE, "runtime": {**self.BASE["runtime"], "commit": "main"}}
        self.assertIn("40-hex", " ".join(runtime_lock_shape_errors(self.tree(unpinned))))
        foreign = {**self.BASE, "runtime": {**self.BASE["runtime"], "repository": "someone-else/noodle"}}
        self.assertIn("poteto/noodle", " ".join(runtime_lock_shape_errors(self.tree(foreign))))
        mismatched = {**self.BASE, "runtime": {**self.BASE["runtime"], "platforms": {"darwin_arm64": {"asset_name": "noodle_linux_amd64.tar.gz", "asset_sha256": "c" * 64, "binary_sha256": "d" * 64}}}}
        self.assertIn("asset_name", " ".join(runtime_lock_shape_errors(self.tree(mismatched))))


if __name__ == "__main__":
    unittest.main()

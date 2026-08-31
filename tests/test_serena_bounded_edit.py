from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
import unittest
from pathlib import Path
from typing import Any, Callable

import noodles
from tests.support import CANDIDATE_ROOT

EVIDENCE_PATH = "migrations/skills-shared/serena-bounded-edit-evidence.json"
PROBE_PATH = "migrations/skills-shared/serena_bounded_edit_probe.py"
UPSTREAM_SOURCE = "https://github.com/oraios/serena.git"
DISTRIBUTION_PACKAGE = "serena-agent"
HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
EXACT_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")

LIFECYCLE = ("export", "find_symbol", "find_referencing_symbols", "replace_symbol_body", "immutable_tests", "diff_readback")
POSITIVE_RUN = "bounded_edit"
REQUIRED_CONTROLS = {
    "out_of_scope_edit": "scope_violation",
    "stale_symbol_index": "stale_index",
    "changed_reference": "reference_drift",
    "failing_immutable_test": "immutable_tests_failed",
}
# constraint: the probe is excluded from the tracked-source scan, so each run is pinned back to the
# constraint: exact body literal it claims to have written; otherwise that exclusion is a blind spot.
RUN_BODIES = {
    POSITIVE_RUN: "EQUIVALENT_BODY",
    "out_of_scope_edit": "OUT_OF_SCOPE_BODY",
    "stale_symbol_index": "EQUIVALENT_BODY",
    "changed_reference": "EQUIVALENT_BODY",
    "failing_immutable_test": "REGRESSING_BODY",
}

def out_of_scope(run: dict[str, Any]) -> list[str]:
    """Derive the scope breach from the diff itself; the receipt's own summary of it is not evidence."""
    return [path for path in run["edit_changed_paths"] if path not in run["declared_scope"]]


# constraint: the admission rule is recomputed here from the recorded facts instead of trusting the
# constraint: receipt's own verdict, so a producer that records a green verdict over red facts fails.
GUARD_RULES: tuple[tuple[str, Callable[[dict[str, Any]], bool]], ...] = (
    ("scope_violation", lambda run: bool(out_of_scope(run))),
    ("stale_index", lambda run: not run["navigation_body_present_at_edit_time"]),
    ("reference_drift", lambda run: not run["reference_sites_intact"]),
    ("immutable_tests_failed", lambda run: not run["immutable_tests"]["passed"]),
    ("immutable_tests_mutated", lambda run: not run["immutable_test_files_unchanged"]),
)


def load_evidence(root: Path) -> dict[str, Any]:
    return json.loads((root / EVIDENCE_PATH).read_text(encoding="utf-8"))


def probe_constants(root: Path) -> dict[str, Any]:
    """Read the producer's own literals so a receipt cannot claim a run the probe never performs."""
    module = ast.parse((root / PROBE_PATH).read_text(encoding="utf-8"))
    constants: dict[str, Any] = {}
    for node in module.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            try:
                constants[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                continue
    return constants


def tracked_source(root: Path) -> list[tuple[str, str]]:
    """Tracked Python source under edit, which is every tracked `.py` file except the producer.

    The probe carries the replacement bodies as literals because a real edit needs real bytes, so
    counting it here would let the probe's own declaration masquerade as a definition in the
    repository and would read its declared bodies as an edit that landed on this checkout.
    """
    sources: list[tuple[str, str]] = []
    for _mode, relative in noodles.tracked_entries(root):
        path = root / relative
        if path.is_file() and relative.endswith(".py") and relative != PROBE_PATH:
            sources.append((relative, path.read_text(encoding="utf-8", errors="ignore")))
    return sources


def guards(run: dict[str, Any]) -> list[str]:
    return [name for name, rule in GUARD_RULES if rule(run)]


def pin_errors(receipt: dict[str, Any], declared: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    pin = receipt.get("pin", {})
    distribution = pin.get("distribution", {})
    if pin.get("source") != UPSTREAM_SOURCE or not HEX40_RE.fullmatch(str(pin.get("commit", ""))):
        errors.append("receipt must pin the upstream Serena repository at an exact 40-hex commit")
    if distribution.get("package") != DISTRIBUTION_PACKAGE:
        errors.append(f"receipt must pin the {DISTRIBUTION_PACKAGE} distribution")
    if not EXACT_VERSION_RE.fullmatch(str(distribution.get("version", ""))):
        errors.append("receipt distribution version is a floating ref, not an exact release")
    for digest_key in ("sdist_sha256", "wheel_sha256"):
        if not HEX64_RE.fullmatch(str(distribution.get(digest_key, ""))):
            errors.append(f"receipt distribution {digest_key} is not an exact 64-hex digest")
    if (pin.get("source"), pin.get("commit"), distribution) != (
        declared.get("PIN_SOURCE"),
        declared.get("PIN_COMMIT"),
        declared.get("PIN_DISTRIBUTION"),
    ):
        errors.append("receipt pin does not match the pin the probe would actually run under")
    if tuple(pin.get("fixed_tools", ())) != tuple(declared.get("BOUNDED_TOOLS", ())):
        errors.append("receipt tool allowlist does not match the allowlist the probe configures")
    if tuple(pin.get("editing_tools", ())) != tuple(declared.get("EDITING_TOOLS", ())) or len(pin.get("editing_tools", ())) != 1:
        errors.append("a bounded edit run must expose exactly the one pinned editing tool")
    return errors


def surface_errors(receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    pin = receipt.get("pin", {})
    surface = receipt.get("tool_surface", {})
    if sorted(surface.get("exposed_tools", [])) != sorted(pin.get("fixed_tools", [])):
        errors.append("exposed tool set does not equal the pinned allowlist")
    if sorted(surface.get("editing_tools_exposed", [])) != sorted(pin.get("editing_tools", [])):
        errors.append(f"run exposed unpinned editing tools: {surface.get('editing_tools_exposed')}")
    if surface.get("project_serena_folder_inside_repository") is not False:
        errors.append("the Serena project data folder was not redirected outside the repository")
    return errors


def navigation_errors(receipt: dict[str, Any], root: Path, declared: dict[str, Any]) -> list[str]:
    """Re-derive the navigation half straight from repository source; Serena is never installed here."""
    errors: list[str] = []
    subject = receipt.get("subject", {})
    symbol = subject.get("symbol")
    relative_path = str(subject.get("relative_path", ""))
    if subject.get("repository") != "ed3c/noodles" or not HEX40_RE.fullmatch(str(subject.get("commit", ""))):
        errors.append("receipt subject must pin ed3c/noodles at an exact 40-hex commit")
    if (symbol, relative_path, tuple(subject.get("declared_scope", ()))) != (
        declared.get("SUBJECT_SYMBOL"),
        declared.get("SUBJECT_FILE"),
        tuple(declared.get("DECLARED_SCOPE", ())),
    ):
        errors.append("receipt subject and scope do not match the subject the probe edits")

    sources = tracked_source(root)
    definitions = sum(text.count(f"def {symbol}(") for _relative, text in sources)
    if definitions != 1:
        errors.append(f"subject symbol is not a unique definition in tracked source, found {definitions}")

    navigation = receipt.get("navigation", {})
    matches = navigation.get("find_symbol", {}).get("matches", [])
    if len(matches) != 1 or matches[0].get("name_path") != symbol or matches[0].get("relative_path") != relative_path:
        errors.append("find_symbol must resolve the subject to exactly one definition in the subject file")
    body = navigation.get("find_symbol", {}).get("body", "")
    if hashlib.sha256(body.encode("utf-8")).hexdigest() != navigation.get("find_symbol", {}).get("body_sha256"):
        errors.append("recorded symbol body does not match its own digest")
    subject_source = (root / relative_path).read_text(encoding="utf-8") if (root / relative_path).is_file() else ""
    if not body or body not in subject_source:
        errors.append("recorded symbol body does not read back byte-exactly from the subject file")

    readbacks = navigation.get("source_readback", [])
    if len(navigation.get("find_referencing_symbols", {}).get("referencing_files", [])) < 2:
        errors.append("find_referencing_symbols must reach a real consumer in more than one file")
    for item in readbacks:
        path = root / item["relative_path"]
        if not path.is_file():
            errors.append(f"recorded readback path is absent: {item['relative_path']}")
            continue
        occurrences = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip() == item["text"]]
        if len(occurrences) != 1:
            errors.append(f"recorded reference text does not occur exactly once in {item['relative_path']}")
        if hashlib.sha256(item["text"].encode("utf-8")).hexdigest() != item["text_sha256"]:
            errors.append(f"recorded reference digest does not match its own text in {item['relative_path']}")

    read_paths = {relative_path} | {item["relative_path"] for item in readbacks}
    if read_paths & set(subject.get("uncommitted_paths_at_probe_time", [])):
        errors.append("a file the receipt reads back was uncommitted when the probe ran")

    # constraint: the edit really happened somewhere else. If a body the probe writes were present in
    # constraint: tracked source, the run would have been editing this repository rather than an export.
    for name in ("EQUIVALENT_BODY", "REGRESSING_BODY", "OUT_OF_SCOPE_BODY"):
        written = str(declared.get(name, ""))
        if written and any(written in text for _relative, text in sources):
            errors.append(f"{name} leaked into tracked source: the edit was not confined to a throwaway export")
    return errors


def run_errors(receipt: dict[str, Any], declared: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if list(receipt.get("guard_names", [])) != [name for name, _rule in GUARD_RULES]:
        errors.append("receipt guard set does not match the guards this gate recomputes")

    runs = receipt.get("runs", {})
    if set(runs) != {POSITIVE_RUN, *REQUIRED_CONTROLS}:
        errors.append(f"runs must be the positive lifecycle plus every planted control, got {sorted(runs)}")
        return errors

    navigation = receipt.get("navigation", {})
    for name, run in sorted(runs.items()):
        if guards(run) != run.get("blocked_by"):
            errors.append(f"{name}: recorded verdict disagrees with the guards its own facts trigger")
        if run.get("admitted") is not (not run.get("blocked_by")):
            errors.append(f"{name}: admission flag disagrees with its blocking guards")
        if run.get("root_outside_repository") is not True:
            errors.append(f"{name}: the lifecycle did not run in an export outside the repository")
        if run.get("immutable_test_files_unchanged") is not True:
            errors.append(f"{name}: the edit surface reached the immutable tests")
        if [step for step in run.get("steps", []) if step != "drift_control"] != list(LIFECYCLE):
            errors.append(f"{name}: lifecycle steps are missing or out of order: {run.get('steps')}")
        expected_body = str(declared.get(RUN_BODIES[name], ""))
        if run.get("edit", {}).get("body_sha256") != hashlib.sha256(expected_body.encode("utf-8")).hexdigest():
            errors.append(f"{name}: recorded edit body is not the {RUN_BODIES[name]} literal the probe writes")
        if run.get("out_of_scope_paths") != out_of_scope(run):
            errors.append(f"{name}: recorded scope breach disagrees with the recorded diff")
        if run.get("immutable_tests", {}).get("passed") is not (run.get("immutable_tests", {}).get("returncode") == 0):
            errors.append(f"{name}: immutable test verdict disagrees with its own exit status")
        if run.get("edit_readback") is not True:
            errors.append(f"{name}: the edit did not read back from the edited file")
        if run.get("navigation", {}).get("body_sha256") != navigation.get("find_symbol", {}).get("body_sha256"):
            errors.append(f"{name}: navigated a different symbol body than the recorded chain")
        if run.get("navigation", {}).get("reference_sites_sha256") != navigation.get("find_referencing_symbols", {}).get("reference_sites_sha256"):
            errors.append(f"{name}: navigated a different reference set than the recorded chain")

    positive = runs[POSITIVE_RUN]
    if positive.get("admitted") is not True or positive.get("blocked_by"):
        errors.append(f"the positive lifecycle must be admitted, blocked by {positive.get('blocked_by')}")
    if positive.get("edit_changed_paths") != list(declared.get("DECLARED_SCOPE", ())):
        errors.append(f"the admitted diff touched {positive.get('edit_changed_paths')} instead of the declared scope")
    if positive.get("immutable_tests", {}).get("returncode") != 0:
        errors.append("the admitted lifecycle did not leave the immutable tests passing")

    designated = [runs[name].get("designated_guard") for name in REQUIRED_CONTROLS]
    if sorted(designated) != sorted(REQUIRED_CONTROLS.values()) or len(set(designated)) != len(designated):
        errors.append("the planted controls do not exercise four distinct guards")
    for name, guard in REQUIRED_CONTROLS.items():
        control = runs[name]
        if control.get("designated_guard") != guard:
            errors.append(f"{name}: control is not aimed at {guard}")
        if control.get("admitted") is not False or control.get("blocked_by") != [guard]:
            errors.append(f"{name}: control must be blocked by {guard} alone, got {control.get('blocked_by')}")

    # constraint: proof the immutable tests can actually go red - the same command over the same export
    # constraint: passes for the equivalent body and fails for the regressing one.
    failing = runs["failing_immutable_test"]
    if failing.get("immutable_tests", {}).get("returncode") == positive.get("immutable_tests", {}).get("returncode"):
        errors.append("the immutable tests answered identically for an equivalent and a regressing body")
    return errors


def evidence_errors(receipt: dict[str, Any], root: Path) -> list[str]:
    declared = probe_constants(root)
    errors = pin_errors(receipt, declared)
    errors.extend(surface_errors(receipt))
    errors.extend(navigation_errors(receipt, root, declared))
    errors.extend(run_errors(receipt, declared))

    tests = receipt.get("immutable_tests", {})
    module_path = root / (str(tests.get("module", "")).replace(".", "/") + ".py")
    if tests.get("module") != declared.get("IMMUTABLE_TEST_MODULE") or not module_path.is_file():
        errors.append("the immutable test module the probe names is absent from this repository")
    if not EXACT_VERSION_RE.fullmatch(str(tests.get("interpreter_version", ""))):
        errors.append("the immutable tests did not record an exact interpreter version")

    residue = receipt.get("residue", {})
    if residue.get("worktree_unchanged") is not True or residue.get("tree_unchanged") is not True:
        errors.append("the bounded edit run did not leave the repository worktree and tree unchanged")
    if residue.get("paths_created_by_invocation"):
        errors.append(f"the run created residue: {residue['paths_created_by_invocation']}")
    if residue.get("serena_folder_in_repository") is not False:
        errors.append("a .serena index folder was left inside the repository")
    if residue.get("workspace_removed") is not True:
        errors.append("the throwaway edit workspace was not cleaned up")
    return errors


class SerenaBoundedEditEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = CANDIDATE_ROOT
        self.receipt = load_evidence(self.root)

    def planted(self, mutate: Any) -> list[str]:
        receipt = copy.deepcopy(self.receipt)
        mutate(receipt)
        return evidence_errors(receipt, self.root)

    def test_positive_control_admits_the_recorded_bounded_edit_receipt(self) -> None:
        self.assertEqual(evidence_errors(self.receipt, self.root), [])

    def test_ledger_routes_to_the_receipt_without_promoting_itself(self) -> None:
        ledger = json.loads((self.root / "migrations/skills-shared/ledger.json").read_text(encoding="utf-8"))
        entry = next(item for item in ledger["capabilities"] if item["id"] == "serena-bounded-edit")
        self.assertEqual(entry["disposition"], "REVALIDATE")
        self.assertEqual(entry["physical_evidence"], [])
        self.assertEqual(entry["validation_receipt"], EVIDENCE_PATH)

    def test_planted_out_of_scope_diff_in_the_admitted_run_is_rejected(self) -> None:
        errors = self.planted(lambda r: r["runs"]["bounded_edit"]["edit_changed_paths"].append("noodles.py"))
        self.assertTrue(any("disagrees with the guards" in error for error in errors), errors)

    def test_planted_control_that_silently_passed_is_rejected(self) -> None:
        def mutate(receipt: dict[str, Any]) -> None:
            receipt["runs"]["out_of_scope_edit"].update(out_of_scope_paths=[], blocked_by=[], admitted=True)

        self.assertTrue(any("blocked by scope_violation alone" in error for error in self.planted(mutate)), self.planted(mutate))

    def test_planted_green_verdict_over_red_facts_is_rejected(self) -> None:
        errors = self.planted(lambda r: r["runs"]["failing_immutable_test"].update(blocked_by=[], admitted=True))
        self.assertTrue(any("disagrees with the guards" in error for error in errors), errors)

    def test_planted_insensitive_immutable_tests_are_rejected(self) -> None:
        def mutate(receipt: dict[str, Any]) -> None:
            receipt["runs"]["failing_immutable_test"]["immutable_tests"].update(returncode=0, passed=True)
            receipt["runs"]["failing_immutable_test"].update(blocked_by=[], admitted=False)

        self.assertTrue(any("answered identically" in error for error in self.planted(mutate)), self.planted(mutate))

    def test_planted_edit_reaching_the_immutable_tests_is_rejected(self) -> None:
        errors = self.planted(lambda r: r["runs"]["bounded_edit"].update(immutable_test_files_unchanged=False))
        self.assertTrue(any("reached the immutable tests" in error for error in errors), errors)

    def test_planted_extra_editing_tool_is_rejected(self) -> None:
        errors = self.planted(lambda r: r["tool_surface"]["editing_tools_exposed"].append("execute_shell_command"))
        self.assertTrue(any("unpinned editing tools" in error for error in errors), errors)

    def test_planted_fabricated_readback_is_rejected(self) -> None:
        errors = self.planted(lambda r: r["navigation"]["source_readback"][0].update(text="return 42  # not in source"))
        self.assertTrue(any("does not occur exactly once" in error for error in errors), errors)

    def test_planted_symbol_body_drift_is_rejected(self) -> None:
        errors = self.planted(lambda r: r["navigation"]["find_symbol"].update(body="def gone():\n    return None\n"))
        self.assertTrue(any("does not match its own digest" in error for error in errors), errors)

    def test_planted_floating_version_pin_is_rejected(self) -> None:
        errors = self.planted(lambda r: r["pin"]["distribution"].update(version="latest", sdist_sha256=""))
        self.assertTrue(any("floating ref" in error for error in errors), errors)
        self.assertTrue(any("sdist_sha256" in error for error in errors), errors)

    def test_planted_skipped_lifecycle_step_is_rejected(self) -> None:
        errors = self.planted(lambda r: r["runs"]["bounded_edit"]["steps"].remove("find_referencing_symbols"))
        self.assertTrue(any("out of order" in error for error in errors), errors)

    def test_planted_workspace_and_index_residue_is_rejected(self) -> None:
        errors = self.planted(lambda r: r["residue"].update(workspace_removed=False, serena_folder_in_repository=True))
        self.assertTrue(any("workspace was not cleaned up" in error for error in errors), errors)
        self.assertTrue(any(".serena index folder" in error for error in errors), errors)

    def test_planted_edit_body_the_probe_never_writes_is_rejected(self) -> None:
        errors = self.planted(lambda r: r["runs"]["failing_immutable_test"]["edit"].update(body_sha256="0" * 64))
        self.assertTrue(any("not the REGRESSING_BODY literal" in error for error in errors), errors)

    def test_planted_dropped_control_is_rejected(self) -> None:
        errors = self.planted(lambda r: r["runs"].pop("changed_reference"))
        self.assertTrue(any("plus every planted control" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()

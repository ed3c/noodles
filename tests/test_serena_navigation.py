from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
import unittest
from pathlib import Path
from typing import Any

import noodles
from tests.support import CANDIDATE_ROOT

EVIDENCE_PATH = "migrations/skills-shared/serena-navigation-evidence.json"
PROBE_PATH = "migrations/skills-shared/serena_navigation_probe.py"
UPSTREAM_SOURCE = "https://github.com/oraios/serena.git"
DISTRIBUTION_PACKAGE = "serena-agent"
HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
EXACT_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def load_evidence(root: Path) -> dict[str, Any]:
    return json.loads((root / EVIDENCE_PATH).read_text(encoding="utf-8"))


def probe_pin_constants(root: Path) -> dict[str, Any]:
    """Read the producer's own pin literals so a receipt cannot claim a build the probe never runs."""
    module = ast.parse((root / PROBE_PATH).read_text(encoding="utf-8"))
    constants: dict[str, Any] = {}
    for node in module.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name.startswith("PIN_"):
                constants[name] = ast.literal_eval(node.value)
    return constants


def tracked_definition_count(root: Path, declaration: str) -> int:
    """Recompute a claimed definition count straight from tracked Python source, never from the receipt.

    Scoped to `.py` because the claim under test is about Python symbols; counting every tracked file
    would let the receipt's own prose about a symbol inflate the count that is supposed to check it.
    """
    count = 0
    for _mode, relative in noodles.tracked_entries(root):
        path = root / relative
        if path.is_file() and relative.endswith(".py"):
            count += path.read_text(encoding="utf-8", errors="ignore").count(declaration)
    return count


def evidence_errors(receipt: dict[str, Any], root: Path) -> list[str]:
    """Re-derive every claim in the receipt from repository source and the pinned provider entry.

    Serena is never installed for this gate. An index receipt is admitted only when the source it
    points at still says what it claims, so a fabricated, mutated, or drifted receipt fails here.
    """
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
    declared = probe_pin_constants(root)
    if (pin.get("source"), pin.get("commit"), distribution) != (
        declared.get("PIN_SOURCE"),
        declared.get("PIN_COMMIT"),
        declared.get("PIN_DISTRIBUTION"),
    ):
        errors.append("receipt pin does not match the pin the probe would actually run under")

    subject = receipt.get("subject", {})
    if subject.get("repository") != "ed3c/noodles" or not HEX40_RE.fullmatch(str(subject.get("commit", ""))):
        errors.append("receipt subject must pin ed3c/noodles at an exact 40-hex commit")

    enforcement = receipt.get("read_only_enforcement", {})
    if enforcement.get("editing_tools_exposed"):
        errors.append(f"read-only run exposed editing tools: {enforcement['editing_tools_exposed']}")
    if sorted(enforcement.get("exposed_tools", [])) != sorted(pin.get("fixed_tools", [])):
        errors.append("exposed tool set does not equal the pinned read-only allowlist")
    if enforcement.get("project_serena_folder_inside_repository") is not False:
        errors.append("the Serena project data folder was not redirected outside the repository")

    residue = receipt.get("residue", {})
    if residue.get("worktree_unchanged") is not True or residue.get("tree_unchanged") is not True:
        errors.append("read-only invocation did not leave the worktree and tree unchanged")
    if residue.get("paths_created_by_invocation"):
        errors.append(f"read-only invocation created residue: {residue['paths_created_by_invocation']}")
    if residue.get("serena_folder_in_repository") is not False:
        errors.append("a .serena index folder was left inside the repository")

    chain = receipt.get("chain", {})
    matches = chain.get("find_symbol", {}).get("matches", [])
    if len(matches) != 1:
        errors.append(f"find_symbol must resolve the subject symbol to exactly one definition, got {len(matches)}")
    for match in matches:
        declaration = f"def {match['name_path']}("
        if tracked_definition_count(root, declaration) != 1:
            errors.append(f"find_symbol match {match['name_path']} is not a unique definition in tracked source")
        if declaration not in (root / match["relative_path"]).read_text(encoding="utf-8"):
            errors.append(f"find_symbol match does not read back from {match['relative_path']}")

    readbacks = chain.get("source_readback", [])
    if len({item["relative_path"] for item in readbacks}) < 2:
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

    controls = receipt.get("controls", {})
    wrong = controls.get("wrong_symbol", {})
    if wrong.get("matches") != 0:
        errors.append("wrong-symbol control must report zero matches")
    if wrong.get("definitions_in_tracked_source") != tracked_definition_count(root, f"def {wrong.get('query')}("):
        errors.append("wrong-symbol control absence claim disagrees with tracked source")

    ambiguous = controls.get("ambiguous_symbol", {})
    candidates = ambiguous.get("candidates", [])
    if len(candidates) < 2 or ambiguous.get("matches") != len(candidates):
        errors.append("ambiguous-symbol control must enumerate every candidate instead of choosing one")
    if len(candidates) != tracked_definition_count(root, f"def {ambiguous.get('query')}("):
        errors.append("ambiguous-symbol candidate count disagrees with tracked source")

    unsupported = controls.get("unsupported_language", {})
    if unsupported.get("matches") != 0 or unsupported.get("outcome") != "bounded_error":
        errors.append("unsupported-language control must fail bounded rather than answer")
    queried = unsupported.get("query", {}).get("relative_path", "")
    token = unsupported.get("query", {}).get("name_path_pattern", "")
    recomputed = (root / queried).read_text(encoding="utf-8").count(token) if (root / queried).is_file() else 0
    if unsupported.get("occurrences_in_queried_file") != recomputed or recomputed < 1:
        errors.append("unsupported-language control must show the miss is a language limit, not absence")

    stale = controls.get("stale_index", {})
    if stale.get("isolated_root_outside_repository") is not True or stale.get("mutation_applied") is not True:
        errors.append("stale-index control must mutate an isolated export, never the repository")
    if stale.get("readback_confirms_definition_after_mutation") is not False:
        errors.append("stale-index control must read back the mutated source rather than trust the index")

    return errors


class SerenaNavigationEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = CANDIDATE_ROOT
        self.receipt = load_evidence(self.root)

    def planted(self, mutate: Any) -> list[str]:
        receipt = copy.deepcopy(self.receipt)
        mutate(receipt)
        return evidence_errors(receipt, self.root)

    def test_positive_control_admits_the_recorded_navigation_receipt(self) -> None:
        self.assertEqual(evidence_errors(self.receipt, self.root), [])

    def test_ledger_records_the_fresh_physical_evidence(self) -> None:
        ledger = json.loads((self.root / "migrations/skills-shared/ledger.json").read_text(encoding="utf-8"))
        entry = next(item for item in ledger["capabilities"] if item["id"] == "serena-symbol-navigation")
        self.assertEqual(entry["disposition"], "MIGRATE")
        self.assertIn(EVIDENCE_PATH, entry["physical_evidence"])
        self.assertNotIn("next_issue", entry)

    def test_planted_fabricated_readback_is_rejected(self) -> None:
        errors = self.planted(lambda r: r["chain"]["source_readback"][0].update(text="return 42  # not in source"))
        self.assertTrue(any("does not occur exactly once" in error for error in errors), errors)

    def test_planted_index_residue_is_rejected(self) -> None:
        errors = self.planted(lambda r: r["residue"].update(serena_folder_in_repository=True))
        self.assertTrue(any(".serena index folder" in error for error in errors), errors)

    def test_planted_exposed_editing_tool_is_rejected(self) -> None:
        errors = self.planted(lambda r: r["read_only_enforcement"]["editing_tools_exposed"].append("replace_symbol_body"))
        self.assertTrue(any("exposed editing tools" in error for error in errors), errors)

    def test_planted_floating_version_pin_is_rejected(self) -> None:
        errors = self.planted(lambda r: r["pin"]["distribution"].update(version="latest", sdist_sha256=""))
        self.assertTrue(any("floating ref" in error for error in errors), errors)
        self.assertTrue(any("sdist_sha256" in error for error in errors), errors)

    def test_planted_index_trusted_over_source_is_rejected(self) -> None:
        errors = self.planted(lambda r: r["controls"]["stale_index"].update(readback_confirms_definition_after_mutation=True))
        self.assertTrue(any("read back the mutated source" in error for error in errors), errors)

    def test_planted_absence_claim_without_source_agreement_is_rejected(self) -> None:
        errors = self.planted(lambda r: r["controls"]["wrong_symbol"].update(definitions_in_tracked_source=3))
        self.assertTrue(any("absence claim disagrees" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()

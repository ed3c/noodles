"""What joins code-intelligence v1 is derived from the corpus run, never asserted next to it.

`migrations/skills-shared/code_intel_v1_probe.py` records only observations. This gate owns the
predeclared admission rule, recomputes every number the rule rests on from the receipt's own rows and
from tracked source, and binds the ledger entry to the result. No retrieval tool, no parser, no
network and no store is installed here.

The rule has two clauses and both are two-sided:

  an edge joins v1        when every task exercised it and its own ledger capability is MIGRATE;
  an optional component   joins v1 when the corpus leaves a residual in the class it addresses *and*
                          its own capability was promoted to MIGRATE.

`test_planted_structural_residual_admits_the_navigation_component` and
`test_planted_store_promotion_admits_the_vector_store` prove the second clause can say yes. What
excludes every optional component on this repository is a measured zero, not the rule.
"""
from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path
from typing import Any

import noodles
from tests.support import CANDIDATE_ROOT
from tests.test_lancedb_ab import probe_constants, unique_declaration_file

EVIDENCE_PATH = "migrations/skills-shared/code-intel-v1-evidence.json"
PROBE_PATH = "migrations/skills-shared/code_intel_v1_probe.py"
CORPUS_PROBE_PATH = "migrations/skills-shared/lancedb_ab_probe.py"
LEDGER_PATH = "migrations/skills-shared/ledger.json"
RETRIEVAL_LOCK_PATH = "policy/retrieval.lock.json"
CAPABILITY = "code-intelligence-v1"
SUBJECT_ISSUE = "ed3c/noodles#13"

# constraint: the files that quote the task queries verbatim. A candidate naming one means the corpus
# constraint: was indexed with its own answer key in it and every number is worthless.
ANSWER_KEYS = (
    CORPUS_PROBE_PATH,
    "migrations/skills-shared/lancedb-ab-evidence.json",
    "tests/test_lancedb_ab.py",
    PROBE_PATH,
    EVIDENCE_PATH,
    "tests/test_code_intel_v1.py",
)

CONTROLS = ("wrong_subject", "stale_source", "wrong_adapter", "wrong_path", "wrong_range")
CONTROL_FAMILIES = ("positive", "boundary_fault", "stale_data", "source_provider_readback", "residue")

HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
CANDIDATE_RE = re.compile(r"^(?P<path>[^:]+):(?P<start>\d+)-(?P<end>\d+)$")


def dispositions(root: Path) -> dict[str, str]:
    ledger = json.loads((root / LEDGER_PATH).read_text(encoding="utf-8"))
    return {item["id"]: item["disposition"] for item in ledger["capabilities"]}


def declares(root: Path, relative: str, name: str) -> bool:
    """Readback for what the chain resolved, by text so line drift never invalidates it.

    Ground truth is identified by being the *unique* declaration of its symbol; a resolved definition
    is not, and must not be held to that. The chain is free to land on a private helper whose name
    repeats across files - `_git` does - so the binding is that the name is still declared in the file
    the receipt named, not that the repository holds exactly one of it.
    """
    if relative not in {path for _mode, path in noodles.tracked_entries(root)}:
        return False
    source = (root / relative).read_text(encoding="utf-8", errors="ignore")
    headers = (f"def {name}(", f"async def {name}(", f"class {name}(", f"class {name}:")
    return any(header in source for header in headers)


def residual_class(row: dict[str, Any]) -> str | None:
    """The gate's own copy of the classifier, so a receipt cannot label its own failures."""
    if row["outcome"] != "admitted":
        return "structural_refusal"
    if row["exact"]:
        return None
    if row["hit_rank"] is None:
        return "retrieval_rank"
    return "definition_selection"


def edge_reasons(receipt: dict[str, Any], ledger: dict[str, str]) -> list[str]:
    """Clause one: the chain itself. An edge is admitted only if every task actually crossed it."""
    reasons: list[str] = []
    admitted = [row for row in receipt["tasks"] if row["outcome"] == "admitted"]
    if not admitted:
        reasons.append("no task produced an admitted evidence row; there is no chain to converge")
        return reasons
    for edge in receipt["admitted_edges"]:
        capability = edge["ledger_capability"]
        if capability is not None and ledger.get(capability) != "MIGRATE":
            reasons.append(f"{edge['edge']}: {capability} is {ledger.get(capability)!r}, not an admitted MIGRATE")
    for row in admitted:
        if not row["candidates"]:
            reasons.append(f"{row['target_path']}: no candidate path was recorded for the intent-query edge")
        if not row["resolved_path"] or not row["resolved_definition"]:
            reasons.append(f"{row['target_path']}: no structural definition was recorded")
        if tuple(row["controls"]) != CONTROLS:
            reasons.append(f"{row['target_path']}: planted controls {row['controls']} are not {list(CONTROLS)}")
    if not receipt["residue"]["tree_unchanged"]:
        reasons.append("the convergence run mutated the candidate tree it was measuring")
    return reasons


def optional_reasons(component: dict[str, Any], residual: dict[str, int], ledger: dict[str, str]) -> list[str]:
    """Clause two: an optional component. Empty reasons mean it joins v1."""
    reasons: list[str] = []
    addresses = component["addresses"]
    if residual.get(addresses, 0) <= 0:
        reasons.append(f"the corpus leaves no {addresses} residual for it to reduce")
    disposition = ledger.get(component["ledger_capability"])
    if disposition != "MIGRATE":
        reasons.append(f"its own capability is {disposition!r}, not an admitted MIGRATE")
    return reasons


def excluded_components(receipt: dict[str, Any], ledger: dict[str, str]) -> dict[str, list[str]]:
    residual = recomputed_residual(receipt)
    excluded = {}
    for component in receipt["optional_components"]:
        reasons = optional_reasons(component, residual, ledger)
        if reasons:
            excluded[component["ledger_capability"]] = reasons
    return excluded


def verdict(receipt: dict[str, Any], ledger: dict[str, str]) -> str:
    return "DROP" if edge_reasons(receipt, ledger) else "MIGRATE"


def recomputed_residual(receipt: dict[str, Any]) -> dict[str, int]:
    # constraint: the class list comes from the producer's own declaration, so a receipt cannot
    # constraint: quietly drop a class it scored badly on and still match its own recomputation.
    counts = {name: 0 for name in probe_constants(CANDIDATE_ROOT, PROBE_PATH)["RESIDUAL_CLASSES"]}
    for row in receipt["tasks"]:
        name = residual_class(row)
        if name is not None:
            counts[name] = counts.get(name, 0) + 1
    return counts


def task_errors(row: dict[str, Any], declared: tuple[str, str, str], top_k: int, tracked: set[str]) -> list[str]:
    query, target_path, target_symbol = declared
    errors: list[str] = []
    if (row["query"], row["target_path"], row["target_symbol"]) != (query, target_path, target_symbol):
        return [f"the run was not scored on the declared task {query!r}"]
    paths: list[str] = []
    for candidate in row["candidates"]:
        match = CANDIDATE_RE.fullmatch(candidate)
        if match is None:
            errors.append(f"{target_path}: unreadable candidate {candidate!r}")
            continue
        if int(match["start"]) < 1 or int(match["end"]) < int(match["start"]):
            errors.append(f"{target_path}: impossible candidate range in {candidate!r}")
        if match["path"] not in tracked:
            errors.append(f"{target_path}: candidate {match['path']!r} is no longer tracked; re-run {PROBE_PATH}")
        if match["path"] in ANSWER_KEYS:
            errors.append(f"{target_path}: candidate {match['path']!r} quotes the task queries verbatim")
        paths.append(match["path"])
    if row["candidates"] and len(row["candidates"]) != top_k:
        errors.append(f"{target_path}: spent {len(row['candidates'])} candidates, not the pinned {top_k}")
    expected_rank = paths.index(target_path) + 1 if target_path in paths else None
    if row["hit_rank"] != expected_rank:
        errors.append(f"{target_path}: claims hit_rank {row['hit_rank']}, its own candidates say {expected_rank}")
    if row["outcome"] == "admitted":
        expected_exact = row["resolved_path"] == target_path and row["resolved_definition"] == target_symbol
        if row["exact"] != expected_exact:
            errors.append(f"{target_path}: claims exact={row['exact']} for {row['resolved_definition']!r}")
        if not declares(CANDIDATE_ROOT, row["resolved_path"], row["resolved_definition"]):
            errors.append(
                f"{target_path}: resolved {row['resolved_definition']!r} is not declared in "
                f"{row['resolved_path']!r} any more; re-run {PROBE_PATH}"
            )
        admitted_row = row["admitted_row"]
        if admitted_row["subject"] != SUBJECT_ISSUE:
            errors.append(f"{target_path}: evidence row names subject {admitted_row['subject']!r}")
        if not HEX64_RE.fullmatch(str(admitted_row["source_sha256"])):
            errors.append(f"{target_path}: evidence row carries no exact source digest")
        start, end = admitted_row["range"]
        if not 0 <= start < end:
            errors.append(f"{target_path}: evidence row records an impossible byte range {start}..{end}")
        if row["context_bytes"] <= 0:
            errors.append(f"{target_path}: claims {row['context_bytes']} context bytes for an admitted row")
    elif row["outcome"] == "refused":
        if not str(row["diagnostic"] or "").strip():
            errors.append(f"{target_path}: a refusal must carry a diagnostic, never a silent miss")
    else:
        errors.append(f"{target_path}: unknown outcome {row['outcome']!r}")
    return errors


def receipt_errors(receipt: dict[str, Any], root: Path) -> list[str]:
    """Every number the verdict rests on, recomputed from the receipt's rows and from tracked source."""
    errors: list[str] = []
    subject = receipt["subject"]
    if subject.get("repository") != "ed3c/noodles" or not HEX40_RE.fullmatch(str(subject.get("commit", ""))):
        errors.append("receipt subject must pin ed3c/noodles at an exact 40-hex commit")
    if subject.get("issue") != SUBJECT_ISSUE:
        errors.append(f"receipt subject must name {SUBJECT_ISSUE}")

    corpus_constants = probe_constants(root, CORPUS_PROBE_PATH)
    tasks = corpus_constants["TASKS"]
    top_k = corpus_constants["TOP_K"]
    if receipt["corpus"]["tasks"] != len(tasks) or receipt["corpus"]["top_k"] != top_k:
        errors.append(f"receipt claims {receipt['corpus']['tasks']} tasks at top_k {receipt['corpus']['top_k']}")
    if receipt["corpus"]["source"] != f"{CORPUS_PROBE_PATH}:TASKS":
        errors.append("the corpus must be the repository's one declared task set, cited by path")
    for answer_key in ANSWER_KEYS:
        if answer_key not in receipt["corpus"]["excluded_from_corpus"]:
            errors.append(f"the corpus must exclude the answer key {answer_key!r}")
    if len(receipt["tasks"]) != len(tasks):
        errors.append(f"the run scored {len(receipt['tasks'])} of the corpus's {len(tasks)} tasks")
        return errors

    tracked = {relative for _mode, relative in noodles.tracked_entries(root)}
    for row, declared in zip(receipt["tasks"], tasks):
        errors.extend(task_errors(row, tuple(declared), top_k, tracked))

    for query, target_path, target_symbol in tasks:
        if unique_declaration_file(root, target_symbol) != target_path:
            errors.append(f"ground truth for {query!r} is not a unique {target_symbol} declaration in {target_path}")

    admitted = [row for row in receipt["tasks"] if row["outcome"] == "admitted"]
    hits = [row for row in receipt["tasks"] if row["hit_rank"] is not None]
    exact = [row for row in admitted if row["exact"]]
    aggregates = {
        "tasks": len(receipt["tasks"]),
        "admitted_rows": len(admitted),
        "refusals": len(receipt["tasks"]) - len(admitted),
        "recall_at_k": round(len(hits) / len(receipt["tasks"]), 6),
        "path_resolution": len([row for row in admitted if row["resolved_path"] == row["target_path"]]),
        "exact_resolution": len(exact),
        "exact_resolution_rate": round(len(exact) / len(receipt["tasks"]), 6),
        "context_bytes_total": sum(row["context_bytes"] for row in admitted),
    }
    for metric, expected in aggregates.items():
        if receipt["quality"][metric] != expected:
            errors.append(f"receipt reports {metric}={receipt['quality'][metric]}, its own rows give {expected}")
    if receipt["residual"] != recomputed_residual(receipt):
        errors.append(f"receipt residual {receipt['residual']} is not what its own rows classify")
    if receipt["residual"]["edit"] != 0:
        errors.append("v1 has no edit edge, so an edit residual can only be a fabricated one")

    locked = json.loads((root / RETRIEVAL_LOCK_PATH).read_text(encoding="utf-8"))["retrieval"]
    providers = receipt["providers"]
    if providers["embedder"]["pinned"] != locked["embedder"]:
        errors.append("the run did not use the embedder the landed retrieval path is pinned to")
    if providers["embedder"]["observed_digest"] != locked["embedder"]["digest"]:
        errors.append("the serving embedder digest was not read back against the pin")
    if providers["retrieval_executable"]["sha256"] != locked["binary_sha256"]:
        errors.append("the run did not use the pinned retrieval executable")
    if locked["version"] not in providers["retrieval_executable"]["version_stdout"]:
        errors.append("the retrieval executable did not report the pinned version")
    if providers["index"]["index_bytes"] <= 0:
        errors.append("an unindexed project answers every query with an empty result")
    for family in CONTROL_FAMILIES:
        if not str(receipt["control_families"].get(family, "")).strip():
            errors.append(f"the receipt declares no {family} control")

    comparison = receipt["baseline_comparison"]
    if comparison["baseline_issue"] != "ed3c/noodles#9":
        errors.append("the convergence must be compared against the minimal #9 baseline")
    if tuple(comparison["baseline"]["controls"]) != CONTROLS:
        errors.append("the baseline run did not plant the same boundary controls")
    if comparison["components_added"]:
        errors.append(f"v1 added {comparison['components_added']} over the baseline without admitting them")
    if len(comparison["pinned_externals"]) < 4:
        errors.append("the comparison must name every external the chain is pinned to")

    residue = receipt["residue"]
    if residue["tree_sha256_before"] != residue["tree_sha256_after"] or not residue["tree_unchanged"]:
        errors.append("the convergence run mutated the candidate tree it was measuring")
    if not residue["index_outside_candidate_tree"] or not residue["ledger_outside_candidate_tree"]:
        errors.append("the run wrote its index or its ledger inside the candidate tree")
    return errors


class CodeIntelV1AdmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = CANDIDATE_ROOT
        self.receipt = json.loads((self.root / EVIDENCE_PATH).read_text(encoding="utf-8"))
        self.ledger = dispositions(self.root)
        self.entry = next(
            item
            for item in json.loads((self.root / LEDGER_PATH).read_text(encoding="utf-8"))["capabilities"]
            if item["id"] == CAPABILITY
        )

    def planted(self, mutate: Any) -> dict[str, Any]:
        receipt = copy.deepcopy(self.receipt)
        mutate(receipt)
        return receipt

    def test_positive_control_admits_the_recorded_convergence(self) -> None:
        self.assertEqual(receipt_errors(self.receipt, self.root), [])

    def test_the_ledger_disposition_is_the_verdict_the_numbers_produce(self) -> None:
        self.assertEqual(self.entry["disposition"], verdict(self.receipt, self.ledger))
        self.assertEqual(self.entry["validation_receipt"], EVIDENCE_PATH)
        self.assertIn(EVIDENCE_PATH, self.entry["physical_evidence"])
        self.assertNotIn("next_issue", self.entry)

    def test_the_ledger_records_exactly_the_components_the_rule_excludes(self) -> None:
        excluded = excluded_components(self.receipt, self.ledger)
        recorded = {item["capability"]: item["reasons"] for item in self.entry["not_admitted"]}
        self.assertEqual(recorded, excluded)
        for item in self.entry["not_admitted"]:
            with self.subTest(capability=item["capability"]):
                self.assertTrue((self.root / item["receipt"]).is_file())
                self.assertRegex(item["evidence_issue"], r"^ed3c/noodles#\d+$")

    def test_every_optional_component_is_excluded_on_this_repository(self) -> None:
        # constraint: the honest state of v1 - four validated components, none of them bought.
        declared = {item["ledger_capability"] for item in self.receipt["optional_components"]}
        self.assertEqual(set(excluded_components(self.receipt, self.ledger)), declared)

    def test_the_only_component_with_headroom_is_the_one_that_was_measured_and_lost(self) -> None:
        # constraint: the vector store is the single optional component the corpus leaves a residual
        # constraint: for; it is excluded by its own A/B verdict, not by a missing opportunity.
        excluded = excluded_components(self.receipt, self.ledger)
        store = excluded["lancedb-retrieval-projection"]
        self.assertEqual(store, ["its own capability is 'DROP', not an admitted MIGRATE"])
        for capability in ("scip-semantic-graph", "serena-symbol-navigation"):
            with self.subTest(capability=capability):
                self.assertIn("no structural_refusal residual", excluded[capability][0])

    def test_the_measured_residual_is_selection_not_a_missing_component(self) -> None:
        residual = recomputed_residual(self.receipt)
        self.assertEqual(residual["structural_refusal"], 0)
        self.assertEqual(residual["edit"], 0)
        self.assertGreater(residual["definition_selection"], 0)

    def test_planted_structural_residual_admits_the_navigation_component(self) -> None:
        # constraint: the yes-side of clause two. A corpus the pinned grammar could not resolve would
        # constraint: buy the navigation component a place in v1 on the same rule that excludes it now.
        def refuse(receipt: dict[str, Any]) -> None:
            receipt["tasks"][0].update(
                outcome="refused", diagnostic="planted", exact=False, resolved_path=None, resolved_definition=None
            )

        self.assertEqual(self.ledger["serena-symbol-navigation"], "MIGRATE")
        self.assertNotIn("serena-symbol-navigation", excluded_components(self.planted(refuse), self.ledger))

    def test_planted_store_promotion_admits_the_vector_store(self) -> None:
        promoted = {**self.ledger, "lancedb-retrieval-projection": "MIGRATE"}
        self.assertNotIn("lancedb-retrieval-projection", excluded_components(self.receipt, promoted))

    def test_planted_edge_demotion_drops_the_whole_capability(self) -> None:
        demoted = {**self.ledger, "grepai-candidate-retrieval-law": "REVALIDATE"}
        self.assertEqual(verdict(self.receipt, demoted), "DROP")

    def test_planted_receipt_mutations_are_all_rejected(self) -> None:
        mutations = {
            "fabricated exact resolution": lambda r: r["quality"].update(exact_resolution=17),
            "fabricated residual": lambda r: r["residual"].update(definition_selection=0),
            "fabricated edit residual": lambda r: r["residual"].update(edit=1),
            "fabricated rank": lambda r: r["tasks"][0].update(hit_rank=1),
            "fabricated exact flag": lambda r: r["tasks"][0].update(exact=True),
            "dropped task": lambda r: r["tasks"].pop(),
            "shortened candidate budget": lambda r: r["tasks"][0]["candidates"].pop(),
            "untracked candidate path": lambda r: r["tasks"][0]["candidates"].__setitem__(0, "nowhere.py:1-2"),
            "answer key indexed": lambda r: r["tasks"][0]["candidates"].__setitem__(0, f"{PROBE_PATH}:1-5"),
            "invented definition": lambda r: r["tasks"][0].update(resolved_definition="not_a_declaration_anywhere"),
            "foreign evidence subject": lambda r: r["tasks"][0]["admitted_row"].update(subject="ed3c/noodles#999999"),
            "forged source digest": lambda r: r["tasks"][0]["admitted_row"].update(source_sha256="deadbeef"),
            "silent refusal": lambda r: r["tasks"][0].update(outcome="refused", diagnostic=""),
            "unshared embedder": lambda r: r["providers"]["embedder"]["pinned"].update(model="embeddinggemma"),
            "unread embedder digest": lambda r: r["providers"]["embedder"].update(observed_digest="0" * 64),
            "foreign retrieval binary": lambda r: r["providers"]["retrieval_executable"].update(sha256="0" * 64),
            "empty index": lambda r: r["providers"]["index"].update(index_bytes=0),
            "missing control family": lambda r: r["control_families"].update(residue=""),
            "undeclared component added": lambda r: r["baseline_comparison"].update(components_added=["lancedb"]),
            "baseline controls skipped": lambda r: r["baseline_comparison"]["baseline"].update(controls=[]),
            "tree mutated": lambda r: r["residue"].update(tree_unchanged=False),
            "ledger inside the tree": lambda r: r["residue"].update(ledger_outside_candidate_tree=False),
            "forged subject commit": lambda r: r["subject"].update(commit="not-a-commit"),
            "corpus disowned": lambda r: r["corpus"].update(source="somewhere/else.py:TASKS"),
            "answer key admitted to the corpus": lambda r: r["corpus"].update(excluded_from_corpus=[]),
        }
        for name, mutate in mutations.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(receipt_errors(self.planted(mutate), self.root), [])

    def test_planted_blind_edge_control_fails_the_verdict(self) -> None:
        def blind(receipt: dict[str, Any]) -> None:
            receipt["tasks"][0]["controls"] = ["wrong_subject"]

        self.assertTrue(any("planted controls" in reason for reason in edge_reasons(self.planted(blind), self.ledger)))


if __name__ == "__main__":
    unittest.main()

"""The LanceDB admission decision is derived from the recorded numbers, never asserted next to them.

`migrations/skills-shared/lancedb_ab_probe.py` produces `lancedb-ab-evidence.json` and records only
measurements. This gate owns the predeclared admission rule, recomputes it, and binds the ledger
disposition to the result, so the ledger cannot say `MIGRATE` while the receipt says the store lost
and cannot say `DROP` if a later re-run wins. LanceDB is never installed here.

The rule is deliberately two-sided, and `test_planted_store_win_flips_the_verdict_to_migrate` proves
it: a receipt whose store arm beats both the landed arm and the store-free control admits. What
fails on this repository is quality, not the rule.
"""
from __future__ import annotations

import ast
import copy
import json
import re
import statistics
import unittest
from pathlib import Path
from typing import Any

import noodles
from tests.support import CANDIDATE_ROOT

EVIDENCE_PATH = "migrations/skills-shared/lancedb-ab-evidence.json"
PROBE_PATH = "migrations/skills-shared/lancedb_ab_probe.py"
LEDGER_PATH = "migrations/skills-shared/ledger.json"
RETRIEVAL_LOCK_PATH = "policy/retrieval.lock.json"
CAPABILITY = "lancedb-retrieval-projection"
DISTRIBUTION_PACKAGE = "lancedb"

BASELINE_ARM = "A_grepai"
STORE_ARM = "B_lancedb"
CONTROL_ARM = "B_prime_exhaustive"

HIGHER_IS_BETTER = ("recall_at_k", "mean_reciprocal_rank")
LOWER_IS_BETTER = ("context_bytes_total", "query_latency_ms_median")
NO_REGRESSION = ("recall_at_k", "mean_reciprocal_rank", "context_bytes_total")

HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
EXACT_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
CANDIDATE_RE = re.compile(r"^(?P<path>[^:]+):(?P<start>\d+)-(?P<end>\d+)$")
FLOATING_REFS = frozenset({"latest", "main", "master", "head", "stable", "*", "next"})


def probe_constants(root: Path, probe_path: str = PROBE_PATH) -> dict[str, Any]:
    """Read the producer's own literals without importing it.

    The trusted job runs the default branch's tests against a candidate tree it must never execute,
    so the pins and the task list are parsed, not imported. The path is a parameter because the
    convergence gate reads a second producer's pins the same way.
    """
    module = ast.parse((root / probe_path).read_text(encoding="utf-8"))
    constants: dict[str, Any] = {}
    for node in module.body:
        if not (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id.isupper()):
            continue
        try:
            constants[node.targets[0].id] = ast.literal_eval(node.value)
        except ValueError:
            # constraint: computed module constants such as the resolved repository root are not pins.
            continue
    return constants


def improves(arm: dict[str, Any], baseline: dict[str, Any], metric: str) -> bool:
    if metric in HIGHER_IS_BETTER:
        return arm[metric] > baseline[metric]
    return arm[metric] < baseline[metric]


def admission_reasons(receipt: dict[str, Any]) -> list[str]:
    """The predeclared admission rule for `lancedb-retrieval-projection`.

    A vector store is admitted only when it (1) costs no task-retrieval quality and no extra context
    against the landed path, (2) actually wins something against it, and (3) is itself the reason for
    that win. Clause (3) is the whole point of the store-free control arm: the store arm chunks the
    corpus differently from grepai, so a win measured only against the landed arm could be the
    chunker's. A win the control arm reproduces without any store is not the store's win.
    """
    baseline = receipt["arms"][BASELINE_ARM]
    store = receipt["arms"][STORE_ARM]
    control = receipt["arms"][CONTROL_ARM]
    reasons: list[str] = []
    for metric in NO_REGRESSION:
        if improves(baseline, store, metric):
            reasons.append(f"{metric} regressed against {BASELINE_ARM}: {store[metric]} vs {baseline[metric]}")
    wins = [metric for metric in HIGHER_IS_BETTER + LOWER_IS_BETTER if improves(store, baseline, metric)]
    if not wins:
        reasons.append(f"no predeclared metric improved against {BASELINE_ARM}")
    elif not [metric for metric in wins if improves(store, control, metric)]:
        reasons.append(f"every win against {BASELINE_ARM} is reproduced by {CONTROL_ARM} without the store: {wins}")
    nonsense = store["nonsense_control"]
    if nonsense["absence_proof"] or not nonsense["returns_nearest_neighbours"]:
        reasons.append("the store arm misreports its nonsense control; a miss is still not an absence proof")
    return reasons


def verdict(receipt: dict[str, Any]) -> str:
    return "DROP" if admission_reasons(receipt) else "MIGRATE"


def unique_declaration_file(root: Path, symbol: str) -> str | None:
    """Ground truth re-derived from tracked source by text, so line drift never invalidates it."""
    declaration = f"def {symbol}("
    hits = [
        relative
        for _mode, relative in noodles.tracked_entries(root)
        if relative.endswith(".py") and declaration in (root / relative).read_text(encoding="utf-8", errors="ignore")
    ]
    return hits[0] if len(hits) == 1 else None


def arm_errors(name: str, arm: dict[str, Any], tasks: tuple[Any, ...], top_k: int, tracked: set[str], excluded: tuple[str, ...]) -> list[str]:
    errors: list[str] = []
    declared = [(query, target_path, target_symbol) for query, target_path, target_symbol in tasks]
    recorded = [(task["query"], task["target_path"], task["target_symbol"]) for task in arm["tasks"]]
    if recorded != declared:
        errors.append(f"{name} was not scored on the probe's declared task list in order")
        return errors
    read_back = 0
    for task in arm["tasks"]:
        candidates = task["candidates"]
        read_back += len(candidates)
        if len(candidates) != top_k:
            errors.append(f"{name} spent {len(candidates)} candidates on {task['target_path']}, not the pinned {top_k}")
        paths: list[str] = []
        for candidate in candidates:
            match = CANDIDATE_RE.fullmatch(candidate)
            if match is None:
                errors.append(f"{name} recorded an unreadable candidate {candidate!r}")
                continue
            start, end = int(match["start"]), int(match["end"])
            if start < 1 or end < start:
                errors.append(f"{name} recorded an impossible range in {candidate!r}")
            if match["path"] not in tracked:
                errors.append(f"{name} names {match['path']!r}, which the candidate tree no longer tracks; re-run {PROBE_PATH}")
            if match["path"] in excluded:
                errors.append(f"{name} retrieved the experiment's own file {match['path']!r}, which quotes every task query verbatim")
            paths.append(match["path"])
        expected_rank = paths.index(task["target_path"]) + 1 if task["target_path"] in paths else None
        if task["hit_rank"] != expected_rank:
            errors.append(f"{name} claims hit_rank {task['hit_rank']} for {task['target_path']}, its own candidates say {expected_rank}")
        if task["context_bytes"] <= 0:
            errors.append(f"{name} claims {task['context_bytes']} context bytes for a five-candidate answer")
    hits = [task for task in arm["tasks"] if task["hit_rank"] is not None]
    aggregates = {
        "recall_at_k": round(len(hits) / len(arm["tasks"]), 6),
        "mean_reciprocal_rank": round(sum(1.0 / task["hit_rank"] for task in hits) / len(arm["tasks"]), 6),
        "context_bytes_total": sum(task["context_bytes"] for task in arm["tasks"]),
        "query_latency_ms_median": round(statistics.median(task["latency_ms"] for task in arm["tasks"]), 3),
    }
    for metric, expected in aggregates.items():
        if arm[metric] != expected:
            errors.append(f"{name} reports {metric}={arm[metric]}, its own per-task rows give {expected}")
    nonsense = arm["nonsense_control"]
    if nonsense["candidate_count"] != len(nonsense["candidates"]):
        errors.append(f"{name} nonsense control count disagrees with the candidates it recorded")
    if nonsense["absence_proof"]:
        errors.append(f"{name} nonsense control claims an absence proof")
    if arm["candidates_read_back"] != read_back + len(nonsense["candidates"]):
        errors.append(f"{name} claims {arm['candidates_read_back']} source readbacks for {read_back + len(nonsense['candidates'])} candidates")
    return errors


def receipt_errors(receipt: dict[str, Any], root: Path) -> list[str]:
    """Every number the verdict rests on is recomputed here from the receipt's own rows and from
    tracked source, so a receipt that fabricates an aggregate, a rank, or a pin fails with no tool
    installed and with no network."""
    errors: list[str] = []
    declared = probe_constants(root)
    distribution = receipt["pin"]["distribution"]
    if distribution != declared.get("PIN_DISTRIBUTION"):
        errors.append("receipt pin does not match the pin the probe would actually run under")
    if distribution.get("package") != DISTRIBUTION_PACKAGE:
        errors.append(f"receipt must pin the {DISTRIBUTION_PACKAGE} distribution")
    if not EXACT_VERSION_RE.fullmatch(str(distribution.get("version", ""))):
        errors.append("receipt distribution version is a floating ref, not an exact release")
    if not HEX64_RE.fullmatch(str(distribution.get("wheel_sha256", ""))):
        errors.append("receipt distribution wheel_sha256 is not an exact 64-hex digest")
    if any(str(value).strip().lower() in FLOATING_REFS for value in distribution.values()):
        errors.append(f"receipt distribution contains a floating ref: {distribution}")

    subject = receipt["subject"]
    if subject.get("repository") != "ed3c/noodles" or not HEX40_RE.fullmatch(str(subject.get("commit", ""))):
        errors.append("receipt subject must pin ed3c/noodles at an exact 40-hex commit")

    top_k = receipt["pin"]["top_k"]
    for name, value in (("top_k", top_k), ("chunk_lines", receipt["pin"]["chunk_lines"]), ("chunk_overlap", receipt["pin"]["chunk_overlap"])):
        if value != declared.get(name.upper()):
            errors.append(f"receipt {name}={value} is not the {name.upper()} the probe runs with")

    tasks = declared["TASKS"]
    budget = receipt["budget"]
    if budget["tasks"] != len(tasks):
        errors.append(f"receipt claims {budget['tasks']} tasks against the probe's {len(tasks)}")
    locked = json.loads((root / RETRIEVAL_LOCK_PATH).read_text(encoding="utf-8"))["retrieval"]["embedder"]
    if budget["embedder"] != locked:
        errors.append("the arms did not share the embedder the landed retrieval path is pinned to")
    if budget["corpus_chunks"] < 1 or budget["corpus_files"] < 1:
        errors.append("an empty corpus cannot separate two retrieval paths")
    excluded = tuple(declared.get("EXPERIMENT_ARTIFACTS", ()))
    if tuple(budget.get("excluded_from_corpus", ())) != excluded:
        errors.append(f"the corpus must exclude exactly the experiment's own files: {excluded}")

    for query, target_path, target_symbol in tasks:
        resolved = unique_declaration_file(root, target_symbol)
        if resolved != target_path:
            errors.append(f"ground truth for {query!r} is not a unique {target_symbol} declaration in {target_path}; re-run {PROBE_PATH}")

    if set(receipt["arms"]) != {BASELINE_ARM, STORE_ARM, CONTROL_ARM}:
        errors.append(f"the A/B needs exactly {BASELINE_ARM}, {STORE_ARM} and {CONTROL_ARM}")
        return errors
    tracked = {relative for _mode, relative in noodles.tracked_entries(root)}
    for name, arm in receipt["arms"].items():
        errors.extend(arm_errors(name, arm, tasks, top_k, tracked, excluded))

    if receipt["residue"]["corpus_sha256_after"] != budget["corpus_sha256"] or not receipt["residue"]["corpus_unchanged"]:
        errors.append("the experiment mutated the corpus it was measuring")
    return errors


class LanceDbAdmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = CANDIDATE_ROOT
        self.receipt = json.loads((self.root / EVIDENCE_PATH).read_text(encoding="utf-8"))
        self.entry = next(
            item
            for item in json.loads((self.root / LEDGER_PATH).read_text(encoding="utf-8"))["capabilities"]
            if item["id"] == CAPABILITY
        )

    def planted(self, mutate: Any) -> dict[str, Any]:
        receipt = copy.deepcopy(self.receipt)
        mutate(receipt)
        return receipt

    def test_positive_control_admits_the_recorded_experiment(self) -> None:
        self.assertEqual(receipt_errors(self.receipt, self.root), [])

    def test_the_ledger_disposition_is_the_verdict_the_numbers_produce(self) -> None:
        self.assertEqual(self.entry["disposition"], verdict(self.receipt))
        self.assertEqual(self.entry["validation_receipt"], EVIDENCE_PATH)
        self.assertIn(EVIDENCE_PATH, self.entry["physical_evidence"])
        self.assertNotIn("next_issue", self.entry)

    def test_the_recorded_drop_is_a_quality_and_context_loss_not_a_missing_run(self) -> None:
        reasons = admission_reasons(self.receipt)
        self.assertTrue(any("recall_at_k regressed" in reason for reason in reasons), reasons)
        self.assertTrue(any("context_bytes_total regressed" in reason for reason in reasons), reasons)

    def test_the_store_arm_reproduces_its_ranking_without_the_store(self) -> None:
        # constraint: this is the attribution control - identical quality with and without LanceDB is
        # constraint: what makes the DROP a statement about the store rather than about the chunker.
        store, control = self.receipt["arms"][STORE_ARM], self.receipt["arms"][CONTROL_ARM]
        self.assertEqual(store["recall_at_k"], control["recall_at_k"])
        self.assertEqual(store["mean_reciprocal_rank"], control["mean_reciprocal_rank"])
        self.assertEqual(
            [task["candidates"] for task in store["tasks"]],
            [task["candidates"] for task in control["tasks"]],
        )

    def test_planted_store_win_flips_the_verdict_to_migrate(self) -> None:
        def win(receipt: dict[str, Any]) -> None:
            baseline = receipt["arms"][BASELINE_ARM]
            store = receipt["arms"][STORE_ARM]
            store["recall_at_k"] = baseline["recall_at_k"] + 0.05
            store["mean_reciprocal_rank"] = baseline["mean_reciprocal_rank"] + 0.05
            store["context_bytes_total"] = baseline["context_bytes_total"] - 1
            receipt["arms"][CONTROL_ARM]["recall_at_k"] = baseline["recall_at_k"] - 0.05

        self.assertEqual(verdict(self.planted(win)), "MIGRATE")

    def test_planted_win_the_control_arm_reproduces_stays_dropped(self) -> None:
        def borrowed(receipt: dict[str, Any]) -> None:
            baseline = receipt["arms"][BASELINE_ARM]
            for arm in (receipt["arms"][STORE_ARM], receipt["arms"][CONTROL_ARM]):
                arm["recall_at_k"] = baseline["recall_at_k"] + 0.05
                arm["mean_reciprocal_rank"] = baseline["mean_reciprocal_rank"] + 0.05
                arm["context_bytes_total"] = baseline["context_bytes_total"] - 1
                arm["query_latency_ms_median"] = baseline["query_latency_ms_median"] - 1.0

        planted = self.planted(borrowed)
        self.assertEqual(verdict(planted), "DROP")
        self.assertTrue(any("reproduced by" in reason for reason in admission_reasons(planted)), admission_reasons(planted))

    def test_planted_receipt_mutations_are_all_rejected(self) -> None:
        mutations = {
            "fabricated recall": lambda r: r["arms"][STORE_ARM].update(recall_at_k=1.0),
            "fabricated rank": lambda r: r["arms"][BASELINE_ARM]["tasks"][0].update(hit_rank=1),
            "dropped task": lambda r: r["arms"][STORE_ARM]["tasks"].pop(),
            "shortened candidate budget": lambda r: r["arms"][STORE_ARM]["tasks"][0]["candidates"].pop(),
            "untracked candidate path": lambda r: r["arms"][BASELINE_ARM]["tasks"][0]["candidates"].__setitem__(0, "nowhere.py:1-2"),
            "floating version pin": lambda r: r["pin"]["distribution"].update(version="latest"),
            "forged wheel digest": lambda r: r["pin"]["distribution"].update(wheel_sha256="deadbeef"),
            "forged subject commit": lambda r: r["subject"].update(commit="not-a-commit"),
            "unshared embedder": lambda r: r["budget"]["embedder"].update(model="embeddinggemma"),
            "absence proof claimed": lambda r: r["arms"][STORE_ARM]["nonsense_control"].update(absence_proof=True),
            "readback skipped": lambda r: r["arms"][STORE_ARM].update(candidates_read_back=0),
            "corpus mutated": lambda r: r["residue"].update(corpus_unchanged=False),
            "answer key indexed": lambda r: r["arms"][STORE_ARM]["tasks"][0]["candidates"].__setitem__(0, f"{PROBE_PATH}:1-5"),
            "exclusion dropped": lambda r: r["budget"].update(excluded_from_corpus=[]),
            "arm removed": lambda r: r["arms"].pop(CONTROL_ARM),
        }
        for name, mutate in mutations.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(receipt_errors(self.planted(mutate), self.root), [])


if __name__ == "__main__":
    unittest.main()

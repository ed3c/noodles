#!/usr/bin/env python3
"""What the landed code-intelligence band actually answers, measured on a corpus instead of one task.

Each atom in the band landed its own receipt, and `ed3c/noodles#9` joined three of them into one
refusable chain on a single query. A single query can show that the mechanism refuses a planted
fault; it cannot show how often the chain, running unplanted, serves a *plausible* answer. That is
the only question convergence has to answer, because a component is worth its cost only against a
residual that is actually there.

So this probe re-runs the repository's declared task corpus through the exact chain `#9` landed,
with ground truth attached, and classifies every task the chain does not answer exactly:

  structural_refusal   no candidate resolved to a definition under the pinned grammar
  retrieval_rank       the ground-truth file was never among the candidates
  definition_selection the ground-truth file was reachable, but the chain named another definition

The classes exist because each optional component addresses exactly one of them. A component facing
a zero residual has nothing to buy, whatever its own receipt proved in isolation - and that is a
measurement, not a preference. `tests/test_code_intel_v1.py` owns the admission rule and recomputes
every number here from the rows below, so this file records observations and never a verdict.
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_ROOT = Path(__file__).resolve().parent
for _entry in (str(REPOSITORY_ROOT), str(MIGRATION_ROOT)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

# constraint: imported after the sys.path inserts above so the probe runs from any cwd.
import lancedb_ab_probe
import retrieval_contract

DEFAULT_OUTPUT = MIGRATION_ROOT / "code-intel-v1-evidence.json"
LEDGER_CAPABILITY = "code-intelligence-v1"
SUBJECT_ISSUE = "ed3c/noodles#13"
BASELINE_ISSUE = "ed3c/noodles#9"
SCHEMA_VERSION = 1

# constraint: the corpus is the repository's one declared task set carrying ground truth. It lives in
# constraint: the LanceDB experiment because that experiment declared it first, and reusing it
# constraint: verbatim is the only thing that makes v1's numbers and the dropped store's comparable.
TASKS = lancedb_ab_probe.TASKS

# constraint: anything quoting the task queries verbatim is an answer key; it is stripped from the
# constraint: index root and the gate refuses any candidate naming one.
EXPERIMENT_ARTIFACTS = lancedb_ab_probe.EXPERIMENT_ARTIFACTS + (
    "migrations/skills-shared/code_intel_v1_probe.py",
    "migrations/skills-shared/code-intel-v1-evidence.json",
    "tests/test_code_intel_v1.py",
)

# constraint: every edge the corpus run executes on every task, and the landed atom that proved it.
# constraint: the fourth edge is #9's consuming end, which has no ledger capability of its own.
ADMITTED_EDGES = (
    {
        "edge": "intent query -> candidate paths",
        "ledger_capability": "grepai-candidate-retrieval-law",
        "evidence_issue": "ed3c/noodles#7",
        "landed_pr": 213,
    },
    {
        "edge": "candidate path -> structural definition range",
        "ledger_capability": "tree-sitter-structural-readback",
        "evidence_issue": "ed3c/noodles#6",
        "landed_pr": 214,
    },
    {
        "edge": "structural claim -> exact-subject evidence row",
        "ledger_capability": "sqlite-exact-subject-ledger",
        "evidence_issue": "ed3c/noodles#5",
        "landed_pr": 204,
    },
    {
        "edge": "stored row -> refusable consumer admission",
        "ledger_capability": None,
        "evidence_issue": "ed3c/noodles#9",
        "landed_pr": 232,
    },
)

# constraint: the residual class each optional component would have to reduce, read off its own
# constraint: landed claim rather than off the architecture it came from.
OPTIONAL_COMPONENTS = (
    {
        "ledger_capability": "scip-semantic-graph",
        "evidence_issue": "ed3c/noodles#10",
        "landed_pr": 210,
        "receipt": "migrations/skills-shared/scip-validation.json",
        "addresses": "structural_refusal",
    },
    {
        "ledger_capability": "serena-symbol-navigation",
        "evidence_issue": "ed3c/noodles#8",
        "landed_pr": 216,
        "receipt": "migrations/skills-shared/serena-navigation-evidence.json",
        "addresses": "structural_refusal",
    },
    {
        "ledger_capability": "serena-bounded-edit",
        "evidence_issue": "ed3c/noodles#12",
        "landed_pr": 229,
        "receipt": "migrations/skills-shared/serena-bounded-edit-evidence.json",
        "addresses": "edit",
    },
    {
        "ledger_capability": "lancedb-retrieval-projection",
        "evidence_issue": "ed3c/noodles#11",
        "landed_pr": 231,
        "receipt": "migrations/skills-shared/lancedb-ab-evidence.json",
        "addresses": "retrieval_rank",
    },
)

# constraint: `edit` can only ever be zero here: v1's chain never writes, and the residue control
# constraint: proves it. It is still declared so a component addressing it is refused by a number.
RESIDUAL_CLASSES = ("structural_refusal", "retrieval_rank", "definition_selection", "edit")

CONTROL_FAMILIES = {
    "positive": "every admitted task serves its row back out of the ledger and reads it from source",
    "boundary_fault": "wrong_subject, wrong_adapter, wrong_path and wrong_range are planted per task",
    "stale_data": "stale_source renames the definition in place, so only the digest moves",
    "source_provider_readback": "pinned grepai digest, pinned embedder digest, pinned parser, and a "
    "direct source re-read behind every served byte range",
    "residue": "the candidate tree is digested before and after the whole corpus, and every ledger "
    "is opened outside it",
}

NON_CLAIMS = (
    "No universal language coverage: the pinned grammar covers .py, and a candidate the grammar "
    "cannot parse is a bounded refusal, never an absence proof.",
    "No production scale: one repository, one corpus, one embedder, one top-5 budget.",
    "Exact-symbol resolution is a P-class measurement of the chain's ceiling, not a correctness "
    "guarantee the chain offers; the chain's admitted authority stays candidate-only.",
    "A component is not admitted because it appears in the original architecture, and not excluded "
    "because it failed - only because the corpus leaves it nothing to reduce, or its own capability "
    "was never promoted.",
)


class ProbeError(RuntimeError):
    """Bounded failure: a run that cannot execute is reported, never silently scored as a miss."""


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=str(root), text=True, capture_output=True, check=True)
    return result.stdout.strip()


def embedder_readback(pin: dict[str, Any], endpoint: str) -> dict[str, Any]:
    """The gap the binary digest alone leaves open.

    `verify_pinned_executable` proves which grepai ran; it says nothing about which model built the
    index that grepai searched. A different embedder produces a different ranking and every number
    below would move without one pin noticing, so the serving model's digest is read back live.
    """
    pinned = dict(pin["embedder"])
    try:
        with urllib.request.urlopen(f"{endpoint.rstrip('/')}/api/tags", timeout=10) as response:
            models = json.loads(response.read().decode("utf-8"))["models"]
    except (urllib.error.URLError, OSError, KeyError, ValueError) as exc:
        raise ProbeError(f"pinned embedder {pinned['model']!r} could not be read back at {endpoint}: {exc}") from exc
    observed = [item for item in models if str(item.get("name", "")).split(":")[0] == pinned["model"]]
    if len(observed) != 1:
        raise ProbeError(f"{endpoint} serves {len(observed)} models named {pinned['model']!r}; the pin is ambiguous")
    digest = str(observed[0].get("digest", ""))
    if digest != pinned["digest"]:
        raise ProbeError(f"embedder {pinned['model']!r} serves digest {digest} != pinned {pinned['digest']}")
    return {"pinned": pinned, "observed_digest": digest, "observed_name": observed[0]["name"], "matches": True}


def residual_class(row: dict[str, Any]) -> str | None:
    """Where a task that was not answered exactly actually broke."""
    if row["outcome"] != "admitted":
        return "structural_refusal"
    if row["exact"]:
        return None
    if row["hit_rank"] is None:
        return "retrieval_rank"
    return "definition_selection"


def run_task(root: Path, search: Any, task: tuple[str, str, str], subject: str) -> dict[str, Any]:
    """One corpus task through the exact chain `#9` landed, planted controls and all.

    The controls are re-planted on every task rather than once for the run. They are cheap, and a
    control that only ever ran against one query would leave every other row's admission resting on
    an assumption instead of on a refusal that was actually observed.
    """
    query, target_path, target_symbol = task
    seen: dict[str, str] = {}

    def capture(intent: str) -> str:
        seen["stdout"] = search(intent)
        return seen["stdout"]

    started = time.perf_counter()
    try:
        journey = retrieval_contract.code_intel_journey(root, capture, subject, query=query, error_cls=ProbeError)
        refusal = None
    except ProbeError as failure:
        journey, refusal = None, str(failure)
    elapsed = round((time.perf_counter() - started) * 1000.0, 3)

    candidates = retrieval_contract.parse_candidates(seen.get("stdout", "[]"), error_cls=ProbeError)
    paths = [item["path"] for item in candidates]
    row: dict[str, Any] = {
        "query": query,
        "target_path": target_path,
        "target_symbol": target_symbol,
        "candidates": [f"{item['path']}:{item['start_line']}-{item['end_line']}" for item in candidates],
        "hit_rank": paths.index(target_path) + 1 if target_path in paths else None,
        "chain_latency_ms": elapsed,
    }
    if journey is None:
        row.update(
            outcome="refused",
            diagnostic=refusal,
            resolved_path=None,
            resolved_definition=None,
            exact=False,
            controls=[],
        )
        return row

    claim = journey["chain"]["structural"]["claim"]
    admitted = journey["chain"]["admitted"]
    row.update(
        outcome="admitted",
        diagnostic=None,
        resolved_path=claim["path"],
        resolved_definition=claim["definition"],
        exact=claim["path"] == target_path and claim["definition"] == target_symbol,
        controls=[control["control"] for control in journey["controls"]],
        admitted_row={
            "subject": admitted["subject"],
            "adapter": admitted["adapter"],
            "source_sha256": admitted["source_sha256"],
            "path": admitted["path"],
            "definition": admitted["definition"],
            "range": admitted["range"],
        },
        context_bytes=journey["metrics"]["context_bytes"],
        retrieval_ms=journey["metrics"]["retrieval_ms"],
        structural_ms=journey["metrics"]["structural_ms"],
        ledger_ms=journey["metrics"]["ledger_ms"],
        evidence_sha256=journey["metrics"]["evidence_sha256"],
    )
    return row


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    admitted = [row for row in rows if row["outcome"] == "admitted"]
    hits = [row for row in rows if row["hit_rank"] is not None]
    exact = [row for row in admitted if row["exact"]]
    return {
        "tasks": len(rows),
        "admitted_rows": len(admitted),
        "refusals": len(rows) - len(admitted),
        "recall_at_k": round(len(hits) / len(rows), 6),
        "path_resolution": len([row for row in admitted if row["resolved_path"] == row["target_path"]]),
        "exact_resolution": len(exact),
        "exact_resolution_rate": round(len(exact) / len(rows), 6),
        "context_bytes_total": sum(row["context_bytes"] for row in admitted),
        "retrieval_ms_median": round(statistics.median([row["retrieval_ms"] for row in admitted]), 3) if admitted else None,
        "chain_ms_median": round(statistics.median([row["chain_latency_ms"] for row in rows]), 3),
    }


def residual_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {name: 0 for name in RESIDUAL_CLASSES}
    for row in rows:
        name = residual_class(row)
        if name is not None:
            counts[name] += 1
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Code-intelligence v1 convergence over the declared task corpus")
    parser.add_argument("--index-root", required=True, help="grepai index root; must stay outside the candidate tree")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    args = parser.parse_args(argv)

    root = REPOSITORY_ROOT.resolve()
    index_root = Path(args.index_root).resolve()
    if index_root == root or root in index_root.parents:
        raise ProbeError("the index root must stay outside the candidate tree to keep the candidate residue-free")

    pin = retrieval_contract.load_retrieval_pin(root, error_cls=ProbeError)
    providers = {
        "retrieval_executable": retrieval_contract.verify_pinned_executable(pin, error_cls=ProbeError),
        "index": {"index_bytes": retrieval_contract.require_index(index_root, error_cls=ProbeError)["index_bytes"]},
        "embedder": embedder_readback(pin, args.endpoint),
    }
    search = retrieval_contract.pinned_search(pin, str(index_root), error_cls=ProbeError)

    before_digest, _ = retrieval_contract._tree_digest(root)
    baseline = retrieval_contract.code_intel_journey(
        root, search, retrieval_contract.CANARY_SUBJECT, error_cls=ProbeError
    )
    providers["parser"] = baseline["chain"]["structural"]["parser"]
    rows = [run_task(root, search, task, SUBJECT_ISSUE) for task in TASKS]
    after_digest, _ = retrieval_contract._tree_digest(root)

    quality = aggregate(rows)
    residual = residual_counts(rows)
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "capability": LEDGER_CAPABILITY,
        "authority": retrieval_contract.AUTHORITY,
        "laws": list(retrieval_contract.LAWS),
        "subject": {
            "repository": "ed3c/noodles",
            "commit": git(root, "rev-parse", "HEAD"),
            "tree": git(root, "rev-parse", "HEAD^{tree}"),
            "issue": SUBJECT_ISSUE,
        },
        "admitted_edges": [dict(edge) for edge in ADMITTED_EDGES],
        "optional_components": [dict(component) for component in OPTIONAL_COMPONENTS],
        "corpus": {
            "source": "migrations/skills-shared/lancedb_ab_probe.py:TASKS",
            "tasks": len(TASKS),
            "top_k": lancedb_ab_probe.TOP_K,
            "excluded_from_corpus": list(EXPERIMENT_ARTIFACTS),
        },
        "providers": providers,
        "control_families": dict(CONTROL_FAMILIES),
        "tasks": rows,
        "quality": quality,
        "residual": residual,
        "baseline_comparison": {
            "baseline_issue": BASELINE_ISSUE,
            "baseline": {
                "query": baseline["chain"]["intent_query"]["query"],
                "tasks": 1,
                "ground_truth": False,
                "context_bytes": baseline["metrics"]["context_bytes"],
                "retrieval_ms": baseline["metrics"]["retrieval_ms"],
                "controls": [control["control"] for control in baseline["controls"]],
            },
            "converged": {
                "tasks": quality["tasks"],
                "ground_truth": True,
                "context_bytes_total": quality["context_bytes_total"],
                "retrieval_ms_median": quality["retrieval_ms_median"],
                "exact_resolution_rate": quality["exact_resolution_rate"],
            },
            # constraint: the convergence result itself - v1 executes the same four pinned externals
            # constraint: and the same three modules as #9, so nothing was added to buy the corpus.
            "components_added": [],
            "pinned_externals": [
                providers["retrieval_executable"]["version_stdout"],
                f"{providers['embedder']['pinned']['model']}@{providers['embedder']['observed_digest']}",
                f"{providers['parser']['library']['distribution']}@{providers['parser']['library']['version']}",
                f"{providers['parser']['grammar']['distribution']}@{providers['parser']['grammar']['version']}",
            ],
        },
        "residue": {
            "tree_sha256_before": before_digest,
            "tree_sha256_after": after_digest,
            "tree_unchanged": before_digest == after_digest,
            "index_outside_candidate_tree": True,
            "ledger_outside_candidate_tree": True,
        },
        "non_claims": list(NON_CLAIMS),
    }
    Path(args.output).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"quality": quality, "residual": residual, "output": args.output}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Same-task A/B measurement for the `lancedb-retrieval-projection` ledger entry (EXP-LANCEDB-01).

LanceDB is not a repository dependency and `tests/run.sh` never imports it. This probe is the
producer of `lancedb-ab-evidence.json`; `tests/test_lancedb_ab.py` is the gate that owns the
predeclared admission rule, recomputes every aggregate from the rows below it, and re-derives each
task's ground truth from tracked source, so a fabricated receipt fails locally with no tool installed.

Three arms run over one corpus, one embed model, and one top-k budget:

    A   the landed path - `retrieval_contract`'s pinned grepai argv against an out-of-tree index,
        then direct source readback. That contract, not ed3c/noodles#9's wider canary chain, is what
        exists to be beaten; #9 had not landed when this ran and its absence cannot flatter B.
    B   the same corpus and the same pinned ollama embedder projected into a LanceDB table.
    B'  the same chunks and the same vectors as B, ranked by exhaustive cosine with no LanceDB.

B' exists because "B beats A" cannot by itself admit a vector store: A and B differ in chunker and
in scoring boosts as well as in storage. B' holds the chunks, the vectors, and the metric fixed and
removes only LanceDB, so whatever separates B from B' is the store's own contribution and nothing
else. Without that control the experiment could only ever measure the chunker.

Run it with an interpreter that has the pinned lancedb installed, against an index root built by
`grepai watch` on an export of the exact candidate commit:

    python3 -m venv /tmp/lancedb-venv
    /tmp/lancedb-venv/bin/pip install lancedb==0.37.1
    /tmp/lancedb-venv/bin/python migrations/skills-shared/lancedb_ab_probe.py --index-root /tmp/abindex
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

# constraint: imported after the sys.path insert above so the probe runs from any cwd.
import noodles
import retrieval_contract

DEFAULT_OUTPUT = Path(__file__).resolve().parent / "lancedb-ab-evidence.json"

# constraint: exact custody pin for the external store. LanceDB is deliberately absent from
# constraint: policy/providers.lock.json: that lock drives provider_sync checkouts under
# constraint: .noodle/providers and its enabled set is a closed allowlist, so an entry there would be
# constraint: an inert fake provider. The pin lives with the evidence it authorises instead, and
# constraint: tests/test_lancedb_ab.py rejects any floating ref recorded here.
PIN_DISTRIBUTION = {
    "index": "https://pypi.org/simple",
    "package": "lancedb",
    "version": "0.37.1",
    "platform": "macosx_11_0_arm64",
    "wheel_sha256": "c15c46f23cf6959c79fb93cdba2c76536cf784d3134386662da03dc6ccac3c26",
}

# constraint: the budget both arms spend. Changing it changes every recorded number, so it is a pin.
TOP_K = 5
CHUNK_LINES = 60
CHUNK_OVERLAP = 15
MAX_CHUNK_CHARS = 4000
EMBED_BATCH = 32
CORPUS_SUFFIXES = (".py", ".md", ".json", ".sh", ".toml", ".yml", ".yaml")

# constraint: the experiment's own files quote every task query verbatim, so leaving them in the
# constraint: corpus would let both arms retrieve the answer key and spend real candidate slots on it.
# constraint: They are removed from the index root as well; the gate refuses any candidate naming one.
EXPERIMENT_ARTIFACTS = (
    "migrations/skills-shared/lancedb_ab_probe.py",
    "migrations/skills-shared/lancedb-ab-evidence.json",
    "tests/test_lancedb_ab.py",
)

# constraint: the intent set is declared before any arm runs and covers every non-test module once,
# constraint: so no arm can be helped by a hand-picked subset. Ground truth is the file holding a
# constraint: declaration that occurs exactly once across tracked source; the gate re-derives that
# constraint: uniqueness from the candidate tree instead of trusting the receipt.
TASKS = (
    ("reject a pull request whose head commit is not the exact verified candidate", "noodles.py", "verify_pull_request"),
    ("audit the live GitHub branch protection settings against the required policy", "github_protection.py", "protection_audit"),
    ("read the exact source bytes back for a retrieval candidate line range", "retrieval_contract.py", "readback_candidate"),
    ("reject a tree-sitter grammar pin that is not an exact version", "structural_contract.py", "validate_parser_lock"),
    ("rebuild the sqlite evidence database from its recorded rows", "evidence_ledger.py", "rebuild"),
    ("refuse to start a second daemon while a live lease already exists", "daemon_lease.py", "reject_existing_lease"),
    ("parse the declared dependency subjects out of an issue body", "issue_contract.py", "parse_dependencies"),
    ("release execute claims whose owning session is no longer alive", "claim_contract.py", "sweep_dead_claims"),
    ("pick the pinned release asset for this operating system and architecture", "runtime_contract.py", "resolve_platform_key"),
    ("check the agent document route stays within the allowed number of hops", "skill_contract.py", "validate_agent_document_route"),
    ("check the codex agent configuration is isolated from the user's own config", "codex_isolation.py", "validate_codex_agent_config"),
    ("reproduce the trusted CI verification locally before pushing", "trusted_preview.py", "preview_trusted_verify"),
    ("validate the admission digests recorded for an external skill", "provider_contract.py", "validate_admission_policy"),
    ("find the open pull request that belongs to an exact issue subject", "repair_contract.py", "find_open_pr_for_subject"),
    ("build a scip index for the repository at an exact commit", "scip_validation.py", "build_index"),
    ("decide whether a backlog subject can be scheduled now", "schedule_domain.py", "schedule_decision"),
    ("run the baseline acceptance gate that binds the candidate head to the tests", "feature_contract.py", "verify_acceptance"),
)


class ProbeError(RuntimeError):
    """Bounded failure: an arm that cannot run is reported, never silently scored as a miss."""


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=str(root), text=True, capture_output=True, check=True)
    return result.stdout.rstrip("\n")


def corpus_files(root: Path, index_root: Path) -> list[str]:
    """Files both arms can actually see.

    A's index is built on an export of the candidate commit, so a file that the candidate tree has
    changed or added since the export exists for B and not for A. Scoring such a file would credit B
    for a corpus A was never offered, so byte-identity between the two trees is the membership test.
    """
    shared: list[str] = []
    for _mode, relative in noodles.tracked_entries(root):
        if not relative.endswith(CORPUS_SUFFIXES) or relative in EXPERIMENT_ARTIFACTS:
            continue
        candidate, exported = root / relative, index_root / relative
        if not candidate.is_file() or not exported.is_file():
            continue
        if candidate.read_bytes() == exported.read_bytes():
            shared.append(relative)
    return sorted(shared)


def corpus_digest(root: Path, relatives: list[str]) -> str:
    entries = [f"{name}:{hashlib.sha256((root / name).read_bytes()).hexdigest()}" for name in relatives]
    return hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()


def chunk_corpus(root: Path, relatives: list[str]) -> list[dict[str, Any]]:
    """Overlapping line windows, capped by a character budget as well as a line count.

    The line cap alone is not enough: a 60-line prose window in `docs/` reaches ~14k characters and
    the embedder answers `400 the input length exceeds the context length`, which would silently
    become a missing chunk rather than a measurement. The character cap keeps every window inside the
    model's context, so no arm scores a file the embedder never actually saw.
    """
    chunks: list[dict[str, Any]] = []
    for relative in relatives:
        lines = (root / relative).read_text(encoding="utf-8", errors="strict").splitlines()
        start = 0
        while start < len(lines):
            end, size = start, 0
            while end < len(lines) and end - start < CHUNK_LINES and size + len(lines[end]) + 1 <= MAX_CHUNK_CHARS:
                size += len(lines[end]) + 1
                end += 1
            # constraint: a single line wider than the budget still has to become one chunk, or the
            # constraint: file after it would never be indexed at all.
            end = max(end, start + 1)
            chunks.append(
                {
                    "path": relative,
                    "start_line": start + 1,
                    "end_line": end,
                    "text": "\n".join(lines[start:end])[:MAX_CHUNK_CHARS],
                }
            )
            if end >= len(lines):
                break
            start = max(end - CHUNK_OVERLAP, start + 1)
    return chunks


def embed(model: str, inputs: list[str], endpoint: str) -> list[list[float]]:
    # constraint: the embed endpoint answers 400 to an oversized body, so batching is correctness,
    # constraint: not tuning; a short count is raised rather than zipped into misaligned vectors.
    vectors: list[list[float]] = []
    for offset in range(0, len(inputs), EMBED_BATCH):
        batch = inputs[offset : offset + EMBED_BATCH]
        request = urllib.request.Request(
            f"{endpoint}/api/embed",
            data=json.dumps({"model": model, "input": batch}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=600) as response:
            payload = json.loads(response.read().decode("utf-8"))
        returned = payload.get("embeddings")
        if not isinstance(returned, list) or len(returned) != len(batch):
            raise ProbeError(f"embedder returned {type(returned).__name__} for {len(batch)} inputs")
        vectors.extend([float(value) for value in vector] for vector in returned)
    return vectors


def unit(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        raise ProbeError("embedder returned a zero vector, which has no direction to rank by")
    return [value / norm for value in vector]


def scored(root: Path, ranked: list[tuple[dict[str, Any], float]]) -> list[dict[str, Any]]:
    """Every arm ends in the same direct source readback: a rank is never source truth."""
    return [
        retrieval_contract.readback_candidate(
            root,
            {"path": chunk["path"], "start_line": chunk["start_line"], "end_line": chunk["end_line"], "score": score},
            error_cls=ProbeError,
        )
        for chunk, score in ranked
    ]


def arm_result(per_task: list[dict[str, Any]], nonsense: list[dict[str, Any]]) -> dict[str, Any]:
    hits = [task for task in per_task if task["hit_rank"] is not None]
    return {
        "tasks": per_task,
        # constraint: every candidate in this arm went through retrieval_contract.readback_candidate,
        # constraint: which raises on a path or range the candidate tree cannot produce. An arm that
        # constraint: skipped source readback could not have reached this count.
        "candidates_read_back": sum(len(task["candidates"]) for task in per_task) + len(nonsense),
        "recall_at_k": round(len(hits) / len(per_task), 6),
        "mean_reciprocal_rank": round(sum(1.0 / task["hit_rank"] for task in hits) / len(per_task), 6),
        "context_bytes_total": sum(task["context_bytes"] for task in per_task),
        "query_latency_ms_median": round(statistics.median(task["latency_ms"] for task in per_task), 3),
        "nonsense_control": {
            "candidate_count": len(nonsense),
            "returns_nearest_neighbours": bool(nonsense),
            "absence_proof": False,
            "candidates": [f"{item['path']}:{item['start_line']}-{item['end_line']}" for item in nonsense],
        },
    }


def run_task(task: tuple[str, str, str], search: Any) -> dict[str, Any]:
    """Record each candidate as `path:start-end` only.

    Every per-candidate byte count the receipt could carry is a number the gate would have to take on
    trust. Recording the range alone forces the gate to re-read the candidate tree to recompute
    `context_bytes`, so a receipt that overstates or understates the context it spent fails.
    """
    query, target_path, target_symbol = task
    started = time.perf_counter()
    candidates = search(query)
    latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
    paths = [candidate["path"] for candidate in candidates]
    return {
        "query": query,
        "target_path": target_path,
        "target_symbol": target_symbol,
        "hit_rank": paths.index(target_path) + 1 if target_path in paths else None,
        "context_bytes": sum(candidate["source_bytes"] for candidate in candidates),
        "latency_ms": latency_ms,
        "candidates": [f"{item['path']}:{item['start_line']}-{item['end_line']}" for item in candidates],
    }


def arm_a(root: Path, index_root: Path, pin: dict[str, Any]) -> dict[str, Any]:
    """The landed path exactly as `./noodles retrieval probe` runs it."""
    executable = retrieval_contract.verify_pinned_executable(pin, error_cls=ProbeError)
    index = retrieval_contract.require_index(index_root, error_cls=ProbeError)

    def search(query: str) -> list[dict[str, Any]]:
        result = subprocess.run(
            retrieval_contract.pinned_argv(pin, query),
            cwd=str(index_root),
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise ProbeError(f"pinned retrieval argv failed: {result.stderr.strip() or result.stdout.strip()}")
        candidates = retrieval_contract.parse_candidates(result.stdout, error_cls=ProbeError)
        return [retrieval_contract.readback_candidate(root, item, error_cls=ProbeError) for item in candidates]

    per_task = [run_task(task, search) for task in TASKS]
    result = arm_result(per_task, search(pin["control"]["nonsense_query"]))
    result["executable"] = executable
    result["storage_bytes"] = index["index_bytes"]
    result["build_seconds"] = None
    return result


def rank_exhaustive(chunks: list[dict[str, Any]], vectors: list[list[float]], query: list[float]) -> list[tuple[dict[str, Any], float]]:
    scores = sorted(
        ((chunk, sum(a * b for a, b in zip(vector, query))) for chunk, vector in zip(chunks, vectors)),
        key=lambda item: item[1],
        reverse=True,
    )
    return scores[:TOP_K]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Same-task A/B for the LanceDB admission decision")
    parser.add_argument("--index-root", required=True, help="grepai index root; must stay outside the candidate tree")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    args = parser.parse_args(argv)

    root = REPOSITORY_ROOT.resolve()
    index_root = Path(args.index_root).resolve()
    if index_root == root or root in index_root.parents:
        raise ProbeError("the index root must stay outside the candidate tree to keep the candidate residue-free")

    import lancedb  # constraint: imported here so the pure gate never needs the store installed.

    if lancedb.__version__ != PIN_DISTRIBUTION["version"]:
        raise ProbeError(f"installed lancedb {lancedb.__version__} != pinned {PIN_DISTRIBUTION['version']}")

    pin = retrieval_contract.load_retrieval_pin(root, error_cls=ProbeError)
    model = pin["embedder"]["model"]
    relatives = corpus_files(root, index_root)
    chunks = chunk_corpus(root, relatives)
    before_digest = corpus_digest(root, relatives)

    arms: dict[str, Any] = {"A_grepai": arm_a(root, index_root, pin)}

    embed_started = time.perf_counter()
    vectors = [unit(vector) for vector in embed(model, [chunk["text"] for chunk in chunks], args.endpoint)]
    embed_seconds = round(time.perf_counter() - embed_started, 3)
    queries = {
        text: unit(vector)
        for text, vector in zip(
            [task[0] for task in TASKS] + [pin["control"]["nonsense_query"]],
            embed(
                model,
                [task[0] for task in TASKS] + [pin["control"]["nonsense_query"]],
                args.endpoint,
            ),
        )
    }

    store = tempfile.TemporaryDirectory(prefix="noodles-lancedb-ab-")
    try:
        store_started = time.perf_counter()
        database = lancedb.connect(store.name)
        table = database.create_table(
            "corpus",
            data=[
                {"vector": vector, "path": chunk["path"], "start_line": chunk["start_line"], "end_line": chunk["end_line"]}
                for chunk, vector in zip(chunks, vectors)
            ],
        )
        store_seconds = round(time.perf_counter() - store_started, 3)

        def lance_search(query: str) -> list[dict[str, Any]]:
            rows = table.search(queries[query]).metric("cosine").limit(TOP_K).to_list()
            return scored(root, [({"path": row["path"], "start_line": row["start_line"], "end_line": row["end_line"]}, 1.0 - float(row["_distance"])) for row in rows])

        def exhaustive_search(query: str) -> list[dict[str, Any]]:
            return scored(root, rank_exhaustive(chunks, vectors, queries[query]))

        lance_tasks = [run_task(task, lance_search) for task in TASKS]
        lance_nonsense = lance_search(pin["control"]["nonsense_query"])
        exhaustive_tasks = [run_task(task, exhaustive_search) for task in TASKS]
        exhaustive_nonsense = exhaustive_search(pin["control"]["nonsense_query"])
        storage_bytes = sum(path.stat().st_size for path in Path(store.name).rglob("*") if path.is_file())
    finally:
        store.cleanup()

    arms["B_lancedb"] = arm_result(lance_tasks, lance_nonsense)
    arms["B_lancedb"]["storage_bytes"] = storage_bytes
    arms["B_lancedb"]["build_seconds"] = round(embed_seconds + store_seconds, 3)
    arms["B_prime_exhaustive"] = arm_result(exhaustive_tasks, exhaustive_nonsense)
    arms["B_prime_exhaustive"]["storage_bytes"] = 0
    arms["B_prime_exhaustive"]["build_seconds"] = embed_seconds

    after_digest = corpus_digest(root, relatives)
    receipt = {
        "schema_version": 1,
        "experiment": "EXP-LANCEDB-01",
        "authority": "P",
        "subject": {"repository": "ed3c/noodles", "commit": git(root, "rev-parse", "HEAD")},
        "pin": {"distribution": dict(PIN_DISTRIBUTION), "top_k": TOP_K, "chunk_lines": CHUNK_LINES, "chunk_overlap": CHUNK_OVERLAP},
        "budget": {
            "embedder": dict(pin["embedder"]),
            "corpus_files": len(relatives),
            "corpus_chunks": len(chunks),
            "corpus_sha256": before_digest,
            "excluded_from_corpus": list(EXPERIMENT_ARTIFACTS),
            "tasks": len(TASKS),
        },
        "arms": arms,
        "runtime_cost": {
            "forbidden_dependency_manifests": sorted(json.loads((root / "policy/fitness.json").read_text(encoding="utf-8"))["forbidden_dependency_manifests"]),
            "tracked_dependency_manifests": sorted(
                relative
                for _mode, relative in noodles.tracked_entries(root)
                if Path(relative).name in set(json.loads((root / "policy/fitness.json").read_text(encoding="utf-8"))["forbidden_dependency_manifests"])
            ),
            "lancedb_import_path": "external interpreter only; never importable from the candidate tree",
        },
        "residue": {"corpus_sha256_after": after_digest, "corpus_unchanged": after_digest == before_digest},
    }
    Path(args.output).write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

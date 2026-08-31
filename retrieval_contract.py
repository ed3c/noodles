"""GrepAI enters noodles only as a low-authority candidate generator.

The whole admitted contract is `query -> candidate paths -> direct source readback`. Three physical
observations on grepai 0.30.0 force this shape:

1. `grepai search --json` returns `[]` with exit 0 when the index is empty, which is byte-identical to
   a genuine no-match. A miss therefore proves nothing unless a positive control in the same run
   returned readable candidates.
2. A nonsense query returns nearest neighbours, and on this repository it scored them *higher* than
   the real query's best hit. A hit is a similarity rank, never source truth.
3. Returned chunk text is a re-wrapped fragment that can start mid-word, so only the path and line
   range are usable; the bytes must be read back from the candidate tree.

`--compact` is pinned into the argv so the tool cannot even hand back content to be trusted.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

LOCK_PATH = "policy/retrieval.lock.json"
EVIDENCE_PATH = ".noodle/retrieval-evidence.json"
INDEX_DIRNAME = ".grepai"
INDEX_FILENAME = "index.gob"
AUTHORITY = "P"
QUERY_PLACEHOLDER = "{query}"
LAWS = (
    "hit != source truth",
    "miss != absence",
    "result authority is candidate-only",
)
NON_CLAIMS = (
    "no semantic correctness",
    "no absence proof",
    "no edit authority",
    "no full causal pipeline",
)
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
FLOATING_REFS = frozenset({"latest", "main", "master", "head", "stable", "*", "@latest", "next"})
# constraint: .grepai stays out of this skip set because an index planted in the candidate tree is the exact residue the digest exists to catch.
RESIDUE_SKIP_DIRS = frozenset({".git", ".noodle"})


def validate_retrieval_lock(root: Path) -> list[str]:
    """Deterministic pin gate: runs with no tool, no index, and no network, so a floating pin fails
    on every host including CI where grepai is absent."""
    path = Path(root) / LOCK_PATH
    if not path.exists():
        return [f"missing {LOCK_PATH}"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        retrieval = payload["retrieval"]
        argv = retrieval["argv"]
        embedder = retrieval["embedder"]
        control = retrieval["control"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        return [f"invalid retrieval lock: {exc}"]
    errors: list[str] = []
    if payload.get("schema_version") != 1:
        errors.append(f"unsupported retrieval lock schema: {payload.get('schema_version')!r}")
    command = str(retrieval.get("command", ""))
    version = str(retrieval.get("version", ""))
    if not command.strip():
        errors.append("retrieval command is required")
    if not SEMVER_RE.fullmatch(version):
        errors.append(f"retrieval version must be an exact semver, got {version!r}")
    if not HEX64_RE.fullmatch(str(retrieval.get("binary_sha256", ""))):
        errors.append("retrieval binary_sha256 must be a 64-hex sha256")
    if retrieval.get("authority") != AUTHORITY:
        errors.append(f"retrieval authority must be {AUTHORITY!r}; candidate generation never gates or lands")
    errors.extend(_argv_errors("argv", argv, command, require_query=True))
    errors.extend(_argv_errors("version_argv", retrieval.get("version_argv"), command, require_query=False))
    errors.extend(_embedder_errors(embedder))
    errors.extend(_control_errors(control))
    return errors


def _argv_errors(field: str, argv: Any, command: str, *, require_query: bool) -> list[str]:
    if not isinstance(argv, list) or not argv or not all(isinstance(token, str) for token in argv):
        return [f"retrieval {field} must be a non-empty list of exact string tokens"]
    errors: list[str] = []
    if argv[0] != command:
        errors.append(f"retrieval {field}[0] must be the pinned command {command!r}, got {argv[0]!r}")
    for token in argv:
        if token.strip().lower() in FLOATING_REFS:
            errors.append(f"retrieval {field} contains floating ref {token!r}")
    placeholders = [token for token in argv if QUERY_PLACEHOLDER in token]
    if require_query and len(placeholders) != 1:
        errors.append(f"retrieval {field} must contain exactly one {QUERY_PLACEHOLDER} token")
    if not require_query and placeholders:
        errors.append(f"retrieval {field} must not contain {QUERY_PLACEHOLDER}")
    return errors


def _embedder_errors(embedder: Any) -> list[str]:
    if not isinstance(embedder, dict):
        return ["retrieval embedder must be an object"]
    errors: list[str] = []
    if not str(embedder.get("provider", "")).strip():
        errors.append("retrieval embedder provider is required")
    model = str(embedder.get("model", ""))
    if not model.strip() or model.strip().lower() in FLOATING_REFS:
        errors.append(f"retrieval embedder model must be an exact model name, got {model!r}")
    if not HEX64_RE.fullmatch(str(embedder.get("digest", ""))):
        errors.append("retrieval embedder digest must be a 64-hex digest; a different embed model changes every candidate set")
    return errors


def _control_errors(control: Any) -> list[str]:
    if not isinstance(control, dict):
        return ["retrieval control must be an object"]
    positive = str(control.get("positive_query", "")).strip()
    nonsense = str(control.get("nonsense_query", "")).strip()
    errors: list[str] = []
    if not positive:
        errors.append("retrieval control positive_query is required")
    if not nonsense:
        errors.append("retrieval control nonsense_query is required")
    if positive and positive == nonsense:
        errors.append("retrieval control nonsense_query must differ from positive_query")
    return errors


def load_retrieval_pin(root: Path, *, error_cls: type[Exception]) -> dict[str, Any]:
    errors = validate_retrieval_lock(root)
    if errors:
        raise error_cls("; ".join(errors))
    payload = json.loads((Path(root) / LOCK_PATH).read_text(encoding="utf-8"))
    return payload["retrieval"]


def pinned_argv(pin: dict[str, Any], query: str) -> list[str]:
    return [token.replace(QUERY_PLACEHOLDER, query) for token in pin["argv"]]


def parse_candidates(stdout: str, *, error_cls: type[Exception]) -> tuple[dict[str, Any], ...]:
    """grepai reports some failures as an exit-zero JSON object carrying an `error` key, so the wire
    shape - not the return code - decides admission."""
    try:
        payload = json.loads(stdout or "")
    except json.JSONDecodeError as exc:
        raise error_cls(f"retrieval produced unreadable candidate output: {exc}") from exc
    if isinstance(payload, dict):
        raise error_cls(f"retrieval reported a failure instead of candidates: {payload.get('error', payload)!r}")
    if not isinstance(payload, list):
        raise error_cls(f"retrieval candidate output must be a JSON array, got {type(payload).__name__}")
    candidates: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise error_cls("retrieval candidate entry must be an object")
        try:
            candidates.append(
                {
                    "path": str(item["file_path"]),
                    "start_line": int(item["start_line"]),
                    "end_line": int(item["end_line"]),
                    "score": float(item["score"]),
                }
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise error_cls(f"retrieval candidate entry is missing an exact path/line/score field: {exc}") from exc
    return tuple(candidates)


def readback_candidate(root: Path, candidate: dict[str, Any], *, error_cls: type[Exception]) -> dict[str, Any]:
    """Direct source readback against the candidate tree. A path or range the tree cannot produce is a
    missing/stale index, reported as such instead of being silently dropped into a shorter result."""
    root = Path(root).resolve()
    relative = Path(candidate["path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise error_cls(f"retrieval candidate path escapes the candidate tree: {candidate['path']!r}")
    source = root / relative
    if not source.is_file():
        raise error_cls(
            f"stale or foreign retrieval index: candidate {candidate['path']!r} is not a file in the candidate tree"
        )
    lines = source.read_bytes().splitlines(keepends=True)
    start, end = candidate["start_line"], candidate["end_line"]
    if start < 1 or end < start or end > len(lines):
        raise error_cls(
            f"stale retrieval index: candidate {candidate['path']!r} lines {start}-{end} exceed the "
            f"{len(lines)} lines the candidate tree actually holds"
        )
    body = b"".join(lines[start - 1 : end])
    return {
        "path": candidate["path"],
        "start_line": start,
        "end_line": end,
        "score": candidate["score"],
        "source_bytes": len(body),
        "source_sha256": hashlib.sha256(body).hexdigest(),
    }


def _tree_digest(root: Path) -> tuple[str, tuple[str, ...]]:
    root = Path(root).resolve()
    entries: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if set(relative.parts) & RESIDUE_SKIP_DIRS or not path.is_file():
            continue
        entries.append((relative.as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()))
    digest = hashlib.sha256("\n".join(f"{name}:{sha}" for name, sha in entries).encode()).hexdigest()
    return digest, tuple(name for name, _ in entries)


def probe_retrieval(root: Path, search: Callable[[str], str], *, error_cls: type[Exception]) -> dict[str, Any]:
    """Run the pinned positive and nonsense controls, read every candidate back from source, and
    record latency, candidate count, context bytes, and residue."""
    root = Path(root).resolve()
    pin = load_retrieval_pin(root, error_cls=error_cls)
    control = pin["control"]
    before_digest, before_paths = _tree_digest(root)
    observations: dict[str, Any] = {}
    for kind, query in (("positive", control["positive_query"]), ("nonsense", control["nonsense_query"])):
        started = time.perf_counter()
        stdout = search(query)
        latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
        candidates = parse_candidates(stdout, error_cls=error_cls)
        readbacks = [readback_candidate(root, candidate, error_cls=error_cls) for candidate in candidates]
        observations[kind] = {
            "query": query,
            "latency_ms": latency_ms,
            "candidate_count": len(readbacks),
            "context_bytes": sum(item["source_bytes"] for item in readbacks),
            "top_score": max((item["score"] for item in readbacks), default=None),
            "candidates": readbacks,
        }
    if not observations["positive"]["candidate_count"]:
        raise error_cls(
            "missing, empty, or stale retrieval index: the pinned positive control returned zero "
            "candidates, and an empty result is not absence proof"
        )
    if not observations["nonsense"]["candidate_count"]:
        raise error_cls(
            "nonsense control returned zero candidates, so nearest-neighbour behaviour was not "
            "demonstrated and no miss in this run may be read as absence"
        )
    after_digest, after_paths = _tree_digest(root)
    residue = sorted(set(after_paths) - set(before_paths))
    if after_digest != before_digest:
        raise error_cls(f"retrieval mutated the candidate tree; residue={residue or 'content-change'}")
    observations["nonsense"]["absence_proof"] = False
    observations["nonsense"]["nearest_neighbours"] = True
    return {
        "schema_version": 1,
        "authority": AUTHORITY,
        "laws": list(LAWS),
        "non_claims": list(NON_CLAIMS),
        "pin": {
            "command": pin["command"],
            "version": pin["version"],
            "binary_sha256": pin["binary_sha256"],
            "argv": list(pin["argv"]),
            "embedder": dict(pin["embedder"]),
        },
        "observations": observations,
        "residue": {"tree_sha256": after_digest, "new_paths": residue},
    }


def verify_pinned_executable(pin: dict[str, Any], *, error_cls: type[Exception]) -> dict[str, Any]:
    resolved = shutil.which(pin["command"])
    if resolved is None:
        raise error_cls(f"pinned retrieval command {pin['command']!r} is not installed on this host")
    real = Path(resolved).resolve()
    digest = hashlib.sha256(real.read_bytes()).hexdigest()
    if digest != pin["binary_sha256"]:
        raise error_cls(f"retrieval executable {real} digest {digest} != pinned {pin['binary_sha256']}")
    reported = subprocess.run(
        [str(real), *pin["version_argv"][1:]], text=True, capture_output=True, check=False
    )
    if reported.returncode != 0 or pin["version"] not in reported.stdout:
        raise error_cls(
            f"retrieval executable did not report pinned version {pin['version']!r}: "
            f"{reported.stdout.strip() or reported.stderr.strip()!r}"
        )
    return {"path": str(real), "sha256": digest, "version_stdout": reported.stdout.strip()}


def require_index(index_root: Path, *, error_cls: type[Exception]) -> dict[str, Any]:
    """The index lives outside the candidate tree on purpose: `grepai init` writes `.grepai/` and
    appends to `.gitignore`, so indexing the candidate itself would plant residue in the artifact
    under test."""
    index_root = Path(index_root).resolve()
    index = index_root / INDEX_DIRNAME / INDEX_FILENAME
    if not index.is_file() or index.stat().st_size == 0:
        raise error_cls(
            f"no usable retrieval index at {index}; an unindexed project answers every query with an "
            "empty result that is indistinguishable from a real miss"
        )
    return {"index_root": str(index_root), "index_bytes": index.stat().st_size}


def retrieval_probe(root: Path, index_root: Path, *, error_cls: type[Exception]) -> dict[str, Any]:
    root = Path(root).resolve()
    if Path(index_root).resolve() == root:
        raise error_cls("retrieval index root must stay outside the candidate tree to keep the candidate residue-free")
    pin = load_retrieval_pin(root, error_cls=error_cls)
    executable = verify_pinned_executable(pin, error_cls=error_cls)
    index = require_index(index_root, error_cls=error_cls)

    def search(query: str) -> str:
        result = subprocess.run(
            pinned_argv(pin, query), cwd=index["index_root"], text=True, capture_output=True, check=False
        )
        if result.returncode != 0:
            raise error_cls(f"pinned retrieval argv failed: {result.stderr.strip() or result.stdout.strip()}")
        return result.stdout

    receipt = probe_retrieval(root, search, error_cls=error_cls)
    receipt["executable"] = executable
    receipt["index"] = index
    return receipt

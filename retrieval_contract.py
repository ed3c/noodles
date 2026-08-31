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

The code-intelligence canary at the end of this module is that same admitted contract carried one
step further, because the step is the same step: the candidate paths a query proposes are handed to
the pinned structural parser and then reduced to one exact-subject evidence row. Nothing new is
trusted along the way - every leg still ends in a direct re-read of the current source bytes.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

import evidence_ledger
import structural_contract

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
CANARY_SUBJECT = "ed3c/noodles#9"
CANARY_ADAPTER = "code-intel-canary"
CANARY_EVIDENCE_PATH = ".noodle/code-intel-canary.json"
CANARY_SCHEMA_VERSION = 1
CANARY_CAPABILITY = "code-intel-canary"
# constraint: planted negative controls - a foreign subject, a foreign adapter identity, and a
# constraint: foreign path that the chosen candidate can never be, since the grammar covers only .py.
CONTROL_FOREIGN_SUBJECT = "ed3c/noodles#999999"
CONTROL_FOREIGN_ADAPTER = "not-the-canary"
CONTROL_FOREIGN_PATH = "policy/fitness.json"
DEFINITION_HEADERS = (b"def ", b"async def ", b"class ")
CANARY_NON_CLAIMS = (
    "no production-proven universal pipeline",
    "no SCIP, LanceDB, Serena edit, or scheduler participation",
    "no absence proof: an empty candidate set stays indistinguishable from a real miss",
    "one repository task at one commit; not a general code-intelligence guarantee",
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


def pinned_search(pin: dict[str, Any], index_root: str, *, error_cls: type[Exception]) -> Callable[[str], str]:
    """The one door to running the tool: the pinned argv, against the index root, never the candidate."""

    def search(query: str) -> str:
        result = subprocess.run(
            pinned_argv(pin, query), cwd=index_root, text=True, capture_output=True, check=False
        )
        if result.returncode != 0:
            raise error_cls(f"pinned retrieval argv failed: {result.stderr.strip() or result.stdout.strip()}")
        return result.stdout

    return search


def _live_retrieval(root: Path, index_root: Path, *, error_cls: type[Exception]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Callable[[str], str]]:
    root = Path(root).resolve()
    if Path(index_root).resolve() == root:
        raise error_cls("retrieval index root must stay outside the candidate tree to keep the candidate residue-free")
    pin = load_retrieval_pin(root, error_cls=error_cls)
    executable = verify_pinned_executable(pin, error_cls=error_cls)
    index = require_index(index_root, error_cls=error_cls)
    return pin, executable, index, pinned_search(pin, index["index_root"], error_cls=error_cls)


def retrieval_probe(root: Path, index_root: Path, *, error_cls: type[Exception]) -> dict[str, Any]:
    _pin, executable, index, search = _live_retrieval(root, index_root, error_cls=error_cls)
    receipt = probe_retrieval(Path(root).resolve(), search, error_cls=error_cls)
    receipt["executable"] = executable
    receipt["index"] = index
    return receipt


def admit_canary_row(
    connection: Any, subject: str, source: bytes, *, adapter: str, path: str, error_cls: type[Exception]
) -> dict[str, Any]:
    """The consuming end of the chain.

    A stored row is served only when the exact subject, the adapter identity, the source digest, the
    recorded path, and the recorded byte range all survive a direct re-read of the current source
    bytes. Each of the five is refusable on its own, so a fault planted at any single boundary is a
    refusal rather than a plausible-looking answer.
    """
    row = evidence_ledger.read_back(connection, subject, source, error_cls=error_cls)
    if row.adapter != adapter:
        raise error_cls(
            f"evidence for {subject} was produced by adapter {row.adapter!r}, not the expected {adapter!r}"
        )
    try:
        claim = json.loads(row.observation)
        recorded_path = str(claim["path"])
        definition = str(claim["definition"])
        start, end = (int(value) for value in claim["range"])
        name_start, name_end = (int(value) for value in claim["name_range"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise error_cls(f"evidence observation for {subject} is not one structural claim: {exc}") from exc
    if recorded_path != path:
        raise error_cls(f"evidence for {subject} names path {recorded_path!r}, not the requested {path!r}")
    if not 0 <= start < end <= len(source) or not start <= name_start < name_end <= end:
        raise error_cls(
            f"evidence for {subject} records range {start}..{end} that is not inside the {len(source)} source bytes"
        )
    if source[name_start:name_end] != definition.encode("utf-8"):
        raise error_cls(
            f"evidence for {subject} records {definition!r} at bytes {name_start}..{name_end}, "
            f"which read back {source[name_start:name_end]!r}"
        )
    if not source[start:end].startswith(DEFINITION_HEADERS):
        raise error_cls(
            f"evidence for {subject} records a definition at bytes {start}..{end}, "
            f"which read back {source[start : start + 16]!r}"
        )
    return {"subject": subject, "adapter": adapter, "source_sha256": row.source_sha256, **claim}


def _line_starts(source: bytes) -> list[int]:
    return [0, *(index + 1 for index, byte in enumerate(source) if byte == 0x0A)]


def _structural_candidate(
    root: Path,
    readbacks: list[dict[str, Any]],
    module: Any,
    language: Any,
    suffixes: tuple[str, ...],
    *,
    error_cls: type[Exception],
) -> tuple[dict[str, Any], bytes, tuple[int, int, int, int]]:
    """Retrieval only proposes. The pinned parser decides which candidate carries a definition, and
    CPython's own parser has to agree with every reported range before one is chosen."""
    for candidate in readbacks:
        if not candidate["path"].endswith(suffixes):
            continue
        source, observed, parse_error = structural_contract.definitions_for_path(
            root, candidate["path"], module, language, suffixes, error_cls=error_cls
        )
        if parse_error is not None or observed is None:
            raise error_cls(f"candidate {candidate['path']} did not parse: bounded error {parse_error}")
        disagreements = structural_contract.readback_errors(
            candidate["path"], source, observed, structural_contract.expected_definitions(source)
        )
        if disagreements:
            raise error_cls(f"structural readback disagreed with CPython: {disagreements[0]}")
        starts = _line_starts(source)
        span_start = starts[candidate["start_line"] - 1]
        span_end = starts[candidate["end_line"]] if candidate["end_line"] < len(starts) else len(source)
        enclosing = [item for item in observed if item[0] < span_end and span_start < item[1]]
        if enclosing:
            return candidate, source, max(enclosing, key=lambda item: item[1] - item[0])
    raise error_cls(
        "no retrieval candidate resolved to a pinned-grammar definition; a candidate miss is never absence proof"
    )


def _canary_control(name: str, description: str, probe: Callable[[], Any], *, error_cls: type[Exception]) -> dict[str, Any]:
    """A planted fault the consumer must refuse; a control that passes means the chain is blind."""
    try:
        probe()
    except error_cls as failure:
        return {"control": name, "description": description, "rejected": True, "diagnostic": str(failure)}
    raise error_cls(f"planted control {name} did not fail; the evidence consumer cannot detect it")


def _planted_ledger(
    directory: Path, name: str, subject: str, source: bytes, observation: str, *, error_cls: type[Exception]
) -> Any:
    connection = evidence_ledger.open_ledger(directory / f"{name}.sqlite3")
    evidence_ledger.record(
        connection,
        evidence_ledger.SourceObservation(
            subject=subject, observation=observation, source=source, adapter=CANARY_ADAPTER
        ),
        error_cls=error_cls,
    )
    return connection


def canary_controls(
    directory: Path,
    connection: Any,
    subject: str,
    source: bytes,
    path: str,
    claim: dict[str, Any],
    *,
    error_cls: type[Exception],
) -> list[dict[str, Any]]:
    """One planted fault per boundary the chain crosses: subject, source digest, adapter, path, range."""
    start, end = claim["range"]
    name_start, name_end = claim["name_range"]
    renamed = source[:name_start] + b"x" * (name_end - name_start) + source[name_end:]
    wrong_path = _planted_ledger(
        directory, "wrong-path", subject, source, json.dumps({**claim, "path": CONTROL_FOREIGN_PATH}, sort_keys=True), error_cls=error_cls
    )
    wrong_range = _planted_ledger(
        directory,
        "wrong-range",
        subject,
        source,
        json.dumps({**claim, "range": [start + 1, end], "name_range": [name_start + 1, name_end + 1]}, sort_keys=True),
        error_cls=error_cls,
    )
    controls = [
        _canary_control(
            "wrong_subject",
            "a different exact subject must find no row at all, never the neighbouring one",
            lambda: admit_canary_row(
                connection, CONTROL_FOREIGN_SUBJECT, source, adapter=CANARY_ADAPTER, path=path, error_cls=error_cls
            ),
            error_cls=error_cls,
        ),
        _canary_control(
            "stale_source",
            "the recorded definition is renamed in place, so every byte offset still fits and only the digest moves",
            lambda: admit_canary_row(
                connection, subject, renamed, adapter=CANARY_ADAPTER, path=path, error_cls=error_cls
            ),
            error_cls=error_cls,
        ),
        _canary_control(
            "wrong_adapter",
            "a row produced by one adapter must not be served to a consumer expecting another",
            lambda: admit_canary_row(
                connection, subject, source, adapter=CONTROL_FOREIGN_ADAPTER, path=path, error_cls=error_cls
            ),
            error_cls=error_cls,
        ),
        _canary_control(
            "wrong_path",
            "the row names a path the consumer did not ask about",
            lambda: admit_canary_row(
                wrong_path, subject, source, adapter=CANARY_ADAPTER, path=path, error_cls=error_cls
            ),
            error_cls=error_cls,
        ),
        _canary_control(
            "wrong_range",
            "the recorded byte range is shifted by one, so it no longer spells the recorded definition",
            lambda: admit_canary_row(
                wrong_range, subject, source, adapter=CANARY_ADAPTER, path=path, error_cls=error_cls
            ),
            error_cls=error_cls,
        ),
    ]
    wrong_path.close()
    wrong_range.close()
    return controls


def code_intel_journey(
    root: Path, search: Callable[[str], str], subject: str, *, error_cls: type[Exception]
) -> dict[str, Any]:
    """One exact repository task across the landed band: intent query -> candidate paths ->
    structural/source readback -> one exact-subject evidence row, with a planted fault at every
    boundary proving the consumer refuses instead of serving something plausible."""
    root = Path(root).resolve()
    lock = structural_contract.load_parser_lock(root, error_cls=error_cls)
    module, language, parser_pins = structural_contract.load_language(lock, error_cls=error_cls)
    suffixes = tuple(lock["grammar"]["suffixes"])
    query = load_retrieval_pin(root, error_cls=error_cls)["control"]["positive_query"]
    before_digest, _ = _tree_digest(root)

    started = time.perf_counter()
    candidates = parse_candidates(search(query), error_cls=error_cls)
    retrieval_ms = round((time.perf_counter() - started) * 1000.0, 3)
    readbacks = [readback_candidate(root, candidate, error_cls=error_cls) for candidate in candidates]

    started = time.perf_counter()
    candidate, source, span = _structural_candidate(root, readbacks, module, language, suffixes, error_cls=error_cls)
    structural_ms = round((time.perf_counter() - started) * 1000.0, 3)
    start, end, name_start, name_end = span
    claim = {
        "path": candidate["path"],
        "definition": source[name_start:name_end].decode("utf-8"),
        "range": [start, end],
        "name_range": [name_start, name_end],
    }

    with tempfile.TemporaryDirectory(prefix="noodles-code-intel-canary-") as workspace:
        directory = Path(workspace).resolve()
        if str(directory).startswith(str(root)):
            raise error_cls("the canary ledger must live outside the candidate tree to keep the candidate residue-free")
        started = time.perf_counter()
        connection = evidence_ledger.open_ledger(directory / "canary.sqlite3")
        row = evidence_ledger.record(
            connection,
            evidence_ledger.SourceObservation(
                subject=subject,
                observation=json.dumps(claim, sort_keys=True),
                source=source,
                adapter=CANARY_ADAPTER,
            ),
            error_cls=error_cls,
        )
        admitted = admit_canary_row(
            connection, subject, source, adapter=CANARY_ADAPTER, path=candidate["path"], error_cls=error_cls
        )
        ledger_ms = round((time.perf_counter() - started) * 1000.0, 3)
        export = evidence_ledger.canonical_export(connection).encode("utf-8")
        controls = canary_controls(directory, connection, subject, source, candidate["path"], claim, error_cls=error_cls)
        connection.close()

    after_digest, after_paths = _tree_digest(root)
    if after_digest != before_digest:
        raise error_cls(f"the code-intelligence canary mutated the candidate tree; {len(after_paths)} paths observed")
    return {
        "schema_version": CANARY_SCHEMA_VERSION,
        "capability": CANARY_CAPABILITY,
        "subject": subject,
        "authority": AUTHORITY,
        "laws": list(LAWS),
        "chain": {
            "intent_query": {"query": query, "candidate_count": len(readbacks), "authority": AUTHORITY},
            "candidate": candidate,
            "structural": {
                "parser": parser_pins,
                "query": structural_contract.DEFINITION_QUERY,
                "cross_parser": "cpython-ast",
                "claim": claim,
            },
            "evidence_row": {
                "subject": row.subject,
                "adapter": row.adapter,
                "source_sha256": row.source_sha256,
                "observation": row.observation,
            },
            "admitted": admitted,
        },
        "controls": controls,
        "metrics": {
            "retrieval_ms": retrieval_ms,
            "structural_ms": structural_ms,
            "ledger_ms": ledger_ms,
            "candidate_context_bytes": candidate["source_bytes"],
            "definition_bytes": end - start,
            "context_bytes": candidate["source_bytes"] + (end - start),
            "evidence_sha256": hashlib.sha256(export).hexdigest(),
            "evidence_bytes": len(export),
        },
        "residue": {"tree_sha256": after_digest, "ledger_outside_candidate_tree": True},
        "non_claims": list(CANARY_NON_CLAIMS),
    }


def code_intel_canary(root: Path, index_root: Path, subject: str, *, error_cls: type[Exception]) -> dict[str, Any]:
    _pin, executable, index, search = _live_retrieval(root, index_root, error_cls=error_cls)
    receipt = code_intel_journey(Path(root).resolve(), search, subject, error_cls=error_cls)
    receipt["executable"] = executable
    receipt["index"] = index
    return receipt

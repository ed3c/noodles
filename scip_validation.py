#!/usr/bin/env python3
"""Fresh exact-commit SCIP validation: build an index, look symbols up, plant failing controls, record receipts.

Live use needs the pinned external indexer/reader; the lookup, readback, control, and admission core is
pure and runs offline, so trusted CI proves the oracle can go red without installing either tool.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Sequence

EVIDENCE_PATH = "migrations/skills-shared/scip-validation.json"
SCHEMA_VERSION = 1
LEDGER_CAPABILITY = "scip-semantic-graph"

# constraint: exact pins; the same commits are recorded in policy/providers.lock.json and re-checked by admit_evidence.
INDEXER_PIN = {
    "tool": "scip-python",
    "version": "0.6.6",
    "commit": "8b60bbce1f2a4c7a517776cb395bbafb2e731e4f",
}
READER_PIN = {
    "tool": "scip",
    "version": "v0.9.0",
    "commit": "e8ee0ae6038f8298e2195812eea9d7b1196748ae",
}

# constraint: SCIP SymbolRole bitmask; bit 0 is Definition, every other role is a reference occurrence.
DEFINITION_ROLE = 1
# constraint: "local N" symbols are numbered per document, so the same id means different things in two files.
GLOBAL_SYMBOL_PREFIX = "scip-python python "
LOCAL_SYMBOL_PREFIX = "local "
CONTROL_UNCOVERED = "unsupported-coverage"
CONTROL_STALE = "stale-index"
EVIDENCE_FIELDS = (
    "schema_version",
    "capability",
    "indexer",
    "reader",
    "repository",
    "index",
    "lookups",
    "controls",
    "metrics",
    "non_claims",
)


class ScipError(RuntimeError):
    """A fail-closed SCIP validation or admission failure."""


def _run(argv: Sequence[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(list(argv), cwd=None if cwd is None else str(cwd), text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise ScipError(f"{' '.join(argv)} failed: {result.stderr.strip() or result.stdout.strip()}")
    return result


def _git(root: Path, *args: str) -> str:
    return _run(["git", *args], cwd=root).stdout.strip()


def documents(payload: Any) -> dict[str, list[dict[str, Any]]]:
    """Index the reader's JSON by relative path; a malformed payload fails closed instead of reading empty."""
    if not isinstance(payload, dict) or not isinstance(payload.get("documents"), list):
        raise ScipError("SCIP payload carries no documents array")
    mapped: dict[str, list[dict[str, Any]]] = {}
    for document in payload["documents"]:
        if not isinstance(document, dict) or not document.get("relative_path"):
            raise ScipError("SCIP document carries no relative_path")
        mapped[str(document["relative_path"])] = list(document.get("occurrences") or [])
    return mapped


def require_covered(payload: Any, relative_path: str) -> None:
    """Unsupported-coverage control: an uncovered file must be a distinct refusal, never an empty result."""
    if relative_path not in documents(payload):
        raise ScipError(f"uncovered: {relative_path} has no SCIP document; absence of occurrences is not absence of symbols")


def _require_global(symbol: str) -> str:
    if symbol.startswith(LOCAL_SYMBOL_PREFIX) or not symbol.startswith(GLOBAL_SYMBOL_PREFIX):
        raise ScipError(f"not a global SCIP symbol: {symbol!r}")
    return symbol


def definition_of(payload: Any, symbol: str) -> tuple[str, list[int]]:
    """Definition lookup: exactly one definition occurrence, or fail closed."""
    _require_global(symbol)
    hits = [
        (path, list(occurrence["range"]))
        for path, occurrences in documents(payload).items()
        for occurrence in occurrences
        if occurrence.get("symbol") == symbol and int(occurrence.get("symbol_roles") or 0) & DEFINITION_ROLE
    ]
    if len(hits) != 1:
        raise ScipError(f"definition lookup for {symbol!r} resolved {len(hits)} definitions, expected exactly 1")
    return hits[0]


def references_of(payload: Any, symbol: str) -> list[tuple[str, list[int]]]:
    """Reference lookup: every non-definition occurrence, or fail closed when there are none."""
    _require_global(symbol)
    hits = [
        (path, list(occurrence["range"]))
        for path, occurrences in documents(payload).items()
        for occurrence in occurrences
        if occurrence.get("symbol") == symbol and not int(occurrence.get("symbol_roles") or 0) & DEFINITION_ROLE
    ]
    if not hits:
        raise ScipError(f"reference lookup for {symbol!r} resolved no references")
    return hits


def cross_file_reference(payload: Any, symbol: str, definition_path: str) -> tuple[str, list[int]]:
    """One relation that only a cross-file index can produce: a reference outside the defining document."""
    for path, occurrence_range in references_of(payload, symbol):
        if path != definition_path:
            return path, occurrence_range
    raise ScipError(f"no cross-file reference for {symbol!r} outside {definition_path}")


def read_range(root: Path, relative_path: str, occurrence_range: Sequence[int]) -> str:
    """Direct-source readback: slice the real file, never the index's own copy of the text."""
    values = [int(value) for value in occurrence_range]
    if len(values) == 3:
        start_line, start_char, end_line, end_char = values[0], values[1], values[0], values[2]
    elif len(values) == 4:
        start_line, start_char, end_line, end_char = values
    else:
        raise ScipError(f"unsupported SCIP range shape: {list(occurrence_range)!r}")
    if start_line != end_line:
        raise ScipError(f"multi-line range readback is out of scope: {list(occurrence_range)!r}")
    source = root / relative_path
    if not source.is_file():
        raise ScipError(f"uncovered: source file missing for readback: {relative_path}")
    lines = source.read_bytes().split(b"\n")
    if start_line >= len(lines):
        raise ScipError(f"stale index: {relative_path} has {len(lines)} lines, range wants line {start_line}")
    line = lines[start_line]
    if end_char > len(line):
        raise ScipError(f"stale index: {relative_path}:{start_line} is {len(line)} bytes, range wants {end_char}")
    return line[start_char:end_char].decode("utf-8")


def verify_readback(root: Path, relative_path: str, occurrence_range: Sequence[int], expected: str) -> str:
    """Stale-index control: the recorded range must still spell the recorded name in the real source."""
    observed = read_range(root, relative_path, occurrence_range)
    if observed != expected:
        raise ScipError(
            f"stale index: {relative_path}{list(occurrence_range)} reads {observed!r}, recorded {expected!r}"
        )
    return observed


def rename_in_place(source: bytes, occurrence_range: Sequence[int]) -> bytes:
    """Plant the hardest stale-index mutation: same line count, same offsets, different identifier."""
    values = [int(value) for value in occurrence_range]
    if len(values) != 3:
        raise ScipError(f"in-place rename needs a single-line range: {list(occurrence_range)!r}")
    line_number, start_char, end_char = values
    lines = source.split(b"\n")
    line = lines[line_number]
    lines[line_number] = line[:start_char] + b"x" * (end_char - start_char) + line[end_char:]
    return b"\n".join(lines)


def _control(name: str, description: str, probe: Any) -> dict[str, Any]:
    """Run a planted control and require it to fail; a control that passes means the oracle is blind."""
    try:
        probe()
    except ScipError as failure:
        return {"control": name, "description": description, "rejected": True, "diagnostic": str(failure)}
    raise ScipError(f"planted control {name} did not fail; the oracle cannot detect it")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tracked(root: Path) -> list[str]:
    return [line for line in _git(root, "ls-files").splitlines() if line]


def build_index(root: Path, out_dir: Path, project_version: str) -> tuple[Path, float]:
    index_path = out_dir / "index.scip"
    started = time.monotonic()
    _run(
        [
            INDEXER_PIN["tool"],
            "index",
            ".",
            "--project-name",
            "noodles",
            "--project-version",
            project_version,
            "--output",
            str(index_path),
        ],
        cwd=root,
    )
    return index_path, round(time.monotonic() - started, 3)


def read_index(index_path: Path) -> tuple[Any, float]:
    started = time.monotonic()
    payload = json.loads(_run([READER_PIN["tool"], "print", "--json", str(index_path)]).stdout)
    return payload, round(time.monotonic() - started, 3)


def _tool_version(argv: Sequence[str], expected: str) -> None:
    observed = _run(list(argv)).stdout.strip()
    if expected not in observed:
        raise ScipError(f"{argv[0]} reports {observed!r}, not pinned {expected!r}")


def validate(root: Path, out_dir: Path, symbol_module: str = "feature_contract", symbol_name: str = "verify_feature") -> dict[str, Any]:
    """Run the whole physical experiment at the exact clean head and return the receipt."""
    root = Path(root).resolve()
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    _tool_version([INDEXER_PIN["tool"], "--version"], INDEXER_PIN["version"])
    _tool_version([READER_PIN["tool"], "--version"], READER_PIN["version"])

    residue_before = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    if residue_before:
        raise ScipError(f"validation requires a clean exact head; worktree is dirty: {residue_before}")
    commit = _git(root, "rev-parse", "HEAD")
    tree = _git(root, "rev-parse", "HEAD^{tree}")

    index_path, build_seconds = build_index(root, out_dir, commit[:12])
    payload, read_seconds = read_index(index_path)

    symbol = f"{GLOBAL_SYMBOL_PREFIX}noodles {commit[:12]} {symbol_module}/{symbol_name}()."
    started = time.monotonic()
    definition_path, definition_range = definition_of(payload, symbol)
    references = references_of(payload, symbol)
    reference_path, reference_range = cross_file_reference(payload, symbol, definition_path)
    definition_text = verify_readback(root, definition_path, definition_range, symbol_name)
    reference_text = verify_readback(root, reference_path, reference_range, symbol_name)
    query_seconds = round(time.monotonic() - started, 3)

    uncovered_path = next((path for path in _tracked(root) if not path.endswith(".py")), "")
    if not uncovered_path:
        raise ScipError("no tracked non-Python file exists to plant the unsupported-coverage control against")
    stale_copy = out_dir / "stale-source.py"
    stale_copy.write_bytes(rename_in_place((root / definition_path).read_bytes(), definition_range))
    controls = [
        _control(
            CONTROL_UNCOVERED,
            f"a tracked non-Python file ({uncovered_path}) is outside the indexer's language coverage",
            lambda: require_covered(payload, uncovered_path),
        ),
        _control(
            CONTROL_STALE,
            "the definition is renamed in place, so line count and every byte offset still match the index",
            lambda: verify_readback(stale_copy.parent, stale_copy.name, definition_range, symbol_name),
        ),
    ]

    covered = sorted(documents(payload))
    tracked = _tracked(root)
    tracked_python = [path for path in tracked if path.endswith(".py")]
    residue_after = [line for line in _git(root, "status", "--porcelain=v1", "--untracked-files=all").splitlines() if line]
    return {
        "schema_version": SCHEMA_VERSION,
        "capability": LEDGER_CAPABILITY,
        "indexer": dict(INDEXER_PIN),
        "reader": dict(READER_PIN),
        "repository": {"repo": "ed3c/noodles", "commit": commit, "tree": tree},
        "index": {
            "project_root": (payload.get("metadata") or {}).get("project_root", ""),
            "tool_info": (payload.get("metadata") or {}).get("tool_info", {}),
            "sha256": _sha256(index_path),
            "bytes": index_path.stat().st_size,
        },
        "lookups": {
            "symbol": symbol,
            "definition": {"path": definition_path, "range": definition_range, "text": definition_text},
            "reference_count": len(references),
            "cross_file_reference": {"path": reference_path, "range": reference_range, "text": reference_text},
            "source_readback": symbol_name,
        },
        "controls": controls,
        "metrics": {
            "build_seconds": build_seconds,
            "index_read_seconds": read_seconds,
            "query_seconds": query_seconds,
            "index_bytes": index_path.stat().st_size,
            "indexed_documents": len(covered),
            "tracked_files": len(tracked),
            "tracked_python_files": len(tracked_python),
            "python_coverage": round(len(covered) / max(len(tracked_python), 1), 6),
            "tracked_coverage": round(len(covered) / max(len(tracked), 1), 6),
            "residue": residue_after,
        },
        "non_claims": [
            "The index digest is host-bound: metadata.project_root records an absolute path, so a different checkout path yields a different sha256.",
            "Coverage is Python-only; every tracked non-Python file is uncovered, and an uncovered file yields refusal, not absence proof.",
            "'local N' symbols are numbered per document and are refused; only global symbols are looked up.",
            "This receipt proves one past physical run at the recorded commit; it is not a required dependency of the Golden Path or of code-intelligence v1.",
        ],
    }


def admit_evidence(evidence: Any, *, root: Path | None = None) -> dict[str, Any]:
    """Admit a receipt only when it names the exact pins, resolves cross-file, and records both controls failing."""
    if not isinstance(evidence, dict):
        raise ScipError("SCIP validation evidence must be a JSON object")
    missing = [field for field in EVIDENCE_FIELDS if field not in evidence]
    if missing:
        raise ScipError(f"SCIP evidence is an agent self-report; missing physical fields: {', '.join(missing)}")
    if evidence["schema_version"] != SCHEMA_VERSION:
        raise ScipError(f"unsupported SCIP evidence schema: {evidence['schema_version']!r}")
    if evidence["capability"] != LEDGER_CAPABILITY:
        raise ScipError(f"SCIP evidence names capability {evidence['capability']!r}, not {LEDGER_CAPABILITY!r}")
    if evidence["indexer"] != INDEXER_PIN or evidence["reader"] != READER_PIN:
        raise ScipError("SCIP evidence was produced by an unpinned indexer/reader pair")

    repository = evidence["repository"]
    for field in ("commit", "tree"):
        value = str((repository or {}).get(field, ""))
        if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
            raise ScipError(f"SCIP evidence {field} is not an exact 40-hex object id: {value!r}")
    index = evidence["index"]
    digest = str((index or {}).get("sha256", ""))
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ScipError(f"SCIP evidence index digest is not a sha256: {digest!r}")
    if int((index or {}).get("bytes", 0)) <= 0:
        raise ScipError("SCIP evidence records no built index")
    # constraint: tool_info is the index's own statement of its producer, read back by the reader, not an agent assertion.
    tool_info = (index or {}).get("tool_info") or {}
    if tool_info.get("name") != INDEXER_PIN["tool"] or tool_info.get("version") != INDEXER_PIN["version"]:
        raise ScipError(f"the built index reports producer {tool_info!r}, not pinned {INDEXER_PIN['tool']} {INDEXER_PIN['version']}")

    lookups = evidence["lookups"]
    if not isinstance(lookups, dict) or not isinstance(evidence["controls"], list):
        raise ScipError("SCIP evidence lookups must be an object and controls must be a list")
    symbol = str(lookups.get("symbol", ""))
    _require_global(symbol)
    definition = lookups.get("definition") or {}
    reference = lookups.get("cross_file_reference") or {}
    name = lookups.get("source_readback")
    if definition.get("path") == reference.get("path") or not reference.get("path"):
        raise ScipError("SCIP evidence records no cross-file relation")
    if int(lookups.get("reference_count") or 0) < 1:
        raise ScipError("SCIP evidence records no reference lookup")
    if not name or definition.get("text") != name or reference.get("text") != name:
        raise ScipError(f"SCIP evidence readback text does not spell {name!r} at both recorded ranges")
    if not symbol.endswith(f"/{name}()."):
        raise ScipError(f"SCIP evidence symbol {symbol!r} does not name the read-back definition {name!r}")
    # constraint: the indexer stamps --project-version into every global symbol, so the symbol itself carries the exact commit.
    if f" {repository['commit'][:12]} " not in symbol:
        raise ScipError(f"SCIP evidence symbol {symbol!r} was not produced at commit {repository['commit']}")

    recorded = {str(item.get("control")) for item in evidence["controls"] if isinstance(item, dict)}
    if recorded != {CONTROL_UNCOVERED, CONTROL_STALE}:
        raise ScipError(f"SCIP evidence records controls {sorted(recorded)}, expected both planted controls")
    for item in evidence["controls"]:
        if item.get("rejected") is not True or not str(item.get("diagnostic") or "").strip():
            raise ScipError(f"planted control {item.get('control')!r} is not recorded as a proven failure")

    metrics = evidence["metrics"]
    for field in ("build_seconds", "index_read_seconds", "query_seconds", "index_bytes", "indexed_documents", "python_coverage", "residue"):
        if field not in metrics:
            raise ScipError(f"SCIP evidence records no {field}")
    if metrics["residue"]:
        raise ScipError(f"SCIP validation left residue: {metrics['residue']}")
    if not evidence["non_claims"]:
        raise ScipError("SCIP evidence records no non-claims")
    if root is not None:
        verify_readback(Path(root), str(definition["path"]), definition["range"], str(name))
    return evidence


def load_evidence(root: Path) -> dict[str, Any]:
    path = Path(root) / EVIDENCE_PATH
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScipError(f"cannot read {EVIDENCE_PATH}: {exc}") from exc


def main(argv: Iterable[str]) -> int:
    arguments = list(argv)
    root = Path(os.getenv("NOODLES_CANDIDATE_ROOT", Path(__file__).resolve().parent)).resolve()
    if arguments and arguments[0] == "admit":
        admit_evidence(load_evidence(root))
        print(f"PASS {EVIDENCE_PATH}")
        return 0
    evidence = validate(root, Path(os.environ.get("TMPDIR", "/tmp")) / "scip-validation")
    admit_evidence(evidence, root=root)
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ScipError as failure:
        print(f"FAIL: {failure}", file=sys.stderr)
        raise SystemExit(1) from failure

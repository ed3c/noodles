"""Pinned tree-sitter structural byte ranges over real repository sources.

The migrated claim is narrow: source bytes -> pinned parser/query -> structural ranges ->
direct source-byte readback. Nothing here is a semantic graph, a context compiler, an edit
engine, or a code-intelligence chain.

The readback is not self-referential. Every structural range tree-sitter reports is compared
against the same definition located by CPython's own `ast` parser, so a wrong range or a wrong
query disagrees with a second, independent parser instead of agreeing with itself.
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
from pathlib import Path
from typing import Any

PARSER_LOCK_PATH = "policy/parser.lock.json"
EXACT_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
DEFINITION_QUERY = (
    "[(function_definition name: (identifier) @name)"
    " (class_definition name: (identifier) @name)] @definition"
)
# constraint: planted negative control - captures parameter lists, so every reported range is wrong.
PLANTED_WRONG_QUERY = "(function_definition name: (identifier) @name parameters: (parameters) @definition)"
# constraint: planted negative control - unparseable bytes must surface one bounded parse error.
MALFORMED_SOURCE = b"def (:::\n    ???\n"


def validate_parser_lock(root: Path) -> list[str]:
    """Shape gate for the pin itself. Runs with no parser installed, so `./noodles verify`
    still refuses a floating or missing parser pin on a host that cannot parse anything."""
    path = Path(root) / PARSER_LOCK_PATH
    if not path.is_file():
        return [f"missing {PARSER_LOCK_PATH}"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        parser = payload["parser"]
        library = parser["library"]
        grammar = parser["grammar"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        return [f"invalid parser lock: {exc}"]
    errors: list[str] = []
    if payload.get("schema_version") != 1:
        errors.append(f"unsupported parser lock schema: {payload.get('schema_version')!r}")
    for label, entry in (("library", library), ("grammar", grammar)):
        if not isinstance(entry, dict):
            errors.append(f"parser lock {label} must be an object")
            continue
        if not str(entry.get("distribution", "")):
            errors.append(f"parser lock {label} distribution is required")
        if not EXACT_VERSION_RE.fullmatch(str(entry.get("version", ""))):
            errors.append(f"parser lock {label} is not pinned to an exact version")
        if not str(entry.get("source", "")).startswith("https://github.com/"):
            errors.append(f"parser lock {label} source must be a GitHub HTTPS URL")
        if not HEX40_RE.fullmatch(str(entry.get("commit", ""))):
            errors.append(f"parser lock {label} is not pinned to an exact 40-hex commit")
    if isinstance(grammar, dict):
        if not str(grammar.get("language", "")):
            errors.append("parser lock grammar language is required")
        if not isinstance(grammar.get("abi_version"), int):
            errors.append("parser lock grammar abi_version must be an integer")
        semantic = grammar.get("semantic_version")
        version = str(grammar.get("version", ""))
        if not isinstance(semantic, list) or [str(part) for part in semantic] != version.split("."):
            errors.append("parser lock grammar semantic_version must restate the pinned version")
        suffixes = grammar.get("suffixes")
        if not isinstance(suffixes, list) or not suffixes or not all(
            isinstance(item, str) and item.startswith(".") for item in suffixes
        ):
            errors.append("parser lock grammar suffixes must be a non-empty list of file suffixes")
    return errors


def load_parser_lock(root: Path, *, error_cls: type[Exception]) -> dict[str, Any]:
    errors = validate_parser_lock(root)
    if errors:
        raise error_cls("; ".join(errors))
    return json.loads((Path(root) / PARSER_LOCK_PATH).read_text(encoding="utf-8"))["parser"]


def load_language(lock: dict[str, Any], *, error_cls: type[Exception]) -> tuple[Any, Any, dict[str, Any]]:
    """Refuse to parse unless the installed parser and grammar are the pinned ones.

    Three independent readbacks have to agree: the distribution metadata of both wheels, and the
    grammar's own compiled `semantic_version`/`abi_version` reported by the built artifact.
    """
    library = lock["library"]
    grammar = lock["grammar"]
    try:
        import importlib.metadata

        import tree_sitter
        import tree_sitter_python
    except ImportError as exc:
        raise error_cls(
            f"pinned parser is not installed: {exc}; install "
            f"{library['distribution']}=={library['version']} {grammar['distribution']}=={grammar['version']}"
        ) from exc
    installed = {}
    for entry in (library, grammar):
        try:
            installed[entry["distribution"]] = importlib.metadata.version(entry["distribution"])
        except importlib.metadata.PackageNotFoundError as exc:
            raise error_cls(f"pinned distribution {entry['distribution']} is not installed") from exc
        if installed[entry["distribution"]] != entry["version"]:
            raise error_cls(
                f"installed {entry['distribution']} {installed[entry['distribution']]} "
                f"is not the pinned {entry['version']}"
            )
    language = tree_sitter.Language(tree_sitter_python.language())
    observed_semantic = list(language.semantic_version)
    if language.name != grammar["language"]:
        raise error_cls(f"loaded grammar is {language.name!r}, not the pinned {grammar['language']!r}")
    if language.abi_version != grammar["abi_version"]:
        raise error_cls(f"loaded grammar ABI {language.abi_version} is not the pinned {grammar['abi_version']}")
    if observed_semantic != list(grammar["semantic_version"]):
        raise error_cls(
            f"loaded grammar semantic version {observed_semantic} is not the pinned {grammar['semantic_version']}"
        )
    pins = {
        "library": {"distribution": library["distribution"], "version": installed[library["distribution"]]},
        "grammar": {
            "distribution": grammar["distribution"],
            "version": installed[grammar["distribution"]],
            "language": language.name,
            "abi_version": language.abi_version,
            "semantic_version": observed_semantic,
        },
    }
    return tree_sitter, language, pins


def bounded_parse_error(node: Any) -> dict[str, Any] | None:
    """Walk only the error-carrying spine and report the first faulty node's byte range.

    Bounded on purpose: a malformed file yields one located error, never a whole-tree dump.
    """
    if not node.has_error:
        return None
    while True:
        if node.type == "ERROR" or node.is_missing:
            return {"type": node.type, "missing": node.is_missing, "start_byte": node.start_byte, "end_byte": node.end_byte}
        deeper = next((child for child in node.children if child.has_error or child.is_missing), None)
        if deeper is None:
            return {"type": node.type, "missing": node.is_missing, "start_byte": node.start_byte, "end_byte": node.end_byte}
        node = deeper


def observed_definitions(
    module: Any, language: Any, source: bytes, query_text: str
) -> tuple[list[tuple[int, int, int, int]] | None, dict[str, Any] | None]:
    """Return sorted (start, end, name_start, name_end) byte ranges, or a bounded parse error."""
    tree = module.Parser(language).parse(source)
    error = bounded_parse_error(tree.root_node)
    if error is not None:
        return None, error
    cursor = module.QueryCursor(module.Query(language, query_text))
    found: list[tuple[int, int, int, int]] = []
    for _pattern, captures in cursor.matches(tree.root_node):
        if "definition" not in captures or "name" not in captures:
            continue
        definition = captures["definition"][0]
        name = captures["name"][0]
        found.append((definition.start_byte, definition.end_byte, name.start_byte, name.end_byte))
    return sorted(found), error


def expected_definitions(source: bytes) -> dict[tuple[int, int], str]:
    """Independent expectation from CPython's own parser: definition byte range -> name.

    `col_offset` is already a UTF-8 byte offset into its line, so line starts convert it to an
    absolute byte offset without re-deriving anything from tree-sitter.
    """
    line_starts = [0]
    for index, byte in enumerate(source):
        if byte == 0x0A:
            line_starts.append(index + 1)
    found: dict[tuple[int, int], str] = {}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = line_starts[node.lineno - 1] + node.col_offset
            end = line_starts[node.end_lineno - 1] + node.end_col_offset
            found[(start, end)] = node.name
    return found


def readback_errors(
    path: str,
    source: bytes,
    observed: list[tuple[int, int, int, int]],
    expected: dict[tuple[int, int], str],
) -> list[str]:
    """Read every reported range back out of the source bytes and reject any disagreement."""
    reported = {(start, end): (name_start, name_end) for start, end, name_start, name_end in observed}
    errors = [
        f"{path}: reported a structural range CPython does not: bytes {span[0]}..{span[1]}"
        for span in sorted(set(reported) - set(expected))
    ]
    errors.extend(
        f"{path}: missed the structural range CPython reports: bytes {span[0]}..{span[1]}"
        for span in sorted(set(expected) - set(reported))
    )
    for span in sorted(set(reported) & set(expected)):
        start, end = span
        name_start, name_end = reported[span]
        if not 0 <= start < end <= len(source) or not start <= name_start < name_end <= end:
            errors.append(f"{path}: structural range {start}..{end} is not inside the source bytes")
            continue
        wanted = expected[span].encode()
        if source[name_start:name_end] != wanted:
            errors.append(
                f"{path}: bytes {name_start}..{name_end} read back {source[name_start:name_end]!r}, expected {wanted!r}"
            )
        if not source[start:end].startswith((b"def ", b"async def ", b"class ")):
            errors.append(
                f"{path}: bytes {start}..{end} read back {source[start : start + 16]!r}, not a definition header"
            )
    return errors


def _git(root: Path, *args: str, error_cls: type[Exception]) -> str:
    result = subprocess.run(["git", *args], cwd=str(root), text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise error_cls(f"structural readback git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def _tracked_paths(root: Path, *, error_cls: type[Exception]) -> list[str]:
    raw = _git(root, "ls-files", "-z", error_cls=error_cls)
    return sorted(record for record in raw.split("\0") if record)


def definitions_for_path(
    root: Path, relative: str, module: Any, language: Any, suffixes: tuple[str, ...], *, error_cls: type[Exception]
) -> tuple[bytes, list[tuple[int, int, int, int]] | None, dict[str, Any] | None]:
    """The one door to parsing a repository path; an unpinned language is refused here, not skipped."""
    if not relative.endswith(suffixes):
        raise error_cls(f"unsupported language for {relative}: the pinned grammar covers {', '.join(suffixes)}")
    source = (Path(root) / relative).read_bytes()
    observed, parse_error = observed_definitions(module, language, source, DEFINITION_QUERY)
    return source, observed, parse_error


def structural_readback(root: Path, *, error_cls: type[Exception]) -> dict[str, Any]:
    """Parse the real repository, read every structural range back out of the source bytes, and
    prove the same comparison rejects a planted wrong range, a planted wrong query, malformed
    input, and an unsupported language."""
    root = Path(root).resolve()
    lock = load_parser_lock(root, error_cls=error_cls)
    module, language, pins = load_language(lock, error_cls=error_cls)
    suffixes = tuple(lock["grammar"]["suffixes"])
    residue_before = sorted(_git(root, "status", "--porcelain=v1", "--untracked-files=all", error_cls=error_cls).splitlines())

    tracked = _tracked_paths(root, error_cls=error_cls)
    supported = [relative for relative in tracked if relative.endswith(suffixes)]
    unsupported = [relative for relative in tracked if not relative.endswith(suffixes)]
    if not supported or not unsupported:
        raise error_cls("structural readback needs a real repository fixture with supported and unsupported paths")

    errors: list[str] = []
    definitions = 0
    readback_bytes = 0
    sample: tuple[str, bytes, list[tuple[int, int, int, int]], dict[tuple[int, int], str]] | None = None
    for relative in supported:
        source, observed, parse_error = definitions_for_path(
            root, relative, module, language, suffixes, error_cls=error_cls
        )
        if parse_error is not None:
            errors.append(
                f"{relative}: bounded parse error at bytes {parse_error['start_byte']}..{parse_error['end_byte']}"
            )
            continue
        expected = expected_definitions(source)
        errors.extend(readback_errors(relative, source, observed, expected))
        definitions += len(observed)
        readback_bytes += sum(end - start for start, end, _, _ in observed)
        if sample is None and observed:
            sample = (relative, source, observed, expected)
    if sample is None:
        raise error_cls("structural readback found no structural range to control against")

    controls = {
        "planted_wrong_range": _planted_range_control(sample),
        "planted_wrong_query": _planted_query_control(module, language, sample),
        "malformed_input": _malformed_control(module, language),
        "unsupported_language": _unsupported_control(root, unsupported[0], module, language, suffixes, error_cls=error_cls),
    }
    errors.extend(
        f"{name} control did not fail: {control['detail']}"
        for name, control in controls.items()
        if not control["rejected"]
    )
    residue_after = sorted(_git(root, "status", "--porcelain=v1", "--untracked-files=all", error_cls=error_cls).splitlines())
    if residue_after != residue_before:
        errors.append(f"structural readback left residue: {sorted(set(residue_after) - set(residue_before))}")
    return {
        "ok": not errors,
        "errors": errors,
        "parser": pins,
        "query": DEFINITION_QUERY,
        "coverage": {
            "language": lock["grammar"]["language"],
            "suffixes": list(suffixes),
            "supported_paths": len(supported),
            "unsupported_paths": len(unsupported),
            "unsupported_suffixes": sorted({Path(relative).suffix or Path(relative).name for relative in unsupported}),
            "definitions": definitions,
            "readback_bytes": readback_bytes,
        },
        "controls": controls,
        "residue": {"before": residue_before, "after": residue_after},
    }


def _planted_range_control(
    sample: tuple[str, bytes, list[tuple[int, int, int, int]], dict[tuple[int, int], str]]
) -> dict[str, Any]:
    relative, source, observed, expected = sample
    start, end, name_start, name_end = observed[0]
    planted = [(start, end - 1, name_start, name_end), *observed[1:]]
    found = readback_errors(relative, source, planted, expected)
    return {"rejected": bool(found), "path": relative, "planted": [start, end - 1], "detail": found[0] if found else ""}


def _planted_query_control(
    module: Any, language: Any, sample: tuple[str, bytes, list[tuple[int, int, int, int]], dict[tuple[int, int], str]]
) -> dict[str, Any]:
    relative, source, _observed, expected = sample
    wrong, parse_error = observed_definitions(module, language, source, PLANTED_WRONG_QUERY)
    if parse_error is not None or wrong is None:
        return {"rejected": False, "path": relative, "query": PLANTED_WRONG_QUERY, "detail": "planted query did not parse"}
    found = readback_errors(relative, source, wrong, expected)
    return {"rejected": bool(found), "path": relative, "query": PLANTED_WRONG_QUERY, "detail": found[0] if found else ""}


def _malformed_control(module: Any, language: Any) -> dict[str, Any]:
    observed, parse_error = observed_definitions(module, language, MALFORMED_SOURCE, DEFINITION_QUERY)
    bounded = (
        parse_error is not None
        and observed is None
        and 0 <= parse_error["start_byte"] < parse_error["end_byte"] <= len(MALFORMED_SOURCE)
    )
    return {"rejected": bounded, "source_bytes": len(MALFORMED_SOURCE), "detail": parse_error or "no parse error reported"}


def _unsupported_control(
    root: Path, relative: str, module: Any, language: Any, suffixes: tuple[str, ...], *, error_cls: type[Exception]
) -> dict[str, Any]:
    try:
        definitions_for_path(root, relative, module, language, suffixes, error_cls=error_cls)
    except error_cls as exc:
        return {"rejected": True, "path": relative, "detail": str(exc)}
    return {"rejected": False, "path": relative, "detail": "unsupported language was parsed anyway"}

"""Exact-commit SCIP code intelligence: the machine's navigation organ over a foreign clone.

The pins are not restated here. `policy/providers.lock.json` is their only writer, every live call
derives them from those bytes, and a binary is used only after its own bytes hash to the pinned
digest - so a tool that merely happens to sit on PATH is refused rather than trusted.

The lookup, readback, control, and admission core is pure and runs offline, so trusted CI proves the
oracle can go red with neither tool installed.

Non-claim: the reader's `binary_sha256` is the darwin/arm64 release artifact. On another platform the
digest check fails closed, which is the intended refusal and not a portability defect; moving a pin is
an explicit review, never an automatic pull.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Sequence

SCHEMA_VERSION = 1
CAPABILITY = "scip-semantic-graph"
LOCK_PATH = "policy/providers.lock.json"
CODE_INTEL_KEY = "code_intel"
PIN_ROLES = ("indexer", "reader")
AUTHORITY = "P"

# constraint: SCIP SymbolRole bitmask; bit 0 is Definition, every other role is a reference occurrence.
DEFINITION_ROLE = 1
# constraint: "local N" symbols are numbered per document, so the same id means different things in two files.
GLOBAL_SYMBOL_PREFIX = "scip-python python "
LOCAL_SYMBOL_PREFIX = "local "
CONTROL_UNCOVERED = "unsupported-coverage"
CONTROL_STALE = "stale-index"
# constraint: ed3c/noodles#294 - every terminal condition of the two verbs is its own declared state.
# constraint: a missing tool, a failed build, a stale index, and a real miss must never share one
# constraint: representation, because collapsing them is exactly how a receipt manufactures a
# constraint: misdiagnosis that reads like an answer.
CHECKOUT_INDEXED = "indexed"
CHECKOUT_INDEX_FAILED = "index-build-failed"
CHECKOUT_INDEXER_MISSING = "indexer-unavailable"
CHECKOUT_STATES = (CHECKOUT_INDEXED, CHECKOUT_INDEX_FAILED, CHECKOUT_INDEXER_MISSING)
LOOKUP_RESOLVED = "resolved"
LOOKUP_SYMBOL_NOT_FOUND = "symbol-not-found"
LOOKUP_READER_MISSING = "reader-unavailable"
LOOKUP_INDEX_MISMATCH = "index-mismatch"
LOOKUP_STATES = (LOOKUP_RESOLVED, LOOKUP_SYMBOL_NOT_FOUND, LOOKUP_READER_MISSING, LOOKUP_INDEX_MISMATCH)
CHECKOUT_FIELDS = (
    "schema_version",
    "capability",
    "verb",
    "state",
    "authority",
    "repository",
    "source",
    "commit",
    "tree",
    "clone_path",
    "indexer",
    "index",
    "non_claims",
)
LOOKUP_FIELDS = (
    "schema_version",
    "capability",
    "verb",
    "state",
    "authority",
    "checkout_receipt",
    "clone_path",
    "repository",
    "commit",
    "reader",
    "symbol",
    "definition",
    "controls",
    "non_claims",
)
CHECKOUT_NON_CLAIMS = (
    "The index digest is host-bound: metadata.project_root records an absolute path, so a different clone path yields a different sha256.",
    "Coverage is Python-only; every other tracked file is uncovered, and an uncovered file yields refusal, not absence proof.",
    "A built index proves the indexer ran at this commit, never that the code does what a downstream claim says.",
)
LOOKUP_NON_CLAIMS = (
    "'local N' symbols are numbered per document and are refused; only global symbols are looked up.",
    "A resolved definition is one exact-commit fact read back from the clone's own bytes, not a claim about current upstream state.",
    "symbol-not-found is a refusal to answer, never proof that the symbol does not exist.",
)
HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
FLOATING_REFS = frozenset({"latest", "main", "master", "head", "stable", "*", "@latest", "next"})


class ScipError(RuntimeError):
    """A fail-closed SCIP validation or admission failure."""


def _run(argv: Sequence[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(list(argv), cwd=None if cwd is None else str(cwd), text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise ScipError(f"{' '.join(argv)} failed: {result.stderr.strip() or result.stdout.strip()}")
    return result


def validate_code_intel_lock(root: Path) -> list[str]:
    """Deterministic pin gate: no tool, no clone, no network, so a floating or digest-free pin reds on
    every host - including hosted CI, where neither binary is installed."""
    path = Path(root) / LOCK_PATH
    try:
        pins = json.loads(path.read_text(encoding="utf-8"))[CODE_INTEL_KEY]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        return [f"invalid {LOCK_PATH} {CODE_INTEL_KEY} pins: {exc}"]
    if not isinstance(pins, dict):
        return [f"{LOCK_PATH} {CODE_INTEL_KEY} must be an object"]
    errors: list[str] = []
    if pins.get("authority") != AUTHORITY:
        errors.append(f"{CODE_INTEL_KEY} authority must be {AUTHORITY!r}; navigation never gates or lands")
    for role in PIN_ROLES:
        pin = pins.get(role)
        if not isinstance(pin, dict):
            errors.append(f"{CODE_INTEL_KEY} {role} pin must be an object")
            continue
        tool = str(pin.get("tool", ""))
        version = str(pin.get("version", ""))
        if not tool.strip():
            errors.append(f"{CODE_INTEL_KEY} {role} tool is required")
        if not version.strip() or version.strip().lower() in FLOATING_REFS:
            errors.append(f"{CODE_INTEL_KEY} {role} version must be an exact release, got {version!r}")
        if not HEX40_RE.fullmatch(str(pin.get("commit", ""))):
            errors.append(f"{CODE_INTEL_KEY} {role} commit must be an exact 40-hex object id")
        if not HEX64_RE.fullmatch(str(pin.get("binary_sha256", ""))):
            errors.append(
                f"{CODE_INTEL_KEY} {role} binary_sha256 must be a 64-hex digest; a tool resolved from "
                "ambient PATH without a digest check is refused"
            )
        if not str(pin.get("source", "")).startswith("https://github.com/"):
            errors.append(f"{CODE_INTEL_KEY} {role} source must be a GitHub HTTPS URL")
        argv = pin.get("version_argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(token, str) for token in argv) or argv[0] != tool:
            errors.append(f"{CODE_INTEL_KEY} {role} version_argv must be exact tokens starting with {tool!r}")
    return errors


def load_code_intel_pins(root: Path) -> dict[str, Any]:
    """The lock is the single writer for these pins; this module derives them and never restates them."""
    errors = validate_code_intel_lock(root)
    if errors:
        raise ScipError("; ".join(errors))
    return json.loads((Path(root) / LOCK_PATH).read_text(encoding="utf-8"))[CODE_INTEL_KEY]


def resolve_pinned_tool(pin: dict[str, Any]) -> dict[str, Any]:
    """The one door to a live tool: PATH proposes a path, the pinned digest decides whether it runs.

    Every refusal names the pin, because "the tool is missing" and "a different tool answered to the
    same name" are different repairs and must not read the same in a receipt."""
    named = f"{pin['tool']} {pin['version']} (commit {pin['commit']}, {LOCK_PATH})"
    resolved = shutil.which(str(pin["tool"]))
    if resolved is None:
        raise ScipError(f"pinned {named} is not installed on this host")
    real = Path(resolved).resolve()
    try:
        digest = hashlib.sha256(real.read_bytes()).hexdigest()
    except OSError as exc:
        raise ScipError(f"pinned {named} at {real} is unreadable: {exc}") from exc
    if digest != pin["binary_sha256"]:
        raise ScipError(f"pinned {named} resolved to {real} with digest {digest}, not the pinned {pin['binary_sha256']}")
    reported = _run([str(real), *list(pin["version_argv"])[1:]]).stdout.strip()
    if str(pin["version"]) not in reported:
        raise ScipError(f"pinned {named} reports {reported!r}, not the pinned version")
    return {"tool": str(pin["tool"]), "version": str(pin["version"]), "commit": str(pin["commit"]), "path": str(real), "sha256": digest}


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




def _write_receipt(path: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    receipt["receipt_path"] = str(path)
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def build_index(clone: Path, index_path: Path, indexer: dict[str, Any], project_name: str, project_version: str) -> float:
    """Build at the exact commit the caller asked about, so the index can never drift from the checkout."""
    started = time.monotonic()
    _run(
        [
            indexer["path"],
            "index",
            ".",
            "--project-name",
            project_name,
            "--project-version",
            project_version,
            "--output",
            str(index_path),
        ],
        cwd=clone,
    )
    return round(time.monotonic() - started, 3)


def read_index(index_path: Path, reader: dict[str, Any]) -> tuple[Any, float]:
    started = time.monotonic()
    payload = json.loads(_run([reader["path"], "print", "--json", str(index_path)]).stdout)
    return payload, round(time.monotonic() - started, 3)


def materialize_clone(destination: Path, source: str, commit: str) -> dict[str, str]:
    """Clone the target and read the checkout back from git, never from the argument that asked for it."""
    if not HEX40_RE.fullmatch(commit):
        raise ScipError(f"checkout requires an exact 40-hex commit, got {commit!r}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    _run(["git", "clone", "--quiet", "--no-checkout", source, str(destination)])
    _run(["git", "checkout", "--quiet", "--detach", commit], cwd=destination)
    head = _git(destination, "rev-parse", "HEAD")
    if head != commit:
        raise ScipError(f"clone readback {head} != requested {commit}")
    return {"head": head, "tree": _git(destination, "rev-parse", "HEAD^{tree}")}


def project_name_for(repository: str) -> str:
    return repository.rsplit("/", 1)[-1]


def symbol_for(project_name: str, commit: str, module: str, name: str) -> str:
    # constraint: the indexer stamps --project-version into every global symbol, so the symbol string
    # constraint: itself carries the exact commit and cannot be reused against another index.
    return f"{GLOBAL_SYMBOL_PREFIX}{project_name} {commit[:12]} {module}/{name}()."


def code_intel_checkout(session_dir: Path, repository: str, source: str, commit: str, *, pins: dict[str, Any]) -> dict[str, Any]:
    """Materialize the target clone at its exact commit and index it in the same step.

    The expensive half is automatic on purpose: no call site is left at which remembering to index is
    a discipline problem, because a cook never holds an unindexed foreign clone. Every terminal
    condition is a declared state on the one combined receipt, so a failed build can never read as an
    absent one."""
    session_dir = Path(session_dir).resolve()
    if not session_dir.is_dir():
        raise ScipError(f"code-intel session directory does not exist: {session_dir}")
    if not HEX40_RE.fullmatch(commit):
        raise ScipError(f"checkout requires an exact 40-hex commit, got {commit!r}")
    workspace = session_dir / "code-intel" / f"{repository.replace('/', '-')}-{commit[:12]}"
    clone = workspace / "clone"
    if clone.exists():
        shutil.rmtree(clone)
    provenance = materialize_clone(clone, source, commit)
    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "capability": CAPABILITY,
        "verb": "checkout",
        "authority": AUTHORITY,
        "state": CHECKOUT_INDEXED,
        "repository": repository,
        "source": source,
        "commit": provenance["head"],
        "tree": provenance["tree"],
        "clone_path": str(clone),
        "indexer": {},
        "index": {},
        "non_claims": list(CHECKOUT_NON_CLAIMS),
    }
    receipt_path = workspace / "checkout.json"
    try:
        indexer = resolve_pinned_tool(pins["indexer"])
    except ScipError as failure:
        receipt["state"] = CHECKOUT_INDEXER_MISSING
        receipt["indexer"] = {"diagnostic": str(failure)}
        return _write_receipt(receipt_path, receipt)
    receipt["indexer"] = indexer
    index_path = workspace / "index.scip"
    try:
        build_seconds = build_index(clone, index_path, indexer, project_name_for(repository), commit[:12])
    except ScipError as failure:
        receipt["state"] = CHECKOUT_INDEX_FAILED
        receipt["index"] = {"diagnostic": str(failure)}
        return _write_receipt(receipt_path, receipt)
    receipt["index"] = {
        "path": str(index_path),
        "sha256": _sha256(index_path),
        "bytes": index_path.stat().st_size,
        "build_seconds": build_seconds,
    }
    return _write_receipt(receipt_path, receipt)


def require_current_index(checkout: dict[str, Any]) -> Path:
    """Refuse a corrupted or commit-mismatched index before any reader runs.

    The digest recorded at build time must still be the digest of the bytes on disk, and the clone
    must still sit at the commit the index was stamped for. Both checks are pure file/git reads, so
    hosted CI runs them with neither pinned binary installed."""
    index = checkout.get("index") if isinstance(checkout, dict) else None
    index = index if isinstance(index, dict) else {}
    recorded = str(index.get("sha256", ""))
    path = Path(str(index.get("path", "")))
    if not HEX64_RE.fullmatch(recorded) or not path.is_file():
        raise ScipError(f"index-mismatch: the checkout receipt records no readable exact-commit index at {path}")
    observed = _sha256(path)
    if observed != recorded:
        raise ScipError(f"index-mismatch: {path} now digests {observed}, not the recorded {recorded}")
    clone = Path(str(checkout.get("clone_path", "")))
    head = _git(clone, "rev-parse", "HEAD")
    if head != str(checkout.get("commit", "")):
        raise ScipError(f"index-mismatch: {clone} now sits at {head}, not the indexed {checkout.get('commit')!r}")
    return path


def _lookup_controls(workspace: Path, clone: Path, payload: Any, definition_path: str, definition_range: Sequence[int], name: str) -> list[dict[str, Any]]:
    uncovered = next((path for path in _tracked(clone) if not path.endswith(".py")), "")
    if not uncovered:
        raise ScipError("no tracked non-Python file exists in the clone to plant the unsupported-coverage control against")
    stale_copy = workspace / "stale-source.py"
    stale_copy.write_bytes(rename_in_place((clone / definition_path).read_bytes(), definition_range))
    return [
        _control(
            CONTROL_UNCOVERED,
            f"a tracked non-Python file ({uncovered}) is outside the indexer's language coverage",
            lambda: require_covered(payload, uncovered),
        ),
        _control(
            CONTROL_STALE,
            "the definition is renamed in place, so the line count and every byte offset still match the index",
            lambda: verify_readback(stale_copy.parent, stale_copy.name, definition_range, name),
        ),
    ]


def code_intel_lookup(checkout_receipt_path: Path, module: str, name: str, *, pins: dict[str, Any]) -> dict[str, Any]:
    """Answer one exact-symbol question against one exact-commit index and record what answered.

    Lookups stay demand-driven: the checkout ceremony pays the build, this verb only spends a query,
    and each refusal keeps its own state so a downstream 'the code does X' carries its provenance."""
    checkout_receipt_path = Path(checkout_receipt_path).resolve()
    try:
        checkout = json.loads(checkout_receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScipError(f"cannot read checkout receipt {checkout_receipt_path}: {exc}") from exc
    admit_checkout_receipt(checkout, pins)
    workspace = checkout_receipt_path.parent
    clone = Path(str(checkout["clone_path"]))
    commit = str(checkout["commit"])
    symbol = symbol_for(project_name_for(str(checkout["repository"])), commit, module, name)
    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "capability": CAPABILITY,
        "verb": "lookup",
        "authority": AUTHORITY,
        "state": LOOKUP_RESOLVED,
        "checkout_receipt": str(checkout_receipt_path),
        "clone_path": str(clone),
        "repository": str(checkout["repository"]),
        "commit": commit,
        "reader": {},
        "symbol": symbol,
        "definition": {},
        "controls": [],
        "non_claims": list(LOOKUP_NON_CLAIMS),
    }
    receipt_path = workspace / f"lookup-{module.replace('/', '-')}-{name}.json"
    try:
        index_path = require_current_index(checkout)
    except ScipError as failure:
        receipt["state"] = LOOKUP_INDEX_MISMATCH
        receipt["diagnostic"] = str(failure)
        return _write_receipt(receipt_path, receipt)
    try:
        reader = resolve_pinned_tool(pins["reader"])
    except ScipError as failure:
        receipt["state"] = LOOKUP_READER_MISSING
        receipt["diagnostic"] = str(failure)
        return _write_receipt(receipt_path, receipt)
    receipt["reader"] = reader
    payload, read_seconds = read_index(index_path, reader)
    receipt["index_read_seconds"] = read_seconds
    try:
        definition_path, definition_range = definition_of(payload, symbol)
        text = verify_readback(clone, definition_path, definition_range, name)
    except ScipError as failure:
        receipt["state"] = LOOKUP_SYMBOL_NOT_FOUND
        receipt["diagnostic"] = str(failure)
        return _write_receipt(receipt_path, receipt)
    receipt["definition"] = {
        "path": definition_path,
        "range": list(definition_range),
        "line": int(definition_range[0]) + 1,
        "name": name,
        "text": text,
    }
    receipt["controls"] = _lookup_controls(workspace, clone, payload, definition_path, definition_range, name)
    return _write_receipt(receipt_path, receipt)


def _admit_shape(receipt: Any, fields: Sequence[str], states: Sequence[str], verb: str) -> None:
    if not isinstance(receipt, dict):
        raise ScipError(f"{verb} receipt must be a JSON object")
    missing = [field for field in fields if field not in receipt]
    if missing:
        raise ScipError(f"{verb} receipt is an agent self-report; missing physical fields: {', '.join(missing)}")
    if receipt["schema_version"] != SCHEMA_VERSION:
        raise ScipError(f"unsupported {verb} receipt schema: {receipt['schema_version']!r}")
    if receipt["capability"] != CAPABILITY:
        raise ScipError(f"{verb} receipt names capability {receipt['capability']!r}, not {CAPABILITY!r}")
    if receipt["verb"] != verb:
        raise ScipError(f"{verb} receipt names verb {receipt['verb']!r}")
    if receipt["authority"] != AUTHORITY:
        raise ScipError(f"{verb} receipt claims authority {receipt['authority']!r}, not {AUTHORITY!r}")
    if receipt["state"] not in states:
        raise ScipError(f"{verb} receipt declares undefined state {receipt['state']!r}; defined: {', '.join(states)}")
    if not receipt["non_claims"]:
        raise ScipError(f"{verb} receipt records no non-claims")


def _admit_tool(recorded: Any, pin: dict[str, Any], role: str, verb: str) -> None:
    if not isinstance(recorded, dict):
        raise ScipError(f"{verb} receipt records no {role}")
    named = [recorded.get(field) for field in ("tool", "version", "commit")]
    if named != [pin["tool"], pin["version"], pin["commit"]]:
        raise ScipError(f"{verb} receipt was produced by an unpinned {role}: {named}")
    if recorded.get("sha256") != pin["binary_sha256"]:
        raise ScipError(
            f"{verb} receipt records a {role} binary digest {recorded.get('sha256')!r}, not the pinned "
            f"{pin['binary_sha256']!r}; a tool resolved from ambient PATH without a digest check is refused"
        )


def admit_checkout_receipt(checkout: Any, pins: dict[str, Any]) -> dict[str, Any]:
    """Admit a checkout only when it names the pinned indexer by digest, an exact commit, and a built index."""
    _admit_shape(checkout, CHECKOUT_FIELDS, CHECKOUT_STATES, "checkout")
    if checkout["state"] != CHECKOUT_INDEXED:
        detail = (checkout.get("indexer") or {}).get("diagnostic") or (checkout.get("index") or {}).get("diagnostic")
        raise ScipError(f"checkout receipt state is {checkout['state']!r}: {detail or 'no diagnostic recorded'}")
    for field in ("commit", "tree"):
        if not HEX40_RE.fullmatch(str(checkout[field])):
            raise ScipError(f"checkout receipt {field} is not an exact 40-hex object id: {checkout[field]!r}")
    _admit_tool(checkout["indexer"], pins["indexer"], "indexer", "checkout")
    index = checkout["index"] if isinstance(checkout["index"], dict) else {}
    if not HEX64_RE.fullmatch(str(index.get("sha256", ""))):
        raise ScipError(f"checkout receipt index digest is not a sha256: {index.get('sha256')!r}")
    if int(index.get("bytes", 0)) <= 0:
        raise ScipError("checkout receipt records no built index")
    return checkout


def admit_lookup_receipt(receipt: Any, pins: dict[str, Any], *, root: Path | None = None) -> dict[str, Any]:
    """Admit a lookup only when the symbol carries the checkout's own commit, the pinned reader
    answered, the recorded range still spells the recorded name, and both planted controls failed."""
    _admit_shape(receipt, LOOKUP_FIELDS, LOOKUP_STATES, "lookup")
    if receipt["state"] != LOOKUP_RESOLVED:
        raise ScipError(f"lookup receipt state is {receipt['state']!r}: {receipt.get('diagnostic') or 'no diagnostic recorded'}")
    commit = str(receipt["commit"])
    if not HEX40_RE.fullmatch(commit):
        raise ScipError(f"lookup receipt commit is not an exact 40-hex object id: {commit!r}")
    if not str(receipt["checkout_receipt"]).strip():
        raise ScipError("lookup receipt names no checkout receipt")
    _admit_tool(receipt["reader"], pins["reader"], "reader", "lookup")
    symbol = str(receipt["symbol"])
    _require_global(symbol)
    definition = receipt["definition"] if isinstance(receipt["definition"], dict) else {}
    name = str(definition.get("name") or "")
    if not name or not symbol.endswith(f"/{name}()."):
        raise ScipError(f"lookup receipt symbol {symbol!r} does not name the read-back definition {name!r}")
    if f" {commit[:12]} " not in symbol:
        raise ScipError(f"lookup receipt symbol {symbol!r} was not produced at commit {commit}")
    if definition.get("text") != name:
        raise ScipError(f"lookup receipt readback text {definition.get('text')!r} does not spell {name!r}")
    if not str(definition.get("path") or "") or int(definition.get("line") or 0) < 1:
        raise ScipError("lookup receipt records no definition file and line")
    controls = receipt["controls"] if isinstance(receipt["controls"], list) else []
    recorded = {str(item.get("control")) for item in controls if isinstance(item, dict)}
    if recorded != {CONTROL_UNCOVERED, CONTROL_STALE}:
        raise ScipError(f"lookup receipt records controls {sorted(recorded)}, expected both planted controls")
    for item in controls:
        if item.get("rejected") is not True or not str(item.get("diagnostic") or "").strip():
            raise ScipError(f"planted control {item.get('control')!r} is not recorded as a proven failure")
    if root is not None:
        verify_readback(Path(root), str(definition["path"]), definition["range"], name)
    return receipt

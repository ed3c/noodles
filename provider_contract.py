from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
CONTROL_NOODLE_PROVIDER = "skill-concerns"
CONTROL_NOODLE_SKILL = "control-noodle"
CONTROL_NOODLE_DESTINATION = ".noodle/providers/skill-concerns"
CONTROL_NOODLE_DISCOVERY_ROOT = ".noodle/providers/skill-concerns/skills/control-noodle"
RETIRED_PROVIDER = "matt-engineering"
RETIRED_PROVIDER_DESTINATION = ".noodle/providers/matt-engineering"
RETIRED_PROVIDER_DISCOVERY_ROOT = ".noodle/providers/matt-engineering/skills/engineering"


def validate_admission_policy(provider_name: str, admission: Any) -> list[str]:
    if not isinstance(admission, dict):
        return [f"provider {provider_name} admission must be an object"]
    errors: list[str] = []
    if not admission.get("skill"):
        errors.append(f"provider {provider_name} admission skill is required")
    if not HEX64_RE.fullmatch(str(admission.get("sha256", ""))):
        errors.append(f"provider {provider_name} admission digest must be a 64-hex sha256")
    if not HEX64_RE.fullmatch(str(admission.get("skill_tree_sha256", ""))):
        errors.append(f"provider {provider_name} admission skill-tree digest must be a 64-hex sha256")
    admission_path = str(admission.get("path", ""))
    if not admission_path:
        errors.append(f"provider {provider_name} admission path is required")
    elif Path(admission_path).is_absolute() or ".." in Path(admission_path).parts:
        errors.append(f"provider {provider_name} admission path must stay under the provider checkout")
    subject_files = admission.get("subject_files")
    if not isinstance(subject_files, dict) or not subject_files:
        return errors + [f"provider {provider_name} admission subject_files must be a non-empty object"]
    for subject_path, sha256 in subject_files.items():
        if Path(str(subject_path)).is_absolute() or ".." in Path(str(subject_path)).parts:
            errors.append(f"provider {provider_name} admission subject file path must stay under the provider checkout")
        if not HEX64_RE.fullmatch(str(sha256)):
            errors.append(f"provider {provider_name} admission subject file digest must be a 64-hex sha256")
    return errors


def validate_enabled_provider_names(enabled_names: set[str], cursor_provider: str) -> list[str]:
    expected = {CONTROL_NOODLE_PROVIDER, cursor_provider}
    if enabled_names == expected:
        return []
    return [
        "enabled providers must be exactly "
        f"{CONTROL_NOODLE_PROVIDER} and {cursor_provider}; got {', '.join(sorted(enabled_names)) or '<empty>'}"
    ]


# constraint: ed3c/noodles#174 - a route bundle is a BYTE-PRESERVING CACHE of one route traversal:
# constraint: verbatim concatenation of the exact pinned files, each section addressed by its own
# constraint: sha256 and length-framed so no section body can be read as a boundary. "Compile" means
# constraint: assemble-and-address, never condense; a paraphrased or truncated section fails closed here.
ROUTE_BUNDLE_ROOT = ".noodle/bundles"
ROUTE_BUNDLE_VERSION = "noodles-route-bundle v1"
ROUTE_BUNDLE_HEADER_LINES = 5
SECTION_HEADER_RE = re.compile(
    r"^--- noodles-bundle-section (?P<index>\d+) (?P<path>\S+) sha256=(?P<digest>[0-9a-f]{64}) bytes=(?P<size>\d+) ---$"
)


def route_bundle_path(route: str) -> str:
    return f"{ROUTE_BUNDLE_ROOT}/{route}.md"


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _section_header(index: int, relative: str, body: bytes) -> bytes:
    return f"--- noodles-bundle-section {index} {relative} sha256={_sha256(body)} bytes={len(body)} ---\n".encode()


def assemble_route_bundle(
    source_root: Path, *, route: str, provider: str, commit: str, paths: Sequence[str]
) -> bytes:
    chunks = [
        (
            f"{ROUTE_BUNDLE_VERSION}\n"
            f"route: {route}\n"
            f"provider: {provider}\n"
            f"commit: {commit}\n"
            f"sections: {len(paths)}\n"
        ).encode()
    ]
    for index, relative in enumerate(paths):
        body = (source_root / relative).read_bytes()
        chunks.extend((_section_header(index, relative, body), body, b"\n"))
    return b"".join(chunks)


def _parse_route_bundle(payload: bytes) -> tuple[dict[str, str], list[tuple[str, str, bytes]]]:
    parts = payload.split(b"\n", ROUTE_BUNDLE_HEADER_LINES)
    if len(parts) <= ROUTE_BUNDLE_HEADER_LINES:
        raise ValueError("header is truncated")
    header_lines = [line.decode("utf-8", "replace") for line in parts[:ROUTE_BUNDLE_HEADER_LINES]]
    header = {"version": header_lines[0]}
    for line in header_lines[1:]:
        key, separator, value = line.partition(": ")
        if not separator:
            raise ValueError(f"unparseable header line {line!r}")
        header[key] = value
    sections: list[tuple[str, str, bytes]] = []
    cursor = parts[ROUTE_BUNDLE_HEADER_LINES]
    while cursor:
        raw_header, separator, remainder = cursor.partition(b"\n")
        if not separator:
            raise ValueError("section header is unterminated")
        match = SECTION_HEADER_RE.match(raw_header.decode("utf-8", "replace"))
        if match is None:
            raise ValueError(f"unparseable section header {raw_header.decode('utf-8', 'replace')!r}")
        if int(match["index"]) != len(sections):
            raise ValueError(f"section index {match['index']} is out of traversal order")
        size = int(match["size"])
        body = remainder[:size]
        if len(body) != size or remainder[size : size + 1] != b"\n":
            raise ValueError(f"section {match['path']} body is not {size} framed bytes")
        sections.append((match["path"], match["digest"], body))
        cursor = remainder[size + 1 :]
    return header, sections


def check_route_bundle(
    payload: bytes,
    source_root: Path,
    *,
    route: str,
    provider: str,
    commit: str,
    expected_paths: Sequence[str],
) -> dict[str, Any]:
    try:
        header, sections = _parse_route_bundle(payload)
    except ValueError as exc:
        return {"errors": [f"route bundle {route} is unparseable: {exc}"], "bundle_fed_sha256": None, "live_loaded_sha256": None}
    errors = [
        f"route bundle {route} header {key} is {header.get(key)!r}; expected {value!r}"
        for key, value in (
            ("version", ROUTE_BUNDLE_VERSION),
            ("route", route),
            ("provider", provider),
            ("commit", commit),
            ("sections", str(len(expected_paths))),
        )
        if header.get(key) != value
    ]
    traversal = [path for path, _digest, _body in sections]
    if traversal != list(expected_paths):
        return {
            "errors": errors + [f"route bundle {route} traversal is {traversal}; expected {list(expected_paths)}"],
            "bundle_fed_sha256": None,
            "live_loaded_sha256": None,
        }
    live: list[bytes] = []
    for path, digest, body in sections:
        pinned = source_root / path
        if not pinned.is_file():
            errors.append(f"route bundle {route} section {path} has no pinned file at {pinned}")
            continue
        pinned_bytes = pinned.read_bytes()
        live.append(pinned_bytes)
        pinned_digest = _sha256(pinned_bytes)
        if digest != pinned_digest:
            errors.append(f"route bundle {route} section {path} digest {digest} != pinned {pinned_digest}")
        if body != pinned_bytes:
            errors.append(f"route bundle {route} section {path} bytes differ from the pinned file")
    return {
        "errors": errors,
        "bundle_fed_sha256": _sha256(b"".join(body for _path, _digest, body in sections)),
        "live_loaded_sha256": _sha256(b"".join(live)) if len(live) == len(sections) else None,
    }


# constraint: ed3c/noodles#170 - ONE lane-health receipt, TWO provider dialects. The dialect branch
# constraint: lives inside normalize_lane_events and nowhere else; lane_health and provider_reading
# constraint: are typed to take normalized KINDS, so no provider-specific branch can reach the output
# constraint: boundary even by accident. tests/test_route_bundles.py::LaneOutputBoundaryTests holds
# constraint: that mechanically: the same normalized sequence, expressed in each dialect's own raw
# constraint: events, must produce receipts differing in nothing but the provider name, and the
# constraint: receipt key set must be identical across every dialect and every health state.
# constraint: Do NOT design a second event protocol here. Both dialects are streams this host and
# constraint: this repository already produce: `codex exec --json` typed JSONL (recorded verbatim in
# constraint: tests/fixtures/lane-events-codex-turn-completed.jsonl, codex-cli 0.149.0) and the
# constraint: Noodle session event log this repository writes through
# constraint: runtime_contract.emit_session_event and reads through runtime_contract.read_session_events.
LANE_DIALECT_CODEX = "codex"
LANE_DIALECT_CLAUDE = "claude"
LANE_DIALECTS = (LANE_DIALECT_CODEX, LANE_DIALECT_CLAUDE)

LANE_STARTED = "started"
LANE_PROGRESS = "progress"
LANE_NOTICE = "notice"
LANE_PARKED = "parked"
LANE_COMPLETED = "completed"
LANE_FAILED = "failed"

LANE_HEALTHY = "HEALTHY"
LANE_QUIET_VALID = "QUIET_VALID"
LANE_SUSPECTED_STALLED = "SUSPECTED_STALLED"
LANE_DEAD = "DEAD"
LANE_COMPLETED_UNRECONCILED = "COMPLETED_UNRECONCILED"
LANE_BLOCKED_EXTERNAL = "BLOCKED_EXTERNAL"
LANE_HEALTH_STATES = (
    LANE_HEALTHY,
    LANE_QUIET_VALID,
    LANE_SUSPECTED_STALLED,
    LANE_DEAD,
    LANE_COMPLETED_UNRECONCILED,
    LANE_BLOCKED_EXTERNAL,
)

PROVIDER_SERVED = "served"
PROVIDER_REFUSED = "refused"
PROVIDER_UNOBSERVED = "unobserved"

# constraint: ed3c/noodles#260 is the sibling rule this map obeys: a lane's terminal state may come
# constraint: only from these typed event names or from the process exit status, never from a
# constraint: substring of any message. `item.completed` needs the item's own type and is decided in
# constraint: _codex_lane_event rather than here.
CODEX_LANE_EVENT_KINDS = {
    "thread.started": LANE_STARTED,
    "turn.started": LANE_STARTED,
    "turn.completed": LANE_COMPLETED,
    "turn.failed": LANE_FAILED,
    "error": LANE_FAILED,
}
# constraint: the Claude harness dialect is the Noodle session event log, and these are the only
# constraint: three types anything on this host puts into it: `stage_message` and
# constraint: `handoff_verify_rerun_intent` are emitted by this repository itself through
# constraint: runtime_contract.emit_session_event, and `action` is the noodle runtime's own, mirrored
# constraint: in tests.support.handoff_fixture. The asymmetry is disclosed rather than
# constraint: papered over: that stream carries no terminal lifecycle event, so a Claude lane's
# constraint: terminal state is decided by the process-exit lane, and the receipt names which lane
# constraint: decided it. Inventing `agent.completed` here to make the two dialects look alike would
# constraint: be a second event protocol with no emitter - the thing the rescope forbids.
CLAUDE_LANE_EVENT_KINDS = {
    "action": LANE_PROGRESS,
    "stage_message": LANE_PROGRESS,
    "handoff_verify_rerun_intent": LANE_PROGRESS,
}


def _codex_lane_event(event: Mapping[str, Any]) -> tuple[str | None, str | None, dict[str, Any] | None]:
    event_type = str(event.get("type") or "")
    if event_type == "item.completed":
        item = event.get("item")
        if not isinstance(item, Mapping):
            return None, None, None
        if str(item.get("type") or "") == "error":
            return LANE_NOTICE, str(item.get("message") or "") or None, None
        return LANE_PROGRESS, None, None
    kind = CODEX_LANE_EVENT_KINDS.get(event_type)
    if kind is None:
        return None, None, None
    usage = event.get("usage")
    error = event.get("error")
    detail = str(error["message"]) if isinstance(error, Mapping) and error.get("message") is not None else None
    if detail is None and event.get("message") is not None:
        detail = str(event["message"])
    return kind, detail, dict(usage) if isinstance(usage, Mapping) else None


def _claude_lane_event(event: Mapping[str, Any]) -> tuple[str | None, str | None, dict[str, Any] | None]:
    kind = CLAUDE_LANE_EVENT_KINDS.get(str(event.get("type") or ""))
    if kind is None:
        return None, None, None
    payload = event.get("payload") if isinstance(event.get("payload"), Mapping) else {}
    detail = str(payload.get("message") or "") or None
    if payload.get("blocking") is True:
        return LANE_PARKED, detail, None
    return kind, detail, None


def normalize_lane_events(
    dialect: str, events: Sequence[Mapping[str, Any]], *, error_cls: type[Exception]
) -> dict[str, Any]:
    """One dialect's raw lifecycle events as normalized lane kinds, plus what it could not type.

    This is the adapter's only provider branch. An event type the dialect map does not know is
    RECORDED in `unmapped_types` rather than guessed at or dropped silently, so a stream that grew a
    new lifecycle event shows up as a named absence instead of quietly changing a verdict."""
    mappers = {LANE_DIALECT_CODEX: _codex_lane_event, LANE_DIALECT_CLAUDE: _claude_lane_event}
    mapper = mappers.get(dialect)
    if mapper is None:
        raise error_cls(f"unknown lane event dialect {dialect!r}; admitted dialects: {', '.join(LANE_DIALECTS)}")
    normalized: list[dict[str, Any]] = []
    unmapped: list[str] = []
    for index, event in enumerate(events):
        if not isinstance(event, Mapping):
            raise error_cls(f"lane event {index} is not an object")
        kind, detail, usage = mapper(event)
        if kind is None:
            unmapped.append(str(event.get("type") or ""))
            continue
        normalized.append({"kind": kind, "index": index, "detail": detail, "usage": usage})
    return {"events": normalized, "unmapped_types": sorted(set(unmapped))}


def lane_terminal_state(kinds: Sequence[str], exit_status: int | None) -> dict[str, Any]:
    """Terminal state from the two typed sources only: the lane's kinds and the process exit status.

    Same conflict rule as codex_isolation.codex_terminal_state and for the same reason: a non-zero
    exit outranks a completed kind because the process is the outer contract, and a `failed` kind
    outranks a zero exit because a stream that reported its own failure is not a success whatever
    the shell said. `exit_status=None` is "has not exited", never a stand-in for zero."""
    terminal_kinds = [kind for kind in kinds if kind in {LANE_COMPLETED, LANE_FAILED}]
    last = terminal_kinds[-1] if terminal_kinds else None
    if exit_status is not None and int(exit_status) != 0:
        return {"state": LANE_FAILED, "terminal": True, "source": "process_exit", "exit_status": exit_status}
    if last is not None:
        return {"state": last, "terminal": True, "source": "lane_event", "exit_status": exit_status}
    if exit_status is not None:
        return {"state": LANE_COMPLETED, "terminal": True, "source": "process_exit", "exit_status": exit_status}
    return {"state": "running", "terminal": False, "source": None, "exit_status": None}


def provider_reading(kinds: Sequence[str], terminal: Mapping[str, Any], usage: Mapping[str, Any] | None) -> dict[str, Any]:
    """What this lane's own lifecycle events measured about the provider that served it.

    Three readings, each with a written antecedent and none of them inferred from message text:
    `served` - the provider emitted work (progress, a notice, or a completed turn); `refused` - the
    lane reached a failed terminal having emitted no work at all, so the provider never served this
    lane; `unobserved` - the stream says nothing either way, which is a distinct answer from "not
    available" and must never be collapsed into one.

    Ceiling, stated rather than implied: there is deliberately NO `exhausted`/quota reading. No typed
    event either dialect emits on this host distinguishes a quota refusal from any other refusal, and
    a label this adapter cannot measure would be a guess wearing a typed name. What IS measured is
    published instead - the provider's own `usage` object, carried verbatim off `turn.completed` -
    so a consumer that needs a budget verdict reads numbers rather than this module's opinion."""
    served = any(kind in {LANE_PROGRESS, LANE_NOTICE, LANE_COMPLETED} for kind in kinds)
    if served:
        reading, available = PROVIDER_SERVED, True
    elif terminal["state"] == LANE_FAILED:
        reading, available = PROVIDER_REFUSED, False
    else:
        reading, available = PROVIDER_UNOBSERVED, None
    return {"reading": reading, "available": available, "usage": dict(usage) if usage else None}


def lane_health(
    kinds: Sequence[str],
    terminal: Mapping[str, Any],
    reading: Mapping[str, Any],
    *,
    silent_seconds: float | None,
    quiet_grace_seconds: float,
    reconciled: bool | None,
) -> str:
    """One of LANE_HEALTH_STATES, from normalized kinds only - no dialect reaches this function.

    The table, written out because every row has to be defensible:

    * failed terminal, provider never served this lane -> BLOCKED_EXTERNAL. The lane did no work and
      the provider refused it, so the fault is outside the lane.
    * failed terminal after the provider served work -> DEAD. The lane ran and then died.
    * completed terminal, reconciliation confirmed -> HEALTHY.
    * completed terminal otherwise -> COMPLETED_UNRECONCILED. Unobserved reconciliation is NOT
      reconciliation: an absent fourth evidence lane must land in the state a human looks at.
    * still running, last kind parked -> BLOCKED_EXTERNAL. The lane declared it is waiting on someone
      else, which is the one thing a lane can say about its own blockage.
    * still running, liveness unobserved -> QUIET_VALID. With no silence measurement a stall cannot be
      suspected, so this is the honest reading rather than a default to health.
    * still running inside the grace -> HEALTHY.
    * still running past the grace with nothing in flight but a start (or nothing at all yet) ->
      QUIET_VALID. A started turn emits nothing while the model works; that silence is explained.
    * still running past the grace mid-stream -> SUSPECTED_STALLED. Suspected, never asserted."""
    if terminal["state"] == LANE_FAILED:
        return LANE_BLOCKED_EXTERNAL if reading["reading"] == PROVIDER_REFUSED else LANE_DEAD
    if terminal["state"] == LANE_COMPLETED:
        return LANE_HEALTHY if reconciled is True else LANE_COMPLETED_UNRECONCILED
    if kinds and kinds[-1] == LANE_PARKED:
        return LANE_BLOCKED_EXTERNAL
    if silent_seconds is None:
        return LANE_QUIET_VALID
    if float(silent_seconds) <= float(quiet_grace_seconds):
        return LANE_HEALTHY
    return LANE_QUIET_VALID if not kinds or kinds[-1] == LANE_STARTED else LANE_SUSPECTED_STALLED


def lane_health_receipt(
    dialect: str,
    events: Sequence[Mapping[str, Any]],
    *,
    quiet_grace_seconds: float,
    exit_status: int | None = None,
    silent_seconds: float | None = None,
    reconciled: bool | None = None,
    error_cls: type[Exception] = ValueError,
) -> dict[str, Any]:
    """One lane-health receipt, whichever provider dialect the events came in as.

    `quiet_grace_seconds` is required rather than defaulted: the threshold is the caller's policy
    value, and a number baked in here would be a threshold living in code.

    The four evidence lanes reach this as four arguments, each with an explicit unobserved reading:
    the provider's own events, the process exit status, the elapsed silence, and `reconciled` - the
    one bit the noodles journal and the repository movement both answer ("did this lane's completion
    show up anywhere outside the provider's own stream"). None means not observed, never False."""
    normalized = normalize_lane_events(dialect, events, error_cls=error_cls)
    kinds = [str(item["kind"]) for item in normalized["events"]]
    usage = next((item["usage"] for item in reversed(normalized["events"]) if item["usage"]), None)
    terminal = lane_terminal_state(kinds, exit_status)
    reading = provider_reading(kinds, terminal, usage)
    return {
        "provider": {"name": dialect, **reading},
        "health": lane_health(
            kinds,
            terminal,
            reading,
            silent_seconds=silent_seconds,
            quiet_grace_seconds=quiet_grace_seconds,
            reconciled=reconciled,
        ),
        "terminal": terminal,
        "kinds": kinds,
        "notices": [item["detail"] for item in normalized["events"] if item["kind"] == LANE_NOTICE and item["detail"]],
        "unmapped_types": normalized["unmapped_types"],
        "observed": {"exit_status": exit_status, "silent_seconds": silent_seconds, "reconciled": reconciled},
    }


def validate_skill_config_paths(skill_paths: list[str]) -> list[str]:
    errors: list[str] = []
    if CONTROL_NOODLE_DISCOVERY_ROOT not in skill_paths:
        errors.append(f".noodle.toml skills.paths must include {CONTROL_NOODLE_DISCOVERY_ROOT}")
    if RETIRED_PROVIDER_DISCOVERY_ROOT in skill_paths:
        errors.append(".noodle.toml skills.paths must not retain retired matt-engineering discovery")
    return errors

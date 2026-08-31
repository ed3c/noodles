"""One typed, read-only Issue contract: exact dependency markers plus schedulability derived from
provider truth. A predecessor's own landed/closed readback is the only dependency-waiting state, so a
landing cannot strand its dependents behind a mirrored marker nobody patched."""
from __future__ import annotations

import hashlib
import re
from typing import Any

SUBJECT_RE = re.compile(r"^(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(?P<number>[1-9][0-9]*)$")
SECTION_RE = re.compile(r"(?m)^##[ \t]+(?P<heading>\S[^\n]*?)[ \t]*$")
DEPENDENCY_PROSE_RE = re.compile(r"(?i)depend|predecessor|blocked by|waiting|#[0-9]")
DEPENDENCY_DECLARATION_RE = re.compile(
    r"(?im)^[ \t]*(?:[-*+][ \t]+)?\**(?:depends[ \t]+on|blocked[ \t]+by|predecessors?)\**[ \t]*:?[ \t]*(?P<targets>[^\n]*)$"
)
ISSUE_REFERENCE_RE = re.compile(r"(?:(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+))?#(?P<number>[1-9][0-9]*)")
NO_DEPENDENCY_WORDS = {"", "-", "n/a", "none", "nothing"}
NO_DEPENDENCIES = "none"
REQUIRED_SECTIONS = ("goal", "physical_acceptance", "non_claims")
NO_WRITE_BOUNDARY = "none"
WRITE_BOUNDARY_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _boundary_segments(prefix: str) -> tuple[str, ...] | None:
    # constraint: ed3c/noodles#98 - a write boundary entry is one exact relative
    # constraint: path prefix; an absolute path, a parent escape, or any prose
    # constraint: token is not a prefix and makes the whole declaration ambiguous.
    raw = prefix.strip()
    if not raw or raw.startswith("/"):
        return None
    trimmed = raw.rstrip("/")
    if not trimmed:
        return None
    segments = trimmed.split("/")
    for segment in segments:
        if segment in {".", ".."} or not WRITE_BOUNDARY_SEGMENT_RE.match(segment):
            return None
    return tuple(segments)


def parse_write_boundary(raw: str | None) -> tuple[str, ...] | None:
    # constraint: ed3c/noodles#98 - one typed write-boundary field of exact path
    # constraint: prefixes with an explicit NO_WRITE_BOUNDARY for a lane that
    # constraint: reserves nothing; a missing, prose, or otherwise ambiguous
    # constraint: boundary returns None so admission fails it closed rather than
    # constraint: parsing a partial or invented surface.
    value = (raw or "").strip()
    if not value:
        return None
    if value.lower() == NO_WRITE_BOUNDARY:
        return ()
    prefixes: list[str] = []
    for token in (item.strip() for item in value.split(",")):
        segments = _boundary_segments(token)
        if segments is None:
            return None
        normalized = "/".join(segments)
        if normalized not in prefixes:
            prefixes.append(normalized)
    return tuple(prefixes) if prefixes else None


def boundary_conflict(candidate: tuple[str, ...], active: tuple[str, ...]) -> str | None:
    # constraint: ed3c/noodles#98 - two declared surfaces intersect when either
    # constraint: prefix path-contains the other (segment-wise, so tests never
    # constraint: collides with tests2); the more specific prefix names the
    # constraint: intersecting surface for the rejection diagnostic.
    for candidate_prefix in candidate:
        candidate_segments = tuple(candidate_prefix.split("/"))
        for active_prefix in active:
            active_segments = tuple(active_prefix.split("/"))
            shorter, longer = sorted((candidate_segments, active_segments), key=len)
            if longer[: len(shorter)] == shorter:
                return "/".join(longer)
    return None


def derive_dependencies(body: str, subject: str) -> str | None:
    """Derive the typed marker value an author never declared, or None when it is not mechanical.

    Only explicit declaration lines are converted, and a body carrying no declaration line at all
    derives NO_DEPENDENCIES. Anything ambiguous stays a named defect for a human, so a tightening
    that newly requires the marker migrates the derivable backlog instead of stranding it."""
    repo = subject.partition("#")[0]
    derived: list[str] = []
    for match in DEPENDENCY_DECLARATION_RE.finditer(body or ""):
        declaration = match.group("targets").strip()
        if declaration.lower().rstrip(".").strip() in NO_DEPENDENCY_WORDS:
            continue
        references = list(ISSUE_REFERENCE_RE.finditer(declaration))
        if not references:
            return None
        for reference in references:
            owner = reference.group("repo") or repo
            token = f"{owner}#{reference.group('number')}"
            if owner != repo or token == subject:
                return None
            if token not in derived:
                derived.append(token)
    return ", ".join(derived) if derived else NO_DEPENDENCIES


def parse_dependencies(raw: str | None, subject: str, *, error_cls: type[Exception]) -> tuple[str, ...]:
    value = (raw or "").strip()
    if value == NO_DEPENDENCIES:
        return ()
    if not value:
        raise error_cls(f"noodles-depends-on must be exactly {NO_DEPENDENCIES!r} or comma-separated owner/repo#N subjects")
    repo = subject.partition("#")[0]
    dependencies: list[str] = []
    for token in (item.strip() for item in value.split(",")):
        match = SUBJECT_RE.fullmatch(token)
        if not match:
            raise error_cls(
                f"noodles-depends-on entry {token!r} is not one exact owner/repo#N subject; "
                f"use {NO_DEPENDENCIES!r} for no dependencies"
            )
        if match.group("repo") != repo:
            raise error_cls(f"noodles-depends-on entry {token} is outside the issue repository {repo}")
        if token == subject:
            raise error_cls(f"noodles-depends-on entry {token} is the issue's own subject")
        if token in dependencies:
            raise error_cls(f"duplicate noodles-depends-on entry: {token}")
        dependencies.append(token)
    return tuple(dependencies)


def parse_blocker(raw: str | None, state: str, *, error_cls: type[Exception]) -> dict[str, str] | None:
    value = (raw or "").strip()
    if state != "blocked":
        if value:
            raise error_cls("noodles-blocker is valid only with noodles-state: blocked")
        return None
    owner, separator, reason = value.partition(":")
    if not separator or not owner.strip() or not reason.strip():
        raise error_cls(
            "noodles-state: blocked requires <!-- noodles-blocker: owner: reason --> naming the exact blocker owner"
        )
    if DEPENDENCY_PROSE_RE.search(value):
        raise error_cls(
            "noodles-blocker must name a blocker distinct from dependency waiting; "
            "dependency eligibility is derived from provider readback"
        )
    return {"owner": owner.strip(), "reason": reason.strip()}


def sections(body: str) -> dict[str, str]:
    text = body or ""
    matches = list(SECTION_RE.finditer(text))
    parsed: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        key = re.sub(r"[^a-z0-9]+", "_", match.group("heading").lower()).strip("_")
        parsed[key] = text[match.end() : end].strip()
    return parsed


def body_digest(body: str) -> str:
    return hashlib.sha256((body or "").encode("utf-8")).hexdigest()


def derive_schedulability(
    contract: dict[str, Any],
    provider_state: str,
    dependency_states: dict[str, dict[str, Any]],
    body_sections: dict[str, str],
) -> dict[str, Any]:
    reasons: list[str] = []
    if provider_state != "open":
        reasons.append(f"issue provider state is {provider_state!r}, not open")
    if contract.get("state") != "ready":
        reasons.append(f"issue state marker is {contract.get('state')!r}, not ready")
    blocker = contract.get("blocker")
    if blocker:
        reasons.append(f"blocker owned by {blocker['owner']}: {blocker['reason']}")
    for name in REQUIRED_SECTIONS:
        if not (body_sections.get(name) or "").strip():
            reasons.append(f"issue body has no '## {name.replace('_', ' ')}' section")
    if contract.get("dependencies") is None:
        reasons.append(f"issue declares no noodles-depends-on marker; use {NO_DEPENDENCIES!r} for no dependencies")
    for dependency in contract.get("dependencies") or ():
        observed = dependency_states.get(dependency)
        if observed is None:
            reasons.append(f"dependency {dependency} was never read back from the provider")
        elif observed.get("error"):
            reasons.append(f"dependency {dependency} provider read failed: {observed['error']}")
        elif observed.get("provider_state") != "closed" or observed.get("state") != "landed":
            reasons.append(
                f"dependency {dependency} is provider_state={observed.get('provider_state')!r} "
                f"state={observed.get('state')!r}, not closed and landed"
            )
    return {"schedulable": not reasons, "reasons": reasons}

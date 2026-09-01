"""One typed, read-only Issue contract: exact dependency markers plus schedulability derived from
provider truth. A predecessor's own landed/closed readback is the only dependency-waiting state, so a
landing cannot strand its dependents behind a mirrored marker nobody patched."""
from __future__ import annotations

import hashlib
import re
from typing import Any, Collection, Sequence

SUBJECT_RE = re.compile(r"^(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#(?P<number>[1-9][0-9]*)$")
SECTION_RE = re.compile(r"(?m)^##[ \t]+(?P<heading>\S[^\n]*?)[ \t]*$")
# constraint: ed3c/noodles#120 monitor reconcile - an HTML comment or fenced example is guidance, not
# constraint: an authored assertion (same rule skill_contract._document_body already applies to
# constraint: SKILL.md/AGENTS.md); without stripping them, a section left as the template's own
# constraint: placeholder comment reads as "filled in" and the completeness gate cannot tell an
# constraint: untouched template from a completed one.
FENCE_RE = re.compile(r"(?ms)^```[^\n]*\n.*?^```[ \t]*$")
HTML_COMMENT_RE = re.compile(r"(?s)<!--.*?-->")
DEPENDENCY_PROSE_RE = re.compile(r"(?i)depend|predecessor|blocked by|waiting|#[0-9]")
DEPENDENCY_DECLARATION_RE = re.compile(
    r"(?im)^[ \t]*(?:[-*+][ \t]+)?\**(?:depends[ \t]+on|blocked[ \t]+by|predecessors?)\**[ \t]*:?[ \t]*(?P<targets>[^\n]*)$"
)
ISSUE_REFERENCE_RE = re.compile(r"(?:(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+))?#(?P<number>[1-9][0-9]*)")
NO_DEPENDENCY_WORDS = {"", "-", "n/a", "none", "nothing"}
NO_DEPENDENCIES = "none"
# constraint: ed3c/noodles#120 - `ready` is necessary but not sufficient. `claim` joins the typed
# constraint: sections a repository-mutating Issue must carry non-empty before it is schedulable.
REQUIRED_SECTIONS = ("goal", "claim", "physical_acceptance", "non_claims")
# constraint: ed3c/noodles#120 - a stable requirement identity is exactly one `### ID` heading in the
# constraint: specification. No JSON/YAML registry, no generated mirror, no mutable status store: the
# constraint: headings are the identities, read directly from the document that owns them.
REQUIREMENT_ID_RE = re.compile(r"^[A-Z][A-Z0-9_.-]+$")
SPEC_REQUIREMENT_HEADING_RE = re.compile(r"(?m)^### (?P<id>[A-Z][A-Z0-9_.-]+)$")
MAX_REQUIREMENTS = 4
# constraint: ed3c/noodles#120 - the rationale section is `## Physical trigger` or one heading from
# constraint: the admitted `Why ...` family, which is how the landed split atoms ed3c/noodles#252 and
# constraint: ed3c/noodles#253 already state theirs. Two rules, both closed and deterministic.
RATIONALE_SECTION = "physical_trigger"
RATIONALE_PREFIX = "why_"
NON_CASE_SECTION = "non_case"
NON_CASE_NONE = "none"
# constraint: ed3c/noodles#120 - each obligation is a small closed vocabulary, not one exact
# constraint: sentence: the gate checks that the acceptance NAMES the obligation, so rewording is
# constraint: free and adding a synonym is a deliberate, reviewable widening.
ACCEPTANCE_OBLIGATIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("positive control", ("positive control", "positive:", "positive/planted", "positive and planted")),
    ("planted-negative control", ("planted-negative", "planted negative", "negative control", "positive/planted")),
    ("direct readback", ("readback",)),
    ("zero-residue readback", ("residue", "cleanup")),
)
PROVIDER_AUTHORITY_TOKENS = ("provider", "github")
PROVIDER_READBACK_TOKENS = ("provider readback", "provider-body", "provider body", "provider/direct", "closure readback", "merge readback", "provider landing")
NO_WRITE_BOUNDARY = "none"
WRITE_BOUNDARY_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._-]+$")
LOCAL_LANE = "local-noodle"
HOSTED_LANES = ("gha-agentic", "gha-runtime")
EXECUTOR_LANES = ("gha-agentic", "gha-runtime", LOCAL_LANE)
EPHEMERAL_CHECKOUT = "ephemeral-branch"
MANAGED_WORKTREE = "managed-worktree"
# constraint: ed3c/noodles#187 - one bounded capability table, data and not a policy
# constraint: DSL: each declared token names the exact lanes that can physically
# constraint: supply it, and admission is the intersection over the declared tokens.
# constraint: GitHub-hosted lanes supply only portable, non-interactive, bounded
# constraint: jobs with no private device or network dependency; hardware/USB,
# constraint: GUI or simulator interaction, private LAN/VPN, host-only credentials,
# constraint: persistent cross-run state, an unsupported host toolchain, and work
# constraint: outside the hosted time/resource envelope are local-only. `none` is
# constraint: contradictory on gha-runtime because that lane exists to execute one.
CAPABILITY_TABLE: dict[str, dict[str, tuple[str, ...]]] = {
    "runtime": {
        "bun-ts": EXECUTOR_LANES,
        "python": EXECUTOR_LANES,
        "shell": EXECUTOR_LANES,
        "none": ("gha-agentic", LOCAL_LANE),
        "usb-device": (LOCAL_LANE,),
        "gui-simulator": (LOCAL_LANE,),
        "private-network": (LOCAL_LANE,),
        "persistent-daemon": (LOCAL_LANE,),
        "host-toolchain": (LOCAL_LANE,),
        "unbounded-duration": (LOCAL_LANE,),
    },
    "evidence": {
        "github-only-v1": EXECUTOR_LANES,
        "drive-full-v1": (LOCAL_LANE,),
    },
}
CAPABILITY_MARKERS = ("executor", *sorted(CAPABILITY_TABLE))


def _one_token(marker: str, raw: str, admitted: tuple[str, ...], *, error_cls: type[Exception]) -> str:
    # constraint: ed3c/noodles#187 - malformed (not one bare token) and unknown (a
    # constraint: bare token outside the table) are separate deterministic
    # constraint: diagnostics, so a typo never reads as an unsupported capability.
    value = raw.strip()
    admitted_text = ", ".join(admitted)
    if not value or "," in value or any(character.isspace() for character in value):
        raise error_cls(
            f"malformed noodles-{marker} {raw!r}: expected exactly one token from {admitted_text}"
        )
    if value not in admitted:
        raise error_cls(f"unknown noodles-{marker} {value!r}; admitted tokens: {admitted_text}")
    return value


def parse_executor(raw: str | None, *, error_cls: type[Exception]) -> str | None:
    return None if raw is None else _one_token("executor", raw, EXECUTOR_LANES, error_cls=error_cls)


def parse_capability(marker: str, raw: str | None, *, error_cls: type[Exception]) -> str | None:
    admitted = tuple(sorted(CAPABILITY_TABLE[marker]))
    return None if raw is None else _one_token(marker, raw, admitted, error_cls=error_cls)


def executor_admission(executor: str | None, runtime: str | None, evidence: str | None) -> dict[str, Any]:
    """Classify one exact Issue's execution lane from its declared tokens alone.

    Decided before any claim, branch, checkout, or worktree exists. A missing marker is undeclared,
    never a default lane, so an Issue authored before this contract fails closed with its own status
    instead of silently landing on the hosted lane."""
    declared = {"executor": executor, "runtime": runtime, "evidence": evidence}
    undeclared = [marker for marker in CAPABILITY_MARKERS if declared[marker] is None]
    if undeclared:
        return {
            "admitted": False,
            "status": "executor_undeclared",
            "lane": None,
            "checkout": None,
            "admitted_lanes": (),
            "reasons": tuple(f"issue declares no noodles-{marker} marker" for marker in undeclared),
        }
    admitted_lanes = tuple(
        lane
        for lane in EXECUTOR_LANES
        if lane in CAPABILITY_TABLE["runtime"][str(runtime)] and lane in CAPABILITY_TABLE["evidence"][str(evidence)]
    )
    if executor in admitted_lanes:
        return {
            "admitted": True,
            "status": "admitted",
            "lane": executor,
            "checkout": EPHEMERAL_CHECKOUT if executor in HOSTED_LANES else MANAGED_WORKTREE,
            "admitted_lanes": admitted_lanes,
            "reasons": (),
        }
    reasons = tuple(
        f"noodles-{marker} {declared[marker]!r} is supplied only by "
        f"{', '.join(CAPABILITY_TABLE[marker][str(declared[marker])])}"
        for marker in sorted(CAPABILITY_TABLE)
        if executor not in CAPABILITY_TABLE[marker][str(declared[marker])]
    )
    return {
        "admitted": False,
        "status": "executor_refused",
        "lane": None,
        "checkout": None,
        "admitted_lanes": admitted_lanes,
        "reasons": reasons + (f"admitted route: {', '.join(admitted_lanes)}",),
    }


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


def requirement_ids(specification: str) -> frozenset[str]:
    """Stable requirement identities exactly as the specification declares them, one `### ID` heading
    each. This is a read, not a mirror: nothing here caches, indexes, or records status."""
    return frozenset(match["id"] for match in SPEC_REQUIREMENT_HEADING_RE.finditer(specification or ""))


def parse_requirements(raw_values: Sequence[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Every `noodles-requirement` marker in declaration order, plus one distinct diagnostic per
    malformed, duplicate, or over-multiplied declaration.

    Total by construction. A malformed marker is a named schedulability reason rather than an
    exception, because `schedule_snapshot` drops an Issue whose contract raises, and an Issue that
    silently disappears from the frontier is exactly the failure this atom exists to prevent."""
    ids: list[str] = []
    errors: list[str] = []
    for raw in raw_values:
        value = raw.strip()
        if not REQUIREMENT_ID_RE.fullmatch(value):
            errors.append(
                f"malformed noodles-requirement {value!r}: expected one stable requirement id "
                "matching a '### ID' heading in the system specification"
            )
        elif value in ids:
            errors.append(f"duplicate noodles-requirement entry: {value}")
        else:
            ids.append(value)
    if len(ids) > MAX_REQUIREMENTS:
        errors.append(
            f"issue binds {len(ids)} stable requirements; at most {MAX_REQUIREMENTS} are admitted"
        )
    return tuple(ids), tuple(errors)


def completeness_reasons(
    contract: dict[str, Any],
    body_sections: dict[str, str],
    known_requirements: Collection[str],
) -> list[str]:
    """ed3c/noodles#120 - the deterministic half of schedulability that `ready` does not cover.

    Structure, identities, and non-emptiness only: which sections exist, which requirement ids
    resolve against the specification's own headings, and which acceptance obligations the text
    names. It never decides whether prose is wise, complete in meaning, or technically correct, and
    it never promotes a natural-language judgment to an L verdict."""
    reasons = list(contract.get("requirement_errors") or ())
    requirements = contract.get("requirements") or ()
    if not requirements:
        reasons.append(
            "issue declares no noodles-requirement marker binding a stable system requirement id"
        )
    for requirement in requirements:
        if requirement not in known_requirements:
            reasons.append(
                f"noodles-requirement {requirement} resolves to no stable requirement heading "
                "in the system specification"
            )
    if not any(
        (body_sections.get(name) or "").strip()
        for name in body_sections
        if name == RATIONALE_SECTION or name.startswith(RATIONALE_PREFIX)
    ):
        reasons.append(
            "issue body has no '## Physical trigger' section and no admitted 'Why ...' rationale heading"
        )
    if not (body_sections.get(NON_CASE_SECTION) or "").strip():
        reasons.append(
            f"issue body has no '## Non-case' section; write exactly {NON_CASE_NONE!r} when there is none"
        )
    acceptance = (body_sections.get("physical_acceptance") or "").lower()
    for label, tokens in ACCEPTANCE_OBLIGATIONS:
        if not any(token in acceptance for token in tokens):
            reasons.append(f"'## Physical acceptance' names no {label} obligation")
    claim = (body_sections.get("claim") or "").lower()
    if any(token in claim for token in PROVIDER_AUTHORITY_TOKENS) and not any(
        token in acceptance for token in PROVIDER_READBACK_TOKENS
    ):
        reasons.append(
            "'## Claim' claims provider authority but '## Physical acceptance' names no provider "
            "readback obligation"
        )
    return reasons


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
    text = HTML_COMMENT_RE.sub("", FENCE_RE.sub("", body or ""))
    matches = list(SECTION_RE.finditer(text))
    parsed: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        key = re.sub(r"[^a-z0-9]+", "_", match.group("heading").lower()).strip("_")
        parsed[key] = text[match.end() : end].strip()
    return parsed


def body_digest(body: str) -> str:
    return hashlib.sha256((body or "").encode("utf-8")).hexdigest()


def required_section_reasons(body_sections: dict[str, str]) -> list[str]:
    # constraint: ed3c/noodles#279 monitor reconcile - the exact reason string is read by
    # constraint: derive_schedulability and by noodles.backlog_completeness_report; one
    # constraint: owner here means an edit to the wording cannot silently diverge between them.
    return [
        f"issue body has no '## {name.replace('_', ' ')}' section"
        for name in REQUIRED_SECTIONS
        if not (body_sections.get(name) or "").strip()
    ]


def derive_schedulability(
    contract: dict[str, Any],
    provider_state: str,
    dependency_states: dict[str, dict[str, Any]],
    body_sections: dict[str, str],
    known_requirements: Collection[str] = (),
) -> dict[str, Any]:
    # constraint: ed3c/noodles#120 - `known_requirements` defaults to empty and therefore fails
    # constraint: closed: a caller that cannot read the specification never admits a requirement id
    # constraint: it could not resolve.
    reasons: list[str] = []
    if provider_state != "open":
        reasons.append(f"issue provider state is {provider_state!r}, not open")
    if contract.get("state") != "ready":
        reasons.append(f"issue state marker is {contract.get('state')!r}, not ready")
    blocker = contract.get("blocker")
    if blocker:
        reasons.append(f"blocker owned by {blocker['owner']}: {blocker['reason']}")
    reasons.extend(required_section_reasons(body_sections))
    reasons.extend(completeness_reasons(contract, body_sections, known_requirements))
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

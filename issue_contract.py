"""One typed, read-only Issue contract: exact dependency markers plus schedulability derived from
provider truth. A predecessor's own landed/closed readback is the only dependency-waiting state, so a
landing cannot strand its dependents behind a mirrored marker nobody patched.

Stated ceiling of the evidence-qualification half (ed3c/noodles#317), the same way the completeness
gate already disclaims prose judgment: `noodles-observer` and `noodles-capability-probe` are verified
STRUCTURALLY - the marker is present, its section exists, both demonstration directions exist, and the
command in each direction is byte-identical to the declared invocation. Nothing here can verify that
the pasted outputs were not fabricated. The value is still real and two-fold. It is a forcing function:
the author must actually run the planted direction, and that is the exact moment an observer that
structurally cannot see what it claims dies - because the planted violation produces silence. And it
converts composed truth into checkable truth: the demonstration is a runnable pair any monitor, judge,
or successor can replay, so a fabricated demonstration is no longer a safe lie. What structure cannot
catch stays owned by monitors and judges, by design."""
from __future__ import annotations

import hashlib
import re
from typing import Any, Collection, Mapping, Sequence

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
# constraint: ed3c/noodles#314 - dedupe that compares subjects answers "is this the same ISSUE";
# constraint: concurrent discovery files the same DEFECT. The mechanical half of defect identity is
# constraint: the identifiers the rationale section QUOTES - a failing test name, a diagnostic
# constraint: literal - so nothing here reads prose and nothing scores similarity.
DEFECT_QUOTE_RE = re.compile(r"`([^`\n]+)`")
# constraint: ed3c/noodles#314 - one closed shape: a lowercase snake_case identifier of at least two
# constraint: parts. `git status`, `noodles.py` and `connection refused` are not mechanical tokens
# constraint: under it, which is what keeps a shared prose quote from blocking an unrelated atom.
DEFECT_TOKEN_RE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+")
RELATION_VERBS = ("enriches", "supersedes")
RELATION_RE = re.compile(
    r"(?P<verb>enriches|supersedes)[ \t]+(?P<elder>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+#[1-9][0-9]*)"
)
FINGERPRINT_COMMENT_MARKER = "<!-- noodles-defect-fingerprint: {elder} -->"
FINGERPRINT_COMMENT = (
    "Defect-fingerprint collision: this issue's rationale section quotes exactly the mechanical "
    "token set {elder} already quotes, so intake holds it unschedulable until it declares "
    "`<!-- noodles-relation: enriches {elder} -->` or `<!-- noodles-relation: supersedes {elder} -->`, "
    "or until {elder} closes. Nothing is closed, merged, or edited automatically: whether these are "
    "one defect stays a human judgment, and the relation marker is how that judgment becomes "
    "permanently visible.\n\n" + FINGERPRINT_COMMENT_MARKER + "\n"
)
# constraint: ed3c/noodles#317 - an issue must prove, before it is allowed to exist, that the observer
# constraint: it cites can actually observe the invariant it claims, and that no acceptance line
# constraint: prescribes an external tool behavior nobody probed. Both markers are required and both
# constraint: admit the literal `none`: the marker is the discriminator, authored explicitly, because
# constraint: classifying a trigger from its prose would be exactly the guess this gate replaces.
EVIDENCE_NONE = "none"
EVIDENCE_SECTIONS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("observer", "Observer demonstration", "observer_demonstration", ("GREEN", "RED")),
    ("capability-probe", "Capability probe", "capability_probe", ()),
)
EVIDENCE_CLAIM = {
    "observer": "makes no absence-or-failure observation claim",
    "capability-probe": "prescribes no external tool behavior in its acceptance",
}
DIRECTION_SUBJECT = {"GREEN": "clean subject", "RED": "planted violation"}
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


def _subject_number(subject: str) -> int:
    match = SUBJECT_RE.fullmatch(subject.strip())
    return int(match.group("number")) if match else 0


def defect_tokens(body_sections: dict[str, str]) -> tuple[str, ...]:
    """The mechanical tokens the rationale section quotes, normalized, de-duplicated, sorted.

    Only backtick-quoted spans are read, and only the snake_case identifiers inside them survive.
    A rationale that quotes nothing mechanical yields no tokens, which is the honest answer for a
    design atom and the reason such an atom can never collide with anything."""
    rationale = "\n".join(
        text
        for name, text in body_sections.items()
        if name == RATIONALE_SECTION or name.startswith(RATIONALE_PREFIX)
    )
    tokens: set[str] = set()
    for quoted in DEFECT_QUOTE_RE.findall(rationale):
        tokens.update(DEFECT_TOKEN_RE.findall(quoted.lower()))
    return tuple(sorted(tokens))


def defect_fingerprint(body_sections: dict[str, str]) -> str | None:
    """One digest over the exact normalized token SET, or None when the rationale quotes none.

    Ceiling, stated rather than hidden: identity here is set equality, so it catches the twin filing
    that quotes the same identifiers and nothing else, and it does NOT catch a partial overlap.
    Set equality is chosen over intersection deliberately - two atoms both quoting one shared token
    are routinely unrelated, and a false block has no honest exit, because `enriches`/`supersedes`
    would be a lie. Partial overlap stays a monitor/judge finding."""
    tokens = defect_tokens(body_sections)
    return hashlib.sha256("\n".join(tokens).encode("utf-8")).hexdigest() if tokens else None


def fingerprint_elders(subject: str, fingerprints: Mapping[str, str | None]) -> tuple[str, ...]:
    """The OPEN subjects that already carry this subject's fingerprint and are older than it.

    Elder is issue order, not clock order: the index only ever contains open issues, so an elder
    that closes drops out and releases its juniors with no marker to patch anywhere."""
    own = fingerprints.get(subject)
    if not own:
        return ()
    number = _subject_number(subject)
    return tuple(
        sorted(
            (
                other
                for other, fingerprint in fingerprints.items()
                if fingerprint == own and _subject_number(other) < number
            ),
            key=_subject_number,
        )
    )


def fingerprint_clusters(fingerprints: Mapping[str, str | None]) -> list[dict[str, Any]]:
    """Every fingerprint at least two open subjects share, with its member subjects in issue order."""
    clusters: dict[str, list[str]] = {}
    for subject, fingerprint in fingerprints.items():
        if fingerprint:
            clusters.setdefault(fingerprint, []).append(subject)
    return [
        {"fingerprint": fingerprint, "members": sorted(members, key=_subject_number)}
        for fingerprint, members in sorted(clusters.items())
        if len(members) > 1
    ]


def parse_relation(raw: str | None, subject: str, *, error_cls: type[Exception]) -> dict[str, str] | None:
    """The declared succession, or None when the issue declares none.

    ed3c/noodles#314 - this is the honest exit from a fingerprint block, so it is typed exactly: one
    admitted verb plus the elder it names, in this repository, and never the issue itself."""
    value = (raw or "").strip()
    if not value:
        return None
    match = RELATION_RE.fullmatch(value)
    if not match:
        raise error_cls(
            f"malformed noodles-relation {raw!r}: expected exactly "
            f"'{'|'.join(RELATION_VERBS)} owner/repo#N' naming the elder"
        )
    elder = match.group("elder")
    if elder.partition("#")[0] != subject.partition("#")[0]:
        raise error_cls(f"noodles-relation elder {elder} is outside the issue repository {subject.partition('#')[0]}")
    if elder == subject:
        raise error_cls(f"noodles-relation elder {elder} is the issue's own subject")
    return {"verb": match.group("verb"), "elder": elder}


def fingerprint_reasons(elders: Sequence[str], relation: dict[str, str] | None) -> list[str]:
    """One reason per open elder this issue shares a defect fingerprint with and has not declared.

    Admission-blocking on purpose: an UNDECLARED duplicate does not schedule. Declaring the relation
    is not an admission of duplication being resolved - it converts silent parallel discovery into a
    succession that stays readable forever, which is the whole exit."""
    declared = (relation or {}).get("elder")
    return [
        f"defect fingerprint is shared with open elder {elder}; declare "
        f"<!-- noodles-relation: enriches {elder} --> or <!-- noodles-relation: supersedes {elder} -->, "
        f"or wait for {elder} to close"
        for elder in elders
        if elder != declared
    ]


def fingerprint_comment(elder: str, existing_comments: Sequence[str]) -> str | None:
    """The one mechanical cross-link comment naming the elder, or None when it is already posted.

    The receipt is the marker inside the comment itself, so a re-sync is a zero-write no-op without
    any second store to keep honest."""
    marker = FINGERPRINT_COMMENT_MARKER.format(elder=elder)
    if any(marker in (body or "") for body in existing_comments):
        return None
    return FINGERPRINT_COMMENT.format(elder=elder)


def _direction_halves(section: str, directions: Sequence[str]) -> dict[str, str]:
    """Each declared direction label to the text under it, split at the next label.

    The labels are a closed uppercase vocabulary matched on word boundaries, so `REDUCE` in prose is
    not a RED direction and the split cannot be produced by accident."""
    found = {
        direction: match.start()
        for direction in directions
        for match in [re.search(rf"\b{direction}\b", section)]
        if match
    }
    ordered = sorted(found.items(), key=lambda item: item[1])
    return {
        direction: section[start : (ordered[index + 1][1] if index + 1 < len(ordered) else len(section))]
        for index, (direction, start) in enumerate(ordered)
    }


def _observed_output(block: str, invocation: str) -> list[str]:
    """The non-empty lines the block records under its copy of the invocation, fences dropped."""
    if invocation not in block:
        return []
    after = block.split(invocation, 1)[1].splitlines()[1:]
    return [line.strip() for line in after if line.strip() and line.strip() != "```"]


def _invocation_reasons(marker: str, heading: str, invocation: str, block: str, where: str) -> list[str]:
    """Command identity plus an observed output, in one block. Nothing here judges the output's truth."""
    if invocation not in block:
        return [
            f"'## {heading}' {where} does not run the declared noodles-{marker} invocation "
            f"{invocation!r}; the demonstration must use the same command, flags, and access path "
            "the claim relies on"
        ]
    if not _observed_output(block, invocation):
        return [
            f"'## {heading}' {where} runs the declared noodles-{marker} invocation but carries no "
            "observed output under it; write what it actually printed, including 'no output'"
        ]
    return []


def evidence_marker_reasons(
    marker: str, value: str | None, heading: str, section: str | None, directions: Sequence[str]
) -> list[str]:
    """One deterministic reason per absent half of one evidence marker.

    A missing marker is its own reason; an honest `none` is complete and untouched; a non-`none`
    marker owes its section, every declared direction, the identical invocation inside each, and an
    output under it. Each half is named separately so the author is told which one is absent."""
    if value is None:
        return [
            f"issue declares no noodles-{marker} marker; write exactly {EVIDENCE_NONE!r} when the "
            f"issue {EVIDENCE_CLAIM[marker]}, or the exact invocation plus a '## {heading}' section"
        ]
    invocation = value.strip()
    if invocation == EVIDENCE_NONE:
        return []
    if not (section or "").strip():
        return [
            f"noodles-{marker} declares {invocation!r} but the issue body has no '## {heading}' section"
        ]
    if not directions:
        return _invocation_reasons(marker, heading, invocation, section or "", "section")
    halves = _direction_halves(section or "", directions)
    reasons: list[str] = []
    for direction in directions:
        if direction not in halves:
            reasons.append(
                f"'## {heading}' carries no {direction} direction ({DIRECTION_SUBJECT[direction]}) "
                f"for noodles-{marker} {invocation!r}"
            )
            continue
        reasons.extend(
            _invocation_reasons(marker, heading, invocation, halves[direction], f"{direction} direction")
        )
    # constraint: ed3c/noodles#317 - the second live blindness case was a probe whose planted
    # constraint: direction returned exactly what its clean direction returned. Structurally that is
    # constraint: an observer that did not discriminate, and it is checkable without judging either
    # constraint: output's truth, so the pair is refused rather than read as a demonstration.
    if not reasons and len(directions) == 2:
        recorded = [_observed_output(halves[direction], invocation) for direction in directions]
        if recorded[0] == recorded[1]:
            reasons.append(
                f"'## {heading}' records identical output for {directions[0]} and {directions[1]}; "
                f"the declared noodles-{marker} invocation {invocation!r} did not discriminate the "
                "planted violation from the clean subject, so it cannot observe what the trigger claims"
            )
    return reasons


def evidence_reasons(body: str, declared: Mapping[str, str | None]) -> list[str]:
    """Both evidence markers judged against the body's own fence-preserving sections."""
    demonstration = sections(body, keep_fences=True)
    return [
        reason
        for marker, heading, key, directions in EVIDENCE_SECTIONS
        for reason in evidence_marker_reasons(
            marker, declared.get(marker), heading, demonstration.get(key), directions
        )
    ]


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
    reasons.extend(contract.get("evidence_reasons") or ())
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


def sections(body: str, *, keep_fences: bool = False) -> dict[str, str]:
    # constraint: ed3c/noodles#317 - a demonstration IS a fenced transcript, so the evidence gate is
    # constraint: the one reader that must keep fences. HTML comments stay stripped either way: an
    # constraint: untouched template placeholder must never read as an authored demonstration.
    stripped = body or "" if keep_fences else FENCE_RE.sub("", body or "")
    text = HTML_COMMENT_RE.sub("", stripped)
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
    *,
    elders: Sequence[str] = (),
) -> dict[str, Any]:
    # constraint: ed3c/noodles#120 - `known_requirements` defaults to empty and therefore fails
    # constraint: closed: a caller that cannot read the specification never admits a requirement id
    # constraint: it could not resolve.
    # constraint: ed3c/noodles#314 - `elders` is the collision the caller measured against the open
    # constraint: backlog it can see. It defaults to none because a single-subject readback has no
    # constraint: backlog in hand and must not invent one; admission runs on the frontier callers
    # constraint: (schedule_snapshot, backlog_items), which read every open issue anyway.
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
    reasons.extend(fingerprint_reasons(elders, contract.get("relation")))
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

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Sequence


@dataclass(frozen=True)
class ScheduleIssue:
    subject: str
    repository: str
    number: int
    dependencies: tuple[str, ...]
    p0: bool
    schedulable: bool
    claimed: bool
    malformed: bool = False
    # constraint: ed3c/noodles#98 - the lane's declared write surface, carried so
    # constraint: admission can prove disjointness; None is an undeclared/ambiguous
    # constraint: boundary that fails closed, () reserves nothing.
    write_boundary: tuple[str, ...] | None = None


@dataclass(frozen=True)
class ScheduleDecision:
    frontier: tuple[str, ...]
    components: tuple[tuple[str, ...], ...]
    winners: tuple[str, ...]
    max_useful_workers: int


def schedule_decision(issues: tuple[ScheduleIssue, ...]) -> ScheduleDecision:
    # constraint: ed3c/noodles#190 - a claimed subject excludes only its
    # constraint: dependency-connected component, never the whole repository;
    # constraint: components are connected components of the typed-dependency
    # constraint: graph within one repository, and a malformed live claim
    # constraint: (unknown edges) fails that repository closed.
    by_repository: dict[str, list[ScheduleIssue]] = {}
    for issue in issues:
        by_repository.setdefault(issue.repository, []).append(issue)

    frontier: list[ScheduleIssue] = []
    components: list[tuple[ScheduleIssue, ...]] = []
    for repository in sorted(by_repository):
        repo_issues = by_repository[repository]
        if any(issue.claimed and issue.malformed for issue in repo_issues):
            continue
        index = {issue.subject: issue for issue in repo_issues}
        parent = {subject: subject for subject in index}

        def find(subject: str) -> str:
            while parent[subject] != subject:
                parent[subject] = parent[parent[subject]]
                subject = parent[subject]
            return subject

        for issue in repo_issues:
            for dependency in issue.dependencies:
                if dependency in index:
                    parent[find(issue.subject)] = find(dependency)

        excluded_roots = {find(issue.subject) for issue in repo_issues if issue.claimed}
        eligible: dict[str, list[ScheduleIssue]] = {}
        for issue in repo_issues:
            root = find(issue.subject)
            if root in excluded_roots:
                continue
            if issue.p0 and issue.schedulable:
                eligible.setdefault(root, []).append(issue)

        for root in sorted(eligible, key=lambda value: min(issue.number for issue in eligible[value])):
            members = tuple(sorted(eligible[root], key=lambda issue: issue.number))
            components.append(members)
            frontier.extend(members)

    frontier_sorted = tuple(
        issue.subject for issue in sorted(frontier, key=lambda issue: (issue.repository, issue.number))
    )
    return ScheduleDecision(
        frontier=frontier_sorted,
        components=tuple(tuple(issue.subject for issue in members) for members in components),
        winners=tuple(members[0].subject for members in components),
        max_useful_workers=len(components),
    )


# constraint: ed3c/noodles#323 - AUTONOMY.BOUNDED.001 bounds ATTEMPTS; nothing bounded REPETITION.
# constraint: One generation ran nineteen consecutive cycles at roughly two hundred fifty provider
# constraint: calls each with an identical signature and zero new evidence, and every record it left
# constraint: was indistinguishable from a lane that was progressing. Retry counters cannot see that;
# constraint: only the delta between one attempt and the one before it can.
@dataclass(frozen=True)
class RepairAttempt:
    """One attempt at one subject, in the terms the supervise/cycle seam already carries.

    `head` is what the attempt left behind and exists only so a revert oscillation is visible;
    movement of the diff on its own is not evidence, which is exactly why nineteen editing cycles
    with one unchanging failure looked like work."""

    subject: str
    diagnostics: tuple[str, ...]
    failing_controls: tuple[str, ...]
    head: str


@dataclass(frozen=True)
class StruggleVerdict:
    subject: str
    signature: str
    attempts: int
    reason: str


STRUGGLE_DECLARATION_RE = re.compile(
    r"NOODLES_STRUGGLE_DETECTED: subject (\S+) attempts (\d+) reason (\S+) signature (.+)"
)
# constraint: normalized away because they differ between two runs of the identical failure, which
# constraint: would otherwise read as new evidence and hide every struggle behind a fresh run id.
# ponytail: literal-level normalization, deliberately no diagnostic parser; if a provider starts
# ponytail: emitting a volatile these five do not cover, add it here rather than growing a grammar.
STRUGGLE_VOLATILE_PATTERNS = (
    re.compile(r"/(?:private/)?(?:tmp|var)/\S+"),
    re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}\S*"),
    re.compile(r"\b[0-9a-f]{7,64}\b"),
    re.compile(r"#\d+"),
    re.compile(r"\b\d+(?:\.\d+)?s\b"),
)


def normalized_literal(value: str) -> str:
    """One diagnostic literal with its per-run volatiles replaced by their own kind."""
    text = " ".join(str(value).split())
    for pattern in STRUGGLE_VOLATILE_PATTERNS:
        text = pattern.sub("<volatile>", text)
    return text


def attempt_signature(attempt: RepairAttempt) -> str:
    """The attempt's failure signature: normalized diagnostic literals plus the failing-control set.

    Legible rather than hashed on purpose - the receipt has to let the dispatcher see the missing
    invariant, and a digest names nothing. Both halves are sorted sets, so a provider that reorders
    the same failures does not manufacture new evidence."""
    diagnostics = sorted({normalized_literal(item) for item in attempt.diagnostics if str(item).strip()})
    controls = sorted({str(item).strip() for item in attempt.failing_controls if str(item).strip()})
    return f"controls=[{' '.join(controls)}] diagnostics=[{' | '.join(diagnostics)}]"


def struggle_verdict(attempts: Sequence[RepairAttempt], same_signature_attempts: int) -> StruggleVerdict | None:
    """Whether this subject's attempts have stopped producing evidence, and why.

    Two triggers, both bounding repetition rather than attempts. `same_signature`: the trailing run
    of attempts sharing one signature reaches the configured threshold - same signature is what "no
    new evidence" means here, because a diff that moves while the failure does not is the burn, not
    the cure. `revert_oscillation`: the tree returned to a state it had already left, which is spend
    with no direction and fires without waiting for the threshold.

    A threshold below two is refused rather than clamped: at one, a single failure would raise a
    struggle, and the whole point is that the first failure is ordinary."""
    if same_signature_attempts < 2:
        raise ValueError(f"struggle threshold must be at least 2 attempts; got {same_signature_attempts}")
    if not attempts:
        return None
    subjects = {attempt.subject for attempt in attempts}
    if len(subjects) != 1:
        raise ValueError(f"struggle is judged per subject; got {sorted(subjects)}")
    signatures = [attempt_signature(attempt) for attempt in attempts]
    heads = [attempt.head for attempt in attempts]
    subject = attempts[-1].subject
    if len(heads) >= 3 and heads[-1] != heads[-2] and heads[-1] in heads[:-2]:
        return StruggleVerdict(subject, signatures[-1], len(attempts), "revert_oscillation")
    repeated = 1
    for index in range(len(signatures) - 1, 0, -1):
        if signatures[index] != signatures[index - 1]:
            break
        repeated += 1
    if repeated >= same_signature_attempts:
        return StruggleVerdict(subject, signatures[-1], repeated, "same_signature")
    return None


def struggle_declaration(verdict: StruggleVerdict) -> str:
    """The one exact line a generation declares a struggle on.

    ed3c/noodles#291 made a provider-ordered wait legible to the supervisor by declaring it in one
    line rather than re-deriving it where it cannot be observed; per-subject attempt history is
    unobservable from outside the generation for the same reason, so it is declared the same way.
    The signature runs to end of line, so it never needs escaping and never truncates."""
    return (
        f"NOODLES_STRUGGLE_DETECTED: subject {verdict.subject} attempts {verdict.attempts} "
        f"reason {verdict.reason} signature {verdict.signature}"
    )


def parse_struggle_declarations(text: str) -> list[dict[str, Any]]:
    """Every struggle declaration in `text`, in the order it was declared.

    Paired with `struggle_declaration` here so the emitted line and the line the supervisor reads
    cannot drift apart in two files."""
    return [
        {"subject": subject, "attempts": int(attempts), "reason": reason, "signature": signature.strip()}
        for subject, attempts, reason, signature in STRUGGLE_DECLARATION_RE.findall(text)
    ]

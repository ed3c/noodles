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
    with one unchanging failure looked like work.

    Non-claim on `head`: it is a COMMIT id, not a tree id. A revert expressed as a new commit -
    the ordinary shape - produces a head nobody has seen, so `revert_oscillation` reaches only a
    literal reset-and-force-push back onto a commit this subject already carried. Everything else
    is left to `same_signature`. A tree id would be the wider reading and the repair receipt does
    not carry one; inventing it would cost a provider call per attempt to answer a question
    `same_signature` already answers."""

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
    the same failures does not manufacture new evidence.

    The signature is only as fine as the fields the caller feeds it, and today's caller
    (`noodles.start_unattended`, off a repair receipt) can feed it exactly three: the failed run's
    conclusion, the failed job's conclusion, and that job's name. Those come from a closed provider
    enum plus a fixed required-check name, so IN PRODUCTION this signature is constant per job and
    `same_signature` reduces to "the same required job failed the same way N times running" - not
    "no new evidence". contracts/system-v1.md AUTONOMY.BOUNDED.001 carries the full non-claim and
    names the cure (carry the failed step names into the receipt). Nothing here guesses: a caller
    that supplies real diagnostic literals gets the finer signature this function is written for."""
    diagnostics = sorted({normalized_literal(item) for item in attempt.diagnostics if str(item).strip()})
    controls = sorted({str(item).strip() for item in attempt.failing_controls if str(item).strip()})
    return f"controls=[{' '.join(controls)}] diagnostics=[{' | '.join(diagnostics)}]"


def struggle_verdict(attempts: Sequence[RepairAttempt], same_signature_attempts: int) -> StruggleVerdict | None:
    """Whether this subject's attempts have stopped producing evidence, and why.

    Two triggers, both bounding repetition rather than attempts. `same_signature`: the trailing run
    of attempts sharing one signature reaches the configured threshold - same signature is what "no
    new evidence" means here, because a diff that moves while the failure does not is the burn, not
    the cure. `revert_oscillation`: the branch head returned to a commit it had already left, which is spend
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


# constraint: ed3c/noodles#407 - PROVIDER.BUDGET_FAIL_SOFT.001. The pure-Codex fallback is ratified
# constraint: provider degradation that must never become governance degradation, but a provider
# constraint: outage was handled as an improvised act: the hardest invariant of the design ("quota
# constraint: exhaustion never substitutes an identity") lived as dispatcher discipline with no
# constraint: mechanical carrier. Everything below is read-only over readings the event adapter
# constraint: (ed3c/noodles#170) produces; this module consumes readings and never produces one, so
# constraint: the whole mechanism's side-effect budget is one receipt stream and zero provider writes.
PROVIDER_MODES = (
    "NORMAL_HYBRID",
    "CODEX_ONLY",
    "READ_ONLY_DRAIN",
    "ADMISSION_ONLY",
    "PAUSED_BUDGET",
    "PAUSED_AUTHORITY",
)

# constraint: the adjudicated transition table, inline so the machine is self-contained and a reader
# constraint: never has to reconstruct it from the issue body: Claude unavailable -> CODEX_ONLY;
# constraint: Codex write-quota pressure -> READ_ONLY_DRAIN; all execution providers unavailable ->
# constraint: ADMISSION_ONLY; total budget exhausted -> PAUSED_BUDGET; GitHub App / landing authority
# constraint: lost -> PAUSED_AUTHORITY. Recovery readings reverse each transition with their own
# constraint: receipt, which is why a clear reading is a first-class row rather than a fall-through.
# ponytail: the table is ordered most-restrictive-first and the first matching trigger wins. That
# ponytail: precedence is THIS atom's declared tie-break, not an operator adjudication - the ratified
# ponytail: contract names one trigger per transition and is silent on a reading carrying several.
# ponytail: If simultaneity is ever adjudicated differently, reorder this tuple; nothing else reads
# ponytail: an ordering, so a table row is the whole upgrade path.
PROVIDER_TRANSITION_TABLE = (
    ("landing_authority_lost", "PAUSED_AUTHORITY"),
    ("budget_exhausted", "PAUSED_BUDGET"),
    ("execution_providers_unavailable", "ADMISSION_ONLY"),
    ("codex_write_quota_pressure", "READ_ONLY_DRAIN"),
    ("claude_unavailable", "CODEX_ONLY"),
)
PROVIDER_TRIGGERS = frozenset(trigger for trigger, _ in PROVIDER_TRANSITION_TABLE)
# constraint: the recovery direction's own trigger name: a reading that carries no degradation
# constraint: trigger is itself evidence, and its transition needs a receipt exactly like the others.
CLEAR_READING = "clear_reading"

# constraint: READ_ONLY_DRAIN's admitted verbs, enumerated by the ratified contract. The mode exists
# constraint: because write quota is the scarce thing, so the drain keeps every verb that reads,
# constraint: classifies, or prepares, and refuses every verb that executes.
READ_ONLY_DRAIN_VERBS = frozenset(
    {
        "dedupe",
        "admission_dry_run",
        "classification",
        "reader_only_monitoring",
        "ledger_reconciliation",
        "next_wave_preparation",
    }
)

MODE_TRANSITION_RECEIPT_RE = re.compile(
    r"NOODLES_MODE_TRANSITION: from (\S+) to (\S+) trigger (\S+) source (\S+) observed_at (\S+)"
)
# constraint: the DEFERRED_BUDGET receipt is parsed rather than substring-scanned, so a receipt whose
# constraint: budget reading was blanked out reads as ABSENT instead of as a present-but-empty field.
BUDGET_DEFERRAL_RECEIPT_RE = re.compile(
    r"NOODLES_TERMINAL_CLASS: subject (\S+) class (\S+) budget_reading (\S+) retry (\S.*)"
)


@dataclass(frozen=True)
class ProviderReading:
    """One measured provider-state reading, in the terms the event adapter already carries.

    `triggers` are MEASURED facts drawn from `PROVIDER_TRIGGERS`, never opinions: an unknown trigger
    is refused rather than ignored, because a reading the machine cannot act on must not read as a
    clear reading. `source` and `observed_at` exist so the receipt names the reading rather than
    merely naming the conclusion - a receipt that cannot be traced back to an observation is the
    prose fallback this atom deletes."""

    triggers: tuple[str, ...]
    source: str
    observed_at: str


@dataclass(frozen=True)
class ModeTransition:
    from_mode: str
    to_mode: str
    trigger: str
    receipt: str


def mode_transition_receipt(from_mode: str, to_mode: str, trigger: str, reading: ProviderReading) -> str:
    """The one exact line a mode transition is declared on.

    Legible rather than hashed for the reason `attempt_signature` is: the supervisor has to see WHICH
    reading moved the machine, and a digest names nothing."""
    return (
        f"NOODLES_MODE_TRANSITION: from {from_mode} to {to_mode} trigger {trigger} "
        f"source {reading.source} observed_at {reading.observed_at}"
    )


def provider_mode_transition(current_mode: str, reading: ProviderReading) -> ModeTransition | None:
    """The transition this reading commands from `current_mode`, or None when it commands nothing.

    Both directions are the same code path on purpose: a degradation trigger selects its adjudicated
    mode, and a reading carrying no trigger selects NORMAL_HYBRID. That makes recovery a transition
    with its own receipt rather than an untracked fall-back, and makes "a clear reading produces no
    transition" true only where it should be - already in NORMAL_HYBRID.

    Zero writes: this returns a value. Nothing here touches a provider, a ledger, or the filesystem."""
    if current_mode not in PROVIDER_MODES:
        raise ValueError(f"unknown provider mode {current_mode!r}; the machine carries {list(PROVIDER_MODES)}")
    unknown = sorted({str(trigger) for trigger in reading.triggers} - PROVIDER_TRIGGERS)
    if unknown:
        raise ValueError(
            f"provider reading from {reading.source} carries unmeasured triggers {unknown}; "
            f"the transition table carries {sorted(PROVIDER_TRIGGERS)}"
        )
    present = set(reading.triggers)
    trigger, target = CLEAR_READING, "NORMAL_HYBRID"
    for candidate, mode in PROVIDER_TRANSITION_TABLE:
        if candidate in present:
            trigger, target = candidate, mode
            break
    if target == current_mode:
        return None
    return ModeTransition(current_mode, target, trigger, mode_transition_receipt(current_mode, target, trigger, reading))


def mode_transition_errors(transition: ModeTransition) -> list[str]:
    """Why this transition's receipt fails to name its own trigger reading, one reason at a time.

    A transition without a receipt - or with one that names a different move than the transition
    carries - is a validator error, not a warning: the receipt IS the transition's evidence, so a
    transition that cannot be read back never happened as far as the supervisor is concerned."""
    errors: list[str] = []
    if transition.to_mode not in PROVIDER_MODES:
        errors.append(f"mode transition names unknown target mode {transition.to_mode!r}")
    if transition.trigger != CLEAR_READING and transition.trigger not in PROVIDER_TRIGGERS:
        errors.append(f"mode transition names unmeasured trigger {transition.trigger!r}")
    match = MODE_TRANSITION_RECEIPT_RE.search(transition.receipt or "")
    if not match:
        errors.append(
            f"mode transition {transition.from_mode}->{transition.to_mode} carries no receipt naming its trigger reading"
        )
        return errors
    from_mode, to_mode, trigger, _, _ = match.groups()
    if (from_mode, to_mode, trigger) != (transition.from_mode, transition.to_mode, transition.trigger):
        errors.append(
            f"mode transition receipt names {from_mode}->{to_mode} on {trigger}, but the transition is "
            f"{transition.from_mode}->{transition.to_mode} on {transition.trigger}"
        )
    return errors


def admit_verb(mode: str, verb: str) -> str:
    """`verb`, when `mode` admits it; a refusal naming the mode otherwise.

    Only READ_ONLY_DRAIN carries an enumerated verb set, because only READ_ONLY_DRAIN is the mode the
    ratified contract enumerates. This is the half that converts "the dispatcher remembers what
    degraded mode allows" into "the forbidden verb does not run"."""
    if mode not in PROVIDER_MODES:
        raise ValueError(f"unknown provider mode {mode!r}; the machine carries {list(PROVIDER_MODES)}")
    if mode == "READ_ONLY_DRAIN" and verb not in READ_ONLY_DRAIN_VERBS:
        raise ValueError(
            f"{mode} refuses execution verb {verb!r}; it admits only {sorted(READ_ONLY_DRAIN_VERBS)}"
        )
    return verb


def identity_substitution_errors(mode: str, declared_identity: str, active_identity: str) -> list[str]:
    """Why this identity pairing is a substitution, under `mode`.

    The mode is named in the diagnostic but is NOT an input to the verdict: no mode reachable by any
    transition admits a substitution, which is the point - degradation may reduce what runs, never
    who runs it. A fallback that swaps identity under quota pressure is the one failure this whole
    machine exists to make unreachable, so it reds under NORMAL_HYBRID exactly as under
    PAUSED_BUDGET."""
    if mode not in PROVIDER_MODES:
        raise ValueError(f"unknown provider mode {mode!r}; the machine carries {list(PROVIDER_MODES)}")
    if active_identity == declared_identity:
        return []
    return [
        f"identity substitution refused under {mode}: declared identity {declared_identity!r} was "
        f"replaced by {active_identity!r}; quota exhaustion never substitutes an identity"
    ]


@dataclass(frozen=True)
class TerminalClassification:
    """One admitted issue's receipted terminal class.

    Produced here for DEFERRED_BUDGET and consumed by the generation-closure predicate
    (ed3c/noodles#408); the shape is shared so the producer and the predicate cannot disagree about
    what a receipted class looks like."""

    subject: str
    terminal_class: str
    receipt: str
    retry_condition: str


DEFERRED_BUDGET = "DEFERRED_BUDGET"


def budget_deferral_classifications(
    reading: ProviderReading, affected_subjects: Sequence[str], retry_condition: str
) -> tuple[TerminalClassification, ...]:
    """DEFERRED_BUDGET for each admitted issue this budget reading defers, receipt included.

    The retry condition is required rather than defaulted: a deferral with no named condition to
    retry under is indistinguishable from abandonment, and the closure predicate would count it as a
    terminal state nobody will ever revisit."""
    if not str(retry_condition).strip():
        raise ValueError("a budget deferral must name the condition it retries under")
    return tuple(
        TerminalClassification(
            subject=subject,
            terminal_class=DEFERRED_BUDGET,
            receipt=(
                f"NOODLES_TERMINAL_CLASS: subject {subject} class {DEFERRED_BUDGET} "
                f"budget_reading {reading.source}@{reading.observed_at} retry {retry_condition}"
            ),
            retry_condition=retry_condition,
        )
        for subject in affected_subjects
    )


def budget_deferral_errors(
    affected_subjects: Sequence[str], classifications: Sequence[TerminalClassification]
) -> list[str]:
    """Why this budget deferral failed its classification duty.

    Entering PAUSED_BUDGET - or deferring work on budget in any mode - is only legal once every
    affected admitted issue carries a DEFERRED_BUDGET receipt naming the budget reading and the
    retry condition. A budget deferral that classifies nothing is the exact shape that lets a
    generation look closed while work silently evaporated, so it is a validator error."""
    errors: list[str] = []
    classified = {item.subject: item for item in classifications}
    if affected_subjects and not classifications:
        errors.append(
            f"budget deferral classified nothing while deferring {sorted(set(affected_subjects))}; "
            f"each affected admitted issue must carry a {DEFERRED_BUDGET} receipt"
        )
    for subject in sorted(set(affected_subjects) - set(classified)):
        errors.append(f"budget deferral leaves {subject} unclassified; it must carry a {DEFERRED_BUDGET} receipt")
    for subject in sorted(classified):
        item = classified[subject]
        if item.terminal_class != DEFERRED_BUDGET:
            errors.append(f"budget deferral classified {subject} as {item.terminal_class}, not {DEFERRED_BUDGET}")
        if not str(item.retry_condition).strip():
            errors.append(f"{DEFERRED_BUDGET} receipt for {subject} names no retry condition")
        match = BUDGET_DEFERRAL_RECEIPT_RE.search(item.receipt or "")
        if not match:
            errors.append(
                f"{DEFERRED_BUDGET} receipt for {subject} names no budget reading and no retry condition"
            )
        elif match.group(1) != subject:
            errors.append(f"{DEFERRED_BUDGET} receipt for {subject} names subject {match.group(1)}")
    return errors

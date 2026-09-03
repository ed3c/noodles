from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

# constraint: ed3c/noodles#393 - the write-boundary collision key reuses CONCURRENCY.WRITE_BOUNDARY.001's
# constraint: own overlap exit rather than carrying a second predicate. Adds no cross-surface import
# constraint: edge: no component's globs admit schedule_domain.py while excluding issue_contract.py.
import issue_contract


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


# constraint: ed3c/noodles#408 - AUTONOMY.BOUNDED.001. "Keep going until all issues are solved" has
# constraint: no machine semantics, and the naive reading (while open_issues > 0) is a non-terminating
# constraint: loop generator: new issues arrive, duplicates enrich, external blockers retry-storm,
# constraint: flaky issues starve the queue, and the daemon burns quota attempting work it has no
# constraint: authority to land. In the pure-Codex fallback there is no human-adjacent dispatcher to
# constraint: notice, so termination must be machine-decidable or the fallback is unsafe to leave
# constraint: running. The predicate below is read-only over existing state and names every issue
# constraint: that blocks closure and why.
TERMINAL_CLASSES = (
    "RESOLVED",
    "DUPLICATE_ENRICHED",
    "GATED_OUT",
    "N_CLASS_DECLARED",
    "BLOCKED_EXTERNAL",
    "DEFERRED_BUDGET",
    "QUARANTINED",
    "SUPERSEDED",
)
# constraint: every non-resolved class is a state somebody may have to leave again, so each one must
# constraint: name the condition it is retried under; RESOLVED is the only arm that terminates for
# constraint: good, which is precisely why it is the arm a masquerade aims at.
RETRY_BEARING_TERMINAL_CLASSES = tuple(name for name in TERMINAL_CLASSES if name != "RESOLVED")
# constraint: the seven conjuncts, named here so a blocker line and this list cannot drift apart.
CLOSURE_CONJUNCTS = (
    "terminal_classification",
    "no_active_lanes",
    "no_unreconciled_lanes",
    "empty_landing_train",
    "findings_accounted",
    "sweeper_balance_zero",
    "ledgers_committed",
)


@dataclass(frozen=True)
class AdmittedIssue:
    """One admitted issue of a generation, with whatever terminal state it currently carries.

    `external_blocker` is carried separately from `terminal_class` on purpose: it is the FACT, and
    the class is the CLAIM about the fact. Keeping them apart is what makes the masquerade visible -
    an issue that names an external blocker and claims RESOLVED is refused, where a single field
    would have simply been overwritten and the lie would have been unobservable."""

    subject: str
    terminal_class: str | None = None
    receipt: str = ""
    retry_condition: str = ""
    external_blocker: str = ""


@dataclass(frozen=True)
class GenerationState:
    """Everything the closure predicate reads. Nothing here is written by anything below."""

    issues: tuple[AdmittedIssue, ...] = ()
    active_lanes: tuple[str, ...] = ()
    unreconciled_lanes: tuple[str, ...] = ()
    landing_train: tuple[str, ...] = ()
    unaccounted_findings: tuple[str, ...] = ()
    sweeper_balance: int = 0
    uncommitted_ledgers: tuple[str, ...] = ()


@dataclass(frozen=True)
class ClosureVerdict:
    closed: bool
    blockers: tuple[str, ...]


def terminal_classification_errors(issues: Sequence[AdmittedIssue]) -> list[str]:
    """Why these classifications are not admissible at all - as opposed to merely not yet closed.

    The distinction is the whole atom: an issue with no class yet is an OPEN generation (ordinary,
    reported by the predicate), while an issue whose class contradicts its own recorded facts is a
    LIE (refused, never reported as a state). BLOCKED_EXTERNAL can never satisfy the RESOLVED arm, so
    external blockage stops masquerading as completion - the self-report honesty the daemon needs
    before any generation is allowed to declare itself done unattended."""
    errors: list[str] = []
    for issue in issues:
        if issue.terminal_class is None:
            continue
        if issue.terminal_class not in TERMINAL_CLASSES:
            errors.append(
                f"{issue.subject} claims terminal class {issue.terminal_class!r}, which is not one of {list(TERMINAL_CLASSES)}"
            )
            continue
        if issue.external_blocker.strip() and issue.terminal_class == "RESOLVED":
            errors.append(
                f"{issue.subject} presents external blockage {issue.external_blocker!r} as RESOLVED; "
                "BLOCKED_EXTERNAL can never satisfy the RESOLVED arm"
            )
    return errors


def generation_closure(state: GenerationState) -> ClosureVerdict:
    """Whether this generation is closed, and every conjunct plus issue that holds it open.

    Seven conjuncts, evaluated in `CLOSURE_CONJUNCTS` order. The output names what blocks closure so
    the report is actionable rather than a bare boolean - "not closed" with no named blocker is the
    aspiration this predicate replaces.

    Zero writes: this reads `state` and returns a value. It closes nothing, retries nothing, and
    touches no provider - acting on the verdict stays with the daemon and the dispatcher."""
    refusals = terminal_classification_errors(state.issues)
    if refusals:
        raise ValueError("; ".join(refusals))
    blockers: list[str] = []
    for issue in state.issues:
        if issue.terminal_class is None:
            blockers.append(f"terminal_classification: {issue.subject} carries no terminal class")
            continue
        if not issue.receipt.strip():
            blockers.append(f"terminal_classification: {issue.subject} is {issue.terminal_class} with no receipt")
        if issue.terminal_class in RETRY_BEARING_TERMINAL_CLASSES and not issue.retry_condition.strip():
            blockers.append(
                f"terminal_classification: {issue.subject} is {issue.terminal_class} with no named retry condition"
            )
    blockers.extend(f"no_active_lanes: {lane} is still active" for lane in state.active_lanes)
    blockers.extend(f"no_unreconciled_lanes: {lane} completed but is unreconciled" for lane in state.unreconciled_lanes)
    blockers.extend(f"empty_landing_train: {entry} is still on the landing train" for entry in state.landing_train)
    blockers.extend(f"findings_accounted: {finding} is unaccounted" for finding in state.unaccounted_findings)
    if state.sweeper_balance != 0:
        blockers.append(
            f"sweeper_balance_zero: sweeper balance is {state.sweeper_balance}, so a tracked nudge or hand-off is unreconciled"
        )
    blockers.extend(f"ledgers_committed: {ledger} is uncommitted" for ledger in state.uncommitted_ledgers)
    return ClosureVerdict(closed=not blockers, blockers=tuple(blockers))


# constraint: ed3c/noodles#410 - AUTONOMY.SUPERVISED_RUNNER.001, admission-mechanization item: wave
# constraint: and generation identifiers must be machine-minted. Today wave labels are
# constraint: dispatcher-authored strings; in the pure-Codex fallback an agent-invented identifier is
# constraint: a collision and forgery surface on every ledger key, run record, and receipt that cites
# constraint: it, with no validator refusing it. One producer, one registry, one refusal.
GENERATION_ID_RE = re.compile(r"g(\d{6})-[a-z0-9][a-z0-9-]*")
GENERATION_MINT_RECEIPT_RE = re.compile(r"NOODLES_GENERATION_MINT: id (\S+) ordinal (\d+) context (\S.*)")


@dataclass(frozen=True)
class MintedGeneration:
    identifier: str
    ordinal: int
    context: str
    receipt: str


class GenerationMint:
    """The single producer of generation/wave identifiers, with the registry that refuses the rest.

    Monotonicity is carried IN the identifier rather than only in the registry: the ordinal is
    zero-padded, so lexicographic order over minted ids equals mint order, and a ledger that sorts by
    key sorts by generation without consulting anything. That is the whole reason the ordinal is not
    a bare counter kept privately - a join key the machine can verify beats one it has to trust.

    Not persistent, deliberately. The registry is process state that a caller hands to whichever
    consumer validates against it; the ratified non-claim says the registry starts at adoption and no
    historical wave label is renamed, so there is nothing to load and a store would be a second
    source of truth this atom does not need.
    # ponytail: in-memory registry, no store. If minted ids must survive a restart, give this a
    # ponytail: `from_receipts(text)` reader over the receipt stream it already emits - the receipts
    # ponytail: carry ordinal and context, so the registry is reconstructible without a new format.
    """

    def __init__(self) -> None:
        self._ordinal = 0
        self._minted: dict[str, MintedGeneration] = {}

    def mint(self, context: str) -> MintedGeneration:
        """The next identifier for `context`, unique and strictly greater than every earlier one.

        A blank context is refused rather than defaulted: the receipt has to name what the generation
        was minted FOR, and an unnamed context makes the receipt unusable as evidence."""
        slug = "-".join(str(context).lower().split())
        if not GENERATION_ID_RE.fullmatch(f"g000000-{slug}"):
            raise ValueError(
                f"generation context {context!r} is not a mintable label; use lowercase words, digits and hyphens"
            )
        self._ordinal += 1
        identifier = f"g{self._ordinal:06d}-{slug}"
        minted = MintedGeneration(
            identifier=identifier,
            ordinal=self._ordinal,
            context=str(context),
            receipt=f"NOODLES_GENERATION_MINT: id {identifier} ordinal {self._ordinal} context {context}",
        )
        self._minted[identifier] = minted
        return minted

    def minted(self, identifier: str) -> MintedGeneration | None:
        """This registry's record for `identifier`, or None. Reads only."""
        return self._minted.get(identifier)

    @property
    def registry(self) -> tuple[MintedGeneration, ...]:
        return tuple(self._minted[key] for key in sorted(self._minted))


def minted_id_errors(mint: GenerationMint, identifier: str) -> list[str]:
    """Why this identifier may not be cited by a machine-side consumer.

    This is the single refusal every ledger and run-record writer routes through: an agent-supplied
    identifier that was never minted is a validator error naming the id, not a warning and not a
    silently-accepted key. Zero writes - it reads the registry and returns a list."""
    if not str(identifier).strip():
        raise ValueError("a machine-side consumer must present an identifier to validate")
    if mint.minted(identifier) is None:
        return [
            f"generation identifier {identifier!r} was never minted; machine-side consumers cite minted ids only"
        ]
    return []


def mint_receipt_errors(minted: MintedGeneration) -> list[str]:
    """Why this mint receipt fails to name the generation context it was minted for."""
    match = GENERATION_MINT_RECEIPT_RE.search(minted.receipt or "")
    if not match:
        return [f"mint of {minted.identifier} carries no receipt naming its generation context"]
    identifier, ordinal, context = match.groups()
    errors: list[str] = []
    if identifier != minted.identifier:
        errors.append(f"mint receipt names id {identifier}, but the mint carries {minted.identifier}")
    if int(ordinal) != minted.ordinal:
        errors.append(f"mint receipt names ordinal {ordinal}, but the mint carries {minted.ordinal}")
    if context.strip() != minted.context.strip():
        errors.append(f"mint receipt names context {context!r}, but the mint carries {minted.context!r}")
    return errors


# constraint: ed3c/noodles#393 - CONCURRENCY.DECLARED_CAPACITY.001. Measured live 2026-09-03: three
# constraint: concurrent dispatch waves put six-plus full test suites on the host at once, swap
# constraint: approached its ceiling, and the operator reported a near forced-shutdown. The
# constraint: post-incident adjudication also derived the landing-side physics: under a strict
# constraint: required check a landing queue of depth n costs ~n^2/2 verify runs to clear, so implement
# constraint: width beyond "keep the queue at depth 1-2" has NEGATIVE marginal value. Both rules lived
# constraint: only as dispatcher discipline in a session ledger - the per-operator-memory class this
# constraint: machine exists to delete. Feedback control, never prediction: two live readings.
CAPACITY_SIGNALS = ("host_memory_headroom", "landing_queue_depth")
CAPACITY_REFUSAL_RE = re.compile(r"NOODLES_CAPACITY_REFUSED: slot (\S+) signal (\S+) reading (\S.*)")


@dataclass(frozen=True)
class DeclaredCapacity:
    """What this host declares it can carry. Declared, not inferred - the requirement's own heading
    demands declarations live where they can be read.

    `swap_ceiling_mb` is the host's DECLARED swap allotment and is deliberately not the observed
    total. The incident proves why: under the storm the kernel grew total from 3072M to 4096M, so the
    RED reading showed MORE free swap (1679.75M) than the recovering GREEN one (1042.12M). Any
    controller that measured headroom against the observed total would therefore have read the storm
    as roomier than the recovery and admitted straight into the near-shutdown. Measuring against a
    fixed declared ceiling makes swap growth visible as the pressure it is."""

    swap_ceiling_mb: float
    swap_headroom_floor_mb: float
    landing_queue_target: int


@dataclass(frozen=True)
class CapacityReading:
    """The two live signals, exactly as their observers state them.

    `swap_used_mb` comes from `sysctl vm.swapusage`; `landing_queue_depth` is the count of open
    awaiting_land pull requests for the repository. Neither is estimated, and there is no third."""

    swap_used_mb: float
    landing_queue_depth: int


def capacity_refusal(slot: str, reading: CapacityReading, declared: DeclaredCapacity) -> str | None:
    """The refusal this reading commands for `slot`, or None when the slot is admitted.

    `slot` names WHICH admission was refused - a dispatch slot or a full-suite run - because both are
    gated by the same two signals and a refusal that does not say what it refused is unusable in a
    receipt. Every refusal names the signal AND the reading that refused it: a refusal naming neither
    is indistinguishable from a policy nobody measured, which is the state this atom replaces.

    Memory is checked before queue depth: memory is the signal that nearly killed the host, and a
    host with no headroom must not be admitted merely because its landing queue happens to be short."""
    if not str(slot).strip():
        raise ValueError("a capacity admission must name the slot it is admitting")
    headroom = declared.swap_ceiling_mb - reading.swap_used_mb
    if headroom < declared.swap_headroom_floor_mb:
        return (
            f"NOODLES_CAPACITY_REFUSED: slot {slot} signal host_memory_headroom reading "
            f"swap_used={reading.swap_used_mb:.2f}M declared_ceiling={declared.swap_ceiling_mb:.2f}M "
            f"headroom={headroom:.2f}M floor={declared.swap_headroom_floor_mb:.2f}M"
        )
    if reading.landing_queue_depth >= declared.landing_queue_target:
        return (
            f"NOODLES_CAPACITY_REFUSED: slot {slot} signal landing_queue_depth reading "
            f"depth={reading.landing_queue_depth} target={declared.landing_queue_target}"
        )
    return None


def refusal_reason_errors(reason: str) -> list[str]:
    """Why this refusal reason fails to name a signal and the reading that refused it.

    A refusal reason that names no signal/reading is a validator error, not a warning: an
    unattributed refusal cannot be argued with, cannot be waited out, and cannot be told apart from a
    controller that is simply broken."""
    match = CAPACITY_REFUSAL_RE.search(reason or "")
    if not match:
        return [f"capacity refusal {reason!r} names no signal and no reading"]
    _, signal, measurement = match.groups()
    errors: list[str] = []
    if signal not in CAPACITY_SIGNALS:
        errors.append(f"capacity refusal names signal {signal!r}, which is not one of {list(CAPACITY_SIGNALS)}")
    if not re.search(r"=-?\d", measurement):
        errors.append(f"capacity refusal names signal {signal} but no measured reading: {measurement!r}")
    return errors


def topological_depth(dependencies_by_subject: Mapping[str, Sequence[str]]) -> dict[str, int]:
    """Each subject's dependency-chain depth: 0 for a root, 1 + its deepest dependency otherwise.

    A dependency outside the map is depth 0 - it is already landed or lives elsewhere, and either way
    it is not a chain this scheduler has to wait through. A cycle is refused rather than assigned a
    depth: a cyclic dependency declaration is a contract error, and silently ordering it would hide
    the error behind a plausible-looking queue."""
    depths: dict[str, int] = {}
    visiting: set[str] = set()

    def depth(subject: str) -> int:
        if subject in depths:
            return depths[subject]
        if subject in visiting:
            raise ValueError(f"dependency cycle reaches {subject!r}; a cyclic chain has no topological depth")
        visiting.add(subject)
        found = max(
            (1 + depth(dependency) for dependency in dependencies_by_subject.get(subject, ()) if dependency in dependencies_by_subject),
            default=0,
        )
        visiting.discard(subject)
        depths[subject] = found
        return found

    for subject in dependencies_by_subject:
        depth(subject)
    return depths


def admission_order(dependencies_by_subject: Mapping[str, Sequence[str]]) -> tuple[str, ...]:
    """The order scarce slots are offered in: shallowest chain first, then by subject.

    Deep chain tails are deprioritized because they cannot land until everything beneath them has,
    so a slot spent on a tail buys a branch that waits; a slot spent on a shallow atom buys one that
    can land this generation and drain the queue the n^2 physics punishes."""
    depths = topological_depth(dependencies_by_subject)
    return tuple(sorted(depths, key=lambda subject: (depths[subject], subject)))


# constraint: ed3c/noodles#393 - operator amendment 2026-09-03, arriving on the issue body after this
# constraint: atom's first commit: the ordering key alone spends slots well but still lets two atoms
# constraint: with overlapping declared write boundaries run at once, and every such pair pays the
# constraint: rebase tax at LANDING, where it is most expensive and where the n^2 queue physics
# constraint: multiplies it. The cure named by the amendment is to never PRODUCE high-collision
# constraint: candidates concurrently, so the collision key binds at candidate production - one slot
# constraint: admits a set whose declared boundaries are pairwise disjoint, and a colliding atom is
# constraint: serialized behind the one it collides with, named together with the overlapping prefix.
COLLISION_SERIALIZED_RE = re.compile(
    r"NOODLES_COLLISION_SERIALIZED: subject (\S+) held behind (\S+) on boundary (\S+)"
)


def codispatch_admission(
    order: Sequence[str], boundaries: Mapping[str, tuple[str, ...] | None]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """`(co-dispatched subjects, serialization refusals)` for one slot, in `order`.

    Overlap is judged by `issue_contract.boundary_conflict`, the SAME exit
    `CONCURRENCY.WRITE_BOUNDARY.001` admission already uses - segment-wise, so `tests` never collides
    with `tests2`. Carrying a second overlap predicate here is the exact drift ed3c/noodles#272 paid
    for in the repair path, where a refusal and its named remedy correlated on different keys and
    manufactured a dead end.

    An undeclared boundary (`None`) fails closed: a lane that could write anywhere cannot be proven
    disjoint from anything, so it is serialized rather than optimistically co-dispatched. An empty
    tuple reserves nothing and always co-dispatches - the two are deliberately different values,
    because "declared nothing" and "declared nothing yet" are different states.

    Greedy in `order` on purpose: the ordering key has already decided who deserves the slot most, so
    collisions are resolved in that order rather than by re-optimizing, and the first-named atom
    keeps its priority instead of being displaced by a later sibling."""
    admitted: list[str] = []
    refusals: list[str] = []
    for subject in order:
        declared = boundaries.get(subject)
        if declared is None:
            refusals.append(
                f"NOODLES_COLLISION_UNDECLARED: subject {subject} held: its write boundary is "
                "undeclared, so disjointness from the slot cannot be proven"
            )
            continue
        collision: tuple[str, str] | None = None
        for sibling in admitted:
            overlap = issue_contract.boundary_conflict(declared, boundaries[sibling] or ())
            if overlap:
                collision = (sibling, overlap)
                break
        if collision is None:
            admitted.append(subject)
        else:
            refusals.append(
                f"NOODLES_COLLISION_SERIALIZED: subject {subject} held behind {collision[0]} "
                f"on boundary {collision[1]}"
            )
    return tuple(admitted), tuple(refusals)

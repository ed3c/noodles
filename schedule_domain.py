from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScheduleIssue:
    subject: str
    repository: str
    number: int
    dependencies: tuple[str, ...]
    p0: bool
    schedulable: bool
    claimed: bool


@dataclass(frozen=True)
class ScheduleDecision:
    frontier: tuple[str, ...]
    components: tuple[tuple[str, ...], ...]
    winners: tuple[str, ...]
    max_useful_workers: int


def schedule_decision(issues: tuple[ScheduleIssue, ...]) -> ScheduleDecision:
    active_repositories = {issue.repository for issue in issues if issue.claimed}
    ready = sorted(
        (
            issue
            for issue in issues
            if issue.p0 and issue.schedulable and not issue.claimed and issue.repository not in active_repositories
        ),
        key=lambda issue: (issue.repository, issue.number),
    )
    grouped: dict[str, list[str]] = {}
    for issue in ready:
        grouped.setdefault(issue.repository, []).append(issue.subject)
    components = tuple(tuple(grouped[repository]) for repository in sorted(grouped))
    return ScheduleDecision(
        frontier=tuple(issue.subject for issue in ready),
        components=components,
        winners=tuple(component[0] for component in components),
        max_useful_workers=len(components),
    )

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
    malformed: bool = False


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

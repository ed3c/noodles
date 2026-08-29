from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


SCHEDULE_OWNERSHIP_PHRASE = "Noodle alone injects and owns the transient `schedule` order."
SCHEDULE_ACTIVE_ORDER_PHRASE = "Do not re-emit any active non-schedule order."
SCHEDULE_PUBLISH_COMMAND = "python3 skill_contract.py publish .noodle/orders-next.candidate.json"


def _has_scheduler_frontmatter(content: str) -> bool:
    lines = content.lstrip(" \t\r\n").splitlines()
    if not lines or lines[0] != "---":
        return False
    try:
        closing = lines.index("---", 1)
    except ValueError:
        return False
    for line in lines[1:closing]:
        if not line.startswith("schedule:"):
            continue
        try:
            value = json.loads(line.partition(":")[2].strip())
        except json.JSONDecodeError:
            return False
        return isinstance(value, str) and bool(value.strip())
    return False


def validate_backlog_scheduler(root: Path, config: dict[str, Any]) -> list[str]:
    skill_name = config.get("adapters", {}).get("backlog", {}).get("skill")
    if not isinstance(skill_name, str) or not skill_name.strip():
        return ["backlog adapter must configure one scheduler-capable skill"]
    skill_file = None
    for raw_path in config.get("skills", {}).get("paths", []):
        if not isinstance(raw_path, str):
            continue
        skill_root = Path(os.path.expanduser(raw_path))
        if not skill_root.is_absolute():
            skill_root = root / skill_root
        candidate = skill_root / skill_name.strip() / "SKILL.md"
        if candidate.is_file():
            skill_file = candidate
            break
    if skill_file is None:
        return [f"backlog adapter skill {skill_name!r} does not resolve from configured skill paths"]
    try:
        content = skill_file.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"cannot read backlog adapter skill {skill_name!r}: {exc}"]
    if not _has_scheduler_frontmatter(content):
        relative = os.path.relpath(skill_file, root)
        return [
            f"backlog adapter skill {skill_name!r} is not scheduler-capable: "
            f"{relative} requires non-empty top-level schedule frontmatter"
        ]
    required_contracts = (
        (SCHEDULE_OWNERSHIP_PHRASE, "self-order ownership"),
        (SCHEDULE_ACTIVE_ORDER_PHRASE, "active-order preservation"),
        (SCHEDULE_PUBLISH_COMMAND, "deterministic publish gate"),
    )
    errors = []
    for phrase, label in required_contracts:
        if phrase not in content:
            errors.append(f"backlog adapter skill {skill_name!r} missing {label} contract")
    return errors


def _orders(payload: Any, label: str) -> tuple[list[Any], list[str]]:
    if not isinstance(payload, dict):
        return [], [f"{label} must be a JSON object"]
    orders = payload.get("orders")
    if not isinstance(orders, list):
        return [], [f"{label} must contain an orders array"]
    return orders, []


def validate_schedule_output(current: Any, proposed: Any) -> list[str]:
    current_orders, errors = _orders(current, "current orders")
    proposed_orders, proposed_errors = _orders(proposed, "scheduler output")
    errors.extend(proposed_errors)
    if errors:
        return errors

    active_ids = {
        str(order.get("id", "")).strip().casefold(): str(order.get("id", "")).strip()
        for order in current_orders
        if isinstance(order, dict)
        and str(order.get("status", "")).strip().casefold() == "active"
        and str(order.get("id", "")).strip().casefold() != "schedule"
    }
    for index, order in enumerate(proposed_orders):
        if not isinstance(order, dict):
            errors.append(f"scheduler output order[{index}] must be a JSON object")
            continue
        raw_id = order.get("id")
        if not isinstance(raw_id, str) or not raw_id.strip():
            errors.append(f"scheduler output order[{index}] requires a non-empty string id")
            continue
        order_id = raw_id.strip()
        normalized_id = order_id.casefold()
        if normalized_id == "schedule":
            errors.append("scheduler output must not contain Noodle-owned transient schedule order 'schedule'")
            continue
        if normalized_id in active_ids:
            errors.append(
                f"scheduler output must omit active non-schedule order {active_ids[normalized_id]!r}; "
                "Noodle preserves its exact order/stage fields"
            )
            continue
        stages = order.get("stages", [])
        if isinstance(stages, list) and any(
            isinstance(stage, dict)
            and str(stage.get("do", stage.get("task_key", ""))).strip().casefold() == "schedule"
            for stage in stages
        ):
            errors.append(f"scheduler output order {order_id!r} must not contain a schedule stage")
    return errors


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {label} {path}: {exc}") from exc


def publish_schedule_output(root: Path, candidate_path: Path) -> Path:
    root = root.resolve()
    runtime = root / ".noodle"
    expected_candidate = runtime / "orders-next.candidate.json"
    candidate = candidate_path if candidate_path.is_absolute() else root / candidate_path
    candidate = candidate.resolve()
    if candidate != expected_candidate.resolve():
        raise ValueError(f"schedule candidate must be {expected_candidate}")
    current_path = runtime / "orders.json"
    current = _read_json(current_path, "current orders") if current_path.exists() else {"orders": []}
    proposed = _read_json(candidate, "schedule candidate")
    errors = validate_schedule_output(current, proposed)
    if errors:
        raise ValueError("schedule output rejected: " + "; ".join(errors))
    destination = runtime / "orders-next.json"
    os.replace(candidate, destination)
    return destination


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if len(args) != 2 or args[0] != "publish":
        print("usage: python3 skill_contract.py publish .noodle/orders-next.candidate.json", file=sys.stderr)
        return 2
    try:
        destination = publish_schedule_output(Path.cwd(), Path(args[1]))
    except ValueError as exc:
        print(f"schedule contract FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"schedule contract PASS: {destination}")
    return 0


def validate_noodle_worktree_ignore(root: Path, tracked_paths: set[str]) -> list[str]:
    diagnostic = "Noodle worktree root .worktrees requires exact tracked ignore rule .worktrees/"
    if ".gitignore" not in tracked_paths:
        return [diagnostic]
    try:
        ignore_lines = (root / ".gitignore").read_text(encoding="utf-8").splitlines()
    except OSError:
        return [diagnostic]
    if ".worktrees/" not in ignore_lines:
        return [diagnostic]
    result = subprocess.run(
        ["git", "check-ignore", "-q", ".worktrees/"], cwd=root, check=False
    )
    return [] if result.returncode == 0 else [diagnostic]


if __name__ == "__main__":
    raise SystemExit(main())

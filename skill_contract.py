from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


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
    return []

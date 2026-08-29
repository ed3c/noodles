from __future__ import annotations

import re
from pathlib import Path
from typing import Any

HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
CONTROL_NOODLE_PROVIDER = "skill-concerns"
CONTROL_NOODLE_SKILL = "control-noodle"
CONTROL_NOODLE_DESTINATION = ".noodle/providers/skill-concerns"
CONTROL_NOODLE_DISCOVERY_ROOT = ".noodle/providers/skill-concerns/skills/control-noodle"
RETIRED_PROVIDER = "matt-engineering"
RETIRED_PROVIDER_DESTINATION = ".noodle/providers/matt-engineering"
RETIRED_PROVIDER_DISCOVERY_ROOT = ".noodle/providers/matt-engineering/skills/engineering"


def validate_admission_policy(provider_name: str, admission: Any) -> list[str]:
    if not isinstance(admission, dict):
        return [f"provider {provider_name} admission must be an object"]
    errors: list[str] = []
    if not admission.get("skill"):
        errors.append(f"provider {provider_name} admission skill is required")
    if not HEX64_RE.fullmatch(str(admission.get("sha256", ""))):
        errors.append(f"provider {provider_name} admission digest must be a 64-hex sha256")
    if not HEX64_RE.fullmatch(str(admission.get("skill_tree_sha256", ""))):
        errors.append(f"provider {provider_name} admission skill-tree digest must be a 64-hex sha256")
    admission_path = str(admission.get("path", ""))
    if not admission_path:
        errors.append(f"provider {provider_name} admission path is required")
    elif Path(admission_path).is_absolute() or ".." in Path(admission_path).parts:
        errors.append(f"provider {provider_name} admission path must stay under the provider checkout")
    subject_files = admission.get("subject_files")
    if not isinstance(subject_files, dict) or not subject_files:
        return errors + [f"provider {provider_name} admission subject_files must be a non-empty object"]
    for subject_path, sha256 in subject_files.items():
        if Path(str(subject_path)).is_absolute() or ".." in Path(str(subject_path)).parts:
            errors.append(f"provider {provider_name} admission subject file path must stay under the provider checkout")
        if not HEX64_RE.fullmatch(str(sha256)):
            errors.append(f"provider {provider_name} admission subject file digest must be a 64-hex sha256")
    return errors


def validate_enabled_provider_names(enabled_names: set[str], cursor_provider: str) -> list[str]:
    expected = {CONTROL_NOODLE_PROVIDER, cursor_provider}
    if enabled_names == expected:
        return []
    return [
        "enabled providers must be exactly "
        f"{CONTROL_NOODLE_PROVIDER} and {cursor_provider}; got {', '.join(sorted(enabled_names)) or '<empty>'}"
    ]


def validate_skill_config_paths(skill_paths: list[str]) -> list[str]:
    errors: list[str] = []
    if CONTROL_NOODLE_DISCOVERY_ROOT not in skill_paths:
        errors.append(f".noodle.toml skills.paths must include {CONTROL_NOODLE_DISCOVERY_ROOT}")
    if RETIRED_PROVIDER_DISCOVERY_ROOT in skill_paths:
        errors.append(".noodle.toml skills.paths must not retain retired matt-engineering discovery")
    return errors

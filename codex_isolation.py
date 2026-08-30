from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping

CODEX_WRAPPER_DIR = ".agents/bin"
CODEX_WRAPPER = f"{CODEX_WRAPPER_DIR}/codex"
ISOLATED_HOME = ".noodle/codex-isolation/home"
ISOLATED_CODEX_HOME = ".noodle/codex-isolation/codex-home"
PROJECT_SKILLS_ROOT = ".agents/skills"
FORBIDDEN_FORWARD_ARG = "--dangerously-bypass-approvals-and-sandbox"
TRUNCATION_RE = re.compile(r"truncat|skill-context-budget", re.I)


def validate_codex_agent_config(root: Path, noodle_config: Mapping[str, Any]) -> list[str]:
    agents = noodle_config.get("agents")
    if not isinstance(agents, Mapping):
        return ["missing [agents.codex] configuration"]
    codex = agents.get("codex")
    if not isinstance(codex, Mapping):
        return ["missing [agents.codex] configuration"]
    errors: list[str] = []
    if str(codex.get("path") or "") != CODEX_WRAPPER_DIR:
        errors.append(f".noodle.toml agents.codex.path must be {CODEX_WRAPPER_DIR!r}")
    args = list(codex.get("args") or [])
    if "--ignore-user-config" not in args:
        errors.append(".noodle.toml agents.codex.args must include '--ignore-user-config'")
    errors.extend(_sandbox_shape_errors(args))
    if _flag_value(args, "-c") != 'approval_policy="never"':
        errors.append('.noodle.toml agents.codex.args must preserve \'-c approval_policy="never"\'')
    wrapper = root / CODEX_WRAPPER
    if not wrapper.is_file():
        errors.append(f"tracked Codex wrapper missing: {CODEX_WRAPPER}")
    return errors


def codex_surface_canary(root: Path, *, error_cls: type[Exception]) -> dict[str, Any]:
    root = root.resolve()
    wrapper = (root / CODEX_WRAPPER).resolve()
    status_before = _git_status(root)
    with tempfile.TemporaryDirectory(prefix="noodles-codex-trace-") as temp_name:
        traces = Path(temp_name)
        schedule = _run_canary_command(root, wrapper, traces / "schedule.json", ["debug", "prompt-input", "use schedule skill"], error_cls=error_cls)
        execute = _run_canary_command(root, wrapper, traces / "execute.json", ["debug", "prompt-input", "use execute skill"], error_cls=error_cls)
        plugins = _run_canary_command(root, wrapper, traces / "plugins.json", ["plugin", "list", "--json"], error_cls=error_cls)
        receipt = {
            "wrapper": str(wrapper),
            "schedule": _surface_receipt(schedule, required_skills={"schedule"}, error_cls=error_cls),
            "execute": _surface_receipt(execute, required_skills={"execute"}, error_cls=error_cls),
            "plugins": _plugin_receipt(plugins, error_cls=error_cls),
            "isolated_paths": {
                "home": str((root / ISOLATED_HOME).resolve()),
                "codex_home": str((root / ISOLATED_CODEX_HOME).resolve()),
            },
        }
    receipt["repository_status_before"] = status_before
    receipt["repository_status_after"] = _git_status(root)
    if receipt["repository_status_after"] != status_before:
        raise error_cls(
            "Codex isolation canary changed repository status: "
            f"{status_before!r} -> {receipt['repository_status_after']!r}"
        )
    return receipt


def _flag_value(args: list[Any], flag: str) -> str | None:
    for index, value in enumerate(args):
        if str(value) == flag and index + 1 < len(args):
            return str(args[index + 1])
    return None


def _all_flag_values(args: list[Any], flag: str) -> list[str]:
    return [str(args[index + 1]) for index, value in enumerate(args) if str(value) == flag and index + 1 < len(args)]


# constraint: staging window (ed3c/noodles#180) - args may carry either the
# constraint: sandbox-flag shape or the complete noodles-cook permissions
# constraint: profile; the profile was proven load-bearing against the pinned
# constraint: codex binary (2026-08-30); the retire step pins one shape after
# constraint: ed3c/noodles#172 lands.
_PROFILE_REQUIRED_EXACT = (
    'default_permissions="noodles-cook"',
    'permissions.noodles-cook.extends=":workspace"',
    "permissions.noodles-cook.network.enabled=true",
)


def _sandbox_shape_errors(args: list[Any]) -> list[str]:
    if _flag_value(args, "--sandbox") == "workspace-write":
        return []
    values = _all_flag_values(args, "-c")
    if not any(value.startswith("default_permissions=") for value in values):
        return [
            ".noodle.toml agents.codex.args must carry either '--sandbox workspace-write' "
            "or the complete noodles-cook permissions profile (staging window, ed3c/noodles#180)"
        ]
    errors = [
        f".noodle.toml agents.codex.args profile shape missing '-c {required}'"
        for required in _PROFILE_REQUIRED_EXACT
        if required not in values
    ]
    if not any(value.startswith("permissions.noodles-cook.workspace_roots=") and ".git" in value for value in values):
        errors.append(
            ".noodle.toml agents.codex.args profile shape must grant the noodles .git root via permissions.noodles-cook.workspace_roots"
        )
    if not any(
        value.startswith("permissions.noodles-cook.filesystem=") and ".agents/skills" in value and "write" in value
        for value in values
    ):
        errors.append(
            ".noodle.toml agents.codex.args profile shape must grant .agents/skills write via permissions.noodles-cook.filesystem"
        )
    return errors


def _run_canary_command(
    root: Path,
    wrapper: Path,
    trace_file: Path,
    argv: list[str],
    *,
    error_cls: type[Exception],
) -> dict[str, Any]:
    env = os.environ.copy()
    env["NOODLES_CODEX_TRACE_FILE"] = str(trace_file)
    result = subprocess.run(
        [str(wrapper), *argv],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )
    if result.returncode != 0:
        raise error_cls(f"Codex isolation canary failed for {' '.join(argv)}: {result.stderr.strip() or result.stdout.strip()}")
    return {
        "argv": argv,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "trace": json.loads(trace_file.read_text(encoding="utf-8")),
    }


def _git_status(root: Path) -> list[str]:
    result = subprocess.run(["git", "status", "--short"], cwd=root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return result.stdout.splitlines()


def _surface_receipt(result: Mapping[str, Any], *, required_skills: set[str], error_cls: type[Exception]) -> dict[str, Any]:
    payload = json.loads(str(result["stdout"]))
    developer_text = "\n".join(
        str(content.get("text") or "")
        for message in payload
        if isinstance(message, Mapping) and message.get("role") == "developer"
        for content in message.get("content", [])
        if isinstance(content, Mapping) and content.get("type") == "input_text"
    )
    roots_match = re.search(r"### Skill roots\n(.*?)### Available skills\n", developer_text, re.S)
    skills_match = re.search(r"### Available skills\n(.*?)(?:</skills_instructions>|<plugins_instructions>)", developer_text, re.S)
    if not skills_match:
        raise error_cls("Codex prompt-input readback missing skills instructions")
    root_map = {name: path for name, path in re.findall(r"- `(r\d+)` = `([^`]+)`", roots_match.group(1) if roots_match else "")}
    skills = set(re.findall(r"- ([^:\n]+):", skills_match.group(1)))
    resolved_skill_paths = {
        name: _expand_skill_path(root_map, raw_path)
        for name, raw_path in re.findall(r"- ([^:\n]+):.*?\(file: ([^)]+)\)", skills_match.group(1))
    }
    missing = sorted(required_skills - skills)
    if missing:
        raise error_cls(f"Codex prompt-input missing required skills: {', '.join(missing)}")
    roots = sorted({str(Path(path).parent.parent.resolve()) for path in resolved_skill_paths.values()})
    forbidden_roots = {
        str((Path(result["trace"]["original_home"]) / ".agents/skills").resolve()),
        str((Path(result["trace"]["original_home"]) / ".codex/skills").resolve()),
    }
    leaked = sorted({
        path
        for path in [*roots, *resolved_skill_paths.values()]
        if path in forbidden_roots or "/plugins/" in path
    })
    if leaked:
        raise error_cls(f"Codex prompt-input exposed forbidden user roots: {', '.join(leaked)}")
    user_skill_paths = []
    isolated_codex_skills = Path(str(result["trace"]["isolated_codex_home"])) / "skills"
    isolated_home_skills = Path(str(result["trace"]["isolated_home"])) / ".agents" / "skills"
    for name, path in resolved_skill_paths.items():
        resolved = Path(path)
        if resolved.is_relative_to(isolated_codex_skills) and not resolved.is_relative_to(isolated_codex_skills / ".system"):
            user_skill_paths.append(f"{name}={path}")
        elif resolved.is_relative_to(isolated_home_skills):
            user_skill_paths.append(f"{name}={path}")
    if user_skill_paths:
        raise error_cls("Codex prompt-input exposed isolated user-only skills: " + ", ".join(sorted(user_skill_paths)))
    warning_hits = sorted(set(TRUNCATION_RE.findall(str(result["stdout"]) + "\n" + str(result["stderr"]))))
    if warning_hits:
        raise error_cls(f"Codex prompt-input emitted truncation warning readback: {warning_hits}")
    if FORBIDDEN_FORWARD_ARG in list(result["trace"]["forwarded_argv"]):
        raise error_cls(f"Codex wrapper forwarded forbidden argv {FORBIDDEN_FORWARD_ARG}")
    return {
        "argv": result["argv"],
        "forwarded_argv": result["trace"]["forwarded_argv"],
        "skill_roots": roots,
        "skill_paths": resolved_skill_paths,
        "skills": sorted(skills),
        "warning_readback": warning_hits,
        "trace": result["trace"],
    }


def _expand_skill_path(root_map: Mapping[str, str], raw_path: str) -> str:
    root_name, _, suffix = raw_path.partition("/")
    if root_name in root_map:
        return str((Path(root_map[root_name]) / suffix).resolve())
    return raw_path


def _plugin_receipt(result: Mapping[str, Any], *, error_cls: type[Exception]) -> dict[str, Any]:
    payload = json.loads(str(result["stdout"]))
    installed = list(payload.get("installed") or [])
    available = list(payload.get("available") or [])
    if installed or available:
        names = [str(item.get("pluginId") or item.get("name") or "<unknown>") for item in [*installed, *available]]
        raise error_cls(f"Codex plugin surface must be empty inside isolated carrier; got {', '.join(names)}")
    return {
        "argv": result["argv"],
        "forwarded_argv": result["trace"]["forwarded_argv"],
        "installed": installed,
        "available": available,
        "trace": result["trace"],
    }

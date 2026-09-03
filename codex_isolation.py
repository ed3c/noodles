from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import tomllib
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, Mapping

CODEX_WRAPPER_DIR = ".agents/bin"
CODEX_WRAPPER = f"{CODEX_WRAPPER_DIR}/codex"
NOODLE_RUNTIME_ROOT = ".noodle"
ISOLATED_HOME = ".noodle/codex-isolation/home"
ISOLATED_CODEX_HOME = ".noodle/codex-isolation/codex-home"
PROJECT_SKILLS_ROOT = ".agents/skills"
FORBIDDEN_FORWARD_ARG = "--dangerously-bypass-approvals-and-sandbox"
# constraint: ed3c/noodles#260 - terminal state is TYPED. These are the only Codex signals that may
# constraint: decide one: the two turn lifecycle terminals and the stream-level error event, plus the
# constraint: process exit status the caller supplies. The strings "truncated"/"failed"/"completed"
# constraint: inside output text are PAYLOAD and are never read as control here, which is why
# constraint: TRUNCATION_RE was deleted rather than anchored - see codex_terminal_state.
CODEX_TURN_COMPLETED = "turn.completed"
CODEX_TURN_FAILED = "turn.failed"
CODEX_STREAM_ERROR = "error"
CODEX_TERMINAL_EVENT_TYPES = (CODEX_TURN_COMPLETED, CODEX_TURN_FAILED, CODEX_STREAM_ERROR)
CODEX_ITEM_COMPLETED = "item.completed"
CODEX_NOTICE_ITEM_TYPE = "error"
PERMISSION_PROFILE_OVERRIDES = (
    'approval_policy="never"',
    'default_permissions="noodles-cook"',
    'permissions.noodles-cook.extends=":workspace"',
    'permissions.noodles-cook.workspace_roots={"/Users/neon/noodles/.git"=true}',
    'permissions.noodles-cook.filesystem={":workspace_roots"={".agents/skills"="write"}}',
    "permissions.noodles-cook.network.enabled=true",
)
PERMISSION_PROFILE_ARGS = (
    "--ignore-user-config",
    *(item for override in PERMISSION_PROFILE_OVERRIDES for item in ("-c", override)),
)
LEGACY_SANDBOX_ERROR = ".noodle.toml agents.codex.args must not combine the permission profile with legacy sandbox settings"
SKILL_PERMISSION_ERROR = ".noodle.toml agents.codex.args must grant write only to '.agents/skills' inside workspace roots"
EXACT_PROFILE_ERROR = ".noodle.toml agents.codex.args must define the exact 'noodles-cook' permission profile"


def parse_codex_events(text: str, *, error_cls: type[Exception]) -> list[dict[str, Any]]:
    """Every typed event on its own line of a `codex exec --json` stream.

    Fails closed on a line it cannot type, the same shape `runtime_contract._session_events` already
    uses for the Noodle event log: a line that is not a JSON object carries no `type`, and guessing
    at one is the substring inference ed3c/noodles#260 exists to delete. The recorded stream in
    tests/fixtures/codex-exec-turn-completed.jsonl is pure JSONL on stdout - the runtime's own
    chatter goes to stderr - so a malformed stdout line is a real defect, not ordinary noise."""
    events: list[dict[str, Any]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise error_cls(f"invalid Codex JSONL event on line {number}: {exc}") from exc
        if not isinstance(event, dict):
            raise error_cls(f"invalid Codex JSONL event on line {number}: expected object")
        events.append(event)
    return events


# constraint: ed3c/noodles#260 - the deleted class, named so a reader does not reintroduce it: the
# constraint: previous TRUNCATION_RE matched `truncat|skill-context-budget` anywhere in stdout+stderr
# constraint: and RAISED. Recorded provider bytes red it in both directions at once. The real notice
# constraint: Codex emits reads "Skill descriptions were shortened to fit the skills context budget"
# constraint: - spaces, not hyphens - so the pattern MISSED the very message it was written for; and
# constraint: any payload carrying the letters "truncat" (a skill described as "truncate long logs",
# constraint: an agent message saying nothing was truncated) hard-failed a healthy run. Deepest of
# constraint: the three: in tests/fixtures/codex-exec-turn-completed.jsonl those notices arrive on a
# constraint: turn whose typed terminal event is `turn.completed` at exit status 0, so even a HIT was
# constraint: never a terminal signal. Text is payload; only the sources below decide.
def codex_terminal_state(
    exit_status: int | None,
    events: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Whether a Codex run reached a terminal state, decided only from typed sources.

    The two admitted sources are the process exit status and the typed lifecycle events
    `turn.completed`, `turn.failed` and the stream-level `error`. `exit_status=None` means the
    process has not exited yet and is a distinct reading, never a stand-in for zero.

    Where the two sources disagree, the rule is written rather than emergent, because both
    directions really happen: a non-zero exit outranks a `turn.completed`, since the process is the
    outer contract and a turn that finished inside a run that then died is not a completed run; and
    `turn.failed`/`error` outrank a zero exit, which is the inversion a text reader gets backwards
    every time - tests/fixtures/codex-exec-turn-failed.jsonl carries an agent message that says the
    step "completed successfully and nothing was truncated" under a `turn.failed` terminal.

    Ceiling, stated rather than implied: the LAST terminal event in the stream is the one that
    decides, so on a resumed multi-turn stream this reports the current turn rather than the first.
    `detail` is copied verbatim off the typed event for a human reader and is never parsed."""
    terminal_event: Mapping[str, Any] | None = None
    for event in events:
        if str(event.get("type") or "") in CODEX_TERMINAL_EVENT_TYPES:
            terminal_event = event
    event_type = str(terminal_event.get("type") or "") if terminal_event is not None else None
    if exit_status is not None and int(exit_status) != 0:
        state, source = "failed", "process_exit"
    elif event_type in {CODEX_TURN_FAILED, CODEX_STREAM_ERROR}:
        state, source = "failed", event_type
    elif event_type == CODEX_TURN_COMPLETED:
        state, source = "completed", event_type
    elif exit_status is not None:
        state, source = "completed", "process_exit"
    else:
        state, source = "running", None
    return {
        "state": state,
        "terminal": state != "running",
        "source": source,
        "exit_status": exit_status,
        "detail": _codex_event_detail(terminal_event) if source != "process_exit" else None,
    }


def _codex_event_detail(event: Mapping[str, Any] | None) -> str | None:
    if event is None:
        return None
    error = event.get("error")
    if isinstance(error, Mapping) and error.get("message") is not None:
        return str(error["message"])
    return str(event["message"]) if event.get("message") is not None else None


def codex_context_notices(events: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Diagnostic-only notices Codex reports as completed items of type `error`.

    Non-control by construction and by receipt: every notice in the recorded successful run is one of
    these, and that run's terminal state is `completed`. Nothing here may reach a verdict - this is
    what "purely diagnostic" has to look like once the inference is gone: read off a typed item,
    carried verbatim, consulted by a human."""
    notices: list[dict[str, str]] = []
    for event in events:
        item = event.get("item")
        if str(event.get("type") or "") != CODEX_ITEM_COMPLETED or not isinstance(item, Mapping):
            continue
        if str(item.get("type") or "") != CODEX_NOTICE_ITEM_TYPE:
            continue
        notices.append({"item_id": str(item.get("id") or ""), "message": str(item.get("message") or "")})
    return notices


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
    overrides = _config_overrides(args)
    parsed_overrides = [_parse_config_override(raw) for raw in overrides]
    legacy_sandbox = any(str(arg) == "--sandbox" or str(arg).startswith("--sandbox=") for arg in args)
    legacy_sandbox = legacy_sandbox or any(
        key == "sandbox_mode" or key == "sandbox_workspace_write" or key.startswith("sandbox_workspace_write.")
        for key, _value in parsed_overrides
    )
    if legacy_sandbox:
        errors.append(LEGACY_SANDBOX_ERROR)
    if not any(key == "approval_policy" and value == "never" for key, value in parsed_overrides):
        errors.append('.noodle.toml agents.codex.args must preserve \'-c approval_policy="never"\'')
    filesystem_values = [
        value for key, value in parsed_overrides if key == "permissions.noodles-cook.filesystem"
    ]
    expected_filesystem = {":workspace_roots": {".agents/skills": "write"}}
    if filesystem_values != [expected_filesystem]:
        errors.append(SKILL_PERMISSION_ERROR)
    if tuple(str(arg) for arg in args) != PERMISSION_PROFILE_ARGS:
        errors.append(EXACT_PROFILE_ERROR)
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


# constraint: ed3c/noodles#313 - .gitignore carries `.noodle/*`, so the observer every lane actually
# constraint: runs to report "zero residue" (`git status --porcelain --untracked-files=all`) is blind
# constraint: to exactly the residue the clause forbids, and the clause has never once been evaluated.
# constraint: `--ignored=matching` is the only git observer that sees these paths at all.
def noodle_runtime_residue(root: Path, *, error_cls: type[Exception]) -> list[str]:
    """Repository-relative `.noodle/` paths this checkout carries that git ignores.

    Scoped to `.noodle/` on purpose: `__pycache__/` is ignored too and is not runtime state, so a
    blanket "anything ignored is residue" observer would red every run and be turned off. Git
    collapses an ignored directory to a single entry, so a directory entry is walked here and the
    directory itself is kept: the diagnostic then names `.noodle/codex-isolation/home` rather than
    only its prefix, and an empty written directory is still residue rather than silence."""
    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all", "--ignored=matching"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise error_cls(f"residue observer could not read git status in {root}: {result.stderr.strip() or result.stdout.strip()}")
    residue: set[str] = set()
    for line in result.stdout.splitlines():
        if not line.startswith("!! "):
            continue
        entry = line[3:].strip().strip('"').rstrip("/")
        if entry != NOODLE_RUNTIME_ROOT and not entry.startswith(f"{NOODLE_RUNTIME_ROOT}/"):
            continue
        residue.add(entry)
        target = root / entry
        if target.is_dir():
            residue.update(child.relative_to(root).as_posix() for child in target.rglob("*"))
    return sorted(residue)


def _config_overrides(args: list[Any]) -> list[str]:
    overrides: list[str] = []
    for index, value in enumerate(args):
        argument = str(value)
        if argument in {"-c", "--config"} and index + 1 < len(args):
            overrides.append(str(args[index + 1]))
        elif argument.startswith("--config="):
            overrides.append(argument.split("=", 1)[1])
    return overrides


def _parse_config_override(raw: str) -> tuple[str, Any]:
    key, separator, value = raw.partition("=")
    if not separator:
        return raw.strip(), None
    try:
        parsed = tomllib.loads(f"value={value}")["value"]
    except (tomllib.TOMLDecodeError, KeyError):
        parsed = None
    return key.strip(), parsed


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
    # constraint: ed3c/noodles#260 - the canary's terminal verdict is read off the typed decision
    # constraint: rather than open-coded here, so this call site and every `codex exec --json`
    # constraint: consumer share ONE rule. `codex debug` emits no lifecycle events, so the exit
    # constraint: status is this run's only admitted source and it is passed as exactly that.
    terminal = codex_terminal_state(result.returncode)
    if terminal["state"] != "completed":
        raise error_cls(f"Codex isolation canary failed for {' '.join(argv)}: {result.stderr.strip() or result.stdout.strip()}")
    return {
        "argv": argv,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "terminal": terminal,
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
    if FORBIDDEN_FORWARD_ARG in list(result["trace"]["forwarded_argv"]):
        raise error_cls(f"Codex wrapper forwarded forbidden argv {FORBIDDEN_FORWARD_ARG}")
    return {
        "argv": result["argv"],
        "forwarded_argv": result["trace"]["forwarded_argv"],
        "skill_roots": roots,
        "skill_paths": resolved_skill_paths,
        "skills": sorted(skills),
        "terminal": result["terminal"],
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

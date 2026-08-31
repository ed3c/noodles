#!/usr/bin/env python3
"""Fresh physical validation of a bounded Serena edit lifecycle (VAL-SERENA-EDIT-01).

`ed3c/noodles#8` proved read-only navigation. This probe runs the next step physically:
`find_symbol -> find_referencing_symbols -> replace_symbol_body -> immutable tests -> diff and
source readback -> cleanup`, once as a positive run and once per planted negative control.

Every run happens inside a throwaway `git archive` export of one exact repository commit, so a
real edit really lands on real source while the repository worktree is never touched. Serena is
not a repository dependency; `tests/test_serena_bounded_edit.py` re-derives the recorded facts
from repository source without importing it.

Run it with an interpreter that has the pinned serena-agent installed:

    uv venv --python 3.13 /tmp/serena-venv
    VIRTUAL_ENV=/tmp/serena-venv uv pip install serena-agent==1.7.0
    /tmp/serena-venv/bin/python migrations/skills-shared/serena_bounded_edit_probe.py

The edit boundary is configuration-enforced, never promised: the exposed tool set is a fixed
allowlist holding exactly one editing tool, so `execute_shell_command`, `create_text_file`,
`replace_content` and `rename_symbol` are absent from the run rather than merely unused.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "serena-bounded-edit-evidence.json"

# constraint: exact custody pin for the external tool, carried the same way ed3c/noodles#8 landed it.
# constraint: Serena stays out of policy/providers.lock.json on purpose: that lock drives provider_sync
# constraint: checkouts under .noodle/providers and its enabled set is a closed allowlist, so an entry
# constraint: there would be an inert fake provider. The pin lives with the evidence it authorises.
PIN_SOURCE = "https://github.com/oraios/serena.git"
PIN_COMMIT = "949a27ef1e5fda1a6e7b561e777bcece345c6ffd"
PIN_DISTRIBUTION = {
    "index": "https://pypi.org/simple",
    "package": "serena-agent",
    "version": "1.7.0",
    "sdist_sha256": "1ef15db14ee5426f3e3dc48fdd7bb7e864d1f35359115eaa3bdd7248b1533ce6",
    "wheel_sha256": "6dbf1459670d96fb0595f84932adef34260a6fe14ba5135b901fdb3c8c76e891",
}

# constraint: bounded by allowlist, not by denylist - exactly one editing tool is reachable, so no
# constraint: shell, no free-form file writer, no rename. A Serena release adding an editing tool
# constraint: cannot widen this run.
BOUNDED_TOOLS = ("find_symbol", "find_referencing_symbols", "replace_symbol_body")
EDITING_TOOLS = ("replace_symbol_body",)

SUBJECT_SYMBOL = "validate_skill_config_paths"
SUBJECT_FILE = "provider_contract.py"
DECLARED_SCOPE = ("provider_contract.py",)
PROTECTED_PREFIX = "tests/"
IMMUTABLE_TEST_MODULE = "tests.test_provider_replacement"

OUT_OF_SCOPE_SYMBOL = "validate_enabled_provider_names"
OUT_OF_SCOPE_FILE = "runtime_contract.py"

EQUIVALENT_BODY = '''def validate_skill_config_paths(skill_paths: list[str]) -> list[str]:
    present = set(skill_paths)
    errors: list[str] = []
    if CONTROL_NOODLE_DISCOVERY_ROOT not in present:
        errors.append(f".noodle.toml skills.paths must include {CONTROL_NOODLE_DISCOVERY_ROOT}")
    if RETIRED_PROVIDER_DISCOVERY_ROOT in present:
        errors.append(".noodle.toml skills.paths must not retain retired matt-engineering discovery")
    return errors
'''

REGRESSING_BODY = '''def validate_skill_config_paths(skill_paths: list[str]) -> list[str]:
    errors: list[str] = []
    if RETIRED_PROVIDER_DISCOVERY_ROOT in skill_paths:
        errors.append(".noodle.toml skills.paths must not retain retired matt-engineering discovery")
    return errors
'''

OUT_OF_SCOPE_BODY = '''def validate_enabled_provider_names(enabled_names: set[str]) -> list[str]:
    return validate_provider_names(set(enabled_names), CURSOR_PSTACK_PROVIDER)
'''

STALE_DRIFT = (
    SUBJECT_FILE,
    "    if RETIRED_PROVIDER_DISCOVERY_ROOT in skill_paths:\n",
    "    if RETIRED_PROVIDER_DISCOVERY_ROOT in list(skill_paths):\n",
)
REFERENCE_DRIFT = (
    "noodles.py",
    '        errors.extend(runtime_contract.validate_skill_config_paths('
    '[str(path) for path in noodle_config.get("skills", {}).get("paths", [])]))\n',
    '        configured_skill_paths = [str(path) for path in noodle_config.get("skills", {}).get("paths", [])]\n'
    '        errors.extend(runtime_contract.validate_skill_config_paths(configured_skill_paths))\n',
)

# constraint: the admission rule lives in exactly one place here and is recomputed independently by
# constraint: tests/test_serena_bounded_edit.py, so the receipt's own verdict is never the oracle.
GUARD_RULES: tuple[tuple[str, Callable[[dict[str, Any]], bool]], ...] = (
    ("scope_violation", lambda run: bool(run["out_of_scope_paths"])),
    ("stale_index", lambda run: not run["navigation_body_present_at_edit_time"]),
    ("reference_drift", lambda run: not run["reference_sites_intact"]),
    ("immutable_tests_failed", lambda run: not run["immutable_tests"]["passed"]),
    ("immutable_tests_mutated", lambda run: not run["immutable_test_files_unchanged"]),
)


def guards(run: dict[str, Any]) -> list[str]:
    return [name for name, rule in GUARD_RULES if rule(run)]


def git(root: Path, *args: str) -> str:
    # constraint: strip only the trailing newline - `status --porcelain` encodes the staging state in
    # constraint: the first two columns, so a full strip would eat the leading column of the first line.
    result = subprocess.run(["git", *args], cwd=str(root), text=True, capture_output=True, check=True)
    return result.stdout.rstrip("\n")


def digest_map(root: Path) -> dict[str, str]:
    """Digest every exported file so a change is a measured fact, not a claim about intent."""
    digests: dict[str, str] = {}
    for path in root.rglob("*"):
        if path.is_file() and ".git" not in path.relative_to(root).parts:
            digests[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


def export(commit: str, root: Path) -> Path:
    """Materialise one exact commit outside the repository and give it its own git identity."""
    root.mkdir(parents=True)
    archive = subprocess.run(
        ["git", "archive", commit], cwd=str(REPOSITORY_ROOT), capture_output=True, check=True
    ).stdout
    subprocess.run(["tar", "-x", "-C", str(root)], input=archive, check=True)
    identity = ["-c", "user.name=ed3c", "-c", "user.email=ed3c@users.noreply.github.com"]
    git(root, "init", "-q", ".")
    git(root, *identity, "add", "-A")
    git(root, *identity, "commit", "-q", "-m", f"export of {commit}")
    return root


def build_agent(project_root: Path, data_root: Path) -> Any:
    """Start one agent whose whole footprint - config, index, memories - lives outside the repository."""
    serena_home = Path(os.environ["SERENA_HOME"])
    serena_home.mkdir(parents=True, exist_ok=True)
    (serena_home / "serena_config.yml").write_text(
        "gui_log_window: false\n"
        "web_dashboard: false\n"
        "record_tool_usage_stats: false\n"
        "log_level: 40\n"
        "projects: []\n"
        f"fixed_tools: [{', '.join(BOUNDED_TOOLS)}]\n"
        f"project_serena_folder_location: {data_root}/$projectFolderName/.serena\n",
        encoding="utf-8",
    )

    from serena.agent import SerenaAgent
    from serena.config.context_mode import SerenaAgentContext
    from serena.config.serena_config import ModeSelectionDefinitionWithBaseModes

    agent = SerenaAgent(
        project=str(project_root),
        context=SerenaAgentContext.load("agent"),
        modes=ModeSelectionDefinitionWithBaseModes(base_modes=(), default_modes=()),
    )
    # constraint: project initialisation is issued to a serial task queue, so a tool call made before it
    # constraint: drains silently answers from an unstarted language server with zero matches. Queue a
    # constraint: no-op behind it and wait, or the navigation step reports absence that is not absence.
    agent.execute_task(lambda: None, name="await_project_initialisation")
    return agent


def shutdown(agent: Any) -> None:
    # constraint: SerenaAgent.shutdown() SIGTERMs its own process; on_shutdown() releases the language
    # constraint: server and task executor without taking the probe down before it writes its receipt.
    agent.on_shutdown()


def find_symbol(agent: Any, pattern: str, **kwargs: Any) -> Any:
    from serena.tools import FindSymbolTool

    return json.loads(agent.get_tool(FindSymbolTool).apply(pattern, **kwargs))


def find_references(agent: Any, name_path: str, relative_path: str) -> Any:
    from serena.tools import FindReferencingSymbolsTool

    return json.loads(agent.get_tool(FindReferencingSymbolsTool).apply(name_path, relative_path))


def replace_symbol_body(agent: Any, name_path: str, relative_path: str, body: str) -> str:
    from serena.tools import ReplaceSymbolBodyTool

    return agent.get_tool(ReplaceSymbolBodyTool).apply(name_path, relative_path, body)


def reference_sites(references: Any) -> list[dict[str, str]]:
    sites: list[dict[str, str]] = []
    for relative_path, by_kind in references.items():
        for entries in by_kind.values():
            for entry in entries:
                for line in entry["content_around_reference"].splitlines():
                    if line.lstrip().startswith(">"):
                        sites.append({"relative_path": relative_path, "text": line.split(":", 1)[1].strip()})
    return sites


def site_readback(root: Path, site: dict[str, str]) -> dict[str, Any]:
    """Resolve a claimed reference straight from source: the index is never the oracle."""
    lines = (root / site["relative_path"]).read_text(encoding="utf-8").splitlines()
    hits = [index + 1 for index, line in enumerate(lines) if line.strip() == site["text"]]
    return {
        "relative_path": site["relative_path"],
        "text": site["text"],
        "text_sha256": hashlib.sha256(site["text"].encode("utf-8")).hexdigest(),
        "occurrences": len(hits),
        "line": hits[0] if hits else None,
    }


def digest_of(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def run_immutable_tests(interpreter: str, root: Path) -> dict[str, Any]:
    environment = dict(os.environ, PYTHONPATH=str(root))
    environment.pop("VIRTUAL_ENV", None)
    result = subprocess.run(
        [interpreter, "-m", "unittest", IMMUTABLE_TEST_MODULE],
        cwd=str(root), capture_output=True, text=True, env=environment,
    )
    return {
        "returncode": result.returncode,
        "passed": result.returncode == 0,
        "summary": result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "",
    }


def apply_drift(root: Path, drift: tuple[str, str, str]) -> dict[str, Any]:
    relative_path, before, after = drift
    path = root / relative_path
    source = path.read_text(encoding="utf-8")
    if before not in source:
        raise SystemExit(f"drift control could not locate its anchor in {relative_path}")
    path.write_text(source.replace(before, after, 1), encoding="utf-8")
    return {"applied": True, "relative_path": relative_path, "semantics_preserving": True}


def run_case(
    commit: str,
    workspace: Path,
    name: str,
    interpreter: str,
    *,
    edit_symbol: str,
    edit_file: str,
    edit_body: str,
    designated_guard: str | None,
    drift: tuple[str, str, str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """One full lifecycle on its own export; every step is appended only once it really completed."""
    root = export(commit, workspace / name)
    steps: list[str] = ["export"]
    data_root = workspace / f"{name}-data"
    agent = build_agent(root, data_root)
    try:
        surface = tool_surface(agent, data_root)
        matches = find_symbol(agent, SUBJECT_SYMBOL, relative_path=SUBJECT_FILE, include_body=True)
        steps.append("find_symbol")
        sites = reference_sites(find_references(agent, SUBJECT_SYMBOL, SUBJECT_FILE))
        steps.append("find_referencing_symbols")
        navigation_body = matches[0]["body"] if matches else ""
        drift_receipt = apply_drift(root, drift) if drift else {"applied": False}
        if drift:
            steps.append("drift_control")
        before = digest_map(root)
        source_at_edit_time = (root / SUBJECT_FILE).read_text(encoding="utf-8")
        edit_result = replace_symbol_body(agent, edit_symbol, edit_file, edit_body)
        steps.append("replace_symbol_body")
    finally:
        shutdown(agent)
    after = digest_map(root)
    tests = run_immutable_tests(interpreter, root)
    steps.append("immutable_tests")

    changed = sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))
    readbacks = [site_readback(root, site) for site in sites]
    steps.append("diff_readback")
    run = {
        "designated_guard": designated_guard,
        "steps": steps,
        "root_outside_repository": str(REPOSITORY_ROOT) not in str(root),
        "drift": drift_receipt,
        "navigation": {
            "match_count": len(matches),
            "body_sha256": hashlib.sha256(navigation_body.encode("utf-8")).hexdigest(),
            "reference_sites_sha256": digest_of(sites),
        },
        "edit": {
            "tool": "replace_symbol_body",
            "name_path": edit_symbol,
            "relative_path": edit_file,
            "result": edit_result.strip(),
            "body_sha256": hashlib.sha256(edit_body.encode("utf-8")).hexdigest(),
        },
        "navigation_body_present_at_edit_time": bool(navigation_body) and navigation_body in source_at_edit_time,
        "edit_readback": edit_body in (root / edit_file).read_text(encoding="utf-8"),
        "declared_scope": list(DECLARED_SCOPE),
        "edit_changed_paths": changed,
        "out_of_scope_paths": [path for path in changed if path not in DECLARED_SCOPE],
        "total_changed_paths_vs_commit": sorted(line[3:] for line in git(root, "status", "--porcelain").splitlines()),
        "reference_sites_intact": bool(readbacks) and all(item["occurrences"] == 1 for item in readbacks),
        "drifted_reference_sites": [item["relative_path"] for item in readbacks if item["occurrences"] != 1],
        "immutable_test_files_unchanged": all(
            before.get(key) == after.get(key)
            for key in set(before) | set(after)
            if key.startswith(PROTECTED_PREFIX)
        ),
        "immutable_tests": tests,
    }
    run["blocked_by"] = guards(run)
    run["admitted"] = not run["blocked_by"]
    return run, {"surface": surface, "matches": matches, "sites": sites}


def tool_surface(agent: Any, data_root: Path) -> dict[str, Any]:
    exposed = agent.get_exposed_tool_instances()
    return {
        "exposed_tools": sorted(tool.get_name_from_cls() for tool in exposed),
        "editing_tools_exposed": sorted(tool.get_name_from_cls() for tool in exposed if tool.can_edit()),
        "project_serena_folder": str(data_root),
        "project_serena_folder_inside_repository": str(data_root).startswith(str(REPOSITORY_ROOT)),
    }


def build_receipt(pins: dict[str, Any], workspace: Path, interpreter: str) -> dict[str, Any]:
    root = REPOSITORY_ROOT
    commit = git(root, "rev-parse", "HEAD")
    tree_before = git(root, "rev-parse", "HEAD^{tree}")
    status_before = git(root, "status", "--porcelain")
    dirty = {line[3:] for line in status_before.splitlines()}
    if dirty & ({SUBJECT_FILE, OUT_OF_SCOPE_FILE, REFERENCE_DRIFT[0]}):
        raise SystemExit("refusing to record evidence: a subject or reference file is uncommitted")

    cases = {
        "bounded_edit": dict(edit_symbol=SUBJECT_SYMBOL, edit_file=SUBJECT_FILE, edit_body=EQUIVALENT_BODY, designated_guard=None),
        "out_of_scope_edit": dict(edit_symbol=OUT_OF_SCOPE_SYMBOL, edit_file=OUT_OF_SCOPE_FILE, edit_body=OUT_OF_SCOPE_BODY, designated_guard="scope_violation"),
        "stale_symbol_index": dict(edit_symbol=SUBJECT_SYMBOL, edit_file=SUBJECT_FILE, edit_body=EQUIVALENT_BODY, designated_guard="stale_index", drift=STALE_DRIFT),
        "changed_reference": dict(edit_symbol=SUBJECT_SYMBOL, edit_file=SUBJECT_FILE, edit_body=EQUIVALENT_BODY, designated_guard="reference_drift", drift=REFERENCE_DRIFT),
        "failing_immutable_test": dict(edit_symbol=SUBJECT_SYMBOL, edit_file=SUBJECT_FILE, edit_body=REGRESSING_BODY, designated_guard="immutable_tests_failed"),
    }
    outcomes = {name: run_case(commit, workspace, name, interpreter, **case) for name, case in cases.items()}
    runs = {name: outcome[0] for name, outcome in outcomes.items()}
    surface = outcomes["bounded_edit"][1]["surface"]
    matches = outcomes["bounded_edit"][1]["matches"]
    sites = outcomes["bounded_edit"][1]["sites"]

    status_after = git(root, "status", "--porcelain")
    shutil.rmtree(workspace)
    return {
        "schema_version": 1,
        "capability_id": "serena-bounded-edit",
        "subject_issue": "ed3c/noodles#12",
        "pin": pins,
        "subject": {
            "repository": "ed3c/noodles",
            "commit": commit,
            "tree": tree_before,
            "symbol": SUBJECT_SYMBOL,
            "relative_path": SUBJECT_FILE,
            "declared_scope": list(DECLARED_SCOPE),
            "uncommitted_paths_at_probe_time": sorted(dirty),
        },
        "tool_surface": surface,
        "navigation": {
            "find_symbol": {
                "query": {"name_path_pattern": SUBJECT_SYMBOL, "relative_path": SUBJECT_FILE},
                "matches": [
                    {key: match[key] for key in ("name_path", "relative_path", "kind", "body_location")}
                    for match in matches
                ],
                "body": matches[0]["body"] if matches else "",
                "body_sha256": hashlib.sha256((matches[0]["body"] if matches else "").encode("utf-8")).hexdigest(),
            },
            "find_referencing_symbols": {
                "query": {"name_path": SUBJECT_SYMBOL, "relative_path": SUBJECT_FILE},
                "referencing_files": sorted({site["relative_path"] for site in sites}),
                "reference_sites_sha256": digest_of(sites),
            },
            "source_readback": [site_readback(root, site) for site in sites],
        },
        "immutable_tests": {
            "module": IMMUTABLE_TEST_MODULE,
            "argv": [interpreter, "-m", "unittest", IMMUTABLE_TEST_MODULE],
            "interpreter_version": subprocess.run(
                [interpreter, "-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))"],
                capture_output=True, text=True, check=True,
            ).stdout.strip(),
            "protected_prefix": PROTECTED_PREFIX,
        },
        "guard_names": [name for name, _rule in GUARD_RULES],
        "runs": runs,
        "residue": {
            "worktree_unchanged": status_after == status_before,
            "tree_unchanged": git(root, "rev-parse", "HEAD^{tree}") == tree_before,
            "paths_created_by_invocation": sorted(set(status_after.splitlines()) - set(status_before.splitlines())),
            "serena_folder_in_repository": (root / ".serena").exists(),
            "workspace_removed": not workspace.exists(),
        },
    }


def resolve_pins() -> dict[str, Any]:
    """Refuse to produce evidence under any build other than the pinned one."""
    import importlib.metadata

    version = importlib.metadata.version(PIN_DISTRIBUTION["package"])
    if version != PIN_DISTRIBUTION["version"]:
        raise SystemExit(f"installed {PIN_DISTRIBUTION['package']} {version} != pinned {PIN_DISTRIBUTION['version']}")
    return {
        "distribution": dict(PIN_DISTRIBUTION),
        "source": PIN_SOURCE,
        "commit": PIN_COMMIT,
        "python": sys.version.split()[0],
        "language_backend": "LSP",
        "context": "agent",
        "modes": [],
        "fixed_tools": list(BOUNDED_TOOLS),
        "editing_tools": list(EDITING_TOOLS),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--test-python", default=shutil.which("python3"))
    args = parser.parse_args()
    pins = resolve_pins()
    if not args.test_python:
        raise SystemExit("no python3 on PATH to run the immutable tests with")

    # constraint: SerenaPaths caches the home directory on first import of the serena package, so a
    # constraint: redirect applied later silently falls back to the operator's real ~/.serena and
    # constraint: autoregisters project paths there. Redirect before any serena import.
    # constraint: resolve() the workspace as well - under a symlinked temp root (macOS /var -> /private/var)
    # constraint: the language server reports zero symbols while edits still land, which reads as absence.
    workspace = Path(tempfile.mkdtemp(prefix="serena-bounded-edit-")).resolve()
    os.environ["SERENA_HOME"] = str(workspace / "home")
    if "serena" in sys.modules:
        raise SystemExit("serena was imported before SERENA_HOME was redirected")

    receipt = build_receipt(pins, workspace, args.test_python)
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

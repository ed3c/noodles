#!/usr/bin/env python3
"""Fresh physical revalidation of read-only Serena symbol navigation (VAL-SERENA-NAV-01).

Serena is not a repository dependency and `tests/run.sh` never imports it. This probe is the
producer of `serena-navigation-evidence.json`; `tests/test_serena_navigation.py` is the gate
that re-derives every recorded location straight from repository source, so a fabricated or
drifted receipt fails locally without Serena installed.

Run it with an interpreter that has the pinned serena-agent installed:

    uv venv --python 3.13 /tmp/serena-venv
    VIRTUAL_ENV=/tmp/serena-venv uv pip install serena-agent==1.7.0
    /tmp/serena-venv/bin/python migrations/skills-shared/serena_navigation_probe.py

Read-only is enforced by configuration, never by promise: the exposed tool set is a fixed
allowlist (so a future Serena release cannot add an editing tool into this run) and the
per-project `.serena` data folder is redirected outside the repository, so neither the tool
surface nor the index can leave residue behind.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "serena-navigation-evidence.json"

# constraint: exact custody pin for the external tool. Serena is deliberately absent from
# constraint: policy/providers.lock.json: that lock drives provider_sync checkouts under
# constraint: .noodle/providers and its enabled set is a closed allowlist, so an entry there would be
# constraint: an inert fake provider. The pin lives with the evidence it authorises instead, and
# constraint: tests/test_serena_navigation.py rejects any floating ref recorded here.
PIN_SOURCE = "https://github.com/oraios/serena.git"
PIN_COMMIT = "949a27ef1e5fda1a6e7b561e777bcece345c6ffd"
PIN_DISTRIBUTION = {
    "index": "https://pypi.org/simple",
    "package": "serena-agent",
    "version": "1.7.0",
    "sdist_sha256": "1ef15db14ee5426f3e3dc48fdd7bb7e864d1f35359115eaa3bdd7248b1533ce6",
    "wheel_sha256": "6dbf1459670d96fb0595f84932adef34260a6fe14ba5135b901fdb3c8c76e891",
}

# constraint: read-only by allowlist, not by denylist - a Serena release that adds a new editing
# constraint: tool cannot widen this run, whereas the shipped `planning` mode demonstrably leaves rename_symbol,
# constraint: replace_in_files and safe_delete_symbol exposed at 1.7.0.
READ_ONLY_TOOLS = ("find_symbol", "find_referencing_symbols", "get_symbols_overview", "read_file")

SUBJECT_SYMBOL = "validate_admission_policy"
SUBJECT_FILE = "provider_contract.py"
ABSENT_SYMBOL = "validate_admission_policy_absent_control"
AMBIGUOUS_SYMBOL = "sha256_file"
UNSUPPORTED_FILE = ".github/workflows/verify.yml"
UNSUPPORTED_SYMBOL = "candidate-self-tests"


def git(root: Path, *args: str) -> str:
    # constraint: strip only the trailing newline - `status --porcelain` encodes the staging state in
    # constraint: the first two columns, so a full strip would silently eat the leading column of the first line.
    result = subprocess.run(["git", *args], cwd=str(root), text=True, capture_output=True, check=True)
    return result.stdout.rstrip("\n")


def line_readback(root: Path, relative_path: str, text: str) -> dict[str, Any]:
    """Resolve a claimed reference straight from repository source: the index is never the oracle."""
    source = (root / relative_path).read_text(encoding="utf-8")
    lines = source.splitlines()
    hits = [index + 1 for index, line in enumerate(lines) if line.strip() == text.strip()]
    return {
        "relative_path": relative_path,
        "text": text.strip(),
        "text_sha256": hashlib.sha256(text.strip().encode("utf-8")).hexdigest(),
        "occurrences": len(hits),
        "line": hits[0] if hits else None,
    }


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
        f"fixed_tools: [{', '.join(READ_ONLY_TOOLS)}]\n"
        f"project_serena_folder_location: {data_root}/$projectFolderName/.serena\n",
        encoding="utf-8",
    )

    from serena.agent import SerenaAgent
    from serena.config.context_mode import SerenaAgentContext
    from serena.config.serena_config import ModeSelectionDefinitionWithBaseModes

    return SerenaAgent(
        project=str(project_root),
        context=SerenaAgentContext.load("agent"),
        modes=ModeSelectionDefinitionWithBaseModes(base_modes=(), default_modes=()),
    )


def find_symbol(agent: Any, pattern: str, **kwargs: Any) -> Any:
    from serena.tools import FindSymbolTool

    return json.loads(agent.get_tool(FindSymbolTool).apply(pattern, **kwargs))


def find_references(agent: Any, name_path: str, relative_path: str) -> Any:
    from serena.tools import FindReferencingSymbolsTool

    return json.loads(agent.get_tool(FindReferencingSymbolsTool).apply(name_path, relative_path))


def bounded(call: Any) -> dict[str, Any]:
    """Every control has an explicit exit: a bounded refusal is evidence, an exception is not silence."""
    try:
        payload = call()
    except Exception as exc:
        return {"outcome": "bounded_error", "error": f"{type(exc).__name__}: {exc}", "matches": 0}
    matches = len(payload) if isinstance(payload, list) else (0 if not payload else 1)
    return {"outcome": "reported", "matches": matches, "payload": payload}


def reference_sites(references: Any) -> list[dict[str, str]]:
    sites: list[dict[str, str]] = []
    for relative_path, by_kind in references.items():
        for entries in by_kind.values():
            for entry in entries:
                for line in entry["content_around_reference"].splitlines():
                    if line.lstrip().startswith(">"):
                        sites.append({"relative_path": relative_path, "text": line.split(":", 1)[1]})
    return sites


def run_navigation_chain(agent: Any, root: Path) -> dict[str, Any]:
    matches = find_symbol(agent, SUBJECT_SYMBOL, relative_path=SUBJECT_FILE)
    references = find_references(agent, SUBJECT_SYMBOL, SUBJECT_FILE)
    sites = reference_sites(references)
    return {
        "find_symbol": {"query": {"name_path_pattern": SUBJECT_SYMBOL, "relative_path": SUBJECT_FILE}, "matches": matches},
        "find_referencing_symbols": {
            "query": {"name_path": SUBJECT_SYMBOL, "relative_path": SUBJECT_FILE},
            "referencing_files": sorted(references),
        },
        "source_readback": [line_readback(root, site["relative_path"], site["text"]) for site in sites],
    }


def run_controls(agent: Any, root: Path) -> dict[str, Any]:
    absent = bounded(lambda: find_symbol(agent, ABSENT_SYMBOL))
    ambiguous = bounded(lambda: find_symbol(agent, AMBIGUOUS_SYMBOL))
    unsupported = bounded(lambda: find_symbol(agent, UNSUPPORTED_SYMBOL, relative_path=UNSUPPORTED_FILE))
    return {
        "wrong_symbol": {
            "query": ABSENT_SYMBOL,
            "matches": absent["matches"],
            "outcome": absent["outcome"],
            "definitions_in_tracked_source": tracked_definitions(root, f"def {ABSENT_SYMBOL}("),
        },
        "ambiguous_symbol": {
            "query": AMBIGUOUS_SYMBOL,
            "matches": ambiguous["matches"],
            "outcome": ambiguous["outcome"],
            "candidates": [
                {"relative_path": item["relative_path"], "name_path": item["name_path"]}
                for item in (ambiguous.get("payload") or [])
            ],
        },
        "unsupported_language": {
            "query": {"name_path_pattern": UNSUPPORTED_SYMBOL, "relative_path": UNSUPPORTED_FILE},
            "matches": unsupported["matches"],
            "outcome": unsupported["outcome"],
            "error": unsupported.get("error"),
            "occurrences_in_queried_file": (root / UNSUPPORTED_FILE).read_text(encoding="utf-8").count(UNSUPPORTED_SYMBOL),
        },
    }


def tracked_definitions(root: Path, declaration: str) -> int:
    """Count a Python declaration across tracked `.py` source, the same rule the gate recomputes with."""
    count = 0
    for relative in git(root, "ls-files").splitlines():
        path = root / relative
        if path.is_file() and relative.endswith(".py"):
            count += path.read_text(encoding="utf-8", errors="ignore").count(declaration)
    return count


def run_stale_index_control(commit: str, workspace: Path) -> dict[str, Any]:
    """Physically demonstrate that an index hit is not source truth.

    The definition is renamed away in a throwaway export of the exact commit *after* the language
    server has indexed it. Whatever the index then reports, only the direct readback decides.
    """
    copy_root = workspace / "stale-copy"
    copy_root.mkdir(parents=True)
    archive = subprocess.run(
        ["git", "archive", commit], cwd=str(REPOSITORY_ROOT), capture_output=True, check=True
    ).stdout
    subprocess.run(["tar", "-x", "-C", str(copy_root)], input=archive, check=True)

    agent = build_agent(copy_root, workspace / "stale-data")
    try:
        before = find_symbol(agent, SUBJECT_SYMBOL, relative_path=SUBJECT_FILE)
        target = copy_root / SUBJECT_FILE
        original = target.read_text(encoding="utf-8")
        mutated = original.replace(f"def {SUBJECT_SYMBOL}(", f"def {SUBJECT_SYMBOL}_renamed_by_control(", 1)
        if mutated == original:
            raise SystemExit(f"stale-index control could not mutate {SUBJECT_FILE}: definition not found")
        target.write_text(mutated, encoding="utf-8")
        after = bounded(lambda: find_symbol(agent, SUBJECT_SYMBOL, relative_path=SUBJECT_FILE))
        source_after = target.read_text(encoding="utf-8")
        return {
            "isolated_root_outside_repository": str(REPOSITORY_ROOT) not in str(copy_root),
            "mutation_applied": True,
            "mutation": f"def {SUBJECT_SYMBOL}( -> def {SUBJECT_SYMBOL}_renamed_by_control(",
            "matches_before_mutation": len(before),
            "matches_after_mutation": after["matches"],
            "outcome_after_mutation": after["outcome"],
            "readback_confirms_definition_after_mutation": f"def {SUBJECT_SYMBOL}(" in source_after,
        }
    finally:
        shutdown(agent)


def shutdown(agent: Any) -> None:
    # constraint: SerenaAgent.shutdown() SIGTERMs its own process; on_shutdown() releases the
    # constraint: language server and task executor without taking the probe down before it writes its receipt.
    agent.on_shutdown()


def read_only_enforcement(agent: Any, root: Path, data_root: Path) -> dict[str, Any]:
    exposed = agent.get_exposed_tool_instances()
    return {
        "exposed_tools": sorted(tool.get_name_from_cls() for tool in exposed),
        "editing_tools_exposed": sorted(tool.get_name_from_cls() for tool in exposed if tool.can_edit()),
        "project_serena_folder": str(data_root),
        "project_serena_folder_inside_repository": str(data_root).startswith(str(root)),
    }


def build_receipt(pins: dict[str, Any], workspace: Path) -> dict[str, Any]:
    root = REPOSITORY_ROOT
    commit = git(root, "rev-parse", "HEAD")
    status_before = git(root, "status", "--porcelain")
    tree_before = git(root, "rev-parse", "HEAD^{tree}")

    data_root = workspace / "data"
    agent = build_agent(root, data_root)
    try:
        enforcement = read_only_enforcement(agent, root, data_root)
        chain = run_navigation_chain(agent, root)
        controls = run_controls(agent, root)
    finally:
        shutdown(agent)
    controls["stale_index"] = run_stale_index_control(commit, workspace)

    status_after = git(root, "status", "--porcelain")
    return {
        "schema_version": 1,
        "capability_id": "serena-symbol-navigation",
        "subject_issue": "ed3c/noodles#8",
        "pin": pins,
        "subject": {
            "repository": "ed3c/noodles",
            "commit": commit,
            "tree": tree_before,
            "project_root_is_repository_root": True,
            "uncommitted_paths_at_probe_time": sorted(line[3:] for line in status_before.splitlines()),
        },
        "read_only_enforcement": enforcement,
        "chain": chain,
        "controls": controls,
        "residue": {
            "worktree_unchanged": status_after == status_before,
            "tree_unchanged": git(root, "rev-parse", "HEAD^{tree}") == tree_before,
            "paths_created_by_invocation": sorted(set(status_after.splitlines()) - set(status_before.splitlines())),
            "serena_folder_in_repository": (root / ".serena").exists(),
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
        "fixed_tools": list(READ_ONLY_TOOLS),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    pins = resolve_pins()

    # constraint: SerenaPaths caches the home directory on first import of the serena package, so a
    # constraint: redirect applied later silently falls back to the operator's real ~/.serena and autoregisters
    # constraint: this project path there. Redirect before any serena import, or the run leaks off-repo residue.
    workspace = Path(tempfile.mkdtemp(prefix="serena-navigation-"))
    os.environ["SERENA_HOME"] = str(workspace / "home")
    if "serena" in sys.modules:
        raise SystemExit("serena was imported before SERENA_HOME was redirected")

    receipt = build_receipt(pins, workspace)
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

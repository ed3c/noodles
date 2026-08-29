from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

import noodles
import runtime_contract

ENGINE_ROOT = Path(noodles.__file__).resolve().parent
CANDIDATE_ROOT = Path(os.getenv("NOODLES_CANDIDATE_ROOT", ENGINE_ROOT)).resolve()
CURRENT_EXTERNAL_SKILL_PATH = ".noodle/providers/matt-engineering/skills/engineering"
RECOVERY_EXTERNAL_SKILL_PATH = ".noodle/providers/skill-concerns/skills/control-noodle"


def cmd(argv: list[str], cwd: Path) -> str:
    result = subprocess.run(argv, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        raise AssertionError(f"command failed {argv}: {result.stderr or result.stdout}")
    return result.stdout.strip()


def initialize_repo(root: Path) -> None:
    cmd(["git", "init", "-q", "-b", "main"], root)
    cmd(["git", "config", "user.name", "tests"], root)
    cmd(["git", "config", "user.email", "tests@example.invalid"], root)
    cmd(["git", "add", "-A"], root)
    cmd(["git", "commit", "-q", "--allow-empty", "-m", "fixture"], root)


def copy_tracked(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True)
    tracked = cmd(["git", "ls-files"], source).splitlines()
    for relative in tracked:
        src = source / relative
        dst = destination / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst, follow_symlinks=False)
    initialize_repo(destination)


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            digest.update(f"L {relative} {os.readlink(path)}\n".encode("utf-8"))
            continue
        if path.is_dir():
            digest.update(f"D {relative}\n".encode("utf-8"))
            continue
        digest.update(f"F {relative}\n".encode("utf-8"))
        digest.update(path.read_bytes())
        digest.update(b"\n")
    return digest.hexdigest()


def write_noodle_stub(path: Path, version: str) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import os\n"
        "import sys\n"
        "args = sys.argv[1:]\n"
        f"if args == ['--version']:\n    print({version!r})\n"
        "elif len(args) >= 4 and args[0] == '--project-dir' and args[2:] == ['skills', 'list']:\n"
        "    print(os.environ.get('NOODLES_TEST_SKILLS_OUTPUT', ''), end='')\n"
        "else:\n"
        "    raise SystemExit(f'unexpected args: {args}')\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def write_handoff_noodle_stub(path: Path, version: str, blocking: bool = True) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import os\n"
        "import pathlib\n"
        "import subprocess\n"
        "import sys\n"
        "args = sys.argv[1:]\n"
        f"if args == ['--version']:\n    print({version!r})\n"
        "elif len(args) >= 5 and args[0] == '--project-dir' and args[2:4] == ['event', 'emit']:\n"
        "    root = pathlib.Path(args[1])\n"
        "    event_type = args[4]\n"
        "    session = ''\n"
        "    payload = {}\n"
        "    index = 5\n"
        "    while index < len(args):\n"
        "        if args[index] == '--session':\n"
        "            session = args[index + 1]\n"
        "            index += 2\n"
        "            continue\n"
        "        if args[index] == '--payload':\n"
        "            payload = json.loads(args[index + 1])\n"
        "            index += 2\n"
        "            continue\n"
        "        raise SystemExit(f'unexpected args: {args}')\n"
        "    if event_type == 'stage_message':\n"
        f"        payload['blocking'] = {blocking!r}\n"
        "    event = {'type': event_type, 'payload': payload, 'timestamp': '2026-08-29T00:00:00Z', 'session_id': session}\n"
        "    target = root / '.noodle' / 'sessions' / session / 'events.ndjson'\n"
        "    with target.open('a', encoding='utf-8') as handle:\n"
        "        handle.write(json.dumps(event) + '\\n')\n"
        "elif len(args) >= 4 and args[:2] == ['worktree', 'exec']:\n"
        "    root = pathlib.Path(os.getcwd()).resolve()\n"
        "    worktree_name = args[2]\n"
        "    command = args[3:]\n"
        "    if not (root / '.noodle').is_dir():\n"
        "        raise SystemExit(f'cwd is not a Noodle project root: {root}')\n"
        "    worktree_path = None\n"
        "    sessions = root / '.noodle' / 'sessions'\n"
        "    for spawn in sessions.glob('*/spawn.json'):\n"
        "        payload = json.loads(spawn.read_text())\n"
        "        candidate_path = pathlib.Path(str(payload.get('worktree_path') or '')).expanduser()\n"
        "        candidate_name = str(payload.get('worktree_name') or candidate_path.name)\n"
        "        if candidate_name == worktree_name:\n"
        "            worktree_path = candidate_path\n"
        "            break\n"
        "    if worktree_path is None:\n"
        "        raise SystemExit(f'unknown worktree: {worktree_name}')\n"
        "    completed = subprocess.run(command, cwd=str(worktree_path), text=True, check=False)\n"
        "    raise SystemExit(completed.returncode)\n"
        "else:\n"
        "    raise SystemExit(f'unexpected args: {args}')\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def handoff_fixture(
    source: Path,
    subject: str = "ed3c/noodles#33",
    *,
    blocking: bool = True,
    worktree_name: str = "ed3c-noodles-33-0-execute",
) -> tuple[tempfile.TemporaryDirectory[str], Path, Path, str]:
    temp = tempfile.TemporaryDirectory(prefix="noodles-handoff-test-")
    root = Path(temp.name) / "repo"
    copy_tracked(source, root)
    cmd(["git", "remote", "add", "origin", "git@github.com:ed3c/noodles.git"], root)
    binary = Path(temp.name) / "noodle"
    write_handoff_noodle_stub(binary, "v0.1.5", blocking)
    lock_path = root / "policy/runtime.lock.json"
    lock = json.loads(lock_path.read_text())
    lock["runtime"]["command"] = str(binary)
    lock["runtime"]["platforms"]["darwin_arm64"]["binary_sha256"] = runtime_contract.sha256_file(binary)
    lock_path.write_text(json.dumps(lock))
    cmd(["git", "add", "policy/runtime.lock.json"], root)
    cmd(["git", "commit", "-q", "-m", "lock handoff runtime"], root)
    session_id = "ed3c-noodles-33-0-execute-fixture"
    session = root / ".noodle" / "sessions" / session_id
    session.mkdir(parents=True)
    (session / "spawn.json").write_text(json.dumps({"worktree_path": str(root), "worktree_name": worktree_name}))
    (session / "events.ndjson").write_text(json.dumps({
        "type": "action",
        "payload": {"message": f"[order:{subject}] fixture"},
        "timestamp": "2026-08-29T00:00:00Z",
        "session_id": session_id,
    }) + "\n")
    return temp, root, binary, session_id


def provider_fixture(subpath: str = "skills/engineering", license_path: str = "LICENSE") -> tuple[tempfile.TemporaryDirectory[str], Path]:
    temp = tempfile.TemporaryDirectory(prefix="noodles-provider-test-")
    base = Path(temp.name)
    candidate = base / "candidate"
    copy_tracked(CANDIDATE_ROOT, candidate)
    source = base / "source"
    source.mkdir()
    initialize_repo(source)
    (source / "LICENSE").write_text("MIT\n")
    (source / "skills/engineering/example").mkdir(parents=True)
    (source / "skills/engineering/example/SKILL.md").write_text("# Example\n")
    cmd(["git", "add", "-A"], source)
    cmd(["git", "commit", "-q", "-m", "provider"], source)
    commit = cmd(["git", "rev-parse", "HEAD"], source)
    lock_path = candidate / "policy/providers.lock.json"
    lock = json.loads(lock_path.read_text())
    lock["providers"] = [
        {
            "name": "fixture",
            "source": str(source),
            "commit": commit,
            "subpath": subpath,
            "destination": ".noodle/providers/fixture",
            "license_path": license_path,
            "enabled": True,
            "authority": "P",
        }
    ]
    lock_path.write_text(json.dumps(lock))
    cmd(["git", "add", "-A"], candidate)
    cmd(["git", "commit", "-q", "-m", "lock fixture"], candidate)
    return temp, candidate


def cursor_pstack_fixture() -> tuple[tempfile.TemporaryDirectory[str], Path]:
    temp = tempfile.TemporaryDirectory(prefix="noodles-cursor-provider-test-")
    base = Path(temp.name)
    candidate = base / "candidate"
    copy_tracked(CANDIDATE_ROOT, candidate)
    source = base / "source"
    source.mkdir()
    initialize_repo(source)
    (source / "pstack/LICENSE").parent.mkdir(parents=True, exist_ok=True)
    (source / "pstack/LICENSE").write_text("MIT\n")
    (source / "cursor-team-kit/LICENSE").parent.mkdir(parents=True, exist_ok=True)
    (source / "cursor-team-kit/LICENSE").write_text("MIT\n")
    for skill in runtime_contract.CURSOR_PSTACK_REQUIRED_NATIVE_SKILLS:
        skill_dir = source / "pstack/skills" / skill
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(f"# {skill}\n")
    poteto_playbooks = source / "pstack/skills/poteto-mode/playbooks"
    poteto_playbooks.mkdir(parents=True, exist_ok=True)
    for name in ("investigation.md", "feature.md", "multi-phase-plan.md"):
        (poteto_playbooks / name).write_text(f"# {name}\n")
    for skill in ("control-cli", "deslop", "control-ui"):
        skill_dir = source / "cursor-team-kit/skills" / skill
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(f"# {skill}\n")
    extra = source / "cursor-team-kit/skills/review-and-ship"
    extra.mkdir(parents=True)
    (extra / "SKILL.md").write_text("# review-and-ship\n")
    cmd(["git", "add", "-A"], source)
    cmd(["git", "commit", "-q", "-m", "provider"], source)
    commit = cmd(["git", "rev-parse", "HEAD"], source)
    lock_path = candidate / "policy/providers.lock.json"
    lock = json.loads(lock_path.read_text())
    providers = lock["providers"]
    providers[0]["source"] = str(source)
    providers[0]["commit"] = commit
    providers[0]["destination"] = runtime_contract.CURSOR_PSTACK_DESTINATION
    lock_path.write_text(json.dumps(lock))
    cmd(["git", "add", "-A"], candidate)
    cmd(["git", "commit", "-q", "-m", "lock fixture"], candidate)
    return temp, candidate


def current_provider_lock() -> list[dict[str, object]]:
    return [
        {
            "name": "cursor-pstack",
            "source": "https://github.com/cursor/plugins.git",
            "commit": "68836ddaf5697224520f1847d90cdb90ca8babaa",
            "subpath": "pstack/skills",
            "destination": runtime_contract.CURSOR_PSTACK_DESTINATION,
            "license_path": "pstack/LICENSE",
            "enabled": True,
            "authority": "P",
            "purpose": "Engineering lifecycle routing; never a correctness authority.",
        },
        {
            "name": "matt-engineering",
            "source": "https://github.com/mattpocock/skills.git",
            "commit": "6654f6b60cd9d5be8b54c6fafe44346dabeb3b76",
            "subpath": "skills/engineering",
            "destination": ".noodle/providers/matt-engineering",
            "license_path": "LICENSE",
            "enabled": True,
            "authority": "P",
            "purpose": "Replaceable engineering knowledge; never a correctness authority.",
        },
        {
            "name": "skills-shared-compat",
            "source": "https://github.com/ed3c/skills-shared.git",
            "commit": "52b29b38ded9eaacbf7fb1bfa8ccf69ab37870b9",
            "subpath": ".",
            "destination": ".noodle/providers/skills-shared-compat",
            "license_path": "LICENSE",
            "enabled": False,
            "authority": "P",
            "purpose": "Explicitly disabled compatibility source; not a Golden Path dependency.",
        },
    ]


def recovery_provider_lock() -> list[dict[str, object]]:
    return [
        {
            "name": "cursor-pstack",
            "source": "https://github.com/cursor/plugins.git",
            "commit": "68836ddaf5697224520f1847d90cdb90ca8babaa",
            "subpath": "pstack/skills",
            "destination": runtime_contract.CURSOR_PSTACK_DESTINATION,
            "license_path": "pstack/LICENSE",
            "enabled": True,
            "authority": "P",
            "purpose": "Engineering lifecycle routing; never a correctness authority.",
        },
        {
            "name": "skill-concerns",
            "source": "https://github.com/ed3c/skill-concerns.git",
            "commit": "c91dbd04d1997b2e0f77907c9c2a40f55b787107",
            "subpath": "skills/control-noodle",
            "destination": ".noodle/providers/skill-concerns",
            "license_path": "LICENSE",
            "admission": {
                "path": "admissions/control-noodle.json",
                "sha256": "4e20f09502ba16db920a89b945ebbb9ac206946a7906ceea92090ecb2c93e42d",
                "skill": "control-noodle",
                "skill_tree_sha256": "969111ff62cc68a1df82e036f2fe892e4ab9a850bbf2020f0f4253f6db866581",
                "subject_files": {
                    "skills/control-noodle/SKILL.md": "efa5a1d2e9166af47f9078bdc5924fb6520ae0171a0a068472f7abab02b00a1a"
                },
            },
            "enabled": True,
            "authority": "P",
            "purpose": "Replaceable engineering knowledge; never a correctness authority.",
        },
        {
            "name": "skills-shared-compat",
            "source": "https://github.com/ed3c/skills-shared.git",
            "commit": "52b29b38ded9eaacbf7fb1bfa8ccf69ab37870b9",
            "subpath": ".",
            "destination": ".noodle/providers/skills-shared-compat",
            "license_path": "LICENSE",
            "enabled": False,
            "authority": "P",
            "purpose": "Explicitly disabled compatibility source; not a Golden Path dependency.",
        },
    ]


def current_skill_paths() -> tuple[str, str, str]:
    return (
        runtime_contract.PROJECT_SKILLS_ROOT,
        runtime_contract.CURSOR_PSTACK_NATIVE_ROOT,
        CURRENT_EXTERNAL_SKILL_PATH,
    )


def recovery_skill_paths() -> tuple[str, str, str]:
    return (
        runtime_contract.PROJECT_SKILLS_ROOT,
        runtime_contract.CURSOR_PSTACK_NATIVE_ROOT,
        RECOVERY_EXTERNAL_SKILL_PATH,
    )


def exact_provider_transition_state(root: Path) -> str:
    payload = json.loads((root / "policy/providers.lock.json").read_text(encoding="utf-8"))
    with (root / ".noodle.toml").open("rb") as handle:
        config = tomllib.load(handle)
    providers = payload["providers"]
    skill_paths = tuple(config["skills"]["paths"])
    if providers == current_provider_lock() and skill_paths == current_skill_paths():
        return "current-matt"
    if providers == recovery_provider_lock() and skill_paths == recovery_skill_paths():
        return "replacement-control-noodle"
    raise AssertionError(
        "provider transition oracle accepts only the current Matt state or the exact #49 control-noodle state"
    )


def control_checkout_fixture() -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
    temp = tempfile.TemporaryDirectory(prefix="noodles-control-checkout-test-")
    base = Path(temp.name)
    provider = base / "provider"
    copy_tracked(CANDIDATE_ROOT, provider)
    control = base / "control"
    cmd(["git", "clone", "-q", str(provider), str(control)], base)
    cmd(["git", "config", "user.name", "tests"], control)
    cmd(["git", "config", "user.email", "tests@example.invalid"], control)
    return temp, control, provider


def write_skill_discovery_fixture(
    candidate: Path,
    *,
    compat_skills: tuple[str, ...] = runtime_contract.CURSOR_PSTACK_COMPAT_SKILLS,
    playbooks: tuple[str, ...] = ("investigation.md", "feature.md", "multi-phase-plan.md"),
) -> str:
    transition_state = exact_provider_transition_state(candidate)
    project_root = (candidate / runtime_contract.PROJECT_SKILLS_ROOT).resolve()
    cursor_root = (candidate / runtime_contract.CURSOR_PSTACK_NATIVE_ROOT).resolve()
    compat_source_root = (
        candidate / runtime_contract.CURSOR_PSTACK_DESTINATION / runtime_contract.CURSOR_PSTACK_COMPAT_SOURCE_ROOT
    ).resolve()

    poteto_skill = cursor_root / "poteto-mode"
    poteto_skill.mkdir(parents=True, exist_ok=True)
    (poteto_skill / "SKILL.md").write_text("# Poteto Mode\n")
    playbook_root = poteto_skill / "playbooks"
    playbook_root.mkdir(exist_ok=True)
    for name in playbooks:
        (playbook_root / name).write_text(f"# {name}\n")

    output_lines = []
    for skill in runtime_contract.PROJECT_REQUIRED_SKILLS:
        project_skill = (candidate / runtime_contract.PROJECT_SKILLS_ROOT / skill).resolve()
        output_lines.append(f"{skill}\t{project_root}\ttrue\t{project_skill}")
    for skill in runtime_contract.CURSOR_PSTACK_REQUIRED_NATIVE_SKILLS:
        skill_dir = cursor_root / skill
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            skill_file.write_text(f"# {skill}\n")
        output_lines.append(f"{skill}\t{cursor_root}\ttrue\t{skill_dir}")

    for skill in compat_skills:
        source_dir = compat_source_root / skill
        source_dir.mkdir(parents=True, exist_ok=True)
        (source_dir / "SKILL.md").write_text(f"# {skill}\n")
        mapped_dir = project_root / skill
        mapped_dir.mkdir(exist_ok=True)
        target = source_dir / "SKILL.md"
        os.symlink(os.path.relpath(target, start=mapped_dir), mapped_dir / "SKILL.md")
        output_lines.append(f"{skill}\t{project_root}\ttrue\t{mapped_dir}")

    if transition_state == "current-matt":
        matt_skill = (candidate / CURRENT_EXTERNAL_SKILL_PATH / "ask-matt").resolve()
        matt_skill.mkdir(parents=True, exist_ok=True)
        (matt_skill / "SKILL.md").write_text("# Ask Matt\n")
        output_lines.append(f"ask-matt\t{matt_skill.parent}\ttrue\t{matt_skill}")
    else:
        control_noodle_root = (candidate / RECOVERY_EXTERNAL_SKILL_PATH).resolve()
        control_noodle_root.mkdir(parents=True, exist_ok=True)
        (control_noodle_root / "SKILL.md").write_text("# Control Noodle\n")
        output_lines.append(f"control-noodle\t{control_noodle_root}\ttrue\t{control_noodle_root}")
    return "\n".join(output_lines) + "\n"


def runtime_release_reader(release: str, commit: str, asset_name: str, asset_sha256: str):
    def read(endpoint: str) -> dict:
        if endpoint == f"repos/poteto/noodle/releases/tags/{release}":
            return {
                "tag_name": release,
                "assets": [{"name": asset_name, "digest": f"sha256:{asset_sha256}"}],
            }
        if endpoint == f"repos/poteto/noodle/git/ref/tags/{release}":
            return {"object": {"type": "commit", "sha": commit}}
        raise AssertionError(f"unexpected endpoint {endpoint}")

    return read

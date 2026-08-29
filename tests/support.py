from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import noodles
import runtime_contract

ENGINE_ROOT = Path(noodles.__file__).resolve().parent
CANDIDATE_ROOT = Path(os.getenv("NOODLES_CANDIDATE_ROOT", ENGINE_ROOT)).resolve()


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
        "import pathlib\n"
        "import sys\n"
        "args = sys.argv[1:]\n"
        f"if args == ['--version']:\n    print({version!r})\n"
        "elif len(args) == 9 and args[0] == '--project-dir' and args[2:5] == ['event', 'emit', 'stage_message']:\n"
        "    root = pathlib.Path(args[1])\n"
        "    session = args[6]\n"
        "    payload = json.loads(args[8])\n"
        f"    payload['blocking'] = {blocking!r}\n"
        "    event = {'type': 'stage_message', 'payload': payload, 'timestamp': '2026-08-29T00:00:00Z', 'session_id': session}\n"
        "    target = root / '.noodle' / 'sessions' / session / 'events.ndjson'\n"
        "    with target.open('a', encoding='utf-8') as handle:\n"
        "        handle.write(json.dumps(event) + '\\n')\n"
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
    session_id = "ed3c-noodles-33-0-execute-fixture"
    session = root / ".noodle" / "sessions" / session_id
    session.mkdir(parents=True)
    (session / "spawn.json").write_text(json.dumps({"worktree_path": str(root)}))
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


def write_skill_discovery_fixture(
    candidate: Path,
    *,
    compat_skills: tuple[str, ...] = runtime_contract.CURSOR_PSTACK_COMPAT_SKILLS,
    playbooks: tuple[str, ...] = ("investigation.md", "feature.md", "multi-phase-plan.md"),
) -> str:
    project_root = (candidate / runtime_contract.PROJECT_SKILLS_ROOT).resolve()
    cursor_root = (candidate / runtime_contract.CURSOR_PSTACK_NATIVE_ROOT).resolve()
    compat_source_root = (
        candidate / runtime_contract.CURSOR_PSTACK_DESTINATION / runtime_contract.CURSOR_PSTACK_COMPAT_SOURCE_ROOT
    ).resolve()
    matt_skill = (candidate / ".noodle/providers/matt-engineering/skills/engineering/ask-matt").resolve()

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

    matt_skill.mkdir(parents=True, exist_ok=True)
    (matt_skill / "SKILL.md").write_text("# Ask Matt\n")
    output_lines.append(f"ask-matt\t{matt_skill.parent}\ttrue\t{matt_skill}")
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

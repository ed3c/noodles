from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import feature_contract
import noodles
import runtime_contract

ENGINE_ROOT = Path(noodles.__file__).resolve().parent
CANDIDATE_ROOT = Path(os.getenv("NOODLES_CANDIDATE_ROOT", ENGINE_ROOT)).resolve()
FEATURE = feature_contract.VERIFICATION_SKILL_FEATURE
ISSUE_FEATURE_MARKER = f"<!-- noodles-feature: {FEATURE.feature_id} -->"


def code_surface_digest(root: Path, feature: feature_contract.FeatureContract = FEATURE) -> str:
    return hashlib.sha256((root / feature.code_surface).read_bytes()).hexdigest()


def write_feature_evidence(
    root: Path, head: str, feature: feature_contract.FeatureContract = FEATURE, **overrides: object
) -> Path:
    """Write an evidence packet shaped exactly like the verifier's own output, then apply planted drift."""
    evidence: dict[str, object] = {
        "feature_id": feature.feature_id,
        "head": head,
        "code_surface": feature.code_surface,
        "code_surface_sha256": code_surface_digest(root, feature),
        "operation": list(feature.operation),
        "oracle": feature.oracle,
        "observed": {"returncode": 0, "ok": True, "errors": []},
    }
    evidence.update(overrides)
    for field in [key for key, value in overrides.items() if value is None]:
        evidence.pop(field, None)
    path = root / feature_contract.EVIDENCE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence), encoding="utf-8")
    return path


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


def write_noodle_stub(path: Path, version: str, *, start_delay: float | None = None) -> None:
    start_clause = ""
    if start_delay is not None:
        start_clause = (
            "elif args == ['start']:\n"
            f"    time.sleep({start_delay!r})\n"
        )
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import os\n"
        "import sys\n"
        "import time\n"
        "args = sys.argv[1:]\n"
        f"if args == ['--version']:\n    print({version!r})\n"
        "elif len(args) >= 4 and args[0] == '--project-dir' and args[2:] == ['skills', 'list']:\n"
        "    print(os.environ.get('NOODLES_TEST_SKILLS_OUTPUT', ''), end='')\n"
        f"{start_clause}"
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


def provider_fixture(subpath: str = "skills/control-noodle", license_path: str = "LICENSE") -> tuple[tempfile.TemporaryDirectory[str], Path]:
    temp = tempfile.TemporaryDirectory(prefix="noodles-provider-test-")
    base = Path(temp.name)
    candidate = base / "candidate"
    copy_tracked(CANDIDATE_ROOT, candidate)
    source = base / "source"
    source.mkdir()
    initialize_repo(source)
    (source / "LICENSE").write_text("MIT\n")
    skill_root = source / "skills/control-noodle"
    skill_root.mkdir(parents=True)
    skill_file = skill_root / "SKILL.md"
    skill_file.write_text("# Control Noodle\n")
    skill_tree_sha256 = tree_digest(skill_root)
    admission_path = source / "admissions/control-noodle.json"
    admission_path.parent.mkdir(parents=True, exist_ok=True)
    admission_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "skill": "control-noodle",
                "status": "ADMITTED",
                "subject_files": [
                    {
                        "path": "skills/control-noodle/SKILL.md",
                        "sha256": runtime_contract.sha256_file(skill_file),
                    }
                ],
                "skill_tree_sha256": skill_tree_sha256,
            }
        )
    )
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
            "admission": {
                "path": "admissions/control-noodle.json",
                "sha256": runtime_contract.sha256_file(admission_path),
                "skill": "control-noodle",
                "skill_tree_sha256": skill_tree_sha256,
                "subject_files": {
                    "skills/control-noodle/SKILL.md": runtime_contract.sha256_file(skill_file),
                },
            },
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


def control_checkout_fixture(source: Path = CANDIDATE_ROOT) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
    temp = tempfile.TemporaryDirectory(prefix="noodles-control-checkout-test-")
    base = Path(temp.name)
    provider = base / "provider"
    copy_tracked(source, provider)
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
    project_root = (candidate / runtime_contract.PROJECT_SKILLS_ROOT).resolve()
    cursor_root = (candidate / runtime_contract.CURSOR_PSTACK_NATIVE_ROOT).resolve()
    compat_source_root = (
        candidate / runtime_contract.CURSOR_PSTACK_DESTINATION / runtime_contract.CURSOR_PSTACK_COMPAT_SOURCE_ROOT
    ).resolve()
    control_noodle_source_root = (candidate / runtime_contract.CONTROL_NOODLE_DISCOVERY_ROOT).resolve()

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

    control_noodle_source_root.mkdir(parents=True, exist_ok=True)
    (control_noodle_source_root / "SKILL.md").write_text("# Control Noodle\n")
    control_noodle_root = project_root / runtime_contract.CONTROL_NOODLE_SKILL
    control_noodle_root.mkdir(exist_ok=True)
    os.symlink(os.path.relpath(control_noodle_source_root / "SKILL.md", start=control_noodle_root), control_noodle_root / "SKILL.md")
    output_lines.append(f"{runtime_contract.CONTROL_NOODLE_SKILL}\t{project_root}\ttrue\t{control_noodle_root}")
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


def script_mode_gateerror_identity(root: Path = CANDIDATE_ROOT) -> dict[str, object]:
    script = (
        "import importlib.util, json, sys\n"
        "from pathlib import Path\n"
        "root = Path(sys.argv[1]).resolve()\n"
        "sys.modules.pop('noodles', None)\n"
        "sys.modules.pop('repair_contract', None)\n"
        "spec = importlib.util.spec_from_file_location('__main__', root / 'noodles.py')\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "sys.modules['__main__'] = module\n"
        "sys.argv = ['noodles.py', '--root', str(root), 'verify']\n"
        "try:\n"
        "    spec.loader.exec_module(module)\n"
        "except SystemExit:\n"
        "    pass\n"
        "import repair_contract\n"
        "import noodles\n"
        "engine = repair_contract._engine()\n"
        "print(json.dumps({'main_module': module.__name__, 'engine_module': engine.__name__, 'same_gate_error_identity': module.GateError is engine.GateError, 'split_gate_error_identity': module.GateError is noodles.GateError}))\n"
    )
    result = subprocess.run(
        ["python3", "-c", script, str(root)],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"script mode GateError readback failed: {result.stderr or result.stdout}")
    return json.loads(result.stdout.strip().splitlines()[-1])


def validate_script_mode_gateerror_identity(readback: dict[str, object]) -> list[str]:
    errors: list[str] = []
    if (readback.get("main_module"), readback.get("engine_module")) != ("__main__", "__main__"):
        errors.append(f"repair path resolved wrong module identity: {readback}")
    if readback.get("same_gate_error_identity") is not True:
        errors.append("repair path did not preserve one GateError identity")
    if readback.get("split_gate_error_identity") is not False:
        errors.append("legacy split GateError identity remains observable in script mode")
    return errors


def _write_fake_gh_stub(path: Path, *, release: str, commit: str, asset_name: str, asset_sha256: str) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "args = sys.argv[1:]\n"
        "if not args or args[0] != 'api':\n    raise SystemExit(f'unexpected args: {args}')\n"
        "rest = args[1:]\n"
        "include = False\n"
        "if rest and rest[0] == '--include':\n    include = True\n    rest = rest[1:]\n"
        "if rest[:2] != ['--method', 'GET']:\n    raise SystemExit(f'unexpected args: {args}')\n"
        "endpoint = rest[2]\n"
        f"release = {release!r}\ncommit = {commit!r}\nasset_name = {asset_name!r}\nasset_sha256 = {asset_sha256!r}\n"
        "if endpoint == f'repos/poteto/noodle/releases/tags/{release}':\n"
        "    body = {'tag_name': release, 'assets': [{'name': asset_name, 'digest': f'sha256:{asset_sha256}'}]}\n"
        "elif endpoint == f'repos/poteto/noodle/git/ref/tags/{release}':\n"
        "    body = {'object': {'type': 'commit', 'sha': commit}}\n"
        "elif endpoint == 'repos/ed3c/noodles/branches/main/protection':\n"
        "    body = {'required_status_checks': {'strict': True, 'contexts': ['verify']}, 'enforce_admins': {'enabled': True}, 'required_pull_request_reviews': {'required_approving_review_count': 0}, 'allow_force_pushes': {'enabled': False}, 'allow_deletions': {'enabled': False}}\n"
        "else:\n    raise SystemExit(f'unexpected endpoint: {endpoint}')\n"
        "if include:\n    sys.stdout.write('HTTP/1.1 200 OK\\nETag: test\\nX-GitHub-Request-Id: test\\n\\n')\n"
        "sys.stdout.write(json.dumps(body))\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _lock_start_runtime(root: Path, binary: Path, *, release: str, commit: str, asset_sha256: str) -> None:
    platform_key = runtime_contract.resolve_platform_key(error_cls=AssertionError)
    asset_name = f"noodle_{platform_key}.tar.gz"
    lock_path = root / "policy/runtime.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock["runtime"] = {
        "repository": "poteto/noodle",
        "release": release,
        "commit": commit,
        "command": "noodle",
        "platforms": {
            platform_key: {
                "asset_name": asset_name,
                "asset_sha256": asset_sha256,
                "binary_sha256": runtime_contract.sha256_file(binary),
            }
        },
    }
    lock_path.write_text(json.dumps(lock), encoding="utf-8")


def write_fake_codex_stub(path: Path) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n"
        "cwd = Path.cwd().resolve()\n"
        "home = Path(os.environ.get('HOME', '~')).expanduser().resolve()\n"
        "codex_home = Path(os.environ.get('CODEX_HOME', str(home))).resolve()\n"
        "skill_rows = []\n"
        "roots = []\n"
        "for idx, root in enumerate([codex_home / 'skills', home / '.agents' / 'skills', cwd / '.agents' / 'skills']):\n"
        "    roots.append((f'r{idx}', str(root.resolve())))\n"
        "    if not root.is_dir():\n"
        "        continue\n"
        "    for skill in sorted(root.iterdir()):\n"
        "        if (skill / 'SKILL.md').is_file():\n"
        "            skill_rows.append((skill.name, f'r{idx}/{skill.name}/SKILL.md'))\n"
        "args = sys.argv[1:]\n"
        "if args[:2] == ['debug', 'prompt-input']:\n"
        "    skills_block = '\\n'.join(f'- {name}: planted (file: {raw})' for name, raw in skill_rows)\n"
        "    roots_block = '\\n'.join(f'- `{name}` = `{root}`' for name, root in roots)\n"
        "    text = '### Skill roots\\n' + roots_block + '\\n### Available skills\\n' + skills_block + '\\n</skills_instructions>'\n"
        "    print(json.dumps([{'role': 'developer', 'content': [{'type': 'input_text', 'text': text}]}]))\n"
        "elif args == ['plugin', 'list', '--json']:\n"
        "    print(json.dumps({'installed': [], 'available': []}))\n"
        "else:\n"
        "    raise SystemExit(f'unexpected args: {args}')\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def write_codex_real_bin_probe(path: Path) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n"
        "self_path = Path(__file__).resolve()\n"
        "override = os.environ.get('NOODLES_CODEX_REAL_BIN', '').strip()\n"
        "if override:\n"
        "    print(override)\n"
        "    raise SystemExit(0)\n"
        "for entry in os.environ.get('PATH', '').split(os.pathsep):\n"
        "    candidate = Path(entry or '.') / 'codex'\n"
        "    try:\n"
        "        resolved = candidate.resolve()\n"
        "    except OSError:\n"
        "        continue\n"
        "    if resolved == self_path:\n"
        "        continue\n"
        "    if candidate.is_file() and os.access(candidate, os.X_OK):\n"
        "        print(str(candidate))\n"
        "        raise SystemExit(0)\n"
        "raise SystemExit('NOODLES_CODEX_WRAPPER_FAIL: cannot resolve real codex binary')\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def codex_real_bin_export(base: Path) -> str | None:
    if os.getenv("NOODLES_OFFLINE_TESTS") != "1":
        return None
    fake_codex = base / "codex-real-fixture"
    write_fake_codex_stub(fake_codex)
    return str(fake_codex)


def codex_real_bin_resolution(*, override: Path | None) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="noodles-codex-real-bin-probe-") as temp_name:
        base = Path(temp_name)
        probe = base / "resolve_codex.py"
        write_codex_real_bin_probe(probe)
        env = os.environ.copy()
        env["PATH"] = str(base)
        if override is not None:
            env["NOODLES_CODEX_REAL_BIN"] = str(override)
        else:
            env.pop("NOODLES_CODEX_REAL_BIN", None)
        result = subprocess.run(
            [sys.executable, str(probe)],
            cwd=base,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def _free_tcp_port() -> int:
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def start_entrypoint_with_delayed_listener(
    delay: float = 0.25,
    interval: float = 0.05,
    *,
    start_listener: bool = True,
    runtime_start_delay: float = 0.7,
) -> dict[str, object]:
    temp, candidate = cursor_pstack_fixture()
    with temp:
        base = Path(temp.name)
        release = "v9.9.9"
        commit = "1" * 40
        asset_sha256 = "2" * 64
        bin_dir = base / "bin"
        bin_dir.mkdir()
        runtime = bin_dir / "noodle"
        write_noodle_stub(runtime, release, start_delay=runtime_start_delay)
        _lock_start_runtime(candidate, runtime, release=release, commit=commit, asset_sha256=asset_sha256)
        cmd(["git", "add", "policy/runtime.lock.json"], candidate)
        cmd(["git", "commit", "-q", "-m", "runtime fixture"], candidate)
        temp_control, control, provider = control_checkout_fixture(candidate)
        try:
            fake_gh = bin_dir / "gh"
            platform_key = runtime_contract.resolve_platform_key(error_cls=AssertionError)
            _write_fake_gh_stub(
                fake_gh,
                release=release,
                commit=commit,
                asset_name=f"noodle_{platform_key}.tar.gz",
                asset_sha256=asset_sha256,
            )
            output = write_skill_discovery_fixture(control)
            port = _free_tcp_port()
            control_url = f"http://127.0.0.1:{port}"
            listener_ready = threading.Event()
            listener_served = threading.Event()
            listener_stop = threading.Event()
            listener_state: dict[str, object] = {
                "listener_ready": False,
                "listener_served": False,
                "listener_request_count": 0,
                "listener_thread_alive": False,
                "listener_error": None,
                "listener_bound_port": port,
                "entrypoint_path": str(control / "noodles"),
                "entrypoint_exists": (control / "noodles").exists(),
            }

            def late_listener() -> None:
                from http.server import BaseHTTPRequestHandler, HTTPServer

                if not start_listener:
                    return
                try:
                    time.sleep(delay)

                    class Handler(BaseHTTPRequestHandler):
                        def do_GET(self) -> None:
                            listener_state["listener_request_count"] = int(listener_state["listener_request_count"]) + 1
                            if self.path != "/api/snapshot":
                                self.send_response(404)
                                self.end_headers()
                                return
                            body = json.dumps({"pending_reviews": [], "unclaimed_orders": []}).encode("utf-8")
                            self.send_response(200)
                            self.send_header("Content-Type", "application/json")
                            self.send_header("Content-Length", str(len(body)))
                            self.end_headers()
                            self.wfile.write(body)
                            listener_state["listener_served"] = True
                            listener_served.set()

                        def log_message(self, _format: str, *_args: object) -> None:
                            return

                    with HTTPServer(("127.0.0.1", port), Handler) as server:
                        server.timeout = 0.05
                        listener_state["listener_ready"] = True
                        listener_ready.set()
                        while not listener_stop.is_set():
                            server.handle_request()
                            if listener_served.is_set():
                                break
                except Exception as exc:
                    listener_state["listener_error"] = f"{type(exc).__name__}: {exc}"
                finally:
                    listener_stop.set()

            listener_thread = threading.Thread(target=late_listener, name="start-entrypoint-listener")
            listener_thread.start()
            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
            env["PYTHONPATH"] = str(CANDIDATE_ROOT)
            env["NOODLES_TEST_ALLOW_LOCAL_PROVIDER"] = "1"
            env["NOODLES_TEST_SKILLS_OUTPUT"] = output
            codex_real_bin = codex_real_bin_export(base)
            if codex_real_bin is not None:
                env["NOODLES_CODEX_REAL_BIN"] = codex_real_bin
            result = subprocess.run(
                [str(control / "noodles"), "start", "--control-url", control_url, "--interval", str(interval)],
                cwd=control,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if start_listener:
                listener_ready.wait(timeout=max(1.0, delay + interval))
                listener_served.wait(timeout=max(1.0, runtime_start_delay + interval))
            listener_stop.set()
            listener_thread.join(timeout=2)
            listener_state["listener_thread_alive"] = listener_thread.is_alive()
            listener_state["listener_ready"] = listener_ready.is_set()
            listener_state["listener_served"] = listener_served.is_set()
            return {
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                **listener_state,
            }
        finally:
            temp_control.cleanup()


def validate_start_entrypoint_receipt(receipt: dict[str, object]) -> list[str]:
    errors: list[str] = []
    if receipt.get("returncode") != 0:
        errors.append(f"entrypoint returned {receipt.get('returncode')!r}: {receipt.get('stderr', '')}")
    stderr = str(receipt.get("stderr") or "")
    if "repair: Noodle control request failed" not in stderr:
        errors.append("wrapper never diagnosed startup connection refusal on repair path")
    if "Traceback" in stderr:
        errors.append("wrapper terminated with traceback instead of retrying")
    if receipt.get("entrypoint_exists") is not True:
        errors.append(f"documented entrypoint missing at {receipt.get('entrypoint_path')}")
    if receipt.get("listener_ready") is not True:
        errors.append("listener never became reachable")
    if receipt.get("listener_served") is not True:
        errors.append("listener never served snapshot readback")
    if int(receipt.get("listener_request_count") or 0) < 1:
        errors.append("listener request readback missing")
    if receipt.get("listener_thread_alive") is not False:
        errors.append("listener thread residue remained after subprocess exit")
    if receipt.get("listener_error") is not None:
        errors.append(f"listener lifecycle failed: {receipt.get('listener_error')}")
    return errors


def assert_valid_start_entrypoint_receipt(receipt: dict[str, object]) -> None:
    errors = validate_start_entrypoint_receipt(receipt)
    if errors:
        raise AssertionError("; ".join(errors))

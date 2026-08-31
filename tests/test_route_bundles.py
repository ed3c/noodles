"""Per-route context bundles compiled at provider sync (ed3c/noodles#174).

A bundle is a byte-preserving cache of one immutable execute route traversal: verbatim
concatenation of the exact pinned files in traversal order, each section addressed by its own
sha256 and chained to the provider pin. These controls prove the three laws the atom claims -
byte identity (planted paraphrase/truncation/self-consistent forgery fail closed against the
pinned tree), cache-not-cage (the out-of-bundle pinned catalog stays live-loadable), and
semantic equivalence (the bundle-fed byte stream equals the live-loaded byte stream, and the
existing execute fixture harness still passes).
"""
from __future__ import annotations

import json
import os
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

import noodles
import provider_contract
import runtime_contract
import skill_contract
from tests.support import CANDIDATE_ROOT, cmd, cursor_pstack_fixture

LOCAL_PROVIDER_ENV = {"NOODLES_TEST_ALLOW_LOCAL_PROVIDER": "1"}
EXECUTE_SKILL = CANDIDATE_ROOT / runtime_contract.PROJECT_SKILLS_ROOT / "execute/SKILL.md"


def pinned_root(candidate: Path) -> Path:
    return candidate / runtime_contract.CURSOR_PSTACK_DESTINATION


def bundle_file(candidate: Path, route: str) -> Path:
    return candidate / provider_contract.route_bundle_path(route)


class RouteBundleAssemblyTests(unittest.TestCase):
    def synced_candidate(self) -> Path:
        temp, candidate = cursor_pstack_fixture()
        self.addCleanup(temp.cleanup)
        with mock.patch.dict(os.environ, LOCAL_PROVIDER_ENV, clear=False):
            self.receipts = noodles.provider_sync(candidate)
        return candidate

    def cursor_receipt(self) -> dict[str, object]:
        return next(item for item in self.receipts if item["name"] == runtime_contract.CURSOR_PSTACK_PROVIDER)

    def test_sync_assembles_every_route_bundle_byte_identical_to_the_pinned_tree(self) -> None:
        candidate = self.synced_candidate()
        source_root = pinned_root(candidate)
        commit = cmd(["git", "rev-parse", "HEAD"], source_root)
        receipt = self.cursor_receipt()
        self.assertEqual(receipt["route_bundle_commit"], commit)
        self.assertEqual(sorted(receipt["route_bundles"]), sorted(runtime_contract.EXECUTE_ROUTE_TRAVERSALS))
        for route, paths in runtime_contract.EXECUTE_ROUTE_TRAVERSALS.items():
            with self.subTest(route=route):
                payload = bundle_file(candidate, route).read_bytes()
                result = provider_contract.check_route_bundle(
                    payload,
                    source_root,
                    route=route,
                    provider=runtime_contract.CURSOR_PSTACK_PROVIDER,
                    commit=commit,
                    expected_paths=paths,
                )
                self.assertEqual(result["errors"], [])
                # constraint: semantic equivalence is demonstrated, not claimed - the identical byte
                # constraint: stream reaches the cook whether it is bundle-fed or live-loaded.
                self.assertEqual(result["bundle_fed_sha256"], result["live_loaded_sha256"])
                for relative in paths:
                    self.assertIn((source_root / relative).read_bytes(), payload)

    def test_assembly_is_concatenation_not_condensation(self) -> None:
        candidate = self.synced_candidate()
        source_root = pinned_root(candidate)
        for route, paths in runtime_contract.EXECUTE_ROUTE_TRAVERSALS.items():
            with self.subTest(route=route):
                payload = bundle_file(candidate, route).read_bytes()
                live = b"".join((source_root / relative).read_bytes() for relative in paths)
                bundled = b"".join(
                    body for _path, _digest, body in provider_contract._parse_route_bundle(payload)[1]
                )
                self.assertEqual(bundled, live)

    def test_existing_execute_fixture_harness_still_passes(self) -> None:
        candidate = self.synced_candidate()
        config = tomllib.loads((candidate / ".noodle.toml").read_text(encoding="utf-8"))
        self.assertEqual(skill_contract.validate_execute_task(candidate, config), [])

    def test_unchanged_pin_is_a_no_op_and_a_pin_change_regenerates(self) -> None:
        temp, candidate = cursor_pstack_fixture()
        self.addCleanup(temp.cleanup)
        with mock.patch.dict(os.environ, LOCAL_PROVIDER_ENV, clear=False):
            first = noodles.provider_sync(candidate)
            before = {
                route: (bundle_file(candidate, route).read_bytes(), bundle_file(candidate, route).stat().st_mtime_ns)
                for route in runtime_contract.EXECUTE_ROUTE_TRAVERSALS
            }
            second = noodles.provider_sync(candidate)
        first_receipt = next(item for item in first if item["name"] == runtime_contract.CURSOR_PSTACK_PROVIDER)
        second_receipt = next(item for item in second if item["name"] == runtime_contract.CURSOR_PSTACK_PROVIDER)
        self.assertEqual(first_receipt["route_bundle_commit"], second_receipt["route_bundle_commit"])
        routes = sorted(runtime_contract.EXECUTE_ROUTE_TRAVERSALS)
        self.assertEqual(first_receipt["route_bundle_status"], dict.fromkeys(routes, "written"))
        self.assertEqual(second_receipt["route_bundle_status"], dict.fromkeys(routes, "unchanged"))
        for route, (payload, mtime_ns) in before.items():
            with self.subTest(route=route):
                target = bundle_file(candidate, route)
                self.assertEqual(target.read_bytes(), payload)
                self.assertEqual(target.stat().st_mtime_ns, mtime_ns)

        lock_path = candidate / "policy/providers.lock.json"
        lock = json.loads(lock_path.read_text())
        source = Path(lock["providers"][0]["source"])
        (source / "pstack/skills/poteto-mode/SKILL.md").write_text("# poteto-mode\n\nrepinned\n")
        cmd(["git", "add", "-A"], source)
        cmd(["git", "commit", "-q", "-m", "repin"], source)
        repinned = cmd(["git", "rev-parse", "HEAD"], source)
        lock["providers"][0]["commit"] = repinned
        lock_path.write_text(json.dumps(lock))
        cmd(["git", "add", "-A"], candidate)
        cmd(["git", "commit", "-q", "-m", "repin lock"], candidate)
        with mock.patch.dict(os.environ, LOCAL_PROVIDER_ENV, clear=False):
            third = noodles.provider_sync(candidate)
        third_receipt = next(item for item in third if item["name"] == runtime_contract.CURSOR_PSTACK_PROVIDER)
        self.assertEqual(third_receipt["route_bundle_commit"], repinned)
        self.assertEqual(third_receipt["route_bundle_status"], dict.fromkeys(routes, "written"))
        for route in runtime_contract.EXECUTE_ROUTE_TRAVERSALS:
            with self.subTest(route=route):
                self.assertNotEqual(bundle_file(candidate, route).read_bytes(), before[route][0])
        self.assertIn(b"repinned\n", bundle_file(candidate, "investigation").read_bytes())

    def test_out_of_bundle_pinned_skills_stay_live_loadable(self) -> None:
        candidate = self.synced_candidate()
        source_root = pinned_root(candidate)
        live_only = runtime_contract.live_only_native_skills()
        self.assertIn("arena", live_only)
        bundled = b"".join(
            bundle_file(candidate, route).read_bytes() for route in runtime_contract.EXECUTE_ROUTE_TRAVERSALS
        )
        for skill in live_only:
            with self.subTest(skill=skill):
                # constraint: monitor finding 5 - this is not a simulated route request (no routing
                # constraint: decision is made or replayed here); it proves the weaker, sufficient fact
                # constraint: that no bundle contains this out-of-bundle skill's bytes, so the only path
                # constraint: to it is the untouched live read against the pinned checkout.
                self.assertNotIn(f"/{skill}/SKILL.md".encode(), bundled)
                pinned = source_root / runtime_contract.CURSOR_PSTACK_NATIVE_SUBPATH / skill / "SKILL.md"
                self.assertTrue(pinned.is_file())
                self.assertEqual(pinned.read_bytes(), f"# {skill}\n".encode())
        self.assertEqual(self.cursor_receipt()["live_only_skills"], list(live_only))


class RouteBundlePlantedNegativeTests(unittest.TestCase):
    def test_planted_bundle_defects_fail_closed_against_the_pinned_tree(self) -> None:
        temp, candidate = cursor_pstack_fixture()
        self.addCleanup(temp.cleanup)
        with mock.patch.dict(os.environ, LOCAL_PROVIDER_ENV, clear=False):
            noodles.provider_sync(candidate)
            target = bundle_file(candidate, "investigation")
            pristine = target.read_bytes()
            pinned = pinned_root(candidate) / runtime_contract.EXECUTE_ROUTE_TRAVERSALS["investigation"][0]
            original = pinned.read_bytes()
            paraphrase = b"# poteto_mode\n"
            self.assertEqual(len(paraphrase), len(original))
            forged_body = b"# poteto-mode (condensed)\n"
            entrypoint = runtime_contract.EXECUTE_ROUTE_TRAVERSALS["investigation"][0]
            forged = pristine.replace(
                provider_contract._section_header(0, entrypoint, original) + original,
                provider_contract._section_header(0, entrypoint, forged_body) + forged_body,
            )
            plantings = {
                "paraphrased section": (pristine.replace(original, paraphrase), "bytes differ from the pinned file"),
                "truncated section": (pristine.replace(original, original[:-1]), "body is not .* framed bytes"),
                "self-consistent forgery": (forged, r"digest [0-9a-f]{64} != pinned [0-9a-f]{64}"),
                "rewritten pin header": (
                    pristine.replace(b"\ncommit: ", b"\ncommit: 0", 1),
                    "header commit is",
                ),
                "dropped bundle": (None, "route bundle missing: .noodle/bundles/investigation.md"),
            }
            for label, (payload, pattern) in plantings.items():
                with self.subTest(planting=label):
                    self.assertNotEqual(payload, pristine)
                    if payload is None:
                        target.unlink()
                    else:
                        target.write_bytes(payload)
                    with self.assertRaisesRegex(noodles.GateError, pattern):
                        noodles.provider_check(candidate)
                    target.write_bytes(pristine)
            self.assertEqual(
                noodles.provider_check(candidate)[0]["route_bundles"]["investigation"]["path"],
                ".noodle/bundles/investigation.md",
            )


class ExecuteRoutingPointerTests(unittest.TestCase):
    def route_files(self, routing: str) -> None:
        with tempfile.TemporaryDirectory(prefix="noodles-route-pointer-") as name:
            root = Path(name)
            playbooks = root / "poteto-mode/playbooks"
            playbooks.mkdir(parents=True)
            (root / "poteto-mode/SKILL.md").write_text("# poteto-mode\n")
            for playbook in ("investigation.md", "feature.md", "multi-phase-plan.md"):
                (playbooks / playbook).write_text(f"# {playbook}\n")
            execute = root / "execute"
            execute.mkdir()
            (execute / "SKILL.md").write_text(routing)
            runtime_contract._validate_execute_route_files(
                root,
                {
                    "poteto-mode": {"resolved_path": str(root / "poteto-mode/SKILL.md")},
                    "execute": {"resolved_path": str(execute / "SKILL.md")},
                },
                error_cls=noodles.GateError,
            )

    def test_committed_execute_skill_names_every_bundle(self) -> None:
        self.route_files(EXECUTE_SKILL.read_text(encoding="utf-8"))

    def test_routing_contract_without_the_bundle_pointer_fails_closed(self) -> None:
        routing = EXECUTE_SKILL.read_text(encoding="utf-8")
        stripped = routing.replace(runtime_contract.EXECUTE_ROUTE_BUNDLE_PHRASE, "Load whatever seems relevant.")
        self.assertNotEqual(stripped, routing)
        with self.assertRaisesRegex(noodles.GateError, "does not point cooks at the pinned route bundles"):
            self.route_files(stripped)

    def test_routing_contract_missing_one_bundle_path_fails_closed(self) -> None:
        routing = EXECUTE_SKILL.read_text(encoding="utf-8")
        dropped = provider_contract.route_bundle_path("cli-control")
        stripped = routing.replace(f"`{dropped}`", "`(unlisted)`")
        self.assertNotEqual(stripped, routing)
        with self.assertRaisesRegex(noodles.GateError, f"does not name route bundle {dropped}"):
            self.route_files(stripped)


class VerifyGateBundleBindingTests(unittest.TestCase):
    """monitor findings 7 and 8: _validate_execute_route_files above runs only through
    skill_discovery_check, which needs a live noodle binary and is not reachable from
    `./noodles verify` - the gate that actually runs on every PR head. These exercise the same two
    failure modes through runtime_contract.validate_execute_route_bundle_contract, the static,
    provider-checkout-free check verify_repository calls directly (both carrier-owned surfaces)."""

    def skill_root(self, root: Path, content: str) -> None:
        skill_dir = root / runtime_contract.PROJECT_SKILLS_ROOT / "execute"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

    def test_verify_gate_passes_on_the_committed_skill(self) -> None:
        with tempfile.TemporaryDirectory(prefix="noodles-verify-gate-") as name:
            root = Path(name)
            self.skill_root(root, EXECUTE_SKILL.read_text(encoding="utf-8"))
            self.assertEqual(runtime_contract.validate_execute_route_bundle_contract(root), [])

    def test_verify_gate_catches_a_deleted_bundle_pointer(self) -> None:
        content = EXECUTE_SKILL.read_text(encoding="utf-8")
        stripped = content.replace(runtime_contract.EXECUTE_ROUTE_BUNDLE_PHRASE, "Load whatever seems relevant.")
        self.assertNotEqual(stripped, content)
        with tempfile.TemporaryDirectory(prefix="noodles-verify-gate-") as name:
            root = Path(name)
            self.skill_root(root, stripped)
            errors = runtime_contract.validate_execute_route_bundle_contract(root)
        self.assertIn("does not point cooks at the pinned route bundles", "; ".join(errors))

    def test_verify_gate_catches_a_route_bundle_mislabeled_to_the_wrong_skill(self) -> None:
        # constraint: monitor finding 7 - if cli-control's traversal were edited to point at deslop
        # constraint: (pre-commit-cleanup's skill) instead of control-cli, the bundle would still byte-
        # constraint: match its own pinned target and the bundle-path string would still appear in the
        # constraint: doc; only a leaf-identity-vs-bullet cross-check catches the mislabeling.
        swapped = dict(runtime_contract.EXECUTE_ROUTE_TRAVERSALS)
        swapped["cli-control"] = (
            runtime_contract.EXECUTE_ROUTE_TRAVERSALS["cli-control"][0],
            runtime_contract.EXECUTE_ROUTE_TRAVERSALS["pre-commit-cleanup"][1],
        )
        with tempfile.TemporaryDirectory(prefix="noodles-verify-gate-") as name:
            root = Path(name)
            self.skill_root(root, EXECUTE_SKILL.read_text(encoding="utf-8"))
            with mock.patch.dict(runtime_contract.EXECUTE_ROUTE_TRAVERSALS, swapped):
                errors = runtime_contract.validate_execute_route_bundle_contract(root)
        self.assertTrue(any("does not name 'deslop'" in error for error in errors), errors)


class NativeCompatNamespaceTests(unittest.TestCase):
    def test_a_compat_skill_sharing_a_native_basename_does_not_shrink_the_live_only_complement(self) -> None:
        # constraint: monitor finding 11 - _route_bundle_skills() must key off the native-rooted prefix,
        # constraint: not the bare leaf directory name, or a same-named compat skill would silently
        # constraint: remove a required native skill from the live-only complement it never actually bundles.
        colliding = dict(runtime_contract.EXECUTE_ROUTE_TRAVERSALS)
        colliding["pre-commit-cleanup"] = (
            runtime_contract.EXECUTE_ROUTE_TRAVERSALS["pre-commit-cleanup"][0],
            f"{runtime_contract.CURSOR_PSTACK_COMPAT_SOURCE_ROOT}/arena/SKILL.md",
        )
        with mock.patch.dict(runtime_contract.EXECUTE_ROUTE_TRAVERSALS, colliding):
            self.assertIn("arena", runtime_contract.live_only_native_skills())


if __name__ == "__main__":
    unittest.main()

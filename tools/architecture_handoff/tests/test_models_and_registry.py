import json
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.architecture_handoff.models import (  # noqa: E402
    ResultCompleteness,
    WorkItemSummary,
    WorkRoute,
)
from tools.architecture_handoff.registry import (  # noqa: E402
    RegistryConfig,
    RepositoryTopology,
    RegistryError,
    StoreConfig,
    StoreRole,
    TargetConfig,
    load_registry,
    load_registry_config,
    resolve_active_store,
    resolve_active_target,
)

FIXTURES = Path(__file__).parent / "fixtures"


class ModelsAndRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.registry_path = Path(self.temp_dir.name) / "targets.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_registry(self, targets, stores=None):
        payload = {"targets": targets}
        if stores is not None:
            payload["stores"] = stores
        self.registry_path.write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

    def _target(self, **overrides):
        target = {
            "key": "pilot-backend",
            "provider": "github",
            "repository": "owner/repository",
            "routing_status": "active",
            "owns": ["backend"],
            "excludes": ["frontend"],
        }
        target.update(overrides)
        return target

    def _store(self, **overrides):
        store = {
            "key": "example-documentation-intake",
            "role": "documentation-intake",
            "provider": "github",
            "repository": "owner/docs",
            "tracker_reference": "github:owner/docs",
            "routing_status": "active",
        }
        store.update(overrides)
        return store

    def test_defines_canonical_work_routes(self):
        self.assertEqual(
            [route.value for route in WorkRoute],
            [
                "architecture-slice-handoff",
                "implementation-conformance-referral",
                "spike-evidence",
                "target-native-internal",
            ],
        )

    def test_compact_work_item_is_immutable_and_has_no_body(self):
        item = WorkItemSummary(
            provider_id="12",
            provider_qualified_id="github:owner/repository#12",
            title="Inspect available work",
            status="ready",
            work_route=WorkRoute.ARCHITECTURE_SLICE_HANDOFF,
            updated="2026-07-30T10:00:00Z",
            url="https://github.com/owner/repository/issues/12",
            labels=("status:ready",),
        )

        self.assertFalse(hasattr(item, "body"))
        with self.assertRaises(FrozenInstanceError):
            item.title = "Changed"
        self.assertEqual(ResultCompleteness.COMPLETE.value, "complete")

    def test_loads_and_resolves_one_active_target(self):
        self._write_registry([self._target()])

        targets = load_registry(self.registry_path)
        target = resolve_active_target(targets, "pilot-backend")

        self.assertEqual(target.provider, "github")
        self.assertEqual(target.repository, "owner/repository")
        self.assertEqual(target.owns, ("backend",))
        self.assertEqual(target.excludes, ("frontend",))

    def test_loads_and_resolves_documentation_intake_store(self):
        self._write_registry(
            [self._target()],
            [self._store()],
        )

        registry = load_registry_config(self.registry_path)
        store = resolve_active_store(
            registry.stores,
            "example-documentation-intake",
            StoreRole.DOCUMENTATION_INTAKE,
        )

        self.assertIsInstance(registry, RegistryConfig)
        self.assertIsInstance(store, StoreConfig)
        self.assertEqual(store.repository, "owner/docs")
        self.assertEqual(store.tracker_reference, "github:owner/docs")
        self.assertEqual(len(load_registry(self.registry_path)), 1)

    def test_target_only_registry_loads_with_no_stores(self):
        self._write_registry([self._target()])

        registry = load_registry_config(self.registry_path)

        self.assertEqual(registry.stores, ())
        self.assertEqual(registry.targets, load_registry(self.registry_path))

    def test_rejects_duplicate_store_keys_and_target_store_collision(self):
        cases = (
            (
                [self._store(), self._store()],
                "duplicate store key: example-documentation-intake",
            ),
            (
                [self._store(key="pilot-backend")],
                "registry key is used by target and store: pilot-backend",
            ),
        )
        for stores, message in cases:
            with self.subTest(message=message):
                self._write_registry([self._target()], stores)
                with self.assertRaisesRegex(RegistryError, message):
                    load_registry_config(self.registry_path)

    def test_rejects_unknown_store_role_and_blank_repository(self):
        cases = (
            (
                self._store(role="delivery"),
                "store role must be one of",
            ),
            (
                self._store(repository=" "),
                "repository must be a non-empty string",
            ),
        )
        for store, message in cases:
            with self.subTest(message=message):
                self._write_registry([self._target()], [store])
                with self.assertRaisesRegex(RegistryError, message):
                    load_registry_config(self.registry_path)

    def test_rejects_missing_or_inactive_documentation_intake_store(self):
        self._write_registry(
            [self._target()],
            [self._store(routing_status="suspended")],
        )
        stores = load_registry_config(self.registry_path).stores

        with self.assertRaisesRegex(
            RegistryError,
            "store example-documentation-intake is not active: suspended",
        ):
            resolve_active_store(
                stores,
                "example-documentation-intake",
                StoreRole.DOCUMENTATION_INTAKE,
            )
        with self.assertRaisesRegex(
            RegistryError,
            "store not found: unknown",
        ):
            resolve_active_store(
                stores,
                "unknown",
                StoreRole.DOCUMENTATION_INTAKE,
            )

    def test_loads_legacy_registry_with_backward_compatible_defaults(self):
        target = load_registry(FIXTURES / "registry-legacy.json")[0]

        self.assertEqual(target.key, "example-implementation")
        self.assertEqual(target.topology, RepositoryTopology.REPOSITORY)
        self.assertIsNone(target.repository_url)
        self.assertIsNone(target.scoped_path)
        self.assertIsNone(target.tracker_reference)
        self.assertEqual(target.source_references, ())
        self.assertIsNone(target.adoption_reference)
        self.assertIsNone(target.adoption_state)

    def test_existing_direct_target_config_constructor_remains_valid(self):
        target = TargetConfig(
            key="example-implementation",
            provider="github",
            repository="owner/repository",
            routing_status="active",
            owns=("pilot implementation",),
            excludes=(),
        )

        self.assertEqual(target.topology, RepositoryTopology.REPOSITORY)
        self.assertEqual(target.source_references, ())

    def test_loads_extended_registry_fields_and_relationships(self):
        targets = load_registry(FIXTURES / "registry-extended.json")
        by_key = {target.key: target for target in targets}

        api = by_key["platform-api"]
        self.assertEqual(api.repository_url, "https://git.example/platform.git")
        self.assertEqual(api.scoped_path, "services/api")
        self.assertEqual(api.tracker_reference, "jira:EXAMPLE")
        self.assertEqual(
            api.source_references,
            (
                "git:docs@example-revision:architecture/05-building-block-view.md",
            ),
        )
        self.assertEqual(api.topology, RepositoryTopology.MONOREPO)
        self.assertEqual(api.adoption_reference, "jira:EXAMPLE-41")
        self.assertEqual(api.adoption_state, "done")

        contracts = by_key["platform-contracts"]
        self.assertEqual(contracts.topology, RepositoryTopology.SUBMODULE)
        self.assertEqual(contracts.superproject_target, "platform-root")
        self.assertEqual(contracts.submodule_path, "packages/contracts")

    def test_tracked_canonical_registry_uses_extended_contract(self):
        registry = REPOSITORY_ROOT / "architecture-handoff.registry.json"

        config = load_registry_config(registry)
        target = config.targets[0]
        store = config.stores[0]

        self.assertEqual(target.key, "example-implementation")
        self.assertEqual(target.provider, "github")
        self.assertEqual(target.routing_status, "suspended")
        self.assertTrue(target.repository_url.startswith("https://example.com/"))
        self.assertEqual(
            target.tracker_reference,
            f"github:{target.repository}",
        )
        self.assertEqual(len(target.source_references), 1)
        self.assertTrue(
            target.source_references[0].endswith(
                ":docs/architecture-handoff.md"
            )
        )
        self.assertEqual(
            target.adoption_reference,
            f"github:{target.repository}#EXAMPLE",
        )
        self.assertEqual(target.adoption_state, "draft")
        self.assertEqual(store.provider, "github")
        self.assertEqual(store.role, StoreRole.DOCUMENTATION_INTAKE)
        self.assertEqual(store.routing_status, "suspended")
        self.assertEqual(store.repository, "example-org/example-documentation")
        self.assertEqual(
            store.tracker_reference,
            "github:example-org/example-documentation",
        )
        self.assertFalse(
            (
                REPOSITORY_ROOT
                / "tools"
                / "architecture_handoff"
                / "example-registry.json"
            ).exists()
        )

    def test_rejects_duplicate_target_keys(self):
        self._write_registry([self._target(), self._target()])

        with self.assertRaisesRegex(
            RegistryError, "duplicate target key: pilot-backend"
        ):
            load_registry(self.registry_path)

    def test_rejects_missing_target(self):
        self._write_registry([self._target()])
        targets = load_registry(self.registry_path)

        with self.assertRaisesRegex(RegistryError, "target not found: unknown"):
            resolve_active_target(targets, "unknown")

    def test_rejects_non_active_target(self):
        self._write_registry([self._target(routing_status="suspended")])
        targets = load_registry(self.registry_path)

        with self.assertRaisesRegex(
            RegistryError,
            "target pilot-backend is not active: suspended",
        ):
            resolve_active_target(targets, "pilot-backend")

    def test_rejects_unknown_routing_status(self):
        self._write_registry([self._target(routing_status="unknown")])

        with self.assertRaisesRegex(
            RegistryError,
            "routing_status must be one of",
        ):
            load_registry(self.registry_path)

    def test_rejects_absolute_or_parent_traversing_scoped_paths(self):
        for scoped_path in ("/services/api", "../services/api", "services/../api"):
            with self.subTest(scoped_path=scoped_path):
                self._write_registry(
                    [
                        self._target(
                            topology="monorepo",
                            scoped_path=scoped_path,
                        )
                    ]
                )

                with self.assertRaisesRegex(
                    RegistryError,
                    "scoped_path must be a relative POSIX path",
                ):
                    load_registry(self.registry_path)

    def test_rejects_monorepo_target_without_scoped_path(self):
        self._write_registry([self._target(topology="monorepo")])

        with self.assertRaisesRegex(
            RegistryError,
            "monorepo target pilot-backend requires scoped_path",
        ):
            load_registry(self.registry_path)

    def test_rejects_submodule_without_superproject_or_path(self):
        for fields, expected in (
            (
                {"topology": "submodule", "submodule_path": "packages/api"},
                "requires superproject_target",
            ),
            (
                {
                    "topology": "submodule",
                    "superproject_target": "platform-root",
                },
                "requires submodule_path",
            ),
        ):
            with self.subTest(fields=fields):
                targets = [self._target(**fields)]
                if "superproject_target" in fields:
                    targets.insert(
                        0,
                        self._target(
                            key="platform-root",
                            owns=["platform"],
                            excludes=[],
                        ),
                    )
                self._write_registry(targets)

                with self.assertRaisesRegex(RegistryError, expected):
                    load_registry(self.registry_path)

    def test_rejects_unknown_or_self_superproject(self):
        for superproject, expected in (
            ("unknown", "unknown superproject target"),
            ("pilot-backend", "cannot be its own superproject"),
        ):
            with self.subTest(superproject=superproject):
                self._write_registry(
                    [
                        self._target(
                            topology="submodule",
                            superproject_target=superproject,
                            submodule_path="packages/api",
                        )
                    ]
                )

                with self.assertRaisesRegex(RegistryError, expected):
                    load_registry(self.registry_path)

    def test_rejects_superproject_cycles(self):
        self._write_registry(
            [
                self._target(
                    key="platform-a",
                    topology="submodule",
                    superproject_target="platform-b",
                    submodule_path="packages/a",
                ),
                self._target(
                    key="platform-b",
                    topology="submodule",
                    superproject_target="platform-a",
                    submodule_path="packages/b",
                ),
            ]
        )

        with self.assertRaisesRegex(
            RegistryError,
            "superproject relationship cycle",
        ):
            load_registry(self.registry_path)

    def test_rejects_duplicate_monorepo_physical_scopes(self):
        self._write_registry(
            [
                self._target(
                    key="api-a",
                    repository_url="https://git.example/platform.git",
                    topology="monorepo",
                    scoped_path="services/api",
                    owns=["backend-a"],
                    excludes=[],
                ),
                self._target(
                    key="api-b",
                    repository_url="https://git.example/platform.git",
                    topology="monorepo",
                    scoped_path="services/api",
                    owns=["backend-b"],
                    excludes=[],
                ),
            ]
        )

        with self.assertRaisesRegex(
            RegistryError,
            "duplicate physical target scope: api-a, api-b",
        ):
            load_registry(self.registry_path)

    def test_rejects_duplicate_whole_repository_scopes(self):
        self._write_registry(
            [
                self._target(
                    key="platform-a",
                    repository_url="https://git.example/platform.git",
                    owns=["platform-a"],
                    excludes=[],
                ),
                self._target(
                    key="platform-b",
                    repository_url="https://git.example/platform.git",
                    owns=["platform-b"],
                    excludes=[],
                ),
            ]
        )

        with self.assertRaisesRegex(
            RegistryError,
            "duplicate physical target scope: platform-a, platform-b",
        ):
            load_registry(self.registry_path)

    def test_rejects_duplicate_submodule_effective_scopes(self):
        self._write_registry(
            [
                self._target(
                    key="platform-root",
                    owns=["platform"],
                    excludes=[],
                ),
                self._target(
                    key="contracts-a",
                    repository="owner/contracts",
                    topology="submodule",
                    superproject_target="platform-root",
                    submodule_path="packages/contracts",
                    owns=["contracts-a"],
                    excludes=[],
                ),
                self._target(
                    key="contracts-b",
                    repository="owner/contracts",
                    topology="submodule",
                    superproject_target="platform-root",
                    submodule_path="packages/contracts",
                    owns=["contracts-b"],
                    excludes=[],
                ),
            ]
        )

        with self.assertRaisesRegex(
            RegistryError,
            "duplicate physical target scope: contracts-a, contracts-b",
        ):
            load_registry(self.registry_path)

    def test_rejects_overlapping_ownership_and_exclusions(self):
        self._write_registry(
            [
                self._target(
                    owns=["backend", "shared"],
                    excludes=["frontend", "shared"],
                )
            ]
        )

        with self.assertRaisesRegex(
            RegistryError,
            "owns and excludes overlap for pilot-backend: shared",
        ):
            load_registry(self.registry_path)

    def test_rejects_unknown_adoption_state(self):
        self._write_registry(
            [
                self._target(
                    adoption_reference="github:owner/repository#1",
                    adoption_state="configured",
                )
            ]
        )

        with self.assertRaisesRegex(
            RegistryError,
            "adoption_state must be a canonical lifecycle value",
        ):
            load_registry(self.registry_path)

    def test_rejects_unpaired_adoption_reference_and_state(self):
        for fields in (
            {"adoption_reference": "github:owner/repository#1"},
            {"adoption_state": "done"},
        ):
            with self.subTest(fields=fields):
                self._write_registry([self._target(**fields)])

                with self.assertRaisesRegex(
                    RegistryError,
                    "adoption_reference and adoption_state must appear together",
                ):
                    load_registry(self.registry_path)


if __name__ == "__main__":
    unittest.main()

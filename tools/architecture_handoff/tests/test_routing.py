import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.architecture_handoff.registry import (  # noqa: E402
    RegistryError,
    TargetConfig,
    load_registry,
)
from tools.architecture_handoff.routing import (  # noqa: E402
    resolve_routed_target,
)


FIXTURES = Path(__file__).parent / "fixtures"


def target(key, **overrides):
    values = {
        "key": key,
        "provider": "github",
        "repository": f"owner/{key}",
        "routing_status": "active",
        "owns": (key,),
        "excludes": (),
    }
    values.update(overrides)
    return TargetConfig(**values)


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.extended_targets = load_registry(
            FIXTURES / "registry-extended.json"
        )

    def test_resolves_exact_ownership(self):
        resolved = resolve_routed_target(
            self.extended_targets,
            ownership=("backend",),
        )

        self.assertEqual(resolved.key, "platform-api")

    def test_resolves_exact_source_reference(self):
        resolved = resolve_routed_target(
            self.extended_targets,
            source_references=(
                "git:docs@example-revision:"
                "architecture/08-crosscutting-concepts.md",
            ),
        )

        self.assertEqual(resolved.key, "platform-contracts")

    def test_resolves_most_specific_monorepo_scope(self):
        resolved = resolve_routed_target(
            self.extended_targets,
            repository="https://git.example/platform.git",
            path="services/api/src/server.py",
        )

        self.assertEqual(resolved.key, "platform-api")

    def test_resolves_submodule_path_through_superproject(self):
        resolved = resolve_routed_target(
            self.extended_targets,
            repository="https://git.example/platform.git",
            path="packages/contracts/src/Types.sol",
        )

        self.assertEqual(resolved.key, "platform-contracts")

    def test_combines_repository_scope_ownership_and_source_reference(self):
        resolved = resolve_routed_target(
            self.extended_targets,
            ownership=("backend",),
            source_references=(
                "git:docs@example-revision:"
                "architecture/05-building-block-view.md",
            ),
            repository="platform",
            path="services/api/src/server.py",
        )

        self.assertEqual(resolved.key, "platform-api")

    def test_does_not_route_to_inactive_target(self):
        targets = (
            target(
                "backend",
                routing_status="suspended",
                owns=("backend",),
            ),
        )

        with self.assertRaisesRegex(
            RegistryError,
            "no active target matches routing criteria",
        ):
            resolve_routed_target(targets, ownership=("backend",))

    def test_rejects_empty_criteria_even_with_one_active_target(self):
        with self.assertRaisesRegex(
            RegistryError,
            "routing criteria are required",
        ):
            resolve_routed_target((target("backend"),))

    def test_rejects_zero_matches(self):
        with self.assertRaisesRegex(
            RegistryError,
            "no active target matches routing criteria",
        ):
            resolve_routed_target(
                self.extended_targets,
                ownership=("mobile",),
            )

    def test_rejects_ambiguous_matches(self):
        targets = (
            target("backend-a", owns=("backend",)),
            target("backend-b", owns=("backend",)),
        )

        with self.assertRaisesRegex(
            RegistryError,
            "ambiguous target match: backend-a, backend-b",
        ):
            resolve_routed_target(targets, ownership=("backend",))

    def test_rejects_path_without_repository(self):
        with self.assertRaisesRegex(
            RegistryError,
            "path requires repository routing criteria",
        ):
            resolve_routed_target(
                self.extended_targets,
                path="services/api/src/server.py",
            )

    def test_rejects_owned_and_excluded_work(self):
        targets = (
            target(
                "backend",
                owns=("backend",),
                excludes=("frontend",),
            ),
        )

        with self.assertRaisesRegex(
            RegistryError,
            "target backend both owns and excludes requested work: frontend",
        ):
            resolve_routed_target(
                targets,
                ownership=("backend", "frontend"),
            )

    def test_rejects_partially_owned_multi_selector_work(self):
        targets = (
            target(
                "backend",
                owns=("backend",),
            ),
        )

        with self.assertRaisesRegex(
            RegistryError,
            "no active target matches routing criteria",
        ):
            resolve_routed_target(
                targets,
                ownership=("backend", "mobile"),
            )

    def test_does_not_use_fuzzy_or_case_insensitive_matching(self):
        with self.assertRaisesRegex(
            RegistryError,
            "no active target matches routing criteria",
        ):
            resolve_routed_target(
                self.extended_targets,
                ownership=("Backend",),
            )


if __name__ == "__main__":
    unittest.main()

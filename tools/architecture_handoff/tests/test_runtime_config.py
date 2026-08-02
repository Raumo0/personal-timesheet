import sys
import json
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.architecture_handoff.runtime_config import (  # noqa: E402
    QueryBudget,
    RuntimeConfigError,
    load_runtime_config,
    resolve_query_budget,
)


class RuntimeConfigTests(unittest.TestCase):
    def test_loads_tracked_defaults_and_ceiling(self):
        config = load_runtime_config(
            REPOSITORY_ROOT / "architecture-handoff.runtime.json"
        )

        self.assertEqual(
            config.return_correlation_fallback_budget,
            QueryBudget(page_size=100, max_pages=1, max_items=100),
        )
        self.assertEqual(config.ceiling.max_pages, 20)
        self.assertEqual(config.ceiling.max_items, 2000)
        self.assertEqual(config.github.request_timeout_seconds, 15)

    def test_operation_override_must_stay_within_ceiling(self):
        config = load_runtime_config(
            REPOSITORY_ROOT / "architecture-handoff.runtime.json"
        )

        self.assertEqual(
            resolve_query_budget(
                config,
                "return_correlation_fallback",
                max_pages=5,
                max_items=500,
            ),
            QueryBudget(page_size=100, max_pages=5, max_items=500),
        )
        with self.assertRaisesRegex(
            RuntimeConfigError,
            "max_items exceeds configured ceiling",
        ):
            resolve_query_budget(
                config,
                "return_correlation_fallback",
                max_items=2001,
            )

    def test_rejects_unknown_keys_and_boolean_integers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = json.loads(
                (
                    REPOSITORY_ROOT
                    / "architecture-handoff.runtime.json"
                ).read_text(encoding="utf-8")
            )
            source["unexpected"] = {}
            path = Path(temp_dir) / "unknown.json"
            path.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaisesRegex(
                RuntimeConfigError,
                "unknown: unexpected",
            ):
                load_runtime_config(path)

            source.pop("unexpected")
            source["query_budgets"]["default"]["max_pages"] = True
            path.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaisesRegex(
                RuntimeConfigError,
                "max_pages must be a positive integer",
            ):
                load_runtime_config(path)


if __name__ == "__main__":
    unittest.main()

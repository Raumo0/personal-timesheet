import unittest

from tools.agentic_workflow.validate_catalog_lifecycle_sqlite import (
    EXPECTED_IMPORT,
    TEST_PATH,
    allows_recovery_coverage,
    expects_red,
    validate_result,
)


class CatalogLifecycleSqliteGateTests(unittest.TestCase):
    def test_detects_the_red_phase_from_task_4_1(self):
        self.assertTrue(expects_red("- [ ] 4.1 RED: SQLite tests\n"))
        self.assertFalse(expects_red("- [x] 4.1 RED: SQLite tests\n"))

    def test_allows_recovery_coverage_until_task_10_1_is_checked(self):
        self.assertTrue(allows_recovery_coverage("- [ ] 10.1 COVERAGE: recovery\n"))
        self.assertFalse(allows_recovery_coverage("- [x] 10.1 COVERAGE: recovery\n"))

    def test_accepts_only_the_expected_missing_adapter_suite(self):
        output = (
            f" FAIL  {TEST_PATH} [ {TEST_PATH} ]\n"
            f"Error: {EXPECTED_IMPORT} from test\n"
            " Test Files  1 failed | 22 passed (23)\n"
            "      Tests  218 passed (218)\n"
        )
        self.assertIsNone(validate_result(1, output, red=True))

    def test_rejects_an_additional_failed_suite_or_test(self):
        output = (
            f" FAIL  {TEST_PATH} [ {TEST_PATH} ]\n"
            " FAIL  src/other.test.ts [ src/other.test.ts ]\n"
            f"Error: {EXPECTED_IMPORT} from test\n"
            " Test Files  2 failed | 21 passed (23)\n"
            "      Tests  1 failed | 218 passed (219)\n"
        )
        self.assertIn("exactly", validate_result(1, output, red=True) or "")

    def test_accepts_passing_or_expected_red_evidence(self):
        self.assertIsNone(validate_result(0, "", red=True))
        self.assertIsNone(validate_result(1, "unexpected", red=False, recovery_coverage=True))
        self.assertIsNone(validate_result(0, "Test Files 1 passed", red=False))
        self.assertIn("failed", validate_result(1, "boom", red=False) or "")


if __name__ == "__main__":
    unittest.main()

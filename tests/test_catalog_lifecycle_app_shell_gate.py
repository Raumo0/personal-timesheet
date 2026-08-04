import unittest

from tools.agentic_workflow.validate_catalog_lifecycle_app_shell import (
    EXPECTED_RED_TESTS,
    TEST_PATH,
    allows_recovery_coverage,
    expects_red,
    validate_result,
)


def red_output(test_names=EXPECTED_RED_TESTS, failed_count=5):
    failures = "".join(f" FAIL  {TEST_PATH} > application shell > {name}\n" for name in test_names)
    return (
        failures
        + " Test Files  1 failed (1)\n"
        + f"      Tests  {failed_count} failed | 17 passed (22)\n"
    )


class CatalogLifecycleAppShellGateTests(unittest.TestCase):
    def test_detects_the_red_phase_from_task_8_1(self):
        self.assertTrue(expects_red("- [ ] 8.1 RED: AppShell lifecycle wiring\n"))
        self.assertFalse(expects_red("- [x] 8.1 RED: AppShell lifecycle wiring\n"))

    def test_allows_recovery_coverage_until_task_10_1_is_checked(self):
        self.assertTrue(allows_recovery_coverage("- [ ] 10.1 COVERAGE: recovery\n"))
        self.assertFalse(allows_recovery_coverage("- [x] 10.1 COVERAGE: recovery\n"))

    def test_accepts_only_the_five_expected_app_shell_failures(self):
        self.assertIsNone(validate_result(1, red_output(), red=True))

    def test_rejects_an_unexpected_or_missing_failure(self):
        output = red_output(EXPECTED_RED_TESTS[:-1], failed_count=4)
        self.assertIn("exactly", validate_result(1, output, red=True) or "")

    def test_accepts_passing_or_expected_red_evidence(self):
        self.assertIsNone(validate_result(0, "", red=True))
        self.assertIsNone(validate_result(1, "unexpected", red=False, recovery_coverage=True))
        self.assertIsNone(validate_result(0, "Test Files 1 passed", red=False))
        self.assertIn("failed", validate_result(1, "boom", red=False) or "")


if __name__ == "__main__":
    unittest.main()

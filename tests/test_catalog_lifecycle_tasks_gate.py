import unittest

from tools.agentic_workflow.validate_catalog_lifecycle_tasks import (
    EXPECTED_RED_TESTS,
    TEST_PATH,
    expects_red,
    validate_result,
)


def red_output(test_names=EXPECTED_RED_TESTS, failed_count=3):
    failures = "".join(f" FAIL  {TEST_PATH} > {name}\n" for name in test_names)
    return (
        failures
        + " Test Files  1 failed (1)\n"
        + f"      Tests  {failed_count} failed | 23 passed (26)\n"
    )


class CatalogLifecycleTasksGateTests(unittest.TestCase):
    def test_detects_the_red_phase_from_task_7_1(self):
        self.assertTrue(expects_red("- [ ] 7.1 RED: Task lifecycle UI\n"))
        self.assertFalse(expects_red("- [x] 7.1 RED: Task lifecycle UI\n"))

    def test_accepts_only_the_three_expected_task_ui_failures(self):
        self.assertIsNone(validate_result(1, red_output(), red=True))

    def test_rejects_an_unexpected_or_missing_failure(self):
        output = red_output(EXPECTED_RED_TESTS[:-1], failed_count=2)
        self.assertIn("exactly", validate_result(1, output, red=True) or "")

    def test_accepts_passing_or_expected_red_evidence(self):
        self.assertIsNone(validate_result(0, "", red=True))
        self.assertIsNone(validate_result(0, "Test Files 1 passed", red=False))
        self.assertIn("failed", validate_result(1, "boom", red=False) or "")


if __name__ == "__main__":
    unittest.main()

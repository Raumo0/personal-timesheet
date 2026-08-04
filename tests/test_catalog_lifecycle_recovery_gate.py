import unittest

from tools.agentic_workflow.validate_catalog_lifecycle_recovery import (
    EXPECTED_RED_TESTS,
    expects_red,
    validate_result,
)


def red_output(test_names=EXPECTED_RED_TESTS, failed_count=2):
    failures = "".join(f"     × {name}\n" for name in test_names)
    return (
        failures
        + " Test Files  2 failed | 21 passed (23)\n"
        + f"      Tests  {failed_count} failed | 248 passed (250)\n"
    )


class CatalogLifecycleRecoveryGateTests(unittest.TestCase):
    def test_detects_the_red_phase_from_task_10_1(self):
        self.assertTrue(expects_red("- [ ] 10.1 COVERAGE: recovery tests\n"))
        self.assertFalse(expects_red("- [x] 10.1 RED: recovery tests\n"))

    def test_accepts_only_the_two_expected_recovery_failures(self):
        self.assertIsNone(validate_result(1, red_output(), red=True))

    def test_rejects_an_unexpected_or_missing_failure(self):
        output = red_output(EXPECTED_RED_TESTS[:-1], failed_count=1)
        self.assertIn("exactly", validate_result(1, output, red=True) or "")

    def test_accepts_passing_or_expected_red_evidence(self):
        self.assertIsNone(validate_result(0, "", red=True))
        self.assertIsNone(validate_result(0, "Test Files 2 passed", red=False))
        self.assertIn("failed", validate_result(1, "boom", red=False) or "")


if __name__ == "__main__":
    unittest.main()

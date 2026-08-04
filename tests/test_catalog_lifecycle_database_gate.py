import unittest

from tools.agentic_workflow.validate_catalog_lifecycle_database import (
    EXPECTED_RED_TEST,
    expects_red,
    validate_result,
)


class CatalogLifecycleDatabaseGateTests(unittest.TestCase):
    def test_detects_the_red_phase_from_task_3_1(self):
        self.assertTrue(expects_red("- [ ] 3.1 RED: migration test\n"))
        self.assertFalse(expects_red("- [x] 3.1 RED: migration test\n"))

    def test_accepts_only_the_expected_single_red_failure(self):
        output = (
            f"test {EXPECTED_RED_TEST} ... FAILED\n"
            "test result: FAILED. 7 passed; 1 failed; 0 ignored; 0 measured\n"
        )
        self.assertIsNone(validate_result(101, output, red=True))

    def test_rejects_an_unexpected_or_additional_red_failure(self):
        output = (
            f"test {EXPECTED_RED_TEST} ... FAILED\n"
            "test database::tests::other ... FAILED\n"
            "test result: FAILED. 6 passed; 2 failed; 0 ignored; 0 measured\n"
        )
        self.assertIn("exactly", validate_result(101, output, red=True) or "")

    def test_accepts_passing_or_expected_red_evidence(self):
        self.assertIsNone(validate_result(0, "", red=True))
        self.assertIsNone(validate_result(0, "test result: ok", red=False))
        self.assertIn("failed", validate_result(101, "boom", red=False) or "")


if __name__ == "__main__":
    unittest.main()

import unittest

from tools.agentic_workflow.validate_catalog_lifecycle_integrated import (
    COMMANDS,
    RECOVERY_COMMANDS,
    commands_for_phase,
    is_recovery_pending,
    run_commands,
)


class Completed:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class CatalogLifecycleIntegratedGateTests(unittest.TestCase):
    def test_uses_only_recovery_gate_while_task_10_1_is_red(self):
        tasks = "- [ ] 10.1 RED: recovery coverage\n"

        self.assertTrue(is_recovery_pending(tasks))
        self.assertEqual(commands_for_phase(tasks), RECOVERY_COMMANDS)

    def test_uses_complete_gate_after_task_10_1(self):
        tasks = "- [x] 10.1 RED: recovery coverage\n"

        self.assertFalse(is_recovery_pending(tasks))
        self.assertEqual(commands_for_phase(tasks), COMMANDS)

    def test_runs_the_exact_integrated_command_set_in_order(self):
        observed = []

        def runner(command):
            observed.append(command)
            return Completed()

        self.assertEqual(run_commands(runner), 0)
        self.assertEqual(observed, COMMANDS)

    def test_fails_after_the_first_unsuccessful_command(self):
        observed = []

        def runner(command):
            observed.append(command)
            return Completed(returncode=1 if len(observed) == 2 else 0)

        self.assertEqual(run_commands(runner), 1)
        self.assertEqual(observed, COMMANDS[:2])


if __name__ == "__main__":
    unittest.main()

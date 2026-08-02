import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.architecture_handoff.provisioning_attempts import (  # noqa: E402
    FileProvisioningAttemptStore,
    InMemoryProvisioningAttemptStore,
    ProvisioningAttemptStoreError,
    default_attempt_ledger_path,
)


FIRST_ID = "prep_" + "a" * 43
SECOND_ID = "prep_" + "b" * 43
FIRST_FINGERPRINT = "1" * 64
SECOND_FINGERPRINT = "2" * 64


class ProvisioningAttemptStoreTests(unittest.TestCase):
    def test_bounds_reject_boolean_values(self):
        with self.assertRaisesRegex(
            ProvisioningAttemptStoreError,
            "max_entries",
        ):
            InMemoryProvisioningAttemptStore(max_entries=True)

    def test_default_ledger_uses_private_user_state_outside_repository(self):
        path = default_attempt_ledger_path(
            {"XDG_STATE_HOME": "/tmp/architecture-handoff-test-state"}
        )

        self.assertEqual(
            path,
            Path(
                "/tmp/architecture-handoff-test-state/architecture-handoff/"
                "provisioning-attempts-v1.json"
            ),
        )

    def test_in_memory_store_consumes_only_an_issued_identity_once(self):
        store = InMemoryProvisioningAttemptStore(max_entries=2)

        self.assertFalse(store.consume(FIRST_ID, FIRST_FINGERPRINT))
        self.assertTrue(store.issue(FIRST_ID, FIRST_FINGERPRINT))
        self.assertFalse(store.consume(FIRST_ID, SECOND_FINGERPRINT))
        self.assertTrue(store.consume(FIRST_ID, FIRST_FINGERPRINT))
        self.assertFalse(store.consume(FIRST_ID, FIRST_FINGERPRINT))

    def test_file_store_blocks_forgery_and_second_instance_replay(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            ledger = Path(temporary_directory) / "state" / "attempts.json"

            first_process = FileProvisioningAttemptStore(ledger)
            second_process = FileProvisioningAttemptStore(ledger)

            self.assertTrue(first_process.issue(FIRST_ID, FIRST_FINGERPRINT))
            self.assertFalse(
                second_process.consume(SECOND_ID, FIRST_FINGERPRINT)
            )
            self.assertFalse(
                second_process.consume(FIRST_ID, SECOND_FINGERPRINT)
            )
            self.assertTrue(
                second_process.consume(FIRST_ID, FIRST_FINGERPRINT)
            )
            self.assertFalse(
                FileProvisioningAttemptStore(ledger).consume(
                    FIRST_ID,
                    FIRST_FINGERPRINT,
                )
            )

    @unittest.skipUnless(os.name == "posix", "requires POSIX file locking")
    def test_file_store_blocks_fresh_process_replay(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            ledger = Path(temporary_directory) / "state" / "attempts.json"
            self.assertTrue(
                FileProvisioningAttemptStore(ledger).issue(
                    FIRST_ID,
                    FIRST_FINGERPRINT,
                )
            )
            program = (
                "import sys;"
                "from pathlib import Path;"
                "from tools.architecture_handoff.provisioning_attempts "
                "import FileProvisioningAttemptStore;"
                "print(FileProvisioningAttemptStore(Path(sys.argv[1]))"
                ".consume(sys.argv[2],sys.argv[3]))"
            )

            first = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-c",
                    program,
                    str(ledger),
                    FIRST_ID,
                    FIRST_FINGERPRINT,
                ],
                cwd=REPOSITORY_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            replay = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-c",
                    program,
                    str(ledger),
                    FIRST_ID,
                    FIRST_FINGERPRINT,
                ],
                cwd=REPOSITORY_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertEqual(first.stdout.strip(), "True")
            self.assertEqual(replay.stdout.strip(), "False")

    def test_file_store_is_private_and_fails_closed_at_bounded_capacity(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            ledger = Path(temporary_directory) / "state" / "attempts.json"
            store = FileProvisioningAttemptStore(
                ledger,
                max_entries=1,
                max_bytes=1024,
            )

            self.assertTrue(store.issue(FIRST_ID, FIRST_FINGERPRINT))
            with self.assertRaisesRegex(
                ProvisioningAttemptStoreError,
                "capacity",
            ):
                store.issue(SECOND_ID, SECOND_FINGERPRINT)

            self.assertLessEqual(ledger.stat().st_size, 1024)
            if os.name == "posix":
                self.assertEqual(
                    stat.S_IMODE(ledger.parent.stat().st_mode),
                    0o700,
                )
                self.assertEqual(
                    stat.S_IMODE(ledger.stat().st_mode),
                    0o600,
                )
                self.assertEqual(
                    stat.S_IMODE(
                        ledger.with_suffix(".json.lock").stat().st_mode
                    ),
                    0o600,
                )

    def test_file_store_rejects_duplicate_keys_and_boolean_version(self):
        damaged_documents = (
            (
                '{"preparations":{},"preparations":{},'
                '"version":1}'
            ),
            '{"preparations":{},"version":true}',
        )
        for document in damaged_documents:
            with self.subTest(document=document):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    ledger = (
                        Path(temporary_directory)
                        / "state"
                        / "attempts.json"
                    )
                    ledger.parent.mkdir(mode=0o700)
                    ledger.write_text(document, encoding="utf-8")
                    ledger.chmod(0o600)

                    with self.assertRaisesRegex(
                        ProvisioningAttemptStoreError,
                        "JSON|schema",
                    ):
                        FileProvisioningAttemptStore(ledger).issue(
                            FIRST_ID,
                            FIRST_FINGERPRINT,
                        )

    def test_file_store_fails_closed_at_byte_bound_and_insecure_mode(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            ledger = Path(temporary_directory) / "state" / "attempts.json"
            with self.assertRaisesRegex(
                ProvisioningAttemptStoreError,
                "byte limit",
            ):
                FileProvisioningAttemptStore(
                    ledger,
                    max_bytes=128,
                ).issue(FIRST_ID, FIRST_FINGERPRINT)

            store = FileProvisioningAttemptStore(ledger)
            self.assertTrue(store.issue(FIRST_ID, FIRST_FINGERPRINT))
            if os.name == "posix":
                ledger.chmod(0o644)
                with self.assertRaisesRegex(
                    ProvisioningAttemptStoreError,
                    "permissions",
                ):
                    store.consume(FIRST_ID, FIRST_FINGERPRINT)

    def test_declared_entry_capacity_fits_within_byte_bound(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            ledger = Path(temporary_directory) / "state" / "attempts.json"
            store = FileProvisioningAttemptStore(ledger)
            preparations = {
                f"prep_{index:043d}": {
                    "fingerprint": f"{index:064x}",
                    "state": "issued",
                }
                for index in range(4096)
            }
            store._prepare_parent()

            store._write_preparations(preparations)

            self.assertLessEqual(ledger.stat().st_size, 524_288)
            self.assertEqual(len(store._read_preparations()), 4096)

    @unittest.skipUnless(os.name == "posix", "requires POSIX file modes")
    def test_file_store_rejects_broken_symlink_and_insecure_lock(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            root.chmod(0o700)
            ledger = root / "attempts.json"
            ledger.symlink_to(root / "missing.json")
            with self.assertRaisesRegex(
                ProvisioningAttemptStoreError,
                "symlink",
            ):
                FileProvisioningAttemptStore(ledger).issue(
                    FIRST_ID,
                    FIRST_FINGERPRINT,
                )

        with tempfile.TemporaryDirectory() as temporary_directory:
            ledger = Path(temporary_directory) / "state" / "attempts.json"
            store = FileProvisioningAttemptStore(ledger)
            self.assertTrue(store.issue(FIRST_ID, FIRST_FINGERPRINT))
            ledger.with_suffix(".json.lock").chmod(0o644)
            with self.assertRaisesRegex(
                ProvisioningAttemptStoreError,
                "lock permissions",
            ):
                store.consume(FIRST_ID, FIRST_FINGERPRINT)

    def test_file_store_converts_raw_io_errors_to_safe_store_errors(self):
        operations = (
            (
                "fstat",
                "tools.architecture_handoff.provisioning_attempts.os.fstat",
            ),
            (
                "flock",
                "tools.architecture_handoff.provisioning_attempts.fcntl.flock",
            ),
            (
                "parent stat",
                "tools.architecture_handoff.provisioning_attempts.Path.stat",
            ),
        )
        for label, target in operations:
            with self.subTest(operation=label):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    ledger = (
                        Path(temporary_directory)
                        / "state"
                        / "attempts.json"
                    )
                    with patch(
                        target,
                        side_effect=OSError("raw-secret-path"),
                    ):
                        with self.assertRaises(
                            ProvisioningAttemptStoreError
                        ) as raised:
                            FileProvisioningAttemptStore(ledger).issue(
                                FIRST_ID,
                                FIRST_FINGERPRINT,
                            )
                    self.assertNotIn(
                        "raw-secret-path",
                        str(raised.exception),
                    )

        with tempfile.TemporaryDirectory() as temporary_directory:
            ledger = Path(temporary_directory) / "state" / "attempts.json"
            store = FileProvisioningAttemptStore(ledger)
            self.assertTrue(store.issue(FIRST_ID, FIRST_FINGERPRINT))
            with patch(
                "tools.architecture_handoff.provisioning_attempts.os.read",
                side_effect=OSError("raw-secret-path"),
            ):
                with self.assertRaises(
                    ProvisioningAttemptStoreError
                ) as raised:
                    store.consume(FIRST_ID, FIRST_FINGERPRINT)
            self.assertNotIn("raw-secret-path", str(raised.exception))


if __name__ == "__main__":
    unittest.main()

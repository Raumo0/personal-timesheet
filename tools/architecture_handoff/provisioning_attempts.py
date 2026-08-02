"""Provider-neutral, bounded replay protection for provisioning attempts."""

from __future__ import annotations

import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from threading import Lock
from typing import Callable, Mapping, Protocol

from .provisioning_models import validate_preparation_id

try:
    import fcntl
except ImportError:  # pragma: no cover - fail-closed platform guard
    fcntl = None


ATTEMPT_LEDGER_VERSION = 1
DEFAULT_ATTEMPT_LEDGER_MAX_ENTRIES = 4096
DEFAULT_ATTEMPT_LEDGER_MAX_BYTES = 524_288
_LEDGER_FILE_NAME = "provisioning-attempts-v1.json"


class ProvisioningAttemptStoreError(ValueError):
    """A preparation identity could not transition safely."""


class ProvisioningAttemptStore(Protocol):
    def issue(self, preparation_id: str, fingerprint: str) -> bool:
        """Persist a new identity/fingerprint binding."""

    def consume(self, preparation_id: str, fingerprint: str) -> bool:
        """Atomically transition a matching issued identity to consumed."""


def default_attempt_ledger_path(
    environ: Mapping[str, str] = os.environ,
) -> Path:
    configured = environ.get("XDG_STATE_HOME")
    if configured:
        state_root = Path(configured)
        if not state_root.is_absolute():
            raise ProvisioningAttemptStoreError(
                "XDG_STATE_HOME must be an absolute path"
            )
    else:
        state_root = Path.home() / ".local" / "state"
    return state_root / "architecture-handoff" / _LEDGER_FILE_NAME


def _validate_bounds(max_entries: int, max_bytes: int) -> None:
    if type(max_entries) is not int or max_entries < 1:
        raise ProvisioningAttemptStoreError(
            "attempt ledger max_entries must be positive"
        )
    if type(max_bytes) is not int or max_bytes < 128:
        raise ProvisioningAttemptStoreError(
            "attempt ledger max_bytes must be at least 128"
        )


def _validate_fingerprint(value: object) -> str:
    if (
        not isinstance(value, str)
        or re.fullmatch(r"[0-9a-f]{64}", value) is None
    ):
        raise ProvisioningAttemptStoreError(
            "attempt fingerprint must be a SHA-256 fingerprint"
        )
    return value


def _reject_duplicate_keys(pairs):
    document = {}
    for key, value in pairs:
        if key in document:
            raise ProvisioningAttemptStoreError(
                "attempt ledger contains a duplicate JSON object key"
            )
        document[key] = value
    return document


class InMemoryProvisioningAttemptStore:
    def __init__(
        self,
        *,
        max_entries: int = DEFAULT_ATTEMPT_LEDGER_MAX_ENTRIES,
    ) -> None:
        _validate_bounds(max_entries, 128)
        self._max_entries = max_entries
        self._preparations: dict[str, tuple[str, str]] = {}
        self._lock = Lock()

    def issue(self, preparation_id: str, fingerprint: str) -> bool:
        preparation_id = validate_preparation_id(preparation_id)
        fingerprint = _validate_fingerprint(fingerprint)
        with self._lock:
            if preparation_id in self._preparations:
                return False
            if len(self._preparations) >= self._max_entries:
                raise ProvisioningAttemptStoreError(
                    "attempt ledger capacity reached; identity was not issued"
                )
            self._preparations[preparation_id] = (
                fingerprint,
                "issued",
            )
            return True

    def consume(self, preparation_id: str, fingerprint: str) -> bool:
        preparation_id = validate_preparation_id(preparation_id)
        fingerprint = _validate_fingerprint(fingerprint)
        with self._lock:
            if self._preparations.get(preparation_id) != (
                fingerprint,
                "issued",
            ):
                return False
            self._preparations[preparation_id] = (
                fingerprint,
                "consumed",
            )
            return True


_path_locks_guard = Lock()
_path_locks: dict[Path, Lock] = {}


def _path_lock(path: Path) -> Lock:
    with _path_locks_guard:
        lock = _path_locks.get(path)
        if lock is None:
            lock = Lock()
            _path_locks[path] = lock
        return lock


class FileProvisioningAttemptStore:
    def __init__(
        self,
        path: Path,
        *,
        max_entries: int = DEFAULT_ATTEMPT_LEDGER_MAX_ENTRIES,
        max_bytes: int = DEFAULT_ATTEMPT_LEDGER_MAX_BYTES,
    ) -> None:
        path = Path(path)
        if not path.is_absolute():
            raise ProvisioningAttemptStoreError(
                "attempt ledger path must be absolute"
            )
        _validate_bounds(max_entries, max_bytes)
        self.path = path
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self._process_lock = _path_lock(path)

    def issue(self, preparation_id: str, fingerprint: str) -> bool:
        preparation_id = validate_preparation_id(preparation_id)
        fingerprint = _validate_fingerprint(fingerprint)

        def transition(
            preparations: dict[str, dict[str, str]],
        ) -> tuple[bool, bool]:
            if preparation_id in preparations:
                return False, False
            if len(preparations) >= self.max_entries:
                raise ProvisioningAttemptStoreError(
                    "attempt ledger capacity reached; identity was not issued"
                )
            preparations[preparation_id] = {
                "fingerprint": fingerprint,
                "state": "issued",
            }
            return True, True

        return self._transition(transition)

    def consume(self, preparation_id: str, fingerprint: str) -> bool:
        preparation_id = validate_preparation_id(preparation_id)
        fingerprint = _validate_fingerprint(fingerprint)

        def transition(
            preparations: dict[str, dict[str, str]],
        ) -> tuple[bool, bool]:
            if preparations.get(preparation_id) != {
                "fingerprint": fingerprint,
                "state": "issued",
            }:
                return False, False
            preparations[preparation_id]["state"] = "consumed"
            return True, True

        return self._transition(transition)

    def _transition(
        self,
        transition: Callable[
            [dict[str, dict[str, str]]],
            tuple[bool, bool],
        ],
    ) -> bool:
        if fcntl is None:
            raise ProvisioningAttemptStoreError(
                "safe cross-process attempt locking is unavailable"
            )
        with self._process_lock:
            self._prepare_parent()
            lock_path = self.path.with_suffix(self.path.suffix + ".lock")
            flags = os.O_CREAT | os.O_RDWR
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            try:
                try:
                    lock_fd = os.open(
                        lock_path,
                        flags | os.O_EXCL,
                        0o600,
                    )
                    lock_created = True
                except FileExistsError:
                    lock_fd = os.open(lock_path, flags, 0o600)
                    lock_created = False
            except OSError as error:
                raise ProvisioningAttemptStoreError(
                    "attempt ledger lock could not be opened safely"
                ) from error
            locked = False
            try:
                try:
                    metadata = os.fstat(lock_fd)
                except OSError as error:
                    raise ProvisioningAttemptStoreError(
                        "attempt ledger lock could not be inspected safely"
                    ) from error
                if not stat.S_ISREG(metadata.st_mode):
                    raise ProvisioningAttemptStoreError(
                        "attempt ledger lock must be a regular file"
                    )
                if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
                    raise ProvisioningAttemptStoreError(
                        "attempt ledger lock must be owned by the current user"
                    )
                if metadata.st_nlink != 1:
                    raise ProvisioningAttemptStoreError(
                        "attempt ledger lock must not have hard links"
                    )
                if lock_created:
                    try:
                        os.fchmod(lock_fd, 0o600)
                    except OSError as error:
                        raise ProvisioningAttemptStoreError(
                            "attempt ledger lock permissions "
                            "could not be secured"
                        ) from error
                elif stat.S_IMODE(metadata.st_mode) != 0o600:
                    raise ProvisioningAttemptStoreError(
                        "attempt ledger lock permissions must be 0600"
                    )
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_EX)
                except OSError as error:
                    raise ProvisioningAttemptStoreError(
                        "attempt ledger lock could not be acquired safely"
                    ) from error
                locked = True
                preparations = self._read_preparations()
                result, changed = transition(preparations)
                if changed:
                    self._write_preparations(preparations)
                return result
            finally:
                active_error = sys.exc_info()[0] is not None
                cleanup_error = None
                try:
                    if locked:
                        try:
                            fcntl.flock(lock_fd, fcntl.LOCK_UN)
                        except OSError as error:
                            cleanup_error = error
                finally:
                    try:
                        os.close(lock_fd)
                    except OSError as error:
                        cleanup_error = cleanup_error or error
                if cleanup_error is not None and not active_error:
                    raise ProvisioningAttemptStoreError(
                        "attempt ledger lock could not be released safely"
                    ) from cleanup_error

    def _prepare_parent(self) -> None:
        parent = self.path.parent
        try:
            parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as error:
            raise ProvisioningAttemptStoreError(
                "attempt ledger directory could not be created"
            ) from error
        try:
            unsafe = parent.is_symlink() or not parent.is_dir()
            metadata = parent.stat()
        except OSError as error:
            raise ProvisioningAttemptStoreError(
                "attempt ledger directory could not be inspected safely"
            ) from error
        if unsafe:
            raise ProvisioningAttemptStoreError(
                "attempt ledger directory is unsafe"
            )
        if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
            raise ProvisioningAttemptStoreError(
                "attempt ledger directory must be owned by the current user"
            )
        try:
            os.chmod(parent, 0o700)
        except OSError as error:
            raise ProvisioningAttemptStoreError(
                "attempt ledger directory permissions could not be secured"
            ) from error

    def _read_preparations(self) -> dict[str, dict[str, str]]:
        try:
            is_symlink = self.path.is_symlink()
            exists = self.path.exists()
        except OSError as error:
            raise ProvisioningAttemptStoreError(
                "attempt ledger path could not be inspected safely"
            ) from error
        if is_symlink:
            raise ProvisioningAttemptStoreError(
                "attempt ledger must not be a symlink"
            )
        if not exists:
            return {}
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            ledger_fd = os.open(self.path, flags)
        except OSError as error:
            raise ProvisioningAttemptStoreError(
                "attempt ledger could not be opened safely"
            ) from error
        try:
            try:
                metadata = os.fstat(ledger_fd)
            except OSError as error:
                raise ProvisioningAttemptStoreError(
                    "attempt ledger could not be inspected safely"
                ) from error
            if not stat.S_ISREG(metadata.st_mode):
                raise ProvisioningAttemptStoreError(
                    "attempt ledger must be a regular file"
                )
            if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
                raise ProvisioningAttemptStoreError(
                    "attempt ledger must be owned by the current user"
                )
            if metadata.st_nlink != 1:
                raise ProvisioningAttemptStoreError(
                    "attempt ledger must not have hard links"
                )
            if stat.S_IMODE(metadata.st_mode) != 0o600:
                raise ProvisioningAttemptStoreError(
                    "attempt ledger permissions must be 0600"
                )
            if metadata.st_size > self.max_bytes:
                raise ProvisioningAttemptStoreError(
                    "attempt ledger exceeds the byte limit"
                )
            payload = bytearray()
            while True:
                try:
                    chunk = os.read(ledger_fd, 65_536)
                except OSError as error:
                    raise ProvisioningAttemptStoreError(
                        "attempt ledger could not be read safely"
                    ) from error
                if not chunk:
                    break
                payload.extend(chunk)
                if len(payload) > self.max_bytes:
                    raise ProvisioningAttemptStoreError(
                        "attempt ledger exceeds the byte limit"
                    )
        finally:
            active_error = sys.exc_info()[0] is not None
            try:
                os.close(ledger_fd)
            except OSError as error:
                if not active_error:
                    raise ProvisioningAttemptStoreError(
                        "attempt ledger could not be closed safely"
                    ) from error
        try:
            document = json.loads(
                payload.decode("utf-8"),
                object_pairs_hook=_reject_duplicate_keys,
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ProvisioningAttemptStoreError(
                "attempt ledger is not valid JSON"
            ) from error
        if (
            not isinstance(document, dict)
            or set(document) != {"version", "preparations"}
            or type(document.get("version")) is not int
            or document["version"] != ATTEMPT_LEDGER_VERSION
            or not isinstance(document.get("preparations"), dict)
        ):
            raise ProvisioningAttemptStoreError(
                "attempt ledger has an unsupported schema"
            )
        preparations = document["preparations"]
        if len(preparations) > self.max_entries:
            raise ProvisioningAttemptStoreError(
                "attempt ledger exceeds the entry limit"
            )
        validated: dict[str, dict[str, str]] = {}
        for preparation_id, record in preparations.items():
            try:
                preparation_id = validate_preparation_id(preparation_id)
            except ValueError as error:
                raise ProvisioningAttemptStoreError(
                    "attempt ledger contains an invalid preparation identity"
                ) from error
            if (
                not isinstance(record, list)
                or len(record) != 2
                or record[1] not in {"i", "c"}
            ):
                raise ProvisioningAttemptStoreError(
                    "attempt ledger contains an invalid preparation record"
                )
            fingerprint = _validate_fingerprint(record[0])
            validated[preparation_id] = {
                "fingerprint": fingerprint,
                "state": "issued" if record[1] == "i" else "consumed",
            }
        return validated

    def _write_preparations(
        self,
        preparations: dict[str, dict[str, str]],
    ) -> None:
        document = {
            "version": ATTEMPT_LEDGER_VERSION,
            "preparations": {
                preparation_id: [
                    record["fingerprint"],
                    "i" if record["state"] == "issued" else "c",
                ]
                for preparation_id, record in preparations.items()
            },
        }
        payload = json.dumps(
            document,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if len(payload) > self.max_bytes:
            raise ProvisioningAttemptStoreError(
                "attempt ledger exceeds the byte limit"
            )
        temporary_fd = -1
        temporary_path = None
        try:
            temporary_fd, temporary_name = tempfile.mkstemp(
                dir=self.path.parent,
                prefix=".provisioning-attempts-",
            )
            temporary_path = Path(temporary_name)
            os.fchmod(temporary_fd, 0o600)
            view = memoryview(payload)
            while view:
                written = os.write(temporary_fd, view)
                view = view[written:]
            os.fsync(temporary_fd)
            os.close(temporary_fd)
            temporary_fd = -1
            os.replace(temporary_path, self.path)
            temporary_path = None
            os.chmod(self.path, 0o600)
            directory_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as error:
            raise ProvisioningAttemptStoreError(
                "attempt ledger could not be written atomically"
            ) from error
        finally:
            active_error = sys.exc_info()[0] is not None
            cleanup_error = None
            if temporary_fd >= 0:
                try:
                    os.close(temporary_fd)
                except OSError as error:
                    cleanup_error = error
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except FileNotFoundError:
                    pass
                except OSError as error:
                    cleanup_error = cleanup_error or error
            if cleanup_error is not None and not active_error:
                raise ProvisioningAttemptStoreError(
                    "attempt ledger temporary state could not be cleaned safely"
                ) from cleanup_error

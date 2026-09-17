"""Durable, locked access to the project-local ciphertext store."""

import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from filelock import FileLock

from agentsafe.exceptions import ConfigError, KeyNotFoundError
from agentsafe.kms.base import EncryptedBlob

SCHEMA_VERSION = 1


class ConfigStore:
    """The JSON ``appconfig`` ciphertext store."""

    def __init__(self, path: Path | str = "appconfig") -> None:
        self.path = Path(path)
        self.lock_path = Path(f"{self.path}.lock")

    def initialize(self) -> None:
        """Create an empty store and fail safely if it already exists."""
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self._lock():
            self._initialize_locked()

    def _initialize_locked(self) -> None:
        """Publish an empty store without exposing a partially-written file."""
        document: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "entries": {}}
        try:
            descriptor, temp_name = tempfile.mkstemp(
                prefix=".appconfig-", dir=self.path.parent, text=True
            )
        except OSError as error:
            raise ConfigError(f"could not create appconfig at {self.path}") from error
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(document, handle)
                handle.flush()
                os.fsync(handle.fileno())
            # link() atomically publishes the completed file but, unlike replace(),
            # refuses to overwrite a store created by another process.
            os.link(temp_name, self.path)
        except FileExistsError as error:
            raise ConfigError(f"appconfig already exists at {self.path}") from error
        except OSError as error:
            raise ConfigError(f"could not create appconfig at {self.path}") from error
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass

    def list_keys(self) -> list[str]:
        return list(self._read_entries().keys())

    def ensure_initialized(self) -> None:
        """Create an empty ciphertext store on the first write only."""
        if self.path.exists():
            return
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self._lock():
            if not self.path.exists():
                self._initialize_locked()

    def get(self, key: str) -> EncryptedBlob:
        entries = self._read_entries()
        try:
            raw = entries[key]
        except KeyError as error:
            raise KeyNotFoundError(f"no configuration value named '{key}'") from error
        if not isinstance(raw, dict):
            raise ConfigError("stored ciphertext envelope cannot be read")
        try:
            return EncryptedBlob.from_mapping(raw)
        except (TypeError, ValueError) as error:
            raise ConfigError("stored ciphertext envelope cannot be routed") from error

    def set(self, key: str, blob: EncryptedBlob) -> None:
        with self._lock():
            document = self._read_document()
            entries = self._entries_from_document(document)
            entries[key] = blob.to_mapping()
            self._write_document(document)

    def remove(self, key: str) -> None:
        with self._lock():
            document = self._read_document()
            entries = self._entries_from_document(document)
            if key not in entries:
                raise KeyNotFoundError(f"no configuration value named '{key}'")
            del entries[key]
            self._write_document(document)

    @contextmanager
    def _lock(self) -> Iterator[None]:
        lock = FileLock(str(self.lock_path))
        with lock:
            # filelock creates this lazily; chmod after acquisition covers supported POSIX systems.
            try:
                os.chmod(self.lock_path, 0o600)
            except OSError:
                pass
            yield

    def _read_entries(self) -> dict[str, Any]:
        return self._entries_from_document(self._read_document())

    def _read_document(self) -> dict[str, Any]:
        try:
            with self.path.open(encoding="utf-8") as handle:
                document = json.load(handle)
        except FileNotFoundError as error:
            raise ConfigError(f"appconfig does not exist at {self.path}") from error
        except (OSError, json.JSONDecodeError) as error:
            raise ConfigError(f"could not read appconfig at {self.path}") from error
        if not isinstance(document, dict):
            raise ConfigError("appconfig root must be a JSON object")
        return document

    @staticmethod
    def _entries_from_document(document: dict[str, Any]) -> dict[str, Any]:
        entries = document.get("entries", {})
        if not isinstance(entries, dict):
            raise ConfigError("appconfig entries must be a JSON object")
        return entries

    def _write_document(self, document: dict[str, Any]) -> None:
        # Migrate older local KMS configuration out of the ciphertext store.
        document.pop("kms_config", None)
        descriptor, temp_name = tempfile.mkstemp(
            prefix=".appconfig-", dir=self.path.parent, text=True
        )
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(document, handle, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.path)
            os.chmod(self.path, 0o600)
        except OSError as error:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
            raise ConfigError(f"could not write appconfig at {self.path}") from error

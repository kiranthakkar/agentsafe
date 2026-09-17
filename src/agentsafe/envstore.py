"""Durable, locked access to the project-local .env ciphertext store."""

import base64
import json
import os
import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from dotenv import dotenv_values
from filelock import FileLock

from agentsafe.exceptions import ConfigError, KeyNotFoundError
from agentsafe.kms.base import EncryptedBlob

BLOB_PREFIX = "agentsafe:v1:"
_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_env_key(key: str) -> None:
    """Raise ConfigError unless `key` is a valid environment-variable identifier."""
    if not isinstance(key, str) or not _KEY_PATTERN.match(key):
        raise ConfigError(
            f"'{key}' is not a valid environment variable name "
            "(letters, digits, underscores only, and it can't start with a digit)"
        )


def encode_blob(blob: EncryptedBlob) -> str:
    """Encode an EncryptedBlob as a single dotenv-safe value."""
    payload = json.dumps(blob.to_mapping(), separators=(",", ":")).encode("utf-8")
    return BLOB_PREFIX + base64.b64encode(payload).decode("ascii")


def decode_blob(key: str, raw: str) -> EncryptedBlob:
    """Decode a dotenv value produced by `encode_blob` back into an EncryptedBlob."""
    if not raw.startswith(BLOB_PREFIX):
        raise ConfigError(f"'{key}' is not an agentsafe-encrypted .env entry")
    try:
        payload = base64.b64decode(raw[len(BLOB_PREFIX) :], validate=True)
        mapping = json.loads(payload)
    except (ValueError, json.JSONDecodeError) as error:
        raise ConfigError(f"'{key}' ciphertext envelope cannot be read") from error
    if not isinstance(mapping, dict):
        raise ConfigError(f"'{key}' ciphertext envelope cannot be read")
    try:
        return EncryptedBlob.from_mapping(mapping)
    except (TypeError, ValueError) as error:
        raise ConfigError(f"'{key}' ciphertext envelope cannot be routed") from error


class EnvStore:
    """The dotenv-shaped `.env` ciphertext store (sibling to store.py's ConfigStore)."""

    def __init__(self, path: Path | str = ".env") -> None:
        self.path = Path(path)
        self.lock_path = Path(f"{self.path}.lock")

    def list_keys(self) -> list[str]:
        return list(self._read_entries().keys())

    def get(self, key: str) -> EncryptedBlob:
        validate_env_key(key)
        entries = self._read_entries()
        try:
            raw = entries[key]
        except KeyError as error:
            raise KeyNotFoundError(f"no configuration value named '{key}'") from error
        return decode_blob(key, raw)

    def set(self, key: str, blob: EncryptedBlob) -> None:
        validate_env_key(key)
        with self._lock():
            entries = self._read_entries()
            entries[key] = encode_blob(blob)
            self._write_entries(entries)

    def remove(self, key: str) -> None:
        validate_env_key(key)
        with self._lock():
            entries = self._read_entries()
            if key not in entries:
                raise KeyNotFoundError(f"no configuration value named '{key}'")
            del entries[key]
            self._write_entries(entries)

    def replace_all(self, entries: dict[str, EncryptedBlob]) -> None:
        """Fully regenerate the store from `entries` (used by `env encrypt`)."""
        for key in entries:
            validate_env_key(key)
        with self._lock():
            self._write_entries({key: encode_blob(blob) for key, blob in entries.items()})

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

    def _read_entries(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        return {key: value for key, value in dotenv_values(self.path).items() if value is not None}

    def _write_entries(self, entries: dict[str, str]) -> None:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        content = "".join(f'{key}="{value}"\n' for key, value in entries.items())
        descriptor, temp_name = tempfile.mkstemp(prefix=".env-", dir=self.path.parent, text=True)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, self.path)
            os.chmod(self.path, 0o600)
        except OSError as error:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
            raise ConfigError(f"could not write {self.path}") from error

"""Resolution and persistence of agentsafe's project-local settings."""

import configparser
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from filelock import FileLock

from agentsafe.exceptions import ConfigError

CONFIG_PATH = Path(".agentsafe") / "config"
CONFIG_SECTION = "agentsafe"
ENVIRONMENT_SETTINGS = {
    "kms_provider": "AGENTSAFE_KMS_PROVIDER",
    "auth_type": "AGENTSAFE_AUTH_TYPE",
    "profile": "AGENTSAFE_PROFILE",
    "crypto_endpoint": "AGENTSAFE_CRYPTO_ENDPOINT",
    "key_id": "AGENTSAFE_KEY_ID",
}


def read_config(path: Path = CONFIG_PATH) -> dict[str, str]:
    """Read the project-local KMS settings' single `[agentsafe]` section."""
    if not path.exists():
        return {}
    parser = configparser.ConfigParser()
    try:
        parser.read(path)
    except (OSError, configparser.Error) as error:
        raise ConfigError(f"could not read agentsafe configuration at {path}") from error
    return dict(parser[CONFIG_SECTION]) if parser.has_section(CONFIG_SECTION) else {}


def resolve_settings(
    explicit: dict[str, Any],
    *,
    config_path: Path = CONFIG_PATH,
) -> dict[str, Any]:
    """Resolve explicit, environment, then project-local settings (first match wins)."""
    file_settings = read_config(config_path)
    resolved: dict[str, Any] = {}
    for key, environment_name in ENVIRONMENT_SETTINGS.items():
        value = explicit.get(key)
        if value is None:
            value = os.environ.get(environment_name)
        if value is None:
            value = file_settings.get(key)
        if value is not None:
            resolved[key] = value
    resolved.setdefault("kms_provider", "oci")
    return resolved


def write_config(settings: dict[str, Any], path: Path = CONFIG_PATH) -> None:
    """Create the project-local KMS configuration without overwriting it."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with _lock(path):
        parser = configparser.ConfigParser()
        if path.exists():
            try:
                parser.read(path)
            except (OSError, configparser.Error) as error:
                raise ConfigError(f"could not read agentsafe configuration at {path}") from error
        if parser.has_section(CONFIG_SECTION):
            raise ConfigError(f"agentsafe configuration already exists at {path}")
        values = {key: str(value) for key, value in settings.items() if value is not None}
        parser[CONFIG_SECTION] = values
        _write_atomic(parser, path)


@contextmanager
def _lock(path: Path) -> Iterator[None]:
    lock_path = Path(f"{path}.lock")
    lock = FileLock(str(lock_path))
    with lock:
        # filelock creates this lazily; chmod after acquisition covers supported POSIX systems.
        try:
            os.chmod(lock_path, 0o600)
        except OSError:
            pass
        yield


def _write_atomic(parser: configparser.ConfigParser, path: Path) -> None:
    descriptor, temp_name = tempfile.mkstemp(
        prefix=".agentsafe-config-", dir=path.parent, text=True
    )
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            parser.write(handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        os.chmod(path, 0o600)
    except OSError as error:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise ConfigError(f"could not write agentsafe configuration at {path}") from error

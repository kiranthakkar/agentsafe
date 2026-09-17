"""Module-level `.env` API: load(), get(), set(), remove(), list_keys(), encrypt()."""

import os
import subprocess
import warnings
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from agentsafe.config import CONFIG_PATH, resolve_settings
from agentsafe.envstore import EnvStore, validate_env_key
from agentsafe.exceptions import ConfigError
from agentsafe.kms import get_provider
from agentsafe.kms.base import KMSProvider

DEFAULT_ENV_PATH = Path(".env")
DEFAULT_ENV_AGENT_PATH = Path(".env.agent")


def load(
    path: Path | str = DEFAULT_ENV_PATH,
    *,
    config_path: Path = CONFIG_PATH,
    **settings: Any,
) -> None:
    """Decrypt every entry in `.env` and populate `os.environ`."""
    resolved = resolve_settings(settings, config_path=config_path)
    store = EnvStore(path)
    providers: dict[str, KMSProvider] = {}
    for key in store.list_keys():
        blob = store.get(key)
        provider = providers.get(blob.provider)
        if provider is None:
            provider = get_provider(blob.provider, **resolved)
            providers[blob.provider] = provider
        os.environ[key] = provider.decrypt(blob)


def get(
    key: str,
    path: Path | str = DEFAULT_ENV_PATH,
    *,
    config_path: Path = CONFIG_PATH,
    **settings: Any,
) -> str:
    """Decrypt and return one `.env` value without touching `os.environ`."""
    resolved = resolve_settings(settings, config_path=config_path)
    blob = EnvStore(path).get(key)
    return get_provider(blob.provider, **resolved).decrypt(blob)


def set(
    key: str,
    value: str,
    path: Path | str = DEFAULT_ENV_PATH,
    *,
    config_path: Path = CONFIG_PATH,
    **settings: Any,
) -> None:
    """Encrypt and write one entry directly into `.env`."""
    if not isinstance(value, str):
        raise ConfigError("configuration values must be strings")
    resolved = resolve_settings(settings, config_path=config_path)
    provider = get_provider(resolved["kms_provider"], **resolved)
    EnvStore(path).set(key, provider.encrypt(value))


def remove(key: str, path: Path | str = DEFAULT_ENV_PATH) -> None:
    """Remove one `.env` entry."""
    EnvStore(path).remove(key)


def list_keys(path: Path | str = DEFAULT_ENV_PATH) -> list[str]:
    """Return `.env` entry names without decrypting any value."""
    return EnvStore(path).list_keys()


def encrypt(
    source: Path | str = DEFAULT_ENV_AGENT_PATH,
    dest: Path | str = DEFAULT_ENV_PATH,
    *,
    config_path: Path = CONFIG_PATH,
    **settings: Any,
) -> None:
    """Compile `.env.agent` into a fully-encrypted `.env` (regenerates `.env`)."""
    source_path = Path(source)
    if not source_path.exists():
        raise ConfigError(f"{source_path} does not exist")
    _warn_if_not_gitignored(source_path)

    resolved = resolve_settings(settings, config_path=config_path)
    provider = get_provider(resolved["kms_provider"], **resolved)

    plaintext_entries = {
        key: value for key, value in dotenv_values(source_path).items() if value is not None
    }
    for key in plaintext_entries:
        validate_env_key(key)

    encrypted = {key: provider.encrypt(value) for key, value in plaintext_entries.items()}
    EnvStore(dest).replace_all(encrypted)


def _warn_if_not_gitignored(source_path: Path) -> None:
    """Best-effort warning only; stays silent whenever the check itself is inconclusive."""
    try:
        result = subprocess.run(
            ["git", "check-ignore", "-q", source_path.name],
            cwd=source_path.resolve().parent,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return
    if result.returncode == 1:
        warnings.warn(
            f"{source_path} does not appear to be gitignored; it holds plaintext "
            "secrets and must never be committed.",
            stacklevel=2,
        )

"""Resolution and persistence of agentsafe's machine-wide settings."""

import configparser
import os
from pathlib import Path
from typing import Any

from agentsafe.exceptions import ConfigError

CONFIG_PATH = Path.home() / ".agentsafe" / "config"
ENVIRONMENT_SETTINGS = {
    "application": "AGENTSAFE_APPLICATION",
    "kms_provider": "AGENTSAFE_KMS_PROVIDER",
    "profile": "AGENTSAFE_PROFILE",
    "compartment": "AGENTSAFE_COMPARTMENT",
    "crypto_endpoint": "AGENTSAFE_CRYPTO_ENDPOINT",
    "key_id": "AGENTSAFE_KEY_ID",
}


def read_config(path: Path = CONFIG_PATH, *, application: str | None = None) -> dict[str, str]:
    """Read global fallback settings and, when selected, one named application profile."""
    if not path.exists():
        return {}
    parser = configparser.ConfigParser()
    try:
        parser.read(path)
    except (OSError, configparser.Error) as error:
        raise ConfigError(f"could not read agentsafe configuration at {path}") from error
    settings = dict(parser["agentsafe"]) if parser.has_section("agentsafe") else {}
    if application:
        section = _application_section(application)
        if parser.has_section(section):
            settings.update(parser[section])
    return settings


def resolve_settings(
    explicit: dict[str, Any],
    *,
    config_path: Path = CONFIG_PATH,
) -> dict[str, Any]:
    """Resolve explicit, environment, named application, and global fallback settings."""
    application = explicit.get("application") or os.environ.get("AGENTSAFE_APPLICATION")
    file_settings = read_config(config_path, application=application)
    global_settings = read_config(config_path)
    resolved: dict[str, Any] = {}
    for key, environment_name in ENVIRONMENT_SETTINGS.items():
        value = explicit.get(key)
        if value is None:
            value = os.environ.get(environment_name)
        if value is None:
            value = file_settings.get(key) if application else None
        if value is None:
            value = global_settings.get(key)
        if value is not None:
            resolved[key] = value
    if application is not None:
        resolved["application"] = application
    resolved.setdefault("kms_provider", "oci")
    return resolved


def write_config(
    settings: dict[str, Any], path: Path = CONFIG_PATH, *, application: str | None = None
) -> None:
    """Create one global or named application configuration without overwriting it."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    parser = configparser.ConfigParser()
    if path.exists():
        try:
            parser.read(path)
        except (OSError, configparser.Error) as error:
            raise ConfigError(f"could not read agentsafe configuration at {path}") from error
    section = _application_section(application) if application else "agentsafe"
    if parser.has_section(section):
        raise ConfigError(
            f"agentsafe configuration already exists for '{application or 'default'}'"
        )
    values = {key: str(value) for key, value in settings.items() if value is not None}
    if application is not None:
        values["application"] = application
    parser[section] = values
    try:
        with path.open("w", encoding="utf-8") as handle:
            os.chmod(path, 0o600)
            parser.write(handle)
    except OSError as error:
        raise ConfigError(f"could not write agentsafe configuration at {path}") from error


def _application_section(application: str) -> str:
    return f"application:{application}"

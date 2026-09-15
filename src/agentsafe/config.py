"""Resolution and persistence of agentsafe's machine-wide settings."""

import configparser
import os
from pathlib import Path
from typing import Any

from agentsafe.exceptions import ConfigError

CONFIG_PATH = Path.home() / ".agentsafe" / "config"
ENVIRONMENT_SETTINGS = {
    "kms_provider": "AGENTSAFE_KMS_PROVIDER",
    "profile": "AGENTSAFE_PROFILE",
    "compartment": "AGENTSAFE_COMPARTMENT",
    "crypto_endpoint": "AGENTSAFE_CRYPTO_ENDPOINT",
    "key_id": "AGENTSAFE_KEY_ID",
}


def read_config(path: Path = CONFIG_PATH) -> dict[str, str]:
    """Read settings from the optional INI configuration file."""
    if not path.exists():
        return {}
    parser = configparser.ConfigParser()
    try:
        parser.read(path)
    except (OSError, configparser.Error) as error:
        raise ConfigError(f"could not read agentsafe configuration at {path}") from error
    return dict(parser["agentsafe"]) if parser.has_section("agentsafe") else {}


def resolve_settings(
    explicit: dict[str, Any], *, config_path: Path = CONFIG_PATH
) -> dict[str, Any]:
    """Resolve settings: explicit, environment, config file, then OCI provider default."""
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
    """Create the global config once, without overwriting an existing file."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    parser = configparser.ConfigParser()
    parser["agentsafe"] = {key: str(value) for key, value in settings.items() if value is not None}
    try:
        with path.open("x", encoding="utf-8") as handle:
            os.chmod(path, 0o600)
            parser.write(handle)
    except FileExistsError as error:
        raise ConfigError(f"agentsafe configuration already exists at {path}") from error
    except OSError as error:
        raise ConfigError(f"could not write agentsafe configuration at {path}") from error

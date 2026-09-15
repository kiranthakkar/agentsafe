"""User-facing AgentSafe SDK."""

from pathlib import Path
from typing import Any

from agentsafe.config import CONFIG_PATH, resolve_settings, write_config
from agentsafe.exceptions import ConfigError
from agentsafe.kms import get_provider
from agentsafe.kms.base import KMSProvider
from agentsafe.store import ConfigStore


class AgentSafe:
    """Store and retrieve string configuration values encrypted by a KMS provider."""

    def __init__(self, appconfig_path: Path | str = "appconfig", **settings: Any) -> None:
        """Create a client using explicit settings, environment, then global configuration."""
        self.settings = resolve_settings(settings)
        self.store = ConfigStore(appconfig_path)

    @classmethod
    def init(
        cls,
        appconfig_path: Path | str = "appconfig",
        *,
        config_path: Path = CONFIG_PATH,
        **settings: Any,
    ) -> "AgentSafe":
        """Create global settings and an empty project store without overwriting either."""
        resolved = resolve_settings(settings, config_path=config_path)
        provider = resolved.get("kms_provider", "oci")
        if provider == "oci":
            missing = [
                key
                for key in ("profile", "compartment", "crypto_endpoint", "key_id")
                if not resolved.get(key)
            ]
            if missing:
                raise ConfigError(f"OCI configuration requires: {', '.join(missing)}")
        store = ConfigStore(appconfig_path)
        if config_path.exists() or store.path.exists():
            target = config_path if config_path.exists() else store.path
            raise ConfigError(f"init refused to overwrite existing file: {target}")
        write_config(resolved, config_path)
        store.initialize()
        return cls(appconfig_path, **resolved)

    def set(self, key: str, value: str) -> None:
        """Encrypt and store a string value under a non-empty configuration name."""
        self._validate_key(key)
        if not isinstance(value, str):
            raise ConfigError("configuration values must be strings")
        provider = self._provider()
        self.store.set(key, provider.encrypt(value))

    def get(self, key: str) -> str:
        """Decrypt and return one configuration value; absent names raise KeyNotFoundError."""
        self._validate_key(key)
        blob = self.store.get(key)
        return self._provider(blob.provider).decrypt(blob)

    def remove(self, key: str) -> None:
        """Remove one encrypted configuration value."""
        self._validate_key(key)
        self.store.remove(key)

    def list_keys(self) -> list[str]:
        """Return configuration names without decrypting any value."""
        return self.store.list_keys()

    def _provider(self, name: str | None = None) -> KMSProvider:
        return get_provider(name or self.settings["kms_provider"], **self.settings)

    @staticmethod
    def _validate_key(key: str) -> None:
        if not isinstance(key, str) or not key:
            raise ConfigError("configuration name must be a non-empty string")

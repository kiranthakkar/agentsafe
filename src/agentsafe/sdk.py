"""User-facing AgentSafe SDK."""

from pathlib import Path
from typing import Any

from agentsafe.config import (
    CONFIG_PATH,
    resolve_settings,
    write_config,
)
from agentsafe.exceptions import ConfigError
from agentsafe.kms import get_provider
from agentsafe.kms.base import KMSProvider
from agentsafe.store import ConfigStore


class AgentSafe:
    """Store and retrieve string configuration values encrypted by a KMS provider."""

    def __init__(
        self,
        appconfig_path: Path | str = "appconfig",
        *,
        config_path: Path = CONFIG_PATH,
        **settings: Any,
    ) -> None:
        """Create a client using explicit, environment, then project-local settings."""
        self.store = ConfigStore(appconfig_path)
        self.settings = resolve_settings(settings, config_path=config_path)
        # Reused so principal-mode signers (metadata-service reads + token exchange) are
        # built once, not on every call. This caches a client, never plaintext.
        self._providers: dict[str, KMSProvider] = {}

    @classmethod
    def init(
        cls,
        *,
        config_path: Path = CONFIG_PATH,
        **settings: Any,
    ) -> "AgentSafe":
        """Register the project-local KMS configuration without touching appconfig."""
        resolved = resolve_settings(settings, config_path=config_path)
        if resolved.get("kms_provider", "oci") == "oci":
            from agentsafe.kms.oci_provider import validate_settings

            validate_settings(resolved)  # static: never authenticates or contacts OCI
        write_config(resolved, config_path)
        return cls(config_path=config_path, **resolved)

    def set(self, key: str, value: str) -> None:
        """Encrypt and store a string value under a non-empty configuration name."""
        self._validate_key(key)
        if not isinstance(value, str):
            raise ConfigError("configuration values must be strings")
        provider = self._provider()
        self.store.ensure_initialized()
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
        name = name or self.settings["kms_provider"]
        provider = self._providers.get(name)
        if provider is None:
            provider = get_provider(name, **self.settings)
            self._providers[name] = provider
        return provider

    @staticmethod
    def _validate_key(key: str) -> None:
        if not isinstance(key, str) or not key:
            raise ConfigError("configuration name must be a non-empty string")

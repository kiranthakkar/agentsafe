"""Entry-point discovery and lazy KMS provider construction."""

from collections.abc import Callable
from importlib import metadata
from typing import Any, cast

from agentsafe.exceptions import ConfigError
from agentsafe.kms.base import KMSProvider

ProviderFactory = Callable[..., KMSProvider]


def _distribution_name(entry_point: metadata.EntryPoint) -> str:
    distribution = getattr(entry_point, "dist", None)
    return distribution.name if distribution is not None else "unknown distribution"


def discover_providers() -> dict[str, metadata.EntryPoint]:
    """Discover provider entry points, rejecting security-sensitive name collisions."""
    entries = list(metadata.entry_points(group="agentsafe.kms_providers"))
    providers: dict[str, metadata.EntryPoint] = {}
    for entry in entries:
        previous = providers.get(entry.name)
        if previous is not None:
            raise ConfigError(
                f"KMS provider name collision for '{entry.name}': "
                f"{_distribution_name(previous)} and {_distribution_name(entry)}"
            )
        providers[entry.name] = entry
    return providers


def get_provider(name: str, **settings: Any) -> KMSProvider:
    """Load and instantiate one selected provider without importing others."""
    entry = discover_providers().get(name)
    if entry is None:
        raise ConfigError(f"KMS provider '{name}' is not installed")
    try:
        factory = entry.load()
        return cast(KMSProvider, factory(**settings))
    except ConfigError:
        raise
    except ImportError as error:
        raise ConfigError(
            f"provider '{name}' is unavailable; install its optional extra"
        ) from error

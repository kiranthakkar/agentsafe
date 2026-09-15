"""Typed errors raised by agentsafe."""


class AgentSafeError(Exception):
    """Base class for all agentsafe errors."""


class ConfigError(AgentSafeError):
    """Raised for invalid or missing agentsafe configuration."""


class KeyNotFoundError(AgentSafeError):
    """Raised when a requested configuration name is absent."""


class KMSError(AgentSafeError):
    """Raised when a KMS provider cannot complete an operation."""

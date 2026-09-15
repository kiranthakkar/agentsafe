"""Public provider contract."""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class EncryptedBlob:
    """A provider-owned ciphertext envelope persisted in ``appconfig``."""

    provider: str
    ciphertext: str
    metadata: dict[str, Any]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "ciphertext": self.ciphertext,
            "metadata": self.metadata,
        }

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "EncryptedBlob":
        try:
            provider = value["provider"]
            ciphertext = value["ciphertext"]
            metadata = value["metadata"]
        except KeyError as error:
            raise ValueError("ciphertext envelope is missing a required field") from error
        if (
            not isinstance(provider, str)
            or not isinstance(ciphertext, str)
            or not isinstance(metadata, dict)
        ):
            raise TypeError("ciphertext envelope has invalid routing fields")
        return cls(provider=provider, ciphertext=ciphertext, metadata=metadata)


class KMSProvider(Protocol):
    """A KMS backend that owns encryption and ciphertext interpretation."""

    def encrypt(self, plaintext: str) -> EncryptedBlob:
        """Encrypt plaintext and return a provider-owned envelope."""

    def decrypt(self, blob: EncryptedBlob) -> str:
        """Decrypt an envelope created by this provider."""

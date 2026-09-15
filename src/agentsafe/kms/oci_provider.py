"""OCI KMS provider implementation, imported only when OCI is selected."""

from base64 import b64decode, b64encode
from typing import Any, cast

from agentsafe.exceptions import ConfigError, KMSError
from agentsafe.kms.base import EncryptedBlob


class OCIProvider:
    """Encrypt and decrypt values through an OCI vault crypto endpoint."""

    def __init__(
        self,
        *,
        profile: str | None = None,
        compartment: str | None = None,
        crypto_endpoint: str | None = None,
        key_id: str | None = None,
        **_: Any,
    ) -> None:
        missing = [
            label
            for label, value in {
                "profile": profile,
                "compartment": compartment,
                "crypto_endpoint": crypto_endpoint,
                "key_id": key_id,
            }.items()
            if not value
        ]
        if missing:
            raise ConfigError(f"OCI provider requires: {', '.join(missing)}")
        try:
            import oci  # type: ignore[import-untyped]
        except ImportError as error:
            raise ConfigError("provider 'oci' requires oci: pip install agentconfigsafe[oci]") from error
        try:
            configuration = oci.config.from_file(profile_name=profile)
            self._client = oci.key_management.KmsCryptoClient(
                configuration, service_endpoint=crypto_endpoint
            )
        except Exception as error:
            raise KMSError("could not initialize OCI KMS client") from error
        self._key_id = key_id
        self._oci: Any = oci

    def encrypt(self, plaintext: str) -> EncryptedBlob:
        try:
            details = self._oci.key_management.models.EncryptDataDetails(
                key_id=self._key_id,
                plaintext=b64encode(plaintext.encode("utf-8")).decode("ascii"),
            )
            response = self._client.encrypt(details).data
            key_version = getattr(response, "key_version_id", None)
            metadata = {"key_id": self._key_id}
            if key_version is not None:
                metadata["key_version"] = key_version
            return EncryptedBlob(provider="oci", ciphertext=response.ciphertext, metadata=metadata)
        except KMSError:
            raise
        except Exception as error:
            raise self._operation_error("encryption", error) from error

    def decrypt(self, blob: EncryptedBlob) -> str:
        try:
            key_id = blob.metadata.get("key_id")
            if not isinstance(key_id, str) or not key_id:
                raise KMSError("OCI ciphertext envelope is missing key_id metadata")
            details = self._oci.key_management.models.DecryptDataDetails(
                ciphertext=blob.ciphertext, key_id=key_id
            )
            response = self._client.decrypt(details).data
            encoded_plaintext = cast(str, response.plaintext)
            return b64decode(encoded_plaintext, validate=True).decode("utf-8")
        except KMSError:
            raise
        except Exception as error:
            raise self._operation_error("decryption", error) from error

    @staticmethod
    def _operation_error(operation: str, error: Exception) -> KMSError:
        """Expose only safe OCI diagnostics; request text may contain a secret."""
        status = getattr(error, "status", None)
        code = getattr(error, "code", None)
        if isinstance(status, int) and isinstance(code, str):
            return KMSError(f"OCI KMS {operation} failed (HTTP {status}, {code})")
        return KMSError(f"OCI KMS {operation} failed ({type(error).__name__})")

"""OCI KMS provider implementation, imported only when OCI is selected."""

from base64 import b64decode, b64encode
from collections.abc import Mapping
from typing import Any, cast

from agentsafe.exceptions import ConfigError, KMSError
from agentsafe.kms.base import EncryptedBlob

AUTH_PROFILE = "profile"
AUTH_INSTANCE_PRINCIPAL = "instance_principal"
AUTH_RESOURCE_PRINCIPAL = "resource_principal"
AUTH_TYPES = (AUTH_PROFILE, AUTH_INSTANCE_PRINCIPAL, AUTH_RESOURCE_PRINCIPAL)
DEFAULT_AUTH_TYPE = AUTH_PROFILE

_REQUIRED_SETTINGS = {
    AUTH_PROFILE: ("profile", "crypto_endpoint", "key_id"),
    AUTH_INSTANCE_PRINCIPAL: ("crypto_endpoint", "key_id"),
    AUTH_RESOURCE_PRINCIPAL: ("crypto_endpoint", "key_id"),
}


def validate_settings(settings: Mapping[str, Any]) -> str:
    """Check OCI settings statically and return the effective auth type.

    Never authenticates or contacts OCI. ``auth_type`` defaults to ``profile``
    when absent; ``profile`` is required (and only used) in that mode.
    """
    auth_type = settings.get("auth_type")
    if auth_type is None:
        auth_type = DEFAULT_AUTH_TYPE
    if auth_type not in AUTH_TYPES:
        raise ConfigError(f"OCI auth_type must be one of: {', '.join(AUTH_TYPES)}")
    missing = [name for name in _REQUIRED_SETTINGS[auth_type] if not settings.get(name)]
    if missing:
        raise ConfigError(f"OCI {auth_type} configuration requires: {', '.join(missing)}")
    return cast(str, auth_type)


class OCIProvider:
    """Encrypt and decrypt values through an OCI vault crypto endpoint."""

    def __init__(
        self,
        *,
        auth_type: str | None = None,
        profile: str | None = None,
        crypto_endpoint: str | None = None,
        key_id: str | None = None,
        **_: Any,
    ) -> None:
        mode = validate_settings(
            {
                "auth_type": auth_type,
                "profile": profile,
                "crypto_endpoint": crypto_endpoint,
                "key_id": key_id,
            }
        )
        try:
            import oci  # type: ignore[import-untyped]
        except ImportError as error:
            raise ConfigError(
                "provider 'oci' requires oci: pip install agentconfigsafe[oci]"
            ) from error
        try:
            if mode == AUTH_PROFILE:
                self._client = oci.key_management.KmsCryptoClient(
                    oci.config.from_file(profile_name=profile), service_endpoint=crypto_endpoint
                )
            else:
                # Principal signers are self-sufficient, so the config is empty. There is
                # deliberately no fallback to another mode if the signer cannot be built.
                signer = (
                    oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
                    if mode == AUTH_INSTANCE_PRINCIPAL
                    else oci.auth.signers.get_resource_principals_signer()
                )
                self._client = oci.key_management.KmsCryptoClient(
                    {}, signer=signer, service_endpoint=crypto_endpoint
                )
        except Exception as error:
            if mode == AUTH_PROFILE:
                raise KMSError("could not initialize OCI KMS client") from error
            label = mode.replace("_", " ")
            raise KMSError(f"OCI {label} authentication could not be initialized") from error
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

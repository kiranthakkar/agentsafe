import sys
from base64 import b64encode
from types import SimpleNamespace

import pytest

from agentsafe.exceptions import ConfigError, KMSError
from agentsafe.kms.base import EncryptedBlob
from agentsafe.kms.oci_provider import OCIProvider, validate_settings


def test_oci_request_and_response_mapping(monkeypatch):
    calls = []

    class FakeCryptoClient:
        def __init__(self, configuration, service_endpoint):
            assert configuration == {"profile": "DEFAULT"}
            assert service_endpoint == "https://crypto.example.test"

        def encrypt(self, details):
            calls.append(("encrypt", details))
            return SimpleNamespace(
                data=SimpleNamespace(ciphertext="encoded", key_version_id="version")
            )

        def decrypt(self, details):
            calls.append(("decrypt", details))
            return SimpleNamespace(
                data=SimpleNamespace(plaintext=b64encode(b"secret").decode("ascii"))
            )

    class EncryptDataDetails:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class DecryptDataDetails:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    fake_oci = SimpleNamespace(
        config=SimpleNamespace(from_file=lambda profile_name: {"profile": profile_name}),
        key_management=SimpleNamespace(
            KmsCryptoClient=FakeCryptoClient,
            models=SimpleNamespace(
                EncryptDataDetails=EncryptDataDetails,
                DecryptDataDetails=DecryptDataDetails,
            ),
        ),
    )
    monkeypatch.setitem(sys.modules, "oci", fake_oci)
    provider = OCIProvider(
        profile="DEFAULT",
        crypto_endpoint="https://crypto.example.test",
        key_id="ocid1.key.oc1..x",
    )

    blob = provider.encrypt("secret")
    assert blob == EncryptedBlob(
        "oci", "encoded", {"key_id": "ocid1.key.oc1..x", "key_version": "version"}
    )
    assert calls[0][1].key_id == "ocid1.key.oc1..x"
    assert calls[0][1].plaintext == "c2VjcmV0"
    assert provider.decrypt(blob) == "secret"
    assert calls[1][1].ciphertext == "encoded"
    assert calls[1][1].key_id == "ocid1.key.oc1..x"


ENDPOINT = "https://crypto.example.test"
KEY_ID = "ocid1.key.oc1..x"


def _install_fake_oci(monkeypatch, *, instance_error=None, resource_error=None):
    """Install a fake `oci` module and return a record of what the provider touched."""
    record = SimpleNamespace(clients=[], from_file_calls=[], signer_calls=[])

    class FakeCryptoClient:
        def __init__(self, configuration, service_endpoint, signer=None):
            record.clients.append(
                SimpleNamespace(
                    configuration=configuration, service_endpoint=service_endpoint, signer=signer
                )
            )

    def instance_signer():
        record.signer_calls.append("instance_principal")
        if instance_error is not None:
            raise instance_error
        return "INSTANCE-SIGNER"

    def resource_signer():
        record.signer_calls.append("resource_principal")
        if resource_error is not None:
            raise resource_error
        return "RESOURCE-SIGNER"

    def from_file(profile_name):
        record.from_file_calls.append(profile_name)
        return {"profile": profile_name}

    fake_oci = SimpleNamespace(
        config=SimpleNamespace(from_file=from_file),
        auth=SimpleNamespace(
            signers=SimpleNamespace(
                InstancePrincipalsSecurityTokenSigner=instance_signer,
                get_resource_principals_signer=resource_signer,
            )
        ),
        key_management=SimpleNamespace(
            KmsCryptoClient=FakeCryptoClient,
            models=SimpleNamespace(),
        ),
    )
    monkeypatch.setitem(sys.modules, "oci", fake_oci)
    return record


def test_profile_is_the_default_auth_type(monkeypatch):
    record = _install_fake_oci(monkeypatch)
    OCIProvider(profile="DEFAULT", crypto_endpoint=ENDPOINT, key_id=KEY_ID)

    assert record.from_file_calls == ["DEFAULT"]
    assert record.signer_calls == []
    assert record.clients[0].configuration == {"profile": "DEFAULT"}
    assert record.clients[0].signer is None


def test_instance_principal_uses_the_signer_and_no_profile(monkeypatch):
    record = _install_fake_oci(monkeypatch)
    OCIProvider(auth_type="instance_principal", crypto_endpoint=ENDPOINT, key_id=KEY_ID)

    assert record.signer_calls == ["instance_principal"]
    assert record.from_file_calls == []
    client = record.clients[0]
    assert client.configuration == {}
    assert client.signer == "INSTANCE-SIGNER"
    assert client.service_endpoint == ENDPOINT


def test_resource_principal_uses_the_signer_and_no_profile(monkeypatch):
    record = _install_fake_oci(monkeypatch)
    OCIProvider(auth_type="resource_principal", crypto_endpoint=ENDPOINT, key_id=KEY_ID)

    assert record.signer_calls == ["resource_principal"]
    assert record.from_file_calls == []
    client = record.clients[0]
    assert client.configuration == {}
    assert client.signer == "RESOURCE-SIGNER"
    assert client.service_endpoint == ENDPOINT


@pytest.mark.parametrize("auth_type", ["instance_principal", "resource_principal"])
def test_a_profile_is_ignored_in_principal_modes(monkeypatch, auth_type):
    record = _install_fake_oci(monkeypatch)
    OCIProvider(auth_type=auth_type, profile="COMMITTED", crypto_endpoint=ENDPOINT, key_id=KEY_ID)

    assert record.from_file_calls == []
    assert len(record.signer_calls) == 1


@pytest.mark.parametrize(
    ("auth_type", "expected_label"),
    [
        ("instance_principal", "instance principal"),
        ("resource_principal", "resource principal"),
    ],
)
def test_signer_failure_raises_kms_error_without_fallback_or_leaking(
    monkeypatch, auth_type, expected_label
):
    secret = RuntimeError("token=SECRET-TOKEN-VALUE")
    record = _install_fake_oci(monkeypatch, instance_error=secret, resource_error=secret)

    with pytest.raises(KMSError) as raised:
        OCIProvider(auth_type=auth_type, profile="DEFAULT", crypto_endpoint=ENDPOINT, key_id=KEY_ID)

    assert raised.value.__cause__ is secret
    assert expected_label in str(raised.value)
    assert "SECRET-TOKEN-VALUE" not in str(raised.value)
    assert record.from_file_calls == []
    assert record.signer_calls == [auth_type]
    assert record.clients == []


def test_an_unknown_auth_type_is_rejected(monkeypatch):
    _install_fake_oci(monkeypatch)
    with pytest.raises(ConfigError, match="profile, instance_principal, resource_principal"):
        OCIProvider(auth_type="api_key", crypto_endpoint=ENDPOINT, key_id=KEY_ID)
    with pytest.raises(ConfigError, match="auth_type"):
        OCIProvider(auth_type="", crypto_endpoint=ENDPOINT, key_id=KEY_ID)


def test_required_settings_depend_on_the_auth_type(monkeypatch):
    _install_fake_oci(monkeypatch)
    with pytest.raises(ConfigError, match="profile, crypto_endpoint, key_id"):
        OCIProvider()
    with pytest.raises(ConfigError) as raised:
        OCIProvider(auth_type="instance_principal", crypto_endpoint=ENDPOINT)
    assert "key_id" in str(raised.value)
    assert "profile" not in str(raised.value).split("requires:")[1]


def test_validate_settings_reports_the_effective_auth_type():
    assert validate_settings({"profile": "P", "crypto_endpoint": ENDPOINT, "key_id": KEY_ID}) == (
        "profile"
    )
    assert (
        validate_settings(
            {"auth_type": "resource_principal", "crypto_endpoint": ENDPOINT, "key_id": KEY_ID}
        )
        == "resource_principal"
    )

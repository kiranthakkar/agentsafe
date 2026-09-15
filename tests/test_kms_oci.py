import sys
from base64 import b64encode
from types import SimpleNamespace

from agentsafe.kms.base import EncryptedBlob
from agentsafe.kms.oci_provider import OCIProvider


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
        compartment="ocid1.compartment.oc1..x",
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

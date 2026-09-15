from agentsafe.kms.base import EncryptedBlob
from agentsafe.sdk import AgentSafe


class FakeProvider:
    def encrypt(self, plaintext: str) -> EncryptedBlob:
        return EncryptedBlob("fake", plaintext[::-1], {})

    def decrypt(self, blob: EncryptedBlob) -> str:
        return blob.ciphertext[::-1]


def test_sdk_uses_provider_contract(monkeypatch, tmp_path):
    monkeypatch.setattr("agentsafe.sdk.get_provider", lambda _name, **_settings: FakeProvider())
    safe = AgentSafe(tmp_path / "appconfig", kms_provider="fake")
    safe.set("TOKEN", "secret")

    assert safe.store.path.exists()
    assert safe.get("TOKEN") == "secret"
    assert safe.list_keys() == ["TOKEN"]
    safe.remove("TOKEN")
    assert safe.list_keys() == []

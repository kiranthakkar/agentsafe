import json

import pytest

from agentsafe.exceptions import ConfigError, KeyNotFoundError
from agentsafe.kms.base import EncryptedBlob
from agentsafe.store import ConfigStore


def test_round_trip_and_no_plaintext(tmp_path):
    path = tmp_path / "appconfig"
    store = ConfigStore(path)
    store.initialize()
    store.set("anything goes / here", EncryptedBlob("fake", "ciphertext", {"id": "x"}))

    assert store.get("anything goes / here").ciphertext == "ciphertext"
    assert store.list_keys() == ["anything goes / here"]
    assert "plaintext" not in path.read_text()
    assert json.loads(path.read_text())["schema_version"] == 1


def test_missing_keys_raise(tmp_path):
    store = ConfigStore(tmp_path / "appconfig")
    store.initialize()
    with pytest.raises(KeyNotFoundError):
        store.get("missing")
    with pytest.raises(KeyNotFoundError):
        store.remove("missing")


def test_initialize_refuses_overwrite(tmp_path):
    store = ConfigStore(tmp_path / "appconfig")
    store.initialize()
    with pytest.raises(ConfigError):
        store.initialize()


def test_store_contains_only_ciphertext_entries_not_kms_configuration(tmp_path):
    path = tmp_path / "appconfig"
    store = ConfigStore(path)
    store.initialize()
    store.set("TOKEN", EncryptedBlob("oci", "ciphertext", {}))

    document = json.loads(path.read_text())
    assert "kms_config" not in document
    assert document["entries"]["TOKEN"]["ciphertext"] == "ciphertext"

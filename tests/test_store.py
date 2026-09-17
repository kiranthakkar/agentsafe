import json
import os
import stat

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


def test_initialize_creates_file_with_owner_only_permissions(tmp_path):
    path = tmp_path / "appconfig"
    ConfigStore(path).initialize()
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_initialize_does_not_leave_a_partial_file_when_publish_fails(monkeypatch, tmp_path):
    path = tmp_path / "appconfig"

    def fail_publish(_source, _destination):
        raise OSError("simulated publish failure")

    monkeypatch.setattr("agentsafe.store.os.link", fail_publish)

    with pytest.raises(ConfigError, match="could not create appconfig"):
        ConfigStore(path).initialize()

    assert not path.exists()
    assert list(tmp_path.glob(".appconfig-*")) == []


def test_store_contains_only_ciphertext_entries_not_kms_configuration(tmp_path):
    path = tmp_path / "appconfig"
    store = ConfigStore(path)
    store.initialize()
    store.set("TOKEN", EncryptedBlob("oci", "ciphertext", {}))

    document = json.loads(path.read_text())
    assert "kms_config" not in document
    assert document["entries"]["TOKEN"]["ciphertext"] == "ciphertext"

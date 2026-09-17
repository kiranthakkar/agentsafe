import os
import stat

import pytest

from agentsafe.envstore import BLOB_PREFIX, EnvStore, validate_env_key
from agentsafe.exceptions import ConfigError, KeyNotFoundError
from agentsafe.kms.base import EncryptedBlob


def test_round_trip_and_no_plaintext(tmp_path):
    path = tmp_path / ".env"
    store = EnvStore(path)
    store.set("TOKEN", EncryptedBlob("fake", "ciphertext", {"id": "x"}))

    assert store.get("TOKEN").ciphertext == "ciphertext"
    assert store.list_keys() == ["TOKEN"]
    assert "ciphertext" not in path.read_text()
    assert BLOB_PREFIX in path.read_text()


def test_missing_keys_raise(tmp_path):
    store = EnvStore(tmp_path / ".env")
    with pytest.raises(KeyNotFoundError):
        store.get("missing")
    with pytest.raises(KeyNotFoundError):
        store.remove("missing")


def test_set_rejects_invalid_key_names(tmp_path):
    store = EnvStore(tmp_path / ".env")
    with pytest.raises(ConfigError):
        store.set("not a valid key", EncryptedBlob("fake", "ciphertext", {}))
    with pytest.raises(ConfigError):
        store.set("1STARTS_WITH_DIGIT", EncryptedBlob("fake", "ciphertext", {}))


def test_valid_env_key_names_are_accepted():
    validate_env_key("OPENAI_API_KEY")
    validate_env_key("_leading_underscore")
    validate_env_key("lower_case")


def test_set_get_remove_round_trip(tmp_path):
    store = EnvStore(tmp_path / ".env")
    store.set("A", EncryptedBlob("fake", "a-cipher", {}))
    store.set("B", EncryptedBlob("fake", "b-cipher", {}))
    assert sorted(store.list_keys()) == ["A", "B"]

    store.remove("A")
    assert store.list_keys() == ["B"]
    with pytest.raises(KeyNotFoundError):
        store.get("A")


def test_replace_all_fully_regenerates_the_file(tmp_path):
    store = EnvStore(tmp_path / ".env")
    store.set("OLD", EncryptedBlob("fake", "old-cipher", {}))

    store.replace_all({"NEW": EncryptedBlob("fake", "new-cipher", {})})

    assert store.list_keys() == ["NEW"]
    with pytest.raises(KeyNotFoundError):
        store.get("OLD")


def test_replace_all_rejects_invalid_key_names(tmp_path):
    store = EnvStore(tmp_path / ".env")
    with pytest.raises(ConfigError):
        store.replace_all({"not a valid key": EncryptedBlob("fake", "cipher", {})})


def test_file_created_with_owner_only_permissions(tmp_path):
    path = tmp_path / ".env"
    EnvStore(path).set("TOKEN", EncryptedBlob("fake", "ciphertext", {}))
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_decoding_a_non_agentsafe_entry_raises(tmp_path):
    path = tmp_path / ".env"
    path.write_text('PLAIN=not-an-agentsafe-value\n', encoding="utf-8")

    store = EnvStore(path)
    with pytest.raises(ConfigError):
        store.get("PLAIN")


def test_list_keys_tolerates_a_foreign_or_invalid_key_name(tmp_path):
    path = tmp_path / ".env"
    path.write_text('1INVALID="agentsafe:v1:ignored"\n', encoding="utf-8")

    assert EnvStore(path).list_keys() == ["1INVALID"]


def test_get_rejects_an_invalid_key_argument(tmp_path):
    with pytest.raises(ConfigError, match="valid environment variable name"):
        EnvStore(tmp_path / ".env").get("1INVALID")


def test_a_foreign_entry_does_not_block_access_to_other_valid_keys(tmp_path):
    path = tmp_path / ".env"
    store = EnvStore(path)
    store.set("GOOD_KEY", EncryptedBlob("fake", "cipher", {}))
    with path.open("a", encoding="utf-8") as handle:
        handle.write('NODE-ENV="production"\n')

    assert sorted(store.list_keys()) == ["GOOD_KEY", "NODE-ENV"]
    assert store.get("GOOD_KEY").ciphertext == "cipher"

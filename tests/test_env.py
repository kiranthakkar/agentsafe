import os
import subprocess
import warnings

import pytest

from agentsafe import env
from agentsafe.exceptions import ConfigError, KeyNotFoundError
from agentsafe.kms.base import EncryptedBlob


class FakeProvider:
    def encrypt(self, plaintext: str) -> EncryptedBlob:
        return EncryptedBlob("fake", plaintext[::-1], {})

    def decrypt(self, blob: EncryptedBlob) -> str:
        return blob.ciphertext[::-1]


@pytest.fixture(autouse=True)
def _fake_provider(monkeypatch):
    monkeypatch.setattr("agentsafe.env.get_provider", lambda _name, **_settings: FakeProvider())


def test_set_and_get_round_trip(tmp_path):
    path = tmp_path / ".env"
    env.set("TOKEN", "secret", path, config_path=tmp_path / "config")
    assert env.get("TOKEN", path, config_path=tmp_path / "config") == "secret"
    assert env.list_keys(path) == ["TOKEN"]


def test_remove(tmp_path):
    path = tmp_path / ".env"
    env.set("TOKEN", "secret", path, config_path=tmp_path / "config")
    env.remove("TOKEN", path)
    with pytest.raises(KeyNotFoundError):
        env.get("TOKEN", path, config_path=tmp_path / "config")


def test_set_rejects_non_string_values(tmp_path):
    with pytest.raises(ConfigError):
        env.set("TOKEN", 123, tmp_path / ".env", config_path=tmp_path / "config")


def test_load_populates_os_environ(tmp_path):
    path = tmp_path / ".env"
    env.set("AGENTSAFE_TEST_LOAD_KEY", "loaded-value", path, config_path=tmp_path / "config")
    try:
        env.load(path, config_path=tmp_path / "config")
        assert os.environ["AGENTSAFE_TEST_LOAD_KEY"] == "loaded-value"
    finally:
        os.environ.pop("AGENTSAFE_TEST_LOAD_KEY", None)


def test_load_constructs_one_provider_per_provider_name(monkeypatch, tmp_path):
    path = tmp_path / ".env"
    env.set("FIRST", "first", path, config_path=tmp_path / "config")
    env.set("SECOND", "second", path, config_path=tmp_path / "config")
    calls = []

    def get_fake_provider(name, **_settings):
        calls.append(name)
        return FakeProvider()

    monkeypatch.setattr("agentsafe.env.get_provider", get_fake_provider)
    try:
        env.load(path, config_path=tmp_path / "config")
        assert calls == ["fake"]
    finally:
        os.environ.pop("FIRST", None)
        os.environ.pop("SECOND", None)


def test_encrypt_compiles_env_agent_into_env(tmp_path):
    source = tmp_path / ".env.agent"
    dest = tmp_path / ".env"
    source.write_text("OPENAI_API_KEY=sk-plaintext\nOTHER=value\n", encoding="utf-8")

    env.encrypt(source, dest, config_path=tmp_path / "config")

    assert sorted(env.list_keys(dest)) == ["OPENAI_API_KEY", "OTHER"]
    assert env.get("OPENAI_API_KEY", dest, config_path=tmp_path / "config") == "sk-plaintext"
    assert "sk-plaintext" not in dest.read_text()


def test_encrypt_fully_regenerates_dest(tmp_path):
    source = tmp_path / ".env.agent"
    dest = tmp_path / ".env"
    env.set("STALE", "stale-value", dest, config_path=tmp_path / "config")

    source.write_text("FRESH=fresh-value\n", encoding="utf-8")
    env.encrypt(source, dest, config_path=tmp_path / "config")

    assert env.list_keys(dest) == ["FRESH"]


def test_encrypt_requires_an_existing_source(tmp_path):
    with pytest.raises(ConfigError):
        env.encrypt(tmp_path / "missing.env.agent", tmp_path / ".env", config_path=tmp_path / "config")


def test_encrypt_rejects_invalid_key_names_in_source(tmp_path):
    source = tmp_path / ".env.agent"
    source.write_text("1STARTS_WITH_DIGIT=value\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        env.encrypt(source, tmp_path / ".env", config_path=tmp_path / "config")


def test_encrypt_warns_if_source_is_not_gitignored(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    source = tmp_path / ".env.agent"
    source.write_text("KEY=value\n", encoding="utf-8")

    with pytest.warns(UserWarning, match="gitignore"):
        env.encrypt(source, tmp_path / ".env", config_path=tmp_path / "config")


def test_encrypt_does_not_warn_if_source_is_gitignored(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text(".env.agent\n", encoding="utf-8")
    source = tmp_path / ".env.agent"
    source.write_text("KEY=value\n", encoding="utf-8")

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        env.encrypt(source, tmp_path / ".env", config_path=tmp_path / "config")

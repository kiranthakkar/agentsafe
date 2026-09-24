import os
import stat

import pytest

from agentsafe.config import resolve_settings, write_config
from agentsafe.exceptions import ConfigError
from agentsafe.sdk import AgentSafe
from agentsafe.store import ConfigStore


def test_empty_name_is_rejected(tmp_path):
    safe = AgentSafe(tmp_path / "appconfig", kms_provider="fake")
    safe.store.initialize()
    with pytest.raises(ConfigError):
        safe.set("", "value")


def test_init_requires_all_oci_settings(tmp_path):
    with pytest.raises(ConfigError, match="key_id"):
        AgentSafe.init(
            config_path=tmp_path / "config",
            profile="DEFAULT",
            crypto_endpoint="https://example.test",
        )


def test_init_registers_oci_configuration_without_creating_appconfig(tmp_path):
    config_path = tmp_path / "project-config"
    appconfig_path = tmp_path / "appconfig"

    AgentSafe.init(
        config_path=config_path,
        profile="DEFAULT",
        crypto_endpoint="https://first.example.test",
        key_id="ocid1.key.oc1..first",
    )

    safe = AgentSafe(appconfig_path, config_path=config_path)
    assert safe.settings["profile"] == "DEFAULT"
    assert safe.settings["key_id"] == "ocid1.key.oc1..first"
    assert not appconfig_path.exists()


def test_init_allows_an_existing_appconfig_without_modifying_it(tmp_path):
    appconfig = tmp_path / "appconfig"
    ConfigStore(appconfig).initialize()

    AgentSafe.init(
        config_path=tmp_path / "agentsafe-config",
        profile="DEMO",
        crypto_endpoint="https://demo.example.test",
        key_id="ocid1.key.oc1..demo",
    )

    assert appconfig.exists()
    assert "kms_config" not in appconfig.read_text()


def test_init_fails_if_project_config_already_exists(tmp_path):
    config_path = tmp_path / "config"
    AgentSafe.init(
        config_path=config_path,
        profile="FIRST",
        crypto_endpoint="https://first.example.test",
        key_id="ocid1.key.oc1..first",
    )

    with pytest.raises(ConfigError):
        AgentSafe.init(
            config_path=config_path,
            profile="SECOND",
            crypto_endpoint="https://second.example.test",
            key_id="ocid1.key.oc1..second",
        )


def test_explicit_settings_override_project_file(tmp_path):
    appconfig = tmp_path / "appconfig"
    config_path = tmp_path / "config"
    write_config(
        {
            "kms_provider": "oci",
            "profile": "FROM_FILE",
            "crypto_endpoint": "https://example.test",
            "key_id": "ocid1.key.oc1..x",
        },
        config_path,
    )

    from_file = AgentSafe(appconfig, config_path=config_path)
    explicit = AgentSafe(appconfig, config_path=config_path, profile="FROM_EXPLICIT")
    assert from_file.settings["profile"] == "FROM_FILE"
    assert explicit.settings["profile"] == "FROM_EXPLICIT"


def test_profile_env_var_overrides_project_file(monkeypatch, tmp_path):
    config_path = tmp_path / "config"
    write_config(
        {
            "kms_provider": "oci",
            "profile": "FROM_FILE",
            "crypto_endpoint": "https://example.test",
            "key_id": "ocid1.key.oc1..x",
        },
        config_path,
    )
    monkeypatch.setenv("AGENTSAFE_PROFILE", "FROM_ENV")

    resolved = resolve_settings({}, config_path=config_path)
    assert resolved["profile"] == "FROM_ENV"


def test_write_config_is_locked_and_written_atomically(tmp_path):
    config_path = tmp_path / "config"
    AgentSafe.init(
        config_path=config_path,
        profile="ATOMIC",
        crypto_endpoint="https://atomic.example.test",
        key_id="ocid1.key.oc1..atomic",
    )

    assert (tmp_path / "config.lock").exists()
    assert stat.S_IMODE(os.stat(config_path).st_mode) == 0o600
    assert list(tmp_path.glob(".agentsafe-config-*")) == []


def test_init_supports_principal_auth_without_a_profile_and_never_authenticates(
    monkeypatch, tmp_path
):
    def fail(*_args, **_kwargs):
        raise AssertionError("init must not construct the provider")

    monkeypatch.setattr("agentsafe.sdk.get_provider", fail)
    config_path = tmp_path / "config"

    AgentSafe.init(
        config_path=config_path,
        auth_type="instance_principal",
        crypto_endpoint="https://crypto.example.test",
        key_id="ocid1.key.oc1..x",
    )

    text = config_path.read_text()
    assert "auth_type = instance_principal" in text
    assert "profile" not in text


def test_init_records_but_does_not_require_a_profile_for_resource_principal(tmp_path):
    config_path = tmp_path / "config"
    AgentSafe.init(
        config_path=config_path,
        auth_type="resource_principal",
        profile="COMMITTED",
        crypto_endpoint="https://crypto.example.test",
        key_id="ocid1.key.oc1..x",
    )
    assert "profile = COMMITTED" in config_path.read_text()


def test_init_rejects_an_unknown_auth_type(tmp_path):
    with pytest.raises(ConfigError, match="instance_principal"):
        AgentSafe.init(
            config_path=tmp_path / "config",
            auth_type="api_key",
            crypto_endpoint="https://crypto.example.test",
            key_id="ocid1.key.oc1..x",
        )
    assert not (tmp_path / "config").exists()


def test_init_names_only_what_the_principal_mode_needs(tmp_path):
    with pytest.raises(ConfigError) as raised:
        AgentSafe.init(config_path=tmp_path / "config", auth_type="instance_principal")
    assert "crypto_endpoint, key_id" in str(raised.value)
    assert "profile" not in str(raised.value).split("requires:")[1]


def test_auth_type_env_var_overrides_the_project_file(monkeypatch, tmp_path):
    config_path = tmp_path / "config"
    write_config(
        {
            "kms_provider": "oci",
            "auth_type": "profile",
            "profile": "FROM_FILE",
            "crypto_endpoint": "https://example.test",
            "key_id": "ocid1.key.oc1..x",
        },
        config_path,
    )
    monkeypatch.setenv("AGENTSAFE_AUTH_TYPE", "instance_principal")

    resolved = resolve_settings({}, config_path=config_path)
    assert resolved["auth_type"] == "instance_principal"
    assert resolved["profile"] == "FROM_FILE"


def test_provider_is_constructed_once_and_reused(monkeypatch, tmp_path):
    from agentsafe.kms.base import EncryptedBlob

    class FakeProvider:
        def encrypt(self, plaintext):
            return EncryptedBlob("fake", plaintext[::-1], {})

        def decrypt(self, blob):
            return blob.ciphertext[::-1]

    constructed = []

    def build(name, **_settings):
        constructed.append(name)
        return FakeProvider()

    monkeypatch.setattr("agentsafe.sdk.get_provider", build)
    safe = AgentSafe(tmp_path / "appconfig", kms_provider="fake")
    safe.set("A", "one")
    safe.set("B", "two")
    assert safe.get("A") == "one"
    assert safe.get("B") == "two"

    assert constructed == ["fake"]


def test_a_failed_provider_construction_is_not_cached(monkeypatch, tmp_path):
    attempts = []

    def build(name, **_settings):
        attempts.append(name)
        raise ConfigError("boom")

    monkeypatch.setattr("agentsafe.sdk.get_provider", build)
    safe = AgentSafe(tmp_path / "appconfig", kms_provider="fake")
    for _ in range(2):
        with pytest.raises(ConfigError):
            safe.set("A", "one")
    assert attempts == ["fake", "fake"]

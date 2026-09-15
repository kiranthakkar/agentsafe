import pytest

from agentsafe.config import write_config
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
            compartment="ocid",
            crypto_endpoint="https://example.test",
        )


def test_init_registers_oci_configuration_without_creating_appconfig(tmp_path):
    global_config = tmp_path / "global-config"
    first_path = tmp_path / "first" / "appconfig"
    second_path = tmp_path / "second" / "appconfig"

    AgentSafe.init(
        config_path=global_config,
        application="first",
        profile="FIRST",
        compartment="ocid1.compartment.oc1..first",
        crypto_endpoint="https://first.example.test",
        key_id="ocid1.key.oc1..first",
    )
    AgentSafe.init(
        config_path=global_config,
        application="second",
        profile="SECOND",
        compartment="ocid1.compartment.oc1..second",
        crypto_endpoint="https://second.example.test",
        key_id="ocid1.key.oc1..second",
    )

    first = AgentSafe(first_path, config_path=global_config, application="first")
    second = AgentSafe(second_path, config_path=global_config, application="second")
    assert first.settings["profile"] == "FIRST"
    assert first.settings["key_id"] == "ocid1.key.oc1..first"
    assert second.settings["profile"] == "SECOND"
    assert second.settings["key_id"] == "ocid1.key.oc1..second"
    assert "[application:first]" in global_config.read_text()
    assert "[application:second]" in global_config.read_text()
    assert not first_path.exists()
    assert not second_path.exists()


def test_init_allows_an_existing_appconfig_without_modifying_it(tmp_path):
    appconfig = tmp_path / "appconfig"
    ConfigStore(appconfig).initialize()

    AgentSafe.init(
        config_path=tmp_path / "agentsafe-config",
        application="demo",
        profile="DEMO",
        compartment="ocid1.compartment.oc1..demo",
        crypto_endpoint="https://demo.example.test",
        key_id="ocid1.key.oc1..demo",
    )

    assert appconfig.exists()
    assert "kms_config" not in appconfig.read_text()


def test_application_configuration_overrides_global_fallback(tmp_path):
    appconfig = tmp_path / "appconfig"
    global_config = tmp_path / "global-config"
    AgentSafe.init(
        config_path=global_config,
        application="application",
        profile="APPLICATION",
        compartment="ocid1.compartment.oc1..application",
        crypto_endpoint="https://application.example.test",
        key_id="ocid1.key.oc1..application",
    )
    write_config(
        {
            "kms_provider": "oci",
            "profile": "GLOBAL",
            "compartment": "ocid1.compartment.oc1..global",
            "crypto_endpoint": "https://global.example.test",
            "key_id": "ocid1.key.oc1..global",
        },
        global_config,
    )

    local = AgentSafe(appconfig, config_path=global_config, application="application")
    explicit = AgentSafe(
        appconfig, config_path=global_config, application="application", profile="EXPLICIT"
    )
    assert local.settings["profile"] == "APPLICATION"
    assert explicit.settings["profile"] == "EXPLICIT"


def test_init_registers_named_application_configurations(tmp_path):
    global_config = tmp_path / "agentsafe-config"
    AgentSafe.init(
        config_path=global_config,
        application="billing",
        profile="BILLING",
        compartment="ocid1.compartment.oc1..billing",
        crypto_endpoint="https://billing.example.test",
        key_id="ocid1.key.oc1..billing",
    )
    AgentSafe.init(
        config_path=global_config,
        application="analytics",
        profile="ANALYTICS",
        compartment="ocid1.compartment.oc1..analytics",
        crypto_endpoint="https://analytics.example.test",
        key_id="ocid1.key.oc1..analytics",
    )

    billing = AgentSafe(
        tmp_path / "missing-billing", config_path=global_config, application="billing"
    )
    analytics = AgentSafe(
        tmp_path / "missing-analytics", config_path=global_config, application="analytics"
    )
    assert billing.settings["profile"] == "BILLING"
    assert analytics.settings["profile"] == "ANALYTICS"
    assert "[application:billing]" in global_config.read_text()
    assert "[application:analytics]" in global_config.read_text()


def test_init_rejects_an_empty_application_name(tmp_path):
    with pytest.raises(ConfigError, match="application"):
        AgentSafe.init(
            config_path=tmp_path / "config",
            application="",
            profile="DEFAULT",
            compartment="ocid1.compartment.oc1..x",
            crypto_endpoint="https://example.test",
            key_id="ocid1.key.oc1..x",
        )

import pytest

from agentsafe.exceptions import ConfigError
from agentsafe.sdk import AgentSafe


def test_empty_name_is_rejected(tmp_path):
    safe = AgentSafe(tmp_path / "appconfig", kms_provider="fake")
    safe.store.initialize()
    with pytest.raises(ConfigError):
        safe.set("", "value")


def test_init_requires_all_oci_settings(tmp_path):
    with pytest.raises(ConfigError, match="key_id"):
        AgentSafe.init(
            tmp_path / "appconfig",
            config_path=tmp_path / "config",
            profile="DEFAULT",
            compartment="ocid",
            crypto_endpoint="https://example.test",
        )

from typer.testing import CliRunner

from agentsafe.cli import app
from agentsafe.config import write_config


def test_cli_includes_command_aliases():
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("store", "retrieve", "rm", "env"):
        assert command in result.output


def test_init_reports_missing_oci_settings(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["init"])
    assert result.exit_code == 1
    assert "profile" in result.output


def test_config_displays_project_settings_without_contacting_kms(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    write_config(
        {
            "kms_provider": "oci",
            "profile": "DEFAULT",
            "crypto_endpoint": "https://crypto.example.test",
            "key_id": "ocid1.key.oc1..example",
        }
    )

    result = CliRunner().invoke(app, ["config"])

    assert result.exit_code == 0
    assert result.output.splitlines() == [
        "Configuration: .agentsafe/config",
        "crypto_endpoint=https://crypto.example.test",
        "key_id=ocid1.key.oc1..example",
        "kms_provider=oci",
        "profile=DEFAULT",
    ]


def test_config_reports_a_missing_project_configuration(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["config"])

    assert result.exit_code == 1
    assert "does not exist" in result.output


def test_list_never_gets_a_value(monkeypatch):
    class FakeSafe:
        def list_keys(self):
            return ["ONE", "TWO"]

        def get(self, _key):
            raise AssertionError("list must not decrypt")

    monkeypatch.setattr("agentsafe.cli._safe", lambda _path: FakeSafe())
    result = CliRunner().invoke(app, ["list"])
    assert result.exit_code == 0
    assert result.output.splitlines() == ["ONE", "TWO"]


def test_set_reads_value_from_piped_stdin_without_prompting(monkeypatch):
    captured = {}

    class FakeSafe:
        def set(self, key, value):
            captured["key"] = key
            captured["value"] = value

    monkeypatch.setattr("agentsafe.cli._safe", lambda _path: FakeSafe())
    result = CliRunner().invoke(app, ["set", "TOKEN"], input="piped-secret\n")

    assert result.exit_code == 0
    assert captured["key"] == "TOKEN"
    assert captured["value"] == "piped-secret"
    assert "Value:" not in result.output


def test_set_value_argument_still_takes_precedence_over_stdin(monkeypatch):
    captured = {}

    class FakeSafe:
        def set(self, key, value):
            captured["value"] = value

    monkeypatch.setattr("agentsafe.cli._safe", lambda _path: FakeSafe())
    result = CliRunner().invoke(app, ["set", "TOKEN", "argument-secret"], input="piped-secret\n")

    assert result.exit_code == 0
    assert captured["value"] == "argument-secret"


def test_env_list_never_gets_a_value(monkeypatch):
    monkeypatch.setattr("agentsafe.cli.env.list_keys", lambda _path: ["ONE", "TWO"])

    def _fail_get(*_args, **_kwargs):
        raise AssertionError("env list must not decrypt")

    monkeypatch.setattr("agentsafe.cli.env.get", _fail_get)

    result = CliRunner().invoke(app, ["env", "list"])
    assert result.exit_code == 0
    assert result.output.splitlines() == ["ONE", "TWO"]


def test_env_set_reads_value_from_piped_stdin(monkeypatch):
    captured = {}

    def fake_set(key, value, path):
        captured["key"] = key
        captured["value"] = value
        captured["path"] = path

    monkeypatch.setattr("agentsafe.cli.env.set", fake_set)
    result = CliRunner().invoke(app, ["env", "set", "TOKEN"], input="piped-secret\n")

    assert result.exit_code == 0
    assert captured["key"] == "TOKEN"
    assert captured["value"] == "piped-secret"


def test_env_get_prints_decrypted_value(monkeypatch):
    monkeypatch.setattr("agentsafe.cli.env.get", lambda key, path: f"value-for-{key}")
    result = CliRunner().invoke(app, ["env", "get", "TOKEN"])

    assert result.exit_code == 0
    assert result.output.strip() == "value-for-TOKEN"


def test_env_encrypt_forwards_source_and_dest(monkeypatch, tmp_path):
    captured = {}

    def fake_encrypt(source, dest):
        captured["source"] = source
        captured["dest"] = dest

    monkeypatch.setattr("agentsafe.cli.env.encrypt", fake_encrypt)
    source = tmp_path / ".env.agent"
    dest = tmp_path / ".env"
    result = CliRunner().invoke(
        app, ["env", "encrypt", "--source", str(source), "--dest", str(dest)]
    )

    assert result.exit_code == 0
    assert str(captured["source"]) == str(source)
    assert str(captured["dest"]) == str(dest)


def test_init_supports_instance_principal_without_a_profile(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        app,
        [
            "init",
            "--auth-type",
            "instance_principal",
            "--crypto-endpoint",
            "https://crypto.example.test",
            "--key-id",
            "ocid1.key.oc1..x",
        ],
    )

    assert result.exit_code == 0, result.output
    shown = CliRunner().invoke(app, ["config"])
    assert "auth_type=instance_principal" in shown.output
    assert "profile" not in shown.output


def test_init_rejects_an_unknown_auth_type(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        app,
        [
            "init",
            "--auth-type",
            "api_key",
            "--crypto-endpoint",
            "https://crypto.example.test",
            "--key-id",
            "ocid1.key.oc1..x",
        ],
    )

    assert result.exit_code == 1
    assert "profile, instance_principal, resource_principal" in result.output
    assert "Traceback" not in result.output

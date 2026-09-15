from typer.testing import CliRunner

from agentsafe.cli import app


def test_cli_includes_command_aliases():
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("store", "retrieve", "rm"):
        assert command in result.output


def test_init_requires_an_application_name():
    result = CliRunner().invoke(app, ["init"])
    assert result.exit_code == 2
    assert "--application" in result.output


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

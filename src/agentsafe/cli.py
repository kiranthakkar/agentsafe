"""Typer command-line interface for agentsafe."""

import sys
from pathlib import Path

import typer

from agentsafe import env
from agentsafe.config import CONFIG_PATH, read_config
from agentsafe.exceptions import AgentSafeError, ConfigError
from agentsafe.sdk import AgentSafe

app = typer.Typer(no_args_is_help=True, add_completion=False)
env_app = typer.Typer(no_args_is_help=True, add_completion=False)
app.add_typer(env_app, name="env")


def _safe(path: Path) -> AgentSafe:
    return AgentSafe(path)


def _handle(action: object) -> None:
    try:
        action()  # type: ignore[operator]
    except AgentSafeError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error


def _read_secret() -> str:
    """Read a value from stdin when it is piped, otherwise a hidden prompt.

    Reading piped stdin directly avoids relying on ``getpass``'s non-TTY
    fallback, which can print a warning and echo the value on some platforms.
    """
    if not sys.stdin.isatty():
        return sys.stdin.read().rstrip("\r\n")
    return str(typer.prompt("Value", hide_input=True))


@app.command()
def init(
    profile: str | None = typer.Option(None),
    crypto_endpoint: str | None = typer.Option(None, "--crypto-endpoint"),
    key_id: str | None = typer.Option(None, "--key-id"),
) -> None:
    """Create the project-local OCI configuration at .agentsafe/config."""
    _handle(
        lambda: AgentSafe.init(
            profile=profile,
            crypto_endpoint=crypto_endpoint,
            key_id=key_id,
        )
    )


@app.command(name="config")
def show_config(path: Path = typer.Option(CONFIG_PATH, "--path")) -> None:
    """Display the project KMS configuration without contacting KMS."""

    def action() -> None:
        settings = read_config(path)
        if not settings:
            raise ConfigError(f"agentsafe configuration does not exist at {path}")
        typer.echo(f"Configuration: {path}")
        for key in sorted(settings):
            typer.echo(f"{key}={settings[key]}")

    _handle(action)


@app.command()
def set(
    key: str,
    value: str | None = typer.Argument(None),
    path: Path = typer.Option(Path("appconfig"), "--path"),
) -> None:
    """Encrypt and store a value; omit VALUE to enter it through a hidden prompt.

    Passing VALUE as an argument exposes it via shell history and process
    listings (e.g. `ps`); prefer the hidden prompt or piping the value on
    stdin instead.
    """
    secret = value if value is not None else _read_secret()
    _handle(lambda: _safe(path).set(key, secret))


app.command(name="store")(set)


@app.command()
def get(key: str, path: Path = typer.Option(Path("appconfig"), "--path")) -> None:
    """Decrypt and print one value."""

    def action() -> None:
        typer.echo(_safe(path).get(key))

    _handle(action)


app.command(name="retrieve")(get)


@app.command(name="remove")
def remove(key: str, path: Path = typer.Option(Path("appconfig"), "--path")) -> None:
    """Remove one value."""
    _handle(lambda: _safe(path).remove(key))


app.command(name="rm")(remove)


@app.command(name="list")
def list_values(path: Path = typer.Option(Path("appconfig"), "--path")) -> None:
    """List names only; this command never decrypts values."""

    def action() -> None:
        for key in _safe(path).list_keys():
            typer.echo(key)

    _handle(action)


@env_app.command(name="encrypt")
def env_encrypt(
    source: Path = typer.Option(Path(".env.agent"), "--source"),
    dest: Path = typer.Option(Path(".env"), "--dest"),
) -> None:
    """Compile .env.agent into a fully-encrypted, git-committable .env."""
    _handle(lambda: env.encrypt(source, dest))


@env_app.command(name="set")
def env_set(
    key: str,
    value: str | None = typer.Argument(None),
    path: Path = typer.Option(Path(".env"), "--path"),
) -> None:
    """Encrypt and write one value directly into .env; omit VALUE for a hidden prompt."""
    secret = value if value is not None else _read_secret()
    _handle(lambda: env.set(key, secret, path))


@env_app.command(name="get")
def env_get(key: str, path: Path = typer.Option(Path(".env"), "--path")) -> None:
    """Decrypt and print one .env value."""

    def action() -> None:
        typer.echo(env.get(key, path))

    _handle(action)


@env_app.command(name="remove")
def env_remove(key: str, path: Path = typer.Option(Path(".env"), "--path")) -> None:
    """Remove one .env value."""
    _handle(lambda: env.remove(key, path))


@env_app.command(name="list")
def env_list(path: Path = typer.Option(Path(".env"), "--path")) -> None:
    """List .env names only; this command never decrypts values."""

    def action() -> None:
        for key in env.list_keys(path):
            typer.echo(key)

    _handle(action)

"""Typer command-line interface for agentsafe."""

from pathlib import Path

import typer

from agentsafe.exceptions import AgentSafeError
from agentsafe.sdk import AgentSafe

app = typer.Typer(no_args_is_help=True, add_completion=False)


def _safe(path: Path, **settings: str | None) -> AgentSafe:
    return AgentSafe(path, **settings)


def _handle(action: object) -> None:
    try:
        action()  # type: ignore[operator]
    except AgentSafeError as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error


@app.command()
def init(
    profile: str | None = typer.Option(None),
    compartment: str | None = typer.Option(None),
    crypto_endpoint: str | None = typer.Option(None, "--crypto-endpoint"),
    key_id: str | None = typer.Option(None, "--key-id"),
    path: Path = typer.Option(Path("appconfig"), "--path"),
) -> None:
    """Create global OCI settings and an empty appconfig without overwriting either."""
    _handle(
        lambda: AgentSafe.init(
            path,
            profile=profile,
            compartment=compartment,
            crypto_endpoint=crypto_endpoint,
            key_id=key_id,
        )
    )


@app.command()
def set(
    key: str,
    value: str | None = typer.Argument(None),
    path: Path = typer.Option(Path("appconfig"), "--path"),
) -> None:
    """Encrypt and store a value; omit VALUE to enter it through a hidden prompt."""
    secret = value if value is not None else typer.prompt("Value", hide_input=True)
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

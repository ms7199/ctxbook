"""ctxbook command-line interface."""

import typer

from ctxbook import __version__

app = typer.Typer(
    name="ctxbook",
    help="Local-first shared memory for MCP clients.",
    no_args_is_help=True,
)


def _show_version(value: bool) -> None:
    if value:
        typer.echo(f"ctxbook {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_show_version,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """Local-first shared memory for MCP clients."""

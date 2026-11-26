"""ctxbook command-line interface."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from ctxbook import __version__
from ctxbook.cli.runtime import LOCAL_HOSTS, Runtime, configure_logging, open_runtime
from ctxbook.errors import CtxbookError

app = typer.Typer(
    name="ctxbook",
    help="Local-first shared memory for MCP clients.",
    no_args_is_help=True,
)

NoEmbeddings = Annotated[
    bool,
    typer.Option("--no-embeddings", help="Keyword search only: no embedding model, no download."),
]


class Transport(StrEnum):
    STDIO = "stdio"
    HTTP = "http"


def _fail(message: str) -> typer.Exit:
    typer.secho(f"Error: {message}", fg=typer.colors.RED, err=True)
    return typer.Exit(code=1)


@contextmanager
def _runtime(*, no_embeddings: bool) -> Iterator[Runtime]:
    """Open the store and service; turn ctxbook errors into a clean message and exit code 1."""
    try:
        runtime = open_runtime(no_embeddings=no_embeddings)
    except CtxbookError as exc:
        raise _fail(str(exc)) from exc
    try:
        yield runtime
    except CtxbookError as exc:
        raise _fail(str(exc)) from exc
    finally:
        runtime.close()


def _show_version(value: bool) -> None:
    if value:
        typer.echo(f"ctxbook {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version", callback=_show_version, is_eager=True, help="Show the version and exit."
        ),
    ] = False,
) -> None:
    """Local-first shared memory for MCP clients."""
    configure_logging()


@app.command()
def serve(
    transport: Annotated[Transport, typer.Option(help="stdio (default) or http.")] = (
        Transport.STDIO
    ),
    host: Annotated[str, typer.Option(help="HTTP only. Must be a localhost address.")] = (
        "127.0.0.1"
    ),
    port: Annotated[int, typer.Option(help="HTTP only.")] = 8000,
    no_embeddings: NoEmbeddings = False,
) -> None:
    """Run the MCP server (AI clients start this for you)."""
    from ctxbook.server.app import build_server

    if transport is Transport.HTTP and host not in LOCAL_HOSTS:
        raise _fail(
            f"refusing to listen on {host!r}. Network mode needs auth, planned for v0.2; "
            "in v0.1 ctxbook serves HTTP on 127.0.0.1 (localhost) only."
        )
    with _runtime(no_embeddings=no_embeddings) as runtime:
        server = build_server(runtime.service)
        if transport is Transport.HTTP:
            typer.echo(f"ctxbook: serving MCP on http://{host}:{port}/mcp", err=True)
            server.run(transport="streamable-http", host=host, port=port)
        else:
            server.run()


@app.command()
def save(
    text: Annotated[str, typer.Argument(help="One short fact to remember.")],
    scope: Annotated[str, typer.Option("--scope", "-s", help='Project folder name, or "global".')],
    no_embeddings: NoEmbeddings = False,
) -> None:
    """Save a fact by hand."""
    with _runtime(no_embeddings=no_embeddings) as runtime:
        result = runtime.service.save(text, scope, "cli")
    if result.status == "needs_resolution":
        typer.echo(f"Saved as pending memory {result.memory_id}: it may conflict with:")
        for candidate in result.candidates:
            typer.echo(f"  [{candidate.id}] {candidate.fact}")
        typer.echo(
            "Your AI client will be asked to resolve it; if nobody does, it is accepted "
            "automatically after 7 days."
        )
    elif result.status == "duplicate":
        typer.echo(f"Already stored as memory {result.memory_id}.")
    else:
        typer.echo(f"Saved as memory {result.memory_id}.")


@app.command("export")
def export_(
    path: Annotated[str, typer.Argument(help="File to write, or - for standard output.")] = "-",
) -> None:
    """Export every memory and its history as JSON Lines (a backup you can import)."""
    from ctxbook.core.transfer import export_lines

    with _runtime(no_embeddings=True) as runtime:
        lines = list(export_lines(runtime.store))
    text = "\n".join(lines) + "\n"
    if path == "-":
        typer.echo(text, nl=False)
    else:
        Path(path).write_text(text, encoding="utf-8")
        typer.echo(f"Exported {len(lines) - 1} memories to {path}.", err=True)


@app.command()
def doctor() -> None:
    """Check storage, vector search, embeddings and pending facts (changes nothing)."""
    from ctxbook.cli.doctor import run_checks

    marks = {
        "ok": ("✓", typer.colors.GREEN),
        "warn": ("!", typer.colors.YELLOW),
        "info": ("·", None),
    }
    for check in run_checks():
        mark, color = marks[check.level]
        typer.secho(f" {mark} ", fg=color, nl=False)
        typer.echo(f"{check.name}: {check.detail}")


@app.command("import")
def import_(
    path: Annotated[
        Path, typer.Argument(exists=True, dir_okay=False, help="A ctxbook export file.")
    ],
) -> None:
    """Import memories from an export. Running it twice adds nothing the second time."""
    from ctxbook.core.transfer import import_lines

    with _runtime(no_embeddings=True) as runtime, path.open(encoding="utf-8") as handle:
        report = import_lines(runtime.store, handle, now=datetime.now(UTC))
    typer.echo(f"Imported {report.imported} memories ({report.skipped} already present).")

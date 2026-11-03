"""CLI do Juris BR MCP."""

from __future__ import annotations

import typer

app = typer.Typer(
    name="juris-br",
    help="Juris BR MCP - acompanhamento de processos via DataJud CNJ.",
    add_completion=False,
)


@app.command()
def serve() -> None:
    """Inicia o servidor MCP em modo stdio."""
    from juris_br_mcp.server import main

    main()


@app.command()
def version() -> None:
    """Exibe a versao instalada."""
    from juris_br_mcp import __version__

    typer.echo(f"juris-br-mcp {__version__}")


@app.command()
def tribunais() -> None:
    """Lista os tribunais suportados."""
    from juris_br_mcp.datajud.tribunais import listar_tribunais

    for t in listar_tribunais():
        typer.echo(t)


def main() -> None:
    app()


if __name__ == "__main__":
    main()

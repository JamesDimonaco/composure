"""
CLI module - command-line interface using Typer.
"""

# Suppress LibreSSL warning on macOS (harmless, just noisy)
import warnings
warnings.filterwarnings("ignore", message=".*LibreSSL.*")

import typer
from typing import Optional

from composure import __version__
from composure.app import ComposureApp
from composure.scanner import find_compose_files

# Create the Typer app
app = typer.Typer(
    name="composure",
    help="Docker-Compose optimizer and TUI dashboard.",
    add_completion=False,
)


@app.command()
def main(
    path: Optional[str] = typer.Argument(
        None,
        help="Path to scan for docker-compose files (default: current directory)",
    ),
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show version and exit",
    ),
    scan_only: bool = typer.Option(
        False,
        "--scan",
        "-s",
        help="Just scan for compose files, don't launch TUI",
    ),
):
    """
    Launch the Composure TUI dashboard.

    Scans for docker-compose files and monitors container resources.
    """
    # Handle --version flag
    if version:
        typer.echo(f"composure {__version__}")
        raise typer.Exit()

    # Default to current directory
    directory = path or "."

    # If scan-only mode, just list files and exit
    if scan_only:
        files = find_compose_files(directory)
        if files:
            typer.echo(f"Found {len(files)} compose file(s):")
            for f in files:
                typer.echo(f"  - {f}")
        else:
            typer.echo("No docker-compose files found.")
        raise typer.Exit()

    # Launch the TUI
    tui = ComposureApp()
    tui.run()


if __name__ == "__main__":
    app()

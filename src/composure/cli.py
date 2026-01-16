"""
CLI module - command-line interface using Typer.
"""

# Suppress LibreSSL warning on macOS (harmless, just noisy)
import warnings
warnings.filterwarnings("ignore", message=".*LibreSSL.*")

import typer
from typing import Optional
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from composure import __version__
from composure.app import ComposureApp
from composure.scanner import find_compose_files
from composure.puller import find_compose_and_images, pull_images_with_progress, format_bytes
from composure.analyzer import get_docker_client

# Create the Typer app
app = typer.Typer(
    name="composure",
    help="Docker-Compose optimizer and TUI dashboard.",
    add_completion=False,
    invoke_without_command=True,
)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
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
    Docker-Compose optimizer and TUI dashboard.

    Run without arguments to launch the TUI.
    """
    # Handle --version flag
    if version:
        typer.echo(f"composure {__version__}")
        raise typer.Exit()

    # If a subcommand was invoked, let it run
    if ctx.invoked_subcommand is not None:
        return

    # If scan-only mode, just list files and exit
    if scan_only:
        files = find_compose_files(".")
        if files:
            typer.echo(f"Found {len(files)} compose file(s):")
            for f in files:
                typer.echo(f"  - {f}")
        else:
            typer.echo("No docker-compose files found.")
        raise typer.Exit()

    # Default: Launch the TUI
    tui = ComposureApp()
    tui.run()


@app.command()
def pull(
    path: Optional[str] = typer.Argument(
        None,
        help="Path to docker-compose file directory (default: current directory)",
    ),
):
    """
    Pull all images from docker-compose.yml with progress tracking.

    Shows a single overall progress percentage across all images.
    """
    console = Console()

    # Find compose file and images
    directory = path or "."
    compose_path, images = find_compose_and_images(directory)

    if not compose_path:
        console.print("[red]No docker-compose.yml found[/red]")
        raise typer.Exit(1)

    if not images:
        console.print("[yellow]No images found in compose file (all services use build?)[/yellow]")
        raise typer.Exit(1)

    console.print(f"[bold]Pulling {len(images)} images from {compose_path.name}[/bold]\n")

    try:
        client = get_docker_client()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TextColumn("{task.fields[status]}"),
            console=console,
        ) as progress:
            # Create overall task
            overall_task = progress.add_task(
                "Overall",
                total=100,
                status=""
            )

            # Create task for each image
            image_tasks = {}
            for img in images:
                image_tasks[img] = progress.add_task(
                    f"  {img}",
                    total=100,
                    status="[dim]waiting[/dim]"
                )

            last_progress = None
            first_real_update = False

            for pull_progress in pull_images_with_progress(client, images):
                last_progress = pull_progress

                # Check if we have real progress data yet
                has_real_data = pull_progress.total_bytes > 0

                if has_real_data and not first_real_update:
                    first_real_update = True

                # Update overall progress
                if has_real_data:
                    progress.update(
                        overall_task,
                        completed=pull_progress.percent,
                        status=f"[dim]{format_bytes(pull_progress.downloaded_bytes)} / {format_bytes(pull_progress.total_bytes)}[/dim]"
                    )
                else:
                    progress.update(
                        overall_task,
                        completed=0,
                        status="[dim]discovering layers...[/dim]"
                    )

                # Update individual image tasks
                for img_name, img_prog in pull_progress.images.items():
                    if img_name in image_tasks:
                        if img_prog.status == "complete":
                            progress.update(image_tasks[img_name], completed=100, status="[green]done[/green]")
                        elif img_prog.status == "pulling":
                            img_total = sum(l.total for l in img_prog.layers.values())
                            if img_total > 0:
                                img_bytes = sum(l.current for l in img_prog.layers.values())
                                img_percent = (img_bytes / img_total) * 100
                                progress.update(image_tasks[img_name], completed=img_percent, status="[yellow]pulling[/yellow]")
                            else:
                                progress.update(image_tasks[img_name], completed=0, status="[dim]starting[/dim]")
                        elif img_prog.status == "error":
                            progress.update(image_tasks[img_name], completed=0, status="[red]error[/red]")

        # Final summary
        if last_progress:
            console.print(f"\n[green]Successfully pulled {last_progress.images_complete}/{last_progress.images_total} images[/green]")

    except Exception as e:
        console.print(f"\n[red]Pull failed: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()

"""
App module - the main Textual TUI application.
"""

import re
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, DataTable, Static, Tree
from textual.widgets.tree import TreeNode
from textual.binding import Binding
from textual.worker import Worker, WorkerState

from composure.analyzer import (
    get_docker_client,
    get_container_stats,
    get_network_map,
    stop_container,
    start_container,
    restart_container,
    get_container_logs,
)
from composure.puller import (
    find_compose_and_images,
    pull_images_with_progress,
    format_bytes,
    PullProgress,
)

# Regex to strip ANSI escape codes from log output
ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;]*m')


class DetailPanel(Static):
    """Panel showing details about the selected container."""

    def __init__(self):
        super().__init__("Select a container to see details...", id="detail-panel")


class ComposureApp(App):
    """Main TUI application for Composure."""

    TITLE = "COMPOSURE // Docker Optimizer"

    # Textual CSS for styling
    CSS = """
    /* Main table takes most of the space */
    DataTable {
        height: 2fr;
        margin: 1;
        border: round $accent;
    }

    /* Detail panel at the bottom */
    #detail-panel {
        height: auto;
        max-height: 15;
        margin: 0 1 1 1;
        padding: 1;
        border: round $secondary;
        background: $surface;
    }

    #status-bar {
        dock: top;
        padding: 1;
        background: $surface;
    }

    /* Tree view styling */
    Tree {
        height: 2fr;
        margin: 1;
        border: round $accent;
    }
    """

    # Keyboard shortcuts
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("n", "toggle_network_view", "Networks"),
        Binding("s", "stop_selected", "Stop"),
        Binding("a", "start_selected", "Start"),
        Binding("x", "restart_selected", "Restart"),
        Binding("l", "show_logs", "Logs"),
        Binding("p", "pull_images", "Pull"),
        Binding("?", "help_screen", "Help"),
    ]

    # Track state
    current_view = "stats"
    container_data = []  # Store fetched container data

    def compose(self) -> ComposeResult:
        """Build the UI layout."""
        yield Header(show_clock=True)
        yield Static("Scanning Docker containers...", id="status-bar")
        yield DataTable()
        yield DetailPanel()
        yield Footer()

    def on_mount(self) -> None:
        """Called when app starts - set up the table."""
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.add_columns(
            "Container",
            "Status",
            "CPU %",
            "CPU Limit",
            "RAM Used",
            "RAM Limit",
            "Efficiency",
            "Waste",
        )
        self.refresh_stats()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Called when user selects a row - show details."""
        if self.current_view != "stats":
            return

        row_index = event.cursor_row
        if row_index < len(self.container_data):
            container = self.container_data[row_index]
            self.show_container_details(container)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Called when user moves cursor - update details."""
        if self.current_view != "stats":
            return

        row_index = event.cursor_row
        if row_index < len(self.container_data):
            container = self.container_data[row_index]
            self.show_container_details(container)

    def show_container_details(self, container) -> None:
        """Update the detail panel with container info and logs."""
        panel = self.query_one("#detail-panel", Static)

        # Get latest logs
        try:
            client = get_docker_client()
            success, logs = get_container_logs(client, container.name, tail=10)
            if success and logs.strip():
                log_lines = logs.strip().split('\n')[-8:]  # Last 8 lines
                # Strip ANSI escape codes from logs to avoid markup conflicts
                clean_lines = [ANSI_ESCAPE.sub('', line) for line in log_lines]
                formatted_logs = '\n'.join(f"  [dim]{line}[/dim]" for line in clean_lines)
            else:
                formatted_logs = "  [dim](no logs)[/dim]"
        except Exception:
            formatted_logs = "  [dim](unable to fetch logs)[/dim]"

        # Format the detail view with easy-to-copy IDs
        detail_text = (
            f"[bold]{container.name}[/bold]  "
            f"{self.format_status(container.status)}  "
            f"[dim]Networks: {', '.join(container.networks) if container.networks else 'none'}[/dim]\n"
            f"[bold]ID:[/bold] [cyan]{container.container_id}[/cyan]  "
            f"[dim]Full:[/dim] [cyan]{container.full_id[:20]}...[/cyan]\n"
            f"[bold]Logs:[/bold]\n{formatted_logs}"
        )

        panel.update(detail_text)

    def refresh_stats(self) -> None:
        """Fetch fresh stats from Docker and update the table."""
        try:
            client = get_docker_client()
            self.container_data = get_container_stats(client)
        except Exception as e:
            status = self.query_one("#status-bar", Static)
            status.update(f"Error connecting to Docker: {e}")
            return

        table = self.query_one(DataTable)
        table.clear()

        for container in self.container_data:
            # Color-code the waste score
            if container.waste_score >= 60:
                waste_display = f"[red]{container.waste_score}[/red]"
            elif container.waste_score >= 30:
                waste_display = f"[yellow]{container.waste_score}[/yellow]"
            else:
                waste_display = f"[green]{container.waste_score}[/green]"

            table.add_row(
                container.name[:30],
                self.format_status(container.status),
                f"{container.cpu_percent:.1f}%",
                self.format_cpu_limit(container.cpu_limit, container.has_cpu_limit),
                f"{container.memory_usage_mb:.0f} MB",
                self.format_memory_limit(container.memory_limit_mb, container.has_memory_limit),
                container.efficiency,
                waste_display,
            )

        status = self.query_one("#status-bar", Static)
        status.update(f"Monitoring {len(self.container_data)} container(s) | ↑↓ Select | 'n' Networks | 'r' Refresh")

        # Update detail panel with first container if available
        if self.container_data:
            self.show_container_details(self.container_data[0])

    def action_refresh(self) -> None:
        """Handle 'r' keypress - refresh current view or return from logs/pull."""
        if self.current_view == "logs":
            self.restore_from_logs()
        elif self.current_view == "pull":
            self.restore_from_pull()
        elif self.current_view == "networks":
            self.refresh_networks()
        else:
            self.refresh_stats()

    def action_optimize(self) -> None:
        """Handle 'o' keypress."""
        status = self.query_one("#status-bar", Static)
        status.update("Optimization coming soon...")

    def action_help_screen(self) -> None:
        """Handle '?' keypress."""
        status = self.query_one("#status-bar", Static)
        status.update("s=Stop | a=Start | x=Restart | l=Logs | p=Pull | n=Networks | r=Refresh | q=Quit")

    def get_selected_container(self):
        """Get the currently selected container, if any."""
        if self.current_view != "stats" or not self.container_data:
            return None
        table = self.query_one(DataTable)
        row_index = table.cursor_row
        if row_index < len(self.container_data):
            return self.container_data[row_index]
        return None

    def action_stop_selected(self) -> None:
        """Stop the selected container (runs in background)."""
        container = self.get_selected_container()
        if not container:
            self.show_message("[yellow]Select a container first[/yellow]")
            return

        self.show_message(f"[yellow]Stopping {container.name}...[/yellow]")

        # Run in background worker so UI doesn't freeze
        def do_stop():
            client = get_docker_client()
            return stop_container(client, container.name)

        self.run_worker(do_stop, name="stop", thread=True)

    def action_start_selected(self) -> None:
        """Start the selected container (runs in background)."""
        container = self.get_selected_container()
        if not container:
            self.show_message("[yellow]Select a container first[/yellow]")
            return

        self.show_message(f"[yellow]Starting {container.name}...[/yellow]")

        def do_start():
            client = get_docker_client()
            return start_container(client, container.name)

        self.run_worker(do_start, name="start", thread=True)

    def action_restart_selected(self) -> None:
        """Restart the selected container (runs in background)."""
        container = self.get_selected_container()
        if not container:
            self.show_message("[yellow]Select a container first[/yellow]")
            return

        self.show_message(f"[yellow]Restarting {container.name}...[/yellow]")

        def do_restart():
            client = get_docker_client()
            return restart_container(client, container.name)

        self.run_worker(do_restart, name="restart", thread=True)

    def on_worker_state_changed(self, event) -> None:
        """Called when a background worker finishes."""
        if event.state.name == "SUCCESS":
            result = event.worker.result
            if result:
                success, message = result
                if success:
                    self.show_message(f"[green]{message}[/green]")
                else:
                    self.show_message(f"[red]{message}[/red]")
                # Refresh the list to show updated status
                self.refresh_stats()

    def action_show_logs(self) -> None:
        """Show extended logs for the selected container (fullscreen, live)."""
        container = self.get_selected_container()
        if not container:
            self.show_message("[yellow]Select a container first[/yellow]")
            return

        # Hide the table and status bar completely
        table = self.query_one(DataTable)
        table.display = False
        status = self.query_one("#status-bar", Static)
        status.display = False

        # Expand the panel to full size
        panel = self.query_one("#detail-panel", Static)
        panel.styles.max_height = "100%"
        panel.styles.height = "1fr"
        panel.styles.width = "100%"
        panel.styles.margin = (0, 1, 1, 1)

        self.current_view = "logs"
        self._logs_container = container

        # Show initial logs
        self._refresh_logs()

        # Start live log refresh (every 2 seconds)
        self._log_timer = self.set_interval(2, self._refresh_logs)

        # Force full screen refresh
        self.refresh()

    def _refresh_logs(self) -> None:
        """Refresh the logs display."""
        if self.current_view != "logs" or not hasattr(self, '_logs_container'):
            return

        container = self._logs_container
        panel = self.query_one("#detail-panel", Static)

        try:
            client = get_docker_client()
            success, logs = get_container_logs(client, container.name, tail=200)

            if success:
                log_lines = logs.strip().split('\n')[-50:]
                # Strip ANSI escape codes from logs to avoid markup conflicts
                clean_lines = [ANSI_ESCAPE.sub('', line) for line in log_lines]
                formatted_logs = '\n'.join(clean_lines)
                panel.update(
                    f"[bold]Logs for {container.name}[/bold] [dim](ID: {container.container_id})[/dim]  "
                    f"[green]LIVE[/green]  [yellow]Press 'r' to return[/yellow]\n\n"
                    f"[dim]{formatted_logs}[/dim]"
                )
            else:
                panel.update(f"[red]{logs}[/red]")
        except Exception as e:
            panel.update(f"[red]Error fetching logs: {e}[/red]")

    def restore_from_logs(self) -> None:
        """Restore the normal view after viewing logs."""
        if self.current_view != "logs":
            return

        # Stop the live refresh timer
        if hasattr(self, '_log_timer'):
            self._log_timer.stop()

        # Show the table and status bar again
        table = self.query_one(DataTable)
        table.display = True
        status = self.query_one("#status-bar", Static)
        status.display = True

        # Restore panel size
        panel = self.query_one("#detail-panel", Static)
        panel.styles.max_height = "15"
        panel.styles.height = "auto"
        panel.styles.width = "auto"
        panel.styles.margin = (0, 1, 1, 1)

        self.current_view = "stats"

        # Refresh to restore normal view
        if hasattr(self, '_logs_container'):
            self.show_container_details(self._logs_container)

        # Force full screen refresh
        self.refresh()

    def action_pull_images(self) -> None:
        """Pull all images from docker-compose.yml with progress tracking."""
        # Find compose file and images
        compose_path, images = find_compose_and_images()

        if not compose_path:
            self.show_message("[red]No docker-compose.yml found in current directory[/red]")
            return

        if not images:
            self.show_message("[yellow]No images found in compose file (all services use build?)[/yellow]")
            return

        # Hide the table and status bar
        table = self.query_one(DataTable)
        table.display = False
        status = self.query_one("#status-bar", Static)
        status.display = False

        # Expand the panel to full size
        panel = self.query_one("#detail-panel", Static)
        panel.styles.max_height = "100%"
        panel.styles.height = "1fr"
        panel.styles.width = "100%"
        panel.styles.margin = (0, 1, 1, 1)

        self.current_view = "pull"
        self._pull_images = images
        self._pull_compose_path = compose_path

        # Show initial state
        panel.update(
            f"[bold]Pulling {len(images)} images from {compose_path.name}[/bold]\n\n"
            f"[dim]Starting...[/dim]\n\n"
            f"[yellow]Press 'r' to cancel and return[/yellow]"
        )

        self.refresh()

        # Start pull in background thread
        self.run_worker(self._do_pull_images, name="pull_worker", thread=True)

    def _do_pull_images(self) -> None:
        """Background worker to pull images (runs in thread)."""
        try:
            client = get_docker_client()
            images = self._pull_images

            for progress in pull_images_with_progress(client, images):
                if self.current_view != "pull":
                    # User cancelled
                    return

                # Update UI from thread safely
                self.call_from_thread(self._update_pull_display, progress)

            # Final update
            self.call_from_thread(self._update_pull_display, progress, True)

        except Exception as e:
            self.call_from_thread(self._show_pull_error, str(e))

    def _show_pull_error(self, error: str) -> None:
        """Show pull error (called from main thread)."""
        panel = self.query_one("#detail-panel", Static)
        # Escape brackets in error message to avoid Rich markup conflicts
        safe_error = error.replace("[", "\\[").replace("]", "\\]")
        panel.update(f"[red]Pull failed: {safe_error}[/red]\n\n[yellow]Press 'r' to return[/yellow]")

    def _update_pull_display(self, progress: PullProgress, complete: bool = False) -> None:
        """Update the pull progress display."""
        if self.current_view != "pull":
            return

        panel = self.query_one("#detail-panel", Static)

        # Build progress bar
        percent = progress.percent
        bar_width = 40
        filled = int(bar_width * percent / 100)
        bar = "[green]" + "#" * filled + "[/green]" + "[dim]" + "-" * (bar_width - filled) + "[/dim]"

        # Build image status lines
        image_lines = []
        for img_name, img_prog in progress.images.items():
            if img_prog.status == "complete":
                status_icon = "[green]OK[/green]"
            elif img_prog.status == "pulling":
                status_icon = "[yellow]...[/yellow]"
            elif img_prog.status == "error":
                status_icon = "[red]ERR[/red]"
            else:
                status_icon = "[dim]---[/dim]"

            image_lines.append(f"  {status_icon} {img_name}")

        images_text = "\n".join(image_lines)

        # Format bytes
        downloaded = format_bytes(progress.downloaded_bytes)
        total = format_bytes(progress.total_bytes)

        if complete:
            header = f"[bold green]Pull Complete![/bold green]"
            footer = f"\n[green]Successfully pulled {progress.images_complete}/{progress.images_total} images[/green]\n\n[yellow]Press 'r' to return[/yellow]"
        else:
            header = f"[bold]Pulling {progress.images_total} images...[/bold]"
            footer = f"\n[yellow]Press 'r' to cancel and return[/yellow]"

        panel.update(
            f"{header}\n\n"
            f"  \\[{bar}\\]  {percent:.0f}%\n"
            f"  {downloaded} / {total}  |  "
            f"Layers: {progress.completed_layers}/{progress.total_layers}  |  "
            f"Images: {progress.images_complete}/{progress.images_total}\n\n"
            f"{images_text}"
            f"{footer}"
        )

    def restore_from_pull(self) -> None:
        """Restore the normal view after pull."""
        if self.current_view != "pull":
            return

        # Show the table and status bar again
        table = self.query_one(DataTable)
        table.display = True
        status = self.query_one("#status-bar", Static)
        status.display = True

        # Restore panel size
        panel = self.query_one("#detail-panel", Static)
        panel.styles.max_height = "15"
        panel.styles.height = "auto"
        panel.styles.width = "auto"
        panel.styles.margin = (0, 1, 1, 1)

        self.current_view = "stats"

        # Refresh stats to show any new containers
        self.refresh_stats()
        self.refresh()

    def show_message(self, message: str) -> None:
        """Show a message in the status bar."""
        status = self.query_one("#status-bar", Static)
        status.update(message)

    def action_toggle_network_view(self) -> None:
        """Toggle between stats view and network tree view."""
        if self.current_view == "stats":
            self.show_network_view()
        else:
            self.show_stats_view()

    def show_stats_view(self) -> None:
        """Switch to the container stats view."""
        self.current_view = "stats"

        # Remove tree if it exists
        try:
            tree = self.query_one(Tree)
            tree.remove()
        except Exception:
            pass

        # Show table and detail panel
        table = self.query_one(DataTable)
        table.display = True
        table.clear(columns=True)
        table.add_columns(
            "Container",
            "Status",
            "CPU %",
            "CPU Limit",
            "RAM Used",
            "RAM Limit",
            "Efficiency",
            "Waste",
        )

        panel = self.query_one("#detail-panel", Static)
        panel.display = True

        self.refresh_stats()

    def show_network_view(self) -> None:
        """Switch to the network tree view."""
        self.current_view = "networks"

        # Hide table and detail panel
        table = self.query_one(DataTable)
        table.display = False

        panel = self.query_one("#detail-panel", Static)
        panel.display = False

        # Create and mount a tree widget
        tree = Tree("Docker Networks", id="network-tree")
        tree.root.expand()

        # Mount after the status bar
        self.mount(tree, after=self.query_one("#status-bar"))

        self.refresh_networks()

    def refresh_networks(self) -> None:
        """Fetch network info and build the tree."""
        try:
            tree = self.query_one(Tree)
        except Exception:
            return

        try:
            client = get_docker_client()
            network_map = get_network_map(client)
        except Exception as e:
            status = self.query_one("#status-bar", Static)
            status.update(f"Error: {e}")
            return

        # Clear and rebuild tree
        tree.root.remove_children()

        # Group networks by type
        system_nets = []
        compose_nets = []
        custom_nets = []

        for net_name, containers in sorted(network_map.items()):
            if net_name in ('bridge', 'none', 'host'):
                system_nets.append((net_name, containers))
            elif net_name.startswith("comp-") or net_name.startswith("test-stack"):
                compose_nets.append((net_name, containers))
            else:
                custom_nets.append((net_name, containers))

        # Helper to format network node
        def format_network(name: str, containers: list, color: str) -> str:
            count = len(containers)
            if count == 0:
                return f"[dim]{name}[/dim] [dim](empty)[/dim]"
            elif count == 1:
                return f"[{color}]{name}[/{color}] [cyan](1 container)[/cyan]"
            else:
                return f"[{color}]{name}[/{color}] [green]({count} containers)[/green]"

        # Helper to format container
        def format_container(name: str) -> str:
            # Highlight by type
            if "db" in name.lower() or "postgres" in name.lower():
                return f"[magenta]{name}[/magenta]"
            elif "cache" in name.lower() or "redis" in name.lower():
                return f"[red]{name}[/red]"
            elif "web" in name.lower() or "nginx" in name.lower() or "load" in name.lower():
                return f"[cyan]{name}[/cyan]"
            elif "api" in name.lower() or "worker" in name.lower():
                return f"[yellow]{name}[/yellow]"
            else:
                return f"[white]{name}[/white]"

        # Add compose networks (most relevant)
        if compose_nets:
            compose_node = tree.root.add("[bold cyan]Compose Networks[/bold cyan]", expand=True)
            for net_name, containers in compose_nets:
                net_node = compose_node.add(format_network(net_name, containers, "bold cyan"), expand=True)
                for container in containers:
                    net_node.add_leaf(format_container(container))

        # Add custom networks
        if custom_nets:
            custom_node = tree.root.add("[bold green]Custom Networks[/bold green]", expand=True)
            for net_name, containers in custom_nets:
                net_node = custom_node.add(format_network(net_name, containers, "bold green"), expand=True)
                for container in containers:
                    net_node.add_leaf(format_container(container))

        # Add system networks (collapsed by default)
        if system_nets:
            system_node = tree.root.add("[dim]System Networks[/dim]", expand=False)
            for net_name, containers in system_nets:
                net_node = system_node.add(format_network(net_name, containers, "dim"), expand=False)
                for container in containers:
                    net_node.add_leaf(format_container(container))

        # Calculate summary stats
        total_containers = sum(len(c) for c in network_map.values())

        status = self.query_one("#status-bar", Static)
        status.update(
            f"[bold]Networks:[/bold] {len(network_map)} | "
            f"[bold]Connections:[/bold] {total_containers} | "
            f"Press 'n' for stats"
        )

    def format_cpu_limit(self, cpu_limit: float, has_limit: bool) -> str:
        """Format CPU limit in a human-readable way."""
        if not has_limit:
            return "[yellow]No limit[/yellow]"
        if cpu_limit >= 1:
            cores = int(cpu_limit)
            return f"{cores} core" if cores == 1 else f"{cores} cores"
        else:
            percent = int(cpu_limit * 100)
            return f"{percent}%"

    def format_memory_limit(self, memory_limit: float, has_limit: bool) -> str:
        """Format memory limit in a human-readable way."""
        if not has_limit:
            return "[yellow]No limit[/yellow]"
        return f"{memory_limit:.0f} MB"

    def format_status(self, status: str) -> str:
        """Format container status with color coding."""
        status_colors = {
            "running": "[green]running[/green]",
            "exited": "[red]exited[/red]",
            "paused": "[yellow]paused[/yellow]",
            "restarting": "[cyan]restarting[/cyan]",
            "dead": "[red]dead[/red]",
            "created": "[dim]created[/dim]",
        }
        return status_colors.get(status, f"[dim]{status}[/dim]")

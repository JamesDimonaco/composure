"""
Analyzer module - compares container stats vs YAML limits.
"""

import docker
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, List, Dict


@dataclass
class ContainerStats:
    """Holds stats for a single container."""

    name: str
    container_id: str  # Short ID for display
    cpu_percent: float
    cpu_limit: float
    has_cpu_limit: bool
    memory_usage_mb: float
    memory_limit_mb: float
    has_memory_limit: bool
    efficiency: str
    waste_score: int  # 0-100, higher = more wasteful
    networks: List[str]  # List of network names this container is connected to
    status: str  # running, paused, etc.


def get_docker_client():
    """Connect to the local Docker daemon."""
    return docker.from_env()


# =============================================================================
# CONTAINER CONTROLS
# =============================================================================

def stop_container(client, container_name: str) -> tuple[bool, str]:
    """
    Stop a running container.

    Returns: (success, message)
    """
    try:
        container = client.containers.get(container_name)
        if container.status != "running":
            return False, f"{container_name} is not running"
        container.stop(timeout=10)
        return True, f"Stopped {container_name}"
    except Exception as e:
        return False, f"Failed to stop: {e}"


def start_container(client, container_name: str) -> tuple[bool, str]:
    """
    Start a stopped container.

    Returns: (success, message)
    """
    try:
        container = client.containers.get(container_name)
        if container.status == "running":
            return False, f"{container_name} is already running"
        container.start()
        return True, f"Started {container_name}"
    except Exception as e:
        return False, f"Failed to start: {e}"


def restart_container(client, container_name: str) -> tuple[bool, str]:
    """
    Restart a container.

    Returns: (success, message)
    """
    try:
        container = client.containers.get(container_name)
        container.restart(timeout=10)
        return True, f"Restarted {container_name}"
    except Exception as e:
        return False, f"Failed to restart: {e}"


def get_container_logs(client, container_name: str, tail: int = 50) -> tuple[bool, str]:
    """
    Get recent logs from a container.

    Returns: (success, logs_or_error)
    """
    try:
        container = client.containers.get(container_name)
        logs = container.logs(tail=tail, timestamps=True).decode('utf-8')
        if not logs.strip():
            return True, "(no logs)"
        return True, logs
    except Exception as e:
        return False, f"Failed to get logs: {e}"


def get_container_stats(client) -> list[ContainerStats]:
    """
    Fetch live stats for ALL containers (running and stopped) IN PARALLEL.

    Instead of waiting 1 second per container (sequential),
    we fetch all stats simultaneously using threads.
    """
    # all=True gets stopped containers too
    containers = client.containers.list(all=True)

    # ThreadPoolExecutor runs multiple functions at the same time
    # max_workers=20 means up to 20 containers fetched simultaneously
    with ThreadPoolExecutor(max_workers=20) as executor:
        # executor.map() applies the function to every item in the list
        # It's like a parallel version of: [func(c) for c in containers]
        results = list(executor.map(get_single_container_stats, containers))

    # Filter out None values (containers that failed to fetch)
    return [r for r in results if r is not None]


def get_single_container_stats(container) -> Optional[ContainerStats]:
    """
    Fetch stats for ONE container.

    This function is called in parallel for each container.
    Returns None if something goes wrong (container stopped mid-fetch, etc.)
    """
    try:
        config = container.attrs['HostConfig']
        status = container.status  # 'running', 'exited', 'paused', etc.

        # Only fetch live stats if container is running
        # Stopped containers can't provide CPU/memory stats
        if status == "running":
            stats = container.stats(stream=False)

            # Calculate CPU percentage
            cpu_delta = (
                stats["cpu_stats"]["cpu_usage"]["total_usage"]
                - stats["precpu_stats"]["cpu_usage"]["total_usage"]
            )
            system_delta = (
                stats["cpu_stats"]["system_cpu_usage"]
                - stats["precpu_stats"]["system_cpu_usage"]
            )
            cpu_percent = (cpu_delta / system_delta) * 100 if system_delta > 0 else 0.0

            # Calculate memory
            mem_usage = stats["memory_stats"].get("usage", 0)
            mem_limit = stats["memory_stats"].get("limit", 1)
            mem_usage_mb = mem_usage / (1024 * 1024)
            mem_limit_mb = mem_limit / (1024 * 1024)

            # Calculate efficiency and waste
            efficiency, waste_score = calculate_efficiency(mem_usage, mem_limit)
        else:
            # Container not running - no live stats available
            cpu_percent = 0.0
            mem_usage_mb = 0.0
            mem_limit_mb = 0.0
            efficiency = "N/A"
            waste_score = 0

        # Check if limits were explicitly set
        has_memory_limit = config.get('Memory', 0) > 0
        has_cpu_limit = config.get('NanoCpus', 0) > 0
        cpu_limit = config.get('NanoCpus', 0) / 1e9 if has_cpu_limit else 0.0

        # Get network information
        network_settings = container.attrs.get('NetworkSettings', {})
        networks = list(network_settings.get('Networks', {}).keys())

        return ContainerStats(
            name=container.name,
            container_id=container.short_id,  # e.g., "a1b2c3d4"
            cpu_percent=cpu_percent,
            cpu_limit=cpu_limit,
            has_cpu_limit=has_cpu_limit,
            memory_usage_mb=mem_usage_mb,
            memory_limit_mb=mem_limit_mb,
            has_memory_limit=has_memory_limit,
            efficiency=efficiency,
            waste_score=waste_score,
            networks=networks,
            status=container.status,  # 'running', 'paused', 'exited', etc.
        )
    except Exception:
        # Container might have stopped while we were fetching
        return None


def get_network_map(client) -> Dict[str, List[str]]:
    """
    Build a map of networks to containers.

    Returns a dict like:
    {
        'frontend': ['nginx', 'webapp'],
        'backend': ['api', 'worker', 'db'],
        'bridge': ['random-container'],
    }
    """
    network_map = {}

    # Get all networks
    for network in client.networks.list():
        network_name = network.name

        # Skip default Docker networks that clutter the view
        if network_name in ('none', 'host'):
            continue

        # IMPORTANT: Reload to get fresh container data!
        # Without this, containers dict is often empty
        network.reload()

        # Get containers attached to this network
        # network.attrs['Containers'] is a dict of container IDs
        containers = network.attrs.get('Containers', {})
        container_names = []

        for container_id, container_info in containers.items():
            # container_info has 'Name' key
            name = container_info.get('Name', container_id[:12])
            container_names.append(name)

        network_map[network_name] = sorted(container_names)

    return network_map


def calculate_efficiency(usage: int, limit: int) -> tuple[str, int]:
    """
    Calculate efficiency rating and waste score.

    Args:
        usage: Actual memory usage in bytes
        limit: Memory limit in bytes

    Returns:
        Tuple of (efficiency_label, waste_score)
    """
    if limit == 0:
        return "UNKNOWN", 50

    ratio = usage / limit

    if ratio < 0.1:
        # Using less than 10% of allocation = very wasteful
        return "LOW", 90
    elif ratio < 0.3:
        return "MEDIUM-LOW", 60
    elif ratio < 0.5:
        return "MEDIUM", 40
    elif ratio < 0.7:
        return "GOOD", 20
    else:
        return "HIGH", 0

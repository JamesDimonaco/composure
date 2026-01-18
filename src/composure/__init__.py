"""
Composure - Docker-Compose Optimizer & TUI

A terminal tool to audit, optimize, and visualize Docker-Compose stacks.

Python API Usage:
    from composure import pull

    # Pull with progress callback
    for progress in pull():
        print(f"{progress.percent:.0f}% - {progress.downloaded_bytes}/{progress.total_bytes}")

    # Or get final result only
    result = pull(progress=False)
    print(f"Pulled {result.images_complete} images")
"""

# Suppress LibreSSL warning on macOS (harmless, just noisy)
import warnings
warnings.filterwarnings("ignore", message=".*LibreSSL.*")

__version__ = "0.1.9"

from typing import Generator, Optional, Union
from pathlib import Path


def pull(
    path: str = ".",
    progress: bool = True
) -> Union[Generator, "PullProgress"]:
    """
    Pull all images from docker-compose.yml.

    Args:
        path: Directory containing docker-compose.yml (default: current dir)
        progress: If True, yields PullProgress objects. If False, returns final result only.

    Yields (if progress=True):
        PullProgress objects with:
            - percent: float (0-100)
            - downloaded_bytes: int
            - total_bytes: int
            - images: dict of image_name -> ImageProgress
            - images_complete: int
            - images_total: int
            - completed_layers: int
            - total_layers: int

    Returns (if progress=False):
        Final PullProgress object

    Example:
        from composure import pull

        for p in pull():
            print(f"{p.percent:.0f}%")
    """
    from composure.puller import find_compose_and_images, pull_images_with_progress, PullProgress
    from composure.analyzer import get_docker_client

    compose_path, images = find_compose_and_images(path)

    if not compose_path:
        raise FileNotFoundError(f"No docker-compose.yml found in {path}")

    if not images:
        raise ValueError("No images found in compose file (all services use build?)")

    client = get_docker_client()

    if progress:
        return pull_images_with_progress(client, images)
    else:
        # Return only final result
        result = None
        for result in pull_images_with_progress(client, images):
            pass
        return result


# Export commonly used types for type hints
from composure.puller import PullProgress, ImageProgress, LayerProgress

__all__ = [
    "__version__",
    "pull",
    "PullProgress",
    "ImageProgress",
    "LayerProgress",
]

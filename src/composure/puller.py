"""
Puller module - pulls Docker images with progress tracking.
"""

from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Callable, Generator
from ruamel.yaml import YAML

from composure.scanner import find_compose_files


@dataclass
class LayerProgress:
    """Track progress of a single layer."""
    layer_id: str
    current: int = 0
    total: int = 0
    status: str = "waiting"  # waiting, downloading, extracting, complete


@dataclass
class ImageProgress:
    """Track progress of a single image pull."""
    image: str
    layers: dict = field(default_factory=dict)  # layer_id -> LayerProgress
    status: str = "pending"  # pending, pulling, complete, error
    error: Optional[str] = None


@dataclass
class PullProgress:
    """Overall pull progress across all images."""
    images: dict = field(default_factory=dict)  # image_name -> ImageProgress

    @property
    def total_bytes(self) -> int:
        """Total bytes to download across all layers."""
        total = 0
        for img in self.images.values():
            for layer in img.layers.values():
                if layer.total > 0:
                    total += layer.total
        return total

    @property
    def downloaded_bytes(self) -> int:
        """Total bytes downloaded so far."""
        downloaded = 0
        for img in self.images.values():
            for layer in img.layers.values():
                downloaded += layer.current
        return downloaded

    @property
    def percent(self) -> float:
        """Overall percentage complete."""
        if self.total_bytes == 0:
            return 0.0
        return (self.downloaded_bytes / self.total_bytes) * 100

    @property
    def total_layers(self) -> int:
        """Total number of layers across all images."""
        return sum(len(img.layers) for img in self.images.values())

    @property
    def completed_layers(self) -> int:
        """Number of completed layers."""
        count = 0
        for img in self.images.values():
            for layer in img.layers.values():
                if layer.status == "complete":
                    count += 1
        return count

    @property
    def images_complete(self) -> int:
        """Number of images fully pulled."""
        return sum(1 for img in self.images.values() if img.status == "complete")

    @property
    def images_total(self) -> int:
        """Total number of images."""
        return len(self.images)


def parse_compose_images(compose_path: Path) -> list[str]:
    """
    Parse a docker-compose file and extract all image names.

    Args:
        compose_path: Path to docker-compose.yml

    Returns:
        List of image names (e.g., ['nginx:latest', 'postgres:15'])
    """
    yaml = YAML()
    yaml.preserve_quotes = True

    with open(compose_path) as f:
        data = yaml.load(f)

    images = []
    services = data.get('services', {})

    for service_name, service_config in services.items():
        if isinstance(service_config, dict):
            # Direct image reference
            if 'image' in service_config:
                images.append(service_config['image'])
            # Build context - skip these (need to build, not pull)
            # elif 'build' in service_config:
            #     pass

    return images


def find_compose_and_images(directory: str = ".") -> tuple[Optional[Path], list[str]]:
    """
    Find docker-compose file and extract images.

    Returns:
        Tuple of (compose_path, list_of_images) or (None, []) if not found
    """
    compose_files = find_compose_files(directory)

    if not compose_files:
        return None, []

    # Use the first compose file found (usually in current dir)
    compose_path = compose_files[0]
    images = parse_compose_images(compose_path)

    return compose_path, images


def pull_images_with_progress(
    client,
    images: list[str],
    progress_callback: Optional[Callable[[PullProgress], None]] = None
) -> Generator[PullProgress, None, None]:
    """
    Pull multiple Docker images IN PARALLEL and yield progress updates.

    All images download simultaneously so overall progress is accurate.

    Args:
        client: Docker client
        images: List of image names to pull
        progress_callback: Optional callback for progress updates

    Yields:
        PullProgress objects with current state
    """
    import threading
    import queue
    import time

    progress = PullProgress()
    update_queue = queue.Queue()
    lock = threading.Lock()

    # Initialize all images as pending
    for image in images:
        progress.images[image] = ImageProgress(image=image)

    yield progress

    def pull_single_image(image: str):
        """Pull a single image in a thread."""
        img_progress = progress.images[image]

        with lock:
            img_progress.status = "pulling"
        update_queue.put(("update", image))

        try:
            repo, tag = _parse_image_name(image)

            for event in client.api.pull(repo, tag=tag, stream=True, decode=True):
                with lock:
                    _update_progress_from_event(img_progress, event)
                update_queue.put(("update", image))

            with lock:
                img_progress.status = "complete"
            update_queue.put(("complete", image))

        except Exception as e:
            with lock:
                img_progress.status = "error"
                img_progress.error = str(e)
            update_queue.put(("error", image))

    # Start all pulls in parallel
    threads = []
    for image in images:
        t = threading.Thread(target=pull_single_image, args=(image,))
        t.start()
        threads.append(t)

    # Discovery phase: wait until all images have discovered their layers
    # This prevents the progress bar from jumping as new layers are found
    discovery_timeout = 3.0  # Max seconds to wait for discovery
    discovery_start = time.time()

    while time.time() - discovery_start < discovery_timeout:
        try:
            event_type, image = update_queue.get(timeout=0.1)
            if event_type in ("complete", "error"):
                # Image finished during discovery (cached?)
                pass
        except queue.Empty:
            pass

        # Check if all images have started discovering layers
        with lock:
            all_discovered = all(
                img.status in ("pulling", "complete", "error") and
                (len(img.layers) > 0 or img.status in ("complete", "error"))
                for img in progress.images.values()
            )

        if all_discovered:
            break

    # Now yield progress updates while threads are running
    completed = sum(1 for img in progress.images.values() if img.status in ("complete", "error"))

    while completed < len(images):
        try:
            event_type, image = update_queue.get(timeout=0.1)

            if event_type in ("complete", "error"):
                completed += 1

            if progress_callback:
                progress_callback(progress)
            yield progress

        except queue.Empty:
            # No update, but yield anyway to keep UI responsive
            yield progress

    # Wait for all threads to finish
    for t in threads:
        t.join()

    yield progress


def _parse_image_name(image: str) -> tuple[str, str]:
    """Parse image name into repo and tag."""
    if ':' in image:
        parts = image.rsplit(':', 1)
        return parts[0], parts[1]
    return image, 'latest'


def _update_progress_from_event(img_progress: ImageProgress, event: dict) -> None:
    """Update image progress from a Docker pull event."""
    status = event.get('status', '')
    layer_id = event.get('id', '')

    if not layer_id:
        return

    # Create layer if it doesn't exist
    if layer_id not in img_progress.layers:
        img_progress.layers[layer_id] = LayerProgress(layer_id=layer_id)

    layer = img_progress.layers[layer_id]

    # Update layer status
    if status == 'Pulling fs layer':
        layer.status = 'waiting'
    elif status == 'Downloading':
        layer.status = 'downloading'
        progress_detail = event.get('progressDetail', {})
        layer.current = progress_detail.get('current', 0)
        layer.total = progress_detail.get('total', 0)
    elif status == 'Extracting':
        layer.status = 'extracting'
        progress_detail = event.get('progressDetail', {})
        layer.current = layer.total  # Count as downloaded
    elif status == 'Pull complete':
        layer.status = 'complete'
        layer.current = layer.total if layer.total > 0 else layer.current
    elif status == 'Already exists':
        layer.status = 'complete'
        # Already cached, counts as complete but no download needed


def format_bytes(bytes_val: int) -> str:
    """Format bytes into human readable string."""
    if bytes_val < 1024:
        return f"{bytes_val}B"
    elif bytes_val < 1024 * 1024:
        return f"{bytes_val / 1024:.1f}KB"
    elif bytes_val < 1024 * 1024 * 1024:
        return f"{bytes_val / (1024 * 1024):.1f}MB"
    else:
        return f"{bytes_val / (1024 * 1024 * 1024):.2f}GB"

"""
Scanner module - finds docker-compose files in a directory.
"""

from pathlib import Path


def find_compose_files(directory: str = ".") -> list[Path]:
    """
    Recursively search for docker-compose files.

    Args:
        directory: Starting directory to search (default: current dir)

    Returns:
        List of Path objects pointing to compose files
    """
    root = Path(directory)

    # Common names for docker-compose files
    patterns = [
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
    ]

    found = []

    # Walk through all subdirectories
    for pattern in patterns:
        found.extend(root.rglob(pattern))

    return sorted(set(found))  # Remove duplicates, sort alphabetically

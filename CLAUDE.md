# composure

Terminal UI (Textual) that audits and visualises Docker Compose stacks. Published to PyPI and Docker Hub as `composure`.
Python 3.9+, managed with uv. Source in `src/composure/` (`cli.py` Typer entry, `app.py` TUI, `scanner.py`, `analyzer.py`, `puller.py`).

## Commands
- `uv sync` to set up. `uv run composure` to run.
- `uv build` builds the package. No test suite or linter is configured.

## Where things live
- Identity lane: personal. No Vercel, Convex, PostHog or database.
- Release: publishing a GitHub release runs `.github/workflows/publish.yml` (PyPI via `PYPI_API_TOKEN`, then Docker Hub `jamesdimonaco/composure`).
- Bump `version` in `pyproject.toml` before you release.
- The Dockerfile installs with `uv sync --frozen`, so commit `uv.lock` with any dependency change.

## Gotchas
- The `origin` remote is https. Push with `git push git@github.com:JamesDimonaco/composure.git <branch>`.
- `src/composure.egg-info/` is on disk but ignored. Do not edit it.

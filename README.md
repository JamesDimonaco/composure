# Composure

A terminal tool to audit, optimize, and visualize Docker-Compose stacks in real-time.

![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)
![PyPI](https://img.shields.io/pypi/v/composure)
![Docker](https://img.shields.io/docker/v/jamesdimonaco/composure?label=docker)

## Quick Install

```bash
pip install composure
```

Or choose your preferred method below.

## What is Composure?

Composure is a TUI (Terminal User Interface) dashboard that helps you:

- **Monitor** all your Docker containers in real-time
- **Detect waste** by comparing actual resource usage vs allocated limits
- **Visualize networks** to see how containers connect to each other
- **Control containers** directly from the terminal (start, stop, restart, view logs)
- **Pull images** with a single overall progress bar across all images

## Features

- **Resource Monitoring**: See CPU and memory usage for all containers
- **Waste Detection**: Identify over-provisioned containers with waste scores
- **Limit Awareness**: Quickly spot containers without resource limits
- **Network Visualization**: Tree view showing container network topology
- **Container Controls**: Start, stop, restart containers with keyboard shortcuts
- **Live Logs**: View recent logs for any container
- **Image Pull Progress**: Pull all images from docker-compose.yml with a single overall progress percentage
- **Parallel Loading**: Fast startup even with many containers

## Installation

### pip (recommended)

```bash
pip install composure
```

### pipx (isolated environment)

```bash
pipx install composure
```

### uv

```bash
uv tool install composure
```

### Docker

```bash
docker run -it -v /var/run/docker.sock:/var/run/docker.sock jamesdimonaco/composure
```

### Debian/Ubuntu

```bash
# One-line install script
curl -fsSL https://jamesdimonaco.github.io/composure/install.sh | sudo bash
```

<details>
<summary>Or install manually</summary>

```bash
# Add the GPG key
curl -fsSL https://jamesdimonaco.github.io/composure/gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/composure.gpg

# Add the repository
echo "deb [signed-by=/usr/share/keyrings/composure.gpg] https://jamesdimonaco.github.io/composure stable main" | sudo tee /etc/apt/sources.list.d/composure.list

# Install
sudo apt update
sudo apt install composure
```

</details>

### From source

```bash
git clone https://github.com/JamesDimonaco/composure.git
cd composure
pip install -e .
```

## Usage

```bash
composure
```

### Pull Images

Pull all images from your docker-compose.yml with a single overall progress percentage:

```bash
composure pull
```

This shows real-time progress across all images downloading in parallel:

```text
Pulling 3 images from docker-compose.yml

⠙ Overall              ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  36%  847MB / 2.3GB
    nginx:alpine       ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100%  done
    redis:alpine       ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  45%  pulling
    postgres:15-alpine ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  20%  pulling
```

You can also press `p` in the TUI to pull images.

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `q` | Quit |
| `r` | Refresh / Return from logs |
| `n` | Toggle network view |
| `s` | Stop selected container |
| `a` | Start selected container |
| `x` | Restart selected container |
| `l` | Show logs for selected container |
| `p` | Pull all images from docker-compose.yml |
| `?` | Show help |
| `↑/↓` | Navigate containers |

## Understanding the Dashboard

### Main View

```
Container     Status   CPU %  CPU Limit  RAM Used  RAM Limit  Efficiency  Waste
nginx         running  0.5%   2 cores    45 MB     512 MB     LOW         90
api           running  2.1%   No limit   128 MB    256 MB     MEDIUM      40
postgres      running  1.2%   1 core     256 MB    512 MB     GOOD        20
```

### Columns Explained

| Column | Description |
|--------|-------------|
| **Status** | running, exited, paused, etc. |
| **CPU %** | Current CPU usage |
| **CPU Limit** | Configured limit (or "No limit") |
| **RAM Used** | Current memory usage |
| **RAM Limit** | Configured limit (or "No limit") |
| **Efficiency** | LOW/MEDIUM/GOOD/HIGH utilization |
| **Waste** | 0-100 score (higher = more over-provisioned) |

### Waste Score

The waste score helps identify containers that have been allocated far more resources than they're using:

| Score | Color | Meaning |
|-------|-------|---------|
| 0-30 | Green | Good utilization |
| 30-60 | Yellow | Could be optimized |
| 60-100 | Red | Significantly over-provisioned |

### Network View

Press `n` to see a tree view of your Docker networks:

```
Docker Networks
├── Compose Networks
│   └── myapp_default (3 containers)
│       ├── nginx
│       ├── api
│       └── postgres
└── System Networks
    └── bridge (empty)
```

## Requirements

- Python 3.9+
- Docker Engine running locally
- Access to Docker socket

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Links

- [PyPI Package](https://pypi.org/project/composure/)
- [Docker Hub](https://hub.docker.com/r/jamesdimonaco/composure)
- [GitHub Repository](https://github.com/JamesDimonaco/composure)
- [Report Issues](https://github.com/JamesDimonaco/composure/issues)

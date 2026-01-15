# Composure APT Repository

This is the APT repository for [Composure](https://github.com/JamesDimonaco/composure) - a terminal tool to audit, optimize, and visualize Docker-Compose stacks.

## Quick Install

```bash
curl -fsSL https://jamesdimonaco.github.io/composure/install.sh | sudo bash
```

## Manual Install

```bash
# Add the GPG key
curl -fsSL https://jamesdimonaco.github.io/composure/gpg.key | sudo gpg --dearmor -o /usr/share/keyrings/composure.gpg

# Add the repository
echo "deb [signed-by=/usr/share/keyrings/composure.gpg] https://jamesdimonaco.github.io/composure stable main" | sudo tee /etc/apt/sources.list.d/composure.list

# Install
sudo apt update
sudo apt install composure
```

## Other Install Methods

- **pip:** `pip install composure`
- **Docker:** `docker run -it -v /var/run/docker.sock:/var/run/docker.sock jamesdimonaco/composure`

See the [main repository](https://github.com/JamesDimonaco/composure) for more information.

#!/bin/bash
# Composure installer for Debian/Ubuntu
# Usage: curl -fsSL https://jamesdimonaco.github.io/composure/install.sh | sudo bash

set -e

echo "Installing Composure..."

# Add GPG key
curl -fsSL https://jamesdimonaco.github.io/composure/gpg.key | gpg --dearmor -o /usr/share/keyrings/composure.gpg

# Add repository
echo "deb [signed-by=/usr/share/keyrings/composure.gpg] https://jamesdimonaco.github.io/composure stable main" > /etc/apt/sources.list.d/composure.list

# Install
apt-get update
apt-get install -y composure

echo ""
echo "Composure installed successfully!"
echo "Run 'composure' to start."

#!/usr/bin/env bash
# LenovoLegionLinux installer — Arch Linux only
# Tested on: Lenovo Legion 5 15ARH05 (82B5)
set -e

echo "==> Installing kernel module via DKMS..."
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR/kernel_module"
sudo make dkms

echo "==> Installing Python package..."
sudo pip install "$REPO_DIR/python/legion_linux/" --break-system-packages

echo ""
echo "Done. Run 'legion_gui' to launch the app."
echo "A reboot may be required for the kernel module to load automatically."

#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -eq 0 ]]; then
  echo "Run bash scripts/install_pi.sh as your regular user, without sudo in front."
  exit 1
fi

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
pi_model="$(tr -d '\0' </proc/device-tree/model 2>/dev/null || true)"
if [[ "$pi_model" != *"Raspberry Pi Zero 2"* ]]; then
  echo "This installer targets a Raspberry Pi Zero 2 W with Raspberry Pi OS."
  echo "Detected model: ${pi_model:-not a Raspberry Pi}. No changes were made."
  exit 1
fi
if [[ ! "$project_dir" =~ ^/[a-zA-Z0-9_./-]+$ ]]; then
  echo "Extract the project into a path without spaces, for example ~/iauso."
  exit 1
fi

# Migration from version 1.1, which was named "codenotch-eink". Done before
# installing so the old unit cannot fire in the middle of the switch.
legacy_unit=/etc/systemd/system/codenotch-eink.timer
if [[ -e "$legacy_unit" ]]; then
  echo "Previous installation detected (codenotch-eink). Migrating to iauso..."
  sudo systemctl disable --now codenotch-eink.timer || true
  sudo rm -f "$legacy_unit" /etc/systemd/system/codenotch-eink.service
  sudo systemctl daemon-reload
fi
for legacy_dir in "$HOME/.config/codenotch-eink" "$HOME/.local/state/codenotch-eink"; do
  target="${legacy_dir/codenotch-eink/iauso}"
  if [[ -d "$legacy_dir" && ! -e "$target" ]]; then
    mv -- "$legacy_dir" "$target"
    echo "Moved $legacy_dir -> $target"
  fi
done
# The old paths are also written inside config.json.
if [[ -f "$project_dir/config.json" ]] && grep -q "codenotch-eink" "$project_dir/config.json"; then
  cp -- "$project_dir/config.json" "$project_dir/config.json.bak"
  sed -i 's/codenotch-eink/iauso/g' "$project_dir/config.json"
  echo "Paths updated in config.json (previous copy in config.json.bak)"
fi

sudo apt-get update
sudo apt-get install -y python3 python3-pil python3-gpiozero python3-lgpio python3-spidev fonts-dejavu-core tzdata
sudo raspi-config nonint do_spi 0
sudo usermod -aG gpio,spi "$(id -un)"

cd "$project_dir"
if [[ ! -e config.json ]]; then
  cp config.example.json config.json
  chmod 600 config.json
fi
unit_dir="$(mktemp -d)"
trap 'rm -rf -- "$unit_dir"' EXIT
python3 scripts/make_systemd.py --project "$project_dir" --user "$(id -un)" --out "$unit_dir"
sudo install -m 644 "$unit_dir/iauso.service" /etc/systemd/system/iauso.service
sudo install -m 644 "$unit_dir/iauso.timer" /etc/systemd/system/iauso.timer
sudo systemctl daemon-reload

echo "Installation ready. Reboot to activate SPI and the GPIO permissions."
echo "Next: python3 -m iauso refresh --config config.json --demo"
echo "Configure the accounts or receiver mode following README.md."
echo "To start updating: sudo systemctl enable --now iauso.timer"

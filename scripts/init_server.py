"""Create private folders for standard Docker on Linux (UID/GID 1000)."""
import argparse
import ipaddress
import os
import secrets
from pathlib import Path


def initialize(root, bind_host="127.0.0.1", uid=1000, gid=1000, rotate_token=False):
    address = ipaddress.ip_address(bind_host)
    if address.version != 4 or address.is_unspecified or address.is_multicast:
        raise ValueError("Give a specific IPv4 of the server; not 0.0.0.0")
    os.umask(0o077)
    folders = [root / "server-data", root / "server-data/home",
               root / "server-data/home/.claude", root / "server-data/home/.codex",
               root / "server-data/state", root / "server-data/public", root / "secrets"]
    for path in folders:
        if path.is_symlink():
            raise ValueError("Symbolic links are not allowed in server-data/secrets")
        path.mkdir(mode=0o700, exist_ok=True)
        path.chmod(0o700)
        if os.geteuid() == 0:
            os.chown(path, uid, gid)
    files = {
        root / "secrets/api-token": secrets.token_urlsafe(32) + "\n",
        root / "server-data/home/.codex/config.toml": 'cli_auth_credentials_store = "file"\n',
        root / ".env": f"API_BIND_HOST={address}\nAPI_PORT=8080\n",
    }
    token_path = root / "secrets/api-token"
    for path, content in files.items():
        if path.is_symlink():
            raise ValueError("Symbolic links are not allowed in the initial configuration")
        force = rotate_token and path == token_path
        try:
            with path.open("w" if force else "x", encoding="utf-8") as handle:
                handle.write(content)
        except FileExistsError:
            continue  # Never rotate keys nor replace existing configuration.
        path.chmod(0o600)
        if os.geteuid() == 0:
            # .env is owned by whoever ran sudo; the secrets, by UID 1000.
            owner = int(os.environ.get("SUDO_UID", "0")) if path.name == ".env" else uid
            group = int(os.environ.get("SUDO_GID", "0")) if path.name == ".env" else gid
            os.chown(path, owner, group)
    return token_path if rotate_token else None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="127.0.0.1", help="Listen IP: loopback, LAN or VPN address of the server")
    parser.add_argument("--rotate-token", action="store_true",
                         help="Generate a new panel key, replacing the existing one")
    args = parser.parse_args()
    if os.name != "posix" or os.geteuid() != 0:
        parser.error("Run with sudo python3 on the Linux server; not on the Raspberry Pi")
    token_path = initialize(Path(__file__).resolve().parents[1], args.bind, rotate_token=args.rotate_token)
    if token_path:
        print("New panel key written to", token_path)
        print("Copy it to each Raspberry Pi (replacing ~/.config/iauso/api-token) and then:")
        print("  sudo docker compose up -d --force-recreate api")
        print("The previous key stops working as soon as 'api' is recreated.")
    else:
        print("Folders and key ready. Existing files were preserved.")
        print("Check API_BIND_HOST in .env. Then run docker compose build.")

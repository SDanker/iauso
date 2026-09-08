"""Integracion HTTP local, sin cuentas reales ni Docker/GPIO."""
import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch
from wsgiref.simple_server import WSGIRequestHandler, make_server

from iauso.__main__ import get_snapshot
from iauso.api import QuotaAPI, create_app, fetch_snapshot, read_api_token, validate_api_url
from iauso.config import load_config
from iauso.providers import UsageError, demo_snapshot
from iauso.storage import read_json, write_json

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "TEST_ONLY_" + "x" * 40


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *args):
        pass


class APITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.now = time.time()
        self.key = self.base / "api-token"
        self.key.write_text(TOKEN + "\n")
        self.snapshot_file = self.base / "snapshot.json"
        self.raw = demo_snapshot(self.now)
        self.raw["demo"] = False
        write_json(self.snapshot_file, self.raw)
        app = QuotaAPI(self.snapshot_file, self.key, clock=lambda: self.now)
        self.server = make_server("127.0.0.1", 0, app, handler_class=QuietHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.config_file = self.base / "config.json"
        write_json(self.config_file, {"source": "api", "api_allow_http": True,
                   "api_url": self.url + "/v1/usage", "api_token_file": str(self.key),
                   "display": "png", "state_dir": str(self.base / "state")})
        self.config = load_config(self.config_file)

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()
        self.tmp.cleanup()

    def request(self, path="/v1/usage", token=TOKEN, method="GET"):
        headers = {"Authorization": "Bearer " + token} if token is not None else {}
        req = urllib.request.Request(self.url + path, headers=headers, method=method)
        try:
            response = urllib.request.urlopen(req, timeout=2)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return response.status, dict(response.headers), json.loads(response.read())

    def test_http_authentication_method_paths_and_health(self):
        for key in (None, "wrong"):
            code, headers, body = self.request(token=key)
            self.assertEqual(code, 401)
            self.assertEqual(headers["WWW-Authenticate"], "Bearer")
            self.assertNotIn(TOKEN, json.dumps(body))
        self.assertEqual(self.request(method="POST")[0], 405)
        self.assertEqual(self.request(path="/v1/usage?token=bad")[0], 400)
        self.assertEqual(self.request(path="/missing")[0], 404)
        self.assertEqual(self.request(path="/healthz", token=None)[2], {"status": "up"})

    def test_api_only_serves_allowlisted_snapshot_and_never_collects(self):
        self.raw["access_token"] = "SECRET-PROVIDER"
        self.raw["providers"]["claude"]["credential_tag"] = "private"
        self.raw["providers"]["claude"]["windows"][0]["secret"] = "also-private"
        write_json(self.snapshot_file, self.raw)
        with patch("iauso.providers.collect", side_effect=AssertionError("No upstream")):
            for _ in range(3):
                code, headers, body = self.request()
                self.assertEqual(code, 200)
                self.assertIn("no-store", headers["Cache-Control"])
                self.assertNotIn("secret", json.dumps(body).lower())
                self.assertNotIn("credential_tag", json.dumps(body))
                self.assertEqual(body["providers"]["claude"]["windows"][0]["used_percent"], 74)

    def test_stale_snapshot_is_not_made_fresh_by_api_requests(self):
        self.now += 1000
        body = fetch_snapshot(self.config)
        self.assertEqual(body["generated_at"], self.raw["generated_at"])
        self.assertEqual(body["providers"]["claude"]["status"], "stale")
        self.assertEqual(body["providers"]["claude"]["updated_at"], self.raw["generated_at"])

    def test_missing_malformed_or_demo_snapshot_fails_closed(self):
        self.snapshot_file.unlink()
        self.assertEqual(self.request()[0], 503)
        self.snapshot_file.write_text("broken")
        self.assertEqual(self.request()[0], 503)
        raw = copy.deepcopy(self.raw); raw["demo"] = True
        write_json(self.snapshot_file, raw)
        self.assertEqual(self.request()[0], 503)
        self.key.unlink()
        self.assertEqual(self.request()[2], {"error": "api_not_configured"})
        with patch.dict(os.environ, {"APP_API_TOKEN_FILE": str(self.key)}):
            with self.assertRaises(ValueError):
                create_app()

    def test_http_client_and_cli_render_without_provider_credentials(self):
        with patch("iauso.providers.load_credential", side_effect=AssertionError("No provider tokens")):
            data = fetch_snapshot(self.config)
        self.assertEqual(data["providers"]["codex"]["windows"][0]["used_percent"], 42)
        for cmd in ("doctor", "refresh"):
            proc = subprocess.run([sys.executable, "-m", "iauso", cmd,
                                  "--config", str(self.config_file)], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertNotIn(TOKEN, proc.stdout + proc.stderr)
        from PIL import Image
        with Image.open(self.base / "state/preview.png") as im:
            self.assertEqual(im.size, (296, 160))
        self.assertNotIn(TOKEN, (self.base / "state/state.json").read_text())

    def test_outage_keeps_cache_and_switching_server_drops_it(self):
        state = {}
        good = get_snapshot(self.config, state, self.now)
        self.snapshot_file.unlink()
        with self.assertLogs("iauso", level="WARNING"):
            offline = get_snapshot(self.config, state, self.now + 301)
        self.assertEqual(offline["providers"]["claude"]["status"], "offline")
        self.assertEqual(offline["providers"]["claude"]["updated_at"], good["generated_at"])
        self.assertEqual(offline["providers"]["claude"]["windows"], good["providers"]["claude"]["windows"])
        self.config["api_url"] = "http://different.example/v1/usage"
        with patch("iauso.api.fetch_snapshot", side_effect=UsageError("offline", "Sin conexion")):
            with self.assertLogs("iauso", level="WARNING"):
                other = get_snapshot(self.config, state, self.now + 302)
        self.assertEqual(other["providers"]["claude"]["windows"], [])

    def test_replayed_older_snapshot_does_not_replace_latest_cache(self):
        state = {}
        get_snapshot(self.config, state, self.now)
        self.raw["generated_at"] -= 600
        for p in self.raw["providers"].values():
            p["updated_at"] -= 600
        write_json(self.snapshot_file, self.raw)
        with self.assertLogs("iauso", level="WARNING"):
            result = get_snapshot(self.config, state, self.now + 301)
        self.assertEqual(result["generated_at"], self.now)
        self.assertEqual(result["providers"]["claude"]["status"], "offline")

    def test_unauthorized_and_redirects_never_expose_tokens(self):
        bad_key = self.base / "bad-token"; bad_key.write_text("y" * 40)
        self.config["api_token_file"] = str(bad_key)
        with self.assertRaises(UsageError) as err:
            fetch_snapshot(self.config)
        self.assertIn("401/403", str(err.exception))
        self.assertNotIn("y" * 40, str(err.exception))
        visited = []
        def redirect(environ, start_response):
            visited.append(environ["PATH_INFO"])
            start_response("302 Found", [("Location", self.url + "/leak"), ("Content-Length", "0")])
            return [b""]
        self.server.set_app(redirect)
        with self.assertRaises(UsageError):
            fetch_snapshot(self.config)
        self.assertEqual(visited, ["/v1/usage"])


class SetupTests(unittest.TestCase):
    def test_https_default_url_and_token_validation(self):
        for url in ("http://example.com/v1/usage", "https://u:p@example.com/v1/usage",
                    "https://example.com/v1/usage?token=x", "https://example.com/v1/usage#x",
                    "file:///v1/usage", "https://example.com/not-the-endpoint"):
            with self.assertRaises(ValueError):
                validate_api_url(url)
        self.assertEqual(validate_api_url("https://example.com/v1/usage"), "https://example.com/v1/usage")
        with tempfile.TemporaryDirectory() as folder:
            key = Path(folder) / "key"
            for invalid in ("short", "x" * 130, "x" * 32 + "\nInjected", "\u00e9" * 32):
                key.write_text(invalid)
                with self.assertRaises(ValueError):
                    read_api_token(key)

    @unittest.skipUnless(os.name == "posix", "Linux/POSIX initializer")
    def test_server_initialization_is_private_and_does_not_rotate_key(self):
        spec = importlib.util.spec_from_file_location("init_server", ROOT / "scripts/init_server.py")
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            module.initialize(base, "127.0.0.1", uid=os.getuid(), gid=os.getgid())
            key = base / "secrets/api-token"
            token = read_api_token(key)
            module.initialize(base, "192.168.1.100", uid=os.getuid(), gid=os.getgid())
            self.assertEqual(read_api_token(key), token)
            self.assertIn("127.0.0.1", (base / ".env").read_text())
            self.assertEqual(key.stat().st_mode & 0o777, 0o600)
            self.assertEqual((base / "server-data/home").stat().st_mode & 0o777, 0o700)
            self.assertIn('"file"', (base / "server-data/home/.codex/config.toml").read_text())


if __name__ == "__main__":
    unittest.main()

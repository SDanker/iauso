"""Pruebas sin Internet, sin credenciales reales y sin GPIO."""
import copy
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from iauso.config import load_config
from iauso.display import display_image
from iauso.providers import (Credential, NoRedirects, UsageError, collect,
    demo_snapshot, fetch_usage, load_credential, parse_claude, parse_codex,
    retry_seconds, validate_snapshot)
from iauso.render import PALETTE, render, reset_label, status_label
from iauso.storage import read_json, write_json
from zoneinfo import ZoneInfo

NOW = 1788807600.0
CODEX = {"rate_limit": {
    "primary_window": {"used_percent": 42, "limit_window_seconds": 18000, "reset_at": NOW + 7200},
    "secondary_window": {"used_percent": 18, "limit_window_seconds": 604800, "reset_after_seconds": 86400}
}, "code_review_rate_limit": {"primary_window": {"used_percent": 100}}}
CLAUDE = {"five_hour": {"utilization": 74, "resets_at": "2026-09-07T22:00:00.000Z"},
          "seven_day": {"utilization": 92, "resets_at": "2026-09-11T22:00:00Z"}}


class QuotaTests(unittest.TestCase):
    def test_codex_uses_reported_duration_and_ignores_review_quota(self):
        windows = parse_codex(CODEX, NOW)
        self.assertEqual([w["used_percent"] for w in windows], [42, 18])
        self.assertEqual(windows[1]["resets_at"], NOW + 86400)
        data = copy.deepcopy(CODEX)
        data["rate_limit"]["primary_window"]["limit_window_seconds"] = 2592000
        self.assertEqual(parse_codex(data, NOW)[0]["label"], "30 d")

    def test_missing_or_bad_usage_is_never_zero(self):
        for invalid in (None, True, -1, 101, float("nan"), "42"):
            data = copy.deepcopy(CODEX)
            data["rate_limit"]["primary_window"]["used_percent"] = invalid
            with self.assertRaises(ValueError):
                parse_codex(data, NOW)
        self.assertEqual(parse_codex({"rate_limit": None}, NOW), [])
        self.assertEqual(parse_claude({"five_hour": None}, NOW), [])

    def test_claude_old_and_new_formats_merge_without_duplicates(self):
        data = {**CLAUDE, "limits": [{"kind": "weekly_all", "percent": 95, "resets_at": "2026-09-11T22:00:00Z"}]}
        windows = parse_claude(data, NOW)
        self.assertEqual([w["id"] for w in windows], ["session", "weekly_all"])
        self.assertEqual(windows[1]["used_percent"], 95)

    def test_zero_without_reset_remains_zero_not_missing(self):
        windows = parse_claude({"five_hour": {"utilization": 0, "resets_at": None}}, NOW)
        self.assertEqual(windows[0]["used_percent"], 0)
        self.assertIsNone(windows[0]["resets_at"])

    def test_cache_backoff_survives_restart_and_secret_is_not_exported(self):
        config = load_config()
        config["codex"]["enabled"] = False
        credential = Credential("FAKE-TOKEN-NOT-A-REAL-SECRET")
        state = {}
        public = collect(config, state, NOW, lambda *a: CLAUDE, lambda *a: credential)
        self.assertEqual(public["providers"]["claude"]["status"], "ok")
        self.assertNotIn(credential.access_token, json.dumps(state))
        self.assertNotIn("credential_tag", json.dumps(public))
        def throttled(*args):
            raise UsageError("rate_limited", "Espera", 3600)
        collect(config, state, NOW + 301, throttled, lambda *a: credential)
        reloaded = json.loads(json.dumps(state))
        self.assertEqual(reloaded["providers"]["claude"]["retry_at"], NOW + 3901)
        collect(config, reloaded, NOW + 310, lambda *a: self.fail("No consultar durante backoff"), lambda *a: credential)
        self.assertEqual(reloaded["providers"]["claude"]["windows"][0]["used_percent"], 74)
        self.assertEqual(reloaded["providers"]["claude"]["updated_at"], NOW)

    def test_account_change_drops_old_reading_on_error(self):
        config = load_config(); config["codex"]["enabled"] = False
        state = {}
        collect(config, state, NOW, lambda *a: CLAUDE, lambda *a: Credential("old"))
        def fail(*args):
            raise UsageError("offline", "Sin conexion")
        public = collect(config, state, NOW + 301, fail, lambda *a: Credential("new"))
        self.assertEqual(public["providers"]["claude"]["windows"], [])

    def test_disabled_provider_never_reads_credentials(self):
        config = load_config()
        for p in ("claude", "codex"):
            config[p]["enabled"] = False
        public = collect(config, {}, NOW, lambda *a: self.fail(), lambda *a: self.fail())
        self.assertEqual(public["providers"]["codex"]["status"], "disabled")

    def test_expired_credential_and_api_key_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "creds.json"
            write_json(path, {"claudeAiOauth": {"accessToken": "fake", "expiresAt": (NOW - 1) * 1000}})
            with self.assertRaises(UsageError) as err:
                load_credential("claude", {"credentials_file": str(path)}, NOW)
            self.assertEqual(err.exception.status, "expired")
            write_json(path, {"OPENAI_API_KEY": "fake"})
            with self.assertRaises(UsageError):
                load_credential("codex", {"credentials_file": str(path)}, NOW)

    def test_expired_reset_is_not_recalculated(self):
        self.assertEqual(reset_label(NOW - 1, NOW, ZoneInfo("UTC")), "R: to confirm")

    def test_retry_header_and_redirect_policy(self):
        self.assertEqual(retry_seconds("3600", NOW), 3600)
        self.assertEqual(retry_seconds("nan", NOW), 0)
        self.assertEqual(retry_seconds("0", NOW), 0)
        self.assertIsNone(NoRedirects().redirect_request(None, None, 302, "", {}, "https://evil.invalid"))

    def test_unauthorized_maps_to_auth_without_body(self):
        import urllib.error
        from email.message import Message
        fake = urllib.error.HTTPError("https://chatgpt.com", 401, "fake-sensitive-body", Message(), None)
        with patch("urllib.request.OpenerDirector.open", side_effect=fake):
            with self.assertRaises(UsageError) as exc:
                fetch_usage("codex", Credential("fake", "fake-account"))
        self.assertEqual(exc.exception.status, "needs_auth")
        self.assertNotIn("fake-sensitive", str(exc.exception))

    def test_snapshot_rejects_demo_future_and_marks_stale(self):
        raw = demo_snapshot(NOW)
        with self.assertRaises(ValueError):
            validate_snapshot(raw, NOW, 900)
        raw["demo"] = False
        old = validate_snapshot(raw, NOW + 901, 900)
        self.assertEqual(old["providers"]["claude"]["status"], "stale")
        with self.assertRaises(ValueError):
            validate_snapshot(raw, NOW - 1000, 900)


class PanelTests(unittest.TestCase):
    def test_render_four_colors_and_all_error_states(self):
        config = load_config()
        for status in ("ok", "offline", "needs_auth", "expired", "rate_limited", "error", "no_data", "stale"):
            snapshot = demo_snapshot(NOW)
            snapshot["providers"]["codex"]["status"] = status
            image = render(snapshot, config, NOW)
            self.assertEqual(image.size, (296, 160))
            self.assertLessEqual({color for _, color in image.getcolors(296*160)}, PALETTE)

    def test_panel_language_is_configurable_and_defaults_to_english(self):
        from iauso.i18n import STRINGS, strings
        self.assertEqual(load_config()["language"], "en")
        # Both languages must define exactly the same keys, so a translation
        # can never leave a hole that only shows up on the physical panel.
        self.assertEqual(set(STRINGS["en"]), set(STRINGS["es"]))
        self.assertEqual(set(STRINGS["en"]["status"]), set(STRINGS["es"]["status"]))
        snapshot = demo_snapshot(NOW)
        snapshot["providers"]["codex"]["status"] = "offline"
        english = load_config()
        spanish = load_config()
        spanish["language"] = "es"
        self.assertEqual(status_label(snapshot["providers"]["codex"], ZoneInfo("UTC"),
                                      strings("en")), "NO CONNECTION")
        self.assertEqual(status_label(snapshot["providers"]["codex"], ZoneInfo("UTC"),
                                      strings("es")), "SIN CONEXION")
        # The rendered image must actually differ between the two languages.
        self.assertNotEqual(render(snapshot, english, NOW).tobytes(),
                            render(snapshot, spanish, NOW).tobytes())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            path.write_text(json.dumps({"language": "fr"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_config(str(path))

    def test_color_thresholds_are_configurable_per_panel_mode(self):
        # demo_snapshot usa 74% y 92% en Claude: con los umbrales por defecto
        # caen en advertencia y critico; subiendolos, ambos vuelven a negro.
        # Sin el rotulo DEMO ni estados de error: asi el unico origen posible
        # de color en la imagen son las barras de uso (74% y 92%).
        snapshot = demo_snapshot(NOW)
        snapshot["demo"] = False

        def colors(**overrides):
            config = load_config()
            config.update(overrides)
            image = render(snapshot, config, NOW)
            return {color for _, color in image.getcolors(image.size[0] * image.size[1])}

        self.assertIn((255, 255, 0), colors())  # 74% -> amarillo con el umbral 70
        self.assertIn((255, 0, 0), colors())    # 92% -> rojo con el umbral 90
        self.assertNotIn((255, 255, 0), colors(warn_percent=95, crit_percent=99))
        self.assertIn((255, 0, 0), colors(warn_percent=10, crit_percent=20))
        # Un panel de un solo color de tinta nunca pinta el segundo color,
        # y uno monocromo no pinta ninguno, cualquiera sea el umbral.
        self.assertLessEqual(colors(panel="7.5b", warn_percent=10, crit_percent=20),
                             {(0, 0, 0), (255, 255, 255), (255, 0, 0)})
        self.assertEqual(colors(panel="7.5", warn_percent=10, crit_percent=20),
                         {(0, 0, 0), (255, 255, 255)})
        for bad in ({"warn_percent": 101}, {"crit_percent": -1}, {"warn_percent": 95, "crit_percent": 90}):
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "config.json"
                path.write_text(json.dumps(bad), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_config(str(path))

    def test_real_waveshare_packing_without_gpio(self):
        # Importa el controlador real y simula solo la capa GPIO, no getbuffer.
        from PIL import Image
        package = types.ModuleType("fake_epd")
        package.__path__ = []
        gpio = types.ModuleType("fake_epd.epdconfig")
        for key in ("RST_PIN", "DC_PIN", "BUSY_PIN", "CS_PIN"):
            setattr(gpio, key, 0)
        path = Path(__file__).resolve().parents[1] / "vendor/waveshare_epd/epd2in15g.py"
        with patch.dict(sys.modules, {"fake_epd": package, "fake_epd.epdconfig": gpio}):
            spec = importlib.util.spec_from_file_location("fake_epd.epd2in15g", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            driver = module.EPD()
            for color, byte in (((0,0,0), 0x00), ((255,255,255), 0x55), ((255,255,0), 0xAA), ((255,0,0), 0xFF)):
                buf = driver.getbuffer(Image.new("RGB", (296,160), color))
                self.assertEqual(len(buf), 11840)
                self.assertEqual(set(buf), {byte})
            buf = driver.getbuffer(render(demo_snapshot(NOW), load_config(), NOW))
            self.assertEqual(len(buf), 11840)
            self.assertTrue(all(0 <= x <= 255 for x in buf))

    def test_panel_interval_and_digest_survive_process_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            config = load_config(); config["state_dir"] = folder
            path = Path(folder) / "state.json"
            state = {"schema_version": 1, "providers": {}}
            image = render(demo_snapshot(NOW), config, NOW)
            calls = []
            result = display_image(image, config, state, path, NOW, lambda *a: calls.append(1))
            self.assertEqual(result, "displayed")
            reloaded = read_json(path)
            self.assertEqual(display_image(image, config, reloaded, path, NOW+30, lambda *a: calls.append(1)), "deferred")
            self.assertEqual(display_image(image, config, reloaded, path, NOW+301, lambda *a: calls.append(1)), "unchanged")
            self.assertEqual(calls, [1])
            self.assertEqual(display_image(image, config, reloaded, path, NOW+86401, lambda *a: calls.append(1)), "displayed")
            self.assertEqual(calls, [1,1])

    def test_failed_hardware_still_throttles_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            config = load_config(); config["state_dir"] = folder
            path = Path(folder) / "state.json"; state = {}
            def fail(*args):
                raise RuntimeError("Simulacion de desconexion")
            with self.assertRaises(RuntimeError):
                display_image(render(demo_snapshot(NOW), config, NOW), config, state, path, NOW, fail)
            self.assertNotIn("display_digest", read_json(path))
            self.assertEqual(read_json(path)["last_display_attempt"], NOW)

    def test_storage_is_atomic_private_and_config_rejects_fast_refresh(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "file.json"
            write_json(path, {"min_refresh_seconds": 10})
            if os.name != "nt":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(ValueError):
                load_config(path)


class WorkflowTests(unittest.TestCase):
    def test_cli_demo_and_receiver_do_not_require_credentials_or_gpio(self):
        from PIL import Image
        import time
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            config = base / "config.json"
            write_json(config, {"display": "png", "source": "file", "state_dir": str(base / "state"),
                                "snapshot_file": str(base / "inbox.json")})
            command = [sys.executable, "-m", "iauso"]
            proc = subprocess.run(command + ["preview", "--config", str(config), "--demo", "--output", str(base / "demo.png")],
                                  cwd=root, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with Image.open(base / "demo.png") as im:
                self.assertEqual(im.size, (296, 160))
            raw = demo_snapshot(time.time()); raw["demo"] = False
            write_json(base / "inbox.json", raw)
            proc = subprocess.run(command + ["refresh", "--config", str(config)], cwd=root, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            cached = read_json(base / "state/state.json")
            self.assertEqual(cached["remote_snapshot"]["providers"]["claude"]["windows"][0]["used_percent"], 74)
            self.assertTrue((base / "state/preview.png").exists())

    def test_ssh_payload_contains_only_public_snapshot_and_fixed_command(self):
        from iauso.__main__ import push_snapshot
        raw = demo_snapshot(NOW); raw["demo"] = False
        with patch("subprocess.run") as run:
            push_snapshot("usuario@raspberrypi.local", raw)
        argv = run.call_args.args[0]
        self.assertIn("BatchMode=yes", argv)
        self.assertIn('cat > "$tmp"', argv[-1])
        self.assertEqual(json.loads(run.call_args.kwargs["input"]), raw)
        with self.assertRaises(ValueError):
            push_snapshot("-oProxyCommand=bad", raw)


if __name__ == "__main__":
    unittest.main()

"""Automated unit tests for CLI (`bin/dpi-hub`), Cinnamon Applet, CSS, and Documentation."""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from dpi_core import cli  # noqa: E402


def _mock_hw_manager() -> mock.MagicMock:
    mgr = mock.MagicMock()
    mgr.get_all_peripherals_snapshot.return_value = {
        "devices": {
            "mouse": {
                "id": "ajazz_aj179_v2",
                "name": "AJAZZ AJ179 V2",
                "connected": True,
                "active": True,
                "battery": 75,
                "charging": False,
                "connection_type": "2.4GHz",
                "current_dpi": 1600,
                "polling_rate": 1000,
                "led_color": "#3B82F6",
                "sleep_seconds": 300,
                "standby": False,
            },
            "headset": {
                "id": "havit_fuxi_h3",
                "name": "Havit Fuxi H3",
                "connected": True,
                "active": True,
                "battery": 60,
                "charging": False,
                "connection_type": "Bluetooth",
                "volume": 72,
                "muted": False,
            },
            "gamepad": {
                "id": "gamepads",
                "name": "GameSir Nova Lite",
                "connected": True,
                "active": True,
                "charging": False,
                "battery": 90,
                "connection_type": "2.4GHz",
                "controllers": [
                    {
                        "id": "gamesir_nova_lite",
                        "name": "GameSir Nova Lite",
                        "connected": True,
                        "active": True,
                        "charging": False,
                        "battery": 90,
                    }
                ],
            },
            "keyboard": {
                "id": "machenike_k500_b94",
                "name": "Machenike K500-B94",
                "connected": True,
                "active": True,
                "connection_type": "USB-C",
                "safe_mode": True,
                "leds": {"capslock": False, "numlock": True, "scrolllock": False},
            },
        },
        "alerts": [
            {
                "type": "device_connected",
                "severity": "info",
                "device": "gamepad",
                "name": "GameSir Nova Lite",
                "message": "GameSir Nova Lite conectado (2.4GHz)",
            }
        ],
    }
    mgr.dispatch_action.return_value = (True, "Ação executada")
    return mgr


def _mock_ag_collector() -> mock.MagicMock:
    ag = mock.MagicMock()
    ag.collect.return_value = {
        "connected": True,
        "plan": {
            "name": "Pro",
            "tier": "PRO",
            "prompt_credits": 45000,
            "monthly_prompt_credits": 50000,
            "flow_credits": 120000,
            "monthly_flow_credits": 150000,
        },
        "active_model": {
            "id": "MODEL_PLACEHOLDER_M668",
            "name": "Orchestrator (Argon)",
            "label": "Orchestrator (Argon)",
            "group": "argon",
        },
        "active_project": "Dynamic-Peripheral-Island",
        "quotas": [
            {
                "id": "neon",
                "name": "Gemini 4 Neon",
                "short_name": "Neon",
                "enabled": True,
                "remaining_pct": 81.0,
                "used_pct": 19.0,
                "reset_time_iso": "2026-11-19T22:00:00Z",
                "reset_countdown": "4h 6m",
                "window": "5h",
                "pace_pct": 18.0,
                "depletion_eta": "~3.8h",
                "models": ["Gemini 4 Neon (High)"],
            },
            {
                "id": "hydrogen",
                "name": "Gemini 4 Hydrogen",
                "short_name": "Hydrogen",
                "enabled": True,
                "remaining_pct": 95.0,
                "used_pct": 5.0,
                "reset_time_iso": "2026-11-19T22:00:00Z",
                "reset_countdown": "4h 6m",
                "window": "5h",
                "pace_pct": 18.0,
                "depletion_eta": None,
                "models": ["Gemini 4 Hydrogen (High)"],
            },
        ],
        "lowest_quota": {
            "id": "neon",
            "name": "Gemini 4 Neon",
            "short_name": "Neon",
            "enabled": True,
            "remaining_pct": 81.0,
            "used_pct": 19.0,
            "reset_time_iso": "2026-11-19T22:00:00Z",
            "reset_countdown": "4h 6m",
            "window": "5h",
            "pace_pct": 18.0,
            "depletion_eta": "~3.8h",
            "models": ["Gemini 4 Neon (High)"],
        },
        "swarm": {
            "active_count": 2,
            "total_count": 3,
            "agents": [
                {"id": "1111aaaa", "role": "coordinator", "status": "WORKING", "steps": 12},
                {"id": "2222bbbb", "role": "hw-engine", "status": "IDLE", "steps": 8},
            ],
        },
        "session_context": {
            "active_project": "Dynamic-Peripheral-Island",
            "conversation_id": "1111aaaa",
            "input_tokens": 1200,
            "cache_read_tokens": 3400,
            "output_tokens": 400,
            "total_tokens": 5000,
        },
        "daily_histogram_7d": [
            {"date": "2026-11-13", "label": "Sex", "tokens": 1000},
            {"date": "2026-11-14", "label": "Sáb", "tokens": 2000},
            {"date": "2026-11-15", "label": "Dom", "tokens": 500},
            {"date": "2026-11-16", "label": "Seg", "tokens": 3000},
            {"date": "2026-11-17", "label": "Ter", "tokens": 4000},
            {"date": "2026-11-18", "label": "Qua", "tokens": 2500},
            {"date": "2026-11-19", "label": "Hoje", "tokens": 5000},
        ],
        "monthly": {
            "month": "2026-11",
            "total_tokens": 18000,
            "input_tokens": 5000,
            "cache_tokens": 11000,
            "output_tokens": 2000,
            "top_projects": [{"name": "Dynamic-Peripheral-Island", "tokens": 18000}],
        },
        "alerts": [],
    }
    return ag


class TestCliAndOutputs(unittest.TestCase):
    """Tests bin/dpi-hub modes (--island-json, --waybar, --pretty) and settings/control flags."""

    def _run_cli(self, argv, settings_path=None, hw=None, ag=None):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cli.main(
                argv=argv,
                hw_manager=hw or _mock_hw_manager(),
                ag_collector=ag or _mock_ag_collector(),
                settings_path=settings_path,
            )
        return rc, buf.getvalue()

    def test_island_json_waybar_and_pretty_modes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "settings.json"

            # --island-json
            rc, out = self._run_cli(["--island-json"], settings_path=settings_path)
            self.assertEqual(rc, 0)
            data = json.loads(out)
            for key in ("version", "timestamp", "theme_suggestion", "capsule", "alerts", "peripherals", "antigravity", "settings"):
                self.assertIn(key, data)
            self.assertEqual(len(data["capsule"]["peripherals"]), 4)
            self.assertEqual(data["capsule"]["antigravity"]["label"], "Neon 81%")
            self.assertEqual(data["capsule"]["antigravity"]["swarm_active"], 2)

            # --waybar (single-line JSON)
            rc_w, out_w = self._run_cli(["--waybar"], settings_path=settings_path)
            self.assertEqual(rc_w, 0)
            self.assertEqual(len(out_w.strip().splitlines()), 1)
            wb = json.loads(out_w)
            self.assertIn("text", wb)
            self.assertIn("tooltip", wb)
            self.assertIn("class", wb)
            self.assertIn("percentage", wb)
            self.assertTrue(0 <= wb["percentage"] <= 100)

            # --pretty
            rc_p, out_p = self._run_cli(["--pretty"], settings_path=settings_path)
            self.assertEqual(rc_p, 0)
            self.assertIn("Dynamic Peripheral Island", out_p)
            self.assertIn("AJAZZ AJ179 V2", out_p)
            self.assertIn("Gemini 4 Neon", out_p)
            self.assertIn("Histograma 7 Dias", out_p)

    def test_cli_settings_pin_and_hardware_control_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "settings.json"
            hw = _mock_hw_manager()

            # Pin device & quota & theme & threshold & poll interval
            for argv in (
                ["--pin-device", "mouse=false"],
                ["--pin-device", "headset=true"],
                ["--pin-quota", "neon"],
                ["--set-theme", "dark"],
                ["--set-alert-threshold", "15"],
                ["--set-poll-interval", "10"],
            ):
                rc, out = self._run_cli(argv, settings_path=settings_path, hw=hw)
                self.assertEqual(rc, 0)
                res = json.loads(out)
                self.assertTrue(res["ok"])

            saved = cli.load_settings(settings_path)
            self.assertFalse(saved["pin_mouse"])
            self.assertTrue(saved["pin_headset"])
            self.assertEqual(saved["pinned_quota"], "neon")
            self.assertEqual(saved["theme_mode"], "dark")
            self.assertEqual(saved["battery_alert_threshold"], 15)
            self.assertEqual(saved["poll_interval"], 10)

            # Invalid setting rejected cleanly
            rc_bad, out_bad = self._run_cli(["--set-theme", "neon-pink"], settings_path=settings_path, hw=hw)
            self.assertEqual(rc_bad, 1)
            self.assertFalse(json.loads(out_bad)["ok"])

            # Hardware control flags dispatch properly
            for argv, expected_action in (
                (["--set-dpi", "3200"], "set_dpi"),
                (["--set-polling", "500"], "set_polling_rate"),
                (["--fix-alsa"], "fix_alsa_volume"),
                (["--set-eq", "gaming"], "set_eq_preset"),
                (["--test-rumble", "--controller-id", "gamesir_nova_lite"], "test_rumble"),
                (["--set-deadzone", "10"], "set_deadzone"),
                (["--set-gamepad-layout", "nintendo"], "set_layout"),
            ):
                rc_h, out_h = self._run_cli(argv, settings_path=settings_path, hw=hw)
                self.assertEqual(rc_h, 0)
                self.assertTrue(json.loads(out_h)["ok"])
                self.assertEqual(hw.dispatch_action.call_args[0][0], expected_action)

    def test_bin_dpi_hub_executable_runs_cleanly(self) -> None:
        bin_path = ROOT_DIR / "bin" / "dpi-hub"
        self.assertTrue(bin_path.is_file())
        self.assertTrue(os.access(bin_path, os.X_OK))

        with tempfile.TemporaryDirectory() as fake_home:
            env = dict(os.environ)
            env["HOME"] = fake_home
            proc = subprocess.run(
                [str(bin_path), "--island-json"],
                capture_output=True,
                text=True,
                timeout=10,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["version"], "1.0.0")
            self.assertIn("capsule", payload)


class TestAppletCssAndDocs(unittest.TestCase):
    """Validates applet.js JS syntax/structure, stylesheet.css, installers, and documentation."""

    def test_applet_js_syntax_and_structure(self) -> None:
        applet_dir = ROOT_DIR / "applet" / "dynamic-peripheral-island@brendo"
        applet_js = applet_dir / "applet.js"
        meta_json = applet_dir / "metadata.json"

        self.assertTrue(applet_js.is_file())
        self.assertTrue(meta_json.is_file())

        meta = json.loads(meta_json.read_text(encoding="utf-8"))
        self.assertEqual(meta["uuid"], "dynamic-peripheral-island@brendo")
        self.assertEqual(meta["max-instances"], 1)

        src = applet_js.read_text(encoding="utf-8")
        # Balanced braces/parens
        self.assertEqual(src.count("{"), src.count("}"))
        self.assertEqual(src.count("("), src.count(")"))

        # Required symbols and async/lifecycle patterns
        for token in (
            "DynamicPeripheralIslandApplet",
            "on_applet_removed_from_panel",
            "addHotKey",
            "removeHotKey",
            "Gio.Subprocess",
            ".ease(",
            "dpi-unified-capsule",
            "org.cinnamon.desktop.interface",
            "_prewarmPopover",
            'this.actor.remove_style_class_name("applet-box")',
            'style_class: "applet-box dpi-capsule-segment"',
            "insert_child_below",
            "_leftSlot",
            "_updateHoverState",
            "_syncCapsuleOpenState",
            "dpi-capsule-hovered",
            "dpi-capsule-open",
        ):
            self.assertIn(token, src)

        # Left slot insertion on the left of calendarActor and lifecycle cleanup
        self.assertIn("centerBox.insert_child_below(this._leftSlot, calendarActor)", src)
        self.assertIn("this._leftSlot.destroy()", src)
        self.assertIn("this._detachUnifiedCapsule()", src)
        self.assertIn("leftParent.remove_child(this._leftSlot)", src)
        self.assertIn('this._unifiedCenterBox.remove_style_class_name("dpi-unified-capsule")', src)
        self.assertIn('this._unifiedCenterBox.remove_style_class_name("dpi-capsule-hovered")', src)
        self.assertIn('this._unifiedCenterBox.remove_style_class_name("dpi-capsule-open")', src)

        # Segments must use button-press-event (not button-release-event) to precede on_applet_clicked
        self.assertIn('this._segPeripherals.connect("button-press-event"', src)
        self.assertIn('this._segAntigravity.connect("button-press-event"', src)
        self.assertNotIn('this._segPeripherals.connect("button-release-event"', src)
        self.assertNotIn('this._segAntigravity.connect("button-release-event"', src)

        # Ensure St.BoxLayout never receives a GObject `spacing:` property outside CSS `style:` strings
        for lineno, line in enumerate(src.splitlines(), start=1):
            if "spacing:" in line:
                self.assertIn(
                    "style:",
                    line,
                    msg=f"GObject spacing property found in applet.js line {lineno}: {line.strip()}",
                )

        # Validate JS syntax via node --check if installed
        node_bin = shutil.which("node")
        if node_bin:
            proc = subprocess.run([node_bin, "--check", str(applet_js)], capture_output=True, text=True, check=False)
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)

        # Zero structural emojis in applet.js
        emoji_re = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]")
        self.assertIsNone(emoji_re.search(src), msg="applet.js must not contain structural emojis")

    def test_stylesheet_css_dark_light_classes_and_braces(self) -> None:
        css_path = ROOT_DIR / "applet" / "dynamic-peripheral-island@brendo" / "stylesheet.css"
        self.assertTrue(css_path.is_file())
        css = css_path.read_text(encoding="utf-8")

        self.assertEqual(css.count("{"), css.count("}"))
        for required_cls in (
            ".dpi-unified-capsule",
            ".dpi-theme-dark",
            ".dpi-theme-light",
            ".dpi-capsule-segment",
            ".dpi-morph-pill",
            ".dpi-pace-marker",
            ".dpi-left-slot",
            ".dpi-capsule-hovered",
            ".dpi-capsule-open",
        ):
            self.assertIn(required_cls, css)

        # Zero font-family overrides (inherits system font, e.g. Lexend 10)
        font_families = re.findall(r"font-family\s*:\s*([^;]+);", css)
        self.assertEqual(len(font_families), 0, msg=f"stylesheet.css should not override font-family: {font_families}")

        # Capsule is transparent in idle (hover-only) and has zero blue background
        self.assertNotIn("rgba(15, 23, 42, 0.84)", css)
        capsule_idle = re.search(r"\.dpi-unified-capsule\s*\{([^}]+)\}", css)
        self.assertIsNotNone(capsule_idle)
        self.assertIn("background-color: transparent;", capsule_idle.group(1))
        self.assertIn("border-radius: 8px;", capsule_idle.group(1))
        self.assertNotIn("999px", capsule_idle.group(1))
        self.assertNotIn("rgba(15, 23, 42", capsule_idle.group(1))

        # Both dark and light idle themes for unified capsule must be completely transparent
        dark_idle = re.search(r"\.dpi-unified-capsule\.dpi-theme-dark\s*\{([^}]+)\}", css)
        self.assertIsNotNone(dark_idle)
        self.assertIn("background-color: transparent;", dark_idle.group(1))
        self.assertNotIn("rgba(15, 23, 42", dark_idle.group(1))

        light_idle = re.search(r"\.dpi-unified-capsule\.dpi-theme-light\s*\{([^}]+)\}", css)
        self.assertIsNotNone(light_idle)
        self.assertIn("background-color: transparent;", light_idle.group(1))
        self.assertNotIn("rgba(15, 23, 42", light_idle.group(1))

        # Hovered and open states must exist and be defined for both dark and light
        self.assertIn(".dpi-unified-capsule.dpi-theme-dark.dpi-capsule-hovered", css)
        self.assertIn(".dpi-unified-capsule.dpi-theme-light.dpi-capsule-hovered", css)
        self.assertIn(".dpi-unified-capsule.dpi-theme-dark.dpi-capsule-open", css)
        self.assertIn(".dpi-unified-capsule.dpi-theme-light.dpi-capsule-open", css)

        # Segments use 6px radius and transparent background
        segment_match = re.search(r"\.dpi-capsule-segment\s*\{([^}]+)\}", css)
        self.assertIsNotNone(segment_match)
        self.assertIn("border-radius: 6px;", segment_match.group(1))
        self.assertNotIn("999px", segment_match.group(1))

        emoji_re = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]")
        self.assertIsNone(emoji_re.search(css), msg="stylesheet.css must not contain structural emojis")

    def test_zero_structural_emojis_in_cli_outputs_and_auto_visibility(self) -> None:
        emoji_re = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]")
        hw = _mock_hw_manager()
        # Simulate charging gamepad (not active) and Bluetooth headset (not pinned)
        hw.get_all_peripherals_snapshot.return_value["devices"]["headset"]["charging"] = True
        hw.get_all_peripherals_snapshot.return_value["devices"]["gamepad"]["active"] = False
        hw.get_all_peripherals_snapshot.return_value["devices"]["gamepad"]["charging"] = True
        hw.get_all_peripherals_snapshot.return_value["devices"]["gamepad"]["controllers"][0]["active"] = False
        hw.get_all_peripherals_snapshot.return_value["devices"]["gamepad"]["controllers"][0]["charging"] = True

        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "settings.json"
            for flag in ("--island-json", "--waybar", "--pretty"):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rc = cli.main(
                        argv=[flag],
                        hw_manager=hw,
                        ag_collector=_mock_ag_collector(),
                        settings_path=settings_path,
                    )
                self.assertEqual(rc, 0)
                out = buf.getvalue()
                self.assertIsNone(
                    emoji_re.search(out),
                    msg=f"Structural emoji found in {flag} output: {out!r}",
                )
                if flag == "--island-json":
                    data = json.loads(out)
                    by_key = {p["key"]: p for p in data["capsule"]["peripherals"]}
                    self.assertTrue(by_key["headset"]["visible"])
                    self.assertTrue(by_key["gamepad"]["visible"])
                    self.assertTrue(by_key["headset"]["status_text"].endswith("+"))

    def test_install_and_uninstall_scripts_syntax(self) -> None:
        for script_name in ("install.sh", "uninstall.sh"):
            script = ROOT_DIR / script_name
            self.assertTrue(script.is_file())
            self.assertTrue(os.access(script, os.X_OK), msg=f"{script_name} must be executable")
            proc = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True, check=False)
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)

        install_text = (ROOT_DIR / "install.sh").read_text(encoding="utf-8")
        self.assertIn("org.Cinnamon.ReloadTheme", install_text)
        self.assertIn("org.Cinnamon.ReloadXlet", install_text)

    def test_documentation_and_design_system_files_exist_and_non_empty(self) -> None:
        required_docs = [
            "README.md",
            "CHANGELOG.md",
            "PRODUCTLOG.md",
            "ROADMAP.md",
            "AGENTS.md",
            "docs/ARCHITECTURE.md",
            "design-system/dynamic-peripheral-island/MASTER.md",
            "design-system/dynamic-peripheral-island/tokens.json",
            "design-system/dynamic-peripheral-island/tokens.css",
            "udev/99-dynamic-peripheral-island.rules",
            "LICENSE",
            ".gitignore",
        ]
        for rel in required_docs:
            p = ROOT_DIR / rel
            self.assertTrue(p.is_file(), msg=f"Missing required file: {rel}")
            content = p.read_text(encoding="utf-8").strip()
            self.assertGreater(len(content), 20, msg=f"File appears empty/trivial: {rel}")


if __name__ == "__main__":
    unittest.main()

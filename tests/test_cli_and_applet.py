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

    def _run_cli(self, argv, settings_path=None, hw=None, ag=None, audio=None, media=None):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cli.main(
                argv=argv,
                hw_manager=hw or _mock_hw_manager(),
                ag_collector=ag or _mock_ag_collector(),
                settings_path=settings_path,
                audio_manager=audio,
                media_manager=media,
            )
        return rc, buf.getvalue()

    def test_island_json_waybar_and_pretty_modes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "settings.json"

            # --island-json
            rc, out = self._run_cli(["--island-json"], settings_path=settings_path)
            self.assertEqual(rc, 0)
            data = json.loads(out)
            for key in (
                "version",
                "timestamp",
                "theme_suggestion",
                "capsule",
                "alerts",
                "peripherals",
                "antigravity",
                "settings",
                "audio",
                "media",
            ):
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

    def test_cli_audio_and_media_control_actions(self) -> None:
        """FEAT-004 & FEAT-005: CLI flags for AudioMixerManager and MediaPlayerManager."""
        audio_mock = mock.MagicMock()
        audio_mock.set_master_volume.return_value = (True, "Volume master 85%")
        audio_mock.toggle_master_mute.return_value = (True, "Mudo master alternado")
        audio_mock.set_default_sink.return_value = (True, "Saída alterada")
        audio_mock.set_mic_volume.return_value = (True, "Volume mic 65%")
        audio_mock.toggle_mic_mute.return_value = (True, "Mudo mic alternado")
        audio_mock.set_default_source.return_value = (True, "Mic padrão alterado")
        audio_mock.set_app_volume.return_value = (True, "Volume app ajustado")
        audio_mock.toggle_app_mute.return_value = (True, "Mudo app alternado")

        media_mock = mock.MagicMock()
        media_mock.play_pause.return_value = (True, "Play/Pause alternado")
        media_mock.next_track.return_value = (True, "Próxima faixa")
        media_mock.previous_track.return_value = (True, "Faixa anterior")

        cases = [
            (["--set-master-volume", "85"], lambda: audio_mock.set_master_volume.assert_called_with(85)),
            (["--toggle-master-mute"], lambda: audio_mock.toggle_master_mute.assert_called_with()),
            (["--set-default-sink", "alsa_output.sink"], lambda: audio_mock.set_default_sink.assert_called_with("alsa_output.sink")),
            (["--set-mic-volume", "65"], lambda: audio_mock.set_mic_volume.assert_called_with(65)),
            (["--toggle-mic-mute"], lambda: audio_mock.toggle_mic_mute.assert_called_with()),
            (["--set-default-source", "alsa_input.source"], lambda: audio_mock.set_default_source.assert_called_with("alsa_input.source")),
            (["--set-app-volume", "12", "70"], lambda: audio_mock.set_app_volume.assert_called_with(12, 70)),
            (["--toggle-app-mute", "12"], lambda: audio_mock.toggle_app_mute.assert_called_with(12)),
            (["--media-play-pause"], lambda: media_mock.play_pause.assert_called_with(bus_name=None)),
            (["--media-next"], lambda: media_mock.next_track.assert_called_with(bus_name=None)),
            (["--media-prev"], lambda: media_mock.previous_track.assert_called_with(bus_name=None)),
            (
                ["--media-play-pause", "--media-player", "org.mpris.MediaPlayer2.spotify"],
                lambda: media_mock.play_pause.assert_called_with(bus_name="org.mpris.MediaPlayer2.spotify"),
            ),
        ]

        for argv, assert_fn in cases:
            rc, out = self._run_cli(argv, audio=audio_mock, media=media_mock)
            self.assertEqual(rc, 0, msg=f"Failed for argv: {argv}")
            res = json.loads(out)
            self.assertTrue(res["ok"])
            assert_fn()

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

        # BUG-003: menuEventFilter intercepts BUTTON_RELEASE and BUTTON_PRESS on _leftSlot/_segPeripherals
        self.assertIn("menuEventFilter(event)", src)
        self.assertIn("Clutter.EventType.BUTTON_RELEASE", src)
        self.assertIn("Clutter.EventType.BUTTON_PRESS", src)
        self.assertIn("this._leftSlot.contains(src)", src)
        self.assertIn("this._segPeripherals.contains(src)", src)
        self.assertIn("this.menu.sourceActor =", src)
        self.assertIn("this.menu.sourceActor = this.actor;", src)
        # UX-012: Popover always centered in middle of TopBar island
        self.assertIn("this.menu.sourceActor = this._unifiedCenterBox || this._calendarActor || this.actor;", src)

        # FEAT-003: Mouse sleep symbolic icon reference
        self.assertIn("dpi-mouse-sleep-symbolic", src)

        # No vertical pipe divider on TopBar
        self.assertIn("this._midDivider.hide();", src)

        # UX-003: Popover attaches _popoverRoot directly via menu.addActor without PopupBaseMenuItem
        self.assertIn("this.menu.addActor(this._popoverRoot);", src)
        self.assertNotIn("PopupBaseMenuItem", src)

        # UX-004: Fluid tab switching and card expansion animations
        self.assertIn("_switchTab(newTabId, animate = true)", src)
        self.assertIn("this._bodyStack.ease(", src)
        self.assertIn("translation_x: 0", src)
        self.assertIn("_animateCardBody(body, cardKey)", src)
        self.assertIn("translation_y: 0", src)

        # UX-006: Hover-switch between open menus/tabs without opening unprompted
        self.assertIn("Clutter.EventType.ENTER", src)
        self.assertIn("_switchTabFromTopBarHover", src)
        self.assertIn('calMenu.connect("open-state-changed"', src)
        self.assertIn("_onCalendarOpenStateChanged", src)
        self.assertIn("_tabHoverTimerId", src)
        self.assertIn("_cancelTabHoverTimer", src)

        # BUG-005: Calendar -> Island hover monitor via _calHoverTimerId, global.get_pointer, and _pointInActor
        self.assertIn("_calHoverTimerId", src)
        self.assertIn("global.get_pointer", src)
        self.assertIn("_pointInActor(actor, px, py)", src)

        # UX-007: Custom device icons and per-device individual tooltips in TopBar
        self.assertIn("const Tooltips = imports.ui.tooltips;", src)
        self.assertIn("new Tooltips.Tooltip(", src)
        self.assertIn("this._pillTooltips", src)
        self.assertIn("_clearPillTooltips()", src)
        self.assertIn("_makeDeviceIcon(", src)
        self.assertIn('this.set_applet_tooltip("")', src)

        # UX-009: Header deduplication in Popover
        self.assertIn('text: "Antigravity View Usage"', src)
        self.assertIn('text: "Dynamic Island"', src)
        self.assertIn("Agente Ativo:", src)

        # UX-010, UX-014, UX-016: Unified 700px Bento Grid layout across all 4 tabs and GPU-only transitions
        self.assertIn("_syncPopoverWidth()", src)
        self.assertIn("dpi-popover-wide", src)
        self.assertIn("this._scrollView.vscrollbar_policy = St.PolicyType.NEVER", src)
        self.assertIn("this._popoverRoot.queue_relayout()", src)
        self.assertIn("this._scheduleMenuReposition()", src)
        self.assertIn("this._popoverRoot.width = 700;", src)
        self.assertIn('style_class: "dpi-bento-grid"', src)
        self.assertIn('style_class: "dpi-bento-col"', src)
        self.assertIn("PROGRESS_TRACK_WIDTH = 290;", src)

        # FEAT-004 & FEAT-005: Audio tab with Volum mixer and Spotify/MPRIS2 media player
        self.assertIn('"audio"', src)
        self.assertIn('"Áudio"', src)
        self.assertIn("_renderAudioTab()", src)
        self.assertIn("_buildMediaPlayerCard(", src)
        self.assertIn("_buildAudioMixerCard(", src)
        self.assertIn("_buildPerAppAudioCard(", src)

        # UX-016: 100% GPU transition (duration: 280, EASE_OUT_CUBIC, opacity: 150) without white flash
        self.assertIn("Clutter.AnimationMode.EASE_OUT_CUBIC", src)
        self.assertIn("duration: 280", src)
        self.assertIn("this._bodyStack.opacity = 150;", src)
        self.assertIn("this._tabHoverTimerId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 110,", src)

        # FEAT-006 & UX-017: Apple Notch Notchy Peek and Animated LiquidGlass Tooltip
        self.assertIn("this._peekActor", src)
        self.assertIn("this._tooltipActor", src)
        self.assertIn("_showAnimatedTooltip(sourceActor, text)", src)
        self.assertIn("_hideAnimatedTooltip()", src)
        self.assertIn("_showNotchPeek()", src)
        self.assertIn("_hideNotchPeek", src)
        self.assertIn("Main.uiGroup.remove_actor(this._peekActor)", src)
        self.assertIn("Main.uiGroup.remove_actor(this._tooltipActor)", src)
        self.assertIn("this._peekActor.destroy()", src)
        self.assertIn("this._tooltipActor.destroy()", src)
        self.assertIn("this._peekShowTimerId", src)
        self.assertIn("this._peekHideTimerId", src)
        self.assertIn("this._tooltipTimerId", src)

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
            ".dpi-popover-wide",
            ".dpi-bento-grid",
            ".dpi-bento-col",
            ".dpi-ag-columns",
            ".dpi-ag-col-left",
            ".dpi-ag-col-right",
            ".dpi-notch-peek",
            ".dpi-glass-tooltip",
        ):
            self.assertIn(required_cls, css)

        # UX-016: Unified 700px Bento Grid layout and 336px columns across all tabs
        popover_root_block = re.search(r"\.dpi-popover-root\s*\{([^}]+)\}", css)
        self.assertIsNotNone(popover_root_block)
        self.assertIn("width: 700px;", popover_root_block.group(1))
        self.assertIn("max-width: 700px;", popover_root_block.group(1))

        popover_wide = re.search(r"\.dpi-popover-root\.dpi-popover-wide\s*\{([^}]+)\}", css)
        self.assertIsNotNone(popover_wide)
        self.assertIn("width: 700px;", popover_wide.group(1))
        self.assertIn("max-width: 700px;", popover_wide.group(1))

        bento_col = re.search(r"\.dpi-bento-col\s*\{([^}]+)\}", css)
        self.assertIsNotNone(bento_col)
        self.assertIn("width: 336px;", bento_col.group(1))

        col_left = re.search(r"\.dpi-ag-col-left\s*\{([^}]+)\}", css)
        self.assertIsNotNone(col_left)
        self.assertIn("width: 336px;", col_left.group(1))

        col_right = re.search(r"\.dpi-ag-col-right\s*\{([^}]+)\}", css)
        self.assertIsNotNone(col_right)
        self.assertIn("width: 336px;", col_right.group(1))

        # FEAT-006: Apple Notch TopBar border-radius (0 0 14px 14px) and Notchy Peek (480px)
        notch_peek = re.search(r"\.dpi-notch-peek\s*\{([^}]+)\}", css)
        self.assertIsNotNone(notch_peek)
        self.assertIn("width: 480px;", notch_peek.group(1))
        self.assertIn("border-radius: 0 0 18px 18px;", notch_peek.group(1))

        # UX-017: Animated LiquidGlass Tooltip
        glass_tooltip = re.search(r"\.dpi-glass-tooltip\s*\{([^}]+)\}", css)
        self.assertIsNotNone(glass_tooltip)
        self.assertIn("border-radius: 6px;", glass_tooltip.group(1))

        # BUG-009: Keyboard LED badges (.dpi-theme-dark .dpi-kbd-badge.dpi-kbd-badge-on)
        self.assertIn(".dpi-theme-dark .dpi-kbd-badge.dpi-kbd-badge-on", css)
        self.assertIn(".dpi-theme-light .dpi-kbd-badge.dpi-kbd-badge-on", css)

        # UX-013: TopBar pills scale dynamically with system font (1em)
        pill_text = re.search(r"\.dpi-pill-text\s*\{([^}]+)\}", css)
        self.assertIsNotNone(pill_text)
        self.assertIn("font-size: 1em;", pill_text.group(1))

        morph_text = re.search(r"\.dpi-morph-text\s*\{([^}]+)\}", css)
        self.assertIsNotNone(morph_text)
        self.assertIn("font-size: 1em;", morph_text.group(1))

        # UX-014 & FEAT-004/FEAT-005: LiquidGlass styling and Audio/Media components
        for glass_token in (
            "rgba(38, 40, 54, 0.82)",
            "rgba(255, 255, 255, 0.14)",
            ".dpi-tab-btn-active",
            ".dpi-media-title",
            ".dpi-media-controls",
            "transition-duration: 320ms;",
        ):
            self.assertIn(glass_token, css)

        # Zero font-family overrides (inherits system font, e.g. Lexend 10)
        font_families = re.findall(r"font-family\s*:\s*([^;]+);", css)
        self.assertEqual(len(font_families), 0, msg=f"stylesheet.css should not override font-family: {font_families}")

        # Capsule is transparent in idle (hover-only) and has zero blue background
        self.assertNotIn("rgba(15, 23, 42, 0.84)", css)
        capsule_idle = re.search(r"\.dpi-unified-capsule\s*\{([^}]+)\}", css)
        self.assertIsNotNone(capsule_idle)
        self.assertIn("background-color: transparent;", capsule_idle.group(1))
        self.assertIn("border-radius: 0 0 14px 14px;", capsule_idle.group(1))
        self.assertIn("margin-top: 0;", capsule_idle.group(1))
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

        # UX-003: Popover uses native Cinnamon Calendar palette and transparent root (no double frame)
        popover_root = re.search(r"\.dpi-popover-root\s*\{([^}]+)\}", css)
        self.assertIsNotNone(popover_root)
        self.assertIn("background-color: transparent;", popover_root.group(1))
        self.assertIn("border: none;", popover_root.group(1))
        for cal_token in (
            "#282a36",
            "#232530",
            "#2c2f3c",
            "#373a4b",
            "#191a22",
            "rgba(189, 147, 249, 0.5)",
            "rgba(25, 26, 34, 0.9)",
        ):
            self.assertIn(cal_token, css)

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

            # UX-005: Auto-visibility and label for wireless GameSir Nova Lite / EasySMX
            hw_gamepad = _mock_hw_manager()
            # Active GameSir controller with battery=None (2.4GHz XInput mode)
            hw_gamepad.get_all_peripherals_snapshot.return_value["devices"]["gamepad"] = {
                "id": "gamepads",
                "name": "GameSir Nova Lite",
                "connected": True,
                "active": True,
                "charging": False,
                "battery": None,
                "connection_type": "2.4GHz (XInput)",
                "controllers": [
                    {
                        "id": "gamesir_nova_lite",
                        "name": "GameSir Nova Lite",
                        "connected": True,
                        "active": True,
                        "charging": False,
                        "battery": None,
                    }
                ],
            }
            # Mouse unpinned and in standby -> hidden
            hw_gamepad.get_all_peripherals_snapshot.return_value["devices"]["mouse"]["active"] = False
            hw_gamepad.get_all_peripherals_snapshot.return_value["devices"]["mouse"]["standby"] = True
            hw_gamepad.get_all_peripherals_snapshot.return_value["devices"]["mouse"]["charging"] = False

            buf_gp = io.StringIO()
            with contextlib.redirect_stdout(buf_gp):
                rc_gp = cli.main(
                    argv=["--island-json"],
                    hw_manager=hw_gamepad,
                    ag_collector=_mock_ag_collector(),
                    settings_path=settings_path,
                )
            self.assertEqual(rc_gp, 0)
            data_gp = json.loads(buf_gp.getvalue())
            gp_periphs = {p["key"]: p for p in data_gp["capsule"]["peripherals"]}
            self.assertTrue(gp_periphs["gamepad"]["visible"])
            self.assertEqual(gp_periphs["gamepad"]["status_text"], "GameSir")

            # Dual controllers active -> "2x"
            hw_gamepad.get_all_peripherals_snapshot.return_value["devices"]["gamepad"]["controllers"].append(
                {
                    "id": "easysmx_9124",
                    "name": "EasySMX 9124",
                    "connected": True,
                    "active": True,
                    "charging": False,
                    "battery": None,
                }
            )
            buf_dual = io.StringIO()
            with contextlib.redirect_stdout(buf_dual):
                rc_dual = cli.main(
                    argv=["--island-json"],
                    hw_manager=hw_gamepad,
                    ag_collector=_mock_ag_collector(),
                    settings_path=settings_path,
                )
            self.assertEqual(rc_dual, 0)
            data_dual = json.loads(buf_dual.getvalue())
            gp_dual = {p["key"]: p for p in data_dual["capsule"]["peripherals"]}
            self.assertTrue(gp_dual["gamepad"]["visible"])
            self.assertEqual(gp_dual["gamepad"]["status_text"], "2x")

            # BUG-006: Headset in standby (active=False) -> visible=False on TopBar
            hw_headset = _mock_hw_manager()
            hw_headset.get_all_peripherals_snapshot.return_value["devices"]["headset"] = {
                "id": "havit_fuxi_h3",
                "name": "Havit Fuxi H3",
                "connected": True,
                "active": False,
                "charging": False,
                "battery": None,
                "connection_type": "2.4GHz",
                "volume": 100,
                "muted": False,
                "sink_state": "SUSPENDED",
            }
            buf_hs_off = io.StringIO()
            with contextlib.redirect_stdout(buf_hs_off):
                rc_hs_off = cli.main(
                    argv=["--island-json"],
                    hw_manager=hw_headset,
                    ag_collector=_mock_ag_collector(),
                    settings_path=settings_path,
                )
            self.assertEqual(rc_hs_off, 0)
            data_hs_off = json.loads(buf_hs_off.getvalue())
            hs_periph_off = {p["key"]: p for p in data_hs_off["capsule"]["peripherals"]}["headset"]
            self.assertFalse(hs_periph_off["visible"])
            self.assertEqual(hs_periph_off["status_text"], "Standby")

            buf_wb_off = io.StringIO()
            with contextlib.redirect_stdout(buf_wb_off):
                cli.main(
                    argv=["--waybar"],
                    hw_manager=hw_headset,
                    ag_collector=_mock_ag_collector(),
                    settings_path=settings_path,
                )
            wb_off = json.loads(buf_wb_off.getvalue())
            self.assertIn("Havit Fuxi H3 (2.4GHz) — Standby", wb_off["tooltip"])

            # FEAT-002 & UX-011: Headset in Bluetooth mode with battery only on TopBar pill
            hw_headset.get_all_peripherals_snapshot.return_value["devices"]["headset"] = {
                "id": "havit_fuxi_h3",
                "name": "Havit Fuxi H3",
                "connected": True,
                "active": True,
                "charging": False,
                "battery": 85,
                "connection_type": "Bluetooth",
                "volume": 70,
                "muted": False,
                "sink_state": "RUNNING",
            }
            buf_hs_bt = io.StringIO()
            with contextlib.redirect_stdout(buf_hs_bt):
                rc_hs_bt = cli.main(
                    argv=["--island-json"],
                    hw_manager=hw_headset,
                    ag_collector=_mock_ag_collector(),
                    settings_path=settings_path,
                )
            self.assertEqual(rc_hs_bt, 0)
            data_hs_bt = json.loads(buf_hs_bt.getvalue())
            hs_periph_bt = {p["key"]: p for p in data_hs_bt["capsule"]["peripherals"]}["headset"]
            self.assertTrue(hs_periph_bt["visible"])
            self.assertEqual(hs_periph_bt["status_text"], "85%")
            self.assertEqual(hs_periph_bt["detail_text"], "Bluetooth · Vol 70%")

            buf_wb_bt = io.StringIO()
            with contextlib.redirect_stdout(buf_wb_bt):
                cli.main(
                    argv=["--waybar"],
                    hw_manager=hw_headset,
                    ag_collector=_mock_ag_collector(),
                    settings_path=settings_path,
                )
            wb_bt = json.loads(buf_wb_bt.getvalue())
            self.assertIn("Havit Fuxi H3 (Bluetooth) — Bateria: 85% | Volume: 70%", wb_bt["tooltip"])

            # Bluetooth with Muted (pill stays 85%, detail shows Mudo, tooltip shows Volume: Mudo)
            hw_headset.get_all_peripherals_snapshot.return_value["devices"]["headset"]["muted"] = True
            buf_hs_mute = io.StringIO()
            with contextlib.redirect_stdout(buf_hs_mute):
                cli.main(
                    argv=["--island-json"],
                    hw_manager=hw_headset,
                    ag_collector=_mock_ag_collector(),
                    settings_path=settings_path,
                )
            data_hs_mute = json.loads(buf_hs_mute.getvalue())
            hs_periph_mute = {p["key"]: p for p in data_hs_mute["capsule"]["peripherals"]}["headset"]
            self.assertEqual(hs_periph_mute["status_text"], "85%")
            self.assertEqual(hs_periph_mute["detail_text"], "Bluetooth · Mudo")

            buf_wb_mute = io.StringIO()
            with contextlib.redirect_stdout(buf_wb_mute):
                cli.main(
                    argv=["--waybar"],
                    hw_manager=hw_headset,
                    ag_collector=_mock_ag_collector(),
                    settings_path=settings_path,
                )
            wb_mute = json.loads(buf_wb_mute.getvalue())
            self.assertIn("Havit Fuxi H3 (Bluetooth) — Bateria: 85% | Mudo", wb_mute["tooltip"])

            # 2.4GHz without battery and muted (pill shows Mudo)
            hw_headset.get_all_peripherals_snapshot.return_value["devices"]["headset"]["battery"] = None
            hw_headset.get_all_peripherals_snapshot.return_value["devices"]["headset"]["connection_type"] = "2.4GHz"
            buf_hs_24_mute = io.StringIO()
            with contextlib.redirect_stdout(buf_hs_24_mute):
                cli.main(
                    argv=["--island-json"],
                    hw_manager=hw_headset,
                    ag_collector=_mock_ag_collector(),
                    settings_path=settings_path,
                )
            data_hs_24_mute = json.loads(buf_hs_24_mute.getvalue())
            hs_periph_24_mute = {p["key"]: p for p in data_hs_24_mute["capsule"]["peripherals"]}["headset"]
            self.assertEqual(hs_periph_24_mute["status_text"], "Mudo")

            # FEAT-003 & BUG-010: Mouse power states (active, sleep, off)
            hw_mouse = _mock_hw_manager()
            # Sleep mode (standby=True, power_state="sleep")
            hw_mouse.get_all_peripherals_snapshot.return_value["devices"]["mouse"] = {
                "id": "ajazz_aj179_v2",
                "name": "AJAZZ AJ179 V2",
                "connected": True,
                "active": False,
                "standby": True,
                "power_state": "sleep",
                "battery": 45,
                "charging": False,
                "connection_type": "Descanso",
                "current_dpi": 950,
                "polling_rate": 1000,
            }
            buf_m_sleep = io.StringIO()
            with contextlib.redirect_stdout(buf_m_sleep):
                rc_m_sleep = cli.main(
                    argv=["--island-json"],
                    hw_manager=hw_mouse,
                    ag_collector=_mock_ag_collector(),
                    settings_path=settings_path,
                )
            self.assertEqual(rc_m_sleep, 0)
            data_m_sleep = json.loads(buf_m_sleep.getvalue())
            m_periph_sleep = {p["key"]: p for p in data_m_sleep["capsule"]["peripherals"]}["mouse"]
            self.assertTrue(m_periph_sleep["visible"])
            self.assertEqual(m_periph_sleep["power_state"], "sleep")
            self.assertEqual(m_periph_sleep["icon"], "dpi-mouse-sleep-symbolic")
            self.assertEqual(m_periph_sleep["level"], "muted")
            self.assertEqual(m_periph_sleep["status_text"], "45%")
            self.assertIn("Modo de Descanso (Sleep)", m_periph_sleep["detail_text"])

            buf_m_wb = io.StringIO()
            with contextlib.redirect_stdout(buf_m_wb):
                cli.main(
                    argv=["--waybar"],
                    hw_manager=hw_mouse,
                    ag_collector=_mock_ag_collector(),
                    settings_path=settings_path,
                )
            wb_mouse = json.loads(buf_m_wb.getvalue())
            self.assertIn("AJAZZ AJ179 V2 (Modo de Descanso (Sleep)) — Bateria: 45%", wb_mouse["tooltip"])

            # Off mode (power_state="off") -> visible=False on TopBar
            hw_mouse.get_all_peripherals_snapshot.return_value["devices"]["mouse"]["power_state"] = "off"
            hw_mouse.get_all_peripherals_snapshot.return_value["devices"]["mouse"]["active"] = False
            hw_mouse.get_all_peripherals_snapshot.return_value["devices"]["mouse"]["standby"] = False
            buf_m_off = io.StringIO()
            with contextlib.redirect_stdout(buf_m_off):
                rc_m_off = cli.main(
                    argv=["--island-json"],
                    hw_manager=hw_mouse,
                    ag_collector=_mock_ag_collector(),
                    settings_path=settings_path,
                )
            self.assertEqual(rc_m_off, 0)
            data_m_off = json.loads(buf_m_off.getvalue())
            m_periph_off = {p["key"]: p for p in data_m_off["capsule"]["peripherals"]}["mouse"]
            self.assertFalse(m_periph_off["visible"])
            self.assertEqual(m_periph_off["power_state"], "off")

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
        import xml.etree.ElementTree as ET

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
            "applet/dynamic-peripheral-island@brendo/icons/dpi-gamepad-symbolic.svg",
            "applet/dynamic-peripheral-island@brendo/icons/dpi-mouse-sleep-symbolic.svg",
            "udev/99-dynamic-peripheral-island.rules",
            "LICENSE",
            ".gitignore",
        ]
        for rel in required_docs:
            p = ROOT_DIR / rel
            self.assertTrue(p.is_file(), msg=f"Missing required file: {rel}")
            content = p.read_text(encoding="utf-8").strip()
            self.assertGreater(len(content), 20, msg=f"File appears empty/trivial: {rel}")

        # Validate SVG XML structure for custom symbolic icons
        for svg_name in ("dpi-gamepad-symbolic.svg", "dpi-mouse-sleep-symbolic.svg"):
            svg_path = ROOT_DIR / "applet" / "dynamic-peripheral-island@brendo" / "icons" / svg_name
            tree = ET.parse(str(svg_path))
            root = tree.getroot()
            self.assertTrue(root.tag.endswith("svg"), msg=f"{svg_name} must have svg root tag")
            self.assertEqual(root.attrib.get("viewBox"), "0 0 16 16", msg=f"{svg_name} must have 16x16 viewBox")


if __name__ == "__main__":
    unittest.main()

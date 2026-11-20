"""Automated unit tests for src/dpi_core/audio.py (100% mocked, CI-safe)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from dpi_core.audio import (  # noqa: E402
    AudioMixerManager,
    MediaPlayerManager,
    parse_gvariant,
)


class TestAudioMixerManager(unittest.TestCase):
    """Tests AudioMixerManager pactl parsing and control actions (Volum-inspired)."""

    def test_get_state_parsing_sinks_sources_and_apps(self) -> None:
        pactl_sinks = """Sink #1
\tState: RUNNING
\tName: alsa_output.pci-0000_00_1f.3.analog-stereo
\tDescription: Built-in Audio Analog Stereo
\tDriver: PipeWire
\tVolume: front-left: 65536 / 100% / 0.00 dB,   front-right: 65536 / 100% / 0.00 dB
\tMute: no
\tProperties:
\t\talsa.card_name = "HDA Intel PCH"
\t\tdevice.description = "Áudio interno Estéreo analógico"
\t\tnode.nick = "ALC887-VD Analog"

Sink #2
\tState: SUSPENDED
\tName: bluez_output.01_92_25_27_09_76.1
\tDescription: Havit Fuxi H3
\tDriver: PipeWire
\tVolume: front-left: 45875 /  70% / -9.31 dB,   front-right: 45875 /  70% / -9.31 dB
\tMute: yes
\tProperties:
\t\tdevice.description = "Havit Fuxi H3"
\t\tnode.nick = "Fuxi H3"
"""

        pactl_sources = """Source #1
\tState: RUNNING
\tName: alsa_input.pci-0000_00_1f.3.analog-stereo
\tDescription: Built-in Audio Analog Stereo
\tDriver: PipeWire
\tVolume: front-left: 52428 /  80% / -5.79 dB,   front-right: 52428 /  80% / -5.79 dB
\tMute: no
\tProperties:
\t\tdevice.description = "Microfone Interno"
\t\tnode.nick = "ALC887-VD Mic"

Source #2
\tState: RUNNING
\tName: alsa_output.pci-0000_00_1f.3.analog-stereo.monitor
\tDescription: Monitor of Built-in Audio Analog Stereo
\tDriver: PipeWire
\tVolume: front-left: 65536 / 100% / 0.00 dB,   front-right: 65536 / 100% / 0.00 dB
\tMute: no
\tProperties:
\t\tdevice.class = "monitor"

Source #3
\tState: SUSPENDED
\tName: bluez_input.01_92_25_27_09_76
\tDescription: Havit Fuxi H3 Mic
\tDriver: PipeWire
\tVolume: mono: 32768 /  50% / -18.06 dB
\tMute: yes
\tProperties:
\t\tdevice.description = "Microfone Fuxi H3"
"""

        pactl_sink_inputs = """Sink Input #12
\tDriver: PipeWire
\tSink: 1
\tVolume: front-left: 55705 /  85% / -4.26 dB,   front-right: 55705 /  85% / -4.26 dB
\tMute: no
\tCorked: no
\tProperties:
\t\tapplication.name = "Spotify"
\t\tapplication.process.binary = "spotify"
\t\tapplication.icon_name = "spotify-client"
\t\tmedia.name = "Spotify"

Sink Input #18
\tDriver: PipeWire
\tSink: 1
\tVolume: front-left: 32768 /  50% / -18.06 dB,   front-right: 32768 /  50% / -18.06 dB
\tMute: yes
\tCorked: yes
\tProperties:
\t\tapplication.name = "Brave"
\t\tapplication.process.binary = "brave"
\t\tmedia.name = "YouTube Video Playback"
"""

        def fake_runner(cmd: list[str]) -> tuple[int, str, str]:
            if cmd == ["pactl", "get-default-sink"]:
                return 0, "alsa_output.pci-0000_00_1f.3.analog-stereo\n", ""
            if cmd == ["pactl", "get-default-source"]:
                return 0, "alsa_input.pci-0000_00_1f.3.analog-stereo\n", ""
            if cmd == ["pactl", "list", "sinks"]:
                return 0, pactl_sinks, ""
            if cmd == ["pactl", "list", "sources"]:
                return 0, pactl_sources, ""
            if cmd == ["pactl", "list", "sink-inputs"]:
                return 0, pactl_sink_inputs, ""
            return 1, "", f"Unknown command: {cmd}"

        mgr = AudioMixerManager(cmd_runner=fake_runner)
        state = mgr.get_state()

        # 1. Master Output
        master = state["master"]
        self.assertEqual(master["name"], "alsa_output.pci-0000_00_1f.3.analog-stereo")
        self.assertEqual(master["volume"], 100)
        self.assertFalse(master["muted"])
        self.assertEqual(master["state"], "RUNNING")

        # 2. Outputs list
        outputs = state["outputs"]
        self.assertEqual(len(outputs), 2)
        out_by_name = {o["name"]: o for o in outputs}
        self.assertTrue(out_by_name["alsa_output.pci-0000_00_1f.3.analog-stereo"]["is_default"])
        self.assertFalse(out_by_name["bluez_output.01_92_25_27_09_76.1"]["is_default"])
        self.assertEqual(out_by_name["bluez_output.01_92_25_27_09_76.1"]["volume"], 70)
        self.assertTrue(out_by_name["bluez_output.01_92_25_27_09_76.1"]["muted"])

        # 3. Mic & Inputs list (.monitor must be excluded)
        mic = state["mic"]
        self.assertEqual(mic["name"], "alsa_input.pci-0000_00_1f.3.analog-stereo")
        self.assertEqual(mic["volume"], 80)
        self.assertFalse(mic["muted"])

        inputs = state["inputs"]
        self.assertEqual(len(inputs), 2)  # Source #2 (.monitor) must be excluded
        in_names = [i["name"] for i in inputs]
        self.assertNotIn("alsa_output.pci-0000_00_1f.3.analog-stereo.monitor", in_names)
        self.assertIn("alsa_input.pci-0000_00_1f.3.analog-stereo", in_names)
        self.assertIn("bluez_input.01_92_25_27_09_76", in_names)

        # 4. Apps (sink inputs)
        apps = state["apps"]
        self.assertEqual(len(apps), 2)
        app_by_id = {a["id"]: a for a in apps}

        spot = app_by_id[12]
        self.assertEqual(spot["app_name"], "Spotify")
        self.assertEqual(spot["icon_name"], "spotify-client")
        self.assertEqual(spot["volume"], 85)
        self.assertFalse(spot["muted"])
        self.assertFalse(spot["corked"])

        brave = app_by_id[18]
        self.assertEqual(brave["app_name"], "Brave")
        self.assertEqual(brave["volume"], 50)
        self.assertTrue(brave["muted"])
        self.assertTrue(brave["corked"])

    def test_mixer_controls_dispatch_and_clamping(self) -> None:
        executed_cmds: list[list[str]] = []

        def recording_runner(cmd: list[str]) -> tuple[int, str, str]:
            executed_cmds.append(cmd)
            return 0, "", ""

        mgr = AudioMixerManager(cmd_runner=recording_runner)

        # Master volume & mute
        ok, _ = mgr.set_master_volume(75)
        self.assertTrue(ok)
        self.assertEqual(executed_cmds[-1], ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "75%"])

        # Clamping
        mgr.set_master_volume(-10)
        self.assertEqual(executed_cmds[-1], ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "0%"])
        mgr.set_master_volume(200)
        self.assertEqual(executed_cmds[-1], ["pactl", "set-sink-volume", "@DEFAULT_SINK@", "150%"])

        ok_mute, _ = mgr.toggle_master_mute()
        self.assertTrue(ok_mute)
        self.assertEqual(executed_cmds[-1], ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])

        # Switch default sink
        ok_sink, _ = mgr.set_default_sink("bluez_output.dev")
        self.assertTrue(ok_sink)
        self.assertEqual(executed_cmds[-1], ["pactl", "set-default-sink", "bluez_output.dev"])

        # Mic controls
        ok_mic, _ = mgr.set_mic_volume(60)
        self.assertTrue(ok_mic)
        self.assertEqual(executed_cmds[-1], ["pactl", "set-source-volume", "@DEFAULT_SOURCE@", "60%"])

        ok_mic_mute, _ = mgr.toggle_mic_mute()
        self.assertTrue(ok_mic_mute)
        self.assertEqual(executed_cmds[-1], ["pactl", "set-source-mute", "@DEFAULT_SOURCE@", "toggle"])

        ok_src, _ = mgr.set_default_source("alsa_input.dev")
        self.assertTrue(ok_src)
        self.assertEqual(executed_cmds[-1], ["pactl", "set-default-source", "alsa_input.dev"])

        # Per-app controls
        ok_app_vol, _ = mgr.set_app_volume(42, 55)
        self.assertTrue(ok_app_vol)
        self.assertEqual(executed_cmds[-1], ["pactl", "set-sink-input-volume", "42", "55%"])

        ok_app_mute, _ = mgr.toggle_app_mute(42)
        self.assertTrue(ok_app_mute)
        self.assertEqual(executed_cmds[-1], ["pactl", "set-sink-input-mute", "42", "toggle"])

        # Validation errors on invalid arguments
        self.assertFalse(mgr.set_master_volume("invalid")[0])
        self.assertFalse(mgr.set_default_sink("")[0])
        self.assertFalse(mgr.set_mic_volume("bad")[0])
        self.assertFalse(mgr.set_default_source("")[0])
        self.assertFalse(mgr.set_app_volume("bad", 50)[0])
        self.assertFalse(mgr.toggle_app_mute("bad")[0])


class TestMediaPlayerManager(unittest.TestCase):
    """Tests MediaPlayerManager MPRIS2 player discovery, GVariant parsing, and transport controls."""

    def test_parse_gvariant_helper(self) -> None:
        raw_gvariant = (
            "({'PlaybackStatus': <'Playing'>, "
            "'Metadata': <{'xesam:title': <'Kids'>, 'xesam:artist': <['MGMT']>, "
            "'xesam:album': <'Oracular Spectacular'>, 'mpris:length': <uint64 302000000>, "
            "'mpris:artUrl': <'https://i.scdn.co/image/ab67616d0000b273'>}>, "
            "'Position': <int64 120000000>, 'CanGoNext': <true>, 'CanGoPrevious': <true>, "
            "'CanPlay': <true>, 'CanPause': <true>},)"
        )
        res = parse_gvariant(raw_gvariant)
        self.assertIsInstance(res, tuple)
        d = res[0]
        self.assertEqual(d["PlaybackStatus"], "Playing")
        self.assertEqual(d["Position"], 120000000)
        self.assertTrue(d["CanGoNext"])
        self.assertEqual(d["Metadata"]["xesam:title"], "Kids")
        self.assertEqual(d["Metadata"]["xesam:artist"], ["MGMT"])
        self.assertEqual(d["Metadata"]["mpris:length"], 302000000)

    def test_list_players_and_spotify_priority(self) -> None:
        dbus_names_resp = "(['org.freedesktop.DBus', 'org.mpris.MediaPlayer2.brave.instance123', 'org.mpris.MediaPlayer2.spotify'],)"

        def fake_runner(cmd: list[str]) -> tuple[int, str, str]:
            if any("ListNames" in c for c in cmd):
                return 0, dbus_names_resp, ""
            return 1, "", "error"

        player_mgr = MediaPlayerManager(cmd_runner=fake_runner)
        players = player_mgr.list_players()
        self.assertEqual(len(players), 2)
        self.assertIn("org.mpris.MediaPlayer2.spotify", players)
        self.assertIn("org.mpris.MediaPlayer2.brave.instance123", players)
        # Spotify has primary priority
        self.assertEqual(player_mgr.get_active_bus_name(), "org.mpris.MediaPlayer2.spotify")

    def test_get_state_playing_telemetry_and_progress(self) -> None:
        gdbus_output = (
            "({'PlaybackStatus': <'Playing'>, "
            "'Metadata': <{'xesam:title': <'Time to Pretend'>, 'xesam:artist': <['MGMT']>, "
            "'xesam:album': <'Oracular Spectacular'>, 'mpris:length': <uint64 261000000>, "
            "'mpris:artUrl': <'https://open.spotify.com/image/123'>}>, "
            "'Position': <int64 105000000>, 'CanGoNext': <true>, 'CanGoPrevious': <true>, "
            "'CanPlay': <true>, 'CanPause': <true>},)"
        )

        def fake_runner(cmd: list[str]) -> tuple[int, str, str]:
            if any("ListNames" in c for c in cmd):
                return 0, "(['org.mpris.MediaPlayer2.spotify'],)", ""
            if any("Properties.GetAll" in c for c in cmd):
                return 0, gdbus_output, ""
            return 1, "", "error"

        player_mgr = MediaPlayerManager(cmd_runner=fake_runner)
        state = player_mgr.get_state()

        self.assertTrue(state["available"])
        self.assertEqual(state["player_name"], "Spotify")
        self.assertEqual(state["status"], "Playing")
        self.assertEqual(state["title"], "Time to Pretend")
        self.assertEqual(state["artist"], "MGMT")
        self.assertEqual(state["album"], "Oracular Spectacular")
        self.assertEqual(state["art_url"], "https://open.spotify.com/image/123")
        self.assertEqual(state["position_sec"], 105)
        self.assertEqual(state["length_sec"], 261)
        self.assertEqual(state["progress_pct"], 40.2)
        self.assertTrue(state["can_go_next"])
        self.assertTrue(state["can_go_previous"])
        self.assertTrue(state["can_play"])
        self.assertTrue(state["can_pause"])

    def test_transport_controls_dispatch(self) -> None:
        executed_cmds: list[list[str]] = []

        def fake_runner(cmd: list[str]) -> tuple[int, str, str]:
            executed_cmds.append(cmd)
            if any("ListNames" in c for c in cmd):
                return 0, "(['org.mpris.MediaPlayer2.spotify'],)", ""
            return 0, "()", ""

        player_mgr = MediaPlayerManager(cmd_runner=fake_runner)

        # PlayPause
        ok_pp, _ = player_mgr.play_pause()
        self.assertTrue(ok_pp)
        self.assertIn("org.mpris.MediaPlayer2.Player.PlayPause", executed_cmds[-1])

        # Next
        ok_nxt, _ = player_mgr.next_track()
        self.assertTrue(ok_nxt)
        self.assertIn("org.mpris.MediaPlayer2.Player.Next", executed_cmds[-1])

        # Previous
        ok_prev, _ = player_mgr.previous_track()
        self.assertTrue(ok_prev)
        self.assertIn("org.mpris.MediaPlayer2.Player.Previous", executed_cmds[-1])

        # Explicit bus name
        ok_exp, _ = player_mgr.play_pause("org.mpris.MediaPlayer2.vlc")
        self.assertTrue(ok_exp)
        self.assertIn("org.mpris.MediaPlayer2.vlc", executed_cmds[-1])

        # When no player is available
        empty_mgr = MediaPlayerManager(cmd_runner=lambda cmd: (0, "()", ""))
        self.assertFalse(empty_mgr.play_pause()[0])
        self.assertFalse(empty_mgr.next_track()[0])
        self.assertFalse(empty_mgr.previous_track()[0])


if __name__ == "__main__":
    unittest.main()

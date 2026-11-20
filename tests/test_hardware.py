"""Automated unit tests for src/dpi_core/hardware.py (100% mocked, CI-safe)."""

from __future__ import annotations

import errno
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from dpi_core.hardware import (  # noqa: E402
    AjazzMouseDriver,
    EVIOCSFF,
    FuxiHeadsetDriver,
    GamepadDriver,
    HardwareHubManager,
    K500KeyboardDriver,
    build_packet,
    is_activity_fresh,
    validate_hid_frame,
    verify_checksum,
)


def _make_fake_hidraw_node(
    hidraw_root: Path,
    name: str,
    vid: str,
    pid: str,
    hid_name: str = "Test HID Device",
    has_input: bool = False,
    report_descriptor: bytes = b"",
) -> Path:
    node = hidraw_root / name / "device"
    node.mkdir(parents=True, exist_ok=True)
    hid_id = f"0003:0000{vid.upper()}:0000{pid.upper()}"
    (node / "uevent").write_text(
        f"HID_ID={hid_id}\nHID_NAME={hid_name}\nHID_PHYS=usb-0000:00:14.0-1/input0\n",
        encoding="utf-8",
    )
    if has_input:
        (node / "input").mkdir(exist_ok=True)
    if report_descriptor:
        (node / "report_descriptor").write_bytes(report_descriptor)
    return node


def _make_fake_power_supply(
    power_root: Path,
    name: str,
    capacity: int,
    status: str = "Discharging",
    model_name: str = "",
    manufacturer: str = "",
) -> Path:
    sup = power_root / name
    sup.mkdir(parents=True, exist_ok=True)
    (sup / "capacity").write_text(str(capacity), encoding="utf-8")
    (sup / "status").write_text(status, encoding="utf-8")
    if model_name:
        (sup / "model_name").write_text(model_name, encoding="utf-8")
    if manufacturer:
        (sup / "manufacturer").write_text(manufacturer, encoding="utf-8")
    (sup / "uevent").write_text(
        f"POWER_SUPPLY_CAPACITY={capacity}\nPOWER_SUPPLY_STATUS={status}\n",
        encoding="utf-8",
    )
    return sup


class TestAjazzMouseDriver(unittest.TestCase):
    """Tests for AJAZZ AJ179 V2 HID packet protocol, standby cache, and controls."""

    def test_build_packet_and_verify_checksum_33b(self) -> None:
        payload = bytes([0x02, 0x40, 0x06])  # e.g. stage 2, 1600 DPI LE
        pkt = build_packet(AjazzMouseDriver.CMD_DPI, write=True, payload=payload)

        self.assertEqual(len(pkt), 33)
        self.assertEqual(pkt[0], 0x00)  # Report ID

        body = pkt[1:]
        self.assertEqual(len(body), 32)
        self.assertEqual(body[0], AjazzMouseDriver.CMD_DPI)
        self.assertEqual(body[2], 0x01)
        self.assertEqual(body[3], len(payload))
        self.assertEqual(body[4 : 4 + len(payload)], payload)
        self.assertEqual(body[31], sum(body[4:31]) & 0xFF)
        self.assertTrue(verify_checksum(body))

        read_pkt = AjazzMouseDriver.build_packet(AjazzMouseDriver.CMD_BATTERY, write=False)
        self.assertEqual(len(read_pkt), 33)
        self.assertEqual(read_pkt[1 + 2], 0x00)
        self.assertEqual(read_pkt[1 + 3], 0)
        self.assertTrue(AjazzMouseDriver.verify_checksum(read_pkt[1:]))

    def test_verify_checksum_rejects_corrupted_or_wrong_size(self) -> None:
        pkt = build_packet(0x04, write=True, payload=bytes([85, 0]))
        body = bytearray(pkt[1:])
        body[31] ^= 0x01
        self.assertFalse(verify_checksum(bytes(body)))
        self.assertFalse(verify_checksum(b"\x00" * 31))
        self.assertFalse(verify_checksum(b"\x00" * 33))

    def test_build_packet_rejects_oversized_payload(self) -> None:
        with self.assertRaises(ValueError):
            build_packet(0x03, write=True, payload=b"A" * 28)

    def test_live_read_and_paw3395_standby_cache_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hidraw_root = root / "hidraw"
            power_root = root / "power"
            cache_path = root / "config" / "mouse_state.json"

            _make_fake_hidraw_node(
                hidraw_root,
                "hidraw1",
                "249a",
                "5c2f",
                hid_name="AJAZZ AJ179 V2 Wireless Receiver",
                has_input=False,
                report_descriptor=b"\x06\x00\xff\x95\x20",
            )

            driver = AjazzMouseDriver(
                cache_path=cache_path,
                hidraw_root=hidraw_root,
                power_supply_root=power_root,
            )

            # Build real read-only firmware frames (0x10, 0x12, 0x13, 0x14, 0x17)
            info_frame = bytearray(32)
            info_frame[0] = driver.CMD_INFO
            info_frame[1] = 0x00
            info_frame[2] = 0x01
            info_frame[3] = 0x0B
            info_frame[12] = 0x00  # not charging
            info_frame[13] = 78    # 78%

            dpi_frame = bytearray(32)
            dpi_frame[0] = driver.CMD_DPI_READ
            dpi_frame[1] = 0x00
            dpi_frame[2] = 0x01
            dpi_frame[3] = 0x19
            dpi_frame[4] = (3 << 4) | 0x06  # active stage = 3
            stages = [400, 950, 1200, 3200, 2400, 6400]
            for idx, d in enumerate(stages):
                raw = d // 50
                lo, hi = raw & 0xFF, (raw >> 8) & 0xFF
                dpi_frame[5 + 4 * idx : 9 + 4 * idx] = bytes([lo, hi, lo, hi])

            poll_frame = bytearray(32)
            poll_frame[0] = driver.CMD_POLLING_READ
            poll_frame[1] = 0x00
            poll_frame[2] = 0x01
            poll_frame[4] = 0x02  # 500 Hz

            led_frame = bytearray(32)
            led_frame[0] = driver.CMD_LED_READ
            led_frame[1] = 0x00
            led_frame[2] = 0x01
            led_frame[3] = 0x12
            colors = [
                (255, 0, 0),
                (0, 255, 0),
                (0, 0, 255),
                (0x22, 0xC5, 0x5E),  # stage 3 -> #22C55E
                (255, 255, 0),
                (255, 0, 255),
            ]
            for idx, (r, g, b) in enumerate(colors):
                led_frame[4 + 3 * idx : 7 + 3 * idx] = bytes([r, g, b])

            sleep_frame = bytearray(32)
            sleep_frame[0] = driver.CMD_SLEEP_READ
            sleep_frame[1] = 0x00
            sleep_frame[2] = 0x01
            sleep_frame[4] = 90  # 90 * 10 = 900s

            responses = {
                driver.CMD_INFO: bytes(info_frame),
                driver.CMD_DPI_READ: bytes(dpi_frame),
                driver.CMD_POLLING_READ: bytes(poll_frame),
                driver.CMD_LED_READ: bytes(led_frame),
                driver.CMD_SLEEP_READ: bytes(sleep_frame),
            }

            with mock.patch.object(
                driver,
                "_hid_exchange",
                side_effect=lambda dev, cmd, write=False, payload=b"", length_override=None: responses.get(cmd),
            ):
                live = driver.read_state()

            self.assertTrue(live["connected"])
            self.assertTrue(live["active"])
            self.assertFalse(live["standby"])
            self.assertFalse(live["cached"])
            self.assertEqual(live["battery"], 78)
            self.assertEqual(live["connection_type"], "2.4GHz")
            self.assertEqual(live["dpi_stages"], stages)
            self.assertEqual(live["current_dpi"], 3200)
            self.assertEqual(live["active_dpi_stage"], 3)
            self.assertEqual(live["polling_rate"], 500)
            self.assertEqual(live["led_color"], "#22C55E")
            self.assertEqual(live["sleep_seconds"], 900)
            self.assertTrue(cache_path.exists())

            # Simulate PAW3395 deep sleep: receiver replies with NACK 0xFF / empty payload
            nack = bytearray(32)
            nack[0] = driver.CMD_INFO
            nack[2] = 0xFF
            nack[3] = 0
            nack[31] = sum(nack[4:31]) & 0xFF

            with mock.patch.object(driver, "_hid_exchange", return_value=bytes(nack)):
                standby_state = driver.read_state()

            self.assertTrue(standby_state["connected"])
            self.assertFalse(standby_state["active"])
            self.assertTrue(standby_state["standby"])
            self.assertTrue(standby_state["cached"])
            self.assertEqual(standby_state["connection_type"], "Standby")
            self.assertEqual(standby_state["battery"], 78)
            self.assertEqual(standby_state["current_dpi"], 3200)
            self.assertEqual(standby_state["polling_rate"], 500)

    def test_read_state_never_sends_write_opcodes(self) -> None:
        """BUG-001 safety regression guard: read_state() must NEVER send write opcodes (0x02..0x09)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hidraw_root = root / "hidraw"
            _make_fake_hidraw_node(hidraw_root, "hidraw4", "249a", "5c2f", hid_name="AJAZZ AJ179 V2")
            driver = AjazzMouseDriver(
                cache_path=root / "mouse_state.json",
                hidraw_root=hidraw_root,
                power_supply_root=root / "power",
            )

            seen_calls = []

            def spy_exchange(dev, cmd, write=False, payload=b"", length_override=None):
                seen_calls.append((cmd, write, payload))
                # Return valid 0x10 battery so sub-queries (0x13/0x12/0x14/0x17) also execute,
                # then return all-zeros/None for sub-queries to confirm no write fallback happens.
                if cmd == driver.CMD_INFO:
                    return bytes.fromhex("1000010b4e3632348401110100300100000000000000000000000000000000b2")
                return bytes(32)

            with mock.patch.object(driver, "_hid_exchange", side_effect=spy_exchange):
                driver.read_state()

            # Also test when 0x10 itself fails / returns None
            with mock.patch.object(driver, "_hid_exchange", side_effect=lambda d, c, write=False, payload=b"", length_override=None: (seen_calls.append((c, write, payload)) or None)):
                driver.read_state()

            self.assertGreater(len(seen_calls), 0)
            for cmd, write, _ in seen_calls:
                self.assertFalse(write, msg=f"read_state sent write=True for cmd=0x{cmd:02X}")
                self.assertNotIn(cmd, range(0x02, 0x0A), msg=f"read_state sent forbidden write opcode 0x{cmd:02X}")

    def test_set_dpi_sends_0x03_25_byte_stage_table(self) -> None:
        """BUG-001 fix guard: set_dpi(1200) must send cmd=0x03, write=0x01, len=0x25, 25B stage table."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hidraw_root = root / "hidraw"
            cache_path = root / "mouse_state.json"
            _make_fake_hidraw_node(hidraw_root, "hidraw4", "249a", "5c2f", hid_name="AJAZZ AJ179 V2")
            driver = AjazzMouseDriver(cache_path=cache_path, hidraw_root=hidraw_root)

            written_frames = []
            ack = bytearray(32)
            ack[0] = 0x03
            ack[1] = 0x00
            ack[2] = 0x01

            def fake_write(fd, data):
                written_frames.append(data)
                return len(data)

            with mock.patch("dpi_core.hardware.os.open", return_value=77), \
                 mock.patch("dpi_core.hardware.os.close"), \
                 mock.patch("dpi_core.hardware.fcntl.flock"), \
                 mock.patch("dpi_core.hardware.select.select", side_effect=[([], [], []), ([77], [], [])]), \
                 mock.patch("dpi_core.hardware.os.write", side_effect=fake_write), \
                 mock.patch("dpi_core.hardware.os.read", return_value=bytes(ack)):
                ok, _ = driver.set_dpi(1200)

            self.assertTrue(ok)
            self.assertEqual(len(written_frames), 1)
            frame33 = written_frames[0]
            self.assertEqual(len(frame33), 33)
            self.assertEqual(frame33[0], 0x00)
            body = frame33[1:]
            self.assertEqual(body[0], 0x03)
            self.assertEqual(body[2], 0x01)
            self.assertEqual(body[3], 0x25)
            self.assertEqual(body[4], (2 << 4) | 0x06)  # stage 2 = 1200 DPI, 6 stages

            expected_stages = [400, 950, 1200, 1600, 2400, 3200]
            for idx, d in enumerate(expected_stages):
                raw = d // 50
                lo, hi = raw & 0xFF, (raw >> 8) & 0xFF
                self.assertEqual(list(body[5 + 4 * idx : 9 + 4 * idx]), [lo, hi, lo, hi])
            self.assertTrue(verify_checksum(body))

    def test_live_read_0x10_device_info_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hidraw_root = root / "hidraw"
            cache_path = root / "config" / "mouse_state.json"

            _make_fake_hidraw_node(
                hidraw_root,
                "hidraw4",
                "249a",
                "5c2f",
                hid_name="AJAZZ AJ179 V2 Wireless Receiver",
                has_input=False,
                report_descriptor=b"\x06\x00\xff\x95\x20",
            )

            driver = AjazzMouseDriver(
                cache_path=cache_path,
                hidraw_root=hidraw_root,
                power_supply_root=root / "power",
            )
            real_0x10 = bytes.fromhex(
                "1000010b4e3632348401110100300100000000000000000000000000000000b2"
            )
            with mock.patch.object(
                driver,
                "_hid_exchange",
                side_effect=lambda dev, cmd, write=False, payload=b"": (
                    real_0x10 if cmd == driver.CMD_INFO else None
                ),
            ):
                state = driver.read_state()

            self.assertTrue(state["connected"])
            self.assertTrue(state["active"])
            self.assertFalse(state["standby"])
            self.assertFalse(state["cached"])
            self.assertEqual(state["battery"], 48)
            self.assertFalse(state["charging"])
            self.assertEqual(state["connection_type"], "2.4GHz")

    def test_mouse_controls_validation_and_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hidraw_root = root / "hidraw"
            cache_path = root / "mouse_state.json"
            _make_fake_hidraw_node(hidraw_root, "hidraw0", "248a", "0001", hid_name="AJAZZ Mouse")
            driver = AjazzMouseDriver(cache_path=cache_path, hidraw_root=hidraw_root)

            with mock.patch.object(driver, "_send_write_control", return_value=(True, "/dev/hidraw0")) as m_send:
                ok, _ = driver.set_dpi(3200)
                self.assertTrue(ok)
                ok, _ = driver.set_polling_rate(1000)
                self.assertTrue(ok)
                ok, _ = driver.set_led_color("#a855f7")
                self.assertTrue(ok)
                ok, _ = driver.set_sleep_timeout(600)
                self.assertTrue(ok)
                self.assertEqual(m_send.call_count, 4)

                # Invalid parameters should fail without calling _send_write_control
                m_send.reset_mock()
                self.assertFalse(driver.set_dpi(200)[0])
                self.assertFalse(driver.set_dpi(30000)[0])
                self.assertFalse(driver.set_polling_rate(333)[0])
                self.assertFalse(driver.set_led_color("ZZZZZZ")[0])
                self.assertFalse(driver.set_sleep_timeout(10)[0])
                m_send.assert_not_called()


class TestFuxiHeadsetDriver(unittest.TestCase):
    """Tests for Havit Fuxi H3 dual BT/2.4GHz detection and ALSA numid=9 fix."""

    def test_bluetooth_mode_detection_and_battery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hidraw_root = root / "hidraw"
            power_root = root / "power"

            def fake_run(cmd, timeout=2.5):
                if cmd[:2] == ["bluetoothctl", "info"]:
                    return (
                        0,
                        "Device 01:92:25:27:09:76 (public)\n"
                        "\tName: Fuxi-H3\n"
                        "\tConnected: yes\n"
                        "\tBattery Percentage: 0x52 (82)\n",
                        "",
                    )
                if cmd[:3] == ["pactl", "list", "cards"]:
                    return (
                        0,
                        "Card #55\n"
                        "\tName: bluez_card.01_92_25_27_09_76\n"
                        "\tProfiles:\n"
                        "\t\ta2dp-sink: High Fidelity Playback (A2DP Sink) (sinks: 1, sources: 0, priority: 10, available: yes)\n"
                        "\t\theadset-head-unit: Headset Head Unit (HSP/HFP) (sinks: 1, sources: 1, priority: 1, available: yes)\n"
                        "\tActive Profile: a2dp-sink\n",
                        "",
                    )
                if cmd[:3] == ["pactl", "list", "sinks"]:
                    return (
                        0,
                        "Sink #99\n"
                        "\tState: RUNNING\n"
                        "\tName: bluez_output.01_92_25_27_09_76.1\n"
                        "\tMute: no\n"
                        "\tVolume: front-left: 45875 /  70% / -9.30 dB,   front-right: 45875 /  70% / -9.30 dB\n",
                        "",
                    )
                return (1, "", "unhandled")

            drv = FuxiHeadsetDriver(
                state_dir=root / "state",
                hidraw_root=hidraw_root,
                power_supply_root=power_root,
                cmd_runner=fake_run,
            )
            state = drv.read_state()

            self.assertTrue(state["connected"])
            self.assertTrue(state["active"])
            self.assertEqual(state["connection_type"], "Bluetooth")
            self.assertEqual(state["battery"], 82)
            self.assertEqual(state["volume"], 70)
            self.assertFalse(state["muted"])
            self.assertEqual(state["active_profile"], "a2dp-sink")
            self.assertIn("headset-head-unit", state["available_profiles"])
            self.assertFalse(state["alsa_zero_bug"])

    def test_24ghz_mode_and_alsa_zero_bug_fix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hidraw_root = root / "hidraw"
            power_root = root / "power"
            _make_fake_hidraw_node(hidraw_root, "hidraw3", "040b", "0897", hid_name="Fuxi-H3 Dongle")
            _make_fake_power_supply(power_root, "hid-fuxi-battery", 64, "Charging", model_name="Fuxi H3")

            calls = []

            def fake_run(cmd, timeout=2.5):
                calls.append(cmd)
                if cmd[:2] == ["bluetoothctl", "info"]:
                    return (0, "Connected: no\n", "")
                if cmd[:3] == ["upower", "-d"]:
                    return (0, "", "")
                if cmd[:3] == ["pactl", "list", "cards"]:
                    return (
                        0,
                        "Card #12\n"
                        "\tName: alsa_card.usb-XiiSound_Fuxi-H3-00\n"
                        "\tProfiles:\n"
                        "\t\toutput:analog-stereo+input:mono-fallback: Analog Stereo (sinks: 1, sources: 1, available: yes)\n"
                        "\tActive Profile: output:analog-stereo+input:mono-fallback\n",
                        "",
                    )
                if cmd[:3] == ["pactl", "list", "sinks"]:
                    return (
                        0,
                        "Sink #12\n"
                        "\tState: IDLE\n"
                        "\tName: alsa_output.usb-XiiSound_Fuxi-H3-00.analog-stereo\n"
                        "\tMute: no\n"
                        "\tVolume: front-left: 65536 / 100% / 0.00 dB\n",
                        "",
                    )
                if cmd == ["amixer", "-c", "FuxiH3", "cget", "numid=9"]:
                    return (0, "numid=9,iface=MIXER,name='PCM Playback Volume'\n  : values=0,0\n", "")
                if cmd == ["amixer", "-c", "FuxiH3", "cget", "numid=7"]:
                    return (0, "numid=7,iface=MIXER,name='PCM Playback Switch'\n  : values=on\n", "")
                if cmd[:3] == ["amixer", "-c", "FuxiH3"] and "cset" in cmd:
                    return (0, "values=100,100\n", "")
                if cmd[:2] == ["pactl", "set-sink-volume"] or cmd[:2] == ["pactl", "set-sink-mute"]:
                    return (0, "", "")
                return (1, "", "err")

            drv = FuxiHeadsetDriver(
                state_dir=root / "state",
                hidraw_root=hidraw_root,
                power_supply_root=power_root,
                cmd_runner=fake_run,
            )
            state = drv.read_state()
            self.assertTrue(state["connected"])
            self.assertEqual(state["connection_type"], "2.4GHz")
            self.assertEqual(state["battery"], 64)
            self.assertTrue(state["charging"])
            self.assertTrue(state["alsa_zero_bug"])

            ok, msg = drv.fix_alsa_volume()
            self.assertTrue(ok)
            self.assertIn("numid=9=100,100", msg)
            self.assertIn(["amixer", "-c", "FuxiH3", "cset", "numid=9", "100,100"], calls)
            self.assertIn(["amixer", "-c", "FuxiH3", "cset", "numid=7", "on"], calls)

            ok_eq, _ = drv.set_eq_preset("gaming")
            self.assertTrue(ok_eq)
            self.assertEqual(drv.read_state()["eq_preset"], "gaming")
            self.assertTrue((root / "state" / "fuxi_eq.conf").exists())


class TestK500KeyboardDriverSafeMode(unittest.TestCase):
    """Tests strict Hardware Safe Mode protections on Machenike K500-B94 (Sino Wealth MCU)."""

    def test_validate_hid_frame_blocks_empty_zeros_and_invalid_sizes(self) -> None:
        # Empty frame
        with self.assertRaises(ValueError):
            validate_hid_frame(b"")

        # All-zero frames of valid sizes
        for size in (8, 16, 32, 33, 64, 65):
            with self.assertRaises(ValueError):
                validate_hid_frame(bytes(size))

        # Report ID non-zero but payload all-zero (33B and 65B)
        with self.assertRaises(ValueError):
            validate_hid_frame(b"\x01" + bytes(32))
        with self.assertRaises(ValueError):
            validate_hid_frame(b"\x01" + bytes(64))

        # Disallowed sizes
        for bad_size in (1, 7, 15, 31, 34, 128):
            with self.assertRaises(ValueError):
                validate_hid_frame(b"\xaa" * bad_size)

        # Valid non-zero frame succeeds validation
        valid = b"\x04" + b"\x11" + bytes(30)
        self.assertEqual(validate_hid_frame(valid), valid)

    def test_send_raw_packet_is_permanently_blocked_by_safe_mode(self) -> None:
        drv = K500KeyboardDriver()
        # Invalid/zero frames still raise ValueError first
        with self.assertRaises(ValueError):
            drv.send_raw_packet(b"")
        with self.assertRaises(ValueError):
            drv.send_raw_packet(bytes(32))
        # Even valid frames MUST be blocked by Hardware Safe Mode (RuntimeError)
        with self.assertRaises(RuntimeError):
            drv.send_raw_packet(b"\x04\x01" + bytes(30))

    def test_passive_read_state_leds_and_shortcuts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hidraw_root = root / "hidraw"
            leds_root = root / "leds"
            input_devs = root / "devices"

            _make_fake_hidraw_node(hidraw_root, "hidraw2", "258a", "0049", hid_name="Machenike K500-B94")
            for led_name, val in (("capslock", "1"), ("numlock", "0"), ("scrolllock", "1")):
                led_dir = leds_root / f"input5::{led_name}"
                (led_dir / "device" / "id").mkdir(parents=True, exist_ok=True)
                (led_dir / "device" / "id" / "vendor").write_text("258a\n", encoding="utf-8")
                (led_dir / "device" / "id" / "product").write_text("0049\n", encoding="utf-8")
                (led_dir / "brightness").write_text(f"{val}\n", encoding="utf-8")

            drv = K500KeyboardDriver(
                hidraw_root=hidraw_root,
                leds_root=leds_root,
                input_devices_path=input_devs,
            )
            state = drv.read_state()
            self.assertTrue(state["connected"])
            self.assertTrue(state["safe_mode"])
            self.assertEqual(state["connection_type"], "USB-C")
            self.assertEqual(
                state["leds"],
                {"capslock": True, "numlock": False, "scrolllock": True},
            )
            self.assertGreaterEqual(len(state["shortcuts"]), 4)


class TestGamepadDriver(unittest.TestCase):
    """Tests for EasySMX dual-node merge, GameSir 60s inactivity window, and ENOSYS rumble."""

    def test_is_activity_fresh_60s_window(self) -> None:
        self.assertFalse(is_activity_fresh(None, now_ts=1000.0))
        self.assertTrue(is_activity_fresh(1000.0, now_ts=1000.0, window=60.0))
        self.assertTrue(is_activity_fresh(940.0, now_ts=1000.0, window=60.0))
        self.assertFalse(is_activity_fresh(939.9, now_ts=1000.0, window=60.0))
        self.assertFalse(is_activity_fresh(1005.0, now_ts=1000.0, window=60.0))

    def test_easysmx_dual_node_consolidation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_devices = root / "devices"
            input_devices.write_text(
                'I: Bus=0003 Vendor=045e Product=028e Version=0110\n'
                'N: Name="Microsoft X-Box 360 pad"\n'
                'P: Phys=usb-0000:00:14.0-2/input0\n'
                'H: Handlers=event10 js0\n'
                'B: FF=0\n\n'
                'I: Bus=0003 Vendor=045e Product=028e Version=0110\n'
                'N: Name="Microsoft X-Box 360 pad"\n'
                'P: Phys=usb-0000:00:14.0-3/input0\n'
                'H: Handlers=event11 js1\n'
                'B: FF=1\n',
                encoding="utf-8",
            )

            drv = GamepadDriver(
                state_dir=root / "state",
                hidraw_root=root / "hidraw",
                input_devices_path=input_devices,
                power_supply_root=root / "power",
                activity_dir=root / "tmp",
                dev_input_root=root / "dev_input",
            )
            state = drv.read_state(now_ts=2000.0)
            self.assertTrue(state["connected"])
            self.assertTrue(state["active"])
            self.assertEqual(state["connected_count"], 1)
            self.assertEqual(len(state["controllers"]), 1)

            ctrl = state["controllers"][0]
            self.assertEqual(ctrl["id"], "easysmx_9124")
            self.assertTrue(ctrl["charging"])
            self.assertEqual(ctrl["connection_type"], "USB-C (Carregando) + Dongle 2.4GHz")
            self.assertTrue(ctrl["ff_supported"])
            self.assertTrue(ctrl["event_path"].endswith("event11"))

    def test_60s_inactivity_hides_gamepad_after_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_devices = root / "devices"
            input_devices.write_text(
                'I: Bus=0003 Vendor=045e Product=028e Version=0110\n'
                'N: Name="Microsoft X-Box 360 pad"\n'
                'P: Phys=usb-0000:00:14.0-1/input0\n'
                'H: Handlers=event14 js0\n'
                'B: FF=1\n',
                encoding="utf-8",
            )
            act_dir = root / "tmp"
            act_dir.mkdir()
            marker = act_dir / "dpi-gamepad-event14.active"
            marker.write_text("1000.0\n", encoding="utf-8")

            drv = GamepadDriver(
                state_dir=root / "state",
                hidraw_root=root / "hidraw",
                input_devices_path=input_devices,
                power_supply_root=root / "power",
                activity_dir=act_dir,
                dev_input_root=root / "dev_input",
            )

            # At +30s -> still active
            s_fresh = drv.read_state(now_ts=1030.0)
            self.assertTrue(s_fresh["active"])
            self.assertEqual(s_fresh["active_count"], 1)

            # At +65s -> hidden from active bar (EasySMX dongle without fresh activity)
            s_stale = drv.read_state(now_ts=1065.0)
            self.assertTrue(s_stale["connected"])
            self.assertFalse(s_stale["active"])
            self.assertEqual(s_stale["active_count"], 0)

    def test_gamesir_nova_lite_xinput_mode_and_standby(self) -> None:
        """BUG-004: GameSir Nova Lite 3537:1040 (XInput) vs 3537:2106 (Standby)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_devices = root / "devices"
            # 3537:1040 creates Generic X-Box pad (event11 js0) + Keyboard (event14)
            input_devices.write_text(
                'I: Bus=0003 Vendor=3537 Product=1040 Version=0110\n'
                'N: Name="2.4G XBOX 360 For Windows Keyboard"\n'
                'P: Phys=usb-0000:00:14.0-1/input1\n'
                'H: Handlers=event14\n'
                'B: FF=0\n\n'
                'I: Bus=0003 Vendor=3537 Product=1040 Version=0110\n'
                'N: Name="Generic X-Box pad"\n'
                'P: Phys=usb-0000:00:14.0-1/input0\n'
                'H: Handlers=event11 js0\n'
                'B: FF=1\n',
                encoding="utf-8",
            )

            drv = GamepadDriver(
                state_dir=root / "state",
                hidraw_root=root / "hidraw",
                input_devices_path=input_devices,
                power_supply_root=root / "power",
                activity_dir=root / "tmp",
                dev_input_root=root / "dev_input",
            )

            state = drv.read_state(now_ts=1000.0)
            self.assertTrue(state["connected"])
            self.assertTrue(state["active"])
            self.assertEqual(state["connected_count"], 1)
            self.assertEqual(state["active_count"], 1)

            ctrl = state["controllers"][0]
            self.assertEqual(ctrl["id"], "gamesir_nova_lite")
            self.assertEqual(ctrl["name"], "GameSir Nova Lite")
            self.assertTrue(ctrl["active"])
            self.assertEqual(ctrl["connection_type"], "2.4GHz (XInput)")
            self.assertTrue(ctrl["event_path"].endswith("event11"))
            self.assertTrue(ctrl["ff_supported"])

            # Standby mode: no active inputs, only hidraw dongle 3537:2106
            input_devices.write_text("", encoding="utf-8")
            hidraw_root = root / "hidraw"
            _make_fake_hidraw_node(hidraw_root, "hidraw1", "3537", "2106", hid_name="2.4G Receiver")
            drv_sb = GamepadDriver(
                state_dir=root / "state",
                hidraw_root=hidraw_root,
                input_devices_path=input_devices,
                power_supply_root=root / "power",
                activity_dir=root / "tmp",
                dev_input_root=root / "dev_input",
            )
            state_sb = drv_sb.read_state(now_ts=1000.0)
            self.assertTrue(state_sb["connected"])
            self.assertFalse(state_sb["active"])
            self.assertEqual(state_sb["active_count"], 0)
            ctrl_sb = state_sb["controllers"][0]
            self.assertFalse(ctrl_sb["active"])
            self.assertEqual(ctrl_sb["connection_type"], "Standby (Dongle 2.4GHz)")

    def test_test_rumble_enosys_error_and_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_devices = root / "devices"
            input_devices.write_text(
                'I: Bus=0003 Vendor=3537 Product=1041 Version=0110\n'
                'N: Name="GameSir Nova Lite"\n'
                'P: Phys=usb-0000:00:14.0-1/input0\n'
                'H: Handlers=event14 js0\n'
                'B: FF=1\n',
                encoding="utf-8",
            )
            drv = GamepadDriver(
                state_dir=root / "state",
                hidraw_root=root / "hidraw",
                input_devices_path=input_devices,
                power_supply_root=root / "power",
                activity_dir=root / "tmp",
                dev_input_root=root / "dev_input",
            )

            # ENOSYS (38) must return helpful XInput instructions
            with mock.patch("dpi_core.hardware.os.open", return_value=42), \
                 mock.patch("dpi_core.hardware.os.close") as m_close, \
                 mock.patch("dpi_core.hardware.fcntl.ioctl", side_effect=OSError(errno.ENOSYS, "Function not implemented")):
                ok, msg = drv.test_rumble("gamesir_nova_lite")
            self.assertFalse(ok)
            self.assertIn("ENOSYS", msg)
            self.assertIn("M + Menu + View", msg)
            m_close.assert_called_once_with(42)

            # Successful rumble path (EVIOCSFF allocates effect_id=0 into buf[2:4])
            def fake_ioctl(fd, req, arg):
                if req == EVIOCSFF and isinstance(arg, bytearray):
                    arg[2:4] = b"\x00\x00"
                return 0

            with mock.patch("dpi_core.hardware.os.open", return_value=42), \
                 mock.patch("dpi_core.hardware.os.write", return_value=24) as m_write, \
                 mock.patch("dpi_core.hardware.os.close"), \
                 mock.patch("dpi_core.hardware.time.sleep"), \
                 mock.patch("dpi_core.hardware.fcntl.ioctl", side_effect=fake_ioctl) as m_ioctl:
                ok_rumble, msg_rumble = drv.test_rumble("gamesir_nova_lite")
            self.assertTrue(ok_rumble)
            self.assertIn("sucesso", msg_rumble.lower())
            self.assertEqual(m_write.call_count, 2)
            self.assertEqual(m_ioctl.call_args_list[0][0][1], EVIOCSFF)


class TestHardwareHubManager(unittest.TestCase):
    """Tests transition alerts and action dispatch in HardwareHubManager."""

    def test_transition_alerts_and_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_dir = Path(tmp) / "state"
            mouse = mock.MagicMock()
            headset = mock.MagicMock()
            gamepad = mock.MagicMock()
            keyboard = mock.MagicMock()

            mouse.read_state.return_value = {
                "id": "ajazz_aj179_v2",
                "name": "AJAZZ AJ179 V2",
                "connected": True,
                "active": True,
                "battery": 50,
                "charging": False,
                "connection_type": "2.4GHz",
            }
            headset.read_state.return_value = {
                "id": "havit_fuxi_h3",
                "name": "Havit Fuxi H3",
                "connected": False,
                "active": False,
                "battery": None,
                "charging": False,
                "connection_type": "Disconnected",
            }
            gamepad.read_state.return_value = {
                "id": "gamepads",
                "name": "Controles",
                "connected": False,
                "active": False,
                "charging": False,
                "battery": None,
                "connection_type": "Disconnected",
            }
            keyboard.read_state.return_value = {
                "id": "machenike_k500_b94",
                "name": "Machenike K500-B94",
                "connected": True,
                "active": True,
                "connection_type": "USB-C",
                "safe_mode": True,
            }

            mgr = HardwareHubManager(
                mouse=mouse,
                headset=headset,
                gamepad=gamepad,
                keyboard=keyboard,
                state_dir=state_dir,
            )
            snap1 = mgr.get_all_peripherals_snapshot(threshold=20)
            self.assertEqual(snap1["alerts"], [])

            # Transition: mouse drops to 9% (critical), headset connects & starts charging
            mouse.read_state.return_value["battery"] = 9
            headset.read_state.return_value.update(
                {"connected": True, "active": True, "charging": True, "connection_type": "Bluetooth"}
            )
            snap2 = mgr.get_all_peripherals_snapshot(threshold=20)
            alert_types = {(a["device"], a["type"], a["severity"]) for a in snap2["alerts"]}
            self.assertIn(("mouse", "low_battery", "critical"), alert_types)
            self.assertIn(("headset", "device_connected", "info"), alert_types)
            self.assertIn(("headset", "charging_started", "info"), alert_types)

            mouse.set_dpi.return_value = (True, "ok")
            self.assertEqual(mgr.dispatch_action("set_dpi", dpi=1600), (True, "ok"))
            headset.fix_alsa_volume.return_value = (True, "fixed")
            self.assertEqual(mgr.dispatch_action("fix_alsa"), (True, "fixed"))
            self.assertFalse(mgr.dispatch_action("unknown_action")[0])


if __name__ == "__main__":
    unittest.main()

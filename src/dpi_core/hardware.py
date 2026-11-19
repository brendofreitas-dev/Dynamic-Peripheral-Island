"""Pure-stdlib Linux hardware telemetry and control drivers for Dynamic Peripheral Island.

Supported peripherals:
1. AJAZZ AJ179 V2 wireless/wired mouse (VID 249a:5c2f & 248a family)
2. Havit Fuxi H3 dual-mode headset (2.4GHz USB 040b:0897 & Bluetooth 01:92:25:27:09:76)
3. Machenike K500-B94 wired keyboard (VID 258a:0049) — STRICT Hardware Safe Mode
4. GameSir Nova Lite (3537:1041 active / 3537:2106 standby) & EasySMX 9124 (045e:028e)
"""

from __future__ import annotations

import errno
import fcntl
import json
import os
import re
import select
import signal
import struct
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_STATE_DIR = Path.home() / ".config" / "dynamic-peripheral-island"

# Linux evdev / Force Feedback ioctl constants (x86_64 / 64-bit ABI)
EV_FF = 0x15
FF_RUMBLE = 0x50
FF_EFFECT_SIZE = 48
EVIOCSFF = 0x40304580  # _IOW('E', 0x80, struct ff_effect)
EVIOCRMFF = 0x40044581  # _IOW('E', 0x81, int)


# ---------------------------------------------------------------------------
# Generic pure helpers
# ---------------------------------------------------------------------------

def _c_env() -> Dict[str, str]:
    """Return a copy of the environment forcing C locale for deterministic CLI parsing."""
    env = dict(os.environ)
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    return env


def _run_cmd(cmd: List[str], timeout: float = 2.5) -> Tuple[int, str, str]:
    """Run an external system command safely without raising on missing binary or timeout."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_c_env(),
            check=False,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except FileNotFoundError:
        return 127, "", f"Comando não encontrado: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"Timeout ao executar: {' '.join(cmd)}"
    except OSError as exc:
        return 1, "", str(exc)


def _read_json_file(path: Path) -> Dict[str, Any]:
    """Read a JSON object from disk, returning {} if absent or invalid."""
    try:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json_file(path: Path, data: Dict[str, Any]) -> bool:
    """Atomically write a JSON object to disk."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def _parse_hid_uevent(uevent_path: Path) -> Dict[str, str]:
    """Parse key=value lines from a sysfs uevent file."""
    info: Dict[str, str] = {}
    try:
        text = uevent_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return info
    for raw_line in text.splitlines():
        if "=" in raw_line:
            key, value = raw_line.split("=", 1)
            info[key.strip()] = value.strip()
    return info


def _parse_hid_vid_pid(hid_id: str) -> Tuple[str, str]:
    """Extract lowercase 4-char hex (vid, pid) from HID_ID=BBBB:VVVVVVVV:PPPPPPPP."""
    parts = hid_id.split(":")
    if len(parts) != 3:
        return "", ""
    vid = parts[1][-4:].lower()
    pid = parts[2][-4:].lower()
    return vid, pid


def _scan_hidraw_nodes(hidraw_root: Path) -> List[Dict[str, Any]]:
    """Enumerate hidraw devices under hidraw_root with parsed VID/PID and metadata."""
    nodes: List[Dict[str, Any]] = []
    if not hidraw_root.exists():
        return nodes
    try:
        entries = sorted(hidraw_root.iterdir(), key=lambda p: p.name)
    except OSError:
        return nodes

    for entry in entries:
        if not entry.name.startswith("hidraw"):
            continue
        dev_dir = entry / "device"
        uevent = _parse_hid_uevent(dev_dir / "uevent")
        vid, pid = _parse_hid_vid_pid(uevent.get("HID_ID", ""))
        has_input = (dev_dir / "input").exists()
        rdesc = b""
        rdesc_path = dev_dir / "report_descriptor"
        try:
            if rdesc_path.exists():
                rdesc = rdesc_path.read_bytes()
        except OSError:
            pass
        nodes.append(
            {
                "name": entry.name,
                "dev_path": f"/dev/{entry.name}",
                "sys_path": entry,
                "vid": vid,
                "pid": pid,
                "hid_name": uevent.get("HID_NAME", ""),
                "hid_phys": uevent.get("HID_PHYS", ""),
                "has_input": has_input,
                "report_descriptor": rdesc,
            }
        )
    return nodes


def _scan_power_supply(power_root: Path) -> List[Dict[str, Any]]:
    """Read available Linux power_supply sysfs entries."""
    supplies: List[Dict[str, Any]] = []
    if not power_root.exists():
        return supplies
    try:
        entries = sorted(power_root.iterdir(), key=lambda p: p.name)
    except OSError:
        return supplies

    for entry in entries:
        if not entry.is_dir():
            continue
        item: Dict[str, Any] = {
            "name": entry.name,
            "path": entry,
            "uevent": _parse_hid_uevent(entry / "uevent"),
            "capacity": None,
            "status": "",
            "model_name": "",
            "manufacturer": "",
        }
        for attr in ("status", "model_name", "manufacturer"):
            p = entry / attr
            try:
                if p.exists():
                    item[attr] = p.read_text(encoding="utf-8", errors="ignore").strip()
            except OSError:
                pass
        cap_path = entry / "capacity"
        try:
            if cap_path.exists():
                item["capacity"] = int(cap_path.read_text(encoding="utf-8", errors="ignore").strip())
        except (OSError, ValueError):
            pass
        if item["capacity"] is None and "POWER_SUPPLY_CAPACITY" in item["uevent"]:
            try:
                item["capacity"] = int(item["uevent"]["POWER_SUPPLY_CAPACITY"])
            except ValueError:
                pass
        if not item["status"] and "POWER_SUPPLY_STATUS" in item["uevent"]:
            item["status"] = item["uevent"]["POWER_SUPPLY_STATUS"]
        supplies.append(item)
    return supplies


# ---------------------------------------------------------------------------
# Pure protocol & validation functions (testable independently)
# ---------------------------------------------------------------------------

def build_packet(cmd: int, write: bool = False, payload: bytes = b"") -> bytes:
    """Build a 33-byte AJAZZ vendor HID frame (0x00 Report ID + 32-byte payload).

    Layout of the 32-byte body `buf`:
      - buf[0] = cmd
      - buf[2] = 0x01 (write) | 0x00 (read)
      - buf[3] = len(payload)
      - buf[4 : 4 + len(payload)] = payload
      - buf[31] = sum(buf[4:31]) & 0xFF
    """
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError("payload deve ser bytes ou bytearray")
    if len(payload) > 27:
        raise ValueError(f"payload excede limite máximo de 27 bytes (recebido {len(payload)})")
    buf = bytearray(32)
    buf[0] = int(cmd) & 0xFF
    buf[2] = 0x01 if write else 0x00
    buf[3] = len(payload) & 0xFF
    if payload:
        buf[4 : 4 + len(payload)] = payload
    buf[31] = sum(buf[4:31]) & 0xFF
    return bytes([0x00]) + bytes(buf)


def verify_checksum(frame32: bytes) -> bool:
    """Validate checksum byte (index 31) of a 32-byte AJAZZ HID frame."""
    if not isinstance(frame32, (bytes, bytearray)) or len(frame32) != 32:
        return False
    expected = sum(frame32[4:31]) & 0xFF
    return frame32[31] == expected


VALID_K500_HID_FRAME_SIZES = frozenset({8, 16, 32, 33, 64, 65})


def validate_hid_frame(frame: bytes) -> bytes:
    """Strictly validate a raw HID frame before any access to the Machenike K500 Sino Wealth MCU.

    Raises ValueError on:
      - non-bytes input
      - empty frames
      - invalid frame lengths (not in {8, 16, 32, 33, 64, 65})
      - all-zero frames (or all-zero payload after Report ID byte)
    """
    if not isinstance(frame, (bytes, bytearray)):
        raise ValueError("Frame HID inválido: esperado bytes ou bytearray.")
    raw = bytes(frame)
    if len(raw) == 0:
        raise ValueError("Frame HID vazio bloqueado pelo Hardware Safe Mode.")
    if len(raw) not in VALID_K500_HID_FRAME_SIZES:
        raise ValueError(
            f"Tamanho de frame HID inválido ({len(raw)} bytes). "
            f"Permitidos: {sorted(VALID_K500_HID_FRAME_SIZES)}."
        )
    if all(b == 0 for b in raw):
        raise ValueError(
            "Frame HID composto apenas de zeros bloqueado pelo Hardware Safe Mode "
            "(proteção contra brick da MCU Sino Wealth)."
        )
    if len(raw) in (33, 65) and all(b == 0 for b in raw[1:]):
        raise ValueError(
            "Payload HID composto apenas de zeros bloqueado pelo Hardware Safe Mode."
        )
    return raw


def is_activity_fresh(
    last_ts: Optional[float],
    now_ts: Optional[float] = None,
    window: float = 60.0,
) -> bool:
    """Return True if `last_ts` falls within the last `window` seconds of `now_ts`."""
    if last_ts is None:
        return False
    now = time.time() if now_ts is None else float(now_ts)
    elapsed = now - float(last_ts)
    return 0.0 <= elapsed <= float(window)


# ---------------------------------------------------------------------------
# 1. AJAZZ AJ179 V2 Mouse Driver
# ---------------------------------------------------------------------------

class AjazzMouseDriver:
    """Driver for AJAZZ AJ179 V2 wireless/wired mouse (VID 249a:5c2f & 248a family)."""

    SUPPORTED_VIDS = frozenset({"249a", "248a"})
    PRIMARY_VID = "249a"
    PRIMARY_PID = "5c2f"

    CMD_POLLING = 0x02
    CMD_DPI = 0x03
    CMD_BATTERY = 0x04
    CMD_LED = 0x05
    CMD_SLEEP = 0x06

    VALID_POLLING_RATES = {125: 0x08, 250: 0x04, 500: 0x02, 1000: 0x01}
    POLLING_FROM_CODE = {v: k for k, v in VALID_POLLING_RATES.items()}
    DEFAULT_DPI_STAGES = [400, 800, 1600, 3200, 6400, 12000]

    def __init__(
        self,
        cache_path: Optional[Path] = None,
        hidraw_root: Path = Path("/sys/class/hidraw"),
        power_supply_root: Path = Path("/sys/class/power_supply"),
        io_timeout: float = 0.25,
    ) -> None:
        self.cache_path = cache_path or (DEFAULT_STATE_DIR / "mouse_state.json")
        self.hidraw_root = Path(hidraw_root)
        self.power_supply_root = Path(power_supply_root)
        self.io_timeout = io_timeout

    @staticmethod
    def build_packet(cmd: int, write: bool = False, payload: bytes = b"") -> bytes:
        return build_packet(cmd, write=write, payload=payload)

    @staticmethod
    def verify_checksum(frame32: bytes) -> bool:
        return verify_checksum(frame32)

    def _load_cache(self) -> Dict[str, Any]:
        cached = _read_json_file(self.cache_path)
        return {
            "battery": cached.get("battery"),
            "charging": bool(cached.get("charging", False)),
            "dpi_stages": list(cached.get("dpi_stages") or self.DEFAULT_DPI_STAGES),
            "active_dpi_stage": int(cached.get("active_dpi_stage", 2)),
            "current_dpi": int(cached.get("current_dpi", 1600)),
            "polling_rate": int(cached.get("polling_rate", 1000)),
            "led_color": str(cached.get("led_color", "#3B82F6")),
            "sleep_seconds": int(cached.get("sleep_seconds", 300)),
            "updated_at": cached.get("updated_at"),
        }

    def _save_cache(self, state: Dict[str, Any]) -> None:
        payload = {
            "battery": state.get("battery"),
            "charging": bool(state.get("charging", False)),
            "dpi_stages": list(state.get("dpi_stages") or self.DEFAULT_DPI_STAGES),
            "active_dpi_stage": int(state.get("active_dpi_stage", 2)),
            "current_dpi": int(state.get("current_dpi", 1600)),
            "polling_rate": int(state.get("polling_rate", 1000)),
            "led_color": str(state.get("led_color", "#3B82F6")),
            "sleep_seconds": int(state.get("sleep_seconds", 300)),
            "updated_at": int(time.time()),
        }
        _write_json_file(self.cache_path, payload)

    def find_vendor_node(self) -> Optional[Dict[str, Any]]:
        """Locate the 32-byte vendor HID endpoint for the AJAZZ AJ179 V2."""
        matches = [
            n
            for n in _scan_hidraw_nodes(self.hidraw_root)
            if n["vid"] in self.SUPPORTED_VIDS
        ]
        if not matches:
            return None

        def _score(node: Dict[str, Any]) -> Tuple[int, int, int, str]:
            is_primary = 1 if (node["vid"] == self.PRIMARY_VID and node["pid"] == self.PRIMARY_PID) else 0
            # Vendor 32-byte endpoint typically has Report Count 0x20 (95 20) and no input subdir
            rdesc: bytes = node["report_descriptor"]
            has_32b_report = 1 if b"\x95\x20" in rdesc else 0
            is_vendor_iface = 1 if not node["has_input"] else 0
            return (is_primary, is_vendor_iface, has_32b_report, node["name"])

        matches.sort(key=_score, reverse=True)
        return matches[0]

    def _hid_exchange(
        self,
        dev_path: str,
        cmd: int,
        write: bool = False,
        payload: bytes = b"",
    ) -> Optional[bytes]:
        """Send a 33-byte vendor HID frame and read a 32-byte response if available."""
        frame = build_packet(cmd, write=write, payload=payload)
        fd: Optional[int] = None
        try:
            fd = os.open(dev_path, os.O_RDWR | os.O_NONBLOCK)
            # Drain stale buffered packets if any
            for _ in range(4):
                ready, _, _ = select.select([fd], [], [], 0.0)
                if not ready:
                    break
                try:
                    if not os.read(fd, 64):
                        break
                except OSError:
                    break

            written = os.write(fd, frame)
            if written != len(frame):
                return None

            ready, _, _ = select.select([fd], [], [], self.io_timeout)
            if not ready:
                return None
            resp = os.read(fd, 64)
            if len(resp) == 33 and resp[0] == 0x00:
                resp = resp[1:]
            if len(resp) == 32:
                return resp
            return None
        except OSError:
            return None
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass

    def _read_sysfs_battery(self) -> Tuple[Optional[int], bool]:
        """Fallback check in /sys/class/power_supply for HID battery drivers."""
        for sup in _scan_power_supply(self.power_supply_root):
            haystack = " ".join(
                [sup["name"], sup["model_name"], sup["manufacturer"], str(sup["uevent"])]
            ).lower()
            if any(k in haystack for k in ("249a", "248a", "ajazz", "aj179", "xctech")):
                charging = sup["status"].lower() == "charging"
                return sup["capacity"], charging
        return None, False

    def read_state(self) -> Dict[str, Any]:
        """Read live mouse telemetry, falling back to persistent cache in PAW3395 deep sleep."""
        cache = self._load_cache()
        node = self.find_vendor_node()

        state: Dict[str, Any] = {
            "id": "ajazz_aj179_v2",
            "name": "AJAZZ AJ179 V2",
            "connected": False,
            "active": False,
            "battery": cache["battery"],
            "charging": cache["charging"],
            "connection_type": "Disconnected",
            "dpi_stages": list(cache["dpi_stages"]),
            "active_dpi_stage": cache["active_dpi_stage"],
            "current_dpi": cache["current_dpi"],
            "polling_rate": cache["polling_rate"],
            "led_color": cache["led_color"],
            "sleep_seconds": cache["sleep_seconds"],
            "standby": False,
            "cached": False,
            "hidraw_path": None,
        }

        if node is None:
            state["cached"] = cache["updated_at"] is not None
            return state

        state["connected"] = True
        state["hidraw_path"] = node["dev_path"]
        hid_name_lower = node["hid_name"].lower()
        is_wireless = any(k in hid_name_lower for k in ("wireless", "receiver", "dongle", "2.4"))
        base_conn = "2.4GHz" if is_wireless else "USB-C"

        live_ok = False
        # Query battery & charging status
        # Note: in PAW3395 deep sleep, the 2.4GHz receiver replies with status=0xFF / len=0 (all-zero payload).
        bat_resp = self._hid_exchange(node["dev_path"], self.CMD_BATTERY, write=False)
        if (
            bat_resp is not None
            and verify_checksum(bat_resp)
            and bat_resp[0] == self.CMD_BATTERY
            and bat_resp[2] != 0xFF
            and bat_resp[3] > 0
        ):
            pct = bat_resp[4]
            if 1 <= pct <= 100:
                state["battery"] = int(pct)
                state["charging"] = bool(bat_resp[5] == 1)
                live_ok = True

        # Optional live DPI / Polling / LED / Sleep readback when awake
        if live_ok:
            dpi_resp = self._hid_exchange(node["dev_path"], self.CMD_DPI, write=False)
            if (
                dpi_resp is not None
                and verify_checksum(dpi_resp)
                and dpi_resp[0] == self.CMD_DPI
                and dpi_resp[2] != 0xFF
                and dpi_resp[3] >= 3
            ):
                stage = int(dpi_resp[4])
                dpi_val = struct.unpack_from("<H", dpi_resp, 5)[0]
                if 400 <= dpi_val <= 26000:
                    state["current_dpi"] = dpi_val
                if 0 <= stage < len(state["dpi_stages"]):
                    state["active_dpi_stage"] = stage

            poll_resp = self._hid_exchange(node["dev_path"], self.CMD_POLLING, write=False)
            if (
                poll_resp is not None
                and verify_checksum(poll_resp)
                and poll_resp[0] == self.CMD_POLLING
                and poll_resp[2] != 0xFF
                and poll_resp[3] >= 1
            ):
                hz = self.POLLING_FROM_CODE.get(poll_resp[4])
                if hz:
                    state["polling_rate"] = hz

            led_resp = self._hid_exchange(node["dev_path"], self.CMD_LED, write=False)
            if (
                led_resp is not None
                and verify_checksum(led_resp)
                and led_resp[0] == self.CMD_LED
                and led_resp[2] != 0xFF
                and led_resp[3] >= 3
            ):
                r, g, b = led_resp[4], led_resp[5], led_resp[6]
                if any((r, g, b)):
                    state["led_color"] = f"#{r:02X}{g:02X}{b:02X}"

            sleep_resp = self._hid_exchange(node["dev_path"], self.CMD_SLEEP, write=False)
            if (
                sleep_resp is not None
                and verify_checksum(sleep_resp)
                and sleep_resp[0] == self.CMD_SLEEP
                and sleep_resp[2] != 0xFF
                and sleep_resp[3] >= 2
            ):
                sec = struct.unpack_from("<H", sleep_resp, 4)[0]
                if 30 <= sec <= 3600:
                    state["sleep_seconds"] = sec

        # Passive power_supply fallback if HID didn't answer
        if not live_ok:
            sys_bat, sys_chg = self._read_sysfs_battery()
            if sys_bat is not None:
                state["battery"] = sys_bat
                state["charging"] = sys_chg
                live_ok = True

        if live_ok:
            state["active"] = True
            state["standby"] = False
            state["cached"] = False
            state["connection_type"] = "USB-C" if state["charging"] else base_conn
            self._save_cache(state)
        else:
            # Receiver present, sensor PAW3395 in deep sleep -> preserve last known cache
            state["active"] = False
            state["standby"] = True
            state["cached"] = True
            state["connection_type"] = "Standby" if is_wireless else "USB-C"

        return state

    def _send_write_control(self, cmd: int, payload: bytes) -> Tuple[bool, str]:
        node = self.find_vendor_node()
        if node is None:
            return False, "Mouse AJAZZ AJ179 V2 não conectado."
        frame = build_packet(cmd, write=True, payload=payload)
        fd: Optional[int] = None
        try:
            fd = os.open(node["dev_path"], os.O_RDWR | os.O_NONBLOCK)
            written = os.write(fd, frame)
            if written != len(frame):
                return False, f"Escrita HID incompleta ({written}/{len(frame)} bytes)."
            return True, node["dev_path"]
        except PermissionError:
            return False, f"Sem permissão em {node['dev_path']}. Instale as regras udev."
        except OSError as exc:
            return False, f"Erro de comunicação HID ({exc})."
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass

    def set_dpi(self, dpi: int) -> Tuple[bool, str]:
        """Set active DPI (400..26000) on the AJAZZ AJ179 V2."""
        try:
            dpi_int = int(dpi)
        except (TypeError, ValueError):
            return False, "Valor de DPI inválido."
        if not (400 <= dpi_int <= 26000):
            return False, "DPI deve estar entre 400 e 26000."

        cache = self._load_cache()
        stages = list(cache["dpi_stages"])
        if dpi_int in stages:
            stage_idx = stages.index(dpi_int)
        else:
            stage_idx = max(0, min(cache["active_dpi_stage"], len(stages) - 1))
            stages[stage_idx] = dpi_int

        payload = struct.pack("<BH", stage_idx, dpi_int)
        ok, info = self._send_write_control(self.CMD_DPI, payload)
        if not ok:
            return False, info

        cache["dpi_stages"] = stages
        cache["active_dpi_stage"] = stage_idx
        cache["current_dpi"] = dpi_int
        self._save_cache(cache)
        return True, f"DPI ajustado para {dpi_int}."

    def set_polling_rate(self, hz: int) -> Tuple[bool, str]:
        """Set USB/2.4GHz polling rate (125, 250, 500 or 1000 Hz)."""
        try:
            hz_int = int(hz)
        except (TypeError, ValueError):
            return False, "Polling rate inválido."
        if hz_int not in self.VALID_POLLING_RATES:
            return False, "Polling rate inválido. Valores aceitos: 125, 250, 500 ou 1000 Hz."

        code = self.VALID_POLLING_RATES[hz_int]
        ok, info = self._send_write_control(self.CMD_POLLING, bytes([code]))
        if not ok:
            return False, info

        cache = self._load_cache()
        cache["polling_rate"] = hz_int
        self._save_cache(cache)
        return True, f"Polling rate ajustado para {hz_int} Hz."

    def set_led_color(self, hex_color: str) -> Tuple[bool, str]:
        """Set mouse side LED RGB color using #RRGGBB notation."""
        if not isinstance(hex_color, str):
            return False, "Cor LED inválida. Use formato #RRGGBB."
        raw = hex_color.strip()
        if not re.fullmatch(r"#?[0-9A-Fa-f]{6}", raw):
            return False, "Cor LED inválida. Use formato hexadecimal #RRGGBB."
        hex_digits = raw.lstrip("#").upper()
        r = int(hex_digits[0:2], 16)
        g = int(hex_digits[2:4], 16)
        b = int(hex_digits[4:6], 16)
        normalized = f"#{hex_digits}"

        ok, info = self._send_write_control(self.CMD_LED, bytes([r, g, b]))
        if not ok:
            return False, info

        cache = self._load_cache()
        cache["led_color"] = normalized
        self._save_cache(cache)
        return True, f"Cor LED ajustada para {normalized}."

    def set_sleep_timeout(self, seconds: int) -> Tuple[bool, str]:
        """Set PAW3395 deep-sleep timeout in seconds (30..3600)."""
        try:
            sec_int = int(seconds)
        except (TypeError, ValueError):
            return False, "Tempo de standby inválido."
        if not (30 <= sec_int <= 3600):
            return False, "Tempo de standby deve estar entre 30 e 3600 segundos."

        payload = struct.pack("<H", sec_int)
        ok, info = self._send_write_control(self.CMD_SLEEP, payload)
        if not ok:
            return False, info

        cache = self._load_cache()
        cache["sleep_seconds"] = sec_int
        self._save_cache(cache)
        return True, f"Tempo de standby ajustado para {sec_int}s."


# ---------------------------------------------------------------------------
# 2. Havit Fuxi H3 Headset Driver
# ---------------------------------------------------------------------------

class FuxiHeadsetDriver:
    """Driver for Havit Fuxi H3 headset (2.4GHz USB 040b:0897 + Bluetooth 01:92:25:27:09:76)."""

    USB_VID = "040b"
    USB_PID = "0897"
    BT_MAC = "01:92:25:27:09:76"
    ALSA_CARD = "FuxiH3"
    EQ_PRESETS = ("gaming", "music", "voice", "flat")

    EQ_CURVES: Dict[str, List[Tuple[str, float, float, float]]] = {
        # (filter_type, freq_hz, q, gain_db)
        "gaming": [
            ("bq_lowshelf", 100.0, 0.7, -2.0),
            ("bq_peaking", 2200.0, 1.2, 4.0),
            ("bq_peaking", 4500.0, 1.4, 3.5),
            ("bq_highshelf", 9000.0, 0.7, 1.5),
        ],
        "music": [
            ("bq_lowshelf", 85.0, 0.7, 3.5),
            ("bq_peaking", 1000.0, 1.0, -1.0),
            ("bq_highshelf", 10000.0, 0.7, 2.5),
        ],
        "voice": [
            ("bq_highpass", 120.0, 0.7, 0.0),
            ("bq_peaking", 1800.0, 1.0, 4.0),
            ("bq_peaking", 3200.0, 1.2, 3.0),
            ("bq_lowpass", 10000.0, 0.7, 0.0),
        ],
        "flat": [
            ("bq_peaking", 1000.0, 1.0, 0.0),
        ],
    }

    def __init__(
        self,
        bt_mac: str = BT_MAC,
        alsa_card: str = ALSA_CARD,
        state_dir: Optional[Path] = None,
        hidraw_root: Path = Path("/sys/class/hidraw"),
        power_supply_root: Path = Path("/sys/class/power_supply"),
        cmd_runner=None,
    ) -> None:
        self.bt_mac = bt_mac
        self.alsa_card = alsa_card
        self.state_dir = state_dir or DEFAULT_STATE_DIR
        self.state_path = self.state_dir / "headset_state.json"
        self.hidraw_root = Path(hidraw_root)
        self.power_supply_root = Path(power_supply_root)
        self._run = cmd_runner or _run_cmd

    def _load_state_file(self) -> Dict[str, Any]:
        data = _read_json_file(self.state_path)
        return {
            "eq_preset": data.get("eq_preset", "flat")
            if data.get("eq_preset") in self.EQ_PRESETS
            else "flat",
            "sidetone_pid": data.get("sidetone_pid"),
        }

    def _save_state_file(self, data: Dict[str, Any]) -> None:
        _write_json_file(self.state_path, data)

    def _check_bluetooth(self) -> Tuple[bool, Optional[int]]:
        rc, out, _ = self._run(["bluetoothctl", "info", self.bt_mac], timeout=2.0)
        if rc != 0 or not out:
            return False, None
        connected = bool(re.search(r"Connected:\s*yes", out, re.IGNORECASE))
        battery: Optional[int] = None
        m = re.search(r"Battery Percentage:\s*0x[0-9a-fA-F]+\s*\((\d+)\)", out)
        if m:
            battery = max(0, min(100, int(m.group(1))))
        return connected, battery

    def _check_upower_battery(self) -> Tuple[Optional[int], bool]:
        rc, out, _ = self._run(["upower", "-d"], timeout=2.5)
        if rc != 0 or not out:
            return None, False
        mac_colon = self.bt_mac.lower()
        mac_under = mac_colon.replace(":", "_")
        blocks = re.split(r"\n(?=Device:\s)", out)
        for blk in blocks:
            low = blk.lower()
            if any(tok in low for tok in (mac_colon, mac_under, "fuxi", "040b", "0897")):
                pct_m = re.search(r"percentage:\s*(\d+)\s*%", blk, re.IGNORECASE)
                state_m = re.search(r"state:\s*([a-zA-Z0-9_-]+)", blk, re.IGNORECASE)
                pct = int(pct_m.group(1)) if pct_m else None
                charging = bool(state_m and state_m.group(1).lower() == "charging")
                if pct is not None:
                    return max(0, min(100, pct)), charging
        return None, False

    def _check_power_supply_battery(self) -> Tuple[Optional[int], bool]:
        mac_low = self.bt_mac.lower()
        for sup in _scan_power_supply(self.power_supply_root):
            hay = " ".join(
                [sup["name"], sup["model_name"], sup["manufacturer"], str(sup["uevent"])]
            ).lower()
            if any(tok in hay for tok in ("fuxi", "040b", "0897", mac_low, mac_low.replace(":", "_"))):
                if sup["capacity"] is not None:
                    return max(0, min(100, int(sup["capacity"]))), sup["status"].lower() == "charging"
        return None, False

    def _has_usb_dongle(self) -> bool:
        for node in _scan_hidraw_nodes(self.hidraw_root):
            if node["vid"] == self.USB_VID and node["pid"] == self.USB_PID:
                return True
        return False

    def _parse_pactl_cards(self) -> List[Dict[str, Any]]:
        rc, out, _ = self._run(["pactl", "list", "cards"], timeout=2.5)
        if rc != 0 or not out:
            return []
        cards: List[Dict[str, Any]] = []
        blocks = re.split(r"(?m)^Card #\d+", out)
        for blk in blocks:
            if not blk.strip():
                continue
            name_m = re.search(r"^\s*Name:\s*(.+)$", blk, re.MULTILINE)
            if not name_m:
                continue
            card_name = name_m.group(1).strip()
            active_m = re.search(r"^\s*Active Profile:\s*(.+)$", blk, re.MULTILINE)
            active_profile = active_m.group(1).strip() if active_m else None

            profiles: List[str] = []
            in_profiles = False
            for line in blk.splitlines():
                if re.match(r"^\s*Profiles:\s*$", line):
                    in_profiles = True
                    continue
                if in_profiles:
                    if re.match(r"^\s*(Active Profile|Ports):", line):
                        break
                    prof_m = re.match(r"^\s{2,}([^\s:]+(?::[^\s:]+)*?):\s+", line)
                    if prof_m:
                        profiles.append(prof_m.group(1).strip())
            cards.append(
                {
                    "name": card_name,
                    "raw": blk,
                    "active_profile": active_profile,
                    "profiles": profiles,
                }
            )
        return cards

    def _parse_pactl_sinks(self) -> List[Dict[str, Any]]:
        rc, out, _ = self._run(["pactl", "list", "sinks"], timeout=2.5)
        if rc != 0 or not out:
            return []
        sinks: List[Dict[str, Any]] = []
        blocks = re.split(r"(?m)^Sink #\d+", out)
        for blk in blocks:
            if not blk.strip():
                continue
            name_m = re.search(r"^\s*Name:\s*(.+)$", blk, re.MULTILINE)
            if not name_m:
                continue
            mute_m = re.search(r"^\s*Mute:\s*(yes|no)", blk, re.MULTILINE | re.IGNORECASE)
            vol_m = re.search(r"^\s*Volume:.*?(\d+)%", blk, re.MULTILINE)
            state_m = re.search(r"^\s*State:\s*(\S+)", blk, re.MULTILINE)
            sinks.append(
                {
                    "name": name_m.group(1).strip(),
                    "raw": blk,
                    "muted": bool(mute_m and mute_m.group(1).lower() == "yes"),
                    "volume": max(0, min(100, int(vol_m.group(1)))) if vol_m else 0,
                    "state": state_m.group(1).upper() if state_m else "UNKNOWN",
                }
            )
        return sinks

    def _match_fuxi_card_and_sink(
        self,
        bt_connected: bool,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        mac_under = self.bt_mac.lower().replace(":", "_")
        cards = self._parse_pactl_cards()
        sinks = self._parse_pactl_sinks()

        def _is_bt(item: Dict[str, Any]) -> bool:
            low = (item["name"] + " " + item["raw"]).lower()
            return ("bluez" in low) and (mac_under in low or "fuxi" in low)

        def _is_usb(item: Dict[str, Any]) -> bool:
            low = (item["name"] + " " + item["raw"]).lower()
            return ("bluez" not in low) and any(
                k in low for k in ("fuxi-h3", "fuxih3", "xiisound", "040b:0897", "0x0897")
            )

        bt_card = next((c for c in cards if _is_bt(c)), None)
        usb_card = next((c for c in cards if _is_usb(c)), None)
        bt_sink = next((s for s in sinks if _is_bt(s)), None)
        usb_sink = next((s for s in sinks if _is_usb(s)), None)

        if bt_connected and (bt_card or bt_sink):
            return bt_card or usb_card, bt_sink or usb_sink
        return usb_card or bt_card, usb_sink or bt_sink

    def _check_alsa_zero_bug(self) -> bool:
        """Detect the known Fuxi H3 USB ALSA bug where numid=9 resets to 0,0 or numid=7 is off."""
        rc9, out9, _ = self._run(["amixer", "-c", self.alsa_card, "cget", "numid=9"], timeout=1.5)
        rc7, out7, _ = self._run(["amixer", "-c", self.alsa_card, "cget", "numid=7"], timeout=1.5)
        if rc9 != 0 and rc7 != 0:
            return False
        if rc9 == 0:
            m = re.search(r"values=([\d,]+)", out9)
            if m:
                vals = [int(v) for v in m.group(1).split(",") if v.isdigit()]
                if vals and any(v == 0 for v in vals):
                    return True
        if rc7 == 0:
            m7 = re.search(r"values=([a-zA-Z,]+)", out7)
            if m7 and "off" in m7.group(1).lower():
                return True
        return False

    def _is_sidetone_running(self, pid: Optional[int]) -> bool:
        if not pid or not isinstance(pid, int):
            return False
        cmdline_path = Path(f"/proc/{pid}/cmdline")
        try:
            if not cmdline_path.exists():
                return False
            cmdline = cmdline_path.read_bytes().decode("utf-8", errors="ignore")
            return "pw-loopback" in cmdline
        except OSError:
            return False

    def _find_fuxi_source(self, bt_connected: bool) -> Optional[str]:
        rc, out, _ = self._run(["pactl", "list", "short", "sources"], timeout=2.0)
        if rc != 0 or not out:
            return None
        mac_under = self.bt_mac.lower().replace(":", "_")
        usb_src = None
        bt_src = None
        for line in out.splitlines():
            cols = line.split("\t")
            if len(cols) < 2:
                continue
            name = cols[1].strip()
            if name.endswith(".monitor"):
                continue
            low = name.lower()
            if "bluez" in low and (mac_under in low or "fuxi" in low):
                bt_src = name
            elif "fuxi" in low or "xiisound" in low:
                usb_src = name
        return (bt_src or usb_src) if bt_connected else (usb_src or bt_src)

    def read_state(self) -> Dict[str, Any]:
        """Collect dual-mode (Bluetooth + 2.4GHz USB) headset telemetry."""
        persisted = self._load_state_file()
        bt_connected, bt_battery = self._check_bluetooth()
        usb_present = self._has_usb_dongle()
        card, sink = self._match_fuxi_card_and_sink(bt_connected=bt_connected)

        if not usb_present and card and "bluez" not in card["name"].lower():
            usb_present = True

        if bt_connected:
            connection_type = "Bluetooth"
            connected = True
        elif usb_present or sink is not None:
            connection_type = "2.4GHz"
            connected = True
        else:
            connection_type = "Disconnected"
            connected = False

        battery: Optional[int] = bt_battery
        charging = False
        if battery is None:
            up_bat, up_chg = self._check_upower_battery()
            if up_bat is not None:
                battery = up_bat
                charging = up_chg
        if battery is None:
            ps_bat, ps_chg = self._check_power_supply_battery()
            if ps_bat is not None:
                battery = ps_bat
                charging = ps_chg

        alsa_zero_bug = self._check_alsa_zero_bug() if (usb_present and not bt_connected) else False
        sidetone_active = self._is_sidetone_running(persisted.get("sidetone_pid"))
        active = connected and (sink is not None or bt_connected)

        return {
            "id": "havit_fuxi_h3",
            "name": "Havit Fuxi H3",
            "connected": connected,
            "active": active,
            "battery": battery,
            "charging": charging,
            "connection_type": connection_type,
            "volume": sink["volume"] if sink else 0,
            "muted": sink["muted"] if sink else False,
            "active_profile": card["active_profile"] if card else None,
            "available_profiles": card["profiles"] if card else [],
            "sidetone": sidetone_active,
            "eq_preset": persisted["eq_preset"],
            "alsa_zero_bug": alsa_zero_bug,
            "card_name": card["name"] if card else None,
            "sink_name": sink["name"] if sink else None,
        }

    def fix_alsa_volume(self) -> Tuple[bool, str]:
        """Fix the Havit Fuxi H3 USB ALSA zero-volume bug (numid=9 -> 100,100 and numid=7 -> on)."""
        rc9, _, err9 = self._run(
            ["amixer", "-c", self.alsa_card, "cset", "numid=9", "100,100"],
            timeout=2.5,
        )
        rc7, _, err7 = self._run(
            ["amixer", "-c", self.alsa_card, "cset", "numid=7", "on"],
            timeout=2.5,
        )
        if rc9 == 0 and rc7 == 0:
            return True, "Volume ALSA do Fuxi H3 corrigido (numid=9=100,100, numid=7=on)."
        detail = "; ".join(msg.strip() for msg in (err9, err7) if msg.strip()) or "Falha no amixer."
        return False, f"Erro ao corrigir ALSA no card {self.alsa_card}: {detail}"

    def set_volume(self, pct: int) -> Tuple[bool, str]:
        """Set headset playback volume (0..100%)."""
        try:
            vol = max(0, min(100, int(pct)))
        except (TypeError, ValueError):
            return False, "Percentual de volume inválido."
        bt_conn, _ = self._check_bluetooth()
        _, sink = self._match_fuxi_card_and_sink(bt_connected=bt_conn)
        if not sink:
            return False, "Sink de áudio do Havit Fuxi H3 não encontrado."
        rc, _, err = self._run(["pactl", "set-sink-volume", sink["name"], f"{vol}%"])
        if rc != 0:
            return False, f"Falha ao ajustar volume: {err.strip() or 'erro pactl'}"
        return True, f"Volume do Fuxi H3 ajustado para {vol}%."

    def toggle_mute(self) -> Tuple[bool, str]:
        """Toggle mute state on the active Havit Fuxi H3 sink."""
        bt_conn, _ = self._check_bluetooth()
        _, sink = self._match_fuxi_card_and_sink(bt_connected=bt_conn)
        if not sink:
            return False, "Sink de áudio do Havit Fuxi H3 não encontrado."
        rc, _, err = self._run(["pactl", "set-sink-mute", sink["name"], "toggle"])
        if rc != 0:
            return False, f"Falha ao alternar mute: {err.strip() or 'erro pactl'}"
        new_state = "desmutado" if sink["muted"] else "mutado"
        return True, f"Havit Fuxi H3 {new_state}."

    def set_profile(self, profile: str) -> Tuple[bool, str]:
        """Switch PipeWire/PulseAudio card profile on the active Havit Fuxi H3 card."""
        if not profile or not isinstance(profile, str):
            return False, "Nome de perfil de áudio inválido."
        bt_conn, _ = self._check_bluetooth()
        card, _ = self._match_fuxi_card_and_sink(bt_connected=bt_conn)
        if not card:
            return False, "Placa de áudio do Havit Fuxi H3 não encontrada."
        rc, _, err = self._run(["pactl", "set-card-profile", card["name"], profile.strip()])
        if rc != 0:
            return False, f"Falha ao alterar perfil: {err.strip() or 'erro pactl'}"
        return True, f"Perfil do Fuxi H3 alterado para {profile.strip()}."

    def set_sidetone(self, enabled: bool) -> Tuple[bool, str]:
        """Enable or disable low-latency microphone sidetone via pw-loopback."""
        persisted = self._load_state_file()
        old_pid = persisted.get("sidetone_pid")
        if self._is_sidetone_running(old_pid):
            try:
                os.kill(int(old_pid), signal.SIGTERM)
            except OSError:
                pass
        persisted["sidetone_pid"] = None

        if not enabled:
            self._save_state_file(persisted)
            return True, "Sidetone do Fuxi H3 desativado."

        bt_conn, _ = self._check_bluetooth()
        _, sink = self._match_fuxi_card_and_sink(bt_connected=bt_conn)
        source = self._find_fuxi_source(bt_connected=bt_conn)
        if not sink or not source:
            self._save_state_file(persisted)
            return False, "Microfone ou saída do Fuxi H3 indisponível para sidetone."

        cmd = [
            "pw-loopback",
            "--name=dpi-fuxi-sidetone",
            "--latency=15",
            f"--capture-props=node.target={source}",
            f"--playback-props=node.target={sink['name']}",
        ]
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                env=_c_env(),
            )
            persisted["sidetone_pid"] = proc.pid
            self._save_state_file(persisted)
            return True, f"Sidetone ativado via pw-loopback (PID {proc.pid})."
        except FileNotFoundError:
            self._save_state_file(persisted)
            return False, "pw-loopback não encontrado no sistema."
        except OSError as exc:
            self._save_state_file(persisted)
            return False, f"Erro ao iniciar pw-loopback: {exc}"

    def set_eq_preset(self, preset: str) -> Tuple[bool, str]:
        """Apply and persist an EQ preset (`gaming`, `music`, `voice`, `flat`)."""
        if not isinstance(preset, str):
            return False, "Preset de EQ inválido."
        key = preset.strip().lower()
        if key not in self.EQ_PRESETS:
            return False, f"Preset inválido. Use: {', '.join(self.EQ_PRESETS)}."

        # Write PipeWire filter-chain preset config for reproducible audio DSP tuning
        bands = self.EQ_CURVES[key]
        eq_conf_path = self.state_dir / "fuxi_eq.conf"
        nodes_lines: List[str] = []
        links_lines: List[str] = []
        for idx, (ftype, freq, q_val, gain) in enumerate(bands, start=1):
            nodes_lines.append(
                "        { type = builtin name = eq_band_%d label = %s "
                "control = { \"Freq\" = %.1f \"Q\" = %.2f \"Gain\" = %.1f } }"
                % (idx, ftype, freq, q_val, gain)
            )
            if idx > 1:
                links_lines.append(
                    f'        {{ output = "eq_band_{idx - 1}:Out" input = "eq_band_{idx}:In" }}'
                )
        conf_text = (
            "# Generated by Dynamic Peripheral Island (Fuxi H3 EQ)\n"
            f"# Preset: {key}\n"
            "context.modules = [\n"
            "  { name = libpipewire-module-filter-chain\n"
            "    args = {\n"
            f'      node.description = "Fuxi H3 EQ ({key})"\n'
            '      media.name = "Fuxi H3 EQ"\n'
            "      filter.graph = {\n"
            "        nodes = [\n"
            + "\n".join(nodes_lines)
            + "\n        ]\n"
            "        links = [\n"
            + "\n".join(links_lines)
            + "\n        ]\n"
            "      }\n"
            "    }\n"
            "  }\n"
            "]\n"
        )
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            eq_conf_path.write_text(conf_text, encoding="utf-8")
        except OSError:
            pass

        persisted = self._load_state_file()
        persisted["eq_preset"] = key
        self._save_state_file(persisted)
        return True, f"Preset de EQ do Fuxi H3 ajustado para '{key}'."


# ---------------------------------------------------------------------------
# 3. Machenike K500-B94 Keyboard Driver (STRICT HARDWARE SAFE MODE)
# ---------------------------------------------------------------------------

class K500KeyboardDriver:
    """Passive, Hardware-Safe-Mode-locked driver for Machenike K500-B94 (VID 258a:0049).

    NEVER sends raw HID writes to the Sino Wealth MCU to prevent bootloader lockup.
    """

    VID = "258a"
    PID = "0049"
    SHORTCUTS: List[Dict[str, str]] = [
        {"keys": "FN+INS", "action": "Alternar efeito de iluminação RGB"},
        {"keys": "FN+↑/↓", "action": "Aumentar / diminuir brilho dos LEDs"},
        {"keys": "FN+←/→", "action": "Ajustar velocidade / direção do efeito"},
        {"keys": "FN+ESC", "action": "Restaurar padrão de fábrica (segurar 3s)"},
    ]

    def __init__(
        self,
        hidraw_root: Path = Path("/sys/class/hidraw"),
        leds_root: Path = Path("/sys/class/leds"),
        input_devices_path: Path = Path("/proc/bus/input/devices"),
    ) -> None:
        self.safe_mode: bool = True
        self.hidraw_root = Path(hidraw_root)
        self.leds_root = Path(leds_root)
        self.input_devices_path = Path(input_devices_path)

    @staticmethod
    def validate_hid_frame(frame: bytes) -> bytes:
        return validate_hid_frame(frame)

    def send_raw_packet(self, frame: bytes) -> Tuple[bool, str]:
        """Strictly refuse raw HID writes to protect the Sino Wealth MCU."""
        # Always validate first so empty/all-zero/malformed frames raise ValueError explicitly
        self.validate_hid_frame(frame)
        raise RuntimeError(
            "Hardware Safe Mode ativo no Machenike K500-B94 (258a:0049): "
            "escrita HID bruta bloqueada permanentemente para evitar travamento de bootloader na MCU Sino Wealth."
        )

    def _is_connected(self) -> bool:
        for node in _scan_hidraw_nodes(self.hidraw_root):
            if node["vid"] == self.VID and node["pid"] == self.PID:
                return True
        try:
            if self.input_devices_path.exists():
                txt = self.input_devices_path.read_text(encoding="utf-8", errors="ignore").lower()
                if f"vendor={self.VID}" in txt and f"product={self.PID}" in txt:
                    return True
        except OSError:
            pass
        return False

    def _read_leds(self) -> Dict[str, bool]:
        leds = {"capslock": False, "numlock": False, "scrolllock": False}
        if not self.leds_root.exists():
            return leds
        try:
            entries = sorted(self.leds_root.iterdir(), key=lambda p: p.name)
        except OSError:
            return leds

        # Prefer LED directories whose parent device matches 258a:0049; fallback to any input*::*
        matched_specific: Dict[str, bool] = {}
        fallback: Dict[str, bool] = {}

        for entry in entries:
            m = re.match(r"^input\d+::(capslock|numlock|scrolllock)$", entry.name)
            if not m:
                continue
            led_key = m.group(1)
            brightness_file = entry / "brightness"
            try:
                val = int(brightness_file.read_text(encoding="utf-8").strip()) > 0
            except (OSError, ValueError):
                continue

            is_k500_led = False
            try:
                vendor_f = entry / "device" / "id" / "vendor"
                product_f = entry / "device" / "id" / "product"
                if vendor_f.exists() and product_f.exists():
                    v = vendor_f.read_text(encoding="utf-8").strip().lower()
                    p = product_f.read_text(encoding="utf-8").strip().lower()
                    if v == self.VID and p == self.PID:
                        is_k500_led = True
            except OSError:
                pass

            if is_k500_led:
                matched_specific[led_key] = val
            elif led_key not in fallback:
                fallback[led_key] = val

        for key in leds:
            if key in matched_specific:
                leds[key] = matched_specific[key]
            elif key in fallback:
                leds[key] = fallback[key]
        return leds

    def read_state(self) -> Dict[str, Any]:
        """Passive read-only state inspection for Machenike K500-B94."""
        connected = self._is_connected()
        return {
            "id": "machenike_k500_b94",
            "name": "Machenike K500-B94",
            "connected": connected,
            "active": connected,
            "connection_type": "USB-C" if connected else "Disconnected",
            "safe_mode": True,
            "leds": self._read_leds(),
            "shortcuts": [dict(s) for s in self.SHORTCUTS],
        }


# ---------------------------------------------------------------------------
# 4. Gamepad Driver (GameSir Nova Lite & EasySMX 9124)
# ---------------------------------------------------------------------------

class GamepadDriver:
    """Driver for GameSir Nova Lite (3537:1041 / 3537:2106) and EasySMX 9124 (045e:028e)."""

    GAMESIR_VID = "3537"
    GAMESIR_ACTIVE_PID = "1041"
    GAMESIR_STANDBY_PID = "2106"

    EASYSMX_VID = "045e"
    EASYSMX_PID = "028e"

    ACTIVITY_WINDOW_SEC = 60.0
    VALID_LAYOUTS = ("xbox", "nintendo")

    def __init__(
        self,
        state_dir: Optional[Path] = None,
        hidraw_root: Path = Path("/sys/class/hidraw"),
        input_devices_path: Path = Path("/proc/bus/input/devices"),
        power_supply_root: Path = Path("/sys/class/power_supply"),
        activity_dir: Path = Path("/tmp"),
        dev_input_root: Path = Path("/dev/input"),
    ) -> None:
        self.state_dir = state_dir or DEFAULT_STATE_DIR
        self.state_path = self.state_dir / "gamepad_state.json"
        self.hidraw_root = Path(hidraw_root)
        self.input_devices_path = Path(input_devices_path)
        self.power_supply_root = Path(power_supply_root)
        self.activity_dir = Path(activity_dir)
        self.dev_input_root = Path(dev_input_root)

    @staticmethod
    def is_activity_fresh(
        last_ts: Optional[float],
        now_ts: Optional[float] = None,
        window: float = 60.0,
    ) -> bool:
        return is_activity_fresh(last_ts, now_ts=now_ts, window=window)

    def _load_prefs(self) -> Dict[str, Dict[str, Any]]:
        data = _read_json_file(self.state_path)
        return data if isinstance(data, dict) else {}

    def _save_prefs(self, prefs: Dict[str, Dict[str, Any]]) -> None:
        _write_json_file(self.state_path, prefs)

    def _get_controller_prefs(self, controller_id: str) -> Tuple[str, int]:
        prefs = self._load_prefs()
        entry = prefs.get(controller_id, {})
        layout = entry.get("layout", "xbox")
        if layout not in self.VALID_LAYOUTS:
            layout = "xbox"
        try:
            deadzone = max(0, min(25, int(entry.get("deadzone_pct", 5))))
        except (TypeError, ValueError):
            deadzone = 5
        return layout, deadzone

    def _parse_input_devices(self) -> List[Dict[str, Any]]:
        if not self.input_devices_path.exists():
            return []
        try:
            content = self.input_devices_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []

        devices: List[Dict[str, Any]] = []
        for block in content.strip().split("\n\n"):
            if not block.strip():
                continue
            dev: Dict[str, Any] = {
                "bus": "",
                "vid": "",
                "pid": "",
                "name": "",
                "phys": "",
                "handlers": [],
                "event_name": None,
                "event_path": None,
                "ff_supported": False,
            }
            for line in block.splitlines():
                if line.startswith("I:"):
                    m_v = re.search(r"Vendor=([0-9a-fA-F]{4})", line)
                    m_p = re.search(r"Product=([0-9a-fA-F]{4})", line)
                    m_b = re.search(r"Bus=([0-9a-fA-F]{4})", line)
                    if m_v:
                        dev["vid"] = m_v.group(1).lower()
                    if m_p:
                        dev["pid"] = m_p.group(1).lower()
                    if m_b:
                        dev["bus"] = m_b.group(1).lower()
                elif line.startswith("N:"):
                    m_n = re.search(r'Name="([^"]*)"', line)
                    if m_n:
                        dev["name"] = m_n.group(1)
                elif line.startswith("P:"):
                    dev["phys"] = line.split("Phys=", 1)[-1].strip()
                elif line.startswith("H:"):
                    handlers = line.split("Handlers=", 1)[-1].strip().split()
                    dev["handlers"] = handlers
                    for h in handlers:
                        if h.startswith("event"):
                            dev["event_name"] = h
                            dev["event_path"] = str(self.dev_input_root / h)
                            break
                elif line.startswith("B: FF="):
                    ff_hex = line.split("B: FF=", 1)[-1].strip()
                    dev["ff_supported"] = any(ch in "123456789abcdefABCDEF" for ch in ff_hex)
            devices.append(dev)
        return devices

    def _activity_file(self, event_name: str) -> Path:
        return self.activity_dir / f"dpi-gamepad-{event_name}.active"

    def _poll_event_activity(
        self,
        event_name: Optional[str],
        event_path: Optional[str],
        now_ts: float,
    ) -> bool:
        """Non-blocking select(..., 0) check + 60s activity file tracker."""
        if not event_name:
            return False

        marker = self._activity_file(event_name)
        saw_live_input = False

        if event_path and os.path.exists(event_path):
            fd: Optional[int] = None
            try:
                fd = os.open(event_path, os.O_RDONLY | os.O_NONBLOCK)
                ready, _, _ = select.select([fd], [], [], 0.0)
                if ready:
                    data = os.read(fd, 4096)
                    if data:
                        saw_live_input = True
            except OSError:
                pass
            finally:
                if fd is not None:
                    try:
                        os.close(fd)
                    except OSError:
                        pass

        if saw_live_input:
            try:
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_text(f"{now_ts:.3f}\n", encoding="utf-8")
            except OSError:
                pass
            return True

        # Check persisted last-activity timestamp
        last_ts: Optional[float] = None
        try:
            if marker.exists():
                raw = marker.read_text(encoding="utf-8").strip()
                if raw:
                    last_ts = float(raw)
                else:
                    last_ts = marker.stat().st_mtime
        except (OSError, ValueError):
            try:
                if marker.exists():
                    last_ts = marker.stat().st_mtime
            except OSError:
                last_ts = None

        return is_activity_fresh(last_ts, now_ts=now_ts, window=self.ACTIVITY_WINDOW_SEC)

    def _find_gamepad_battery(self, keywords: Tuple[str, ...]) -> Tuple[Optional[int], bool]:
        for sup in _scan_power_supply(self.power_supply_root):
            hay = " ".join(
                [sup["name"], sup["model_name"], sup["manufacturer"], str(sup["uevent"])]
            ).lower()
            if any(k in hay for k in keywords):
                return sup["capacity"], sup["status"].lower() == "charging"
        return None, False

    def read_state(self, now_ts: Optional[float] = None) -> Dict[str, Any]:
        """Scan GameSir Nova Lite and EasySMX 9124 controllers with consolidation & 60s activity window."""
        now = time.time() if now_ts is None else float(now_ts)
        input_devs = self._parse_input_devices()
        hidraw_nodes = _scan_hidraw_nodes(self.hidraw_root)

        controllers: List[Dict[str, Any]] = []

        # --- 1. GameSir Nova Lite (3537:1041 active / 3537:2106 dongle standby) ---
        gs_active_inputs = [
            d for d in input_devs if d["vid"] == self.GAMESIR_VID and d["pid"] == self.GAMESIR_ACTIVE_PID
        ]
        gs_active_hid = [
            n for n in hidraw_nodes if n["vid"] == self.GAMESIR_VID and n["pid"] == self.GAMESIR_ACTIVE_PID
        ]
        gs_standby_hid = [
            n for n in hidraw_nodes if n["vid"] == self.GAMESIR_VID and n["pid"] == self.GAMESIR_STANDBY_PID
        ]

        if gs_active_inputs or gs_active_hid:
            primary = gs_active_inputs[0] if gs_active_inputs else None
            ev_name = primary["event_name"] if primary else None
            ev_path = primary["event_path"] if primary else None
            fresh = self._poll_event_activity(ev_name, ev_path, now) if ev_name else True
            # 3537:1041 enumerates when controller is on; if an explicit stale marker exists, respect 60s hide rule
            if ev_name and not fresh:
                marker = self._activity_file(ev_name)
                is_active = not marker.exists()
            else:
                is_active = fresh
            bat, chg = self._find_gamepad_battery(("3537", "gamesir", "nova"))
            layout, dz = self._get_controller_prefs("gamesir_nova_lite")
            controllers.append(
                {
                    "id": "gamesir_nova_lite",
                    "name": "GameSir Nova Lite",
                    "brand": "GameSir",
                    "connected": True,
                    "active": is_active,
                    "charging": chg,
                    "battery": bat,
                    "connection_type": "USB-C (Carregando)" if chg else "2.4GHz",
                    "layout": layout,
                    "deadzone_pct": dz,
                    "ff_supported": bool(primary["ff_supported"]) if primary else False,
                    "event_path": ev_path,
                }
            )
        elif gs_standby_hid:
            layout, dz = self._get_controller_prefs("gamesir_nova_lite")
            controllers.append(
                {
                    "id": "gamesir_nova_lite",
                    "name": "GameSir Nova Lite",
                    "brand": "GameSir",
                    "connected": True,
                    "active": False,
                    "charging": False,
                    "battery": None,
                    "connection_type": "Standby (Dongle 2.4GHz)",
                    "layout": layout,
                    "deadzone_pct": dz,
                    "ff_supported": False,
                    "event_path": None,
                }
            )

        # --- 2. EasySMX 9124 (045e:028e) — consolidate dual nodes (USB-C + 2.4GHz dongle) ---
        easysmx_nodes = [
            d for d in input_devs if d["vid"] == self.EASYSMX_VID and d["pid"] == self.EASYSMX_PID
        ]
        if easysmx_nodes:
            # Prefer a node with FF support and an event_path as primary
            easysmx_nodes.sort(key=lambda d: (bool(d["ff_supported"]), bool(d["event_path"])), reverse=True)
            primary = easysmx_nodes[0]
            bat, ps_chg = self._find_gamepad_battery(("045e", "easysmx", "xpad"))
            layout, dz = self._get_controller_prefs("easysmx_9124")

            dual_node = len(easysmx_nodes) >= 2
            any_fresh = any(
                self._poll_event_activity(n["event_name"], n["event_path"], now)
                for n in easysmx_nodes
            )
            if dual_node:
                charging = True
                conn_type = "USB-C (Carregando) + Dongle 2.4GHz"
                is_active = True
            else:
                charging = ps_chg
                conn_type = "USB-C (Carregando)" if charging else ("2.4GHz / USB" if any_fresh else "Standby (Dongle 2.4GHz)")
                is_active = bool(any_fresh or charging)

            controllers.append(
                {
                    "id": "easysmx_9124",
                    "name": "EasySMX 9124",
                    "brand": "EasySMX",
                    "connected": True,
                    "active": is_active,
                    "charging": charging,
                    "battery": bat,
                    "connection_type": conn_type,
                    "layout": layout,
                    "deadzone_pct": dz,
                    "ff_supported": any(bool(n["ff_supported"]) for n in easysmx_nodes),
                    "event_path": primary["event_path"],
                }
            )

        active_list = [c for c in controllers if c["active"]]
        primary_ctrl = active_list[0] if active_list else (controllers[0] if controllers else None)

        return {
            "id": "gamepads",
            "name": primary_ctrl["name"] if primary_ctrl else "Controles",
            "connected": any(c["connected"] for c in controllers),
            "active": bool(active_list),
            "charging": any(c["charging"] for c in controllers),
            "battery": primary_ctrl["battery"] if primary_ctrl else None,
            "connection_type": primary_ctrl["connection_type"] if primary_ctrl else "Disconnected",
            "active_count": len(active_list),
            "connected_count": len(controllers),
            "controllers": controllers,
        }

    def _resolve_controller(self, controller_id: Optional[str]) -> Optional[Dict[str, Any]]:
        state = self.read_state()
        ctrls = state["controllers"]
        if not ctrls:
            return None
        if controller_id:
            for c in ctrls:
                if c["id"] == controller_id:
                    return c
            return None
        # Prefer active controller with event_path, then any with event_path, then first
        for c in ctrls:
            if c["active"] and c["event_path"]:
                return c
        for c in ctrls:
            if c["event_path"]:
                return c
        return ctrls[0]

    def test_rumble(self, controller_id: Optional[str] = None) -> Tuple[bool, str]:
        """Trigger a short force-feedback rumble via Linux evdev EVIOCSFF ioctl."""
        ctrl = self._resolve_controller(controller_id)
        if ctrl is None or not ctrl.get("event_path"):
            return (
                False,
                "Nenhum controle com nó evdev ativo encontrado para teste de vibração.",
            )

        event_path = str(ctrl["event_path"])
        # struct ff_effect (48 bytes on 64-bit Linux):
        #   offset 0:  type (H) = FF_RUMBLE (0x50)
        #   offset 2:  id (h) = -1 (allocate new slot)
        #   offset 4:  direction (H) = 0
        #   offset 6:  trigger (HH) = 0, 0
        #   offset 10: replay (HH) = length_ms (350), delay_ms (0)
        #   offset 14: 2 bytes alignment padding
        #   offset 16: u.rumble (HH) = strong_magnitude (0xC000), weak_magnitude (0x8000)
        effect_buf = bytearray(FF_EFFECT_SIZE)
        struct.pack_into("<HhHHHHH", effect_buf, 0, FF_RUMBLE, -1, 0, 0, 0, 350, 0)
        struct.pack_into("<HH", effect_buf, 16, 0xC000, 0x8000)

        fd: Optional[int] = None
        effect_id: Optional[int] = None
        try:
            fd = os.open(event_path, os.O_RDWR | os.O_NONBLOCK)
            fcntl.ioctl(fd, EVIOCSFF, effect_buf)
            effect_id = struct.unpack_from("<h", effect_buf, 2)[0]

            # Start rumble (EV_FF, effect_id, 1)
            play_evt = struct.pack("llHHi", 0, 0, EV_FF, effect_id, 1)
            os.write(fd, play_evt)
            time.sleep(0.35)
            # Stop rumble (EV_FF, effect_id, 0)
            stop_evt = struct.pack("llHHi", 0, 0, EV_FF, effect_id, 0)
            os.write(fd, stop_evt)
            return True, f"Vibração testada com sucesso em {ctrl['name']}."
        except PermissionError:
            return (
                False,
                f"Sem permissão em {event_path}. Instale as regras udev e reconecte o controle.",
            )
        except OSError as exc:
            if exc.errno == errno.ENOSYS:
                return (
                    False,
                    "Vibração não suportada no modo atual (ENOSYS 38). "
                    "Alterne o controle para modo XInput segurando M + Menu + View por 2s.",
                )
            return False, f"Falha ao acionar vibração em {ctrl['name']}: {exc}"
        finally:
            if fd is not None:
                if effect_id is not None and effect_id >= 0:
                    try:
                        fcntl.ioctl(fd, EVIOCRMFF, effect_id)
                    except OSError:
                        pass
                try:
                    os.close(fd)
                except OSError:
                    pass

    def set_deadzone(self, controller_id: Optional[str], pct: int) -> Tuple[bool, str]:
        """Configure and persist analog stick deadzone (0..25%)."""
        try:
            val = int(pct)
        except (TypeError, ValueError):
            return False, "Valor de deadzone inválido."
        if not (0 <= val <= 25):
            return False, "Deadzone deve estar entre 0% e 25%."

        target_id = controller_id
        if not target_id:
            ctrl = self._resolve_controller(None)
            target_id = ctrl["id"] if ctrl else "default"

        prefs = self._load_prefs()
        entry = dict(prefs.get(target_id, {}))
        entry["deadzone_pct"] = val
        prefs[target_id] = entry
        self._save_prefs(prefs)
        return True, f"Deadzone de '{target_id}' ajustada para {val}%."

    def set_layout(self, controller_id: Optional[str], layout: str) -> Tuple[bool, str]:
        """Configure and persist button layout (`xbox` or `nintendo`)."""
        if not isinstance(layout, str):
            return False, "Layout inválido. Use 'xbox' ou 'nintendo'."
        norm = layout.strip().lower()
        if norm not in self.VALID_LAYOUTS:
            return False, "Layout inválido. Use 'xbox' ou 'nintendo'."

        target_id = controller_id
        if not target_id:
            ctrl = self._resolve_controller(None)
            target_id = ctrl["id"] if ctrl else "default"

        prefs = self._load_prefs()
        entry = dict(prefs.get(target_id, {}))
        entry["layout"] = norm
        prefs[target_id] = entry
        self._save_prefs(prefs)
        return True, f"Layout de '{target_id}' alterado para {norm.capitalize()}."


# ---------------------------------------------------------------------------
# 5. Unified Hardware Hub Manager
# ---------------------------------------------------------------------------

class HardwareHubManager:
    """Aggregates all peripheral drivers, transition alerts, and control dispatch."""

    def __init__(
        self,
        mouse: Optional[AjazzMouseDriver] = None,
        headset: Optional[FuxiHeadsetDriver] = None,
        gamepad: Optional[GamepadDriver] = None,
        keyboard: Optional[K500KeyboardDriver] = None,
        state_dir: Optional[Path] = None,
    ) -> None:
        self.state_dir = state_dir or DEFAULT_STATE_DIR
        self.transition_path = self.state_dir / "hardware_transitions.json"
        self.mouse = mouse or AjazzMouseDriver(cache_path=self.state_dir / "mouse_state.json")
        self.headset = headset or FuxiHeadsetDriver(state_dir=self.state_dir)
        self.gamepad = gamepad or GamepadDriver(state_dir=self.state_dir)
        self.keyboard = keyboard or K500KeyboardDriver()

    def _safe_read(self, name: str, reader) -> Dict[str, Any]:
        try:
            return reader()
        except Exception as exc:  # pragma: no cover - defensive guard
            return {
                "id": name,
                "name": name,
                "connected": False,
                "active": False,
                "error": str(exc),
            }

    def _detect_transitions(
        self,
        devices: Dict[str, Dict[str, Any]],
        threshold: int,
    ) -> List[Dict[str, Any]]:
        prev_all = _read_json_file(self.transition_path)
        next_all: Dict[str, Any] = {}
        alerts: List[Dict[str, Any]] = []
        now = int(time.time())

        for key, dev in devices.items():
            prev = prev_all.get(key) if isinstance(prev_all.get(key), dict) else None
            dev_name = str(dev.get("name", key))
            connected = bool(dev.get("connected", False))
            charging = bool(dev.get("charging", False))
            battery = dev.get("battery")
            bat_int = int(battery) if isinstance(battery, (int, float)) else None

            # Connection transition
            if prev is not None and not prev.get("connected", False) and connected:
                alerts.append(
                    {
                        "type": "device_connected",
                        "severity": "info",
                        "device": key,
                        "name": dev_name,
                        "message": f"{dev_name} conectado ({dev.get('connection_type', 'OK')})",
                        "timestamp": now,
                    }
                )

            # Charging transition
            if prev is not None and not prev.get("charging", False) and charging:
                alerts.append(
                    {
                        "type": "charging_started",
                        "severity": "info",
                        "device": key,
                        "name": dev_name,
                        "message": f"{dev_name} iniciou carregamento",
                        "timestamp": now,
                    }
                )

            # Battery level classification & transition
            bat_level = "ok"
            if connected and bat_int is not None and not charging:
                if bat_int <= 10:
                    bat_level = "critical"
                elif bat_int < threshold:
                    bat_level = "low"

            prev_level = prev.get("bat_level") if prev is not None else None
            if bat_level == "critical" and prev_level != "critical":
                alerts.append(
                    {
                        "type": "low_battery",
                        "severity": "critical",
                        "device": key,
                        "name": dev_name,
                        "battery": bat_int,
                        "message": f"{dev_name}: bateria crítica ({bat_int}%)",
                        "timestamp": now,
                    }
                )
            elif bat_level == "low" and prev_level not in ("low", "critical"):
                alerts.append(
                    {
                        "type": "low_battery",
                        "severity": "warning",
                        "device": key,
                        "name": dev_name,
                        "battery": bat_int,
                        "message": f"{dev_name}: bateria baixa ({bat_int}%)",
                        "timestamp": now,
                    }
                )

            next_all[key] = {
                "connected": connected,
                "charging": charging,
                "battery": bat_int,
                "bat_level": bat_level,
            }

        _write_json_file(self.transition_path, next_all)
        return alerts

    def get_all_peripherals_snapshot(self, threshold: int = 20) -> Dict[str, Any]:
        """Collect unified telemetry from all 4 peripheral classes plus transition alerts."""
        devices = {
            "mouse": self._safe_read("mouse", self.mouse.read_state),
            "headset": self._safe_read("headset", self.headset.read_state),
            "gamepad": self._safe_read("gamepad", self.gamepad.read_state),
            "keyboard": self._safe_read("keyboard", self.keyboard.read_state),
        }
        alerts = self._detect_transitions(devices, threshold=int(threshold))
        return {
            "devices": devices,
            "alerts": alerts,
        }

    def dispatch_action(self, action: str, **kwargs: Any) -> Tuple[bool, str]:
        """Execute a named peripheral control action and return `(ok, message)`."""
        act = (action or "").strip().lower()

        if act == "set_dpi":
            return self.mouse.set_dpi(kwargs.get("dpi"))  # type: ignore[arg-type]
        if act in ("set_polling_rate", "set_polling"):
            return self.mouse.set_polling_rate(kwargs.get("hz", kwargs.get("rate")))  # type: ignore[arg-type]
        if act in ("set_led_color", "set_mouse_led"):
            return self.mouse.set_led_color(kwargs.get("hex_color", kwargs.get("color", "")))
        if act in ("set_sleep_timeout", "set_mouse_sleep"):
            return self.mouse.set_sleep_timeout(kwargs.get("seconds", kwargs.get("timeout")))  # type: ignore[arg-type]

        if act in ("fix_alsa_volume", "fix_alsa"):
            return self.headset.fix_alsa_volume()
        if act == "set_volume":
            return self.headset.set_volume(kwargs.get("pct", kwargs.get("volume")))  # type: ignore[arg-type]
        if act == "toggle_mute":
            return self.headset.toggle_mute()
        if act in ("set_profile", "set_audio_profile"):
            return self.headset.set_profile(kwargs.get("profile", ""))
        if act == "set_sidetone":
            enabled = kwargs.get("enabled", False)
            if isinstance(enabled, str):
                enabled = enabled.strip().lower() in ("1", "true", "yes", "on")
            return self.headset.set_sidetone(bool(enabled))
        if act in ("set_eq_preset", "set_eq"):
            return self.headset.set_eq_preset(kwargs.get("preset", kwargs.get("eq", "")))

        if act == "test_rumble":
            return self.gamepad.test_rumble(controller_id=kwargs.get("controller_id"))
        if act == "set_deadzone":
            return self.gamepad.set_deadzone(
                kwargs.get("controller_id"),
                kwargs.get("pct", kwargs.get("deadzone")),  # type: ignore[arg-type]
            )
        if act in ("set_layout", "set_gamepad_layout"):
            return self.gamepad.set_layout(
                kwargs.get("controller_id"),
                kwargs.get("layout", ""),
            )

        return False, f"Ação de hardware desconhecida: '{action}'."

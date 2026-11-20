"""Dynamic Peripheral Island — Native System Monitor (FEAT-007).

Provides hardware and system performance telemetry using exclusively Linux
sysfs, /proc, and Python 3 standard library:
  - CPU: usage percentage via /proc/stat delta, temperatures via hwmon (k10temp, coretemp, zenpower, acpitz), loadavg, and cores.
  - RAM: used, total, and percentage via /proc/meminfo.
  - GPU: usage percentage, VRAM used/total, and edge/junction temps via AMD DRM /sys/class/drm and hwmon.
  - Disk: used, total, and percentage via os.statvfs, plus NVMe Composite temp from hwmon.
  - Network: active physical interface selection, RX/TX rate deltas (KB/s, MB/s) via /proc/net/dev.
  - Uptime: seconds and formatted duration via /proc/uptime.

100% Python 3 standard library, zero external dependencies.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_STATE_DIR = Path.home() / ".config" / "dynamic-peripheral-island"


def _read_json_file(path: Path) -> Dict[str, Any]:
    """Read a JSON object from disk, returning {} if absent or invalid."""
    try:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json_file(path: Path, data: Dict[str, Any]) -> None:
    """Safely persist a JSON object to disk atomically."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(f".tmp.{os.getpid()}")
        tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp_path.replace(path)
    except OSError:
        pass


def format_rate(kbps: float) -> str:
    """Format network rate in human-readable KB/s or MB/s."""
    if kbps >= 1024.0:
        return f"{kbps / 1024.0:.1f} MB/s"
    return f"{int(round(kbps))} KB/s"


def format_uptime(seconds: int) -> str:
    """Format uptime seconds into a human-readable duration (e.g. '4h 58m' or '2d 4h 10m')."""
    if seconds <= 0:
        return "0m"
    hours = seconds // 3600
    mins = (seconds % 3600) // 60
    days = hours // 24
    hours_in_day = hours % 24
    if days > 0:
        return f"{days}d {hours_in_day}h {mins}m"
    if hours > 0:
        return f"{hours}h {mins}m"
    return f"{mins}m"


class SystemMonitor:
    """Native system monitor gathering CPU, RAM, GPU, Disk, Network, and Uptime telemetry."""

    def __init__(
        self,
        proc_root: Path = Path("/proc"),
        sys_root: Path = Path("/sys"),
        state_path: Optional[Path] = None,
        disk_path: str = "/",
    ) -> None:
        self.proc_root = Path(proc_root)
        self.sys_root = Path(sys_root)
        self.state_path = Path(state_path) if state_path else (DEFAULT_STATE_DIR / "sysmon_state.json")
        self.disk_path = str(disk_path)

    # -----------------------------------------------------------------------
    # 1. CPU
    # -----------------------------------------------------------------------

    def _read_cpu(self, now: float, cached: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        cores = os.cpu_count() or 1
        load_1m = 0.0

        loadavg_path = self.proc_root / "loadavg"
        if loadavg_path.exists():
            try:
                load_1m = float(loadavg_path.read_text(encoding="utf-8").split()[0])
            except (OSError, ValueError, IndexError):
                pass

        total_ticks = 0
        idle_ticks = 0
        stat_path = self.proc_root / "stat"
        if stat_path.exists():
            try:
                for line in stat_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if line.startswith("cpu "):
                        parts = [int(x) for x in line.split()[1:]]
                        if len(parts) >= 4:
                            idle_ticks = parts[3] + (parts[4] if len(parts) > 4 else 0)
                            total_ticks = sum(parts)
                        break
            except (OSError, ValueError):
                pass

        usage_pct = 0.0
        prev_cpu = cached.get("cpu", {})
        prev_total = prev_cpu.get("total")
        prev_idle = prev_cpu.get("idle")

        if prev_total is not None and prev_idle is not None and total_ticks > prev_total:
            diff_total = total_ticks - int(prev_total)
            diff_idle = idle_ticks - int(prev_idle)
            if diff_total > 0:
                usage_pct = round(max(0.0, min(100.0, (1.0 - (diff_idle / diff_total)) * 100.0)), 1)
        elif load_1m > 0 and cores > 0:
            usage_pct = round(min(100.0, (load_1m / cores) * 100.0), 1)

        # CPU Temperature: scan hwmon prioritizing k10temp, coretemp, zenpower, acpitz
        cpu_temp: Optional[float] = None
        hwmon_root = self.sys_root / "class" / "hwmon"
        if hwmon_root.exists():
            candidate_hwmons: List[Tuple[int, Path, str]] = []
            try:
                for h in hwmon_root.iterdir():
                    name_f = h / "name"
                    if name_f.exists():
                        try:
                            n = name_f.read_text(encoding="utf-8").strip().lower()
                            if n == "k10temp":
                                candidate_hwmons.append((1, h, n))
                            elif n == "zenpower":
                                candidate_hwmons.append((2, h, n))
                            elif n == "coretemp":
                                candidate_hwmons.append((3, h, n))
                            elif n == "acpitz":
                                candidate_hwmons.append((4, h, n))
                        except OSError:
                            pass
            except OSError:
                pass

            candidate_hwmons.sort(key=lambda x: x[0])
            target_labels = ("tctl", "tdie", "package id 0", "package")

            for _, h, _ in candidate_hwmons:
                # 1. Search for matching labels
                try:
                    for lbl_file in sorted(h.glob("temp*_label")):
                        lbl = lbl_file.read_text(encoding="utf-8").strip().lower()
                        if any(t in lbl for t in target_labels):
                            stem = lbl_file.stem.split("_")[0]
                            inp = h / f"{stem}_input"
                            if inp.exists():
                                cpu_temp = round(int(inp.read_text(encoding="utf-8").strip()) / 1000.0, 1)
                                break
                except OSError:
                    pass

                # 2. Fallback to temp1_input
                if cpu_temp is None:
                    inp1 = h / "temp1_input"
                    if inp1.exists():
                        try:
                            cpu_temp = round(int(inp1.read_text(encoding="utf-8").strip()) / 1000.0, 1)
                        except (OSError, ValueError):
                            pass
                if cpu_temp is not None:
                    break

        cpu_state = {
            "usage_pct": usage_pct,
            "temp_c": cpu_temp,
            "cores": cores,
            "load_1m": load_1m,
        }
        cache_cpu = {
            "total": total_ticks,
            "idle": idle_ticks,
        }
        return cpu_state, cache_cpu

    # -----------------------------------------------------------------------
    # 2. RAM
    # -----------------------------------------------------------------------

    def _read_ram(self) -> Dict[str, Any]:
        mem_total_kb = 0
        mem_avail_kb = 0
        meminfo_path = self.proc_root / "meminfo"

        if meminfo_path.exists():
            try:
                for line in meminfo_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if line.startswith("MemTotal:"):
                        mem_total_kb = int(line.split()[1])
                    elif line.startswith("MemAvailable:"):
                        mem_avail_kb = int(line.split()[1])
                    if mem_total_kb > 0 and mem_avail_kb > 0:
                        break
            except (OSError, ValueError, IndexError):
                pass

        if mem_total_kb > 0:
            used_kb = max(0, mem_total_kb - mem_avail_kb)
            total_gb = round(mem_total_kb / (1024 * 1024), 1)
            used_gb = round(used_kb / (1024 * 1024), 1)
            used_pct = round((used_kb / mem_total_kb) * 100.0, 1)
        else:
            total_gb = 0.0
            used_gb = 0.0
            used_pct = 0.0

        return {
            "used_gb": used_gb,
            "total_gb": total_gb,
            "used_pct": used_pct,
        }

    # -----------------------------------------------------------------------
    # 3. GPU (AMD DRM & hwmon)
    # -----------------------------------------------------------------------

    def _read_gpu(self) -> Dict[str, Any]:
        gpu_state: Dict[str, Any] = {
            "available": False,
            "vendor": "GPU",
            "usage_pct": 0,
            "temp_c": None,
            "junction_c": None,
            "vram_used_gb": 0.0,
            "vram_total_gb": 0.0,
            "vram_pct": 0.0,
        }

        drm_root = self.sys_root / "class" / "drm"
        if not drm_root.exists():
            return gpu_state

        try:
            entries = sorted(drm_root.iterdir(), key=lambda p: p.name)
        except OSError:
            return gpu_state

        for card in entries:
            # Match card0, card1, etc. (ignore card1-DP-1, etc.)
            if not re.match(r"^card\d+$", card.name):
                continue
            dev_dir = card / "device"
            if not dev_dir.exists():
                continue

            gpu_busy_f = dev_dir / "gpu_busy_percent"
            vram_total_f = dev_dir / "mem_info_vram_total"
            vram_used_f = dev_dir / "mem_info_vram_used"

            if gpu_busy_f.exists() or vram_total_f.exists():
                gpu_state["available"] = True

                # Detect vendor from vendor file or driver
                vendor_f = dev_dir / "vendor"
                if vendor_f.exists():
                    try:
                        v_hex = vendor_f.read_text(encoding="utf-8").strip().lower()
                        if "1002" in v_hex:
                            gpu_state["vendor"] = "AMD"
                        elif "10de" in v_hex:
                            gpu_state["vendor"] = "NVIDIA"
                        elif "8086" in v_hex:
                            gpu_state["vendor"] = "Intel"
                    except OSError:
                        pass

                if gpu_busy_f.exists():
                    try:
                        gpu_state["usage_pct"] = max(0, min(100, int(gpu_busy_f.read_text(encoding="utf-8").strip())))
                    except (OSError, ValueError):
                        pass

                if vram_total_f.exists():
                    try:
                        tot_bytes = int(vram_total_f.read_text(encoding="utf-8").strip())
                        gpu_state["vram_total_gb"] = round(tot_bytes / (1024**3), 2)
                        if vram_used_f.exists():
                            used_bytes = int(vram_used_f.read_text(encoding="utf-8").strip())
                            gpu_state["vram_used_gb"] = round(used_bytes / (1024**3), 2)
                            if tot_bytes > 0:
                                gpu_state["vram_pct"] = round((used_bytes / tot_bytes) * 100.0, 1)
                    except (OSError, ValueError):
                        pass

                # Scan temperatures from device hwmon or amdgpu hwmon
                hwmon_dirs: List[Path] = []
                dev_hwmon = dev_dir / "hwmon"
                if dev_hwmon.exists():
                    try:
                        hwmon_dirs.extend(dev_hwmon.glob("hwmon*"))
                    except OSError:
                        pass
                if not hwmon_dirs:
                    global_hwmon = self.sys_root / "class" / "hwmon"
                    if global_hwmon.exists():
                        try:
                            for h in global_hwmon.glob("hwmon*"):
                                nf = h / "name"
                                if nf.exists() and nf.read_text(encoding="utf-8").strip().lower() == "amdgpu":
                                    hwmon_dirs.append(h)
                        except OSError:
                            pass

                for h in hwmon_dirs:
                    try:
                        for lbl_file in h.glob("temp*_label"):
                            lbl = lbl_file.read_text(encoding="utf-8").strip().lower()
                            stem = lbl_file.stem.split("_")[0]
                            inp = h / f"{stem}_input"
                            if inp.exists():
                                val = round(int(inp.read_text(encoding="utf-8").strip()) / 1000.0, 1)
                                if lbl == "edge" and gpu_state["temp_c"] is None:
                                    gpu_state["temp_c"] = val
                                elif lbl == "junction" and gpu_state["junction_c"] is None:
                                    gpu_state["junction_c"] = val
                    except (OSError, ValueError):
                        pass

                    if gpu_state["temp_c"] is None:
                        inp1 = h / "temp1_input"
                        if inp1.exists():
                            try:
                                gpu_state["temp_c"] = round(int(inp1.read_text(encoding="utf-8").strip()) / 1000.0, 1)
                            except (OSError, ValueError):
                                pass
                break

        return gpu_state

    # -----------------------------------------------------------------------
    # 4. Disk & NVMe
    # -----------------------------------------------------------------------

    def _read_disk(self) -> Dict[str, Any]:
        total_gb = 0.0
        used_gb = 0.0
        used_pct = 0.0

        try:
            st = os.statvfs(self.disk_path)
            total_b = st.f_frsize * st.f_blocks
            free_b = st.f_frsize * st.f_bavail
            used_b = total_b - (st.f_frsize * st.f_bfree)

            total_gb = round(total_b / (1024**3), 1)
            used_gb = round(used_b / (1024**3), 1)
            used_pct = round((used_b / total_b) * 100.0, 1) if total_b > 0 else 0.0
        except OSError:
            pass

        # Check NVMe temperature in hwmon
        nvme_temp: Optional[float] = None
        hwmon_root = self.sys_root / "class" / "hwmon"
        if hwmon_root.exists():
            try:
                for h in hwmon_root.glob("hwmon*"):
                    nf = h / "name"
                    if nf.exists() and nf.read_text(encoding="utf-8").strip().lower() == "nvme":
                        for lbl_file in h.glob("temp*_label"):
                            if lbl_file.read_text(encoding="utf-8").strip().lower() == "composite":
                                stem = lbl_file.stem.split("_")[0]
                                inp = h / f"{stem}_input"
                                if inp.exists():
                                    nvme_temp = round(int(inp.read_text(encoding="utf-8").strip()) / 1000.0, 1)
                                    break
                        if nvme_temp is None:
                            inp1 = h / "temp1_input"
                            if inp1.exists():
                                nvme_temp = round(int(inp1.read_text(encoding="utf-8").strip()) / 1000.0, 1)
                        if nvme_temp is not None:
                            break
            except (OSError, ValueError):
                pass

        return {
            "path": self.disk_path,
            "used_gb": used_gb,
            "total_gb": total_gb,
            "used_pct": used_pct,
            "temp_c": nvme_temp,
            "nvme_temp_c": nvme_temp,
        }

    # -----------------------------------------------------------------------
    # 5. Network
    # -----------------------------------------------------------------------

    def _read_network(self, now: float, cached: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        net_dev_path = self.proc_root / "net" / "dev"
        candidates: List[Tuple[int, str, int, int]] = []

        if net_dev_path.exists():
            try:
                for line in net_dev_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if ":" not in line:
                        continue
                    iface, rest = line.split(":", 1)
                    iface = iface.strip()
                    parts = rest.split()
                    if len(parts) >= 9:
                        rx = int(parts[0])
                        tx = int(parts[8])
                        total = rx + tx
                        # Non-virtual / non-lo candidates get higher priority
                        is_phy = 1 if not iface.startswith(("lo", "docker", "veth", "br-")) else 0
                        candidates.append((is_phy, total, iface, rx, tx))
            except (OSError, ValueError):
                pass

        if candidates:
            # Sort by is_phy DESC, total bytes DESC
            candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
            _, _, chosen_iface, rx_bytes, tx_bytes = candidates[0]
        else:
            chosen_iface = "lo"
            rx_bytes = 0
            tx_bytes = 0

        rx_kbps = 0.0
        tx_kbps = 0.0

        prev_net = cached.get("net", {})
        prev_iface = prev_net.get("interface")
        prev_ts = prev_net.get("timestamp")
        prev_rx = prev_net.get("rx_bytes")
        prev_tx = prev_net.get("tx_bytes")

        if (
            prev_iface == chosen_iface
            and prev_ts is not None
            and prev_rx is not None
            and prev_tx is not None
            and now > float(prev_ts)
        ):
            dt = max(0.1, now - float(prev_ts))
            delta_rx = max(0, rx_bytes - int(prev_rx))
            delta_tx = max(0, tx_bytes - int(prev_tx))
            rx_kbps = round((delta_rx / dt) / 1024.0, 1)
            tx_kbps = round((delta_tx / dt) / 1024.0, 1)

        net_state = {
            "interface": chosen_iface,
            "rx_kbps": rx_kbps,
            "tx_kbps": tx_kbps,
            "rx_text": format_rate(rx_kbps),
            "tx_text": format_rate(tx_kbps),
        }
        cache_net = {
            "interface": chosen_iface,
            "rx_bytes": rx_bytes,
            "tx_bytes": tx_bytes,
            "timestamp": now,
        }
        return net_state, cache_net

    # -----------------------------------------------------------------------
    # 6. Uptime
    # -----------------------------------------------------------------------

    def _read_uptime(self) -> Dict[str, Any]:
        uptime_sec = 0
        uptime_path = self.proc_root / "uptime"
        if uptime_path.exists():
            try:
                txt = uptime_path.read_text(encoding="utf-8").split()
                uptime_sec = int(float(txt[0]))
            except (OSError, ValueError, IndexError):
                pass

        return {
            "uptime_sec": uptime_sec,
            "uptime_str": format_uptime(uptime_sec),
        }

    # -----------------------------------------------------------------------
    # Main Snapshot Collector
    # -----------------------------------------------------------------------

    def get_state(self, now_ts: Optional[float] = None) -> Dict[str, Any]:
        """Collect unified system monitor snapshot and update persisted delta cache."""
        now = time.time() if now_ts is None else float(now_ts)
        cached = _read_json_file(self.state_path)

        cpu_state, new_cache_cpu = self._read_cpu(now, cached)
        ram_state = self._read_ram()
        gpu_state = self._read_gpu()
        disk_state = self._read_disk()
        net_state, new_cache_net = self._read_network(now, cached)
        uptime_state = self._read_uptime()

        # Persist updated snapshot for next delta calculation
        new_cached = {
            "timestamp": now,
            "cpu": new_cache_cpu,
            "net": new_cache_net,
        }
        _write_json_file(self.state_path, new_cached)

        return {
            "cpu": cpu_state,
            "ram": ram_state,
            "gpu": gpu_state,
            "disk": disk_state,
            "network": net_state,
            "uptime": uptime_state,
        }

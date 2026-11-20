"""Automated unit tests for Native System Monitor (FEAT-007 — `src/dpi_core/sysmon.py`).

Validates deterministic telemetry for CPU, RAM, GPU, Disk, Network deltas, and Uptime
using mocked /proc and /sys filesystem hierarchies.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from dpi_core.sysmon import SystemMonitor, format_rate, format_uptime  # noqa: E402


class TestSystemMonitor(unittest.TestCase):
    """Test suite for SystemMonitor with isolated temporary /proc and /sys hierarchies."""

    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.proc_root = self.root / "proc"
        self.sys_root = self.root / "sys"
        self.state_path = self.root / "sysmon_state.json"

        self.proc_root.mkdir(parents=True, exist_ok=True)
        self.sys_root.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_cpu_usage_delta_and_hwmon_temp(self) -> None:
        """Validates CPU usage % calculation via /proc/stat delta and k10temp Tctl temperature."""
        stat_file = self.proc_root / "stat"
        loadavg_file = self.proc_root / "loadavg"
        loadavg_file.write_text("0.80 0.60 0.50 1/800 1234\n", encoding="utf-8")

        # Mock hwmon k10temp (AMD Ryzen)
        hwmon1 = self.sys_root / "class" / "hwmon" / "hwmon1"
        hwmon1.mkdir(parents=True, exist_ok=True)
        (hwmon1 / "name").write_text("k10temp\n", encoding="utf-8")
        (hwmon1 / "temp1_label").write_text("Tctl\n", encoding="utf-8")
        (hwmon1 / "temp1_input").write_text("54200\n", encoding="utf-8")

        # Sample 1: Initial ticks (100 total, 80 idle)
        stat_file.write_text("cpu  10 5 5 80 0 0 0 0 0 0\n", encoding="utf-8")
        monitor = SystemMonitor(
            proc_root=self.proc_root,
            sys_root=self.sys_root,
            state_path=self.state_path,
        )

        state1 = monitor.get_state(now_ts=1000.0)
        self.assertEqual(state1["cpu"]["temp_c"], 54.2)
        self.assertGreater(state1["cpu"]["cores"], 0)
        self.assertEqual(state1["cpu"]["load_1m"], 0.8)

        # Sample 2: 100 ticks later (total 200, idle 140 -> 60 work / 100 total = 40% usage)
        stat_file.write_text("cpu  40 10 10 140 0 0 0 0 0 0\n", encoding="utf-8")
        state2 = monitor.get_state(now_ts=1002.0)
        self.assertEqual(state2["cpu"]["usage_pct"], 40.0)
        self.assertEqual(state2["cpu"]["temp_c"], 54.2)

    def test_ram_usage_parsing(self) -> None:
        """Validates RAM total, used, and percentage calculation from /proc/meminfo."""
        meminfo = self.proc_root / "meminfo"
        meminfo.write_text(
            "MemTotal:       16274432 kB\n"
            "MemFree:         4096000 kB\n"
            "MemAvailable:    8137216 kB\n"
            "Buffers:          200000 kB\n"
            "Cached:          3800000 kB\n",
            encoding="utf-8",
        )
        monitor = SystemMonitor(
            proc_root=self.proc_root,
            sys_root=self.sys_root,
            state_path=self.state_path,
        )
        state = monitor.get_state(now_ts=1000.0)
        ram = state["ram"]
        self.assertEqual(ram["total_gb"], 15.5)
        self.assertEqual(ram["used_gb"], 7.8)
        self.assertEqual(ram["used_pct"], 50.0)

    def test_gpu_amd_drm_and_vram_and_hwmon(self) -> None:
        """Validates AMD DRM sysfs busy percent, VRAM total/used, and edge/junction temps."""
        card_dev = self.sys_root / "class" / "drm" / "card0" / "device"
        card_dev.mkdir(parents=True, exist_ok=True)

        (card_dev / "vendor").write_text("0x1002\n", encoding="utf-8")
        (card_dev / "gpu_busy_percent").write_text("35\n", encoding="utf-8")
        (card_dev / "mem_info_vram_total").write_text(str(6 * 1024**3) + "\n", encoding="utf-8")
        (card_dev / "mem_info_vram_used").write_text(str(int(1.5 * 1024**3)) + "\n", encoding="utf-8")

        dev_hwmon = card_dev / "hwmon" / "hwmon2"
        dev_hwmon.mkdir(parents=True, exist_ok=True)
        (dev_hwmon / "name").write_text("amdgpu\n", encoding="utf-8")
        (dev_hwmon / "temp1_label").write_text("edge\n", encoding="utf-8")
        (dev_hwmon / "temp1_input").write_text("51000\n", encoding="utf-8")
        (dev_hwmon / "temp2_label").write_text("junction\n", encoding="utf-8")
        (dev_hwmon / "temp2_input").write_text("54500\n", encoding="utf-8")

        monitor = SystemMonitor(
            proc_root=self.proc_root,
            sys_root=self.sys_root,
            state_path=self.state_path,
        )
        state = monitor.get_state(now_ts=1000.0)
        gpu = state["gpu"]
        self.assertTrue(gpu["available"])
        self.assertEqual(gpu["vendor"], "AMD")
        self.assertEqual(gpu["usage_pct"], 35)
        self.assertEqual(gpu["vram_total_gb"], 6.0)
        self.assertEqual(gpu["vram_used_gb"], 1.5)
        self.assertEqual(gpu["vram_pct"], 25.0)
        self.assertEqual(gpu["temp_c"], 51.0)
        self.assertEqual(gpu["junction_c"], 54.5)

    def test_disk_and_nvme_hwmon(self) -> None:
        """Validates disk space calculation via statvfs and NVMe Composite temperature."""
        hwmon_nvme = self.sys_root / "class" / "hwmon" / "hwmon3"
        hwmon_nvme.mkdir(parents=True, exist_ok=True)
        (hwmon_nvme / "name").write_text("nvme\n", encoding="utf-8")
        (hwmon_nvme / "temp1_label").write_text("Composite\n", encoding="utf-8")
        (hwmon_nvme / "temp1_input").write_text("43200\n", encoding="utf-8")

        monitor = SystemMonitor(
            proc_root=self.proc_root,
            sys_root=self.sys_root,
            state_path=self.state_path,
        )

        mock_stat = mock.MagicMock()
        mock_stat.f_frsize = 4096
        mock_stat.f_blocks = 26214400  # 100 GB
        mock_stat.f_bfree = 13107200   # 50 GB free
        mock_stat.f_bavail = 13107200

        with mock.patch("os.statvfs", return_value=mock_stat):
            state = monitor.get_state(now_ts=1000.0)

        disk = state["disk"]
        self.assertEqual(disk["total_gb"], 100.0)
        self.assertEqual(disk["used_gb"], 50.0)
        self.assertEqual(disk["used_pct"], 50.0)
        self.assertEqual(disk["temp_c"], 43.2)
        self.assertEqual(disk["nvme_temp_c"], 43.2)

    def test_network_active_iface_delta_and_format_rate(self) -> None:
        """Validates interface selection (ignoring lo) and rate delta formatting in KB/s and MB/s."""
        net_dev = self.proc_root / "net" / "dev"
        net_dev.parent.mkdir(parents=True, exist_ok=True)

        # Sample 1: Initial byte counts
        net_dev.write_text(
            "Inter-|   Receive                                                |  Transmit\n"
            " face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed\n"
            "    lo: 1000000       0    0    0    0     0          0         0  1000000       0    0    0    0     0       0          0\n"
            "enp7s0: 10485760      10   0    0    0     0          0         0  5242880       5    0    0    0     0       0          0\n",
            encoding="utf-8",
        )

        monitor = SystemMonitor(
            proc_root=self.proc_root,
            sys_root=self.sys_root,
            state_path=self.state_path,
        )

        state1 = monitor.get_state(now_ts=1000.0)
        self.assertEqual(state1["network"]["interface"], "enp7s0")
        self.assertEqual(state1["network"]["rx_kbps"], 0.0)
        self.assertEqual(state1["network"]["tx_kbps"], 0.0)

        # Sample 2: 2.0s later with +2MB RX (1024 KB/s) and +1MB TX (512 KB/s)
        # 10485760 + 2097152 = 12582912, 5242880 + 1048576 = 6291456
        net_dev.write_text(
            "Inter-|   Receive                                                |  Transmit\n"
            " face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed\n"
            "    lo: 1000000       0    0    0    0     0          0         0  1000000       0    0    0    0     0       0          0\n"
            "enp7s0: 12582912      20   0    0    0     0          0         0  6291456      10    0    0    0     0       0          0\n",
            encoding="utf-8",
        )

        state2 = monitor.get_state(now_ts=1002.0)
        net2 = state2["network"]
        self.assertEqual(net2["interface"], "enp7s0")
        self.assertEqual(net2["rx_kbps"], 1024.0)
        self.assertEqual(net2["tx_kbps"], 512.0)
        self.assertEqual(net2["rx_text"], "1.0 MB/s")
        self.assertEqual(net2["tx_text"], "512 KB/s")

        # Helpers verification
        self.assertEqual(format_rate(250.0), "250 KB/s")
        self.assertEqual(format_rate(2048.0), "2.0 MB/s")

    def test_uptime_parsing_and_formatting(self) -> None:
        """Validates /proc/uptime parsing and human-readable format strings."""
        uptime_file = self.proc_root / "uptime"
        uptime_file.write_text("18185.50 72000.12\n", encoding="utf-8")

        monitor = SystemMonitor(
            proc_root=self.proc_root,
            sys_root=self.sys_root,
            state_path=self.state_path,
        )
        state = monitor.get_state(now_ts=1000.0)
        self.assertEqual(state["uptime"]["uptime_sec"], 18185)
        self.assertEqual(state["uptime"]["uptime_str"], "5h 3m")

        self.assertEqual(format_uptime(0), "0m")
        self.assertEqual(format_uptime(120), "2m")
        self.assertEqual(format_uptime(3660), "1h 1m")
        self.assertEqual(format_uptime(90060), "1d 1h 1m")


if __name__ == "__main__":
    unittest.main()

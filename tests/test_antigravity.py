"""Automated unit tests for src/dpi_core/antigravity.py (100% mocked, CI-safe)."""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from dpi_core.antigravity import (  # noqa: E402
    AntigravityCollector,
    format_countdown,
    infer_model_group,
    prettify_model_id,
)


class _FakeHttpResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


class TestAntigravityCollector(unittest.TestCase):
    """Tests daemon discovery, pbtxt model mapping, quota grouping, pace/ETA, swarm & mtime_ns cache."""

    def test_daemon_discovery_hub_json_and_proc_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ag_dir = root / "antigravity"
            proc_dir = root / "proc"
            daemon_dir = ag_dir / "daemon"
            daemon_dir.mkdir(parents=True)

            # Stale hub JSON (pid 111 is NOT language_server)
            (proc_dir / "111").mkdir(parents=True)
            (proc_dir / "111" / "comm").write_text("bash\n", encoding="utf-8")
            (daemon_dir / "hub_stale.json").write_text(
                json.dumps({"pid": 111, "httpPort": 10001, "csrfToken": "bad"}),
                encoding="utf-8",
            )

            # Live hub JSON (pid 222 IS language_server_linux_x64)
            (proc_dir / "222").mkdir(parents=True)
            (proc_dir / "222" / "comm").write_text("language_server\n", encoding="utf-8")
            (daemon_dir / "hub_live.json").write_text(
                json.dumps({"pid": 222, "httpPort": 43210, "csrfToken": "tok-live"}),
                encoding="utf-8",
            )

            collector = AntigravityCollector(
                antigravity_dir=ag_dir,
                cache_path=root / "cache" / "ag_index.json",
                proc_dir=proc_dir,
            )
            daemon = collector.discover_daemon()
            self.assertIsNotNone(daemon)
            self.assertEqual(daemon["pid"], 222)
            self.assertEqual(daemon["http_port"], 43210)
            self.assertEqual(daemon["csrf_token"], "tok-live")

            # Remove hub_live.json and verify /proc/*/cmdline fallback
            (daemon_dir / "hub_live.json").unlink()
            (proc_dir / "333").mkdir(parents=True)
            (proc_dir / "333" / "cmdline").write_bytes(
                b"/opt/antigravity/language_server\x00--csrf_token=tok-proc\x00--http_port=45678\x00"
            )
            fallback = collector.discover_daemon()
            self.assertIsNotNone(fallback)
            self.assertEqual(fallback["pid"], 333)
            self.assertEqual(fallback["http_port"], 45678)
            self.assertEqual(fallback["csrf_token"], "tok-proc")
            self.assertEqual(fallback["source"], "proc_cmdline")

    def test_read_active_model_from_pbtxt_and_future_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ag_dir = root / "antigravity"
            ag_dir.mkdir(parents=True)
            pbtxt = ag_dir / "antigravity_state.pbtxt"

            collector = AntigravityCollector(
                antigravity_dir=ag_dir,
                cache_path=root / "ag_index.json",
                proc_dir=root / "proc",
            )

            cases = [
                ("MODEL_PLACEHOLDER_M668", "Orchestrator (Argon)", "argon"),
                ("MODEL_PLACEHOLDER_M532", "Gemini 4 Neon", "neon"),
                ("MODEL_PLACEHOLDER_M537", "Orchestrator (Neon)", "neon"),
                ("MODEL_PLACEHOLDER_M525", "Gemini 4 Hydrogen", "hydrogen"),
                ("MODEL_PLACEHOLDER_M417", "Gemini 4 Argon", "argon"),
                ("MODEL_PLACEHOLDER_M318", "Gemini 3.8 Flash", "flash"),
                ("MODEL_PLACEHOLDER_M400", "Claude 5.5", "claude_gpt"),
                ("MODEL_OPENAI_GPT_OSS_120B_MEDIUM", "GPT-OSS 120B", "claude_gpt"),
                ("MODEL_PLACEHOLDER_M670", "Gemini 4 Carbon", "carbon"),
            ]
            for model_id, expected_name, expected_group in cases:
                pbtxt.write_text(f'last_selected_agent_model: "{model_id}"\n', encoding="utf-8")
                res = collector.read_active_model()
                self.assertEqual(res["id"], model_id)
                self.assertEqual(res["name"], expected_name)
                self.assertEqual(res["group"], expected_group)

            # Future model resolved dynamically from clientModelConfigs label
            pbtxt.write_text('last_selected_agent_model: "MODEL_PLACEHOLDER_M999"\n', encoding="utf-8")
            future_cfgs = [
                {"modelOrAlias": {"model": "MODEL_PLACEHOLDER_M999"}, "label": "Gemini 5 Quantum (High)"}
            ]
            res_future = collector.read_active_model(future_cfgs)
            self.assertEqual(res_future["name"], "Gemini 5 Quantum")
            self.assertEqual(res_future["group"], "gemini_5_quantum")
            self.assertEqual(prettify_model_id("MODEL_GOOGLE_TITAN_2"), "Titan 2")
            self.assertEqual(infer_model_group("MODEL_X", "Future Ultra")[0], "future_ultra")

    def test_group_quotas_pace_marker_depletion_eta_and_future_groups(self) -> None:
        now_dt = datetime(2026, 11, 19, 12, 0, 0, tzinfo=timezone.utc)
        now_ts = now_dt.timestamp()

        def iso_in(seconds: float) -> str:
            return (now_dt + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")

        # 5h window = 18000s. If 2h remaining (7200s), elapsed = 3h = 60% pace.
        # Neon has 20% remaining (80% used > 60% pace): burn = 80%/3h = 26.67%/h -> ETA = 20/26.67 = 0.75h (45m) < 2h -> depletion_eta!
        # Hydrogen has 85% remaining (15% used < 60% pace): depletion_eta should be None.
        # Carbon on 7d window (e.g. 5d remaining -> elapsed 2d = 28.6% pace).
        client_configs = [
            {
                "label": "Gemini 4 Neon (High)",
                "modelOrAlias": {"model": "MODEL_PLACEHOLDER_M532"},
                "quotaInfo": {"remainingFraction": 0.20, "resetTime": iso_in(7200)},
            },
            {
                "label": "Gemini 4 Hydrogen (Medium)",
                "modelOrAlias": {"model": "MODEL_PLACEHOLDER_M525"},
                "quotaInfo": {"remainingFraction": 0.85, "resetTime": iso_in(7200)},
            },
            {
                "label": "Gemini 4 Argon (High)",
                "modelOrAlias": {"model": "MODEL_PLACEHOLDER_M417"},
                "quotaInfo": {"remainingFraction": 0.92, "resetTime": iso_in(14400)},
            },
            {
                "label": "Gemini 3.8 Flash",
                "modelOrAlias": {"model": "MODEL_PLACEHOLDER_M318"},
                "quotaInfo": {"remainingFraction": 0.99, "resetTime": iso_in(16200)},
            },
            {
                "label": "Claude 5.5 Opus",
                "modelOrAlias": {"model": "MODEL_PLACEHOLDER_M400"},
                "quotaInfo": {"remainingFraction": 0.55, "resetTime": iso_in(5 * 86400)},
            },
            {
                "label": "Gemini 4 Carbon",
                "modelOrAlias": {"model": "MODEL_PLACEHOLDER_M670"},
                "quotaInfo": {"remainingFraction": 0.70, "resetTime": iso_in(5 * 86400)},
            },
            {
                "label": "Nova Model 9",
                "modelOrAlias": {"model": "MODEL_PLACEHOLDER_M909"},
                "quotaInfo": {"remainingFraction": 0.65, "resetTime": iso_in(10800)},
            },
        ]

        collector = AntigravityCollector()
        quotas, lowest = collector.group_quotas(client_configs, now_ts=now_ts)
        by_id = {q["id"]: q for q in quotas}

        for expected_id in ("neon", "hydrogen", "argon", "flash", "claude_gpt", "carbon", "nova_model_9"):
            self.assertIn(expected_id, by_id)

        neon = by_id["neon"]
        self.assertEqual(neon["remaining_pct"], 20.0)
        self.assertEqual(neon["used_pct"], 80.0)
        self.assertEqual(neon["window"], "5h")
        self.assertEqual(neon["pace_pct"], 60.0)
        self.assertEqual(neon["reset_countdown"], "2h 0m")
        self.assertIsNotNone(neon["depletion_eta"])
        self.assertTrue(neon["depletion_eta"].startswith("⚡ ~"))

        hydrogen = by_id["hydrogen"]
        self.assertIsNone(hydrogen["depletion_eta"])

        carbon = by_id["carbon"]
        self.assertEqual(carbon["window"], "7d")
        self.assertEqual(carbon["reset_countdown"], "5d 0h")
        self.assertEqual(format_countdown(2 * 86400 + 3 * 3600), "2d 3h")

        self.assertIsNotNone(lowest)
        self.assertEqual(lowest["id"], "neon")

    def test_transcript_indexer_swarm_histogram_and_mtime_ns_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ag_dir = root / "antigravity"
            cache_path = root / "cache" / "ag_index.json"
            proc_dir = root / "proc"

            # Setup daemon + RPC
            (ag_dir / "daemon").mkdir(parents=True)
            (proc_dir / "777").mkdir(parents=True)
            (proc_dir / "777" / "comm").write_text("language_server\n", encoding="utf-8")
            (ag_dir / "daemon" / "hub_1.json").write_text(
                json.dumps({"pid": 777, "httpPort": 50001, "csrfToken": "secret-csrf"}),
                encoding="utf-8",
            )
            (ag_dir / "antigravity_state.pbtxt").write_text(
                'last_selected_agent_model: "MODEL_PLACEHOLDER_M525"\n',
                encoding="utf-8",
            )

            now_local = datetime.now().astimezone()
            today_iso = now_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            yesterday_iso = (now_local - timedelta(days=1)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            now_ts = now_local.timestamp()

            # Coordinator transcript
            coord_log = ag_dir / "brain" / "coord12345" / ".system_generated" / "logs" / "transcript.jsonl"
            coord_log.parent.mkdir(parents=True)
            coord_lines = [
                {
                    "step_index": 0,
                    "type": "USER_INPUT",
                    "created_at": yesterday_iso,
                    "content": "Active Workspaces:\n- /home/brendo/Projetos/Dynamic-Peripheral-Island\n",
                },
                {
                    "step_index": 1,
                    "type": "PLANNER_RESPONSE",
                    "created_at": yesterday_iso,
                    "input_tokens": 1000,
                    "cache_read_tokens": 2000,
                    "output_tokens": 300,
                    "tool_calls": [{"name": "swarm", "args": {"action": "add"}}],
                },
                {
                    "step_index": 2,
                    "type": "PLANNER_RESPONSE",
                    "created_at": today_iso,
                    "input_tokens": 500,
                    "cache_read_tokens": 1500,
                    "output_tokens": 200,
                    "tool_calls": [{"name": "read_board", "args": {}}],
                },
            ]
            coord_log.write_text("\n".join(json.dumps(x) for x in coord_lines) + "\n", encoding="utf-8")

            # Active worker transcript (working)
            worker_log = ag_dir / "brain" / "work99999" / ".system_generated" / "logs" / "transcript.jsonl"
            worker_log.parent.mkdir(parents=True)
            worker_lines = [
                {
                    "step_index": 0,
                    "type": "SYSTEM_MESSAGE",
                    "created_at": today_iso,
                    "content": "Your assignment (recorded on the board as #1 for @hw-engine): Trabalhe em `/home/brendo/Projetos/Dynamic-Peripheral-Island`",
                },
                {
                    "step_index": 1,
                    "type": "PLANNER_RESPONSE",
                    "created_at": today_iso,
                    "input_tokens": 400,
                    "cache_read_tokens": 600,
                    "output_tokens": 100,
                    "tool_calls": [{"name": "write_file", "args": {}}],
                },
            ]
            worker_log.write_text("\n".join(json.dumps(x) for x in worker_lines) + "\n", encoding="utf-8")

            rpc_payload = {
                "userStatus": {
                    "planStatus": {
                        "planInfo": {
                            "planName": "Pro",
                            "teamsTier": "PRO",
                            "monthlyPromptCredits": 50000,
                            "monthlyFlowCredits": 150000,
                        },
                        "availablePromptCredits": 42000,
                        "availableFlowCredits": 140000,
                    },
                    "cascadeModelConfigData": {
                        "clientModelConfigs": [
                            {
                                "label": "Gemini 4 Hydrogen (High)",
                                "modelOrAlias": {"model": "MODEL_PLACEHOLDER_M525"},
                                "quotaInfo": {
                                    "remainingFraction": 0.15,
                                    "resetTime": (now_local + timedelta(hours=3)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                },
                            }
                        ]
                    },
                }
            }

            captured_headers = {}

            def fake_urlopen(req, timeout=1.5):
                captured_headers.update(dict(req.header_items()))
                return _FakeHttpResp(json.dumps(rpc_payload).encode("utf-8"))

            collector = AntigravityCollector(
                antigravity_dir=ag_dir,
                cache_path=cache_path,
                proc_dir=proc_dir,
                rpc_opener=fake_urlopen,
            )

            snap = collector.collect(now_ts=now_ts)
            self.assertTrue(snap["connected"])
            self.assertEqual(captured_headers.get("X-codeium-csrf-token"), "secret-csrf")
            self.assertEqual(snap["plan"]["name"], "Pro")
            self.assertEqual(snap["active_model"]["name"], "Gemini 4 Hydrogen")
            self.assertEqual(snap["active_project"], "Dynamic-Peripheral-Island")
            self.assertEqual(snap["session_context"]["total_tokens"], 5500)
            self.assertEqual(snap["swarm"]["active_count"], 2)
            self.assertEqual(len(snap["daily_histogram_7d"]), 7)
            self.assertEqual(snap["daily_histogram_7d"][-1]["label"], "Hoje")
            self.assertEqual(snap["daily_histogram_7d"][-1]["tokens"], 3300)
            self.assertEqual(snap["daily_histogram_7d"][-2]["tokens"], 3300)
            self.assertEqual(snap["monthly"]["total_tokens"], 6600)
            self.assertTrue(cache_path.is_file())

            # Alerts should include swarm_active and low_quota
            alert_types = {a["type"] for a in snap["alerts"]}
            self.assertIn("swarm_active", alert_types)
            self.assertIn("low_quota", alert_types)

            # Second collect with identical mtime_ns & size must hit cache without re-parsing transcripts
            with mock.patch.object(collector, "_parse_transcript", side_effect=AssertionError("Should use mtime_ns cache")) as m_parse:
                snap2 = collector.collect(now_ts=now_ts)
                m_parse.assert_not_called()
            self.assertEqual(snap2["monthly"]["total_tokens"], 6600)

            # Modify worker transcript -> mtime_ns/size changes -> cache invalidates and re-parses
            worker_lines.append(
                {
                    "step_index": 2,
                    "type": "PLANNER_RESPONSE",
                    "created_at": today_iso,
                    "input_tokens": 100,
                    "cache_read_tokens": 0,
                    "output_tokens": 50,
                    "content": "@coordinator [done] finished",
                }
            )
            worker_log.write_text("\n".join(json.dumps(x) for x in worker_lines) + "\n", encoding="utf-8")
            os.utime(worker_log, ns=(worker_log.stat().st_atime_ns, worker_log.stat().st_mtime_ns + 1_000_000))
            snap3 = collector.collect(now_ts=now_ts)
            self.assertEqual(snap3["monthly"]["total_tokens"], 6750)
            # Worker posted [done] -> now IDLE
            roles = {a["role"]: a["status"] for a in snap3["swarm"]["agents"]}
            self.assertEqual(roles.get("hw-engine"), "IDLE")


if __name__ == "__main__":
    unittest.main()

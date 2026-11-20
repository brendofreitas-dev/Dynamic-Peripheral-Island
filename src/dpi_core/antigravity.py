"""Antigravity telemetry collector (daemon RPC, quotas, model state, and transcript indexer).

100% Python 3 standard library implementation with zero external dependencies.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

MODEL_ID_MAP: Dict[str, str] = {
    "MODEL_PLACEHOLDER_M668": "Orchestrator (Argon)",
    "MODEL_PLACEHOLDER_M532": "Gemini 4 Neon",
    "MODEL_PLACEHOLDER_M533": "Gemini 4 Neon",
    "MODEL_PLACEHOLDER_M534": "Gemini 4 Neon",
    "MODEL_PLACEHOLDER_M535": "Gemini 4 Neon",
    "MODEL_PLACEHOLDER_M537": "Orchestrator (Neon)",
    "MODEL_PLACEHOLDER_M525": "Gemini 4 Hydrogen",
    "MODEL_PLACEHOLDER_M526": "Gemini 4 Hydrogen",
    "MODEL_PLACEHOLDER_M527": "Gemini 4 Hydrogen",
    "MODEL_PLACEHOLDER_M528": "Gemini 4 Hydrogen",
    "MODEL_PLACEHOLDER_M417": "Gemini 4 Argon",
    "MODEL_PLACEHOLDER_M418": "Gemini 4 Argon",
    "MODEL_PLACEHOLDER_M419": "Gemini 4 Argon",
    "MODEL_PLACEHOLDER_M318": "Gemini 3.8 Flash",
    "MODEL_PLACEHOLDER_M319": "Gemini 3.8 Flash",
    "MODEL_PLACEHOLDER_M320": "Gemini 3.8 Flash",
    "MODEL_PLACEHOLDER_M400": "Claude 5.5",
    "MODEL_PLACEHOLDER_M401": "Claude 5.5",
    "MODEL_PLACEHOLDER_M402": "Claude 5.5",
    "MODEL_PLACEHOLDER_M403": "Claude 5.5",
    "MODEL_PLACEHOLDER_M404": "Claude 5.5",
    "MODEL_PLACEHOLDER_M405": "Claude 5.5",
    "MODEL_OPENAI_GPT_OSS_120B_MEDIUM": "GPT-OSS 120B",
    "MODEL_PLACEHOLDER_M670": "Gemini 4 Carbon",
}

KNOWN_GROUP_SPECS: List[Dict[str, Any]] = [
    {
        "id": "neon",
        "name": "Gemini 4 Neon",
        "short_name": "Neon",
        "model_ids": {
            "MODEL_PLACEHOLDER_M532",
            "MODEL_PLACEHOLDER_M533",
            "MODEL_PLACEHOLDER_M534",
            "MODEL_PLACEHOLDER_M535",
            "MODEL_PLACEHOLDER_M537",
        },
        "keywords": ("neon",),
    },
    {
        "id": "hydrogen",
        "name": "Gemini 4 Hydrogen",
        "short_name": "Hydrogen",
        "model_ids": {
            "MODEL_PLACEHOLDER_M525",
            "MODEL_PLACEHOLDER_M526",
            "MODEL_PLACEHOLDER_M527",
            "MODEL_PLACEHOLDER_M528",
        },
        "keywords": ("hydrogen",),
    },
    {
        "id": "argon",
        "name": "Orchestrator / Argon",
        "short_name": "Argon",
        "model_ids": {
            "MODEL_PLACEHOLDER_M417",
            "MODEL_PLACEHOLDER_M418",
            "MODEL_PLACEHOLDER_M419",
            "MODEL_PLACEHOLDER_M668",
        },
        "keywords": ("argon", "orchestrator (argon)"),
    },
    {
        "id": "flash",
        "name": "Gemini 3.8 Flash",
        "short_name": "Flash",
        "model_ids": {
            "MODEL_PLACEHOLDER_M318",
            "MODEL_PLACEHOLDER_M319",
            "MODEL_PLACEHOLDER_M320",
        },
        "keywords": ("flash",),
    },
    {
        "id": "claude_gpt",
        "name": "Claude 5.5 & GPT-OSS",
        "short_name": "Claude/GPT",
        "model_ids": {
            "MODEL_PLACEHOLDER_M400",
            "MODEL_PLACEHOLDER_M401",
            "MODEL_PLACEHOLDER_M402",
            "MODEL_PLACEHOLDER_M403",
            "MODEL_PLACEHOLDER_M404",
            "MODEL_PLACEHOLDER_M405",
            "MODEL_OPENAI_GPT_OSS_120B_MEDIUM",
        },
        "keywords": ("claude", "gpt-oss", "gpt_oss", "opus", "sonnet"),
    },
    {
        "id": "carbon",
        "name": "Gemini 4 Carbon",
        "short_name": "Carbon",
        "model_ids": {"MODEL_PLACEHOLDER_M670"},
        "keywords": ("carbon",),
    },
]

_KNOWN_GROUP_MAP: Dict[str, Dict[str, Any]] = {spec["id"]: spec for spec in KNOWN_GROUP_SPECS}
_TIER_SUFFIX_RE = re.compile(r"\s*\((?:Low|Medium|High|XHigh|Minimal|Max)\)\s*$", re.IGNORECASE)
_SELECTED_MODEL_RE = re.compile(r'last_selected_agent_model\s*:\s*"?([A-Za-z0-9_.-]+)"?')
_SWARM_ASSIGN_RE = re.compile(r"recorded on the board as #\d+ for @([a-zA-Z0-9_-]+)")
_PROJECT_PATH_RE = re.compile(
    r"(?:Active Workspaces:\s*\n-\s*|Command Working Directory:\s*|Trabalhe em\s*`?)"
    r"(/[^\s`'\"]+)"
)
_ANY_PROJ_RE = re.compile(r"/(?:Projetos|Projects|workspace|repos)/([A-Za-z0-9._-]+)")
_PT_WEEKDAYS = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")

FIVE_HOURS_SEC = 5 * 3600
SEVEN_DAYS_SEC = 7 * 86400


def parse_iso_utc(value: Optional[str]) -> Optional[float]:
    """Parse an ISO-8601 timestamp (typically UTC with trailing 'Z') into epoch seconds."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def format_countdown(delta_seconds: float) -> str:
    """Format remaining seconds into compact `Xd Yh` or `Xh Ym` strings."""
    sec = max(0, int(delta_seconds))
    days, rem = divmod(sec, 86400)
    hours, rem = divmod(rem, 3600)
    mins = rem // 60
    if days > 0:
        return f"{days}d {hours}h"
    if hours > 0:
        return f"{hours}h {mins}m"
    return f"{mins}m"


def prettify_model_id(raw_id: str) -> str:
    """Create a human-readable fallback name for unknown model identifiers."""
    if not raw_id:
        return "Desconhecido"
    if raw_id in MODEL_ID_MAP:
        return MODEL_ID_MAP[raw_id]
    cleaned = raw_id
    for prefix in ("MODEL_PLACEHOLDER_", "MODEL_OPENAI_", "MODEL_ANTHROPIC_", "MODEL_GOOGLE_", "MODEL_"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]
            break
    if re.fullmatch(r"M\d+", cleaned):
        return f"Model {cleaned}"
    parts = [p for p in cleaned.replace("-", "_").split("_") if p]
    formatted: List[str] = []
    for part in parts:
        upper = part.upper()
        if upper in {"GPT", "OSS", "AI"}:
            formatted.append(upper)
        elif re.fullmatch(r"\d+[A-Z]?", upper):
            formatted.append(upper)
        else:
            formatted.append(part.capitalize())
    return " ".join(formatted) if formatted else raw_id


def infer_model_group(raw_id: str, label: str = "") -> Tuple[str, str, str]:
    """Return `(group_id, group_name, short_name)` for a model ID and display label."""
    low_label = (label or "").lower()
    for spec in KNOWN_GROUP_SPECS:
        if raw_id in spec["model_ids"] or any(kw in low_label for kw in spec["keywords"]):
            return spec["id"], spec["name"], spec["short_name"]

    base_name = _TIER_SUFFIX_RE.sub("", label).strip() if label else prettify_model_id(raw_id)
    slug = re.sub(r"[^a-z0-9]+", "_", base_name.lower()).strip("_") or "other"
    short = base_name if len(base_name) <= 14 else base_name.split()[0]
    return slug, base_name, short


def _safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _extract_project_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    m = _PROJECT_PATH_RE.search(text)
    if m:
        candidate = Path(m.group(1)).name
        if candidate and candidate not in {".gemini", "antigravity", "tmp"}:
            return candidate
    m2 = _ANY_PROJ_RE.search(text)
    if m2:
        return m2.group(1)
    return None


class AntigravityCollector:
    """Collects Antigravity daemon quotas, active model, swarm agents, and token telemetry."""

    def __init__(
        self,
        antigravity_dir: Optional[Path] = None,
        cache_path: Optional[Path] = None,
        proc_dir: Optional[Path] = None,
        rpc_timeout: float = 1.5,
        rpc_opener: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.antigravity_dir = Path(antigravity_dir) if antigravity_dir else Path.home() / ".gemini" / "antigravity"
        self.cache_path = (
            Path(cache_path)
            if cache_path
            else Path.home() / ".cache" / "dynamic-peripheral-island" / "ag_index.json"
        )
        self.proc_dir = Path(proc_dir) if proc_dir else Path("/proc")
        self.rpc_timeout = float(rpc_timeout)
        self._rpc_opener = rpc_opener or urllib.request.urlopen

    def _is_language_server_pid(self, pid: int) -> bool:
        proc_pid = self.proc_dir / str(pid)
        if not proc_pid.is_dir():
            return False
        comm = _safe_read_text(proc_pid / "comm").strip()
        if "language_server" in comm:
            return True
        try:
            raw = (proc_pid / "cmdline").read_bytes()
        except OSError:
            return False
        cmdline = raw.replace(b"\x00", b" ").decode("utf-8", errors="replace")
        return "language_server" in cmdline

    def _scan_proc_for_daemon(self) -> Optional[Dict[str, Any]]:
        if not self.proc_dir.is_dir():
            return None
        try:
            entries = sorted(self.proc_dir.iterdir(), key=lambda p: p.name)
        except OSError:
            return None

        for entry in entries:
            if not entry.name.isdigit():
                continue
            try:
                raw = (entry / "cmdline").read_bytes()
            except OSError:
                continue
            args = [a for a in raw.decode("utf-8", errors="replace").split("\x00") if a]
            if not args or not any("language_server" in a for a in args):
                continue

            csrf_token: Optional[str] = None
            http_port: Optional[int] = None
            for idx, arg in enumerate(args):
                if arg.startswith("--csrf_token="):
                    csrf_token = arg.split("=", 1)[1]
                elif arg == "--csrf_token" and idx + 1 < len(args):
                    csrf_token = args[idx + 1]
                elif arg.startswith("--http_port="):
                    http_port = self._parse_int(arg.split("=", 1)[1])
                elif arg == "--http_port" and idx + 1 < len(args):
                    http_port = self._parse_int(args[idx + 1])
                elif arg.startswith("--extension_server_port=") and http_port is None:
                    http_port = self._parse_int(arg.split("=", 1)[1])
                elif arg == "--extension_server_port" and idx + 1 < len(args) and http_port is None:
                    http_port = self._parse_int(args[idx + 1])
                elif arg.startswith("--server_port=") and http_port is None:
                    http_port = self._parse_int(arg.split("=", 1)[1])
                elif arg == "--server_port" and idx + 1 < len(args) and http_port is None:
                    http_port = self._parse_int(args[idx + 1])

            if csrf_token and http_port:
                return {
                    "pid": int(entry.name),
                    "http_port": http_port,
                    "https_port": None,
                    "csrf_token": csrf_token,
                    "ls_version": None,
                    "source": "proc_cmdline",
                }
        return None

    @staticmethod
    def _parse_int(val: Any) -> Optional[int]:
        try:
            return int(val)
        except (TypeError, ValueError):
            return None

    def discover_daemon(self) -> Optional[Dict[str, Any]]:
        """Locate the active Antigravity language_server daemon via hub_*.json or /proc."""
        daemon_dir = self.antigravity_dir / "daemon"
        hub_files: List[Path] = []
        if daemon_dir.is_dir():
            try:
                hub_files = sorted(
                    daemon_dir.glob("hub_*.json"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
            except OSError:
                hub_files = []

        for hub_file in hub_files:
            try:
                data = json.loads(hub_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            pid = self._parse_int(data.get("pid"))
            http_port = self._parse_int(data.get("httpPort"))
            csrf_token = data.get("csrfToken")
            if pid and http_port and csrf_token and self._is_language_server_pid(pid):
                return {
                    "pid": pid,
                    "http_port": http_port,
                    "https_port": self._parse_int(data.get("httpsPort")),
                    "csrf_token": str(csrf_token),
                    "ls_version": data.get("lsVersion"),
                    "source": hub_file.name,
                }

        return self._scan_proc_for_daemon()

    def fetch_user_status(self, daemon: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Query ConnectRPC GetUserStatus from the active daemon."""
        url = f"http://127.0.0.1:{daemon['http_port']}/exa.language_server_pb.LanguageServerService/GetUserStatus"
        req = urllib.request.Request(
            url,
            data=b"{}",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "x-codeium-csrf-token": daemon["csrf_token"],
            },
        )
        try:
            with self._rpc_opener(req, timeout=self.rpc_timeout) as resp:
                raw = resp.read()
            payload = json.loads(raw.decode("utf-8"))
            if isinstance(payload, dict):
                return payload.get("userStatus", payload)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, json.JSONDecodeError):
            return None
        return None

    def read_active_model(self, client_configs: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Read `last_selected_agent_model` from antigravity_state.pbtxt and resolve its name."""
        pbtxt = _safe_read_text(self.antigravity_dir / "antigravity_state.pbtxt")
        match = _SELECTED_MODEL_RE.search(pbtxt)
        raw_id = match.group(1) if match else ""

        matched_label = ""
        if raw_id and client_configs:
            for cfg in client_configs:
                alias_id = (cfg.get("modelOrAlias") or {}).get("model")
                if alias_id == raw_id:
                    matched_label = str(cfg.get("label") or "")
                    break

        if raw_id in MODEL_ID_MAP:
            name = MODEL_ID_MAP[raw_id]
        elif matched_label:
            name = _TIER_SUFFIX_RE.sub("", matched_label).strip() or matched_label
        elif raw_id:
            name = prettify_model_id(raw_id)
        else:
            name = "Desconhecido"

        group_id, _, _ = infer_model_group(raw_id, matched_label or name)
        return {
            "id": raw_id or "UNKNOWN",
            "name": name,
            "label": matched_label or name,
            "group": group_id,
        }

    def group_quotas(
        self,
        client_configs: Iterable[Dict[str, Any]],
        now_ts: float,
    ) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """Group clientModelConfigs into quota buckets with pace marker and depletion ETA."""
        buckets: Dict[str, Dict[str, Any]] = {}

        for cfg in client_configs:
            raw_id = str((cfg.get("modelOrAlias") or {}).get("model") or cfg.get("modelId") or "")
            label = str(cfg.get("label") or prettify_model_id(raw_id))
            group_id, group_name, short_name = infer_model_group(raw_id, label)

            bucket = buckets.setdefault(
                group_id,
                {
                    "id": group_id,
                    "name": group_name,
                    "short_name": short_name,
                    "fractions": [],
                    "reset_times": [],
                    "models": [],
                    "disabled": True,
                },
            )
            if label and label not in bucket["models"]:
                bucket["models"].append(label)

            qinfo = cfg.get("quotaInfo") or {}
            if "remainingFraction" in qinfo and qinfo["remainingFraction"] is not None:
                try:
                    frac = float(qinfo["remainingFraction"])
                except (TypeError, ValueError):
                    frac = None
                if frac is not None:
                    bucket["fractions"].append(max(0.0, min(1.0, frac)))
                    bucket["disabled"] = False
            reset_iso = qinfo.get("resetTime")
            if isinstance(reset_iso, str) and reset_iso.strip():
                bucket["reset_times"].append(reset_iso.strip())

        known_order = [spec["id"] for spec in KNOWN_GROUP_SPECS]
        ordered_ids = [gid for gid in known_order if gid in buckets] + [
            gid for gid in buckets if gid not in known_order
        ]

        quotas: List[Dict[str, Any]] = []
        for gid in ordered_ids:
            b = buckets[gid]
            if b["fractions"]:
                remaining_frac = min(b["fractions"])
                remaining_pct = round(remaining_frac * 100.0, 1)
                used_pct = round(max(0.0, 100.0 - remaining_pct), 1)
                enabled = True
            else:
                remaining_pct = 0.0
                used_pct = 0.0
                enabled = False

            reset_iso: Optional[str] = None
            reset_ts: Optional[float] = None
            for cand_iso in b["reset_times"]:
                cand_ts = parse_iso_utc(cand_iso)
                if cand_ts is not None and (reset_ts is None or cand_ts < reset_ts):
                    reset_ts = cand_ts
                    reset_iso = cand_iso

            reset_countdown = "--"
            pace_pct = 0.0
            depletion_eta: Optional[str] = None
            window_label = "5h"

            if enabled and reset_ts is not None:
                delta_sec = max(0.0, reset_ts - now_ts)
                reset_countdown = format_countdown(delta_sec)
                window_sec = SEVEN_DAYS_SEC if delta_sec > 6 * 3600 else FIVE_HOURS_SEC
                window_label = "7d" if window_sec == SEVEN_DAYS_SEC else "5h"
                elapsed_sec = max(0.0, min(float(window_sec), float(window_sec) - delta_sec))
                pace_pct = round((elapsed_sec / float(window_sec)) * 100.0, 1)

                if elapsed_sec >= 60.0 and used_pct > pace_pct and used_pct > 0.5 and remaining_pct > 0.0:
                    elapsed_hours = elapsed_sec / 3600.0
                    burn_rate_per_hour = used_pct / elapsed_hours
                    if burn_rate_per_hour > 0.0:
                        eta_hours = remaining_pct / burn_rate_per_hour
                        if eta_hours < (delta_sec / 3600.0):
                            if eta_hours >= 24.0:
                                depletion_eta = f"~{eta_hours / 24.0:.1f}d"
                            elif eta_hours >= 1.0:
                                depletion_eta = f"~{eta_hours:.1f}h"
                            else:
                                depletion_eta = f"~{max(1, int(round(eta_hours * 60.0)))}m"

            quotas.append(
                {
                    "id": b["id"],
                    "name": b["name"],
                    "short_name": b["short_name"],
                    "enabled": enabled,
                    "remaining_pct": remaining_pct,
                    "used_pct": used_pct,
                    "reset_time_iso": reset_iso,
                    "reset_countdown": reset_countdown,
                    "window": window_label,
                    "pace_pct": pace_pct,
                    "depletion_eta": depletion_eta,
                    "models": b["models"],
                }
            )

        enabled_quotas = [q for q in quotas if q["enabled"]]
        lowest = min(enabled_quotas, key=lambda q: q["remaining_pct"]) if enabled_quotas else None
        return quotas, lowest

    def _load_index_cache(self) -> Dict[str, Any]:
        if not self.cache_path.is_file():
            return {"version": 2, "files": {}}
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("files"), dict):
                if data.get("version") == 2:
                    return data
        except (OSError, json.JSONDecodeError):
            pass
        return {"version": 2, "files": {}}

    def _save_index_cache(self, cache: Dict[str, Any]) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.cache_path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp_path, self.cache_path)
        except OSError:
            pass

    def _parse_transcript(self, path: Path, mtime_ns: int, size: int) -> Dict[str, Any]:
        # Path format: .../brain/<conv_id>/.system_generated/logs/transcript.jsonl
        conv_id = path.parent.parent.parent.name
        project: Optional[str] = None
        role = "agent"
        is_swarm_worker = False
        is_coordinator = False
        steps = 0
        last_step_ts = float(mtime_ns) / 1e9
        last_step_type = ""
        last_step_status = ""
        last_tool_names: List[str] = []
        last_planner_tools: List[str] = []
        last_planner_had_wait = False
        last_is_wait_output = False
        last_content = ""

        input_tokens = 0
        cache_read_tokens = 0
        output_tokens = 0
        daily: Dict[str, Dict[str, int]] = {}
        monthly: Dict[str, Dict[str, int]] = {}

        local_tz = datetime.now().astimezone().tzinfo

        try:
            with path.open("r", encoding="utf-8", errors="replace") as fp:
                for line in fp:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(obj, dict):
                        continue

                    step_idx = obj.get("step_index")
                    if isinstance(step_idx, int):
                        steps = max(steps, step_idx + 1)
                    else:
                        steps += 1

                    step_type = str(obj.get("type") or "")
                    last_step_type = step_type
                    step_status = str(obj.get("status") or "")
                    last_step_status = step_status
                    created_ts = parse_iso_utc(obj.get("created_at"))
                    if created_ts is not None:
                        last_step_ts = created_ts

                    content = str(obj.get("content") or "")
                    last_content = content

                    if step_type == "USER_INPUT":
                        last_planner_had_wait = False
                        last_is_wait_output = False

                    if step_type == "SYSTEM_MESSAGE":
                        m_role = _SWARM_ASSIGN_RE.search(content)
                        if m_role:
                            role = m_role.group(1)
                            is_swarm_worker = True

                    if project is None and content:
                        project = _extract_project_from_text(content)

                    tool_calls = obj.get("tool_calls") or []
                    if isinstance(tool_calls, list) and tool_calls:
                        names: List[str] = []
                        for tc in tool_calls:
                            if not isinstance(tc, dict):
                                continue
                            tname = str(tc.get("name") or "")
                            if tname:
                                names.append(tname)
                            if tname == "swarm":
                                is_coordinator = True
                                if not is_swarm_worker:
                                    role = "coordinator"
                            if project is None:
                                args = tc.get("args") or {}
                                if isinstance(args, dict):
                                    for key in ("Path", "TargetFile", "SearchPath", "Cwd", "CommandLine"):
                                        val = str(args.get(key) or "")
                                        proj = _extract_project_from_text(val) or (
                                            _ANY_PROJ_RE.search(val).group(1) if _ANY_PROJ_RE.search(val) else None
                                        )
                                        if proj:
                                            project = proj
                                            break
                        last_tool_names = names
                    elif step_type == "PLANNER_RESPONSE":
                        last_tool_names = []

                    if step_type == "PLANNER_RESPONSE":
                        last_planner_tools = list(last_tool_names)
                        last_planner_had_wait = "swarm_wait" in last_planner_tools
                        last_is_wait_output = False
                    elif step_type == "GENERIC":
                        if "Waiting for " in content:
                            last_is_wait_output = True

                    if step_type == "PLANNER_RESPONSE":
                        inp = int(obj.get("input_tokens") or 0)
                        cache = int(obj.get("cache_read_tokens") or 0)
                        out = int(obj.get("output_tokens") or 0)
                        tot = inp + cache + out

                        input_tokens += inp
                        cache_read_tokens += cache
                        output_tokens += out

                        if created_ts is not None:
                            dt = datetime.fromtimestamp(created_ts, tz=timezone.utc).astimezone(local_tz)
                            day_key = dt.strftime("%Y-%m-%d")
                            month_key = dt.strftime("%Y-%m")
                            d_rec = daily.setdefault(day_key, {"input": 0, "cache": 0, "output": 0, "total": 0})
                            d_rec["input"] += inp
                            d_rec["cache"] += cache
                            d_rec["output"] += out
                            d_rec["total"] += tot

                            m_rec = monthly.setdefault(month_key, {"input": 0, "cache": 0, "output": 0, "total": 0})
                            m_rec["input"] += inp
                            m_rec["cache"] += cache
                            m_rec["output"] += out
                            m_rec["total"] += tot
        except OSError:
            pass

        if project is None:
            ann_text = _safe_read_text(self.antigravity_dir / "annotations" / f"{conv_id}.pbtxt")
            m_title = re.search(r'title\s*:\s*"([^"]+)"', ann_text)
            project = m_title.group(1) if m_title else conv_id[:8]

        total_tokens = input_tokens + cache_read_tokens + output_tokens
        return {
            "schema_version": 2,
            "mtime_ns": mtime_ns,
            "size": size,
            "conv_id": conv_id,
            "project": project,
            "role": role,
            "is_swarm_worker": is_swarm_worker,
            "is_coordinator": is_coordinator,
            "steps": steps,
            "last_step_ts": last_step_ts,
            "last_step_type": last_step_type,
            "last_step_status": last_step_status,
            "last_tool_names": last_tool_names,
            "last_planner_tools": last_planner_tools,
            "last_planner_had_wait": last_planner_had_wait,
            "last_is_wait_output": last_is_wait_output,
            "last_done": "[done]" in last_content,
            "input_tokens": input_tokens,
            "cache_read_tokens": cache_read_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "daily": daily,
            "monthly": monthly,
        }

    def index_transcripts(self, now_ts: float) -> Dict[str, Any]:
        """Incrementally index transcript.jsonl files using mtime_ns + size cache."""
        brain_dir = self.antigravity_dir / "brain"
        transcript_paths: List[Path] = []
        if brain_dir.is_dir():
            transcript_paths = list(brain_dir.glob("*/.system_generated/logs/transcript.jsonl"))

        cache = self._load_index_cache()
        files_cache: Dict[str, Any] = cache.get("files", {})
        dirty = False

        seen_keys = set()
        records: List[Dict[str, Any]] = []

        for path in transcript_paths:
            key = str(path)
            seen_keys.add(key)
            try:
                st = path.stat()
            except OSError:
                continue

            cached = files_cache.get(key)
            if (
                isinstance(cached, dict)
                and cached.get("schema_version") == 2
                and cached.get("mtime_ns") == st.st_mtime_ns
                and cached.get("size") == st.st_size
            ):
                records.append(cached)
            else:
                rec = self._parse_transcript(path, st.st_mtime_ns, st.st_size)
                files_cache[key] = rec
                records.append(rec)
                dirty = True

        stale_keys = [k for k in list(files_cache.keys()) if k not in seen_keys]
        if stale_keys:
            for k in stale_keys:
                del files_cache[k]
            dirty = True

        if dirty:
            cache["version"] = 2
            cache["files"] = files_cache
            self._save_index_cache(cache)

        records.sort(key=lambda r: r.get("mtime_ns", 0), reverse=True)

        # Active project & session context: most recent session with tokens (preferring main/coordinator if active)
        active_rec: Optional[Dict[str, Any]] = None
        with_tokens = [r for r in records if r.get("total_tokens", 0) > 0]
        if with_tokens:
            newest_ts = with_tokens[0]["mtime_ns"] / 1e9
            recent_non_workers = [
                r
                for r in with_tokens
                if not r.get("is_swarm_worker") and (newest_ts - (r["mtime_ns"] / 1e9)) <= 300.0
            ]
            active_rec = recent_non_workers[0] if recent_non_workers else with_tokens[0]
        elif records:
            active_rec = records[0]

        active_project = active_rec["project"] if active_rec else "Nenhum"
        session_context = {
            "active_project": active_project,
            "conversation_id": active_rec["conv_id"][:8] if active_rec else "",
            "input_tokens": int(active_rec["input_tokens"]) if active_rec else 0,
            "cache_read_tokens": int(active_rec["cache_read_tokens"]) if active_rec else 0,
            "output_tokens": int(active_rec["output_tokens"]) if active_rec else 0,
            "total_tokens": int(active_rec["total_tokens"]) if active_rec else 0,
        }

        # Swarm tracking (active within last 10 minutes)
        swarm_agents: List[Dict[str, Any]] = []
        for rec in records:
            if not (rec.get("is_swarm_worker") or rec.get("is_coordinator")):
                continue
            age_sec = now_ts - (rec.get("mtime_ns", 0) / 1e9)
            if age_sec > 600.0:
                continue

            last_type = str(rec.get("last_step_type") or "")
            last_status = str(rec.get("last_step_status") or "")
            planner_tools = rec.get("last_planner_tools") or []

            is_idle = (
                (last_type == "PLANNER_RESPONSE" and last_status == "DONE" and not planner_tools)
                or bool(rec.get("last_planner_had_wait"))
                or bool(rec.get("last_is_wait_output"))
                or bool(rec.get("last_done"))
                or (now_ts - float(rec.get("last_step_ts", 0.0))) > 45.0
            )
            status = "IDLE" if is_idle else "WORKING"
            swarm_agents.append(
                {
                    "id": rec["conv_id"][:8],
                    "role": rec["role"],
                    "status": status,
                    "steps": int(rec.get("steps", 0)),
                }
            )

        active_count = sum(1 for a in swarm_agents if a["status"] == "WORKING")
        swarm = {
            "active_count": active_count,
            "total_count": len(swarm_agents),
            "agents": swarm_agents,
        }

        # 7-day histogram + monthly aggregation in local timezone
        local_tz = datetime.now().astimezone().tzinfo
        now_local = datetime.fromtimestamp(now_ts, tz=timezone.utc).astimezone(local_tz)
        today_date = now_local.date()
        current_month = now_local.strftime("%Y-%m")

        daily_totals: Dict[str, int] = {}
        monthly_input = 0
        monthly_cache = 0
        monthly_output = 0
        monthly_total = 0
        project_monthly: Dict[str, int] = {}

        for rec in records:
            for dkey, dvals in (rec.get("daily") or {}).items():
                daily_totals[dkey] = daily_totals.get(dkey, 0) + int(dvals.get("total", 0))
            mvals = (rec.get("monthly") or {}).get(current_month)
            if mvals:
                monthly_input += int(mvals.get("input", 0))
                monthly_cache += int(mvals.get("cache", 0))
                monthly_output += int(mvals.get("output", 0))
                mtot = int(mvals.get("total", 0))
                monthly_total += mtot
                pname = rec.get("project") or "Outros"
                project_monthly[pname] = project_monthly.get(pname, 0) + mtot

        daily_histogram_7d: List[Dict[str, Any]] = []
        for offset in range(6, -1, -1):
            day = today_date - timedelta(days=offset)
            dkey = day.strftime("%Y-%m-%d")
            label = "Hoje" if offset == 0 else _PT_WEEKDAYS[day.weekday()]
            daily_histogram_7d.append(
                {
                    "date": dkey,
                    "label": label,
                    "tokens": daily_totals.get(dkey, 0),
                }
            )

        top_projects = [
            {"name": name, "tokens": tok}
            for name, tok in sorted(project_monthly.items(), key=lambda kv: kv[1], reverse=True)[:5]
            if tok > 0
        ]

        monthly = {
            "month": current_month,
            "total_tokens": monthly_total,
            "input_tokens": monthly_input,
            "cache_tokens": monthly_cache,
            "output_tokens": monthly_output,
            "top_projects": top_projects,
        }

        return {
            "active_project": active_project,
            "session_context": session_context,
            "swarm": swarm,
            "daily_histogram_7d": daily_histogram_7d,
            "monthly": monthly,
        }

    def collect(self, now_ts: Optional[float] = None) -> Dict[str, Any]:
        """Collect complete Antigravity telemetry snapshot."""
        now = float(now_ts) if now_ts is not None else time.time()

        daemon = self.discover_daemon()
        user_status = self.fetch_user_status(daemon) if daemon else None
        connected = user_status is not None

        plan_status = (user_status or {}).get("planStatus") or {}
        plan_info = plan_status.get("planInfo") or {}
        plan = {
            "name": plan_info.get("planName") or ("Offline" if not connected else "Free"),
            "tier": plan_info.get("teamsTier") or "",
            "prompt_credits": plan_status.get("availablePromptCredits", 0),
            "monthly_prompt_credits": plan_info.get("monthlyPromptCredits", 0),
            "flow_credits": plan_status.get("availableFlowCredits", 0),
            "monthly_flow_credits": plan_info.get("monthlyFlowCredits", 0),
        }

        client_configs = ((user_status or {}).get("cascadeModelConfigData") or {}).get("clientModelConfigs") or []
        active_model = self.read_active_model(client_configs)
        quotas, lowest_quota = self.group_quotas(client_configs, now)
        transcript_data = self.index_transcripts(now)

        alerts: List[Dict[str, Any]] = []
        if transcript_data["swarm"]["active_count"] > 0:
            alerts.append(
                {
                    "type": "swarm_active",
                    "severity": "info",
                    "source": "antigravity",
                    "title": "Swarm Ativo",
                    "message": f"{transcript_data['swarm']['active_count']} agente(s) trabalhando",
                }
            )
        for q in quotas:
            if q["enabled"] and q["remaining_pct"] <= 20.0:
                alerts.append(
                    {
                        "type": "low_quota",
                        "severity": "critical" if q["remaining_pct"] <= 10.0 else "warning",
                        "source": "antigravity",
                        "title": f"Cota Baixa: {q['short_name']}",
                        "message": f"{q['remaining_pct']:.0f}% restante ({q['reset_countdown']})",
                    }
                )

        return {
            "connected": connected,
            "plan": plan,
            "active_model": active_model,
            "active_project": transcript_data["active_project"],
            "quotas": quotas,
            "lowest_quota": lowest_quota,
            "swarm": transcript_data["swarm"],
            "session_context": transcript_data["session_context"],
            "daily_histogram_7d": transcript_data["daily_histogram_7d"],
            "monthly": transcript_data["monthly"],
            "alerts": alerts,
        }

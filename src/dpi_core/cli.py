"""Unified CLI, settings manager, and Island/Waybar/Pretty formatters for dpi-hub.

100% Python 3 standard library implementation with zero external dependencies.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dpi_core.antigravity import AntigravityCollector

VERSION = "1.0.0"

DEFAULT_SETTINGS: Dict[str, Any] = {
    "pin_mouse": True,
    "pin_headset": False,
    "pin_gamepad": False,
    "pin_keyboard": False,
    "pinned_quota": "auto",
    "battery_alert_threshold": 20,
    "poll_interval": 5,
    "theme_mode": "auto",
}

DEFAULT_SETTINGS_PATH = Path.home() / ".config" / "dynamic-peripheral-island" / "settings.json"

DEVICE_META: Dict[str, Dict[str, str]] = {
    "mouse": {"name": "AJAZZ AJ179 V2", "icon": "mouse", "short": "Mouse"},
    "headset": {"name": "Havit Fuxi H3", "icon": "headset", "short": "Headset"},
    "gamepad": {"name": "Gamepad", "icon": "gamepad", "short": "Ctrl"},
    "keyboard": {"name": "Machenike K500-B94", "icon": "keyboard", "short": "K500"},
}


def load_settings(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load persisted user preferences merged with defaults."""
    target = Path(path) if path else DEFAULT_SETTINGS_PATH
    settings = dict(DEFAULT_SETTINGS)
    if target.is_file():
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for key in DEFAULT_SETTINGS:
                    if key in raw:
                        settings[key] = raw[key]
        except (OSError, json.JSONDecodeError):
            pass
    return settings


def save_settings(settings: Dict[str, Any], path: Optional[Path] = None) -> None:
    """Persist user preferences atomically."""
    target = Path(path) if path else DEFAULT_SETTINGS_PATH
    merged = dict(DEFAULT_SETTINGS)
    merged.update({k: v for k, v in settings.items() if k in DEFAULT_SETTINGS})
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, target)


def _parse_bool(value: str) -> bool:
    low = value.strip().lower()
    if low in {"1", "true", "on", "yes", "sim"}:
        return True
    if low in {"0", "false", "off", "no", "nao", "não"}:
        return False
    raise ValueError(f"Valor booleano inválido: {value!r}")


def _get_hardware_manager() -> Any:
    from dpi_core.hardware import HardwareHubManager

    return HardwareHubManager()


def _get_audio_manager() -> Any:
    try:
        from dpi_core.audio import AudioMixerManager

        return AudioMixerManager()
    except Exception:
        return None


def _get_media_manager() -> Any:
    try:
        from dpi_core.audio import MediaPlayerManager

        return MediaPlayerManager()
    except Exception:
        return None


def _safe_audio_state(audio_manager: Any = None) -> Dict[str, Any]:
    if audio_manager is None:
        audio_manager = _get_audio_manager()
    if audio_manager is not None:
        try:
            state = audio_manager.get_state()
            if isinstance(state, dict):
                return state
        except Exception as exc:
            return {
                "error": str(exc),
                "master": {},
                "outputs": [],
                "mic": {},
                "inputs": [],
                "apps": [],
            }
    return {"master": {}, "outputs": [], "mic": {}, "inputs": [], "apps": []}


def _safe_media_state(media_manager: Any = None) -> Dict[str, Any]:
    if media_manager is None:
        media_manager = _get_media_manager()
    if media_manager is not None:
        try:
            state = media_manager.get_state()
            if isinstance(state, dict):
                return state
        except Exception as exc:
            return {"available": False, "error": str(exc)}
    return {"available": False}


def _safe_hw_snapshot(hw_manager: Any, threshold: int) -> Dict[str, Any]:
    if hw_manager is None:
        try:
            hw_manager = _get_hardware_manager()
        except Exception as exc:
            return {
                "devices": {k: {"connected": False, "error": str(exc)} for k in DEVICE_META},
                "alerts": [],
            }
    try:
        snap = hw_manager.get_all_peripherals_snapshot(threshold=threshold)
        if isinstance(snap, dict):
            snap.setdefault("devices", {})
            snap.setdefault("alerts", [])
            return snap
    except Exception as exc:
        return {
            "devices": {k: {"connected": False, "error": str(exc)} for k in DEVICE_META},
            "alerts": [],
        }
    return {"devices": {}, "alerts": []}


def _summarize_device(key: str, dev: Dict[str, Any], settings: Dict[str, Any]) -> Dict[str, Any]:
    meta = DEVICE_META[key]
    threshold = int(settings.get("battery_alert_threshold", 20))
    pinned = bool(settings.get(f"pin_{key}", False))

    conn_type = str(dev.get("connection_type") or ("USB" if dev.get("connected") else "Disconnected"))
    connected = bool(dev.get("connected", conn_type != "Disconnected"))
    active = bool(dev.get("active", connected and not dev.get("standby", False)))
    battery = dev.get("battery")
    charging = bool(dev.get("charging", False))

    low_battery = isinstance(battery, (int, float)) and connected and battery <= threshold
    critical_battery = isinstance(battery, (int, float)) and connected and battery <= 10
    power_state = None
    if key == "mouse":
        power_state = str(
            dev.get("power_state")
            or ("active" if active else ("sleep" if dev.get("standby") else "off"))
        )
        if not connected:
            power_state = "off"
        visible = (power_state != "off")
    elif key == "headset":
        visible = bool(connected and active)
    elif key == "gamepad":
        visible = pinned or active or charging or low_battery
    else:  # keyboard
        visible = pinned

    dev_icon = meta["icon"]

    if not connected:
        status_text = "Off"
        detail_text = "Desconectado"
        if key == "mouse":
            dev_icon = "input-mouse-symbolic"
    elif key == "mouse":
        has_bat = isinstance(battery, (int, float))
        bat_str = f"{int(battery)}%" if has_bat else "--"
        dpi = dev.get("current_dpi") or dev.get("dpi") or "--"
        hz = dev.get("polling_rate") or "--"

        if power_state == "active":
            dev_icon = "battery-full-charging-symbolic" if charging else "input-mouse-symbolic"
            status_text = f"{int(battery)}%+" if (charging and has_bat) else (bat_str if has_bat else "On")
            detail_text = f"{dpi} DPI · {hz}Hz"
        elif power_state == "sleep":
            dev_icon = "dpi-mouse-sleep-symbolic"
            status_text = bat_str if has_bat else "Descanso"
            detail_text = f"Modo de Descanso (Sleep) · {dpi} DPI · {hz}Hz"
        else:  # off
            dev_icon = "input-mouse-symbolic"
            status_text = "Off"
            detail_text = "Desligado"
    elif key == "headset":
        vol = dev.get("volume")
        muted = bool(dev.get("muted", False))
        vol_str = "Mudo" if muted else (f"Vol {int(vol)}%" if isinstance(vol, (int, float)) else "Vol --")
        has_bat = isinstance(battery, (int, float))

        if not active:
            status_text = "Standby"
            detail_text = f"{conn_type} · Standby"
        elif has_bat:
            status_text = f"{int(battery)}%+" if charging else f"{int(battery)}%"
            detail_text = f"{conn_type} · {vol_str}"
        else:
            tag = "BT" if conn_type == "Bluetooth" else (conn_type if conn_type else "2.4GHz")
            base_status = "Mudo" if muted else tag
            status_text = f"{base_status}+" if charging else base_status
            detail_text = f"{conn_type} · {vol_str}"
    elif key == "gamepad":
        controllers = dev.get("controllers") or []
        active_ctrls = [c for c in controllers if c.get("active")]
        all_ctrls = [c for c in controllers if c.get("active") or c.get("connected")]
        first = active_ctrls[0] if active_ctrls else (all_ctrls[0] if all_ctrls else {})
        bat = first.get("battery", battery)
        is_chg = bool(first.get("charging", charging))
        if isinstance(bat, (int, float)):
            status_text = f"{int(bat)}%+" if is_chg else f"{int(bat)}%"
        elif active_ctrls or active:
            if len(active_ctrls) > 1:
                base = f"{len(active_ctrls)}x"
            else:
                first_name = str(first.get("name") or dev.get("name") or "").lower()
                if "gamesir" in first_name:
                    base = "GameSir"
                elif "easysmx" in first_name:
                    base = "EasySMX"
                else:
                    base = "Pad"
            status_text = f"{base}+" if is_chg else base
        else:
            status_text = "USB+" if is_chg else "Standby"
        detail_text = str(first.get("name") or dev.get("name") or conn_type)
    else:  # keyboard
        leds = dev.get("leds") or {}
        on_leds = [name.upper()[:4] for name in ("capslock", "numlock", "scrolllock") if leds.get(name)]
        status_text = "+".join(on_leds) if on_leds else "Safe"
        detail_text = "Hardware Safe Mode"

    level = "normal"
    if critical_battery:
        level = "critical"
    elif low_battery:
        level = "warning"

    if key == "mouse" and power_state == "sleep":
        level = "muted"

    res = {
        "key": key,
        "name": str(dev.get("name") or meta["name"]),
        "short_name": meta["short"],
        "icon": dev_icon,
        "connected": connected,
        "active": active,
        "pinned": pinned,
        "visible": visible,
        "battery": battery,
        "charging": charging,
        "connection_type": conn_type,
        "status_text": status_text,
        "detail_text": detail_text,
        "level": level,
    }
    if key == "mouse":
        res["power_state"] = power_state
    if key == "headset":
        res["volume"] = dev.get("volume")
        res["muted"] = bool(dev.get("muted", False))
    return res


def _select_pinned_quota(ag_snap: Dict[str, Any], pinned_id: str) -> Optional[Dict[str, Any]]:
    quotas = ag_snap.get("quotas") or []
    if pinned_id and pinned_id != "auto":
        for q in quotas:
            if q.get("id") == pinned_id and q.get("enabled", True):
                return q
    if ag_snap.get("lowest_quota"):
        return ag_snap["lowest_quota"]
    for q in quotas:
        if q.get("enabled"):
            return q
    return quotas[0] if quotas else None


def build_island_payload(
    hw_manager: Any = None,
    ag_collector: Optional[AntigravityCollector] = None,
    settings_path: Optional[Path] = None,
    now_ts: Optional[float] = None,
    audio_manager: Any = None,
    media_manager: Any = None,
) -> Dict[str, Any]:
    """Assemble the complete unified `--island-json` payload."""
    ts = int(now_ts if now_ts is not None else time.time())
    settings = load_settings(settings_path)
    threshold = int(settings.get("battery_alert_threshold", 20))

    hw_snap = _safe_hw_snapshot(hw_manager, threshold=threshold)
    devices: Dict[str, Any] = hw_snap.get("devices") or {}

    audio_state = _safe_audio_state(audio_manager)
    media_state = _safe_media_state(media_manager)

    collector = ag_collector or AntigravityCollector()
    ag_snap = collector.collect(now_ts=now_ts)

    capsule_peripherals = [
        _summarize_device(key, devices.get(key) or {}, settings)
        for key in ("mouse", "headset", "gamepad", "keyboard")
    ]

    pinned_quota = _select_pinned_quota(ag_snap, str(settings.get("pinned_quota", "auto")))
    if pinned_quota and pinned_quota.get("enabled"):
        ag_label = f"{pinned_quota['short_name']} {pinned_quota['remaining_pct']:.0f}%"
    elif ag_snap.get("connected"):
        ag_label = ag_snap.get("active_model", {}).get("name", "Antigravity")
    else:
        ag_label = "AG Offline"

    capsule_antigravity = {
        "connected": bool(ag_snap.get("connected")),
        "plan": (ag_snap.get("plan") or {}).get("name", "Offline"),
        "active_model": (ag_snap.get("active_model") or {}).get("name", "Desconhecido"),
        "active_model_id": (ag_snap.get("active_model") or {}).get("id", "UNKNOWN"),
        "pinned_quota": pinned_quota,
        "swarm_active": int((ag_snap.get("swarm") or {}).get("active_count", 0)),
        "label": ag_label,
    }

    combined_alerts: List[Dict[str, Any]] = []
    for alert in hw_snap.get("alerts") or []:
        if isinstance(alert, dict):
            entry = dict(alert)
            entry.setdefault("source", "hardware")
            combined_alerts.append(entry)
    for alert in ag_snap.get("alerts") or []:
        if isinstance(alert, dict):
            entry = dict(alert)
            entry.setdefault("source", "antigravity")
            combined_alerts.append(entry)

    return {
        "version": VERSION,
        "timestamp": ts,
        "theme_suggestion": str(settings.get("theme_mode", "auto")),
        "capsule": {
            "peripherals": capsule_peripherals,
            "antigravity": capsule_antigravity,
        },
        "alerts": combined_alerts,
        "peripherals": devices,
        "audio": audio_state,
        "media": media_state,
        "antigravity": ag_snap,
        "settings": settings,
    }


def format_waybar(payload: Dict[str, Any]) -> str:
    """Format unified payload as single-line JSON for Waybar custom modules."""
    capsule = payload.get("capsule") or {}
    peripherals = [p for p in (capsule.get("peripherals") or []) if p.get("visible") and p.get("connected")]
    labels = {"mouse": "Mouse", "headset": "Headset", "gamepad": "Ctrl", "keyboard": "K500"}

    parts = [f"{labels.get(p['key'], p.get('short_name', 'Dev'))} {p['status_text']}" for p in peripherals]
    ag_cap = capsule.get("antigravity") or {}
    if ag_cap.get("connected"):
        swarm_n = int(ag_cap.get("swarm_active", 0))
        swarm_tag = f" [Swarm {swarm_n}]" if swarm_n > 0 else ""
        parts.append(f"AG {ag_cap.get('label', 'OK')}{swarm_tag}")
    else:
        parts.append("AG Offline")

    text = "  ".join(parts) if parts else "DPI Hub"

    alerts = payload.get("alerts") or []
    severities = {a.get("severity") for a in alerts}
    if "critical" in severities:
        css_class = "critical"
    elif "warning" in severities:
        css_class = "warning"
    else:
        css_class = "normal"

    pcts: List[float] = []
    for p in peripherals:
        if isinstance(p.get("battery"), (int, float)):
            pcts.append(float(p["battery"]))
    pq = ag_cap.get("pinned_quota") or {}
    if pq.get("enabled") and isinstance(pq.get("remaining_pct"), (int, float)):
        pcts.append(float(pq["remaining_pct"]))
    percentage = int(round(min(pcts))) if pcts else 100

    tooltip_lines: List[str] = ["Dynamic Peripheral Island", ""]
    for p in capsule.get("peripherals") or []:
        if p.get("key") == "mouse":
            m_pstate = p.get("power_state")
            bat = p.get("battery")
            bat_str = f" — Bateria: {int(bat)}%" if isinstance(bat, (int, float)) else ""
            if m_pstate == "sleep":
                tooltip_lines.append(f"{p['name']} (Modo de Descanso (Sleep)){bat_str}")
            elif m_pstate == "off" or not p.get("connected"):
                tooltip_lines.append(f"{p['name']}: Off (Desconectado)")
            else:
                tooltip_lines.append(f"{p['name']}: {p['status_text']} ({p['detail_text']})")
        elif p.get("key") == "headset":
            conn = p.get("connection_type") or "2.4GHz"
            vol = p.get("volume")
            muted = p.get("muted", False)
            vol_disp = "Mudo" if muted else (f"Volume: {int(vol)}%" if isinstance(vol, (int, float)) else "Volume: --")
            bat = p.get("battery")
            if not p.get("connected"):
                tooltip_lines.append(f"{p['name']}: Off (Desconectado)")
            elif not p.get("active"):
                tooltip_lines.append(f"{p['name']} ({conn}) — Standby")
            elif isinstance(bat, (int, float)):
                tooltip_lines.append(f"{p['name']} ({conn}) — Bateria: {int(bat)}% | {vol_disp}")
            else:
                tooltip_lines.append(f"{p['name']} ({conn}) — {vol_disp}")
        else:
            tooltip_lines.append(f"{p['name']}: {p['status_text']} ({p['detail_text']})")
    tooltip_lines.append("")
    ag = payload.get("antigravity") or {}
    tooltip_lines.append(
        f"Antigravity ({ag_cap.get('plan', 'Offline')}): {ag_cap.get('active_model', '')}"
    )
    tooltip_lines.append(f"Projeto: {ag.get('active_project', 'Nenhum')}")
    for q in ag.get("quotas") or []:
        if q.get("enabled"):
            tooltip_lines.append(f"  {q['short_name']}: {q['remaining_pct']:.0f}% (reset {q['reset_countdown']})")

    return json.dumps(
        {
            "text": text,
            "tooltip": "\n".join(tooltip_lines),
            "class": css_class,
            "percentage": max(0, min(100, percentage)),
        },
        ensure_ascii=False,
    )


def format_pretty(payload: Dict[str, Any]) -> str:
    """Format a colorful ANSI terminal dashboard."""
    reset = "\033[0m"
    bold = "\033[1m"
    cyan = "\033[36m"
    green = "\033[32m"
    yellow = "\033[33m"
    red = "\033[31m"
    dim = "\033[2m"

    def bar(pct: float, width: int = 16, pace: Optional[float] = None) -> str:
        filled = max(0, min(width, int(round((pct / 100.0) * width))))
        pace_idx = (
            max(0, min(width - 1, int(round((pace / 100.0) * width))))
            if pace is not None
            else -1
        )
        chars: List[str] = []
        for idx in range(width):
            if idx == pace_idx:
                chars.append("|")
            elif idx < filled:
                chars.append("█")
            else:
                chars.append("░")
        color = red if pct <= 15 else (yellow if pct <= 35 else green)
        return f"{color}{''.join(chars)}{reset}"

    lines: List[str] = [
        f"{bold}{cyan}══ Dynamic Peripheral Island v{payload.get('version', VERSION)} ══{reset}",
        "",
        f"{bold}Periféricos{reset}",
    ]

    for p in (payload.get("capsule") or {}).get("peripherals") or []:
        dot = f"{green}●{reset}" if p["connected"] else f"{dim}○{reset}"
        pin = f" {cyan}[PIN]{reset}" if p.get("pinned") else ""
        lines.append(
            f"  {dot} {bold}{p['name']:<20}{reset} {p['status_text']:<10} {dim}{p['detail_text']}{reset}{pin}"
        )

    audio = payload.get("audio") or {}
    master = audio.get("master") or {}
    mic = audio.get("mic") or {}
    apps = audio.get("apps") or []
    if master or mic or apps:
        lines.extend(["", f"{bold}Áudio & Mixer{reset}"])
        if master:
            m_vol = master.get("volume", "--")
            m_muted = f" {red}[MUDO]{reset}" if master.get("muted") else ""
            m_desc = master.get("description") or master.get("name") or "Master"
            lines.append(f"  Master: {m_vol}%{m_muted} {dim}[{m_desc}]{reset}")
        if mic:
            mic_vol = mic.get("volume", "--")
            mic_muted = f" {red}[MUDO]{reset}" if mic.get("muted") else ""
            mic_desc = mic.get("description") or mic.get("name") or "Mic"
            lines.append(f"  Mic:    {mic_vol}%{mic_muted} {dim}[{mic_desc}]{reset}")
        if apps:
            lines.append(f"  {dim}Aplicativos ({len(apps)}):{reset}")
            for app in apps:
                app_vol = app.get("volume", "--")
                app_m = f" {red}[MUDO]{reset}" if app.get("muted") else ""
                lines.append(f"    - [{app.get('id')}] {app.get('app_name', 'App')}: {app_vol}%{app_m}")

    media = payload.get("media") or {}
    if media.get("available"):
        p_name = media.get("player_name", "Mídia")
        status = media.get("status", "")
        title = media.get("title", "")
        artist = media.get("artist", "")
        pos_s = int(media.get("position_sec") or 0)
        len_s = int(media.get("length_sec") or 0)
        pos_str = f"{pos_s // 60}:{pos_s % 60:02d}"
        len_str = f"{len_s // 60}:{len_s % 60:02d}" if len_s > 0 else "--:--"
        lines.extend([
            "",
            f"{bold}Mídia ({p_name}){reset} [{status}]",
            f"  {bold}{title}{reset}" + (f" · {artist}" if artist else ""),
            f"  {dim}{pos_str} / {len_str}{reset}",
        ])

    ag = payload.get("antigravity") or {}
    plan = ag.get("plan") or {}
    model = ag.get("active_model") or {}
    lines.extend(
        [
            "",
            f"{bold}Antigravity View Usage{reset} ({plan.get('name', 'Offline')} · {cyan}{model.get('name', '?')}{reset})",
            f"  Projeto ativo: {bold}{ag.get('active_project', 'Nenhum')}{reset}",
        ]
    )

    for q in ag.get("quotas") or []:
        if not q.get("enabled"):
            lines.append(f"  {dim}{q['name']:<22} Indisponível{reset}")
            continue
        eta = f"  {yellow}{q['depletion_eta']}{reset}" if q.get("depletion_eta") else ""
        pace_pct = q.get("pace_pct")
        expected_remaining = (100.0 - float(pace_pct)) if pace_pct is not None else None
        lines.append(
            f"  {q['name']:<22} {bar(q['remaining_pct'], pace=expected_remaining)} "
            f"{q['remaining_pct']:5.1f}%  {dim}reset {q['reset_countdown']}{reset}{eta}"
        )

    ctx = ag.get("session_context") or {}
    swarm = ag.get("swarm") or {}
    lines.extend(
        [
            "",
            f"{bold}Sessão & Swarm{reset}",
            f"  Tokens sessão: {ctx.get('total_tokens', 0):,} "
            f"{dim}(in {ctx.get('input_tokens', 0):,} · cache {ctx.get('cache_read_tokens', 0):,} · out {ctx.get('output_tokens', 0):,}){reset}",
            f"  Swarm ativo: {swarm.get('active_count', 0)}/{swarm.get('total_count', 0)}",
        ]
    )
    for agent in swarm.get("agents") or []:
        st_color = green if agent["status"] == "WORKING" else dim
        lines.append(f"    - {agent['role']:<14} {st_color}{agent['status']:<7}{reset} ({agent['steps']} steps)")

    hist = ag.get("daily_histogram_7d") or []
    max_tok = max((d.get("tokens", 0) for d in hist), default=0) or 1
    lines.extend(["", f"{bold}Histograma 7 Dias{reset}"])
    for d in hist:
        tok = int(d.get("tokens", 0))
        w = int(round((tok / max_tok) * 20))
        lines.append(f"  {d['label']:<5} {cyan}{'▇' * w}{reset} {tok:,}")

    monthly = ag.get("monthly") or {}
    lines.append(
        f"\n{bold}Mensal ({monthly.get('month', '')}){reset}: {monthly.get('total_tokens', 0):,} tokens"
    )

    alerts = payload.get("alerts") or []
    if alerts:
        lines.extend(["", f"{bold}{yellow}Alertas{reset}"])
        for a in alerts:
            lines.append(f"  ! [{a.get('severity', 'info').upper()}] {a.get('title')}: {a.get('message')}")

    return "\n".join(lines)


def _handle_settings_flag(args: argparse.Namespace, settings_path: Optional[Path]) -> Optional[Tuple[bool, str]]:
    settings = load_settings(settings_path)

    if args.pin_device is not None:
        raw = args.pin_device.strip()
        if ":" in raw or "=" in raw:
            sep = ":" if ":" in raw else "="
            dev, val = raw.split(sep, 1)
            dev = dev.strip().lower()
            try:
                state = _parse_bool(val)
            except ValueError as exc:
                return False, str(exc)
        else:
            dev = raw.lower()
            state = not bool(settings.get(f"pin_{dev}", False))

        key = f"pin_{dev}"
        if key not in DEFAULT_SETTINGS:
            return False, f"Periférico desconhecido para pin: {dev}"
        settings[key] = state
        save_settings(settings, settings_path)
        return True, f"Pin de {dev} definido para {'ativo' if state else 'inativo'}"

    if args.pin_quota is not None:
        qid = args.pin_quota.strip().lower()
        if not qid:
            return False, "ID de cota inválido"
        settings["pinned_quota"] = qid
        save_settings(settings, settings_path)
        return True, f"Cota fixada alterada para '{qid}'"

    if args.set_theme is not None:
        mode = args.set_theme.strip().lower()
        if mode not in {"auto", "dark", "light"}:
            return False, f"Tema inválido: {mode}. Use auto, dark ou light"
        settings["theme_mode"] = mode
        save_settings(settings, settings_path)
        return True, f"Tema definido para '{mode}'"

    if args.set_alert_threshold is not None:
        pct = int(args.set_alert_threshold)
        if not 5 <= pct <= 50:
            return False, "Limiar de bateria deve ficar entre 5% e 50%"
        settings["battery_alert_threshold"] = pct
        save_settings(settings, settings_path)
        return True, f"Limiar de alerta de bateria definido para {pct}%"

    if args.set_poll_interval is not None:
        sec = int(args.set_poll_interval)
        if not 1 <= sec <= 60:
            return False, "Intervalo de polling deve ficar entre 1s e 60s"
        settings["poll_interval"] = sec
        save_settings(settings, settings_path)
        return True, f"Intervalo de polling definido para {sec}s"

    return None


def _dispatch_hw_flag(args: argparse.Namespace, hw_manager: Any) -> Optional[Tuple[bool, str]]:
    action_map: List[Tuple[str, Any, Dict[str, Any]]] = []
    if args.set_dpi is not None:
        action_map.append(("set_dpi", True, {"dpi": args.set_dpi}))
    elif args.set_polling is not None:
        action_map.append(("set_polling_rate", True, {"hz": args.set_polling}))
    elif args.set_mouse_led is not None:
        action_map.append(("set_led_color", True, {"hex_color": args.set_mouse_led}))
    elif args.set_mouse_sleep is not None:
        action_map.append(("set_sleep_timeout", True, {"seconds": args.set_mouse_sleep}))
    elif args.set_volume is not None:
        action_map.append(("set_volume", True, {"pct": args.set_volume}))
    elif args.toggle_mute:
        action_map.append(("toggle_mute", True, {}))
    elif args.fix_alsa:
        action_map.append(("fix_alsa_volume", True, {}))
    elif args.set_audio_profile is not None:
        action_map.append(("set_profile", True, {"profile": args.set_audio_profile}))
    elif args.set_sidetone is not None:
        try:
            enabled = _parse_bool(args.set_sidetone)
        except ValueError as exc:
            return False, str(exc)
        action_map.append(("set_sidetone", True, {"enabled": enabled}))
    elif args.set_eq is not None:
        action_map.append(("set_eq_preset", True, {"preset": args.set_eq}))
    elif args.test_rumble:
        action_map.append(("test_rumble", True, {"controller_id": args.controller_id}))
    elif args.set_deadzone is not None:
        action_map.append(("set_deadzone", True, {"controller_id": args.controller_id, "pct": args.set_deadzone}))
    elif args.set_gamepad_layout is not None:
        action_map.append(("set_layout", True, {"controller_id": args.controller_id, "layout": args.set_gamepad_layout}))

    if not action_map:
        return None

    action, _, kwargs = action_map[0]
    try:
        mgr = hw_manager if hw_manager is not None else _get_hardware_manager()
        ok, msg = mgr.dispatch_action(action, **kwargs)
        return bool(ok), str(msg)
    except Exception as exc:
        return False, f"Erro ao executar {action}: {exc}"


def _dispatch_audio_flag(args: argparse.Namespace, audio_manager: Any = None) -> Optional[Tuple[bool, str]]:
    if args.set_master_volume is not None:
        mgr = audio_manager if audio_manager is not None else _get_audio_manager()
        if mgr is None:
            return False, "Gerenciador de áudio indisponível"
        try:
            return mgr.set_master_volume(args.set_master_volume)
        except Exception as exc:
            return False, f"Erro ao definir volume master: {exc}"
    elif args.toggle_master_mute:
        mgr = audio_manager if audio_manager is not None else _get_audio_manager()
        if mgr is None:
            return False, "Gerenciador de áudio indisponível"
        try:
            return mgr.toggle_master_mute()
        except Exception as exc:
            return False, f"Erro ao alternar mudo master: {exc}"
    elif args.set_default_sink is not None:
        mgr = audio_manager if audio_manager is not None else _get_audio_manager()
        if mgr is None:
            return False, "Gerenciador de áudio indisponível"
        try:
            return mgr.set_default_sink(args.set_default_sink)
        except Exception as exc:
            return False, f"Erro ao definir saída padrão: {exc}"
    elif args.set_mic_volume is not None:
        mgr = audio_manager if audio_manager is not None else _get_audio_manager()
        if mgr is None:
            return False, "Gerenciador de áudio indisponível"
        try:
            return mgr.set_mic_volume(args.set_mic_volume)
        except Exception as exc:
            return False, f"Erro ao definir volume do microfone: {exc}"
    elif args.toggle_mic_mute:
        mgr = audio_manager if audio_manager is not None else _get_audio_manager()
        if mgr is None:
            return False, "Gerenciador de áudio indisponível"
        try:
            return mgr.toggle_mic_mute()
        except Exception as exc:
            return False, f"Erro ao alternar mudo do microfone: {exc}"
    elif args.set_default_source is not None:
        mgr = audio_manager if audio_manager is not None else _get_audio_manager()
        if mgr is None:
            return False, "Gerenciador de áudio indisponível"
        try:
            return mgr.set_default_source(args.set_default_source)
        except Exception as exc:
            return False, f"Erro ao definir microfone padrão: {exc}"
    elif args.set_app_volume is not None:
        mgr = audio_manager if audio_manager is not None else _get_audio_manager()
        if mgr is None:
            return False, "Gerenciador de áudio indisponível"
        try:
            stream_id, pct = args.set_app_volume
            return mgr.set_app_volume(int(stream_id), int(pct))
        except Exception as exc:
            return False, f"Erro ao definir volume do aplicativo: {exc}"
    elif args.toggle_app_mute is not None:
        mgr = audio_manager if audio_manager is not None else _get_audio_manager()
        if mgr is None:
            return False, "Gerenciador de áudio indisponível"
        try:
            return mgr.toggle_app_mute(int(args.toggle_app_mute))
        except Exception as exc:
            return False, f"Erro ao alternar mudo do aplicativo: {exc}"

    return None


def _dispatch_media_flag(args: argparse.Namespace, media_manager: Any = None) -> Optional[Tuple[bool, str]]:
    if args.media_play_pause:
        mgr = media_manager if media_manager is not None else _get_media_manager()
        if mgr is None:
            return False, "Gerenciador de mídia indisponível"
        try:
            return mgr.play_pause(bus_name=args.media_player)
        except Exception as exc:
            return False, f"Erro ao alternar reprodução/pausa de mídia: {exc}"
    elif args.media_next:
        mgr = media_manager if media_manager is not None else _get_media_manager()
        if mgr is None:
            return False, "Gerenciador de mídia indisponível"
        try:
            return mgr.next_track(bus_name=args.media_player)
        except Exception as exc:
            return False, f"Erro ao avançar faixa de mídia: {exc}"
    elif args.media_prev:
        mgr = media_manager if media_manager is not None else _get_media_manager()
        if mgr is None:
            return False, "Gerenciador de mídia indisponível"
        try:
            return mgr.previous_track(bus_name=args.media_player)
        except Exception as exc:
            return False, f"Erro ao voltar faixa de mídia: {exc}"

    return None


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser for dpi-hub."""
    parser = argparse.ArgumentParser(
        prog="dpi-hub",
        description="Dynamic Peripheral Island — Hub de Telemetria de Periféricos & Antigravity",
    )
    parser.add_argument("--island-json", action="store_true", help="Saída JSON unificada para o Applet Cinnamon")
    parser.add_argument("--waybar", action="store_true", help="Saída JSON linha única para Waybar")
    parser.add_argument("--pretty", action="store_true", help="Dashboard colorido no terminal")

    # Hardware controls
    parser.add_argument("--set-dpi", type=int, metavar="DPI", help="Define DPI do mouse (400..26000)")
    parser.add_argument("--set-polling", type=int, metavar="HZ", help="Define polling rate do mouse (125/250/500/1000)")
    parser.add_argument("--set-mouse-led", type=str, metavar="HEX", help="Define cor LED lateral (#RRGGBB)")
    parser.add_argument("--set-mouse-sleep", type=int, metavar="SEC", help="Define timeout de sleep do mouse (s)")
    parser.add_argument("--set-volume", type=int, metavar="PCT", help="Define volume do headset (0..100)")
    parser.add_argument("--toggle-mute", action="store_true", help="Alterna mudo do headset")
    parser.add_argument("--fix-alsa", action="store_true", help="Corrige bug ALSA numid=9 do Fuxi H3")
    parser.add_argument("--set-audio-profile", type=str, metavar="PROFILE", help="Define perfil de áudio Pulse/PipeWire")
    parser.add_argument("--set-sidetone", type=str, metavar="ON|OFF", help="Liga/desliga retorno de microfone")
    parser.add_argument("--set-eq", type=str, metavar="PRESET", help="Define preset de EQ (gaming/music/voice/flat)")
    parser.add_argument("--test-rumble", action="store_true", help="Testa vibração do controle")
    parser.add_argument("--set-deadzone", type=int, metavar="PCT", help="Define deadzone do controle (0..25)")
    parser.add_argument("--controller-id", type=str, default=None, help="ID alvo do controle")
    parser.add_argument("--set-gamepad-layout", type=str, metavar="LAYOUT", help="Define layout (xbox/nintendo)")

    # Audio & Mixer controls (PipeWire / pactl)
    parser.add_argument("--set-master-volume", type=int, metavar="PCT", help="Define volume master (0..150)")
    parser.add_argument("--toggle-master-mute", action="store_true", help="Alterna mudo da saída master")
    parser.add_argument("--set-default-sink", type=str, metavar="NAME", help="Define saída de áudio padrão")
    parser.add_argument("--set-mic-volume", type=int, metavar="PCT", help="Define volume do microfone (0..150)")
    parser.add_argument("--toggle-mic-mute", action="store_true", help="Alterna mudo do microfone")
    parser.add_argument("--set-default-source", type=str, metavar="NAME", help="Define microfone padrão")
    parser.add_argument("--set-app-volume", nargs=2, type=int, metavar=("ID", "PCT"), help="Define volume do app por stream ID (ID PCT)")
    parser.add_argument("--toggle-app-mute", type=int, metavar="ID", help="Alterna mudo do app por stream ID")

    # Media player controls (Spotify / MPRIS2)
    parser.add_argument("--media-play-pause", action="store_true", help="Alterna reprodução/pausa no player MPRIS2")
    parser.add_argument("--media-next", action="store_true", help="Avança faixa no player MPRIS2")
    parser.add_argument("--media-prev", action="store_true", help="Volta faixa no player MPRIS2")
    parser.add_argument("--media-player", type=str, default=None, metavar="BUS", help="Define bus do player MPRIS2 (ex: org.mpris.MediaPlayer2.spotify)")

    # Settings controls
    parser.add_argument("--pin-device", type=str, metavar="DEV[:BOOL]", help="Fixa/desafixa periférico na barra")
    parser.add_argument("--pin-quota", type=str, metavar="GROUP", help="Fixa grupo de cota Antigravity na barra")
    parser.add_argument("--set-theme", type=str, metavar="MODE", help="Define tema (auto/dark/light)")
    parser.add_argument("--set-alert-threshold", type=int, metavar="PCT", help="Define limiar de bateria baixa (5..50)")
    parser.add_argument("--set-poll-interval", type=int, metavar="SEC", help="Define intervalo de coleta (1..60)")

    return parser


def main(
    argv: Optional[List[str]] = None,
    hw_manager: Any = None,
    ag_collector: Optional[AntigravityCollector] = None,
    settings_path: Optional[Path] = None,
    audio_manager: Any = None,
    media_manager: Any = None,
) -> int:
    """CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)

    settings_res = _handle_settings_flag(args, settings_path)
    if settings_res is not None:
        ok, msg = settings_res
        print(json.dumps({"ok": ok, "message": msg}, ensure_ascii=False))
        return 0 if ok else 1

    hw_res = _dispatch_hw_flag(args, hw_manager)
    if hw_res is not None:
        ok, msg = hw_res
        print(json.dumps({"ok": ok, "message": msg}, ensure_ascii=False))
        return 0 if ok else 1

    audio_res = _dispatch_audio_flag(args, audio_manager)
    if audio_res is not None:
        ok, msg = audio_res
        print(json.dumps({"ok": ok, "message": msg}, ensure_ascii=False))
        return 0 if ok else 1

    media_res = _dispatch_media_flag(args, media_manager)
    if media_res is not None:
        ok, msg = media_res
        print(json.dumps({"ok": ok, "message": msg}, ensure_ascii=False))
        return 0 if ok else 1

    payload = build_island_payload(
        hw_manager=hw_manager,
        ag_collector=ag_collector,
        settings_path=settings_path,
        audio_manager=audio_manager,
        media_manager=media_manager,
    )

    if args.waybar:
        print(format_waybar(payload))
    elif args.pretty:
        print(format_pretty(payload))
    else:
        print(json.dumps(payload, indent=2 if not args.island_json else None, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

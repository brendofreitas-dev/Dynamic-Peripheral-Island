"""Dynamic Peripheral Island — Audio Mixer & Media Player Management.

Provides:
  - AudioMixerManager: PipeWire/PulseAudio master, microphone, device switching,
    and per-app volume mixer via `LC_ALL=C pactl`. Inspired by Volum (esdrasstm/Volum).
  - MediaPlayerManager: MPRIS2 player discovery, metadata inspection (Spotify, Brave, VLC),
    and transport controls via `gdbus`.

100% Python 3 standard library, zero external dependencies.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
from typing import Any, Callable, Dict, List, Optional, Tuple

CmdRunner = Callable[[List[str]], Tuple[int, str, str]]


def _c_env() -> Dict[str, str]:
    """Return a copy of the environment forcing C locale for deterministic CLI parsing."""
    env = dict(os.environ)
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    return env


def default_cmd_runner(cmd: List[str], timeout: float = 2.5) -> Tuple[int, str, str]:
    """Execute an external command safely without raising on missing binary or timeout."""
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


# ---------------------------------------------------------------------------
# GVariant Parser (Pure Python stdlib, safe ast.literal_eval)
# ---------------------------------------------------------------------------

def parse_gvariant(text: str) -> Any:
    """Parse GVariant text representation from gdbus into native Python objects.

    Handles variant wrappers (<...>), typed integers (<uint64 N>), booleans
    (<true>/<false>), and preserves single- and double-quoted strings safely.
    """
    if not text or not text.strip():
        return ()

    chars: List[str] = []
    in_quote = False
    quote_char = ""
    escape = False
    i = 0
    n = len(text)
    type_names = frozenset(
        {
            "uint64",
            "int64",
            "uint32",
            "int32",
            "uint16",
            "int16",
            "byte",
            "double",
            "int",
            "uint",
            "boolean",
            "string",
        }
    )

    while i < n:
        c = text[i]
        if in_quote:
            chars.append(c)
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == quote_char:
                in_quote = False
                quote_char = ""
            i += 1
        else:
            if c in ("'", '"'):
                in_quote = True
                quote_char = c
                chars.append(c)
                i += 1
            elif c == "<":
                # Check for type prefix inside variant: <uint64 1234>
                j = i + 1
                while j < n and text[j].isspace():
                    j += 1
                word_start = j
                while j < n and (text[j].isalnum() or text[j] == "_"):
                    j += 1
                word = text[word_start:j]
                if word in type_names:
                    i = j
                else:
                    i += 1
            elif c == ">":
                i += 1
            else:
                if text[i : i + 4] == "true" and not (i + 4 < n and text[i + 4].isalnum()):
                    chars.append("True")
                    i += 4
                elif text[i : i + 5] == "false" and not (i + 5 < n and text[i + 5].isalnum()):
                    chars.append("False")
                    i += 5
                else:
                    chars.append(c)
                    i += 1

    cleaned = "".join(chars).strip()
    try:
        return ast.literal_eval(cleaned)
    except Exception:
        return ()


# ---------------------------------------------------------------------------
# 1. AudioMixerManager (PipeWire / PulseAudio via pactl)
# ---------------------------------------------------------------------------

class AudioMixerManager:
    """Manages audio outputs, microphone inputs, and per-app audio streams via pactl."""

    def __init__(self, cmd_runner: Optional[CmdRunner] = None) -> None:
        self.cmd_runner: CmdRunner = cmd_runner or default_cmd_runner

    @staticmethod
    def _parse_volume(vol_str: str) -> int:
        """Extract average percentage from pactl Volume: line."""
        if not vol_str:
            return 100
        matches = re.findall(r"(\d+)%", vol_str)
        if not matches:
            return 100
        pcts = [int(p) for p in matches]
        return int(sum(pcts) / len(pcts))

    @staticmethod
    def _derive_short_name(block: Dict[str, Any], default_val: str) -> str:
        """Derive a clean, concise device name for compact UI chips."""
        props = block.get("properties", {})
        candidate = (
            props.get("node.nick")
            or props.get("device.nick")
            or props.get("alsa.card_name")
            or props.get("device.description")
            or block.get("description")
            or default_val
        )
        # Strip generic suffixes
        candidate = re.sub(r"\s+Est[eé]reo digital.*", "", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\s+Est[eé]reo anal[oó]gico.*", "", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\s+Mono.*", "", candidate, flags=re.IGNORECASE)
        return candidate.strip() or default_val

    def _parse_pactl_blocks(self, raw_text: str, header_prefix: str) -> List[Dict[str, Any]]:
        """Parse structured blocks from `pactl list sinks/sources/sink-inputs`."""
        blocks: List[Dict[str, Any]] = []
        current: Optional[Dict[str, Any]] = None

        for line in raw_text.splitlines():
            if line.startswith(header_prefix):
                if current:
                    blocks.append(current)
                match = re.search(r"#(\d+)", line)
                block_id = int(match.group(1)) if match else 0
                current = {"id": block_id, "properties": {}}
                continue
            if current is None:
                continue

            trimmed = line.strip()
            if not trimmed:
                continue

            # Top-level field lines have 1 tab indentation and a colon
            if line.startswith("\t") and not line.startswith("\t\t") and ":" in trimmed:
                key, val = trimmed.split(":", 1)
                k_lower = key.strip().lower()
                if k_lower != "properties":
                    current[k_lower] = val.strip()
            elif line.startswith("\t\t") and "=" in trimmed:
                prop_key, prop_val = trimmed.split("=", 1)
                clean_val = prop_val.strip().strip('"')
                current["properties"][prop_key.strip()] = clean_val

        if current:
            blocks.append(current)
        return blocks

    def get_state(self) -> Dict[str, Any]:
        """Collect unified audio mixer state: master output, available outputs, mic, inputs, apps."""
        # 1. Get default sink & source names
        rc_ds, out_ds, _ = self.cmd_runner(["pactl", "get-default-sink"])
        default_sink_name = out_ds.strip() if rc_ds == 0 else ""

        rc_src, out_src, _ = self.cmd_runner(["pactl", "get-default-source"])
        default_source_name = out_src.strip() if rc_src == 0 else ""

        # 2. Parse outputs (sinks)
        rc_sinks, out_sinks, _ = self.cmd_runner(["pactl", "list", "sinks"])
        raw_sinks = self._parse_pactl_blocks(out_sinks, "Sink #") if rc_sinks == 0 else []

        outputs: List[Dict[str, Any]] = []
        master_dict: Dict[str, Any] = {
            "name": default_sink_name,
            "description": "Saída Principal",
            "short_name": "Master",
            "volume": 100,
            "muted": False,
            "state": "IDLE",
        }

        for s in raw_sinks:
            name = s.get("name", "")
            desc = s.get("description", name)
            short_name = self._derive_short_name(s, desc)
            vol = self._parse_volume(s.get("volume", ""))
            muted = s.get("mute", "no").lower() == "yes"
            is_def = bool(name and name == default_sink_name)

            out_item = {
                "name": name,
                "description": desc,
                "short_name": short_name,
                "volume": vol,
                "muted": muted,
                "is_default": is_def,
            }
            outputs.append(out_item)

            if is_def or (not default_sink_name and not master_dict.get("name")):
                master_dict = {
                    "name": name,
                    "description": desc,
                    "short_name": short_name,
                    "volume": vol,
                    "muted": muted,
                    "state": s.get("state", "IDLE"),
                }

        # 3. Parse inputs (sources, excluding monitors)
        rc_sources, out_sources, _ = self.cmd_runner(["pactl", "list", "sources"])
        raw_sources = self._parse_pactl_blocks(out_sources, "Source #") if rc_sources == 0 else []

        inputs: List[Dict[str, Any]] = []
        mic_dict: Dict[str, Any] = {
            "name": default_source_name,
            "description": "Microfone Padrão",
            "short_name": "Mic",
            "volume": 100,
            "muted": False,
        }

        for s in raw_sources:
            name = s.get("name", "")
            # Filter out monitor sources
            if name.endswith(".monitor") or s.get("properties", {}).get("device.class") == "monitor":
                continue
            desc = s.get("description", name)
            short_name = self._derive_short_name(s, desc)
            vol = self._parse_volume(s.get("volume", ""))
            muted = s.get("mute", "no").lower() == "yes"
            is_def = bool(name and name == default_source_name)

            in_item = {
                "name": name,
                "description": desc,
                "short_name": short_name,
                "volume": vol,
                "muted": muted,
                "is_default": is_def,
            }
            inputs.append(in_item)

            if is_def or (not default_source_name and not mic_dict.get("name")):
                mic_dict = {
                    "name": name,
                    "description": desc,
                    "short_name": short_name,
                    "volume": vol,
                    "muted": muted,
                }

        # 4. Parse per-app streams (sink inputs)
        rc_apps, out_apps, _ = self.cmd_runner(["pactl", "list", "sink-inputs"])
        raw_apps = self._parse_pactl_blocks(out_apps, "Sink Input #") if rc_apps == 0 else []

        apps: List[Dict[str, Any]] = []
        for app in raw_apps:
            props = app.get("properties", {})
            app_id = int(app.get("id", 0))
            app_name = (
                props.get("application.name")
                or props.get("application.process.binary")
                or props.get("media.name")
                or f"App #{app_id}"
            )
            media_name = props.get("media.name", "")
            icon_name = (
                props.get("application.icon_name")
                or props.get("application.process.binary")
                or "audio-x-generic"
            )
            vol = self._parse_volume(app.get("volume", ""))
            muted = app.get("mute", "no").lower() == "yes"
            corked = app.get("corked", "no").lower() == "yes"

            apps.append(
                {
                    "id": app_id,
                    "app_name": app_name,
                    "media_name": media_name,
                    "icon_name": icon_name,
                    "volume": vol,
                    "muted": muted,
                    "corked": corked,
                }
            )

        return {
            "master": master_dict,
            "outputs": outputs,
            "mic": mic_dict,
            "inputs": inputs,
            "apps": apps,
        }

    # -----------------------------------------------------------------------
    # Output & Master Controls
    # -----------------------------------------------------------------------

    def set_master_volume(self, pct: int) -> Tuple[bool, str]:
        """Set master output volume (clamped between 0 and 150%)."""
        try:
            val = max(0, min(150, int(pct)))
        except (ValueError, TypeError):
            return False, f"Volume inválido: {pct}"
        rc, _, err = self.cmd_runner(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{val}%"])
        if rc == 0:
            return True, f"Volume master definido para {val}%."
        return False, f"Falha ao ajustar volume master: {err.strip()}"

    def toggle_master_mute(self) -> Tuple[bool, str]:
        """Toggle master output mute."""
        rc, _, err = self.cmd_runner(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"])
        if rc == 0:
            return True, "Mute do master alternado com sucesso."
        return False, f"Falha ao alternar mute master: {err.strip()}"

    def set_default_sink(self, sink_name: str) -> Tuple[bool, str]:
        """Change the active audio output sink device in 1 click."""
        name = (sink_name or "").strip()
        if not name:
            return False, "Nome do dispositivo de saída não especificado."
        rc, _, err = self.cmd_runner(["pactl", "set-default-sink", name])
        if rc == 0:
            return True, f"Dispositivo de saída alterado para '{name}'."
        return False, f"Falha ao alterar dispositivo de saída: {err.strip()}"

    # -----------------------------------------------------------------------
    # Microphone / Input Controls
    # -----------------------------------------------------------------------

    def set_mic_volume(self, pct: int) -> Tuple[bool, str]:
        """Set microphone input volume (clamped between 0 and 150%)."""
        try:
            val = max(0, min(150, int(pct)))
        except (ValueError, TypeError):
            return False, f"Volume de microfone inválido: {pct}"
        rc, _, err = self.cmd_runner(["pactl", "set-source-volume", "@DEFAULT_SOURCE@", f"{val}%"])
        if rc == 0:
            return True, f"Volume do microfone definido para {val}%."
        return False, f"Falha ao ajustar volume do microfone: {err.strip()}"

    def toggle_mic_mute(self) -> Tuple[bool, str]:
        """Toggle microphone mute."""
        rc, _, err = self.cmd_runner(["pactl", "set-source-mute", "@DEFAULT_SOURCE@", "toggle"])
        if rc == 0:
            return True, "Mute do microfone alternado com sucesso."
        return False, f"Falha ao alternar mute do microfone: {err.strip()}"

    def set_default_source(self, source_name: str) -> Tuple[bool, str]:
        """Change the active microphone input source device in 1 click."""
        name = (source_name or "").strip()
        if not name:
            return False, "Nome da fonte de microfone não especificado."
        rc, _, err = self.cmd_runner(["pactl", "set-default-source", name])
        if rc == 0:
            return True, f"Microfone padrão alterado para '{name}'."
        return False, f"Falha ao alterar microfone padrão: {err.strip()}"

    # -----------------------------------------------------------------------
    # Per-App Stream Controls
    # -----------------------------------------------------------------------

    def set_app_volume(self, stream_id: int, pct: int) -> Tuple[bool, str]:
        """Set volume of a specific application audio stream."""
        try:
            sid = int(stream_id)
            val = max(0, min(150, int(pct)))
        except (ValueError, TypeError):
            return False, f"Parâmetros inválidos: stream_id={stream_id}, pct={pct}"
        rc, _, err = self.cmd_runner(["pactl", "set-sink-input-volume", str(sid), f"{val}%"])
        if rc == 0:
            return True, f"Volume do stream #{sid} ajustado para {val}%."
        return False, f"Falha ao ajustar volume do stream #{sid}: {err.strip()}"

    def toggle_app_mute(self, stream_id: int) -> Tuple[bool, str]:
        """Toggle mute of a specific application audio stream."""
        try:
            sid = int(stream_id)
        except (ValueError, TypeError):
            return False, f"stream_id inválido: {stream_id}"
        rc, _, err = self.cmd_runner(["pactl", "set-sink-input-mute", str(sid), "toggle"])
        if rc == 0:
            return True, f"Mute do stream #{sid} alternado com sucesso."
        return False, f"Falha ao alternar mute do stream #{sid}: {err.strip()}"


# ---------------------------------------------------------------------------
# 2. MediaPlayerManager (Spotify + MPRIS2 via gdbus)
# ---------------------------------------------------------------------------

class MediaPlayerManager:
    """Discovers and controls media players (Spotify, Brave, VLC, etc.) via MPRIS2 DBus."""

    PRIMARY_PLAYER = "org.mpris.MediaPlayer2.spotify"

    def __init__(self, cmd_runner: Optional[CmdRunner] = None) -> None:
        self.cmd_runner: CmdRunner = cmd_runner or default_cmd_runner

    def list_players(self) -> List[str]:
        """Enumerate active MPRIS2 player DBus bus names on the session bus."""
        rc, out, _ = self.cmd_runner(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                "org.freedesktop.DBus",
                "--object-path",
                "/org/freedesktop/DBus",
                "--method",
                "org.freedesktop.DBus.ListNames",
            ]
        )
        if rc != 0 or not out:
            return []
        matches = re.findall(r"['\"](org\.mpris\.MediaPlayer2\.[^'\"]+)['\"]", out)
        return list(dict.fromkeys(matches))

    def _query_player_raw(self, bus_name: str) -> Dict[str, Any]:
        """Query GetAll org.mpris.MediaPlayer2.Player for a specific bus name."""
        rc, out, _ = self.cmd_runner(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                bus_name,
                "--object-path",
                "/org/mpris/MediaPlayer2",
                "--method",
                "org.freedesktop.DBus.Properties.GetAll",
                "org.mpris.MediaPlayer2.Player",
            ]
        )
        if rc != 0 or not out:
            return {}
        parsed = parse_gvariant(out)
        return parsed[0] if isinstance(parsed, tuple) and parsed else (parsed if isinstance(parsed, dict) else {})

    def get_active_bus_name(self) -> Optional[str]:
        """Find the most relevant MPRIS2 player bus name (prioritizing Spotify and Playing state)."""
        players = self.list_players()
        if not players:
            return None

        # If Spotify is running, check if active or available
        if self.PRIMARY_PLAYER in players:
            return self.PRIMARY_PLAYER

        # Otherwise prioritize playing player, then paused, then first available
        best_bus: Optional[str] = None
        for bus in players:
            props = self._query_player_raw(bus)
            status = props.get("PlaybackStatus", "")
            if status == "Playing":
                return bus
            if status == "Paused" and best_bus is None:
                best_bus = bus

        return best_bus or players[0]

    def get_state(self, bus_name: Optional[str] = None) -> Dict[str, Any]:
        """Collect rich media playback telemetry from active MPRIS2 player."""
        target_bus = (bus_name or "").strip() or self.get_active_bus_name()

        default_state: Dict[str, Any] = {
            "available": False,
            "bus_name": "",
            "player_name": "",
            "status": "Stopped",
            "title": "",
            "artist": "",
            "album": "",
            "art_url": "",
            "position_sec": 0,
            "length_sec": 0,
            "progress_pct": 0.0,
            "can_go_next": False,
            "can_go_previous": False,
            "can_play": False,
            "can_pause": False,
        }

        if not target_bus:
            return default_state

        d = self._query_player_raw(target_bus)
        if not d:
            return default_state

        meta = d.get("Metadata", {}) if isinstance(d.get("Metadata"), dict) else {}

        # Player human-readable name
        parts = target_bus.replace("org.mpris.MediaPlayer2.", "").split(".")
        player_name = parts[0].capitalize() if parts else "Player"

        # Artist
        raw_artist = meta.get("xesam:artist")
        if isinstance(raw_artist, (list, tuple)):
            artist = ", ".join(str(a) for a in raw_artist)
        elif raw_artist:
            artist = str(raw_artist)
        else:
            artist = ""

        # Title & Album
        title = str(meta.get("xesam:title", "") or "")
        album = str(meta.get("xesam:album", "") or "")
        art_url = self._resolve_local_art_url(str(meta.get("mpris:artUrl", "") or ""))

        # Length & Position in seconds (MPRIS values are microseconds)
        raw_len = meta.get("mpris:length", 0)
        len_sec = max(0, int(raw_len) // 1_000_000) if raw_len else 0

        raw_pos = d.get("Position", 0)
        pos_sec = max(0, int(raw_pos) // 1_000_000) if raw_pos else 0

        progress_pct = round(min(100.0, max(0.0, (pos_sec / len_sec) * 100.0)), 1) if len_sec > 0 else 0.0

        status = str(d.get("PlaybackStatus", "Stopped"))

        return {
            "available": True,
            "bus_name": target_bus,
            "player_name": player_name,
            "status": status,
            "title": title,
            "artist": artist,
            "album": album,
            "art_url": art_url,
            "position_sec": pos_sec,
            "length_sec": len_sec,
            "progress_pct": progress_pct,
            "can_go_next": bool(d.get("CanGoNext", False)),
            "can_go_previous": bool(d.get("CanGoPrevious", False)),
            "can_play": bool(d.get("CanPlay", False)),
            "can_pause": bool(d.get("CanPause", False)),
        }

    @staticmethod
    def _resolve_local_art_url(art_url: str) -> str:
        """Cache remote http(s) MPRIS album art locally so Cinnamon St.Icon can render it."""
        if not art_url or art_url.startswith("file://"):
            return art_url
        if not (art_url.startswith("http://") or art_url.startswith("https://")):
            return art_url
        try:
            import hashlib
            import tempfile
            import urllib.request
            from pathlib import Path

            cache_dir = Path(tempfile.gettempdir()) / "dpi-album-art"
            cache_dir.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha1(art_url.encode("utf-8")).hexdigest()
            dest = cache_dir / f"{digest}.img"
            if not dest.exists() or dest.stat().st_size == 0:
                req = urllib.request.Request(
                    art_url,
                    headers={"User-Agent": "DynamicPeripheralIsland/1.4"},
                )
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    data = resp.read(2 * 1024 * 1024)
                if data:
                    dest.write_bytes(data)
            if dest.exists() and dest.stat().st_size > 0:
                return dest.as_uri()
        except Exception:
            pass
        return art_url

    # -----------------------------------------------------------------------
    # Transport Controls
    # -----------------------------------------------------------------------

    def play_pause(self, bus_name: Optional[str] = None) -> Tuple[bool, str]:
        """Toggle Play/Pause on the specified or active media player."""
        target_bus = (bus_name or "").strip() or self.get_active_bus_name()
        if not target_bus:
            return False, "Nenhum reprodutor de mídia ativo."

        rc, _, err = self.cmd_runner(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                target_bus,
                "--object-path",
                "/org/mpris/MediaPlayer2",
                "--method",
                "org.mpris.MediaPlayer2.Player.PlayPause",
            ]
        )
        if rc == 0:
            return True, f"Play/Pause alternado em {target_bus}."
        return False, f"Falha ao executar Play/Pause: {err.strip()}"

    def next_track(self, bus_name: Optional[str] = None) -> Tuple[bool, str]:
        """Skip to the next track on the specified or active media player."""
        target_bus = (bus_name or "").strip() or self.get_active_bus_name()
        if not target_bus:
            return False, "Nenhum reprodutor de mídia ativo."

        rc, _, err = self.cmd_runner(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                target_bus,
                "--object-path",
                "/org/mpris/MediaPlayer2",
                "--method",
                "org.mpris.MediaPlayer2.Player.Next",
            ]
        )
        if rc == 0:
            return True, f"Próxima faixa acionada em {target_bus}."
        return False, f"Falha ao avançar faixa: {err.strip()}"

    def previous_track(self, bus_name: Optional[str] = None) -> Tuple[bool, str]:
        """Skip to the previous track on the specified or active media player."""
        target_bus = (bus_name or "").strip() or self.get_active_bus_name()
        if not target_bus:
            return False, "Nenhum reprodutor de mídia ativo."

        rc, _, err = self.cmd_runner(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                target_bus,
                "--object-path",
                "/org/mpris/MediaPlayer2",
                "--method",
                "org.mpris.MediaPlayer2.Player.Previous",
            ]
        )
        if rc == 0:
            return True, f"Faixa anterior acionada em {target_bus}."
        return False, f"Falha ao voltar faixa: {err.strip()}"

# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e este projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [1.0.1] - 2026-11-19

### Corrigido
- **BUG-001 (`src/dpi_core/hardware.py`)**: Corrigida a queda do AJAZZ AJ179 V2 para **50 DPI** e a falha ao ajustar DPI/LED/Sleep na MCU:
  - Removido completamente o envio de opcodes de escrita (`0x02..0x09`) durante `AjazzMouseDriver.read_state()`, restringindo o polling estritamente aos opcodes de leitura (`0x10`, `0x12`, `0x13`, `0x14`, `0x17`).
  - Corrigido `build_packet(..., length_override=...)` e `set_dpi()` para montar o frame real de **25 bytes** (`cmd=0x03`, `buf[3]=0x25`) com os 6 estágios `[lo, hi, lo, hi]` (`raw = dpi // 50`).
  - Corrigido `set_led_color()` para `cmd=0x04` (`length_override=0x12`, 6×RGB = 18B) e `set_sleep_timeout()` para `cmd=0x07` (`length_override=0x04`), com `fcntl.flock(LOCK_EX)` para evitar corrida com o polling.
- **UI do Mouse (`applet/dynamic-peripheral-island@brendo/applet.js`)**: `_buildMouseCard` agora combina `mouse.dpi_stages` reais do backend com os presets extras, ordenados e deduplicados, destacando o `current_dpi` ativo.
- **Testes (`tests/test_hardware.py`)**: Atualizados e adicionados testes de regressão validando os opcodes `0x10..0x17`, o bloqueio de escrita em `read_state()` e o encoding de 25 bytes (`0x03` / `0x25`) em `set_dpi()`.

## [1.0.0] - 2026-11-19

### Adicionado
- **Core de Drivers de Hardware (`src/dpi_core/hardware.py`, `src/dpi_core/__init__.py`)** em Python 3 stdlib puro:
  - `AjazzMouseDriver`: protocolo HID vendor de 33 bytes (`build_packet`, `verify_checksum`), telemetria de bateria/DPI/polling/LED/sleep, cache persistente em `mouse_state.json` para deep sleep do PAW3395 e controles completos.
  - `FuxiHeadsetDriver`: detecção dual 2.4GHz USB (`040b:0897`) e Bluetooth (`01:92:25:27:09:76`), volume/mute, perfis PipeWire/PulseAudio, sidetone via `pw-loopback`, presets de EQ e correção automática do bug ALSA `numid=9` (`fix_alsa_volume`).
  - `K500KeyboardDriver`: leitura passiva de LEDs (`capslock`, `numlock`, `scrolllock`) via `/sys/class/leds` e guia de atalhos físicos `FN`.
  - `GamepadDriver`: suporte a GameSir Nova Lite (`3537:1041` / `3537:2106`) e EasySMX 9124 (`045e:028e`), consolidação de nós cabo+dongle, janela de atividade não-bloqueante de 60s (`is_activity_fresh`), deadzone, layout Xbox/Nintendo e teste de vibração `EVIOCSFF` com orientação XInput em `ENOSYS`.
  - `HardwareHubManager`: snapshot unificado com detecção de transições de alerta e `dispatch_action`.
- **Coletor Antigravity & CLI (`src/dpi_core/antigravity.py`, `src/dpi_core/cli.py`, `bin/dpi-hub`)**:
  - `AntigravityCollector`: descoberta automática do daemon `language_server`, chamada ConnectRPC `GetUserStatus`, leitura do modelo ativo em `antigravity_state.pbtxt`, agrupamento de cotas (`neon`, `hydrogen`, `argon`, `flash`, `claude_gpt`, `carbon` e grupos dinâmicos), Pace Marker, ETA de esgotamento, Swarm Tracker e indexação incremental (`mtime_ns`) de `transcript.jsonl` para histograma de 7 dias e resumo mensal.
  - `bin/dpi-hub`: saídas `--island-json`, `--waybar`, `--pretty` e flags de controle com persistência de preferências em `~/.config/dynamic-peripheral-island/settings.json`.
- **Applet Cinnamon Unificado (`applet/dynamic-peripheral-island@brendo/`)**:
  - `DynamicPeripheralIslandApplet` (`applet.js`, `stylesheet.css`, `metadata.json`): cápsula unificada no `panel2:center` com Data/Hora + Periféricos + Antigravity, Morphing Alert Pill animado (`actor.ease` por 4s), atalho global `Super + Alt + I`, Popover Bento Grid com 3 abas (`Periféricos`, `Antigravity VU`, `Ajustes`) e tema adaptativo Dark/Light Glassmorphism.
- **Instalação e Sistema (`udev/99-dynamic-peripheral-island.rules`, `install.sh`, `uninstall.sh`)**:
  - Regras `udev` para `usb`, `hidraw` e `input` dos dispositivos suportados e scripts idempotentes de instalação/remoção.
- **Design System & Documentação**:
  - Tokens W3C DTCG (`tokens.json`), variáveis CSS (`tokens.css`) e `MASTER.md` gerados via UI/UX Pro Max.
  - `README.md`, `PRODUCTLOG.md`, `ROADMAP.md`, `AGENTS.md`, `docs/ARCHITECTURE.md`, `.gitignore` e `LICENSE` (MIT 2026 Brendo Freitas).
- **Testes Automatizados (`tests/`)**:
  - Suíte `unittest` cobrindo hardware (`test_hardware.py`), coletor Antigravity (`test_antigravity.py`) e CLI/Applet/Documentação (`test_cli_and_applet.py`).

### Segurança
- **Hardware Safe Mode Estrito no `K500KeyboardDriver`**: implementação de `validate_hid_frame` (rejeita buffers vazios, zerados ou fora de tamanho válido) e bloqueio explícito de escrita em `send_raw_packet` (`RuntimeError`) para proteger a MCU Sino Wealth (`258a:0049`).

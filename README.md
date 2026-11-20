# Dynamic Peripheral Island

**Dynamic Peripheral Island** é um hub unificado de telemetria e controle de periféricos + monitor **Antigravity View Usage** integrado como uma cápsula fluida (*Dynamic Island*) na TopBar do **Linux Mint Cinnamon** (com saída nativa também para **Waybar** e terminal).

Construído 100% em **Python 3 stdlib** (zero dependências externas no core) e **Cinnamon JavaScript (CJS)** seguindo o Design System **UI/UX Pro Max** (Glassmorphism adaptativo Dark/Light, ícones SVG simbólicos e animações assíncronas).

---

## Visão Geral & Layout

### Cápsula Unificada na TopBar (`panel2:center`) + Popover Bento Grid

```text
+---------------------------------------------------------------------------------------------------+
|  [ Activities ]       ╭─────────────────────────────────────────────────────────────╮    [Tray]   |
|                       │ [Mouse 85%] [Headset 90%]  |  18:37  |  Neon 81% • Swarm 6  │             |
|                       ╰──────────────────────────┬──────────────────────────────────╯             |
+--------------------------------------------------┼------------------------------------------------+
                                                   ▼  (Clique ou Super + Alt + I)
                        ╭─────────────────────────────────────────────────────────────╮
                        │ [ Periféricos ] [ Áudio ] [ Sistema ] [ Antigravity ] [ Ajustes ] │
                        ├─────────────────────────────────────────────────────────────┤
                        │  ┌───────────────────────────┐ ┌─────────────────────────┐  │
                        │  │ AJAZZ AJ179 V2     85%    │ │ Havit Fuxi H3      90%  │  │
                        │  │ [2.4GHz] DPI 1600  1000Hz │ │ [Bluetooth]  EQ Gaming  │  │
                        │  └───────────────────────────┘ └─────────────────────────┘  │
                        │  ┌───────────────────────────┐ ┌─────────────────────────┐  │
                        │  │ GameSir / EasySMX         │ │ Machenike K500-B94      │  │
                        │  │ [USB-C + 2.4G]  Xbox      │ │ [Hardware Safe Mode]    │  │
                        │  └───────────────────────────┘ └─────────────────────────┘  │
                        ╰─────────────────────────────────────────────────────────────╯
```

- **Layout Central Balanceado**: organiza os **Periféricos** à esquerda, o relógio do sistema (**Data e Hora** via `calendar@cinnamon.org`) no centro e o monitor de **Antigravity** à direita.
- **True Apple Phone Notch na TopBar**: geometria autêntica colada na borda superior da tela (`border-radius: 0 0 16px 16px; margin-top: 0;`), com suporte a 3 estilos visuais configuráveis: **Notch Sólido / Obsidian** (padrão `#0b0c12`), **Clear Glass** (vidro translúcido LiquidGlass) e **Pílula Flutuante** (`border-radius: 999px`), com expansão orgânica elegante no hover (`.dpi-capsule-hovered` / `.dpi-capsule-open`).
- **Expansão Imediata em 1 Clique**: clique direto nos segmentos de Periféricos ou Antigravity abre instantaneamente o Popover Bento Grid completo (`700px`), sem barras flutuantes intermediárias interceptando a interação.
- **Popover Bento Grid Completo**: painel de 700px fixos em 2 colunas com 5 abas (`Periféricos`, `Áudio`, `Sistema`, `Antigravity VU`, `Ajustes`), transições 100% GPU sem flash em branco e zero barras de rolagem vertical.
- **Tooltips Animados LiquidGlass**: microinteração flutuante suave com escala e slide posicionada de forma limpa 6px abaixo da barra superior.
- **Segmento Periféricos**: exibe dispositivos fixados (`pin_*`) ou ativos; clique abre diretamente a aba **Periféricos**.
- **Segmento Data/Hora**: preserva o calendário nativo do Cinnamon integrado harmoniosamente à ilha.
- **Segmento Antigravity**: exibe a cota fixada (`auto` para a menor ou grupo específico) e contador do Swarm; clique abre diretamente a aba **Antigravity VU**.
- **Morphing Alert Pill**: alertas relevantes (`low_battery`, `device_connected`, `charging_started`, `swarm_active`, `low_quota`) expandem suavemente na TopBar por 4 segundos via `.ease(...)`.

---

## Periféricos Suportados

| Dispositivo | VID:PID / Interface | Telemetria | Controles Disponíveis |
| :--- | :--- | :--- | :--- |
| **AJAZZ AJ179 V2** | `249a:5c2f` / `248a:*` (`hidraw` 33B) | Bateria %, carga, conexão (`2.4GHz`, `USB-C`, `Standby`), DPI, Polling Rate, LED, Sleep (com cache em deep sleep) | DPI (`400`–`26000`), Polling (`125`/`250`/`500`/`1000` Hz), Cor LED (`#RRGGBB`), Sleep timeout (`s`) |
| **Havit Fuxi H3** | `040b:0897` (2.4G) + BT `01:92:25:27:09:76` | Bateria %, carga, conexão (`Bluetooth`/`2.4GHz`), Volume, Mudo, Perfil, Sidetone, EQ, detecção de bug ALSA `numid=9` | Volume (`0`–`100%`), Mute, `Corrigir Volume ALSA`, Perfil PipeWire/Pulse, Sidetone (`pw-loopback`), EQ (`gaming`, `music`, `voice`, `flat`) |
| **Machenike K500-B94** | `258a:0049` (`sysfs` / `hidraw`) | **Hardware Safe Mode** ativo (`safe_mode=True`), LEDs (`CAPS`, `NUM`, `SCROLL`) | Somente leitura (proteção da MCU Sino Wealth) + guia de atalhos físicos (`FN+INS`, `FN+↑/↓`, `FN+←/→`, `FN+ESC`) |
| **GameSir Nova Lite** | `3537:1041` (ativo) / `3537:2106` (standby) | Status ativo/standby, bateria (se disponível), `ff_supported`, layout, deadzone (oculto após 60s inativo) | Teste de vibração (`EVIOCSFF`), Deadzone (`0`–`25%`), Layout (`xbox`/`nintendo`) |
| **EasySMX 9124** | `045e:028e` (`hidraw` + `evdev`) | Consolidação automática de cabo USB-C + dongle 2.4GHz em 1 card (`USB-C (Carregando) + Dongle 2.4GHz`) | Teste de vibração (com orientação XInput `M + Menu + View` se `ENOSYS`), Deadzone (`0`–`25%`), Layout |

---

## Mixer de Áudio & Player MPRIS2

O módulo `AudioMixerManager` e `MediaPlayerManager` (`src/dpi_core/audio.py`) fornece controle unificado de áudio e mídia via **PipeWire/PulseAudio** (`pactl`) e **DBus MPRIS2** (`gdbus`), sem dependências externas:

- **Master & Microfone**: controle de volume individual (`0-100%`), alternância de mudo e seleção dinâmica de sinks/sources padrão.
- **Mixer por Aplicativo (Volum-style)**: lista de streams de reprodução ativos (Spotify, Brave, Discord, etc.) com ícones dos apps, sliders individuais de volume e botão de mute por stream.
- **Player de Mídia Spotify / MPRIS2**: card com capa de álbum (`art_url`), título da faixa, artista, barra de progresso com tempo decorrido/total (`mm:ss / mm:ss`) e botões de transporte (`Play/Pause`, `Next`, `Prev`).

---

## Monitor de Sistema

O módulo `SystemMonitor` (`src/dpi_core/sysmon.py`) coleta telemetria de hardware diretamente do kernel Linux (`/proc` e `/sys`) em 100% Python 3 stdlib:

- **CPU**: percentual de uso por delta de `/proc/stat`, monitoramento térmico via `/sys/class/hwmon` (`k10temp` Tctl/Tdie, `zenpower`, `coretemp`, `acpitz`), núcleos e load average 1m.
- **GPU**: atividade do processador gráfico e alocação de VRAM via AMD DRM (`gpu_busy_percent`, `mem_info_vram_*`) e temperaturas `edge`/`junction`.
- **Memória RAM**: ocupação em GB e percentual via `/proc/meminfo` com barra de severidade adaptativa.
- **Armazenamento & NVMe**: uso da partição `/` (`os.statvfs`) e temperatura do SSD NVMe (`hwmon` `nvme`).
- **Rede em Tempo Real**: identificação da interface física ativa mais utilizada (`/proc/net/dev`) e cálculo de taxas de download/upload em KB/s e MB/s.
- **Uptime**: tempo de atividade do sistema em horas e minutos formatados.

---

## Antigravity View Usage

O coletor `AntigravityCollector` (`src/dpi_core/antigravity.py`) descobre o daemon `language_server` ativo em `~/.gemini/antigravity/daemon/hub_*.json`, consulta o endpoint ConnectRPC `GetUserStatus`, lê o modelo selecionado em `~/.gemini/antigravity/antigravity_state.pbtxt` e indexa incrementalmente (`mtime_ns`) os transcripts em `~/.gemini/antigravity/brain/*/.system_generated/logs/transcript.jsonl`:

- **Grupos de Cotas**: `Gemini 4 Neon` (`neon`), `Gemini 4 Hydrogen` (`hydrogen`), `Gemini 4 Argon / Orchestrator` (`argon`), `Gemini 4 Carbon` (`carbon`), `Gemini 3.8 Flash` (`flash`), `Claude 5.5 & GPT-OSS` (`claude_gpt`) e detecção dinâmica de novos modelos.
- **Pace Marker & ETA**: marcador vertical indicando a fração de tempo decorrida na janela (`5h` ou `7d`) e estimativa de esgotamento (`⚡ ~Xh`) quando o ritmo ultrapassa a janela.
- **Swarm Tracker**: lista de subagentes ativos/inativos (`WORKING` / `IDLE`) e contagem de steps da sessão atual, além de tokens (`IN`, `CACHE`, `OUT`).
- **Histograma 7 Dias & Mensal**: gráfico de barras diário dos últimos 7 dias + consumo total mensal e ranking dos top projetos.

---

## Instalação e Atalho

### Pré-requisitos
- Linux Mint Cinnamon (X11), `python3` (>= 3.8), `pactl`, `amixer`, `bluetoothctl`, `upower` (utilitários padrão de sistema).

### Instalar
```bash
git clone <url-do-repositorio> Dynamic-Peripheral-Island
cd Dynamic-Peripheral-Island
./install.sh
```
O script `install.sh`:
1. Cria o symlink `~/.local/bin/dpi-hub` apontando para `bin/dpi-hub`.
2. Instala o applet em `~/.local/share/cinnamon/applets/dynamic-peripheral-island@brendo`.
3. Registra o applet em `org.cinnamon enabled-applets` na posição `panel2:center:1:dynamic-peripheral-island@brendo:99`.
4. Instala `/etc/udev/rules.d/99-dynamic-peripheral-island.rules` via `pkexec` (se ainda não existir) e recarrega as regras `udev`.
5. Recarrega o tema e o applet via `dbus-send` (`org.Cinnamon.ReloadTheme` e `org.Cinnamon.ReloadXlet`).

### Atalho Global
- **`Super + Alt + I`**: abre ou fecha o Popover da Dynamic Peripheral Island a partir de qualquer workspace.

### Desinstalar
```bash
./uninstall.sh
```

---

## Comandos `dpi-hub`

### Modos de Saída
```bash
dpi-hub --island-json   # JSON unificado consumido pelo Applet Cinnamon
dpi-hub --waybar        # JSON em linha única para Waybar (text, tooltip, class, percentage)
dpi-hub --pretty        # Dashboard colorido no terminal
```

### Flags de Controle (retornam `{"ok": bool, "message": str}`)

| Categoria | Flag | Exemplo |
| :--- | :--- | :--- |
| **Mouse AJAZZ** | `--set-dpi <DPI>` | `dpi-hub --set-dpi 1600` |
| | `--set-polling <HZ>` | `dpi-hub --set-polling 1000` |
| | `--set-mouse-led <HEX>` | `dpi-hub --set-mouse-led "#22C55E"` |
| | `--set-mouse-sleep <SEC>` | `dpi-hub --set-mouse-sleep 300` |
| **Headset Fuxi H3** | `--set-volume <PCT>` | `dpi-hub --set-volume 80` |
| | `--toggle-mute` | `dpi-hub --toggle-mute` |
| | `--fix-alsa` | `dpi-hub --fix-alsa` |
| | `--set-audio-profile <PROFILE>` | `dpi-hub --set-audio-profile a2dp-sink` |
| | `--set-sidetone <ON\|OFF>` | `dpi-hub --set-sidetone on` |
| | `--set-eq <PRESET>` | `dpi-hub --set-eq gaming` |
| **Gamepads** | `--test-rumble [--controller-id ID]` | `dpi-hub --test-rumble` |
| | `--set-deadzone <PCT> [--controller-id ID]` | `dpi-hub --set-deadzone 5` |
| | `--set-gamepad-layout <xbox\|nintendo>` | `dpi-hub --set-gamepad-layout xbox` |
| **Áudio & Mixer** | `--set-master-volume <PCT>` | `dpi-hub --set-master-volume 75` |
| | `--toggle-master-mute` | `dpi-hub --toggle-master-mute` |
| | `--set-default-sink <NAME>` | `dpi-hub --set-default-sink alsa_output.pci...` |
| | `--set-mic-volume <PCT>` | `dpi-hub --set-mic-volume 80` |
| | `--toggle-mic-mute` | `dpi-hub --toggle-mic-mute` |
| | `--set-default-source <NAME>` | `dpi-hub --set-default-source alsa_input.usb...` |
| | `--set-app-volume <ID> <PCT>` | `dpi-hub --set-app-volume 42 60` |
| | `--toggle-app-mute <ID>` | `dpi-hub --toggle-app-mute 42` |
| **Mídia (Spotify/MPRIS2)** | `--media-play-pause [--media-player BUS]` | `dpi-hub --media-play-pause` |
| | `--media-next [--media-player BUS]` | `dpi-hub --media-next` |
| | `--media-prev [--media-player BUS]` | `dpi-hub --media-prev` |
| **Preferências** | `--pin-device <DEV[:BOOL]>` | `dpi-hub --pin-device headset:true` |
| | `--pin-quota <GROUP>` | `dpi-hub --pin-quota neon` |
| | `--set-theme <auto\|dark\|light>` | `dpi-hub --set-theme auto` |
| | `--set-notch-style <obsidian\|glass\|pill>` | `dpi-hub --set-notch-style obsidian` |
| | `--set-alert-threshold <PCT>` | `dpi-hub --set-alert-threshold 20` |
| | `--set-poll-interval <SEC>` | `dpi-hub --set-poll-interval 5` |

---

## Testes

```bash
python3 -m unittest discover -s tests -v
```

---

## Documentação Adicional

- [Arquitetura Técnica](file:///home/brendo/Projetos/Dynamic-Peripheral-Island/docs/ARCHITECTURE.md)
- [Design System MASTER](file:///home/brendo/Projetos/Dynamic-Peripheral-Island/design-system/dynamic-peripheral-island/MASTER.md)
- [Governança e Regras (`AGENTS.md`)](file:///home/brendo/Projetos/Dynamic-Peripheral-Island/AGENTS.md)
- [Product Log & Decisões (`PRODUCTLOG.md`)](file:///home/brendo/Projetos/Dynamic-Peripheral-Island/PRODUCTLOG.md)
- [Roadmap](file:///home/brendo/Projetos/Dynamic-Peripheral-Island/ROADMAP.md)
- [Changelog](file:///home/brendo/Projetos/Dynamic-Peripheral-Island/CHANGELOG.md)
- [Licença MIT](file:///home/brendo/Projetos/Dynamic-Peripheral-Island/LICENSE)

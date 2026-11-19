# Product Log & Decisões de Engenharia (`PRODUCTLOG.md`)

Registro histórico das decisões de arquitetura, design de produto, análise de riscos de hardware, topologia do Swarm de construção e procedimentos de rollback do projeto **Dynamic Peripheral Island** (`v1.0.0`).

---

## 1. Decisões da Entrevista de Produto (`/grill-me`)

Antes da implementação, os requisitos do produto foram consolidados em **7 decisões arquiteturais** fundamentais:

| # | Decisão | Escolha Adotada | Racional Técnico |
| :---: | :--- | :--- | :--- |
| **1** | **Integração na TopBar** | **Cápsula Unificada (`panel2:center`)** envolvendo Data/Hora (`calendar@cinnamon.org`) + Periféricos + Antigravity | Evita fragmentação visual no painel superior do Cinnamon, mantendo o clique na Data/Hora para o calendário nativo e oferecendo pontos de entrada dedicados por segmento. |
| **2** | **Interface do Popover** | **100% CJS Nativo (Bento Grid)** dentro do próprio `PopupMenu` do Cinnamon | Elimina a latência e complexidade de spawnar uma janela GTK4/Electron externa; garante fechamento automático ao clicar fora e integração nativa com o compositor Muffin. |
| **3** | **Stack do Backend** | **100% Python 3 Stdlib** escrito do zero (`src/dpi_core/`) | Zero dependências `pip`, portabilidade imediata em qualquer Linux Mint/Ubuntu/Arch e tempo de inicialização mínimo para chamadas periódicas do applet. |
| **4** | **Segurança do Teclado K500** | **Hardware Safe Mode Estrito** (somente leitura) | Protege a MCU Sino Wealth (`258a:0049`) contra corrupção de bootloader causada por pacotes HID malformados, expondo apenas LEDs via `sysfs` e guia de atalhos `FN`. |
| **5** | **Telemetria Antigravity** | **Antigravity View Usage Completo** (cotas agrupadas, Pace Marker, ETA, Swarm Tracker, Histograma 7d) | Centraliza o consumo de IA (Neon, Hydrogen, Argon, Carbon, Flash, Claude/GPT) e o status de subagentes diretamente na barra, sem precisar alternar janelas. |
| **6** | **Linguagem Visual** | **Glassmorphism Adaptativo** (Dark/Light automático via `Gio.Settings`) | Segue o tema ativo do Cinnamon (ex.: `WhiteSur-Dark-solid`) e os tokens do UI/UX Pro Max (`MASTER.md`), sem emojis estruturais — apenas ícones SVG simbólicos. |
| **7** | **Interação & Alertas** | **Atalho Global `Super + Alt + I` + Morphing Pill (4s)** | Permite abrir/fechar a ilha via teclado de qualquer workspace e exibe expansões suaves (`actor.ease`) apenas em eventos relevantes (bateria baixa, conexão, carga, Swarm ativo). |

---

## 2. Topologia do Swarm de Construção

A versão `v1.0.0` foi construída de forma paralela por um Swarm multi-agente coordenado com separação estrita de arquivos:

| Agente | Modelo | Papel & Escopo Exclusivo |
| :--- | :--- | :--- |
| `coordinator` | Argon | Orquestração geral, definição de contratos de interface e integração final. |
| `hw-engine` | Gemini 4 Neon (High) | Drivers Python stdlib (`src/dpi_core/hardware.py`, `__init__.py`) e regras `udev`. |
| `ag-engine` | Gemini 4 Hydrogen (High) | Coletor ConnectRPC + parser incremental (`src/dpi_core/antigravity.py`), CLI (`cli.py`, `bin/dpi-hub`). |
| `island-ui` | Gemini 4 Neon (High) | Applet Cinnamon CJS (`applet.js`, `stylesheet.css`, `metadata.json`), `install.sh` e `uninstall.sh`. |
| `design-docs` | Gemini 4 Hydrogen (Medium) | Tokens UI/UX Pro Max (`MASTER.md`, `tokens.json`, `tokens.css`), governança e documentação técnica. |
| `test-verifier` | Gemini 4 Hydrogen (High) | Suíte `unittest` (`tests/test_*.py`), auditoria cruzada, instalação runtime e commit inicial. |

---

## 3. Análise de Riscos de Hardware e Mitigações

### 3.1. MCU Sino Wealth — Machenike K500-B94 (`258a:0049`) [CRÍTICO]
- **Risco**: Controladores Sino Wealth podem entrar em estado irrecuperável ou travar em modo bootloader ao receberem frames HID vendor vazios, zerados ou com checksum/tamanho incorreto.
- **Mitigação**:
  - `K500KeyboardDriver` opera exclusivamente em `safe_mode = True`.
  - `validate_hid_frame(frame)` rejeita com `ValueError` qualquer buffer vazio, composto exclusivamente por `0x00`, ou fora dos tamanhos válidos.
  - `send_raw_packet()` bloqueia explicitamente qualquer escrita (`RuntimeError`) enquanto em Safe Mode.
  - Leitura de estado feita de forma passiva via `/sys/class/leds/input*::*`.

### 3.2. Deep Sleep do Sensor PAW3395 — AJAZZ AJ179 V2 (`249a:5c2f` / `248a:*`) [MÉDIO]
- **Risco**: Quando o mouse entra em standby sem fio, consultas HID retornam timeout ou falha de leitura, fazendo a UI piscar como "Desconectado" ou perder o último percentual de bateria.
- **Mitigação**: Persistência do último estado válido em `~/.config/dynamic-peripheral-island/mouse_state.json` com flags `standby` e `cached`, preservando a última leitura conhecida.

### 3.3. Bug de Volume Zero no ALSA — Havit Fuxi H3 (`040b:0897`) [BAIXO]
- **Risco**: Ao reconectar o dongle 2.4GHz, o driver USB Audio do kernel pode inicializar o controle `numid=9` do card `FuxiH3` em `0,0` e `numid=7` silenciado.
- **Mitigação**: Detecção automática (`alsa_zero_bug`) e ação `fix_alsa_volume()` via `amixer -c FuxiH3 cset numid=9 100,100` + `numid=7 on`.

### 3.4. Duplicidade e Modo DInput — Gamepads (`3537:*` e `045e:028e`) [BAIXO]
- **Risco**: O EasySMX 9124 conectado simultaneamente via cabo USB-C e dongle 2.4GHz expõe dois nós `045e:028e`; além disso, em modo DirectInput, `ioctl(EVIOCSFF)` retorna `ENOSYS (38)`.
- **Mitigação**:
  - Consolidação automática dos dois nós `045e:028e` em um único dispositivo com status `USB-C (Carregando) + Dongle 2.4GHz`.
  - Janela de atividade não-bloqueante de 60 segundos (`/tmp/dpi-gamepad-<event>.active`) para ocultar controles inativos da TopBar.
  - Tratamento amigável de `errno.ENOSYS` orientando a alternância para XInput (`M + Menu + View` por 2s).

---

## 4. Procedimentos de Rollback

Caso seja necessário reverter a instalação da Dynamic Peripheral Island no sistema:

1. **Remoção automatizada do Applet e CLI**:
   ```bash
   ./uninstall.sh
   ```
   O script remove `dynamic-peripheral-island@brendo` de `org.cinnamon enabled-applets`, apaga `~/.local/share/cinnamon/applets/dynamic-peripheral-island@brendo` e remove `~/.local/bin/dpi-hub`.

2. **Restauração manual do painel Cinnamon (se necessário)**:
   ```bash
   gsettings get org.cinnamon enabled-applets
   # Garantir que calendar@cinnamon.org permaneça em panel2:center:0
   dbus-send --session --dest=org.Cinnamon --type=method_call /org/Cinnamon org.Cinnamon.ReloadXlet string:'calendar@cinnamon.org' string:'APPLET'
   ```

3. **Remoção de regras `udev` (opcional)**:
   ```bash
   sudo rm -f /etc/udev/rules.d/99-dynamic-peripheral-island.rules
   sudo udevadm control --reload-rules && sudo udevadm trigger
   ```

4. **Limpeza de caches e preferências**:
   ```bash
   rm -rf ~/.config/dynamic-peripheral-island ~/.cache/dynamic-peripheral-island
   ```

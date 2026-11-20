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

### 2.1. Evolução do Swarm na v1.0.2–v1.0.5 e Agente `docs-git`

O `coordinator` opera em **Orchestrator (Argon)** (`gemini-pro-orchestrator-g1-pro`), e todos os workers do Swarm operam em **Gemini 3.8 Flash (High)** (`gemini-3.8-flash-high`) com a renovação da janela de cota de 5h.
Além disso, foi consolidado o agente dedicado **`docs-git`** (`.agents/agents/docs-git.md`) para centralizar a governança da documentação técnica contínua, auditoria de integridade e geração de commits semânticos no Git (Conventional Commits).

| Agente | Modelo Ativo | Papel Atualizado |
| :--- | :--- | :--- |
| `coordinator` | `Orchestrator (Argon)` | Orquestração do Swarm e alinhamento de entregáveis. |
| `hw-engine` | `Gemini 3.8 Flash (High)` | Drivers de hardware Python stdlib (`src/dpi_core/hardware.py`). |
| `ag-engine` | `Gemini 3.8 Flash (High)` | Coletor Antigravity ConnectRPC e CLI (`src/dpi_core/antigravity.py`, `cli.py`). |
| `island-ui` | `Gemini 3.8 Flash (High)` | Applet Cinnamon CJS (`applet.js`, `stylesheet.css`, `metadata.json`). |
| `design-docs` | `Gemini 3.8 Flash (High)` | Design System (`MASTER.md`, tokens DTCG) e arquitetura visual. |
| `test-verifier` | `Gemini 3.8 Flash (High)` | Testes automatizados (`tests/test_*.py`) e validação em runtime. |
| `docs-git` | `Gemini 3.8 Flash (High)` | Governança de documentação técnica, histórico de produto e Conventional Commits. |

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

## 4. Registro de Bugs e Incidentes

### `BUG-001` — Queda de DPI do AJAZZ AJ179 V2 para 50 DPI e Falha de Ajuste via `0x03` (`2026-11-19`)
- **Severidade**: Alta (alteração involuntária de estado em hardware real).
- **Causa Raiz**:
  1. Quando as leituras HID `0x13`/`0x12`/`0x14`/`0x17` não casavam o parser anterior, `AjazzMouseDriver.read_state()` executava fallback enviando opcodes de **escrita** (`0x03`, `0x02`, `0x05`, `0x06`) com payload zerado a cada ciclo de 5s.
  2. `set_dpi()` enviava apenas 3 bytes (`<BH`) em vez do frame real de **25 bytes** com `buf[3]=0x25` (`length_override=0x25`) e 6 estágios `[lo, hi, lo, hi]` (`raw = dpi // 50`).
  3. `set_led_color()` enviava `0x05` em vez de `0x04` (`length_override=0x12`, 6×RGB = 18B) e `set_sleep_timeout()` enviava `0x06` (Sensor LOD/MotionSync) em vez de `0x07` (`length_override=0x04`).
- **Impacto no Hardware**: A MCU do AJAZZ AJ179 V2 interpretou o pacote `0x03` zerado como gravação de `raw=0` (**50 DPI**, mínimo absoluto do sensor PAW3395) em todos os 6 estágios de DPI.
- **Correção Aplicada**:
  - Remoção total dos opcodes de escrita (`0x02..0x09`) de `read_state()`, restringindo o polling a `0x10`, `0x12`, `0x13`, `0x14`, `0x17`.
  - Suporte a `length_override` em `build_packet()`, encoding de 25 bytes em `set_dpi()`, correção de `set_led_color()` (`0x04`/`0x12`) e `set_sleep_timeout()` (`0x07`/`0x04`), e serialização via `fcntl.flock(LOCK_EX)`.
  - Atualização do card do mouse no `applet.js` para combinar `mouse.dpi_stages` do backend com os presets extras.
- **Restauração do Perfil do Usuário**: Perfil restaurado no hardware real (`/dev/hidraw4`) com estágios `[400, 950, 1200, 1600, 2400, 3200]`, estágio ativo `2` (**1200 DPI**), polling rate `250 Hz`, LOD `2mm` e sleep `300s`.
- **Nova Regra Preventiva**: Formalizada em `AGENTS.md` a proibição absoluta de enviar opcodes de escrita (`0x02..0x09`) em rotinas de leitura (`read_state()`), com cobertura obrigatória por teste de regressão em `tests/test_hardware.py`.

### `UX-001` — Fundo Azul Artificial e Hover Não-Nativo na TopBar do Cinnamon (`2026-11-19`)
- **Severidade**: Média (inconsistência estética e quebra da integração visual com a barra do Cinnamon).
- **Causa Raiz**:
  - A cápsula da TopBar estava renderizada como um bloco estático de pílula azul (`.dpi-unified-capsule` com `background-color: rgba(15, 23, 42, 0.84)` e `border-radius: 999px`).
  - O hover era forçado via regras CSS customizadas (`.dpi-capsule-segment:hover`) que aplicavam fundo azul translúcido, destoando do comportamento e da estética dos ícones nativos da área de notificação do Cinnamon (`systray@cinnamon.org`).
- **Arquivos Modificados**:
  - `applet/dynamic-peripheral-island@brendo/applet.js`: remoção da classe `applet-box` do container raiz (`this.actor.remove_style_class_name("applet-box")`) e aplicação direta de `applet-box` em cada segmento clicável (`_segPeripherals` e `_segAntigravity`).
  - `applet/dynamic-peripheral-island@brendo/stylesheet.css`: remoção do fundo azul e de `border-radius: 999px` em `.dpi-unified-capsule` / `.dpi-capsule-segment`, adoção de `border-radius: 6px` com fundo transparente, remoção das regras customizadas de hover (permitindo que o `.applet-box:hover` nativo do tema do usuário dite a cor exata de hover), e suavização do estado ativo (`.dpi-capsule-segment-active`) para tons neutros e violeta.
  - `tests/test_cli_and_applet.py`: asserções automatizadas validando a presença de `remove_style_class_name("applet-box")`, o uso de `applet-box` nos segmentos, e a ausência do fundo azul `rgba(15, 23, 42, 0.84)` e `border-radius: 999px`.
- **Validação**: Aprovado nos testes unitários e confirmado visualmente no Cinnamon Desktop com hover retangular de cantos arredondados (`6px`), perfeitamente integrado ao SystemTray nativo.

### `BUG-002` — Conflito de Evento no Clique do Segmento Antigravity e Alternância de Fonte (`2026-11-19`)
- **Severidade**: Média (falha ao abrir a aba correspondente no Popover e oscilação tipográfica).
- **Causa Raiz**:
  1. Conflito de ciclo de eventos no Clutter/CJS: a classe base `Applet.Applet` do Cinnamon conecta `this.actor` ao sinal `button-press-event` chamando `on_applet_clicked()`. Como os segmentos internos (`_segAntigravity` e `_segPeripherals`) conectavam-se ao `button-release-event`, o clique pressionado disparava a ação padrão da ilha antes da liberação do mouse, abrindo a aba padrão de periféricos em vez da aba de telemetria do Antigravity.
  2. Declarações forçadas de `font-family: Monospace;` e `font-family: Sans;` no `stylesheet.css` sobrescreviam a fonte padrão do sistema do usuário (`Lexend 10`), gerando uma troca visível de fonte entre os estados de repouso e interação no applet.
- **Arquivos Modificados**:
  - `applet/dynamic-peripheral-island@brendo/applet.js`: migração de `button-release-event` para `button-press-event` em `_segPeripherals`, `_segAntigravity` e `_morphPill`, retornando `Clutter.EVENT_STOP` no botão 1 (esquerdo) para interromper a propagação até o ator pai; guarda defensiva adicional em `on_applet_clicked(event)` inspecionando `event.get_source()` para abrir a aba correta se o evento atingir os nós dos segmentos.
  - `applet/dynamic-peripheral-island@brendo/stylesheet.css`: remoção total de declarações `font-family`, padronizando o uso de classes `applet-label dpi-pill-text` e `font-weight: bold;` para herdar integralmente a tipografia nativa do Cinnamon (`Lexend 10`).
  - `tests/test_cli_and_applet.py`: testes unitários garantindo conexão exclusiva a `button-press-event` nos segmentos e ausência de declarações `font-family:` no CSS.
- **Validação**: Suíte completa de 30 testes aprovada, reload do applet sem nenhum `JS ERROR` ou `St-WARNING` em `~/.xsession-errors`, e verificação de clique no segmento Antigravity abrindo diretamente a aba correspondente sem qualquer oscilação de fonte.

### `UX-002` — Dynamic Island Hover-Only, Layout Periféricos | Data e Hora | Antigravity e Reload de Tema (`2026-11-19`)
- **Severidade**: Média (refinamento visual da TopBar e persistência indesejada de cache CSS no Cinnamon).
- **Causa Raiz**:
  1. A cápsula unificada mantinha todos os componentes à direita da data e hora (`calendar@cinnamon.org`), quebrando a simetria orgânica de uma Ilha Dinâmica centralizada.
  2. A cápsula permanecia visível com borda/fundo estáticos mesmo quando o usuário não estava interagindo com ela, poluindo a barra superior do Cinnamon.
  3. Descoberta de runtime: a chamada D-Bus `org.Cinnamon.ReloadXlet` recarrega apenas o arquivo JavaScript (`applet.js`), mas o Cinnamon armazena em cache o `stylesheet.css`. A recarga efetiva do CSS exige a invocação explícita de `org.Cinnamon.ReloadTheme`.
- **Arquivos Modificados**:
  - `applet/dynamic-peripheral-island@brendo/applet.js`: criação do container `_leftSlot` (`St.BoxLayout`) inserido à esquerda do `calendarActor` via `centerBox.insert_child_below(this._leftSlot, calendarActor)`, mantendo `this.actor` à direita; conexão de eventos `enter-event` e `leave-event` no conjunto da ilha com debounce de 80ms para alternar `.dpi-capsule-hovered` suavemente; sincronização com `.dpi-capsule-open`; e descarte limpo de listeners e atores no lifecycle.
  - `applet/dynamic-peripheral-island@brendo/stylesheet.css`: definição de `.dpi-unified-capsule` como 100% transparente em estado idle; regras de glassmorphism em `.dpi-capsule-hovered` e `.dpi-capsule-open` (`rgba(40, 42, 54, 0.90)` no dark, `rgba(248, 250, 252, 0.92)` no light com bordas sutis e zero cor azul).
  - `install.sh`: inclusão do comando D-Bus `org.Cinnamon.ReloadTheme` antes de `org.Cinnamon.ReloadXlet` para garantir aplicação atômica de estilos.
  - `tests/test_cli_and_applet.py`: testes unitários adicionados para validar a inserção de `_leftSlot`, transparência em idle, classes de hover e presença de `ReloadTheme` no script de instalação.
- **Validação**: 30/30 testes aprovados, reload de tema e applet validados sem erros no `~/.xsession-errors`, transição contínua sem piscar entre os elementos centrais e transparência perfeita da barra em repouso.

### `BUG-003` — Fechamento Prematuro do Popover ao Soltar o Clique no Segmento Esquerdo (`_leftSlot`) (`2026-11-19`)
- **Severidade**: Alta (impedia que o clique normal no segmento esquerdo de Periféricos mantivesse o Popover aberto).
- **Causa Raiz**:
  - Quando `this.menu.open(true)` é chamado durante `button-press-event`, o `PopupMenuManager` do Cinnamon entra em captura global de eventos (`_onEventCapture` em `popupMenu.js:3688`).
  - No `BUTTON_RELEASE` subsequente, `PopupMenuManager` verifica `_activeMenuContains(event.get_source())`, que testa apenas se o ator clicado está dentro de `this.menu.actor` ou `this.menu.sourceActor` (por padrão `this.actor`, posicionado à direita do relógio).
  - Como `this._leftSlot` (segmento de Periféricos) é inserido diretamente em `panel._centerBox` à esquerda do relógio (fora de `this.actor`), `_activeMenuContains` retornava `false` no `BUTTON_RELEASE` e fechava o menu imediatamente ao soltar o botão do mouse.
- **Arquivos Modificados**:
  - `applet/dynamic-peripheral-island@brendo/applet.js`: implementação do hook oficial `menuEventFilter(event)` do Cinnamon (invocado em `popupMenu.js:3673` antes da lógica de fechamento) retornando `true` para eventos `BUTTON_RELEASE` e tratando `BUTTON_PRESS` em `this._leftSlot` / `this._segPeripherals` e `this.actor` / `this._segAntigravity`; atualização dinâmica de `this.menu.sourceActor` em `_openTabFromSegment(tabName)` para o segmento clicado e restauração de `this.menu.sourceActor = this.actor` no unload; ocultação do divisor vertical (`this._midDivider.hide()`) entre Data/Hora e Antigravity.
  - `tests/test_cli_and_applet.py`: testes cobrindo `menuEventFilter(event)`, `Clutter.EventType.BUTTON_RELEASE`, atualização de `this.menu.sourceActor` e `this._midDivider.hide()`.
- **Validação**: 30/30 testes aprovados e validação em runtime no Cinnamon confirmando abertura estável e alinhada do Popover ao clicar tanto em Periféricos (esquerda) quanto em Antigravity (direita).

### `UX-003` — Alinhamento Visual e Temático das 3 Abas do Popover com o Calendário Nativo (`2026-11-19`)
- **Severidade**: Média (coesão visual com os applets nativos do Cinnamon).
- **Causa Raiz**:
  - O Popover usava um `PopupMenu.PopupBaseMenuItem` envolvendo `this._popoverRoot`, criando uma caixa e borda interna duplicada dentro do `.popup-menu`, além de cores de superfície (`rgba(15, 23, 42, ...)`) distintas do `calendar@cinnamon.org`.
- **Arquivos Modificados**:
  - `applet/dynamic-peripheral-island@brendo/applet.js`: remoção de `PopupMenu.PopupBaseMenuItem` em `_buildPopover()` e anexação direta via `this.menu.addActor(this._popoverRoot)` (idêntico ao `calendar@cinnamon.org`).
  - `applet/dynamic-peripheral-island@brendo/stylesheet.css`: `.dpi-popover-root` transparente usando a moldura nativa `.popup-menu` do tema Cinnamon; superfícies `.dpi-tab-bar`, `.dpi-card`, `.dpi-hero-box` e `.dpi-metric-tile` em `#282a36` com `border: 1px solid rgba(25, 26, 34, 0.9)` e `border-radius: 4px`; subcards/rows em `#232530`; chips e botões em `#2c2f3c` (hover `#373a4b`); estados selecionados/ativos em `rgba(189, 147, 249, 0.5)` e trilhas de barra em `#191a22`.
  - `tests/test_cli_and_applet.py`: asserções validando `this.menu.addActor(this._popoverRoot)` e a paleta do Calendário em `stylesheet.css`.
- **Validação**: Reload de tema (`org.Cinnamon.ReloadTheme`) e applet (`org.Cinnamon.ReloadXlet`) sem erros ou warnings em `~/.xsession-errors`.

### `UX-004` — Transições Fluidas entre Abas e Expansão de Cards no Popover (`2026-11-19`)
- **Severidade**: Baixa (polimento de micro-interações no Popover Bento Grid).
- **Causa Raiz**:
  - A troca de abas reconstruía todo o Popover instantaneamente sem transição espacial, e o polling periódico de 5s re-renderizava o Popover aberto mesmo quando o payload JSON não havia mudado.
- **Arquivos Modificados**:
  - `applet/dynamic-peripheral-island@brendo/applet.js`: criação de `_switchTab(newTabId, animate = true)` animando `this._bodyStack.ease({ opacity: 255, translation_x: 0, duration: 180, mode: Clutter.AnimationMode.EASE_OUT_CUBIC })` a partir de `translation_x = dir * 14`; criação de `_animateCardBody(body, cardKey)` animando a expansão de cards (`translation_y: -6 -> 0`, `160ms`, `EASE_OUT_QUAD`); comparação de `payloadHash` em `_refreshNow()` para evitar re-renderização redundante com o menu aberto.
  - `tests/test_cli_and_applet.py`: asserções garantindo a presença de `_switchTab`, `_animateCardBody`, `translation_x` e `EASE_OUT_CUBIC`.
- **Validação**: 30/30 testes aprovados e transições verificadas em runtime no Cinnamon.

### `BUG-004` — Omissão do GameSir Nova Lite em Modo XInput 2.4GHz (`3537:1040`) (`2026-11-19`)
- **Severidade**: Alta (o controle desaparecia completamente da detecção ao ser ligado em modo XInput via dongle sem fio).
- **Causa Raiz**:
  - Quando o GameSir Nova Lite é ligado no modo XInput 2.4GHz, a MCU do dongle altera dinamicamente seu PID USB de `3537:2106` (standby) para `3537:1040` (`2.4G XBOX 360 For Windows`), expondo o gamepad real em `event11 js0` e uma interface auxiliar de teclado (`2.4G XBOX 360 For Windows Keyboard`) em `event14`.
  - O `GamepadDriver` anterior possuía `GAMESIR_ACTIVE_PID = "1041"` fixo (modo HID/Android), descartando silenciosamente o nó `3537:1040`. Além disso, a varredura selecionava por vezes a interface secundária `Keyboard` em vez do gamepad com Force Feedback.
- **Arquivos Modificados**:
  - `src/dpi_core/hardware.py`: substituição por conjuntos `GAMESIR_STANDBY_PIDS = frozenset({"2106"})` e `GAMESIR_ACTIVE_PIDS = frozenset({"1040", "1041"})`, aceitando qualquer PID ativo não-standby; ordenação estrita em `gs_active_inputs` priorizando nós com handler `js*`, `ff_supported == True` e sem substring `keyboard`; atribuição imediata de `is_active = True` (o dongle só assume o PID ativo quando o controle está ligado); e formatação descritiva em `connection_type` (`"2.4GHz (XInput)"`).
  - `tests/test_hardware.py`: novo teste unitário `test_gamesir_nova_lite_xinput_mode_and_standby` cobrindo o nó composto `1040` + `Keyboard` e atualização de `test_60s_inactivity_hides_gamepad_after_timeout` para isolar o controle EasySMX.
- **Validação**: 31/31 testes aprovados e detecção imediata do controle no hardware real como `2.4GHz (XInput)`.

### `UX-005` — Auto-exibição de Periféricos Ativos na TopBar (`2026-11-19`)
- **Severidade**: Média (melhoria ergonômica de visibilidade solicitada pelo usuário).
- **Causa Raiz**:
  - Periféricos sem fio não fixados (`pinned == False`) permaneciam ocultos na cápsula da TopBar até que o usuário os fixasse manualmente em Ajustes, mesmo quando o dispositivo estava ativamente em uso.
- **Arquivos Modificados**:
  - `src/dpi_core/cli.py`: em `_summarize_device`, a condição de visibilidade foi expandida para incluir qualquer periférico sem fio ativo (`active == True`) ou em carregamento (`charging == True`) nos cards de mouse, headset e gamepad; em gamepads sem telemetria percentual de bateria no protocolo XInput, implementado rótulo contextual (`"GameSir"`, `"EasySMX"` ou `"Pad"` com sufixo `"+"` se carregando).
  - `tests/test_cli_and_applet.py`: asserções automatizadas validando a presença automática de periféricos ativos na saída da TopBar.
- **Validação**: Saídas `--island-json`, `--waybar` e `--pretty` exibindo o GameSir ativo na TopBar sem necessidade de fixação prévia.

### `UX-006` — Troca Fluida por Hover com Menus Abertos (`2026-11-19`)
- **Severidade**: Média (fluxo de navegação unificado entre a Ilha Dinâmica e o Calendário do Cinnamon).
- **Causa Raiz**:
  - Ao abrir o Popover ou o Calendário, o usuário precisava clicar explicitamente nos outros segmentos da barra central para alternar entre as visões, exigindo múltiplos cliques repetitivos.
- **Arquivos Modificados**:
  - `applet/dynamic-peripheral-island@brendo/applet.js`:
    1. Quando o Popover da ilha está aberto (`this.menu.isOpen`), `menuEventFilter(event)` captura `Clutter.EventType.ENTER`: se o cursor mover para o outro segmento da ilha, invoca `_switchTabFromTopBarHover` reposicionando o `sourceActor` e animando a troca de abas; se entrar no `calendarActor`, fecha a ilha e abre o menu nativo do Calendário.
    2. Quando o menu do Calendário estiver aberto, um listener temporário monitora a entrada do mouse nos segmentos da ilha para fechar o calendário e abrir o Popover diretamente na aba correspondente, desconectando-se imediatamente ao fechar o menu.
    3. Dentro do Popover, adicionado listener com debounce de 75ms (`_tabHoverTimerId`) nas abas da barra superior para troca suave entre Periféricos, Antigravity e Ajustes ao passar o cursor.
  - `tests/test_cli_and_applet.py`: testes unitários verificando a lógica de `menuEventFilter`, `calMenu.connect("open-state-changed")` e timers de hover.
- **Validação**: Suíte completa de 31 testes aprovada e navegação contínua por hover validada no Cinnamon Desktop sem vazamento de memória ou eventos órfãos.

### `FEAT-001` — Leitura de Bateria do GameSir Nova Lite via Protocolo HID `0xFF7A` (`2026-11-19`)
- **Severidade**: Funcionalidade Crítica (telemetria de bateria em gamepad sem fio).
- **Causa & Racional Técnico**:
  - Em modo XInput (`3537:1040`), o kernel Linux não expõe nós padrão de bateria em `/sys/class/power_supply` para gamepads genéricos Xbox 360 sem fio.
  - Com base na especificação de engenharia reversa do projeto open-source MIT `krisgfx9/Wireless-Device-Battery-Monitor` (`gamesir.cpp`), identificou-se que o receptor USB da GameSir implementa a Usage Page Vendor `0xFF7A`.
  - O envio de um pacote somente-leitura de 65 bytes (`bytes([0x00, 0x01, 0x01]) + bytes(62)`) ao endpoint `hidraw` apropriado retorna um frame de resposta onde o byte 18 (`r[18]`) indica o percentual exato de carga (`0` a `100`), ou o valor `0xFF` indicando carregamento ativo com conexão USB-C cabeada.
- **Arquivos Modificados**:
  - `src/dpi_core/hardware.py`: adição do método `_read_gamesir_hid_battery(hidraw_nodes, pid)` com filtragem de nós da `3537` (priorizando `0xFF7A` e nós sem subsistema `input`), serialização via `fcntl.flock(LOCK_EX)`, descarte de pacotes assíncronos (`0xF4`), persistência de cache em `gamepad_state.json` e integração com `GamepadDriver.read_state()`.
  - `tests/test_hardware.py`: adição do teste unitário `test_gamesir_hid_battery_0xff7a_reading_and_charging_cache`.
- **Validação**: 32/32 testes aprovados e validação com simulação determinística de frames de resposta.

### `UX-007` — Ícone Customizado de Gamepad Vetorial & Tooltips Individuais na TopBar (`2026-11-19`)
- **Severidade**: Média (ergonomia visual e identificação clara de periféricos na barra do Cinnamon).
- **Causa Raiz**:
  - O applet utilizava o ícone genérico do sistema (`input-gaming-symbolic`) que variava dependendo do tema de ícones do Linux Mint, além de não fornecer informações detalhadas de cada dispositivo ao passar o cursor pela TopBar sem clicar.
- **Arquivos Modificados**:
  - `applet/dynamic-peripheral-island@brendo/icons/dpi-gamepad-symbolic.svg`: criação do asset vetorial SVG simbólico (viewBox `0 0 16 16`, compatível com `St.IconType.SYMBOLIC`) desenhado sob o design system UI/UX Pro Max.
  - `applet/dynamic-peripheral-island@brendo/applet.js`: helper `_makeDeviceIcon` para carregamento dinâmico via `Gio.icon_new_for_string`; importação de `imports.ui.tooltips`; desativação do tooltip global e adição de tooltips contextuais por dispositivo com ciclo de vida rastreado em `this._pillTooltips` (destruição limpa em `_clearPillTooltips` para prevenir vazamentos de memória).
  - `install.sh`: atualização do comando de cópia (`cp -a "${APPLET_SRC}/." "${APPLET_DEST}/"`) para garantir a instalação do diretório `icons/`.
  - `tests/test_cli_and_applet.py`: testes de integridade XML do SVG e verificação da arquitetura de tooltips.
- **Validação**: Suíte completa de testes aprovada, ícone renderizado com sucesso no Cinnamon e tooltips contextuais exibidos ao passar o mouse.

### `BUG-005` — Bloqueio do Hover entre Calendário Nativo e Segmentos da Ilha Dinâmica (`2026-11-19`)
- **Severidade**: Média (quebrava a navegação contínua por hover introduzida na v1.0.5 ao abrir o calendário).
- **Causa Raiz**:
  - Ao abrir o calendário nativo do Cinnamon (`calendar@cinnamon.org`), a sua instância interna de `PopupMenuManager` anexa um listener de captura no `global.stage.connect('enter-event')` e retorna `Clutter.EVENT_STOP`, interceptando e cancelando qualquer sinal de entrada que o applet da ilha tentasse escutar.
- **Arquivos Modificados**:
  - `applet/dynamic-peripheral-island@brendo/applet.js`: substituição do listener passivo de `enter-event` por um timer leve de pooling de cursor `this._calHoverTimerId = GLib.timeout_add(60, ...)` ativado **exclusivamente** durante o estado `calMenu.isOpen === true` (0% de impacto de CPU com o calendário fechado); a cada 60ms, consulta as coordenadas reais do ponteiro via `global.get_pointer()` e testa contenção via `_pointInActor(actor, px, py)` com coordenadas transformadas, fechando o calendário e abrindo o Popover no segmento correspondente de forma instantânea.
  - `tests/test_cli_and_applet.py`: testes cobrindo a presença do monitor `_calHoverTimerId`, `global.get_pointer` e `_pointInActor`.
- **Validação**: Verificação em runtime no Cinnamon Desktop com transição imediata e sem travamentos ao deslizar o mouse entre o Calendário e os segmentos da ilha.

### `BUG-006` — Headset Havit Fuxi H3 Desligado Aparecendo na TopBar (`2026-11-20`)
- **Severidade**: Média (poluição visual na TopBar quando o periférico está inativo).
- **Causa Raiz**:
  - No modo sem fio 2.4GHz, o dongle USB (`040b:0897`) permanece fisicamente plugado ao computador, fazendo com que o driver USB Audio do kernel e o PipeWire mantenham o nó de saída (sink) registrado indefinidamente, atribuindo `connected = True` e `active = True` mesmo com o headset desligado na chave física.
- **Arquivos Modificados**:
  - `src/dpi_core/hardware.py`: aprimoramento de `FuxiHeadsetDriver.read_state()` para checar o estado operacional do sink PipeWire (`sink_state`) e perfil ALSA (`active_profile`); quando o estado for `SUSPENDED` ou perfil `off`, define `active = False` mantendo `connected = True`.
  - `src/dpi_core/cli.py`: o headset só é marcado como `visible = True` na TopBar quando `active == True` (ou `pinned == True`), ocultando-o automaticamente ao ser desligado.
  - `tests/test_hardware.py` e `tests/test_cli_and_applet.py`: testes unitários adicionados para validar a transição `SUSPENDED` -> `active=False` / `visible=False`.
- **Validação**: 34/34 testes aprovados e headset saindo da TopBar em repouso no Cinnamon.

### `FEAT-002` — Telemetria de Bateria e Controles BlueZ para o Havit Fuxi H3 em Modo Bluetooth (`2026-11-20`)
- **Severidade**: Melhoria de Funcionalidade (paridade de recursos no modo Bluetooth).
- **Causa & Racional Técnico**:
  - Quando conectado via Bluetooth (`01:92:25:27:09:76`), o headset expõe telemetria de bateria via serviço BlueZ Battery1 e sink de áudio `bluez_output.*`. Era necessário unificar a leitura de bateria, controle de volume e mute no backend e na UI.
- **Arquivos Modificados**:
  - `src/dpi_core/hardware.py`: leitura robusta de bateria hexadecimal (`0xNN (DD)`) via `bluetoothctl info` e `upower`, seleção automática do card e sink BlueZ em `_match_fuxi_card_and_sink(bt_connected=True)`, com despacho de `set_volume` e `toggle_mute` diretamente no sink BlueZ ativo.
  - `src/dpi_core/cli.py`: formatação combinada na TopBar (`NN% · Vol VV%` ou `NN% · Mudo`) e tooltips contextuais.
  - `applet/dynamic-peripheral-island@brendo/applet.js`: suporte a exibição de bateria na pílula da TopBar e card detalhado no Popover.
- **Validação**: Testes unitários cobrindo decodificação hexadecimal e controle de volume via mock BlueZ aprovados com 100% de sucesso.

### `UX-009` — Deduplicação do Header no Popover Bento Grid (`2026-11-20`)
- **Severidade**: Baixa (limpeza e organização visual da interface).
- **Causa Raiz**:
  - O topo do Popover exibia `Dynamic Island [Pro]` + modelo ativo, e ao abrir a aba `Antigravity VU` havia um card interno repetindo `Antigravity View Usage [Pro]` e `Modelo Ativo: <modelo>`, desperdiçando espaço vertical valioso.
- **Arquivos Modificados**:
  - `applet/dynamic-peripheral-island@brendo/applet.js`: consolidação do cabeçalho unificado com o título do hub, badge de plano `Pro` e rótulo estilizado `Agente Ativo: <modelo>` uma única vez; remoção do card de cabeçalho redundante dentro de `_renderAntigravityTab()`.
- **Validação**: Interface limpa e sem redundâncias em todas as 3 abas.

### `UX-010` — Aba Antigravity VU em Bento Grid de 2 Colunas sem Scrollbar (`2026-11-20`)
- **Severidade**: Média (otimização de layout para visualização completa de telemetria de IA sem rolagem).
- **Causa Raiz**:
  - Na largura padrão de 452px, todos os blocos de telemetria do Antigravity (Cotas, Sessão, Tokens, Swarm e Histograma) ficavam empilhados verticalmente, exigindo rolagem contínua para acompanhar o consumo e o histórico.
- **Arquivos Modificados**:
  - `applet/dynamic-peripheral-island@brendo/applet.js` e `stylesheet.css`: reorganização da aba em Bento Grid de duas colunas paralelas (`_colLeft` com Cotas de Modelos e Pace Marker; `_colRight` com Sessão Ativa, Tokens, Swarm Tracker e Histograma de 7 dias + Resumo Mensal); aplicação dinâmica da classe `.dpi-popover-wide` (680px) com política `vscrollbar_policy = NEVER` na aba Antigravity, restaurando a largura compacta (452px) e scroll automático nas demais abas.
- **Validação**: Testes automatizados e inspeção no Cinnamon confirmando visualização simultânea de todas as métricas sem barra de rolagem.

### `BUG-007` — Overflow da 2ª Coluna e Botão Refresh no Popover Wide de 2 Colunas (`2026-11-20`)
- **Severidade**: Média (quebra de enquadramento visual na aba Antigravity VU).
- **Causa Raiz**:
  - A largura definida na v1.0.7 para o container wide (680px) era insuficiente para acomodar a soma das larguras das duas colunas de cards somada ao espaçamento, padding interno e moldura `.popup-menu`. Como resultado, os cards da coluna direita (`Sessão Ativa & Swarm` e `Histograma 7 Dias & Resumo Mensal`) e o botão `[refresh]` no topo vazavam para fora da borda do Popover.
- **Arquivos Modificados**:
  - `applet/dynamic-peripheral-island@brendo/stylesheet.css`: expansão de `.dpi-popover-wide` para `width: 720px; max-width: 720px;`; definição estrita de `width: 342px;` em `.dpi-ag-col-left` e `.dpi-ag-col-right` com espaçamento de 10px (`342 + 10 + 342 = 694px < 716px` de área útil); ajuste das barras do histograma para 14px com colunas de 36px e espaçamento de 4px para contenção perfeita.
  - `applet/dynamic-peripheral-island@brendo/applet.js`: adição de `St.Widget({ x_expand: true })` entre os badges e o botão `[refresh]` no cabeçalho; título dinâmico responsivo (`Dynamic Island · Antigravity View Usage` em wide / `Dynamic Island · Antigravity VU` em compact); implementação de `_scheduleMenuReposition()` com chamadas a `queue_relayout()` e `GLib.idle_add` para recentralizar o menu no Cinnamon logo após a mudança de tamanho.
  - `tests/test_cli_and_applet.py`: testes unitários adicionados para validar a classe de 720px, larguras das colunas de 342px, histograma contido e rotinas de relayout.
- **Validação**: 34/34 testes aprovados e visualização 100% contida e alinhada sem vazamentos no Cinnamon Desktop.

### `UX-011` — Pílula Compacta do Headset na TopBar (`2026-11-20`)
- **Severidade**: Baixa (refinamento ergonômico e consistência visual).
- **Causa Raiz**:
  - A inclusão do percentual de volume no texto da TopBar (`80% · Vol 100%`) tornava a pílula do headset consideravelmente mais larga do que as dos demais periféricos (mouse e controle), desbalanceando visualmente o segmento de periféricos na barra.
- **Arquivos Modificados**:
  - `src/dpi_core/cli.py` e `applet/dynamic-peripheral-island@brendo/applet.js`: simplificação de `status_text` para exibir exclusivamente a bateria (`80%` ou `80%+`), mantendo o volume no `detail_text`, nos tooltips do Cinnamon e na saída Waybar.
  - `tests/test_cli_and_applet.py`: asserções atualizadas para validar o texto compacto `85%`.
- **Validação**: 34/34 testes aprovados e cápsula da TopBar harmonizada no Cinnamon.

### `BUG-008` — Falso Positivo de Subagentes em Estado WORKING no Swarm Tracker (`2026-11-20`)
- **Severidade**: Média (telemetria incorreta de subagentes ativos no monitor Antigravity VU).
- **Causa Raiz**:
  1. Quando um agente do Swarm conclui seu turno, o step final gravado em `transcript.jsonl` possui `type = "PLANNER_RESPONSE"`, `status = "DONE"` e `tool_calls = []`. O parser anterior considerava qualquer step recente (< 90s) como indicativo de `WORKING`, ignorando a ausência de tools pendentes.
  2. Quando um worker chama `swarm_wait`, o `PLANNER_RESPONSE` é imediatamente sucedido por um step assíncrono `type = "GENERIC"` com a mensagem de espera (`"Waiting for..."`) e `tool_calls = []`. O parser antigo sobrescrevia a lista de tools com a do step genérico, apagando o registro da chamada a `swarm_wait` e mantendo o agente como ativo.
- **Arquivos Modificados**:
  - `src/dpi_core/antigravity.py`: estruturado o rastreamento em `_parse_transcript` para reter `last_planner_had_wait` (resetado apenas se ocorrer novo `USER_INPUT`), `last_is_wait_output` e `last_planner_tools`; redefinida a heurística de `IDLE` imediato para turnos encerrados sem tools, esperas em `swarm_wait` ou inatividade superior a 45s; introduzido `schema_version = 2` para invalidação imediata do cache `antigravity_index.json`.
  - `tests/test_antigravity.py`: novo teste unitário `test_swarm_subagent_idle_vs_working_states_bug_008` validando a transição determinística para `IDLE` e `WORKING`.
- **Validação**: 35/35 testes unitários aprovados e contagem exata de agentes ativos no Swarm verificada em runtime real via `dpi-hub --island-json`.

### `FEAT-003` / `BUG-010` — Gestão Determinística de Estados do Mouse AJAZZ AJ179 V2 (`active` / `sleep` / `off`) (`2026-11-20`)
- **Severidade**: Média (precisão no status de conectividade do mouse e limpeza visual da TopBar).
- **Causa & Racional Técnico**:
  - Quando o mouse sem fio AJAZZ entra em standby ou é desligado fisicamente, o dongle 2.4GHz USB (`249a:5c2f`) permanece conectado ao PC. O driver anterior mantinha o mouse visível como conectado com status residual.
  - No frame de resposta `CMD_INFO` (`0x10`), o byte 14 indica se o rádio do sensor está online (`0x01`) ou offline (`0x00`).
  - Foi implementado um modelo de 3 estados de energia: `active` (quando `live_ok = True` e online), `sleep` (quando offline por até 180s, indicando modo de descanso) e `off` (quando offline por mais de 180s ou com o dongle desconectado).
- **Arquivos Modificados**:
  - `src/dpi_core/hardware.py`: persistência de `offline_since` em `mouse_state.json`; cálculo de `power_state` em `AjazzMouseDriver.read_state()` mantendo 100% de leitura passiva e zero escritas HID (`safe_mode`).
  - `applet/dynamic-peripheral-island@brendo/icons/dpi-mouse-sleep-symbolic.svg`: novo ícone vetorial SVG simbolizando modo de descanso.
  - `src/dpi_core/cli.py` e `applet/dynamic-peripheral-island@brendo/applet.js`: ocultação automática na TopBar (`visible = False`) quando `power_state == "off"`; exibição com ícone de repouso e tom suave (`muted`) quando em `sleep`.
  - `tests/test_hardware.py` e `tests/test_cli_and_applet.py`: testes unitários adicionados cobrindo os 3 estados.
- **Validação**: Testes unitários aprovados e comportamento em runtime validado ao vivo.

### `BUG-009` — Visibilidade dos Badges de LEDs do Teclado K500 & Fallback Passivo (`2026-11-20`)
- **Severidade**: Baixa (estética e feedback de digitação).
- **Causa Raiz**:
  1. A regra CSS `.dpi-theme-dark .dpi-kbd-badge` possuía especificidade superior (0,2,0) em relação a `.dpi-kbd-badge-on` (0,1,0), sobrescrevendo a cor de ativação e fazendo com que os badges `CAPS`, `NUM` e `SCROLL` permanecessem apagados mesmo quando a tecla estava ligada.
  2. Em algumas distribuições ou sessões X11 sem nós sysfs mapeados para LEDs, a leitura retornava sempre desligada.
- **Arquivos Modificados**:
  - `applet/dynamic-peripheral-island@brendo/stylesheet.css`: adição das regras `.dpi-theme-dark .dpi-kbd-badge.dpi-kbd-badge-on` e `.dpi-theme-light .dpi-kbd-badge.dpi-kbd-badge-on` com destaque vibrante.
  - `src/dpi_core/hardware.py`: adição de `_read_leds_from_xset()` utilizando `xset q` (LED mask) como fallback seguro e passivo (100% Safe Mode).
  - `tests/test_cli_and_applet.py` e `tests/test_hardware.py`: testes cobrindo a especificidade CSS e o fallback do `xset q`.
- **Validação**: 37/37 testes aprovados e badge de `NUML` acendendo claramente no Popover.

### `UX-012` — Popover Sempre Centralizado na TopBar (`2026-11-20`)
- **Severidade**: Baixa (alinhamento visual e previsibilidade espacial da interface).
- **Causa Raiz**:
  - A troca dinâmica de `sourceActor` para `_segPeripherals` ou `_segAntigravity` fazia com que o Popover mudasse sua posição horizontal dependendo do segmento clicado.
- **Arquivos Modificados**:
  - `applet/dynamic-peripheral-island@brendo/applet.js`: fixação de `this.menu.sourceActor` exclusivamente no centro da ilha (`_unifiedCenterBox || _calendarActor || actor`), garantindo ancoragem estável no centro do painel superior.
  - `tests/test_cli_and_applet.py`: asserção validando a fixação de `sourceActor`.
- **Validação**: Abertura do Popover rigorosamente centralizada em todos os cliques e hovers.

### `UX-013` — Sincronização Tipográfica Dinâmica na TopBar (`2026-11-20`)
- **Severidade**: Baixa (conformidade com configurações de acessibilidade e fontes do sistema).
- **Causa Raiz**:
  - O tamanho fixo de `font-size: 11px;` impedia que os rótulos da TopBar acompanhassem alterações na escala de fontes do painel e do relógio nativo (`calendar@cinnamon.org`).
- **Arquivos Modificados**:
  - `applet/dynamic-peripheral-island@brendo/stylesheet.css`: substituição por `font-size: 1em;` em `.dpi-pill-text` e `.dpi-morph-text`.
  - `tests/test_cli_and_applet.py`: teste validando o uso de `1em`.
- **Validação**: Herança perfeita do dimensionamento da fonte em runtime no Cinnamon.

### `FEAT-004` — Mixer de Áudio Completo com Controle por Aplicativo (Inspirado no Volum) (`2026-11-20`)
- **Severidade**: Nova Feature Principal (ecossistema de áudio integrado na Ilha).
- **Causa & Racional Técnico**:
  - No desktop Linux, o usuário frequentemente precisa ajustar o volume de aplicativos individuais (Spotify, navegadores, jogos), alternar entre saídas de áudio (headset, caixas de som, monitor) e mutar o microfone sem precisar abrir o painel de configurações do sistema.
  - Inspirando-se na experiência moderna do aplicativo `Volum` (`esdrasstm/Volum`), desenvolveu-se o `AudioMixerManager` em Python 3 stdlib puro via `pactl`, respeitando a política estrita de zero dependências externas de `AGENTS.md`.
- **Arquivos Modificados**:
  - `src/dpi_core/audio.py`: criação da classe `AudioMixerManager` com leitura de `pactl list sinks`, `pactl list sources` (filtrando `.monitor`) e `pactl list sink-inputs`; métodos de controle de volume Master, microfone, seleção de saída/entrada padrão e controle individual de volume e mudo por aplicativo com clampeamento seguro em 0..150%.
  - `src/dpi_core/cli.py`: integração no payload `--island-json` e adição das flags CLI de controle de áudio (`--set-master-volume`, `--toggle-master-mute`, `--set-default-sink`, `--set-mic-volume`, `--toggle-mic-mute`, `--set-default-source`, `--set-app-volume`, `--toggle-app-mute`).
  - `tests/test_audio.py`: testes unitários determinísticos cobrindo o parsing de pactl e despacho de comandos.
- **Validação**: Testes automatizados aprovados e integração com o PipeWire real validada ao vivo no Linux Mint.

### `FEAT-005` — Central de Controle de Mídia com Spotify e MPRIS2 Nativo (`2026-11-20`)
- **Severidade**: Nova Feature Principal (integração multimídia na TopBar).
- **Causa & Racional Técnico**:
  - Permitir controle de reprodução musical e visualização de metadados em tempo real diretamente na Ilha Dinâmica, sem janelas flutuantes extras.
  - Implementado o `MediaPlayerManager` utilizando comunicação D-Bus via utilitário `gdbus` (padrão em sistemas GLib/GNOME/Cinnamon), consumindo a interface MPRIS2 (`org.mpris.MediaPlayer2.Player`).
- **Arquivos Modificados**:
  - `src/dpi_core/audio.py`: criação da classe `MediaPlayerManager` e parser GVariant nativo stdlib (`parse_gvariant`), priorizando o Spotify e extraindo título, artista, álbum, duração, posição atual e porcentagem de progresso, com comandos de transporte (`play_pause`, `next_track`, `previous_track`).
  - `src/dpi_core/cli.py`: inclusão do objeto `media` no JSON e novas flags CLI (`--media-play-pause`, `--media-next`, `--media-prev`, `--media-player`).
  - `tests/test_audio.py`: testes unitários para o parser GVariant, listagem de players e despacho de transporte.
- **Validação**: Spotify ativo detectado com precisão e controle de faixas verificado em runtime.

### `UX-014` — Nova Aba Áudio no Popover Bento Grid, Estética LiquidGlass e Transições Fluidas (`2026-11-20`)
- **Severidade**: Melhoria Visual e Arquitetura de Interface.
- **Causa Raiz & Solução**:
  - A adição de controles de som e mídia exigia uma aba dedicada com visual moderno e de alta fidelidade para não sobrecarregar a aba de Periféricos.
  - O Popover foi expandido para 4 abas (`Periféricos` | `Áudio` | `Antigravity VU` | `Ajustes`), com largura de 480px nas abas regulares e 720px na aba ampla de Antigravity.
  - Implementada a estética **LiquidGlass** com superfícies translúcidas em camadas (`rgba(38, 40, 54, 0.82)`), bordas especulares reflexivas (`rgba(255, 255, 255, 0.14)`), realce glow na aba ativa e transições espaciais fluidas combinando escala (`0.98 -> 1.0`), translação direcional e interpolação exponencial (`EASE_OUT_EXPO`) sem travamentos.
- **Arquivos Modificados**:
  - `applet/dynamic-peripheral-island@brendo/applet.js`: métodos `_renderAudioTab()`, `_buildMediaPlayerCard()`, `_buildAudioMixerCard()` e `_buildPerAppAudioCard()`; transições aprimoradas em `_switchTab()`.
  - `applet/dynamic-peripheral-island@brendo/stylesheet.css`: classes e tokens LiquidGlass, botões de transporte arredondados e estilos da aba de áudio (200 regras balanceadas, zero `font-family`).
  - `tests/test_cli_and_applet.py`: testes unitários cobrindo a aba de áudio, métodos de renderização e tokens CSS.
- **Validação**: 44/44 testes aprovados, reload instantâneo no Cinnamon em 317ms sem erros no `~/.xsession-errors`.

### `UX-015` — Morphing Fluido LiquidGlass com Expansão Centralizada e Cadência Sedosa (`2026-11-20`)
- **Severidade**: Aprimoramento de Fluidez de Animação e Microinteração.
- **Causa Raiz & Solução**:
  - Ao alternar entre abas compactas (`480px`, como `Periféricos` ou `Áudio`) e a aba ampla de `Antigravity VU` (`720px`), a largura do Popover sofria alteração brusca em um único frame, rompendo a ilusão de continuidade do LiquidGlass. Além disso, a curva anterior `EASE_OUT_EXPO` em 240ms era excessivamente rápida.
  - Foi introduzido o morphing dinâmico contínuo de largura (`_popoverRoot.ease({ width: targetW, duration: 420, mode: Clutter.AnimationMode.EASE_OUT_QUINT })`) combinado com a interpolação no eixo horizontal da posição do menu (`this.menu.actor.ease({ x: Math.round(oldX - (targetW - oldW) / 2), duration: 420, mode: Clutter.AnimationMode.EASE_OUT_QUINT })`). Dessa forma, a janela expande e contrai concentricamente a partir do centro da Ilha Dinâmica.
  - A cadência de transição de abas e expansão de cards foi suavizada para `420ms` / `300ms` com `EASE_OUT_QUINT`, e o `transition-duration` das classes CSS de cards, abas e chips foi unificado em `320ms`.
- **Arquivos Modificados**:
  - `applet/dynamic-peripheral-island@brendo/applet.js`: lógica de morphing de largura e cálculo de offset `x` em `_switchTab()`; cadência de `420ms` / `300ms` com `EASE_OUT_QUINT` em `_bodyStack` e `_animateCardBody()`; sincronização em `_syncPopoverWidth()`.
  - `applet/dynamic-peripheral-island@brendo/stylesheet.css`: unificação de `transition-duration: 320ms;` nas classes temáticas.
  - `tests/test_cli_and_applet.py`: asserções de validação para `EASE_OUT_QUINT`, `duration: 420` e `transition-duration: 320ms`.
- **Validação**: 44/44 testes aprovados, reload no Cinnamon em 309ms com transição perfeitamente sedosa e contínua sem saltos visuais.

### `UX-016` — Bento Grid 2 Colunas Unificado em 700px nas 4 Abas + Transição 100% GPU sem Flash em Branco (`2026-11-20`)
- **Severidade**: Alta (otimização de renderização, consistência espacial e eliminação de artefatos visuais).
- **Causa Raiz & Análise Frame-a-Frame**:
  - A análise de gravação de tela revelou três problemas:
    1. A interpolação de largura na CPU forçava o compositor Clutter a recalcular o layout de todos os nós a cada frame, gerando jitter e pequenos saltos laterais no popup.
    2. Iniciar a transição com `opacity = 0` fazia o corpo do Popover piscar em branco por ~200ms antes do fade-in da nova aba.
    3. Na aba `Áudio`, o layout em coluna única causava corte vertical do mixer de aplicativos e ativava barras de rolagem indesejadas.
- **Solução Arquitetural**:
  - Padronização da largura do Popover em **700px fixos** em todas as 4 abas, utilizando Bento Grid de 2 colunas com colunas equilibradas de 336px (`.dpi-bento-col`). Com isso, o Popover permanece imóvel e perfeitamente ancorado ao centro da Ilha Dinâmica, sem qualquer alteração dimensional na CPU.
  - Na aba `Áudio`, o player Spotify/MPRIS2 e o mixer de apps ficam na coluna esquerda, enquanto Master e Microfone ocupam a coluna direita, eliminando barras de rolagem vertical.
  - Transição entre abas 100% executada na GPU via `_bodyStack.ease`: início em `opacity: 150` (eliminando completamente o flash em branco), com `scale: 0.99` e `translation_x: dir * 16`, animando para `opacity: 255`, `scale: 1.0` e `translation_x: 0` em `280ms` com `Clutter.AnimationMode.EASE_OUT_CUBIC` a 60 FPS reais.
  - Debounce de alternância por hover no TabBar estendido para `110ms` (`_tabHoverTimerId`).
- **Arquivos Modificados**:
  - `applet/dynamic-peripheral-island@brendo/applet.js`: layout Bento Grid de 2 colunas em todas as 4 abas, remoção da animação de largura/eixo X, transição de GPU sem flash (`opacity: 150`), debounce de hover de 110ms e redimensionamento das barras de progresso para `PROGRESS_TRACK_WIDTH = 290;`.
  - `applet/dynamic-peripheral-island@brendo/stylesheet.css`: fixação de `.dpi-popover-root` e `.dpi-popover-wide` em `700px`, e colunas em `336px` (202 regras CSS balanceadas).
  - `tests/test_cli_and_applet.py`: testes unitários atualizados para `700px`, `280ms`, `EASE_OUT_CUBIC` e `opacity: 150`.
- **Validação**: 44/44 testes aprovados, recarregamento no Cinnamon via D-Bus em 819ms com zero `JS ERROR` e zero `St-WARNING`.

### `FEAT-006` — Estágio Intermediário Notchy Peek Inspirado no notchy.dev (`2026-11-20`)
- **Severidade**: Nova Feature Principal (microinteração progressiva em 3 estágios).
- **Causa & Racional Técnico**:
  - Abrir o Popover Bento Grid completo (700px) apenas para pausar uma música no Spotify ou verificar a cota Antigravity é excessivo para tarefas rápidas.
  - Inspirando-se no conceito moderno de ilha/notch do `notchy.dev`, implementou-se o **Notchy Peek** (`this._peekActor`) como um estágio intermediário de 480px montado em `Main.uiGroup`, proporcionando acesso imediato aos controles mais frequentes antes da expansão completa.
- **Arquivos Modificados**:
  - `applet/dynamic-peripheral-island@brendo/applet.js`: métodos `_initNotchPeek()`, `_showNotchPeek()`, `_hideNotchPeek()`, `_buildPeekMediaSegment()` e `_buildPeekAntigravitySegment()`; descida animada suave em 260ms com `EASE_OUT_CUBIC` após 220ms de hover contínuo no Notch, grace timer de 240ms e recolhimento em 200ms; botão de expansão total para o Popover completo; ciclo de vida com remoção explícita de `Main.uiGroup` em `on_applet_removed_from_panel()`.
  - `applet/dynamic-peripheral-island@brendo/stylesheet.css`: classes `.dpi-notch-peek` com `border-radius: 0 0 18px 18px;`, fundo escuro LiquidGlass (`rgba(16, 18, 28, 0.92)`) e sombra profunda.
  - `tests/test_cli_and_applet.py`: testes unitários validando a criação, métodos de controle e descarte de `_peekActor`.
- **Validação**: Testes automatizados aprovados e comportamento de hover/peek fluido verificado no Cinnamon.

### `UX-017` — Estética Apple Notch na TopBar e Tooltips Animados LiquidGlass (`2026-11-20`)
- **Severidade**: Refinamento Visual e Acessibilidade.
- **Causa Raiz & Solução**:
  - A cápsula anterior utilizava cantos arredondados simétricos em todos os lados (`6px` ou pílula inteira), distanciando-se visualmente do conceito de ilha ancorada no topo do monitor.
  - A cápsula da TopBar foi redesenhada no formato característico do **Apple Notch**: topo plano colado na borda superior (`0 0`) e cantos arredondados na base inferior (`14px 14px`).
  - Substituição dos tooltips estáticos por tooltips animados LiquidGlass flutuantes (`this._tooltipActor`, `.dpi-glass-tooltip`) com animação fluida multieixo (180ms de fade/scale/slide) e algoritmo anti-colisão inteligente que evita qualquer sobreposição com o Notchy Peek.
- **Arquivos Modificados**:
  - `applet/dynamic-peripheral-island@brendo/stylesheet.css`: regras de recorte `.dpi-unified-capsule` e `.dpi-standalone-capsule` (`border-radius: 0 0 14px 14px; margin-top: 0;`), e estilos de `.dpi-glass-tooltip`.
  - `applet/dynamic-peripheral-island@brendo/applet.js`: `_initGlassTooltip()`, `_showAnimatedTooltip()`, `_hideAnimatedTooltip()` e posicionamento anti-colisão (`peekBottom + 6px`).
  - `tests/test_cli_and_applet.py`: asserções de validação CSS e métodos de tooltip.
- **Validação**: 44/44 testes aprovados, applet recarregado em 324ms sem alertas no `~/.xsession-errors`.

---

## 5. Procedimentos de Rollback

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

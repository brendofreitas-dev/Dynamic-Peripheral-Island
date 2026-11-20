# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e este projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [1.0.7] - 2026-11-20

### Corrigido
- **BUG-006 (Ocultação Automática do Headset Desligado na TopBar)**:
  - `FuxiHeadsetDriver` (`src/dpi_core/hardware.py`): no modo 2.4GHz com o dongle USB plugado, o headset desligado no botão físico mantinha o sink ALSA/PipeWire criado. Agora o driver inspeciona o estado do sink (`sink_state == "SUSPENDED"` ou perfil `"off"`), marcando `active = False` quando o headset está inativo e preservando `connected = True` apenas no Popover (evitando poluição na TopBar).

### Adicionado
- **FEAT-002 (Telemetria de Bateria e Controles BlueZ para o Havit Fuxi H3)**:
  - `FuxiHeadsetDriver` (`src/dpi_core/hardware.py`): suporte completo ao modo Bluetooth (`01:92:25:27:09:76`), com decodificação de percentual de bateria hexadecimal via `bluetoothctl` e `upower`, seleção automática do sink BlueZ (`bluez_output.*`), e controle de volume/mudo.
  - `src/dpi_core/cli.py`: exibição combinada de bateria e volume na TopBar (`85% · Vol 70%` ou `85% · Mudo`) e tooltips informativos sem emojis.
- **UX-009 (Deduplicação do Header no Popover Bento Grid)**:
  - `applet/dynamic-peripheral-island@brendo/applet.js`: consolidação do cabeçalho superior unificado exibindo `Dynamic Island · Antigravity View Usage [Pro]` e o indicador `Agente Ativo: <modelo>` uma única vez, eliminando o card de boas-vindas redundante dentro da aba Antigravity.
- **UX-010 (Aba Antigravity VU em Bento Grid 2 Colunas sem Scrollbar)**:
  - `applet/dynamic-peripheral-island@brendo/applet.js` e `stylesheet.css`: redesenhada a aba Antigravity VU em layout de duas colunas paralelas (Cotas e Pace Marker à esquerda; Sessão Ativa, Swarm e Histograma 7 dias à direita).
  - Expansão dinâmica de largura para 680px (`.dpi-popover-wide`) com centralização automática abaixo da ilha e desativação de rolagem vertical (`vscrollbar_policy = NEVER`), retornando à largura compacta padrão (452px) nas outras abas.

## [1.0.6] - 2026-11-19

### Adicionado
- **FEAT-001 (Leitura de Bateria do GameSir Nova Lite via HID `0xFF7A`)**:
  - `GamepadDriver` (`src/dpi_core/hardware.py`): implementado o método `_read_gamesir_hid_battery` baseado na especificação do projeto open-source `krisgfx9/Wireless-Device-Battery-Monitor`.
  - Envio de frame de 65 bytes (`00 01 01`), descarte de frames assíncronos (`0xF4`), decodificação de `r[18]` (percentual de 0 a 100%) e detecção de status de carregamento (`r[18] == 0xFF`) com persistência em cache (`gamepad_state.json`).
  - Suporte estendido aos PIDs `1040` (XInput), `1041` (HID/DInput), `1098` e `100f`.
- **UX-007 (Ícone Customizado de Gamepad Vetorial & Tooltips Individuais na TopBar)**:
  - Criado o arquivo vetorial `icons/dpi-gamepad-symbolic.svg` com silhueta ergonômica de controle moderno, compatível com `St.IconType.SYMBOLIC`.
  - Implementados tooltips contextuais por dispositivo via `Tooltips.Tooltip` na TopBar com ciclo de vida gerenciado em `_pillTooltips` (exibindo nome do modelo, tipo de conexão, nível de bateria, DPI no mouse, volume no headset e status do Antigravity/Swarm).
  - Atualizado `install.sh` para copiar recursivamente o diretório de ícones para o diretório de destino do Cinnamon.

### Corrigido
- **BUG-005 (Hover de Data/Hora de Volta para Periféricos ou Antigravity)**:
  - `applet/dynamic-peripheral-island@brendo/applet.js`: contornado o bloqueio de eventos causado pelo `PopupMenuManager` do Calendário ao abrir (`calendar@cinnamon.org`), implementando um monitor leve `_calHoverTimerId` (60ms) ativo exclusivamente enquanto o calendário está aberto, usando `global.get_pointer()` e `_pointInActor` para fechar o calendário e abrir o segmento correspondente da Ilha Dinâmica de forma contínua e sem travamentos.

## [1.0.5] - 2026-11-19

### Corrigido
- **BUG-004 (Detecção do GameSir Nova Lite em 2.4GHz XInput `3537:1040`)**:
  - `GamepadDriver` (`src/dpi_core/hardware.py`): ampliado o suporte para múltiplos PIDs ativos da VID `3537` (`GAMESIR_ACTIVE_PIDS = frozenset({"1040", "1041"})`), reconhecendo a mudança física de PID do dongle de `2106` (standby) para `1040` no modo XInput 2.4GHz.
  - Priorização estrita do nó primário de controle (com handler `js*` e `ff_supported == True`), descartando a interface auxiliar `Keyboard` (`event14`).
  - Ativação imediata no pareamento (`active = True`), sem exigir clique prévio na janela de 60s, e descrição exata da conexão (`2.4GHz (XInput)`).

### Adicionado
- **UX-005 (Auto-exibição de Dispositivos Ativos na TopBar)**:
  - `src/dpi_core/cli.py`: periféricos sem fio ativos (`active == True`) ou carregando (`charging == True`) são automaticamente exibidos na cápsula da TopBar (`visible = True`) assim que são ligados.
  - Para gamepads sem leitura percentual de bateria no protocolo XInput, implementado rótulo contextual dinâmico (`GameSir`, `EasySMX` ou `Nx`) com indicador de carga (`+`).
- **UX-006 (Troca Fluida por Hover com Menus Abertos)**:
  - `applet/dynamic-peripheral-island@brendo/applet.js`: quando o Popover da ilha estiver aberto, passar o cursor por cima dos outros elementos centrais da TopBar alterna instantaneamente a visualização (Periféricos ↔ Antigravity ou fecha a ilha e abre o menu nativo do `calendar@cinnamon.org`).
  - Quando o menu do Calendário nativo estiver aberto, passar o mouse sobre Periféricos ou Antigravity fecha o calendário e abre suavemente a aba correspondente da ilha.
  - Dentro do Popover, passar o mouse sobre as abas (`Periféricos` | `Antigravity VU` | `Ajustes`) realiza a troca automática debounced em 75ms.

## [1.0.4] - 2026-11-19

### Corrigido
- **BUG-003 (Clique no Segmento Esquerdo de Periféricos que Fechava no `BUTTON_RELEASE`)**:
  - Implementado o método oficial `menuEventFilter(event)` do Cinnamon em `DynamicPeripheralIslandApplet` (`applet/dynamic-peripheral-island@brendo/applet.js`) para interceptar `Clutter.EventType.BUTTON_RELEASE` e `Clutter.EventType.BUTTON_PRESS` originados em `this._leftSlot` / `this._segPeripherals` (que residem fora de `this.actor`), impedindo que `PopupMenuManager._onEventCapture` fechasse o menu ao soltar o botão esquerdo do mouse.
  - Atualização dinâmica de `this.menu.sourceActor` em `_openTabFromSegment(tabName)` para o segmento clicado (`_segPeripherals` ou `_segAntigravity`), alinhando o Popover diretamente abaixo do segmento ativo e restaurando `this.menu.sourceActor = this.actor` no unload.

### Alterado
- **Remoção do Pipe Vertical (`|`) na TopBar**:
  - Ocultado `this._midDivider` (`this._midDivider.hide()`) em `_buildTopBar()`, eliminando a linha divisória vertical entre a Data/Hora e o VU do Antigravity.
- **UX-003 (Visual e Paleta Idênticos ao Calendário Nativo do Cinnamon)**:
  - Removido o wrapper `PopupMenu.PopupBaseMenuItem` em `_buildPopover()`, anexando `this._popoverRoot` diretamente via `this.menu.addActor(this._popoverRoot)` (mesmo padrão do `calendar@cinnamon.org`) para eliminar a borda/caixa dupla.
  - Harmonizada toda a paleta dark de `stylesheet.css` com o calendário nativo do tema Cinnamon: `.dpi-popover-root` transparente sobre a moldura `.popup-menu`, cards/abas/tiles em `#282a36` com borda `1px solid rgba(25, 26, 34, 0.9)` e `border-radius: 4px`, subcards/linhas em `#232530`, botões/chips em `#2c2f3c` (hover `#373a4b`), estados ativos em `rgba(189, 147, 249, 0.5)` e trilhas de barra em `#191a22`.
- **UX-004 (Transições Fluidas entre Abas e Cards)**:
  - Implementado `_switchTab(newTabId, animate = true)` animando `this._bodyStack.ease({ opacity: 255, translation_x: 0, duration: 180, mode: Clutter.AnimationMode.EASE_OUT_CUBIC })` com deslocamento direcional (`dir * 14px`).
  - Adicionado `_animateCardBody(body, cardKey)` para animar a expansão de cards de periféricos (`translation_y: -6 -> 0`, `160ms`, `EASE_OUT_QUAD`) e verificação de `payloadHash` em `_refreshNow()` para evitar re-renderizações desnecessárias quando o Popover está aberto.

## [1.0.3] - 2026-11-19

### Adicionado
- **Layout Centralizado `[ Periféricos | Data e Hora | Antigravity ]` (`applet/dynamic-peripheral-island@brendo/applet.js`)**:
  - Implementado container `_leftSlot` inserido à esquerda do relógio do sistema (`calendar@cinnamon.org`) no painel central via `centerBox.insert_child_below(this._leftSlot, calendarActor)`.
  - Posicionamento orgânico com Periféricos à esquerda da Data/Hora e Antigravity + Morphing Pill à direita em `this.actor`, sem reparentar nem corromper instâncias de applets vizinhos.
  - Limpeza completa no ciclo de vida (`_detachUnifiedCapsule` e `on_applet_removed_from_panel`), prevenindo memory leaks e nós órfãos em reloads do Cinnamon.

### Alterado
- **UX-002 (Dynamic Island Hover-Only & Transparência em Idle)**:
  - Cápsula central (`.dpi-unified-capsule`) configurada com transparência total em estado de repouso/idle (`background-color: transparent`, `border: 1px solid transparent`, `box-shadow: none`).
  - Efeito hover dinâmico ativado ao passar o mouse por qualquer um dos 3 elementos (Periféricos, Data/Hora ou Antigravity), aplicando `.dpi-capsule-hovered` no container com debounce de 80ms no leave para navegação contínua e sem piscar.
  - Sincronização automática com `.dpi-capsule-open` quando o Popover Bento Grid ou um alerta morphing estiver ativo, garantindo visibilidade suave e consistente.
  - Remoção definitiva de resquícios de fundo azul, utilizando tons suaves de glassmorphism (`rgba(40, 42, 54, 0.90)` no dark e `rgba(248, 250, 252, 0.92)` no light com bordas sutis).
- **Recarga Automatizada do Tema (`install.sh`)**:
  - Adicionada a chamada D-Bus `org.Cinnamon.ReloadTheme` antecedendo `org.Cinnamon.ReloadXlet`, garantindo que atualizações de classes e estilos em `stylesheet.css` entrem em vigor instantaneamente no compositor Muffin.

## [1.0.2] - 2026-11-19

### Corrigido
- **BUG-002 (Clique no Antigravity & Fonte do Sistema no Applet Cinnamon)**:
  - Corrigido o evento de clique nos segmentos da TopBar (`applet/dynamic-peripheral-island@brendo/applet.js`): migrado de `button-release-event` para `button-press-event` em `_segPeripherals`, `_segAntigravity` e `_morphPill` com retorno `Clutter.EVENT_STOP` no botão 1, eliminando o conflito com a interceptação antecipada por `on_applet_clicked`.
  - Adicionada verificação defensiva de origem (`event.get_source()`) em `on_applet_clicked` para rotear diretamente para as abas `"antigravity"` ou `"peripherals"` se o evento atingir os respectivos containers.
  - Removidos todos os overrides `font-family: Monospace;` e `font-family: Sans;` de `stylesheet.css`, garantindo que o applet herde de forma estável a fonte configurada no sistema operacional (`Lexend 10`), sem alternâncias indesejadas de família tipográfica ao interagir com a interface.

### Alterado
- **UX-001 (Estética da TopBar & Hover Nativo SystemTray)**:
  - Removido o container de fundo azul escuro (`rgba(15, 23, 42, 0.84)`) e `border-radius: 999px` de `.dpi-unified-capsule` e `.dpi-capsule-segment`.
  - Aplicada a classe CSS nativa Cinnamon `.applet-box` em cada segmento clicável da cápsula com `border-radius: 6px` e chamada `this.actor.remove_style_class_name("applet-box")` no ator raiz do applet para prevenir borda externa duplicada.
  - Removidas as regras customizadas de hover azul/slate, delegando ao seletor nativo `.applet-box:hover` do tema ativo do Cinnamon o controle da cor e da transparência de hover, mantendo a geometria retangular com cantos arredondados de `6px` idêntica aos ícones da bandeja do sistema (`systray@cinnamon.org`).
  - Atualizados os seletores de segmento ativo e destaques secundários para tons neutros e violeta suave (`rgba(189, 147, 249, 0.35)` no modo escuro e `rgba(0, 0, 0, 0.12)` no modo claro).

### Governança
- **Migração do Swarm para Gemini 3.8 Flash (High)**: Todos os workers do Swarm (`island-ui`, `test-verifier`, `hw-engine`, `ag-engine`, `design-docs`, `docs-git`) migrados para `Gemini 3.8 Flash (High)` por solicitação do usuário.
- **Agente `docs-git`**: Criação formal do agente responsável por documentação contínua, governança e Conventional Commits (`.agents/agents/docs-git.md`).

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

# Governança e Regras de Engenharia (`AGENTS.md`)

Este documento define as regras obrigatórias de governança, segurança de hardware, qualidade de código e fluxo de trabalho para qualquer agente ou contribuidor que atue no repositório **Dynamic Peripheral Island**.

---

## 1. Princípios Fundamentais

1. **Zero Dependências Externas no Core**:
   - Todo o backend (`src/dpi_core/` e `bin/dpi-hub`) deve ser escrito exclusivamente em **Python 3 stdlib** (`os`, `fcntl`, `select`, `struct`, `subprocess`, `json`, `urllib`, `time`, `pathlib`, `re`, `errno`, `argparse`).
   - Não introduza pacotes de terceiros (`pip`) no core de telemetria ou CLI.
2. **UI/UX Pro Max & Estética Limpa**:
   - O applet Cinnamon (`applet/dynamic-peripheral-island@brendo/`) segue o Design System persistido em [`design-system/dynamic-peripheral-island/MASTER.md`](file:///home/brendo/Projetos/Dynamic-Peripheral-Island/design-system/dynamic-peripheral-island/MASTER.md).
   - **Proibido emojis estruturais** na interface gráfica ou no terminal padrão: utilize ícones simbólicos SVG (`St.Icon`) e tipografia limpa (`Fira Sans` / `Fira Code`).
3. **Execução 100% Assíncrona na TopBar**:
   - O applet CJS nunca deve bloquear o loop principal do Cinnamon (`Main.panel`). Toda chamada a `dpi-hub` deve usar `Gio.Subprocess` assíncrono.

---

## 2. Regra Crítica: Hardware Safe Mode (Machenike K500-B94)

> ⚠️ **AVISO DE RISCO DE HARDWARE**: O teclado **Machenike K500-B94** (VID `258a`, PID `0049`) utiliza uma MCU **Sino Wealth**. O envio de frames HID brutos vazios, compostos apenas por zeros ou fora do formato esperado pode corromper o estado do controlador e travar o teclado em modo bootloader.

Regras inegociáveis para qualquer alteração em `K500KeyboardDriver`:
- **Modo Somente Leitura por Padrão (`safe_mode=True`)**: Nenhuma escrita HID ativa é permitida na MCU do K500 sem revisão formal e protocolo validado.
- **Validação Estrita de Frames (`validate_hid_frame`)**: Qualquer tentativa de validar ou enviar pacotes deve rejeitar explicitamente (`ValueError`) frames vazios, compostos apenas de `0x00`, ou fora dos tamanhos válidos.
- **Bloqueio de Escrita (`send_raw_packet`)**: Deve recusar qualquer escrita enquanto `safe_mode` estiver ativo (lançando `RuntimeError`).
- Toda alteração nessa classe exige validação imediata pelos testes de segurança em `tests/test_hardware.py`.

---

## 3. Separação de Responsabilidades por Camada

| Camada | Diretórios / Arquivos | Responsabilidade |
| :--- | :--- | :--- |
| **Hardware Drivers** | `src/dpi_core/hardware.py`, `udev/99-dynamic-peripheral-island.rules` | Comunicação HID/ALSA/evdev/Bluetooth/sysfs e regras de permissão `udev`. Não conhece UI nem Antigravity. |
| **Antigravity & CLI** | `src/dpi_core/antigravity.py`, `src/dpi_core/cli.py`, `bin/dpi-hub` | Descoberta do daemon LanguageServer, ConnectRPC, parsing incremental de transcripts, persistência de `settings.json` e saída JSON/Waybar/Terminal. |
| **Island UI (CJS)** | `applet/dynamic-peripheral-island@brendo/*`, `install.sh`, `uninstall.sh` | Cápsula unificada na TopBar do Cinnamon, Popover Bento Grid, animações (`actor.ease`), tema adaptativo e instaladores. |
| **Design System & Docs** | `design-system/*`, `README.md`, `CHANGELOG.md`, `PRODUCTLOG.md`, `ROADMAP.md`, `AGENTS.md`, `docs/ARCHITECTURE.md` | Tokens DTCG/CSS, especificações visuais, documentação técnica e registro de decisões. |
| **Qualidade & Verificação** | `tests/test_*.py` | Suíte `unittest` com mocks determinísticos de hardware, rede e sistema de arquivos. |

---

## 4. Exigência de Testes Antes de Releases

Nenhuma release, tag ou merge para a branch principal é permitida sem que:
1. Todos os arquivos Python passem em `python3 -m py_compile`.
2. A suíte completa execute com **100% de aprovação** via:
   ```bash
   python3 -m unittest discover -s tests -v
   ```
3. A sintaxe do `applet.js` e a integridade do `stylesheet.css` e da documentação estejam validadas.
4. Em ambiente desktop Cinnamon, `dpi-hub --island-json`, `dpi-hub --waybar` e `dpi-hub --pretty` produzam saídas válidas sem exceções não tratadas.

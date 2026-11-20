# Roadmap — Dynamic Peripheral Island

Este documento descreve a evolução planejada do **Dynamic Peripheral Island**, partindo da experiência nativa unificada no Linux Mint Cinnamon até a expansão para outros compositors Wayland/X11, novos periféricos e automação contextual.

---

## Fase 1 — Linux Mint Cinnamon Unified Island (`v1.0.0` — Concluída)
- [x] **Core Hardware Engine (`src/dpi_core/hardware.py`)**: Drivers em Python 3 stdlib para AJAZZ AJ179 V2 (HID 33B + cache deep sleep), Havit Fuxi H3 (dual BT/2.4GHz + fix ALSA `numid=9`), Machenike K500-B94 (Hardware Safe Mode), GameSir Nova Lite e EasySMX 9124 (fusão cabo+dongle + janela de inatividade 60s + teste de rumble `EVIOCSFF`).
- [x] **Antigravity View Usage (`src/dpi_core/antigravity.py`)**: Descoberta automática do `language_server`, ConnectRPC `GetUserStatus`, agrupamento de cotas (`neon`, `hydrogen`, `argon`, `flash`, `claude_gpt`, `carbon`), Pace Marker, ETA de esgotamento, Swarm Tracker e histograma incremental de 7 dias + resumo mensal.
- [x] **CLI Unificada (`bin/dpi-hub`)**: Modos `--island-json`, `--waybar`, `--pretty` e flags completas de controle de dispositivos e preferências.
- [x] **Applet Cinnamon (`applet/dynamic-peripheral-island@brendo`)**: Cápsula única na TopBar (`panel2:center`) envolvendo Data/Hora + Periféricos + Antigravity, Morphing de alertas (4s), atalho global `Super + Alt + I`, Popover Bento Grid com 3 abas (`Periféricos`, `Antigravity VU`, `Ajustes`) e tema adaptativo Dark/Light Glassmorphism.
- [x] **Instalação & Testes**: Regras `udev`, `install.sh`, `uninstall.sh` e suíte `unittest` automatizada.

---

## Fase 2 — Waybar / Hyprland / Sway / GNOME Shell (`v1.1.0` — Planejada)
- [ ] **Integração Waybar Nauta**: Módulo customizado oficial usando `dpi-hub --waybar`, com presets de CSS Glassmorphism prontos para Hyprland e Sway.
- [ ] **Popover Wayland Nativo (GTK4 / Layer-Shell)**: Camada opcional leve para compositors Wayland que não utilizam o painel do Cinnamon, consumindo o mesmo JSON de `--island-json`.
- [ ] **Extensão GNOME Shell**: Porta do módulo da TopBar para GNOME 45+ (ESM) mantendo paridade visual com o Design System `MASTER.md`.
- [ ] **Notificações `libnotify` Opcionais**: Alertas nativos de sistema configuráveis quando a bateria cair abaixo do limiar ou quando um agente do Swarm concluir uma tarefa longa.

---

## Fase 3 — KDE Plasma 6 & Novos Periféricos Wireless (`v1.2.0` — Planejada)
- [ ] **Widget Plasmoid (KDE Plasma 6 / QML)**: Cápsula nativa para o painel do Plasma 6 reutilizando o backend `dpi-hub`.
- [ ] **Expansão de Drivers HID & Compatibilidade Open-Source**:
  - Adoção contínua das especificações de engenharia reversa documentadas no projeto open-source `krisgfx9/Wireless-Device-Battery-Monitor` (já inauguradas na v1.0.6 com o protocolo `0xFF7A` da GameSir):
    - **Logitech HID++ 2.0 / 4.0**: telemetria de bateria nativa para mouses (MX Master, G Pro, G502) e teclados sem fio via features `0x0001` (Battery Level Status) e `0x1000` (Unified Battery) diretamente em `hidraw` sem `pip`.
    - **Razer Wireless**: leitura de percentual de bateria e estado do dock de carregamento via pacotes vendor `0x02` (DeathAdder, Viper, Basilisk).
    - **Corsair & SteelSeries Engine Wireless**: decodificação de telemetria de bateria (Dark Core, Scimitar, Aerox, Arctis Nova) via pacotes Raw HID vendor.
  - Suporte a teclados QMK/VIA com leitura de layer ativa via Raw HID.
  - Detecção estendida de baterias Bluetooth via `UPower` e `bluez` GATT Battery Service.
- [ ] **Gráficos Históricos de Bateria**: Estimativa de autonomia restante dos periféricos baseada na taxa de descarga observada.

---

## Fase 4 — Automação de Perfis por Jogo / IDE (`v2.0.0` — Visão Futura)
- [ ] **Watcher de Janela Ativa (X11/Wayland)**: Detecção de aplicação em foco para troca automática de perfis.
- [ ] **Perfis Contextuais**:
  - *Modo IDE / Antigravity*: Mouse em DPI de precisão, Polling Rate 500Hz para economia de bateria, EQ `Voice`/`Flat`, destaque para cotas e Swarm na cápsula.
  - *Modo Gaming*: Mouse em DPI/Polling Rate 1000Hz configurados por jogo, EQ `Gaming`, ativação automática do layout `Xbox` ou `Nintendo` por título no Steam/Heroic.
- [ ] **Perfis Exportáveis**: Importação e exportação de presets em JSON compartilhável.

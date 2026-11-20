/*
 * Dynamic Peripheral Island — Cinnamon Unified TopBar Applet
 * 100% original Cinnamon CJS implementation (UI/UX Pro Max Glassmorphism)
 * Zero structural emojis: uses symbolic SVG St.Icon and clean typography.
 */

const Applet = imports.ui.applet;
const Clutter = imports.gi.Clutter;
const Gio = imports.gi.Gio;
const GLib = imports.gi.GLib;
const Main = imports.ui.main;
const Pango = imports.gi.Pango;
const PopupMenu = imports.ui.popupMenu;
const St = imports.gi.St;
const Tooltips = imports.ui.tooltips;

const UUID = "dynamic-peripheral-island@brendo";
const HOTKEY_NAME = "dpi-toggle-island";
const HOTKEY_BINDING = "<Super><Alt>i";
const DEFAULT_POLL_SECONDS = 5;
const MORPH_DURATION_MS = 4000;
const ALERT_COOLDOWN_MS = 60000;
const PROGRESS_TRACK_WIDTH = 290;

const DPI_PRESETS = [400, 800, 1600, 3200, 6400, 12000];
const POLLING_PRESETS = [125, 250, 500, 1000];
const MOUSE_LED_COLORS = ["#3B82F6", "#22C55E", "#F59E0B", "#EF4444", "#A855F7"];
const MOUSE_SLEEP_PRESETS = [
    { label: "60s", value: 60 },
    { label: "300s", value: 300 },
    { label: "900s", value: 900 },
    { label: "1800s", value: 1800 },
];
const EQ_PRESETS = [
    { id: "gaming", label: "Gaming" },
    { id: "music", label: "Music" },
    { id: "voice", label: "Voice" },
    { id: "flat", label: "Flat" },
];
const DEADZONE_PRESETS = [0, 5, 10, 15, 20];
const PINNED_QUOTA_OPTIONS = [
    { id: "auto", label: "Auto" },
    { id: "neon", label: "Neon" },
    { id: "hydrogen", label: "Hydrogen" },
    { id: "argon", label: "Argon" },
    { id: "flash", label: "Flash" },
    { id: "claude_gpt", label: "Claude/GPT" },
];
const ALERT_THRESHOLD_OPTIONS = [20, 15, 10];
const POLL_INTERVAL_OPTIONS = [3, 5, 10];
const THEME_MODE_OPTIONS = [
    { id: "auto", label: "Auto" },
    { id: "dark", label: "Dark" },
    { id: "light", label: "Light" },
];
const K500_DEFAULT_SHORTCUTS = [
    { keys: "FN + INS", desc: "Alternar modo de iluminacao RGB" },
    { keys: "FN + ↑ / ↓", desc: "Ajustar brilho do backlight" },
    { keys: "FN + ← / →", desc: "Ajustar velocidade / direcao do efeito" },
    { keys: "FN + ESC", desc: "Restaurar padrao de fabrica (segurar 3s)" },
];

function stripEmojis(text) {
    if (!text) return "";
    return String(text)
        .replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}]/gu, "")
        .replace(/\s{2,}/g, " ")
        .trim();
}

function formatTokens(n) {
    let val = Number(n) || 0;
    if (val >= 1000000000) return (val / 1000000000).toFixed(1) + "B";
    if (val >= 1000000) return (val / 1000000).toFixed(1) + "M";
    if (val >= 1000) return (val / 1000).toFixed(1) + "k";
    return String(Math.round(val));
}

function clamp(val, min, max) {
    return Math.max(min, Math.min(max, val));
}

function formatSecondsToTime(totalSec) {
    let s = Math.max(0, Math.round(Number(totalSec) || 0));
    let mins = Math.floor(s / 60);
    let secs = s % 60;
    return mins + ":" + (secs < 10 ? "0" + secs : secs);
}

function pctSeverityClass(pct, lowThresh) {
    let thresh = lowThresh || 20;
    if (pct === null || pct === undefined || isNaN(pct)) return "muted";
    if (pct <= 10) return "crit";
    if (pct <= thresh) return "warn";
    return "ok";
}

function quotaSeverityClass(pct) {
    if (pct === null || pct === undefined || isNaN(pct)) return "muted";
    if (pct <= 15) return "crit";
    if (pct <= 35) return "warn";
    return "ok";
}

function sysSeverityClass(pct, warnThresh = 60, critThresh = 85) {
    let p = Number(pct) || 0;
    if (p >= critThresh) return "crit";
    if (p >= warnThresh) return "warn";
    return "ok";
}

function tempSeverityClass(tempC, warnThresh = 75, critThresh = 85) {
    if (tempC === null || tempC === undefined || isNaN(tempC)) return "muted";
    let t = Number(tempC);
    if (t >= critThresh) return "crit";
    if (t >= warnThresh) return "warn";
    return "info";
}

function formatAudioProfileName(profileId) {
    let raw = String(profileId || "");
    if (raw === "off") return "Off";
    if (raw === "pro-audio") return "Pro Audio";
    if (raw.indexOf("analog-stereo") !== -1 && raw.indexOf("input:") !== -1) return "Analog + Mic";
    if (raw.indexOf("analog-stereo") !== -1) return "Analog";
    if (raw.indexOf("iec958-stereo") !== -1 && raw.indexOf("input:") !== -1) return "Digital + Mic";
    if (raw.indexOf("iec958-stereo") !== -1) return "Digital";
    if (raw.indexOf("headset-head-unit") !== -1) return "HFP/HSP";
    if (raw.indexOf("a2dp") !== -1) return "A2DP HiFi";
    return raw.length > 16 ? raw.slice(0, 14) + ".." : raw;
}

function batteryIconName(pct, charging) {
    if (charging) return "battery-full-charging-symbolic";
    if (pct === null || pct === undefined) return "battery-caution-symbolic";
    if (pct >= 75) return "battery-full-symbolic";
    if (pct >= 35) return "battery-good-symbolic";
    if (pct >= 15) return "battery-low-symbolic";
    return "battery-caution-symbolic";
}

class DynamicPeripheralIslandApplet extends Applet.Applet {
    constructor(metadata, orientation, panelHeight, instanceId) {
        super(orientation, panelHeight, instanceId);
        this._meta = metadata;
        this._orientation = orientation;

        this.setAllowedLayout(Applet.AllowedLayout.HORIZONTAL);
        this.actor.remove_style_class_name("applet-box");
        this.actor.add_style_class_name("dpi-applet-box");
        this.set_applet_tooltip("");

        // Runtime state
        this._data = null;
        this._activeTab = "peripherals";
        this._expandedCards = {
            mouse: false,
            headset: false,
            gamepad: false,
            keyboard: false,
            media: true,
            master_audio: true,
            per_app_audio: true,
        };
        this._resolvedTheme = "dark";
        this._pollSeconds = DEFAULT_POLL_SECONDS;
        this._pollTimerId = 0;
        this._morphTimerId = 0;
        this._toastTimerId = 0;
        this._idleAttachId = 0;
        this._hoverLeaveTimerId = 0;
        this._hoverCounter = 0;
        this._isPolling = false;
        this._prewarmed = false;
        this._destroyed = false;
        this._unifiedCenterBox = null;
        this._leftSlot = null;
        this._calendarActor = null;
        this._calMenu = null;
        this._calMenuSignalId = 0;
        this._calHoverTimerId = 0;
        this._tabHoverTimerId = 0;
        this._repositionIdleId = 0;
        this._tooltipActor = null;
        this._tooltipLabel = null;
        this._tooltipTimerId = 0;
        this._pillTooltips = [];
        this._taggedClockActors = [];
        this._hoverSignals = [];
        this._seenAlerts = {};
        this._toastState = null;
        this._lastPayloadHash = "";
        this._justExpandedCard = null;

        this._dpiHubPath = this._resolveDpiHubBinary();

        // Monitor Cinnamon desktop/shell themes
        this._ifaceSettings = null;
        this._cinnamonThemeSettings = null;
        this._themeSignalIds = [];
        this._initThemeMonitors();

        // Build TopBar segments
        this._buildTopBar();

        // Build Popover Bento Menu
        this._buildPopover(orientation);

        // Initialize Animated LiquidGlass Tooltip (UX-017)
        this._initAnimatedTooltip();

        // Register global shortcut Super + Alt + I
        try {
            Main.keybindingManager.addHotKey(HOTKEY_NAME, HOTKEY_BINDING, () => {
                this._toggleIsland();
            });
        } catch (e) {
            global.logError(UUID + ": failed to register hotkey: " + e);
        }

        // Apply initial theme and trigger first async poll
        this._applyTheme();
        this._refreshNow();
        this._schedulePoll();
    }

    _resolveDpiHubBinary() {
        let homeBin = GLib.build_filenamev([GLib.get_home_dir(), ".local", "bin", "dpi-hub"]);
        if (GLib.file_test(homeBin, GLib.FileTest.IS_EXECUTABLE)) {
            return homeBin;
        }
        let inPath = GLib.find_program_in_path("dpi-hub");
        if (inPath) {
            return inPath;
        }
        if (this._meta && this._meta.path) {
            let repoBin = GLib.build_filenamev([this._meta.path, "..", "..", "bin", "dpi-hub"]);
            if (GLib.file_test(repoBin, GLib.FileTest.IS_EXECUTABLE)) {
                return repoBin;
            }
        }
        return "dpi-hub";
    }

    _initThemeMonitors() {
        try {
            this._ifaceSettings = new Gio.Settings({ schema_id: "org.cinnamon.desktop.interface" });
            let id1 = this._ifaceSettings.connect("changed::gtk-theme", () => this._applyTheme());
            this._themeSignalIds.push({ settings: this._ifaceSettings, id: id1 });
        } catch (e) {
            global.logWarning(UUID + ": unable to watch org.cinnamon.desktop.interface: " + e);
        }

        try {
            this._cinnamonThemeSettings = new Gio.Settings({ schema_id: "org.cinnamon.theme" });
            let id2 = this._cinnamonThemeSettings.connect("changed::name", () => this._applyTheme());
            this._themeSignalIds.push({ settings: this._cinnamonThemeSettings, id: id2 });
        } catch (e) {
            global.logWarning(UUID + ": unable to watch org.cinnamon.theme: " + e);
        }
    }

    _detectSystemDarkMode() {
        let gtkTheme = "";
        let shellTheme = "";
        try {
            if (this._ifaceSettings) gtkTheme = (this._ifaceSettings.get_string("gtk-theme") || "").toLowerCase();
        } catch (e) {
            // ignore
        }
        try {
            if (this._cinnamonThemeSettings) shellTheme = (this._cinnamonThemeSettings.get_string("name") || "").toLowerCase();
        } catch (e) {
            // ignore
        }

        let combined = gtkTheme + " " + shellTheme;
        let darkHints = ["dark", "black", "noir", "night", "dracula", "obsidian", "midnight", "mocha", "nord"];
        let lightHints = ["light", "white", "latte", "day", "bright"];

        for (let hint of darkHints) {
            if (combined.indexOf(hint) !== -1) return true;
        }
        if (this._data && this._data.theme_suggestion) {
            let sugg = String(this._data.theme_suggestion).toLowerCase();
            if (sugg === "dark") return true;
            if (sugg === "light") return false;
        }
        for (let hint of lightHints) {
            if (combined.indexOf(hint) !== -1) return false;
        }
        return true;
    }

    _resolveThemeMode() {
        let configured = (this._data && this._data.settings && this._data.settings.theme_mode) || "auto";
        if (configured === "dark") return "dark";
        if (configured === "light") return "light";
        return this._detectSystemDarkMode() ? "dark" : "light";
    }

    _applyThemeToActor(actor, themeName) {
        if (!actor) return;
        actor.remove_style_class_name("dpi-theme-dark");
        actor.remove_style_class_name("dpi-theme-light");
        actor.add_style_class_name(themeName === "light" ? "dpi-theme-light" : "dpi-theme-dark");
    }

    _applyTheme() {
        this._resolvedTheme = this._resolveThemeMode();
        this._applyThemeToActor(this.actor, this._resolvedTheme);
        if (this._unifiedCenterBox) {
            this._applyThemeToActor(this._unifiedCenterBox, this._resolvedTheme);
        }
        if (this._popoverRoot) {
            this._applyThemeToActor(this._popoverRoot, this._resolvedTheme);
        }
        if (this._tooltipActor) {
            this._applyThemeToActor(this._tooltipActor, this._resolvedTheme);
        }
    }

    /* ======================================================================
     * TopBar Unified Capsule Lifecycle
     * ====================================================================== */

    _buildTopBar() {
        // Left slot for Peripherals on the left side of the Clock
        this._leftSlot = new St.BoxLayout({
            style_class: "dpi-left-slot",
            y_align: Clutter.ActorAlign.CENTER,
            reactive: true,
            track_hover: true,
        });

        // Peripherals Segment
        this._segPeripherals = new St.BoxLayout({
            style_class: "applet-box dpi-capsule-segment",
            reactive: true,
            can_focus: true,
            track_hover: true,
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._segPeripherals.connect("button-press-event", (actor, event) => {
            if (event.get_button() === 1) {
                this._openTabFromSegment("peripherals");
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        });
        this._leftSlot.add_child(this._segPeripherals);

        // Mid divider between Clock and Antigravity (hidden: no vertical pipe on TopBar)
        this._midDivider = new St.Widget({ style_class: "dpi-capsule-divider" });
        this._midDivider.y_align = Clutter.ActorAlign.CENTER;
        this._midDivider.hide();
        this.actor.add_child(this._midDivider);

        // Antigravity Segment
        this._segAntigravity = new St.BoxLayout({
            style_class: "applet-box dpi-capsule-segment",
            reactive: true,
            can_focus: true,
            track_hover: true,
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._segAntigravity.connect("button-press-event", (actor, event) => {
            if (event.get_button() === 1) {
                this._openTabFromSegment("antigravity");
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        });
        this.actor.add_child(this._segAntigravity);

        // Dynamic Morphing Alert Pill (animated via actor.ease)
        this._morphPill = new St.BoxLayout({
            style_class: "dpi-morph-pill dpi-morph-info",
            reactive: true,
            track_hover: true,
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._morphIcon = new St.Icon({
            icon_name: "dialog-warning-symbolic",
            icon_type: St.IconType.SYMBOLIC,
            style_class: "dpi-pill-icon",
        });
        this._morphLabel = new St.Label({
            text: "",
            style_class: "dpi-morph-text",
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._morphPill.add_child(this._morphIcon);
        this._morphPill.add_child(this._morphLabel);
        this._morphPill.opacity = 0;
        this._morphPill.hide();
        this._morphAlertTab = "peripherals";
        this._morphPill.connect("button-press-event", (actor, event) => {
            if (event.get_button() === 1) {
                this._dismissMorphAlert();
                this._openTabFromSegment(this._morphAlertTab);
                return Clutter.EVENT_STOP;
            }
            return Clutter.EVENT_PROPAGATE;
        });
        this.actor.add_child(this._morphPill);

        this._renderTopBarPlaceholder();
    }

    _renderTopBarPlaceholder() {
        this._clearPillTooltips();
        this._segPeripherals.destroy_all_children();
        this._segPeripherals.add_child(this._makePillItem("input-mouse-symbolic", "--", "muted", null, "Perifericos"));

        this._segAntigravity.destroy_all_children();
        this._segAntigravity.add_child(this._makePillItem("applications-science-symbolic", "AG", "muted", null, "Antigravity"));
    }

    _makeDeviceIcon(iconName, styleClass, size) {
        if (iconName && iconName.startsWith("dpi-") && this._meta && this._meta.path) {
            let svgPath = GLib.build_filenamev([this._meta.path, "icons", iconName + ".svg"]);
            if (GLib.file_test(svgPath, GLib.FileTest.EXISTS)) {
                let iconProps = {
                    gicon: Gio.icon_new_for_string(svgPath),
                    icon_type: St.IconType.SYMBOLIC,
                    style_class: styleClass || "dpi-pill-icon",
                };
                if (size) iconProps.icon_size = size;
                return new St.Icon(iconProps);
            }
        }
        let fallbackName = iconName;
        if (iconName === "dpi-gamepad-symbolic") fallbackName = "input-gaming-symbolic";
        else if (iconName === "dpi-mouse-sleep-symbolic") fallbackName = "input-mouse-symbolic";

        let iconProps = {
            icon_name: fallbackName,
            icon_type: St.IconType.SYMBOLIC,
            style_class: styleClass || "dpi-pill-icon",
        };
        if (size) iconProps.icon_size = size;
        return new St.Icon(iconProps);
    }

    _clearPillTooltips() {
        this._hideAnimatedTooltip();
        if (Array.isArray(this._pillTooltips)) {
            for (let tip of this._pillTooltips) {
                try {
                    tip.destroy();
                } catch (e) {
                    // ignore
                }
            }
        }
        this._pillTooltips = [];
    }

    _makePillItem(iconName, text, tone, extraDotClass, tooltipText) {
        let item = new St.BoxLayout({
            style_class: "dpi-pill-item",
            y_align: Clutter.ActorAlign.CENTER,
        });
        if (iconName) {
            item.add_child(this._makeDeviceIcon(iconName, "dpi-pill-icon"));
        }
        if (extraDotClass) {
            let dot = new St.Widget({
                style_class: "dpi-status-dot " + extraDotClass,
                y_align: Clutter.ActorAlign.CENTER,
            });
            item.add_child(dot);
        }
        if (text !== null && text !== undefined && text !== "") {
            let textClass = "applet-label dpi-pill-text";
            if (tone && tone !== "default") {
                textClass += " dpi-pill-text-" + tone;
            }
            item.add_child(new St.Label({
                text: String(text),
                style_class: textClass,
                y_align: Clutter.ActorAlign.CENTER,
            }));
        }
        if (tooltipText) {
            item.reactive = true;
            item.track_hover = true;
            // UX-017: Animated LiquidGlass tooltip replaces static new Tooltips.Tooltip()
            item.connect("enter-event", () => {
                this._showAnimatedTooltip(item, tooltipText);
                return Clutter.EVENT_PROPAGATE;
            });
            item.connect("leave-event", () => {
                this._hideAnimatedTooltip();
                return Clutter.EVENT_PROPAGATE;
            });
        }
        return item;
    }

    on_applet_added_to_panel() {
        this._attachUnifiedCapsule();
        if (this._idleAttachId) {
            GLib.source_remove(this._idleAttachId);
            this._idleAttachId = 0;
        }
        this._idleAttachId = GLib.idle_add(GLib.PRIORITY_DEFAULT_IDLE, () => {
            this._idleAttachId = 0;
            if (!this._destroyed) {
                this._attachUnifiedCapsule();
            }
            return GLib.SOURCE_REMOVE;
        });
    }

    _updateHoverState(isEntering) {
        if (this._destroyed) return;
        let box = this._unifiedCenterBox || this.actor;
        if (!box) return;

        if (this._hoverLeaveTimerId) {
            GLib.source_remove(this._hoverLeaveTimerId);
            this._hoverLeaveTimerId = 0;
        }

        if (isEntering) {
            this._hoverCounter = (this._hoverCounter || 0) + 1;
            box.add_style_class_name("dpi-capsule-hovered");
        } else {
            this._hoverCounter = Math.max(0, (this._hoverCounter || 0) - 1);

            this._hoverLeaveTimerId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 80, () => {
                this._hoverLeaveTimerId = 0;
                if (this._destroyed) return GLib.SOURCE_REMOVE;
                let anyHover = false;
                let checkList = [this._leftSlot, this.actor, this._unifiedCenterBox].concat(this._taggedClockActors);
                for (let a of checkList) {
                    if (a && (a.hover || a.has_pointer)) {
                        anyHover = true;
                        break;
                    }
                }
                let menuOpen = Boolean(this.menu && this.menu.isOpen);
                let alertActive = Boolean(this._morphPill && this._morphPill.visible);
                if (!anyHover && this._hoverCounter <= 0 && !menuOpen && !alertActive) {
                    box.remove_style_class_name("dpi-capsule-hovered");
                }
                return GLib.SOURCE_REMOVE;
            });
        }
    }

    _syncCapsuleOpenState() {
        let box = this._unifiedCenterBox || this.actor;
        if (!box) return;
        let menuOpen = Boolean(this.menu && this.menu.isOpen);
        let alertActive = Boolean(this._morphPill && this._morphPill.visible);
        if (menuOpen || alertActive) {
            box.add_style_class_name("dpi-capsule-open");
        } else {
            box.remove_style_class_name("dpi-capsule-open");
        }
    }

    _attachUnifiedCapsule() {
        this._detachUnifiedCapsule();

        let parent = this.actor.get_parent();
        let centerBox = this.panel ? this.panel._centerBox : null;

        if (centerBox && (parent === centerBox || this._panelLocation === centerBox)) {
            this._unifiedCenterBox = centerBox;
            this.actor.remove_style_class_name("dpi-standalone-capsule");
            centerBox.add_style_class_name("dpi-unified-capsule");
            this._applyThemeToActor(centerBox, this._resolvedTheme);

            let children = centerBox.get_children();
            let calendarActor = null;
            for (let i = 0; i < children.length; i++) {
                let child = children[i];
                if (child === this.actor || child === this._leftSlot) continue;
                let siblingUuid = child._applet ? child._applet._uuid : "";
                if (siblingUuid === "calendar@cinnamon.org" || i < children.indexOf(this.actor)) {
                    child.add_style_class_name("dpi-capsule-clock");
                    this._taggedClockActors.push(child);
                    calendarActor = child;
                    break;
                }
            }
            this._calendarActor = calendarActor;

            if (this._leftSlot) {
                if (calendarActor) {
                    centerBox.insert_child_below(this._leftSlot, calendarActor);
                } else {
                    this.actor.insert_child_at_index(this._leftSlot, 0);
                }
            }

            let calApplet = calendarActor && calendarActor._applet;
            let calMenu = calApplet && calApplet.menu;
            if (calMenu && calMenu !== this._calMenu) {
                this._disconnectCalMenu();
                this._calMenu = calMenu;
                try {
                    this._calMenuSignalId = calMenu.connect("open-state-changed", (menu, isOpen) => {
                        this._onCalendarOpenStateChanged(isOpen);
                    });
                } catch (e) {
                    global.logWarning(UUID + ": failed to connect to calendar menu: " + e);
                }
            }

            let hoverActors = [this._leftSlot, this.actor, centerBox];
            if (calendarActor) hoverActors.push(calendarActor);

            for (let a of hoverActors) {
                if (!a) continue;
                a.reactive = true;
                a.track_hover = true;
                let enterId = a.connect("enter-event", () => this._updateHoverState(true));
                let leaveId = a.connect("leave-event", () => this._updateHoverState(false));
                this._hoverSignals.push({ actor: a, id: enterId });
                this._hoverSignals.push({ actor: a, id: leaveId });
            }

            this._syncCapsuleOpenState();
        } else {
            this.actor.add_style_class_name("dpi-standalone-capsule");
            this._applyThemeToActor(this.actor, this._resolvedTheme);

            if (this._leftSlot) {
                this.actor.insert_child_at_index(this._leftSlot, 0);
            }

            let hoverActors = [this._leftSlot, this.actor];
            for (let a of hoverActors) {
                if (!a) continue;
                a.reactive = true;
                a.track_hover = true;
                let enterId = a.connect("enter-event", () => this._updateHoverState(true));
                let leaveId = a.connect("leave-event", () => this._updateHoverState(false));
                this._hoverSignals.push({ actor: a, id: enterId });
                this._hoverSignals.push({ actor: a, id: leaveId });
            }

            this._syncCapsuleOpenState();
        }
    }

    _onCalendarOpenStateChanged(isOpen) {
        if (this._destroyed) return;
        if (isOpen) {
            this._hideAnimatedTooltip();
            this._startCalHoverMonitor();
        } else {
            this._stopCalHoverMonitor();
        }
    }

    _pointInActor(actor, px, py) {
        if (!actor || !actor.visible || !actor.get_stage()) return false;
        try {
            let [ax, ay] = actor.get_transformed_position();
            let [aw, ah] = actor.get_transformed_size();
            return px >= ax && px < ax + aw && py >= ay && py < ay + ah;
        } catch (e) {
            return false;
        }
    }

    _startCalHoverMonitor() {
        this._stopCalHoverMonitor();
        let calMenu = this._calMenu || (this._calendarActor && this._calendarActor._applet && this._calendarActor._applet.menu);
        if (!calMenu || !calMenu.isOpen) return;

        this._calHoverTimerId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 60, () => {
            if (this._destroyed) {
                this._calHoverTimerId = 0;
                return GLib.SOURCE_REMOVE;
            }
            let menu = this._calMenu || (this._calendarActor && this._calendarActor._applet && this._calendarActor._applet.menu);
            if (!menu || !menu.isOpen) {
                this._calHoverTimerId = 0;
                return GLib.SOURCE_REMOVE;
            }

            if (typeof global.get_pointer === "function") {
                let [px, py] = global.get_pointer();
                let inLeft = this._pointInActor(this._segPeripherals, px, py) ||
                             this._pointInActor(this._leftSlot, px, py);
                let inRight = this._pointInActor(this._segAntigravity, px, py) ||
                              this._pointInActor(this.actor, px, py);

                if (inLeft) {
                    this._calHoverTimerId = 0;
                    menu.close(false);
                    this._openTabFromSegment("peripherals");
                    return GLib.SOURCE_REMOVE;
                }
                if (inRight) {
                    this._calHoverTimerId = 0;
                    menu.close(false);
                    this._openTabFromSegment("antigravity");
                    return GLib.SOURCE_REMOVE;
                }
            }
            return GLib.SOURCE_CONTINUE;
        });
    }

    _stopCalHoverMonitor() {
        if (this._calHoverTimerId) {
            GLib.source_remove(this._calHoverTimerId);
            this._calHoverTimerId = 0;
        }
    }

    _disconnectCalMenu() {
        this._stopCalHoverMonitor();
        if (this._calMenu && this._calMenuSignalId) {
            try {
                this._calMenu.disconnect(this._calMenuSignalId);
            } catch (e) {
                // ignore
            }
            this._calMenuSignalId = 0;
        }
        this._calMenu = null;
    }

    _detachUnifiedCapsule() {
        this._clearPillTooltips();
        this._disconnectCalMenu();
        this._calendarActor = null;
        if (this._hoverLeaveTimerId) {
            GLib.source_remove(this._hoverLeaveTimerId);
            this._hoverLeaveTimerId = 0;
        }

        for (let s of this._hoverSignals) {
            try {
                s.actor.disconnect(s.id);
            } catch (e) {
                // ignore
            }
        }
        this._hoverSignals = [];

        if (this._leftSlot) {
            let leftParent = this._leftSlot.get_parent();
            if (leftParent) {
                try {
                    leftParent.remove_child(this._leftSlot);
                } catch (e) {
                    // ignore
                }
            }
        }

        if (this._unifiedCenterBox) {
            try {
                this._unifiedCenterBox.remove_style_class_name("dpi-unified-capsule");
                this._unifiedCenterBox.remove_style_class_name("dpi-capsule-hovered");
                this._unifiedCenterBox.remove_style_class_name("dpi-capsule-open");
                this._unifiedCenterBox.remove_style_class_name("dpi-theme-dark");
                this._unifiedCenterBox.remove_style_class_name("dpi-theme-light");
            } catch (e) {
                // actor might already be disposed during panel teardown
            }
            this._unifiedCenterBox = null;
        }

        for (let actor of this._taggedClockActors) {
            try {
                actor.remove_style_class_name("dpi-capsule-clock");
            } catch (e) {
                // ignore
            }
        }
        this._taggedClockActors = [];
        this.actor.remove_style_class_name("dpi-standalone-capsule");
        this.actor.remove_style_class_name("dpi-capsule-hovered");
        this.actor.remove_style_class_name("dpi-capsule-open");
    }

    on_applet_removed_from_panel() {
        this._destroyed = true;

        try {
            Main.keybindingManager.removeHotKey(HOTKEY_NAME);
        } catch (e) {
            // ignore
        }

        if (this._pollTimerId) {
            GLib.source_remove(this._pollTimerId);
            this._pollTimerId = 0;
        }
        if (this._morphTimerId) {
            GLib.source_remove(this._morphTimerId);
            this._morphTimerId = 0;
        }
        if (this._toastTimerId) {
            GLib.source_remove(this._toastTimerId);
            this._toastTimerId = 0;
        }
        if (this._idleAttachId) {
            GLib.source_remove(this._idleAttachId);
            this._idleAttachId = 0;
        }
        if (this._hoverLeaveTimerId) {
            GLib.source_remove(this._hoverLeaveTimerId);
            this._hoverLeaveTimerId = 0;
        }
        if (this._repositionIdleId) {
            GLib.source_remove(this._repositionIdleId);
            this._repositionIdleId = 0;
        }
        if (this._tooltipTimerId) {
            GLib.source_remove(this._tooltipTimerId);
            this._tooltipTimerId = 0;
        }
        this._cancelTabHoverTimer();
        this._disconnectCalMenu();

        if (this._tooltipActor) {
            try {
                Main.uiGroup.remove_actor(this._tooltipActor);
                this._tooltipActor.destroy();
            } catch (e) {
                // ignore
            }
            this._tooltipActor = null;
        }

        for (let item of this._themeSignalIds) {
            try {
                item.settings.disconnect(item.id);
            } catch (e) {
                // ignore
            }
        }
        this._themeSignalIds = [];

        this._detachUnifiedCapsule();

        if (this._leftSlot) {
            try {
                this._leftSlot.destroy();
            } catch (e) {
                // ignore
            }
            this._leftSlot = null;
        }

        if (this.menu) {
            try {
                this.menu.sourceActor = this.actor;
                this.menu.destroy();
            } catch (e) {
                // ignore
            }
            this.menu = null;
        }
    }

    menuEventFilter(event) {
        let src = event ? event.get_source() : null;
        if (!src) return false;
        let inLeft = (this._leftSlot && this._leftSlot.contains(src)) ||
                     (this._segPeripherals && this._segPeripherals.contains(src));
        let inRight = (this.actor && this.actor.contains(src)) ||
                      (this._segAntigravity && this._segAntigravity.contains(src));
        let inCalendar = Boolean(this._calendarActor && this._calendarActor.contains(src));

        if (!inLeft && !inRight && !inCalendar) return false;

        let etype = event.type();

        if (this.menu && this.menu.isOpen) {
            if (etype === Clutter.EventType.ENTER || etype === Clutter.EventType.MOTION) {
                if (inLeft && this._activeTab !== "peripherals") {
                    this._switchTabFromTopBarHover("peripherals");
                    return true;
                }
                if (inRight && this._activeTab !== "antigravity") {
                    this._switchTabFromTopBarHover("antigravity");
                    return true;
                }
                if (inCalendar) {
                    this.menu.close(false);
                    let calMenu = this._calendarActor && this._calendarActor._applet && this._calendarActor._applet.menu;
                    if (calMenu && !calMenu.isOpen) {
                        calMenu.open(true);
                    }
                    return true;
                }
            }
        }

        if (etype === Clutter.EventType.BUTTON_RELEASE) {
            return true;
        }
        if (etype === Clutter.EventType.BUTTON_PRESS && event.get_button() === 1) {
            if (inLeft) {
                this._openTabFromSegment("peripherals");
                return true;
            }
            if (inRight) {
                this._openTabFromSegment("antigravity");
                return true;
            }
            if (inCalendar) {
                if (this.menu && this.menu.isOpen) {
                    this.menu.close(false);
                }
                let calMenu = this._calendarActor && this._calendarActor._applet && this._calendarActor._applet.menu;
                if (calMenu && !calMenu.isOpen) {
                    calMenu.open(true);
                }
                return true;
            }
        }
        return false;
    }

    _switchTabFromTopBarHover(tabName) {
        if (!this.menu || !this.menu.isOpen) return;
        this.menu.sourceActor = this._unifiedCenterBox || this._calendarActor || this.actor;
        this._switchTab(tabName, true);
        if (typeof this.menu._reposition === "function") {
            try {
                this.menu._reposition();
            } catch (e) {
                // ignore
            }
        } else if (typeof this.menu._calculatePosition === "function") {
            try {
                let [xPos, yPos] = this.menu._calculatePosition();
                this.menu.actor.set_position(xPos, yPos);
            } catch (e) {
                // ignore
            }
        }
    }

    _cancelTabHoverTimer() {
        if (this._tabHoverTimerId) {
            GLib.source_remove(this._tabHoverTimerId);
            this._tabHoverTimerId = 0;
        }
    }

    on_applet_clicked(event) {
        let src = event ? event.get_source() : null;
        if (src && this._segAntigravity && this._segAntigravity.contains(src)) {
            this._openTabFromSegment("antigravity");
        } else if (src && this._segPeripherals && this._segPeripherals.contains(src)) {
            this._openTabFromSegment("peripherals");
        } else {
            this._toggleIsland();
        }
    }

    _openTabFromSegment(tabName) {
        if (!this.menu) return;
        this._hideAnimatedTooltip();
        if (this.menu.isOpen && this._activeTab === tabName) {
            this.menu.close(true);
            return;
        }
        this.menu.sourceActor = this._unifiedCenterBox || this._calendarActor || this.actor;
        if (this.menu.isOpen) {
            this._switchTab(tabName, true);
        } else {
            this._activeTab = tabName;
            this._renderPopover();
            this.menu.open(true);
        }
        this._refreshNow();
    }

    _toggleIsland() {
        if (!this.menu) return;
        this._hideAnimatedTooltip();
        this.menu.sourceActor = this._unifiedCenterBox || this._calendarActor || this.actor;
        if (this.menu.isOpen) {
            this.menu.close(true);
        } else {
            this._renderPopover();
            this.menu.open(true);
            this._refreshNow();
        }
    }

    /* ======================================================================
     * Morphing Alert Pill (TopBar Animation)
     * ====================================================================== */

    _processAlerts(alerts) {
        if (!Array.isArray(alerts) || alerts.length === 0) return;

        let now = Date.now();
        let chosen = null;

        for (let alert of alerts) {
            if (!alert) continue;
            let type = String(alert.type || alert.kind || "info");
            let msg = stripEmojis(alert.message || alert.title || alert.text || "");
            if (!msg) continue;

            let key = type + "::" + msg;
            let lastSeen = this._seenAlerts[key] || 0;
            if (now - lastSeen < ALERT_COOLDOWN_MS) continue;

            this._seenAlerts[key] = now;
            chosen = {
                type: type,
                severity: String(alert.severity || alert.level || ""),
                message: msg,
            };
            break;
        }

        if (chosen) {
            this._showMorphAlert(chosen);
        }
    }

    _showMorphAlert(alert) {
        if (this._destroyed || !this._morphPill) return;

        if (this._morphTimerId) {
            GLib.source_remove(this._morphTimerId);
            this._morphTimerId = 0;
        }

        let toneClass = "dpi-morph-info";
        let iconName = "dialog-warning-symbolic";
        this._morphAlertTab = "peripherals";

        let t = alert.type;
        if (t === "low_battery") {
            toneClass = alert.severity === "critical" ? "dpi-morph-crit" : "dpi-morph-warn";
            iconName = "battery-caution-symbolic";
        } else if (t === "charging_started") {
            toneClass = "dpi-morph-ok";
            iconName = "battery-full-charging-symbolic";
        } else if (t === "device_connected") {
            toneClass = "dpi-morph-ok";
            iconName = "input-gaming-symbolic";
        } else if (t === "swarm_active") {
            toneClass = "dpi-morph-swarm";
            iconName = "network-workgroup-symbolic";
            this._morphAlertTab = "antigravity";
        } else if (t === "low_quota") {
            toneClass = "dpi-morph-warn";
            iconName = "applications-science-symbolic";
            this._morphAlertTab = "antigravity";
        } else if (alert.severity === "critical") {
            toneClass = "dpi-morph-crit";
        }

        this._morphPill.style_class = "dpi-morph-pill " + toneClass;
        this._morphIcon.icon_name = iconName;
        let text = alert.message;
        if (text.length > 34) {
            text = text.slice(0, 31) + "...";
        }
        this._morphLabel.set_text(text);

        this._morphPill.remove_all_transitions();
        this._morphPill.opacity = 0;
        this._morphPill.show();
        this._syncCapsuleOpenState();
        this._morphPill.ease({
            opacity: 255,
            duration: 240,
            mode: Clutter.AnimationMode.EASE_OUT_QUAD,
        });

        this._morphTimerId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, MORPH_DURATION_MS, () => {
            this._morphTimerId = 0;
            this._dismissMorphAlert();
            return GLib.SOURCE_REMOVE;
        });
    }

    _dismissMorphAlert() {
        if (!this._morphPill || !this._morphPill.visible) return;
        this._morphPill.remove_all_transitions();
        this._morphPill.ease({
            opacity: 0,
            duration: 220,
            mode: Clutter.AnimationMode.EASE_IN_QUAD,
            onComplete: () => {
                if (this._morphPill) {
                    this._morphPill.hide();
                    this._syncCapsuleOpenState();
                }
            },
        });
    }

    /* ======================================================================
     * Async Subprocess Polling & Actions (Gio.Subprocess)
     * ====================================================================== */

    _schedulePoll() {
        if (this._pollTimerId) {
            GLib.source_remove(this._pollTimerId);
            this._pollTimerId = 0;
        }
        let secs = clamp(Number(this._pollSeconds) || DEFAULT_POLL_SECONDS, 2, 60);
        this._pollTimerId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, secs, () => {
            if (this._destroyed) return GLib.SOURCE_REMOVE;
            this._refreshNow();
            return GLib.SOURCE_CONTINUE;
        });
    }

    _runCliAsync(args, callback) {
        try {
            let argv = [this._dpiHubPath].concat(args);
            let proc = Gio.Subprocess.new(
                argv,
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE
            );
            proc.communicate_utf8_async(null, null, (p, res) => {
                if (this._destroyed) return;
                try {
                    let [, stdout, stderr] = p.communicate_utf8_finish(res);
                    let ok = p.get_successful();
                    callback(ok, stdout || "", stderr || "");
                } catch (err) {
                    callback(false, "", String(err));
                }
            });
        } catch (err) {
            callback(false, "", String(err));
        }
    }

    _refreshNow() {
        if (this._isPolling || this._destroyed) return;
        this._isPolling = true;

        this._runCliAsync(["--island-json"], (ok, stdout, stderr) => {
            this._isPolling = false;
            if (this._destroyed) return;

            if (!ok || !stdout.trim()) {
                if (!this._data) {
                    this._renderTopBarPlaceholder();
                }
                if (stderr) {
                    global.logWarning(UUID + ": dpi-hub error: " + stderr.trim());
                }
                return;
            }

            try {
                let parsed = JSON.parse(stdout);
                let payloadHash = JSON.stringify({
                    capsule: parsed.capsule,
                    peripherals: parsed.peripherals,
                    antigravity: parsed.antigravity,
                    settings: parsed.settings,
                });
                let payloadChanged = payloadHash !== this._lastPayloadHash;
                this._lastPayloadHash = payloadHash;
                this._data = parsed;

                let newInterval = parsed.settings && Number(parsed.settings.poll_interval);
                if (newInterval && newInterval !== this._pollSeconds) {
                    this._pollSeconds = newInterval;
                    this._schedulePoll();
                }

                this._applyTheme();
                this._updateTopBar();
                this._processAlerts(parsed.alerts || []);

                if (!this._prewarmed) {
                    this._prewarmed = true;
                    this._prewarmPopover();
                } else if (this.menu && this.menu.isOpen && payloadChanged) {
                    this._renderPopover();
                }
            } catch (parseErr) {
                global.logError(UUID + ": failed to parse --island-json: " + parseErr);
            }
        });
    }

    _prewarmPopover() {
        if (!this._popoverRoot || this._destroyed) return;
        let savedTab = this._activeTab;
        let savedExpanded = Object.assign({}, this._expandedCards);

        this._expandedCards = {
            mouse: true,
            headset: true,
            gamepad: true,
            keyboard: true,
            media: true,
            master_audio: true,
            per_app_audio: true,
        };
        for (let tabId of ["peripherals", "audio", "antigravity", "settings"]) {
            this._activeTab = tabId;
            this._renderPopover();
        }

        this._expandedCards = savedExpanded;
        this._activeTab = savedTab || "peripherals";
        this._renderPopover();
    }

    _dispatchCliAction(args, pendingText) {
        if (pendingText) {
            this._showToast("info", pendingText);
        }
        this._runCliAsync(args, (ok, stdout, stderr) => {
            if (this._destroyed) return;
            let resultOk = ok;
            let message = "";

            if (stdout && stdout.trim()) {
                try {
                    let parsed = JSON.parse(stdout.trim());
                    if (typeof parsed.ok === "boolean") resultOk = parsed.ok;
                    message = stripEmojis(parsed.message || "");
                } catch (e) {
                    message = stripEmojis(stdout.trim());
                }
            }
            if (!message) {
                message = resultOk ? "Acao aplicada com sucesso." : stripEmojis(stderr.trim() || "Falha ao executar comando.");
            }

            this._showToast(resultOk ? "ok" : "error", message);
            this._refreshNow();
        });
    }

    _showToast(kind, message) {
        this._toastState = { kind: kind, message: stripEmojis(message) };
        if (this._toastTimerId) {
            GLib.source_remove(this._toastTimerId);
            this._toastTimerId = 0;
        }
        this._toastTimerId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 5500, () => {
            this._toastTimerId = 0;
            this._toastState = null;
            if (this.menu && this.menu.isOpen) {
                this._renderToastBanner();
            }
            return GLib.SOURCE_REMOVE;
        });
        this._renderToastBanner();
    }

    /* ======================================================================
     * TopBar Rendering
     * ====================================================================== */

    _updateTopBar() {
        if (!this._data) return;

        this._clearPillTooltips();

        let settings = this._data.settings || {};
        let threshold = Number(settings.battery_alert_threshold) || 20;
        let peripherals = this._getDevicesMap();
        let ag = this._data.antigravity || {};

        // 1. Peripherals Segment
        this._segPeripherals.destroy_all_children();
        let pillCount = 0;
        let capsulePeriphs = this._data.capsule && Array.isArray(this._data.capsule.peripherals)
            ? this._data.capsule.peripherals
            : null;

        if (capsulePeriphs && capsulePeriphs.length > 0) {
            let iconMap = {
                mouse: "input-mouse-symbolic",
                headset: "audio-headphones-symbolic",
                gamepad: "dpi-gamepad-symbolic",
                keyboard: "input-keyboard-symbolic",
            };
            for (let p of capsulePeriphs) {
                if (!p || !p.visible) continue;
                let icon = p.charging ? "battery-full-charging-symbolic" : (iconMap[p.key] || "input-mouse-symbolic");
                let text = p.status_text || (p.battery !== null && p.battery !== undefined ? p.battery + "%" : "--");
                let tone = !p.connected ? "muted" : (p.charging ? "ok" : (
                    p.level === "critical" ? "crit" : (
                        p.level === "warning" ? "warn" : (
                            p.battery !== null && p.battery !== undefined
                                ? pctSeverityClass(p.battery, threshold)
                                : (p.active ? "info" : "muted")
                        )
                    )
                ));

                let tooltipText = "";
                if (p.key === "mouse") {
                    let m = peripherals.mouse || {};
                    let pState = p.power_state || m.power_state || (m.connected && !m.standby ? "active" : (m.standby ? "sleep" : "off"));
                    if (pState === "off" || (!p.connected && !p.active && !m.connected)) {
                        continue;
                    }
                    if (pState === "sleep") {
                        icon = "dpi-mouse-sleep-symbolic";
                        tone = "muted";
                        let bat = (p.battery !== null && p.battery !== undefined) ? p.battery : m.battery;
                        text = (p.status_text && p.status_text !== "Off") ? p.status_text : (bat !== null && bat !== undefined ? bat + "%" : "Descanso");
                        tooltipText = (m.name || "AJAZZ AJ179 V2") + " · Modo de Descanso (Sleep)" + (bat !== null && bat !== undefined ? " · Última bateria: " + bat + "%" : "");
                    } else {
                        let conn = m.connection_type || p.connection_type || "2.4GHz";
                        tooltipText = (m.name || "AJAZZ AJ179 V2") + " · " + conn;
                        let bat = (p.battery !== null && p.battery !== undefined) ? p.battery : m.battery;
                        if (bat !== null && bat !== undefined) tooltipText += " · Bateria " + bat + "%";
                        if (m.current_dpi) tooltipText += " · " + m.current_dpi + " DPI";
                        else if (m.dpi) tooltipText += " · " + m.dpi + " DPI";
                    }
                } else if (p.key === "headset") {
                    if (!p.active) continue;
                    let h = peripherals.headset || {};
                    let conn = h.connection_type || p.connection_type || "2.4GHz";
                    let isBt = conn === "Bluetooth" || p.connection_type === "Bluetooth";
                    let bat = (p.battery !== null && p.battery !== undefined) ? p.battery : h.battery;
                    let vol = (p.volume !== null && p.volume !== undefined) ? p.volume : h.volume;
                    let isMuted = p.muted !== undefined ? p.muted : Boolean(h.muted);
                    let volDisp = isMuted ? "Mudo" : (vol !== null && vol !== undefined ? vol + "%" : "100%");

                    if (isBt && bat !== null && bat !== undefined) {
                        text = p.charging ? bat + "%+" : bat + "%";
                        tooltipText = "Havit Fuxi H3 (Bluetooth) — Bateria: " + bat + "% | Volume: " + volDisp;
                    } else if (isBt) {
                        text = "BT";
                        tooltipText = "Havit Fuxi H3 (Bluetooth) — Volume: " + volDisp;
                    } else if (bat !== null && bat !== undefined) {
                        text = p.charging ? bat + "%+" : bat + "%";
                        tooltipText = "Havit Fuxi H3 (2.4GHz) — Bateria: " + bat + "% | Volume: " + volDisp;
                    } else {
                        text = "2.4GHz";
                        tooltipText = "Havit Fuxi H3 (2.4GHz) — Volume: " + volDisp;
                    }
                } else if (p.key === "gamepad") {
                    let g = peripherals.gamepad || {};
                    let ctrls = Array.isArray(g.controllers) ? g.controllers : [];
                    let c = ctrls.find((x) => x.active) || ctrls.find((x) => x.connected) || null;
                    let name = (c && c.name) || (p.status_text && p.status_text.indexOf("EasySMX") !== -1 ? "EasySMX 9124" : "GameSir Nova Lite");
                    let conn = (c && c.connection_type) || "2.4GHz (XInput)";
                    tooltipText = name + " · " + conn;
                    let bat = (p.battery !== null && p.battery !== undefined) ? p.battery : (c && c.battery);
                    if (bat !== null && bat !== undefined) tooltipText += " · Bateria " + bat + "%";
                } else if (p.key === "keyboard") {
                    let k = peripherals.keyboard || {};
                    tooltipText = (k.name || "Machenike K500-B94") + " · USB-C · Hardware Safe Mode";
                }

                this._segPeripherals.add_child(this._makePillItem(icon, text, tone, null, tooltipText));
                pillCount++;
            }
        } else {
            let mouse = peripherals.mouse || {};
            let mPower = mouse.power_state || (mouse.connected && !mouse.standby ? "active" : (mouse.standby ? "sleep" : "off"));
            let showMouse = settings.pin_mouse !== false && mPower !== "off" && (mouse.connected || mPower === "sleep");
            if (showMouse) {
                let bat = mouse.battery;
                let text = "";
                let icon = "";
                let tone = "";
                let tip = "";
                if (mPower === "sleep") {
                    icon = "dpi-mouse-sleep-symbolic";
                    text = bat !== null && bat !== undefined ? bat + "%" : "Descanso";
                    tone = "muted";
                    tip = (mouse.name || "AJAZZ AJ179 V2") + " · Modo de Descanso (Sleep)" + (bat !== null && bat !== undefined ? " · Última bateria: " + bat + "%" : "");
                } else {
                    icon = mouse.charging ? "battery-full-charging-symbolic" : "input-mouse-symbolic";
                    text = bat !== null && bat !== undefined ? (mouse.charging ? bat + "%+" : bat + "%") : "OK";
                    tone = mouse.charging ? "ok" : pctSeverityClass(bat, threshold);
                    tip = (mouse.name || "AJAZZ AJ179 V2") + " · " + (mouse.connection_type || "2.4GHz");
                    if (bat !== null && bat !== undefined) tip += " · Bateria " + bat + "%";
                    if (mouse.current_dpi || mouse.dpi) tip += " · " + (mouse.current_dpi || mouse.dpi) + " DPI";
                }
                this._segPeripherals.add_child(this._makePillItem(icon, text, tone, null, tip));
                pillCount++;
            }

            let headset = peripherals.headset || {};
            let showHeadset = Boolean(headset.connected && headset.active);
            if (showHeadset) {
                let bat = headset.battery;
                let vol = headset.volume;
                let isMuted = Boolean(headset.muted);
                let isBt = headset.connection_type === "Bluetooth";
                let volDisp = isMuted ? "Mudo" : (vol !== null && vol !== undefined ? vol + "%" : "100%");
                let text = "";
                let tip = "";
                if (isBt && bat !== null && bat !== undefined) {
                    text = headset.charging ? bat + "%+" : bat + "%";
                    tip = "Havit Fuxi H3 (Bluetooth) — Bateria: " + bat + "% | Volume: " + volDisp;
                } else if (isBt) {
                    text = "BT";
                    tip = "Havit Fuxi H3 (Bluetooth) — Volume: " + volDisp;
                } else if (bat !== null && bat !== undefined) {
                    text = headset.charging ? bat + "%+" : bat + "%";
                    tip = "Havit Fuxi H3 (2.4GHz) — Bateria: " + bat + "% | Volume: " + volDisp;
                } else {
                    text = "2.4GHz";
                    tip = "Havit Fuxi H3 (2.4GHz) — Volume: " + volDisp;
                }
                let tone = isMuted ? "warn" : (bat !== null && bat !== undefined ? pctSeverityClass(bat, threshold) : "info");
                this._segPeripherals.add_child(this._makePillItem("audio-headphones-symbolic", text, tone, null, tip));
                pillCount++;
            }

            let gamepad = peripherals.gamepad || {};
            let showGamepad = Boolean(settings.pin_gamepad) || Boolean(gamepad.active);
            if (showGamepad) {
                let ctrls = Array.isArray(gamepad.controllers) ? gamepad.controllers : [];
                let activeCtrl = ctrls.find((c) => c.active) || ctrls.find((c) => c.connected) || null;
                let text = "PAD";
                let tone = "muted";
                if (activeCtrl) {
                    if (activeCtrl.charging) {
                        text = activeCtrl.battery !== null && activeCtrl.battery !== undefined ? activeCtrl.battery + "%+" : "CHG";
                        tone = "ok";
                    } else if (activeCtrl.battery !== null && activeCtrl.battery !== undefined) {
                        text = activeCtrl.battery + "%";
                        tone = pctSeverityClass(activeCtrl.battery, threshold);
                    } else {
                        text = activeCtrl.active ? "ON" : "Standby";
                        tone = activeCtrl.active ? "info" : "muted";
                    }
                }
                let gpName = (activeCtrl && activeCtrl.name) || "GameSir Nova Lite";
                let gpConn = (activeCtrl && activeCtrl.connection_type) || "2.4GHz (XInput)";
                let tip = gpName + " · " + gpConn;
                if (activeCtrl && activeCtrl.battery !== null && activeCtrl.battery !== undefined) {
                    tip += " · Bateria " + activeCtrl.battery + "%";
                }
                this._segPeripherals.add_child(this._makePillItem("dpi-gamepad-symbolic", text, tone, null, tip));
                pillCount++;
            }

            let keyboard = peripherals.keyboard || {};
            if (settings.pin_keyboard) {
                let leds = keyboard.leds || {};
                let flags = [];
                if (leds.capslock) flags.push("C");
                if (leds.numlock) flags.push("N");
                let text = keyboard.connected ? (flags.length ? flags.join("") : "SAFE") : "OFF";
                let tone = keyboard.connected ? "info" : "muted";
                let tip = (keyboard.name || "Machenike K500-B94") + " · USB-C · Hardware Safe Mode";
                this._segPeripherals.add_child(this._makePillItem("input-keyboard-symbolic", text, tone, null, tip));
                pillCount++;
            }
        }

        if (pillCount === 0) {
            this._segPeripherals.add_child(this._makePillItem("input-mouse-symbolic", "Hub", "muted", null, "Perifericos em Standby"));
        }

        // 2. Antigravity Segment
        this._segAntigravity.destroy_all_children();
        let capsuleAg = (this._data.capsule && this._data.capsule.antigravity) || {};
        let pinnedQuota = (capsuleAg.pinned_quota && capsuleAg.pinned_quota.enabled !== false)
            ? capsuleAg.pinned_quota
            : this._selectTopBarQuota(ag, settings.pinned_quota || "auto");
        let swarmCount = (ag.swarm && Number(ag.swarm.active_count)) || Number(capsuleAg.swarm_active) || 0;

        let agText = "AG";
        let agTone = "muted";
        let dotClass = "dpi-dot-muted";

        if (ag.connected || pinnedQuota) {
            if (pinnedQuota) {
                let shortName = pinnedQuota.short_name || pinnedQuota.name || "AG";
                let rem = Math.round(Number(pinnedQuota.remaining_pct));
                agText = shortName + " " + rem + "%";
                agTone = quotaSeverityClass(rem);
                dotClass = "dpi-dot-" + agTone;
            } else if (capsuleAg.label) {
                agText = stripEmojis(capsuleAg.label);
                agTone = "info";
                dotClass = "dpi-dot-info";
            } else {
                agText = "AG ON";
                agTone = "ok";
                dotClass = "dpi-dot-ok";
            }
        }

        if (swarmCount > 0) {
            dotClass = "dpi-dot-swarm";
        }

        let planName = this._extractPlanName(ag.plan) || "Pro";
        let activeModel = this._extractActiveModelName(ag.active_model) || "PBTXT";
        let quotaDesc = pinnedQuota
            ? (pinnedQuota.name || pinnedQuota.short_name || "AG") + " " + Math.round(Number(pinnedQuota.remaining_pct)) + "%"
            : (capsuleAg.label || "OK");
        let agTooltip = "Antigravity (" + planName + ") · Modelo: " + activeModel + " · Cota: " + quotaDesc;

        this._segAntigravity.add_child(
            this._makePillItem("applications-science-symbolic", agText, agTone, dotClass, agTooltip)
        );
        if (swarmCount > 0) {
            let swarmTooltip = "Swarm Ativo · " + swarmCount + " subagente" + (swarmCount > 1 ? "s" : "") + " em execucao";
            this._segAntigravity.add_child(
                this._makePillItem("network-workgroup-symbolic", String(swarmCount), "purple", null, swarmTooltip)
            );
        }

        // Update active highlight on segments when menu is open
        this._syncSegmentHighlight();
    }

    _selectTopBarQuota(ag, pinnedId) {
        let quotas = Array.isArray(ag.quotas) ? ag.quotas.filter((q) => q && q.enabled !== false) : [];
        if (quotas.length === 0) return ag.lowest_quota || null;
        if (pinnedId && pinnedId !== "auto") {
            let match = quotas.find((q) => q.id === pinnedId);
            if (match) return match;
        }
        if (ag.lowest_quota && ag.lowest_quota.enabled !== false && ag.lowest_quota.remaining_pct !== undefined) {
            return ag.lowest_quota;
        }
        return quotas.reduce((min, q) =>
            (Number(q.remaining_pct) < Number(min.remaining_pct) ? q : min), quotas[0]
        );
    }

    _syncSegmentHighlight() {
        let open = Boolean(this.menu && this.menu.isOpen);
        this._segPeripherals.remove_style_class_name("dpi-capsule-segment-active");
        this._segAntigravity.remove_style_class_name("dpi-capsule-segment-active");
        if (open && this._activeTab === "peripherals") {
            this._segPeripherals.add_style_class_name("dpi-capsule-segment-active");
        } else if (open && this._activeTab === "antigravity") {
            this._segAntigravity.add_style_class_name("dpi-capsule-segment-active");
        }
    }

    _getDevicesMap() {
        if (!this._data || !this._data.peripherals) return {};
        return this._data.peripherals.devices || this._data.peripherals || {};
    }

    /* ======================================================================
     * Animated LiquidGlass Tooltip (UX-017)
     * ====================================================================== */

    _initAnimatedTooltip() {
        if (this._tooltipActor) return;
        this._tooltipActor = new St.BoxLayout({
            reactive: false,
            style_class: "dpi-glass-tooltip dpi-theme-dark",
            vertical: false,
        });
        this._tooltipLabel = new St.Label({
            text: "",
            style_class: "dpi-tooltip-text",
        });
        this._tooltipActor.add_child(this._tooltipLabel);
        try {
            Main.uiGroup.add_actor(this._tooltipActor);
        } catch (e) {
            // ignore
        }
        this._tooltipActor.hide();
    }

    _showAnimatedTooltip(sourceActor, text) {
        if (this._destroyed || !sourceActor || !text || (this.menu && this.menu.isOpen)) return;
        if (!sourceActor.get_stage() || !this._tooltipActor) return;

        if (this._tooltipTimerId) {
            GLib.source_remove(this._tooltipTimerId);
            this._tooltipTimerId = 0;
        }

        this._tooltipLabel.text = String(text);

        let [ax, ay] = sourceActor.get_transformed_position();
        let [aw, ah] = sourceActor.get_transformed_size();

        let tipW = this._tooltipActor.get_preferred_width(-1)[1] || 100;
        let tipX = Math.round(ax + (aw - tipW) / 2);
        let tipY = Math.round(ay + ah + 6);

        this._tooltipActor.set_position(tipX, tipY);
        this._tooltipActor.remove_all_transitions();
        this._tooltipActor.opacity = 0;
        this._tooltipActor.translation_y = -6;
        this._tooltipActor.scale_x = 0.95;
        this._tooltipActor.scale_y = 0.95;
        this._tooltipActor.show();

        this._tooltipActor.ease({
            opacity: 255,
            translation_y: 0,
            scale_x: 1.0,
            scale_y: 1.0,
            duration: 180,
            mode: Clutter.AnimationMode.EASE_OUT_CUBIC,
        });
    }

    _hideAnimatedTooltip() {
        if (this._tooltipTimerId) {
            GLib.source_remove(this._tooltipTimerId);
            this._tooltipTimerId = 0;
        }
        if (!this._tooltipActor || !this._tooltipActor.visible) return;

        this._tooltipActor.remove_all_transitions();
        this._tooltipActor.ease({
            opacity: 0,
            translation_y: -4,
            duration: 130,
            mode: Clutter.AnimationMode.EASE_OUT_CUBIC,
            onComplete: () => {
                if (!this._destroyed && this._tooltipActor) {
                    this._tooltipActor.hide();
                }
            },
        });
    }

    /* ======================================================================
     * Popover Bento Grid UI
     * ====================================================================== */

    _buildPopover(orientation) {
        this.menuManager = new PopupMenu.PopupMenuManager(this);
        this.menu = new Applet.AppletPopupMenu(this, orientation);
        this.menuManager.addMenu(this.menu);

        this.menu.connect("open-state-changed", (menu, isOpen) => {
            if (!isOpen) {
                this._cancelTabHoverTimer();
            } else {
                this._hideAnimatedTooltip();
            }
            this._syncSegmentHighlight();
            this._syncCapsuleOpenState();
            if (isOpen) {
                this._renderPopover();
            }
        });

        this._popoverRoot = new St.BoxLayout({
            vertical: true,
            style_class: "dpi-popover-root dpi-theme-dark",
        });

        // Header bar
        this._headerBox = new St.BoxLayout({
            style_class: "dpi-header-row",
            style: "spacing: 6px;",
            x_expand: true,
            y_align: Clutter.ActorAlign.CENTER,
        });
        this._popoverRoot.add_child(this._headerBox);

        // Tab bar
        this._tabBar = new St.BoxLayout({
            style_class: "dpi-tab-bar",
            x_expand: true,
        });
        this._popoverRoot.add_child(this._tabBar);

        // Toast container
        this._toastBox = new St.BoxLayout({ vertical: true, x_expand: true });
        this._toastBox.hide();
        this._popoverRoot.add_child(this._toastBox);

        // Scrollable Bento body
        this._scrollView = new St.ScrollView({
            style_class: "dpi-scroll-view",
            hscrollbar_policy: St.PolicyType.NEVER,
            vscrollbar_policy: St.PolicyType.AUTOMATIC,
            x_expand: true,
        });
        this._bodyStack = new St.BoxLayout({
            vertical: true,
            style_class: "dpi-content-stack",
            x_expand: true,
        });
        this._scrollView.add_actor(this._bodyStack);
        this._popoverRoot.add_child(this._scrollView);

        this.menu.addActor(this._popoverRoot);
    }

    _renderPopover() {
        if (!this._popoverRoot) return;
        this._applyTheme();
        this._syncPopoverWidth();
        this._renderHeader();
        this._renderTabBar();
        this._renderToastBanner();
        this._renderActiveTabBody();
        this._justExpandedCard = null;
    }

    _syncPopoverWidth() {
        if (!this._popoverRoot) return;
        this._popoverRoot.width = 700;
        this._popoverRoot.add_style_class_name("dpi-popover-wide");
        if (this._scrollView) {
            this._scrollView.vscrollbar_policy = St.PolicyType.NEVER;
        }
        this._popoverRoot.queue_relayout();
        if (this.menu && this.menu.box) {
            this.menu.box.queue_relayout();
        }
    }

    _scheduleMenuReposition() {
        if (this._repositionIdleId) {
            GLib.source_remove(this._repositionIdleId);
            this._repositionIdleId = 0;
        }
        if (this._popoverRoot) {
            this._popoverRoot.queue_relayout();
        }
        if (this.menu && this.menu.box) {
            this.menu.box.queue_relayout();
        }
        this._repositionIdleId = GLib.idle_add(GLib.PRIORITY_DEFAULT, () => {
            this._repositionIdleId = 0;
            if (this._destroyed || !this.menu || !this.menu.isOpen) {
                return GLib.SOURCE_REMOVE;
            }
            if (typeof this.menu._reposition === "function") {
                try {
                    this.menu._reposition();
                } catch (e) {
                    // ignore
                }
            } else if (typeof this.menu._calculatePosition === "function") {
                try {
                    let [xPos, yPos] = this.menu._calculatePosition();
                    this.menu.actor.set_position(xPos, yPos);
                } catch (e) {
                    // ignore
                }
            }
            return GLib.SOURCE_REMOVE;
        });
    }

    _renderActiveTabBody() {
        if (!this._bodyStack) return;
        this._bodyStack.destroy_all_children();
        if (this._activeTab === "peripherals") {
            this._renderPeripheralsTab();
        } else if (this._activeTab === "audio") {
            this._renderAudioTab();
        } else if (this._activeTab === "system") {
            this._renderSystemTab();
        } else if (this._activeTab === "antigravity") {
            this._renderAntigravityTab();
        } else {
            this._renderSettingsTab();
        }
    }

    _switchTab(newTabId, animate = true) {
        if (!this._popoverRoot) return;
        let order = ["peripherals", "audio", "system", "antigravity", "settings"];
        let oldTab = this._activeTab;
        let oldIdx = Math.max(0, order.indexOf(oldTab));
        let newIdx = Math.max(0, order.indexOf(newTabId));
        let dir = newIdx >= oldIdx ? 1 : -1;

        this._activeTab = newTabId;
        this._justExpandedCard = null;

        // UX-016: Unified 700px Bento Grid layout across all 4 tabs.
        // Dynamic width morphing (width: targetW, this.menu.actor.ease({ ... })) and duration: 420
        // removed in favor of a fixed 700px width with 100% GPU-only composition (duration: 280, EASE_OUT_CUBIC, opacity: 150)
        // to eliminate CPU relayout stutter, frame drops and white flash.
        this._syncPopoverWidth();
        this._syncSegmentHighlight();
        this._renderTabBar();
        this._renderActiveTabBody();
        this._scheduleMenuReposition();

        if (animate && this._bodyStack) {
            this._bodyStack.remove_all_transitions();
            // Start at opacity: 150 (never 0) to eliminate white flash
            this._bodyStack.opacity = 150;
            this._bodyStack.scale_x = 0.99;
            this._bodyStack.scale_y = 0.99;
            this._bodyStack.translation_x = dir * 16;

            if (typeof this._bodyStack.set_pivot_point === "function") {
                try {
                    this._bodyStack.set_pivot_point(0.5, 0.5);
                } catch (e) {
                    // ignore
                }
            }

            // 100% GPU transition: Clutter.AnimationMode.EASE_OUT_CUBIC (evolved from EASE_OUT_QUINT and EASE_OUT_EXPO)
            let easeParams = {
                opacity: 255,
                scale_x: 1.0,
                scale_y: 1.0,
                translation_x: 0,
                duration: 280,
                mode: Clutter.AnimationMode.EASE_OUT_CUBIC,
            };
            try {
                const Graphene = imports.gi.Graphene;
                if (Graphene && Graphene.Point) {
                    easeParams.pivot_point = new Graphene.Point({ x: 0.5, y: 0.5 });
                }
            } catch (e) {
                // ignore
            }
            this._bodyStack.ease(easeParams);
        }
    }

    _animateCardBody(body, cardKey) {
        if (!body || this._justExpandedCard !== cardKey) return;
        body.opacity = 0;
        body.translation_y = -6;
        body.ease({
            opacity: 255,
            translation_y: 0,
            duration: 300,
            mode: Clutter.AnimationMode.EASE_OUT_QUINT,
        });
    }

    _renderHeader() {
        this._headerBox.destroy_all_children();

        let ag = (this._data && this._data.antigravity) || {};
        let planName = this._extractPlanName(ag.plan) || (ag.connected ? "Pro" : null);
        let activeModel = this._extractActiveModelName(ag.active_model) || (ag.connected ? "Orchestrator (Argon)" : null);
        let creditsStr = this._extractPlanCredits(ag.plan);

        let leftCol = new St.BoxLayout({ vertical: true, x_expand: true });
        let titleRow = new St.BoxLayout({ style: "spacing: 6px;", y_align: Clutter.ActorAlign.CENTER, x_expand: true });
        titleRow.add_child(new St.Icon({
            icon_name: "view-grid-symbolic",
            icon_type: St.IconType.SYMBOLIC,
            icon_size: 14,
        }));
        titleRow.add_child(new St.Label({
            text: "Dynamic Island",
            style_class: "dpi-title",
            y_align: Clutter.ActorAlign.CENTER,
        }));
        titleRow.add_child(new St.Label({
            text: "·",
            style_class: "dpi-subtitle",
            y_align: Clutter.ActorAlign.CENTER,
        }));
        let isWide = this._activeTab === "antigravity";
        let titleLabel = new St.Label({
            text: "Antigravity View Usage",
            style_class: "dpi-title",
            y_align: Clutter.ActorAlign.CENTER,
        });
        if (!isWide) {
            titleLabel.text = "Antigravity VU";
        }
        titleRow.add_child(titleLabel);
        if (planName) {
            titleRow.add_child(this._makeBadge(planName, "purple"));
        }
        if (creditsStr) {
            titleRow.add_child(this._makeBadge(creditsStr, "info"));
        }
        titleRow.add_child(new St.Widget({ x_expand: true }));
        leftCol.add_child(titleRow);

        let subtitleText = activeModel ? "Agente Ativo: " + activeModel : "Daemon Antigravity";
        leftCol.add_child(new St.Label({
            text: subtitleText,
            style_class: "dpi-subtitle",
        }));
        this._headerBox.add_child(leftCol);

        // Refresh button
        let refreshBtn = new St.Button({
            style_class: "dpi-icon-btn",
            can_focus: true,
            child: new St.Icon({
                icon_name: "view-refresh-symbolic",
                icon_type: St.IconType.SYMBOLIC,
                icon_size: 14,
            }),
        });
        refreshBtn.connect("clicked", () => {
            this._showToast("info", "Atualizando telemetria...");
            this._refreshNow();
        });
        this._headerBox.add_child(refreshBtn);
    }

    _renderTabBar() {
        this._cancelTabHoverTimer();
        this._tabBar.destroy_all_children();
        let tabs = [
            { id: "peripherals", label: "Perifericos", icon: "input-mouse-symbolic" },
            { id: "audio", label: "Áudio", icon: "audio-headphones-symbolic" },
            { id: "system", label: "Sistema", icon: "utilities-system-monitor-symbolic" },
            { id: "antigravity", label: "Antigravity VU", icon: "applications-science-symbolic" },
            { id: "settings", label: "Ajustes", icon: "preferences-system-symbolic" },
        ];

        for (let tab of tabs) {
            let active = this._activeTab === tab.id;
            let content = new St.BoxLayout({
                style: "spacing: 5px;",
                x_align: Clutter.ActorAlign.CENTER,
                y_align: Clutter.ActorAlign.CENTER,
            });
            content.add_child(new St.Icon({
                icon_name: tab.icon,
                icon_type: St.IconType.SYMBOLIC,
                icon_size: 13,
            }));
            content.add_child(new St.Label({
                text: tab.label,
                y_align: Clutter.ActorAlign.CENTER,
            }));

            let btn = new St.Button({
                style_class: active ? "dpi-tab-btn dpi-tab-btn-active" : "dpi-tab-btn",
                x_expand: true,
                can_focus: true,
                child: content,
            });
            btn.connect("clicked", () => {
                this._cancelTabHoverTimer();
                if (this._activeTab !== tab.id) {
                    this._switchTab(tab.id, true);
                }
            });
            btn.connect("enter-event", () => {
                this._cancelTabHoverTimer();
                if (this._activeTab !== tab.id && this.menu && this.menu.isOpen) {
                    this._tabHoverTimerId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 110, () => {
                        this._tabHoverTimerId = 0;
                        if (!this._destroyed && this.menu && this.menu.isOpen && this._activeTab !== tab.id) {
                            this._switchTab(tab.id, true);
                        }
                        return GLib.SOURCE_REMOVE;
                    });
                }
                return Clutter.EVENT_PROPAGATE;
            });
            btn.connect("leave-event", () => {
                this._cancelTabHoverTimer();
                return Clutter.EVENT_PROPAGATE;
            });
            this._tabBar.add_child(btn);
        }
    }

    _renderToastBanner() {
        if (!this._toastBox) return;
        this._toastBox.destroy_all_children();
        if (!this._toastState || !this._toastState.message) {
            this._toastBox.hide();
            return;
        }
        let iconName = this._toastState.kind === "error"
            ? "dialog-warning-symbolic"
            : (this._toastState.kind === "ok" ? "security-high-symbolic" : "system-run-symbolic");

        let row = new St.BoxLayout({
            style_class: "dpi-toast dpi-toast-" + this._toastState.kind,
            x_expand: true,
            y_align: Clutter.ActorAlign.CENTER,
        });
        row.add_child(new St.Icon({
            icon_name: iconName,
            icon_type: St.IconType.SYMBOLIC,
            icon_size: 14,
        }));
        let lbl = new St.Label({
            text: this._toastState.message,
            x_expand: true,
            y_align: Clutter.ActorAlign.CENTER,
        });
        lbl.clutter_text.line_wrap = true;
        lbl.clutter_text.line_wrap_mode = Pango.WrapMode.WORD_CHAR;
        lbl.clutter_text.ellipsize = Pango.EllipsizeMode.NONE;
        row.add_child(lbl);

        this._toastBox.add_child(row);
        this._toastBox.show();
    }

    /* ======================================================================
     * Tab 1: Peripherals Bento Grid
     * ====================================================================== */

    _renderPeripheralsTab() {
        let devices = this._getDevicesMap();
        let threshold = (this._data && this._data.settings && Number(this._data.settings.battery_alert_threshold)) || 20;

        let grid = new St.BoxLayout({
            style_class: "dpi-bento-grid",
            style: "spacing: 10px;",
            x_expand: true,
        });

        // Left Column: Mouse AJAZZ + Headset Havit Fuxi H3
        let colLeft = new St.BoxLayout({
            vertical: true,
            style_class: "dpi-bento-col",
            style: "spacing: 8px; width: 336px;",
            x_expand: false,
        });
        colLeft.add_child(this._buildMouseCard(devices.mouse || {}, threshold));
        colLeft.add_child(this._buildHeadsetCard(devices.headset || {}, threshold));
        grid.add_child(colLeft);

        // Right Column: Controles GameSir/EasySMX + Teclado Machenike K500
        let colRight = new St.BoxLayout({
            vertical: true,
            style_class: "dpi-bento-col",
            style: "spacing: 8px; width: 336px;",
            x_expand: false,
        });
        colRight.add_child(this._buildGamepadCard(devices.gamepad || {}, threshold));
        colRight.add_child(this._buildKeyboardCard(devices.keyboard || {}));
        grid.add_child(colRight);

        this._bodyStack.add_child(grid);
    }

    _buildMouseCard(mouse, threshold) {
        let expanded = Boolean(this._expandedCards.mouse);
        let card = new St.BoxLayout({ vertical: true, style_class: "dpi-card", x_expand: true });

        let pState = mouse.power_state || (mouse.connected && !mouse.standby ? "active" : (mouse.standby ? "sleep" : "off"));
        let connType = mouse.connection_type || (mouse.connected ? "2.4GHz" : "Desconectado");
        let bat = mouse.battery;
        let batLabel = bat !== null && bat !== undefined ? bat + "%" : (pState === "sleep" ? "Descanso" : (pState === "off" ? "Off" : "--"));
        let tone = pState === "off" ? "muted" : (mouse.charging ? "ok" : (pState === "sleep" ? "warn" : pctSeverityClass(bat, threshold)));

        let iconName = "input-mouse-symbolic";
        if (mouse.charging) {
            iconName = "battery-full-charging-symbolic";
        } else if (pState === "sleep") {
            iconName = "dpi-mouse-sleep-symbolic";
        }

        let badgeText = connType;
        let badgeTone = "muted";
        if (mouse.charging) {
            badgeText = connType + " / Chg";
            badgeTone = "ok";
        } else if (pState === "sleep") {
            badgeText = "Descanso";
            badgeTone = "warn";
        } else if (pState === "off") {
            badgeText = "Desligado";
            badgeTone = "muted";
        } else if (mouse.connected) {
            badgeText = connType;
            badgeTone = "info";
        }

        let header = this._buildCardHeader({
            cardKey: "mouse",
            icon: iconName,
            title: "AJAZZ AJ179 V2",
            badgeText: badgeText,
            badgeTone: badgeTone,
            metricText: batLabel,
            metricTone: tone,
            expanded: expanded,
        });
        card.add_child(header);

        if (bat !== null && bat !== undefined) {
            card.add_child(this._makeProgressBar(bat, tone, null));
        }

        if (expanded) {
            let body = new St.BoxLayout({ vertical: true, style_class: "dpi-card-body", x_expand: true });
            this._animateCardBody(body, "mouse");

            // DPI Presets (combines hardware dpi_stages with standard presets, sorted & deduplicated)
            let curDpi = Number(mouse.current_dpi) || 0;
            let dpiSet = {};
            if (Array.isArray(mouse.dpi_stages) && mouse.dpi_stages.length > 0) {
                for (let rawStage of mouse.dpi_stages) {
                    let v = Math.round(Number(rawStage));
                    if (isFinite(v) && v >= 50 && v <= 26000) {
                        dpiSet[v] = true;
                    }
                }
            }
            for (let preset of DPI_PRESETS) {
                dpiSet[preset] = true;
            }
            if (isFinite(curDpi) && curDpi >= 50 && curDpi <= 26000) {
                dpiSet[Math.round(curDpi)] = true;
            }
            let dpiOptions = Object.keys(dpiSet)
                .map((k) => Number(k))
                .sort((a, b) => a - b);

            body.add_child(this._makeSectionLabel("DPI SENSOR" + (curDpi ? " (" + curDpi + ")" : "")));
            let rowSize = dpiOptions.length <= 6 ? dpiOptions.length : Math.ceil(dpiOptions.length / 2);
            for (let i = 0; i < dpiOptions.length; i += rowSize) {
                let slice = dpiOptions.slice(i, i + rowSize);
                body.add_child(this._makeChipRow(
                    slice.map((v) => ({ label: String(v), value: v })),
                    curDpi,
                    (v) => this._dispatchCliAction(["--set-dpi", String(v)], "Aplicando " + v + " DPI...")
                ));
            }

            // Polling Rate
            let curPoll = Number(mouse.polling_rate) || 0;
            body.add_child(this._makeSectionLabel("POLLING RATE (HZ)"));
            body.add_child(this._makeChipRow(
                POLLING_PRESETS.map((hz) => ({ label: hz + " Hz", value: hz })),
                curPoll,
                (hz) => this._dispatchCliAction(["--set-polling", String(hz)], "Definindo " + hz + " Hz...")
            ));

            // LED Color Swatches
            let curColor = String(mouse.led_color || "").toUpperCase();
            body.add_child(this._makeSectionLabel("COR LED LATERAL"));
            let swatchRow = new St.BoxLayout({ style_class: "dpi-chip-row", y_align: Clutter.ActorAlign.CENTER });
            for (let hex of MOUSE_LED_COLORS) {
                let active = curColor === hex.toUpperCase();
                let swatch = new St.Button({
                    style_class: active ? "dpi-color-swatch dpi-color-swatch-active" : "dpi-color-swatch",
                    can_focus: true,
                    style: "background-color: " + hex + ";",
                });
                swatch.connect("clicked", () => {
                    this._dispatchCliAction(["--set-mouse-led", hex], "Aplicando LED " + hex + "...");
                });
                swatchRow.add_child(swatch);
            }
            body.add_child(swatchRow);

            // Sleep Timeout
            let curSleep = Number(mouse.sleep_seconds) || 0;
            body.add_child(this._makeSectionLabel("DEEP SLEEP"));
            body.add_child(this._makeChipRow(
                MOUSE_SLEEP_PRESETS,
                curSleep,
                (secs) => this._dispatchCliAction(["--set-mouse-sleep", String(secs)], "Definindo sleep para " + secs + "s...")
            ));

            card.add_child(body);
        }

        return card;
    }

    _buildHeadsetCard(headset, threshold) {
        let expanded = Boolean(this._expandedCards.headset);
        let card = new St.BoxLayout({ vertical: true, style_class: "dpi-card", x_expand: true });

        let connType = headset.connection_type || (headset.connected ? "2.4GHz" : "Desconectado");
        let bat = headset.battery;
        let vol = headset.volume !== null && headset.volume !== undefined ? Number(headset.volume) : null;
        let metricText = bat !== null && bat !== undefined
            ? bat + "%"
            : (vol !== null ? (headset.muted ? "MUTE" : vol + "%") : "--");
        let tone = !headset.connected ? "muted" : (bat !== null && bat !== undefined ? pctSeverityClass(bat, threshold) : "info");

        let header = this._buildCardHeader({
            cardKey: "headset",
            icon: "audio-headphones-symbolic",
            title: "Havit Fuxi H3",
            badgeText: connType,
            badgeTone: headset.connected ? (connType === "Bluetooth" ? "info" : "ok") : "muted",
            metricText: metricText,
            metricTone: tone,
            expanded: expanded,
        });
        card.add_child(header);

        if (bat !== null && bat !== undefined) {
            card.add_child(this._makeProgressBar(bat, tone, null));
        }

        if (expanded) {
            let body = new St.BoxLayout({ vertical: true, style_class: "dpi-card-body", x_expand: true });
            this._animateCardBody(body, "headset");

            // Volume Controls
            let curVol = vol !== null ? vol : 70;
            body.add_child(this._makeSectionLabel("VOLUME" + (headset.muted ? " (MUDO)" : " (" + curVol + "%)")));
            let volRow = new St.BoxLayout({ style_class: "dpi-chip-row", x_expand: true });

            let volButtons = [
                { label: "-10%", delta: -10 },
                { label: "-5%", delta: -5 },
                { label: headset.muted ? "Unmute" : "Mute", mute: true },
                { label: "+5%", delta: 5 },
                { label: "+10%", delta: 10 },
            ];
            for (let b of volButtons) {
                let cls = b.mute && headset.muted ? "dpi-chip dpi-chip-active" : "dpi-chip";
                let btn = new St.Button({ label: b.label, style_class: cls, x_expand: true, can_focus: true });
                btn.connect("clicked", () => {
                    if (b.mute) {
                        this._dispatchCliAction(["--toggle-mute"], "Alternando mudo...");
                    } else {
                        let nextVol = clamp(curVol + b.delta, 0, 100);
                        this._dispatchCliAction(["--set-volume", String(nextVol)], "Ajustando volume para " + nextVol + "%...");
                    }
                });
                volRow.add_child(btn);
            }
            body.add_child(volRow);

            // ALSA Fix & Sidetone
            let actionRow = new St.BoxLayout({ style_class: "dpi-chip-row", x_expand: true });
            let alsaBtn = this._makeActionButton(
                "audio-volume-high-symbolic",
                "Corrigir Volume ALSA",
                headset.alsa_zero_bug ? "warn" : "default",
                () => this._dispatchCliAction(["--fix-alsa"], "Corrigindo volume ALSA FuxiH3...")
            );
            actionRow.add_child(alsaBtn);

            let sidetoneOn = Boolean(headset.sidetone);
            let sidetoneBtn = this._makeActionButton(
                "audio-headphones-symbolic",
                sidetoneOn ? "Sidetone: ON" : "Sidetone: OFF",
                sidetoneOn ? "primary" : "default",
                () => this._dispatchCliAction(
                    ["--set-sidetone", sidetoneOn ? "off" : "on"],
                    (sidetoneOn ? "Desativando" : "Ativando") + " sidetone..."
                )
            );
            actionRow.add_child(sidetoneBtn);
            body.add_child(actionRow);

            // Audio Profile Selector
            let profiles = Array.isArray(headset.available_profiles) ? headset.available_profiles : [];
            if (profiles.length > 0) {
                body.add_child(this._makeSectionLabel("PERFIL DE AUDIO"));
                let prioritized = profiles.filter((p) => p === headset.active_profile);
                for (let p of profiles) {
                    if (prioritized.length >= 4) break;
                    if (prioritized.indexOf(p) === -1) prioritized.push(p);
                }
                body.add_child(this._makeChipRow(
                    prioritized.map((p) => {
                        let id = typeof p === "string" ? p : (p.id || p.name);
                        let label = typeof p === "string" ? formatAudioProfileName(id) : (p.label || formatAudioProfileName(id));
                        return { label: label, value: id };
                    }),
                    headset.active_profile || "",
                    (prof) => this._dispatchCliAction(["--set-audio-profile", String(prof)], "Alterando perfil de audio...")
                ));
            }

            // EQ Presets
            let curEq = String(headset.eq_preset || "flat").toLowerCase();
            body.add_child(this._makeSectionLabel("PRESET DE EQ"));
            body.add_child(this._makeChipRow(
                EQ_PRESETS.map((e) => ({ label: e.label, value: e.id })),
                curEq,
                (preset) => this._dispatchCliAction(["--set-eq", preset], "Aplicando EQ " + preset + "...")
            ));

            card.add_child(body);
        }

        return card;
    }

    _buildGamepadCard(gamepad, threshold) {
        let expanded = Boolean(this._expandedCards.gamepad);
        let card = new St.BoxLayout({ vertical: true, style_class: "dpi-card", x_expand: true });

        let controllers = Array.isArray(gamepad.controllers) ? gamepad.controllers : [];
        let activeCount = controllers.filter((c) => c.active).length;
        let chargingAny = controllers.some((c) => c.charging);
        let statusText = "Standby";
        let statusTone = "muted";

        if (chargingAny) {
            statusText = "Carregando USB-C + 2.4G";
            statusTone = "ok";
        } else if (activeCount > 0 || gamepad.active) {
            statusText = "Ativo";
            statusTone = "ok";
        } else if (gamepad.connected || controllers.length > 0) {
            statusText = "Standby";
            statusTone = "warn";
        }

        let header = this._buildCardHeader({
            cardKey: "gamepad",
            icon: "dpi-gamepad-symbolic",
            title: "Controles GameSir / EasySMX",
            badgeText: statusText,
            badgeTone: statusTone,
            metricText: controllers.length ? String(controllers.length) + "x" : "0",
            metricTone: statusTone,
            expanded: expanded,
        });
        card.add_child(header);

        if (expanded) {
            let body = new St.BoxLayout({ vertical: true, style_class: "dpi-card-body", x_expand: true });
            this._animateCardBody(body, "gamepad");

            if (controllers.length === 0) {
                body.add_child(new St.Label({
                    text: "Nenhum controle detectado no barramento (GameSir Nova Lite / EasySMX 9124).",
                    style_class: "dpi-subtitle",
                }));
            } else {
                for (let ctrl of controllers) {
                    let sub = new St.BoxLayout({ vertical: true, style_class: "dpi-subcard", x_expand: true });

                    let topRow = new St.BoxLayout({ style: "spacing: 6px;", y_align: Clutter.ActorAlign.CENTER });
                    topRow.add_child(new St.Label({
                        text: ctrl.name || ctrl.brand || "Gamepad",
                        style_class: "dpi-card-title",
                        x_expand: true,
                    }));

                    let cStatus = ctrl.charging
                        ? "Carregando USB-C + 2.4G"
                        : (ctrl.active ? "Ativo" : "Standby");
                    let cTone = ctrl.charging || ctrl.active ? "ok" : "warn";
                    topRow.add_child(this._makeBadge(cStatus, cTone));
                    sub.add_child(topRow);

                    if (ctrl.connection_type) {
                        let metaText = ctrl.connection_type;
                        if (ctrl.battery !== null && ctrl.battery !== undefined) {
                            metaText += " | Bateria " + ctrl.battery + "%";
                        }
                        sub.add_child(new St.Label({ text: metaText, style_class: "dpi-subtitle" }));
                    }

                    // Layout Xbox / Nintendo + Rumble Test
                    let ctrlId = ctrl.id || "";
                    let curLayout = String(ctrl.layout || "xbox").toLowerCase();
                    let actionRow = new St.BoxLayout({ style_class: "dpi-chip-row", x_expand: true });

                    for (let lay of [{ id: "xbox", label: "Xbox" }, { id: "nintendo", label: "Nintendo" }]) {
                        let btn = new St.Button({
                            label: lay.label,
                            style_class: curLayout === lay.id ? "dpi-chip dpi-chip-active" : "dpi-chip",
                            can_focus: true,
                        });
                        btn.connect("clicked", () => {
                            let args = ["--set-gamepad-layout", lay.id];
                            if (ctrlId) args.push("--controller-id", ctrlId);
                            this._dispatchCliAction(args, "Alterando layout para " + lay.label + "...");
                        });
                        actionRow.add_child(btn);
                    }

                    let rumbleBtn = this._makeActionButton(
                        "media-playback-start-symbolic",
                        "Testar Vibracao",
                        "primary",
                        () => {
                            let args = ["--test-rumble"];
                            if (ctrlId) args.push("--controller-id", ctrlId);
                            this._dispatchCliAction(args, "Testando motores de vibracao...");
                        }
                    );
                    actionRow.add_child(rumbleBtn);
                    sub.add_child(actionRow);

                    // Deadzone
                    let curDz = Number(ctrl.deadzone_pct);
                    if (isNaN(curDz)) curDz = 5;
                    sub.add_child(this._makeSectionLabel("DEADZONE (" + curDz + "%)"));
                    sub.add_child(this._makeChipRow(
                        DEADZONE_PRESETS.map((dz) => ({ label: dz + "%", value: dz })),
                        curDz,
                        (dz) => {
                            let args = ["--set-deadzone", String(dz)];
                            if (ctrlId) args.push("--controller-id", ctrlId);
                            this._dispatchCliAction(args, "Aplicando deadzone " + dz + "%...");
                        }
                    ));

                    body.add_child(sub);
                }
            }

            card.add_child(body);
        }

        return card;
    }

    _buildKeyboardCard(keyboard) {
        let expanded = Boolean(this._expandedCards.keyboard);
        let card = new St.BoxLayout({ vertical: true, style_class: "dpi-card", x_expand: true });

        let header = this._buildCardHeader({
            cardKey: "keyboard",
            icon: "input-keyboard-symbolic",
            title: "Machenike K500-B94",
            badgeText: "Hardware Safe Mode",
            badgeTone: "safe",
            metricText: keyboard.connected ? "USB" : "OFF",
            metricTone: keyboard.connected ? "info" : "muted",
            expanded: expanded,
        });
        card.add_child(header);

        // Lock badges row (CAPS, NUM, SCROLL)
        let leds = keyboard.leds || {};
        let locksRow = new St.BoxLayout({ style: "spacing: 6px;", y_align: Clutter.ActorAlign.CENTER });
        let lockSpecs = [
            { label: "CAPS", on: Boolean(leds.capslock) },
            { label: "NUM", on: Boolean(leds.numlock) },
            { label: "SCROLL", on: Boolean(leds.scrolllock) },
        ];
        for (let lk of lockSpecs) {
            locksRow.add_child(new St.Label({
                text: lk.label,
                style_class: lk.on ? "dpi-kbd-badge dpi-kbd-badge-on" : "dpi-kbd-badge",
            }));
        }
        let safePill = new St.BoxLayout({ style: "spacing: 4px;", x_expand: true, x_align: Clutter.ActorAlign.END });
        safePill.add_child(new St.Icon({
            icon_name: "security-high-symbolic",
            icon_type: St.IconType.SYMBOLIC,
            icon_size: 12,
        }));
        safePill.add_child(new St.Label({
            text: "Leitura Passiva",
            style_class: "dpi-subtitle",
        }));
        locksRow.add_child(safePill);
        card.add_child(locksRow);

        if (expanded) {
            let body = new St.BoxLayout({ vertical: true, style_class: "dpi-card-body", x_expand: true });
            this._animateCardBody(body, "keyboard");
            body.add_child(this._makeSectionLabel("ATALHOS FISICOS (PROTECAO MCU SINO WEALTH)"));

            let shortcuts = Array.isArray(keyboard.shortcuts) && keyboard.shortcuts.length > 0
                ? keyboard.shortcuts
                : K500_DEFAULT_SHORTCUTS;

            for (let sc of shortcuts) {
                let keys = typeof sc === "string" ? sc : (sc.keys || sc.shortcut || "");
                let desc = typeof sc === "string" ? "" : (sc.desc || sc.description || sc.action || "");
                let row = new St.BoxLayout({ style_class: "dpi-shortcut-row", y_align: Clutter.ActorAlign.CENTER });
                row.add_child(new St.Label({ text: keys, style_class: "dpi-kbd-key" }));
                if (desc) {
                    let dl = new St.Label({ text: desc, style_class: "dpi-subtitle", x_expand: true });
                    dl.clutter_text.ellipsize = Pango.EllipsizeMode.END;
                    row.add_child(dl);
                }
                body.add_child(row);
            }
            card.add_child(body);
        }

        return card;
    }

    /* ======================================================================
     * Tab: Áudio & Mídia (Spotify MPRIS2 & Mixer Volum)
     * ====================================================================== */

    _renderAudioTab() {
        let media = (this._data && this._data.media) || {};
        let audio = (this._data && this._data.audio) || {};

        let grid = new St.BoxLayout({
            style_class: "dpi-bento-grid",
            style: "spacing: 10px;",
            x_expand: true,
        });

        // Left Column: Player Spotify/MPRIS2 + Mixer por Aplicativo (Volum)
        let colLeft = new St.BoxLayout({
            vertical: true,
            style_class: "dpi-bento-col",
            style: "spacing: 8px; width: 336px;",
            x_expand: false,
        });
        colLeft.add_child(this._buildMediaPlayerCard(media));
        colLeft.add_child(this._buildPerAppAudioCard(audio));
        grid.add_child(colLeft);

        // Right Column: Saída Principal (Master) + Microfone
        let colRight = new St.BoxLayout({
            vertical: true,
            style_class: "dpi-bento-col",
            style: "spacing: 8px; width: 336px;",
            x_expand: false,
        });
        colRight.add_child(this._buildAudioMixerCard(audio));
        grid.add_child(colRight);

        this._bodyStack.add_child(grid);
    }

    _buildMediaPlayerCard(media) {
        let expanded = this._expandedCards.media !== false;
        let card = new St.BoxLayout({ vertical: true, style_class: "dpi-card", x_expand: true });

        let isAvailable = Boolean(media && media.available);
        let isPlaying = isAvailable && media.status === "Playing";
        let isPaused = isAvailable && media.status === "Paused";

        let statusBadge = isPlaying ? "Tocando" : (isPaused ? "Pausado" : "Inativo");
        let statusTone = isPlaying ? "ok" : "muted";

        let timeStr = "";
        if (isAvailable && media.length_sec) {
            timeStr = formatSecondsToTime(media.position_sec) + " / " + formatSecondsToTime(media.length_sec);
        }

        let header = this._buildCardHeader({
            cardKey: "media",
            icon: "multimedia-player-symbolic",
            title: media.player_name || "Spotify",
            badgeText: statusBadge,
            badgeTone: statusTone,
            metricText: timeStr,
            expanded: expanded,
        });
        card.add_child(header);

        if (expanded) {
            let body = new St.BoxLayout({ vertical: true, style_class: "dpi-card-body", style: "spacing: 8px;", x_expand: true });
            this._animateCardBody(body, "media");

            if (!isAvailable) {
                let inactiveLabel = new St.Label({
                    text: "Spotify / Mídia inativo — abra um player para controlar",
                    style_class: "dpi-subtitle",
                });
                body.add_child(inactiveLabel);
            } else {
                // Track Title & Artist
                let trackBox = new St.BoxLayout({ vertical: true, style: "spacing: 2px;" });
                let titleLabel = new St.Label({
                    text: media.title || "Sem título",
                    style_class: "dpi-media-title",
                });
                titleLabel.clutter_text.ellipsize = Pango.EllipsizeMode.END;
                trackBox.add_child(titleLabel);

                let subtitle = media.artist || "Artista desconhecido";
                if (media.album) subtitle += " · " + media.album;
                let artistLabel = new St.Label({
                    text: subtitle,
                    style_class: "dpi-subtitle",
                });
                artistLabel.clutter_text.ellipsize = Pango.EllipsizeMode.END;
                trackBox.add_child(artistLabel);
                body.add_child(trackBox);

                // Progress Bar with Time Labels
                let progressRow = new St.BoxLayout({
                    style: "spacing: 8px;",
                    x_align: Clutter.ActorAlign.CENTER,
                    y_align: Clutter.ActorAlign.CENTER,
                    x_expand: true,
                });
                let posLabel = new St.Label({
                    text: formatSecondsToTime(media.position_sec),
                    style_class: "dpi-subtitle",
                    y_align: Clutter.ActorAlign.CENTER,
                });
                let lenLabel = new St.Label({
                    text: formatSecondsToTime(media.length_sec),
                    style_class: "dpi-subtitle",
                    y_align: Clutter.ActorAlign.CENTER,
                });
                progressRow.add_child(posLabel);
                let progressPct = clamp(Number(media.progress_pct) || 0, 0, 100);
                progressRow.add_child(this._makeProgressBar(progressPct, "purple", null, 210));
                progressRow.add_child(lenLabel);
                body.add_child(progressRow);

                // Transport Controls
                let controlsRow = new St.BoxLayout({
                    style_class: "dpi-media-controls",
                    style: "spacing: 14px;",
                    x_align: Clutter.ActorAlign.CENTER,
                    y_align: Clutter.ActorAlign.CENTER,
                    x_expand: true,
                });

                let prevBtn = this._makeActionButton(
                    "media-skip-backward-symbolic",
                    "",
                    null,
                    () => this._dispatchCliAction(["--media-prev"], "Faixa anterior...")
                );
                let playPauseIcon = isPlaying ? "media-playback-pause-symbolic" : "media-playback-start-symbolic";
                let playPauseBtn = this._makeActionButton(
                    playPauseIcon,
                    "",
                    "primary",
                    () => this._dispatchCliAction(["--media-play-pause"], "Play/Pause...")
                );
                let nextBtn = this._makeActionButton(
                    "media-skip-forward-symbolic",
                    "",
                    null,
                    () => this._dispatchCliAction(["--media-next"], "Próxima faixa...")
                );

                controlsRow.add_child(prevBtn);
                controlsRow.add_child(playPauseBtn);
                controlsRow.add_child(nextBtn);
                body.add_child(controlsRow);
            }

            card.add_child(body);
        }

        return card;
    }

    _buildAudioMixerCard(audio) {
        let expanded = this._expandedCards.master_audio !== false;
        let card = new St.BoxLayout({ vertical: true, style_class: "dpi-card", x_expand: true });

        let master = (audio && audio.master) || {};
        let mic = (audio && audio.mic) || {};
        let masterVol = Number(master.volume) || 0;
        let masterMuted = Boolean(master.muted);

        let header = this._buildCardHeader({
            cardKey: "master_audio",
            icon: masterMuted ? "audio-volume-muted-symbolic" : "audio-volume-high-symbolic",
            title: "Mixer Master & Microfone",
            badgeText: masterMuted ? "Mudo" : masterVol + "%",
            badgeTone: masterMuted ? "warn" : "ok",
            expanded: expanded,
        });
        card.add_child(header);

        if (expanded) {
            let body = new St.BoxLayout({ vertical: true, style_class: "dpi-card-body", style: "spacing: 10px;", x_expand: true });
            this._animateCardBody(body, "master_audio");

            // --- Section: Master Output ---
            body.add_child(this._makeSectionLabel("SAÍDA PRINCIPAL (MASTER)"));

            let outDesc = master.description || master.name || "Saída Padrão";
            let outLabel = new St.Label({ text: outDesc, style_class: "dpi-subtitle" });
            outLabel.clutter_text.ellipsize = Pango.EllipsizeMode.END;
            body.add_child(outLabel);

            body.add_child(this._makeProgressBar(Math.min(100, masterVol), masterMuted ? "warn" : "ok", null, 290));

            // Controls row: Mute + Steps
            let masterCtrlRow = new St.BoxLayout({ style: "spacing: 6px;", x_expand: true });
            masterCtrlRow.add_child(this._makeActionButton(
                masterMuted ? "audio-volume-muted-symbolic" : "audio-volume-high-symbolic",
                masterMuted ? "Desmutar" : "Mudo",
                masterMuted ? "warn" : null,
                () => this._dispatchCliAction(["--toggle-master-mute"], "Alternando mute master...")
            ));
            masterCtrlRow.add_child(this._makeActionButton(
                null,
                "-5%",
                null,
                () => this._dispatchCliAction(["--set-master-volume", String(Math.max(0, masterVol - 5))], "Volume -5%...")
            ));
            masterCtrlRow.add_child(this._makeActionButton(
                null,
                "+5%",
                null,
                () => this._dispatchCliAction(["--set-master-volume", String(Math.min(150, masterVol + 5))], "Volume +5%...")
            ));
            body.add_child(masterCtrlRow);

            // Volume Presets (25%, 50%, 75%, 100%)
            let volPresets = [
                { label: "25%", value: 25 },
                { label: "50%", value: 50 },
                { label: "75%", value: 75 },
                { label: "100%", value: 100 },
            ];
            body.add_child(this._makeChipRow(
                volPresets,
                masterVol,
                (v) => this._dispatchCliAction(["--set-master-volume", String(v)], "Volume Master " + v + "%...")
            ));

            // Output Sinks Switcher
            let outputs = Array.isArray(audio.outputs) ? audio.outputs : [];
            if (outputs.length > 0) {
                body.add_child(this._makeSectionLabel("DISPOSITIVO DE SAÍDA"));
                let defaultOut = outputs.find((o) => o.is_default) || outputs[0];
                let sinkChips = outputs.map((o) => ({
                    label: o.short_name || o.description || o.name,
                    value: o.name,
                }));
                body.add_child(this._makeChipRow(
                    sinkChips,
                    defaultOut ? defaultOut.name : null,
                    (sinkName) => this._dispatchCliAction(["--set-default-sink", sinkName], "Definindo saída de áudio...")
                ));
            }

            // --- Section: Microphone ---
            body.add_child(this._makeSectionLabel("MICROFONE"));

            let micVol = Number(mic.volume) || 0;
            let micMuted = Boolean(mic.muted);
            let micDesc = mic.description || mic.name || "Microfone Padrão";
            let micLabel = new St.Label({ text: micDesc, style_class: "dpi-subtitle" });
            micLabel.clutter_text.ellipsize = Pango.EllipsizeMode.END;
            body.add_child(micLabel);

            body.add_child(this._makeProgressBar(Math.min(100, micVol), micMuted ? "warn" : "info", null, 290));

            let micCtrlRow = new St.BoxLayout({ style: "spacing: 6px;", x_expand: true });
            micCtrlRow.add_child(this._makeActionButton(
                micMuted ? "microphone-sensitivity-muted-symbolic" : "audio-input-microphone-symbolic",
                micMuted ? "Desmutar" : "Mudo",
                micMuted ? "warn" : null,
                () => this._dispatchCliAction(["--toggle-mic-mute"], "Alternando mute mic...")
            ));
            micCtrlRow.add_child(this._makeActionButton(
                null,
                "-10%",
                null,
                () => this._dispatchCliAction(["--set-mic-volume", String(Math.max(0, micVol - 10))], "Ganho mic -10%...")
            ));
            micCtrlRow.add_child(this._makeActionButton(
                null,
                "+10%",
                null,
                () => this._dispatchCliAction(["--set-mic-volume", String(Math.min(150, micVol + 10))], "Ganho mic +10%...")
            ));
            body.add_child(micCtrlRow);

            // Input Sources Switcher (if > 1)
            let inputs = Array.isArray(audio.inputs) ? audio.inputs : [];
            if (inputs.length > 1) {
                body.add_child(this._makeSectionLabel("DISPOSITIVO DE ENTRADA"));
                let defaultIn = inputs.find((i) => i.is_default) || inputs[0];
                let srcChips = inputs.map((i) => ({
                    label: i.short_name || i.description || i.name,
                    value: i.name,
                }));
                body.add_child(this._makeChipRow(
                    srcChips,
                    defaultIn ? defaultIn.name : null,
                    (srcName) => this._dispatchCliAction(["--set-default-source", srcName], "Definindo microfone...")
                ));
            }

            card.add_child(body);
        }

        return card;
    }

    _buildPerAppAudioCard(audio) {
        let expanded = this._expandedCards.per_app_audio !== false;
        let card = new St.BoxLayout({ vertical: true, style_class: "dpi-card", x_expand: true });

        let apps = Array.isArray(audio && audio.apps) ? audio.apps : [];
        let header = this._buildCardHeader({
            cardKey: "per_app_audio",
            icon: "audio-card-symbolic",
            title: "Mixer por Aplicativo",
            badgeText: apps.length > 0 ? apps.length + " ativo(s)" : "Inativo",
            badgeTone: apps.length > 0 ? "info" : "muted",
            expanded: expanded,
        });
        card.add_child(header);

        if (expanded) {
            let body = new St.BoxLayout({ vertical: true, style_class: "dpi-card-body", style: "spacing: 8px;", x_expand: true });
            this._animateCardBody(body, "per_app_audio");

            if (apps.length === 0) {
                let emptyLabel = new St.Label({
                    text: "Nenhum aplicativo reproduzindo áudio no momento",
                    style_class: "dpi-subtitle",
                });
                body.add_child(emptyLabel);
            } else {
                for (let app of apps) {
                    let appBox = new St.BoxLayout({
                        vertical: true,
                        style_class: "dpi-app-audio-item",
                        style: "spacing: 4px;",
                        x_expand: true,
                    });

                    let topRow = new St.BoxLayout({
                        style: "spacing: 6px;",
                        y_align: Clutter.ActorAlign.CENTER,
                        x_expand: true,
                    });
                    topRow.add_child(new St.Icon({
                        icon_name: app.icon_name || "audio-x-generic-symbolic",
                        icon_type: St.IconType.SYMBOLIC,
                        icon_size: 14,
                    }));
                    let nameLabel = new St.Label({
                        text: app.app_name || ("Stream #" + app.id),
                        style_class: "dpi-bold",
                        x_expand: true,
                        y_align: Clutter.ActorAlign.CENTER,
                    });
                    nameLabel.clutter_text.ellipsize = Pango.EllipsizeMode.END;
                    topRow.add_child(nameLabel);

                    let appVol = Number(app.volume) || 0;
                    let appMuted = Boolean(app.muted);
                    topRow.add_child(new St.Label({
                        text: appMuted ? "Mudo" : appVol + "%",
                        style_class: "dpi-card-metric",
                        y_align: Clutter.ActorAlign.CENTER,
                    }));
                    appBox.add_child(topRow);

                    appBox.add_child(this._makeProgressBar(Math.min(100, appVol), appMuted ? "warn" : "info", null, 290));

                    let ctrlRow = new St.BoxLayout({ style: "spacing: 6px;", x_expand: true });
                    ctrlRow.add_child(this._makeActionButton(
                        appMuted ? "audio-volume-muted-symbolic" : "audio-volume-high-symbolic",
                        appMuted ? "Desmutar" : "Mudo",
                        appMuted ? "warn" : null,
                        () => this._dispatchCliAction(["--toggle-app-mute", String(app.id)], "Alternando mute " + app.app_name + "...")
                    ));
                    ctrlRow.add_child(this._makeActionButton(
                        null,
                        "-10%",
                        null,
                        () => this._dispatchCliAction(["--set-app-volume", String(app.id), String(Math.max(0, appVol - 10))], "Volume app -10%...")
                    ));
                    ctrlRow.add_child(this._makeActionButton(
                        null,
                        "+10%",
                        null,
                        () => this._dispatchCliAction(["--set-app-volume", String(app.id), String(Math.min(150, appVol + 10))], "Volume app +10%...")
                    ));
                    appBox.add_child(ctrlRow);

                    body.add_child(appBox);
                }
            }

            card.add_child(body);
        }

        return card;
    }

    /* ======================================================================
     * Tab: Sistema (Monitor de Sistema Nativo — FEAT-007)
     * ====================================================================== */

    _renderSystemTab() {
        let sys = (this._data && this._data.system) || {};
        let cpu = sys.cpu || {};
        let gpu = sys.gpu || {};
        let ram = sys.ram || {};
        let disk = sys.disk || {};
        let net = sys.network || sys.net || {};
        let uptimeStr = sys.uptime_str || (sys.uptime && sys.uptime.uptime_str) || "";

        let grid = new St.BoxLayout({
            style_class: "dpi-bento-grid",
            style: "spacing: 10px;",
            x_expand: true,
        });

        // Left Column: CPU + GPU
        let colLeft = new St.BoxLayout({
            vertical: true,
            style_class: "dpi-bento-col",
            style: "spacing: 8px; width: 336px;",
            x_expand: false,
        });
        colLeft.add_child(this._buildCpuCard(cpu, uptimeStr));
        colLeft.add_child(this._buildGpuCard(gpu));
        grid.add_child(colLeft);

        // Right Column: RAM + Disk & Net
        let colRight = new St.BoxLayout({
            vertical: true,
            style_class: "dpi-bento-col",
            style: "spacing: 8px; width: 336px;",
            x_expand: false,
        });
        colRight.add_child(this._buildRamCard(ram));
        colRight.add_child(this._buildDiskNetCard(disk, net));
        grid.add_child(colRight);

        this._bodyStack.add_child(grid);
    }

    _buildCpuCard(cpu, uptimeStr) {
        let expanded = this._expandedCards.sys_cpu !== false;
        let card = new St.BoxLayout({ vertical: true, style_class: "dpi-card", x_expand: true });

        let rawCpu = cpu && (cpu.usage_pct !== undefined ? cpu.usage_pct : cpu.cpu_pct);
        let cpuPct = clamp(Math.round(Number(rawCpu) || 0), 0, 100);
        let tone = sysSeverityClass(cpuPct, 60, 85);
        let tempVal = cpu ? (cpu.temp_c !== undefined ? cpu.temp_c : cpu.cpu_temp_c) : null;
        let tempText = tempVal !== null && tempVal !== undefined
            ? Math.round(Number(tempVal)) + "°C"
            : null;
        let tempTone = tempSeverityClass(tempVal);

        let header = this._buildCardHeader({
            cardKey: "sys_cpu",
            icon: "computer-symbolic",
            title: "Processador (CPU)",
            badgeText: tempText,
            badgeTone: tempTone,
            metricText: cpuPct + "%",
            expanded: expanded,
        });
        card.add_child(header);

        if (expanded) {
            let body = new St.BoxLayout({ vertical: true, style_class: "dpi-card-body", style: "spacing: 8px;", x_expand: true });
            this._animateCardBody(body, "sys_cpu");

            body.add_child(this._makeProgressBar(cpuPct, tone, null, 290));

            let coresText = cpu && cpu.cores ? cpu.cores + " núcleos" : "";
            let load1m = cpu && cpu.load_1m !== undefined ? "Load: " + Number(cpu.load_1m).toFixed(2) : "";
            let detParts = [coresText, load1m].filter(Boolean);
            if (uptimeStr) detParts.push("Uptime: " + uptimeStr);

            let subLabel = new St.Label({
                text: detParts.join(" · ") || "CPU Ativa",
                style_class: "dpi-subtitle",
            });
            subLabel.clutter_text.ellipsize = Pango.EllipsizeMode.END;
            body.add_child(subLabel);

            card.add_child(body);
        }

        return card;
    }

    _buildGpuCard(gpu) {
        let expanded = this._expandedCards.sys_gpu !== false;
        let card = new St.BoxLayout({ vertical: true, style_class: "dpi-card", x_expand: true });

        let rawGpu = gpu && (gpu.usage_pct !== undefined ? gpu.usage_pct : gpu.gpu_pct);
        let gpuPct = clamp(Math.round(Number(rawGpu) || 0), 0, 100);
        let tempVal = gpu ? (gpu.temp_c !== undefined ? gpu.temp_c : gpu.gpu_temp_c) : null;
        let tempText = tempVal !== null && tempVal !== undefined
            ? Math.round(Number(tempVal)) + "°C"
            : null;
        let tempTone = tempSeverityClass(tempVal);

        let header = this._buildCardHeader({
            cardKey: "sys_gpu",
            icon: "video-display-symbolic",
            title: "Placa Gráfica (GPU)",
            badgeText: tempText,
            badgeTone: tempTone,
            metricText: gpuPct + "%",
            expanded: expanded,
        });
        card.add_child(header);

        if (expanded) {
            let body = new St.BoxLayout({ vertical: true, style_class: "dpi-card-body", style: "spacing: 8px;", x_expand: true });
            this._animateCardBody(body, "sys_gpu");

            body.add_child(this._makeSectionLabel("USO DA GPU"));
            body.add_child(this._makeProgressBar(gpuPct, sysSeverityClass(gpuPct, 70, 90), null, 290));

            let vramUsed = Number(gpu && gpu.vram_used_gb) || 0;
            let vramTotal = Number(gpu && gpu.vram_total_gb) || 0;
            let vramPct = clamp(Math.round(Number(gpu && gpu.vram_pct) || 0), 0, 100);

            body.add_child(this._makeSectionLabel("MEMÓRIA DE VÍDEO (VRAM)"));
            let vramSubText = (vramTotal > 0 ? vramUsed.toFixed(1) + " / " + vramTotal.toFixed(1) + " GB · " : "") + vramPct + "%";
            let vramLabel = new St.Label({
                text: vramSubText,
                style_class: "dpi-subtitle",
            });
            body.add_child(vramLabel);
            body.add_child(this._makeProgressBar(vramPct, sysSeverityClass(vramPct, 75, 90), null, 290));

            card.add_child(body);
        }

        return card;
    }

    _buildRamCard(ram) {
        let expanded = this._expandedCards.sys_ram !== false;
        let card = new St.BoxLayout({ vertical: true, style_class: "dpi-card", x_expand: true });

        let rawRam = ram && (ram.used_pct !== undefined ? ram.used_pct : ram.ram_pct);
        let ramPct = clamp(Math.round(Number(rawRam) || 0), 0, 100);
        let ramUsed = Number(ram && (ram.used_gb !== undefined ? ram.used_gb : ram.ram_used_gb)) || 0;
        let ramTotal = Number(ram && (ram.total_gb !== undefined ? ram.total_gb : ram.ram_total_gb)) || 0;

        let badgeStr = ramTotal > 0 ? ramUsed.toFixed(1) + " GB" : null;

        let header = this._buildCardHeader({
            cardKey: "sys_ram",
            icon: "drive-harddisk-symbolic",
            title: "Memória RAM",
            badgeText: badgeStr,
            badgeTone: "info",
            metricText: ramPct + "%",
            expanded: expanded,
        });
        card.add_child(header);

        if (expanded) {
            let body = new St.BoxLayout({ vertical: true, style_class: "dpi-card-body", style: "spacing: 8px;", x_expand: true });
            this._animateCardBody(body, "sys_ram");

            let ramSubText = (ramTotal > 0 ? ramUsed.toFixed(1) + " / " + ramTotal.toFixed(1) + " GB · " : "") + ramPct + "% em uso";
            let subLabel = new St.Label({
                text: ramSubText,
                style_class: "dpi-subtitle",
            });
            body.add_child(subLabel);
            body.add_child(this._makeProgressBar(ramPct, sysSeverityClass(ramPct, 70, 88), null, 290));

            card.add_child(body);
        }

        return card;
    }

    _buildDiskNetCard(disk, net) {
        let expanded = this._expandedCards.sys_disk_net !== false;
        let card = new St.BoxLayout({ vertical: true, style_class: "dpi-card", x_expand: true });

        let rawDisk = disk && (disk.used_pct !== undefined ? disk.used_pct : disk.disk_pct);
        let diskPct = clamp(Math.round(Number(rawDisk) || 0), 0, 100);
        let iface = (net && net.interface) || (disk && disk.path) || "/";

        let header = this._buildCardHeader({
            cardKey: "sys_disk_net",
            icon: "network-workgroup-symbolic",
            title: "Armazenamento & Rede",
            badgeText: iface,
            badgeTone: "info",
            metricText: diskPct + "%",
            expanded: expanded,
        });
        card.add_child(header);

        if (expanded) {
            let body = new St.BoxLayout({ vertical: true, style_class: "dpi-card-body", style: "spacing: 8px;", x_expand: true });
            this._animateCardBody(body, "sys_disk_net");

            // Disk Section
            let mountPoint = (disk && (disk.path || disk.mount_point)) || "/";
            body.add_child(this._makeSectionLabel("DISCO PRINCIPAL (" + mountPoint + ")"));

            let dUsed = Number(disk && (disk.used_gb !== undefined ? disk.used_gb : disk.disk_used_gb)) || 0;
            let dTotal = Number(disk && (disk.total_gb !== undefined ? disk.total_gb : disk.disk_total_gb)) || 0;
            let dSub = (dTotal > 0 ? dUsed.toFixed(0) + " / " + dTotal.toFixed(0) + " GB · " : "") + diskPct + "%";
            let dTemp = disk && (disk.temp_c !== undefined ? disk.temp_c : (disk.nvme_temp_c !== undefined ? disk.nvme_temp_c : disk.disk_temp_c));
            if (dTemp !== null && dTemp !== undefined) {
                dSub += " · NVMe: " + Math.round(Number(dTemp)) + "°C";
            }
            body.add_child(new St.Label({ text: dSub, style_class: "dpi-subtitle" }));
            body.add_child(this._makeProgressBar(diskPct, sysSeverityClass(diskPct, 80, 92), null, 290));

            // Network Section
            body.add_child(this._makeSectionLabel("REDE EM TEMPO REAL (" + iface + ")"));
            let netRow = new St.BoxLayout({ style: "spacing: 12px;", x_expand: true, y_align: Clutter.ActorAlign.CENTER });

            // Download
            let rxBox = new St.BoxLayout({ style: "spacing: 4px;", y_align: Clutter.ActorAlign.CENTER });
            rxBox.add_child(new St.Icon({
                icon_name: "network-receive-symbolic",
                icon_type: St.IconType.SYMBOLIC,
                icon_size: 13,
                y_align: Clutter.ActorAlign.CENTER,
            }));
            rxBox.add_child(new St.Label({
                text: (net && net.rx_text) || "0 KB/s",
                style_class: "dpi-card-metric",
                y_align: Clutter.ActorAlign.CENTER,
            }));
            netRow.add_child(rxBox);

            // Upload
            let txBox = new St.BoxLayout({ style: "spacing: 4px;", y_align: Clutter.ActorAlign.CENTER });
            txBox.add_child(new St.Icon({
                icon_name: "network-transmit-symbolic",
                icon_type: St.IconType.SYMBOLIC,
                icon_size: 13,
                y_align: Clutter.ActorAlign.CENTER,
            }));
            txBox.add_child(new St.Label({
                text: (net && net.tx_text) || "0 KB/s",
                style_class: "dpi-card-metric",
                y_align: Clutter.ActorAlign.CENTER,
            }));
            netRow.add_child(txBox);

            body.add_child(netRow);

            card.add_child(body);
        }

        return card;
    }

    /* ======================================================================
     * Tab 2: Antigravity View Usage
     * ====================================================================== */

    _renderAntigravityTab() {
        let ag = (this._data && this._data.antigravity) || {};
        let settings = (this._data && this._data.settings) || {};
        let pinnedQuota = settings.pinned_quota || "auto";

        // 2-Column Bento Grid: Left Column (Quotas) | Right Column (Session & Swarm, Histogram & Monthly)
        let grid = new St.BoxLayout({
            style_class: "dpi-bento-grid dpi-ag-columns",
            style: "spacing: 10px;",
            x_expand: true,
        });

        // Left Column: Quota cards
        let leftCol = new St.BoxLayout({
            vertical: true,
            style_class: "dpi-ag-col-left",
            style: "spacing: 8px; width: 336px;",
            x_expand: false,
        });
        let quotas = Array.isArray(ag.quotas) ? ag.quotas : [];
        if (quotas.length === 0) {
            let emptyCard = new St.BoxLayout({ vertical: true, style_class: "dpi-card", x_expand: true });
            emptyCard.add_child(new St.Label({
                text: ag.connected
                    ? "Nenhuma cota retornada pelo daemon Antigravity."
                    : "Daemon Antigravity offline ou inacessivel no momento.",
                style_class: "dpi-subtitle",
            }));
            leftCol.add_child(emptyCard);
        } else {
            for (let q of quotas) {
                leftCol.add_child(this._buildQuotaCard(q, pinnedQuota));
            }
        }
        grid.add_child(leftCol);

        // Right Column: Session & Swarm + 7-Day Histogram & Monthly Summary
        let rightCol = new St.BoxLayout({
            vertical: true,
            style_class: "dpi-ag-col-right",
            style: "spacing: 8px; width: 336px;",
            x_expand: false,
        });
        rightCol.add_child(this._buildSwarmSessionCard(ag));
        rightCol.add_child(this._buildHistogramMonthlyCard(ag));
        grid.add_child(rightCol);

        this._bodyStack.add_child(grid);
    }

    _buildQuotaCard(q, pinnedQuotaId) {
        let card = new St.BoxLayout({ vertical: true, style_class: "dpi-card", x_expand: true });
        let enabled = q.enabled !== false;
        let rem = enabled ? clamp(Math.round(Number(q.remaining_pct) || 0), 0, 100) : 0;
        let pace = enabled && q.pace_pct !== null && q.pace_pct !== undefined
            ? clamp(Number(q.pace_pct), 0, 100)
            : null;
        let tone = enabled ? quotaSeverityClass(rem) : "muted";
        let isPinned = pinnedQuotaId === q.id;

        let header = new St.BoxLayout({ style: "spacing: 6px;", y_align: Clutter.ActorAlign.CENTER });
        let nameLbl = new St.Label({
            text: q.name || q.short_name || q.id || "Cota",
            style_class: "dpi-card-title",
            x_expand: true,
        });
        nameLbl.clutter_text.ellipsize = Pango.EllipsizeMode.END;
        header.add_child(nameLbl);

        if (enabled) {
            header.add_child(new St.Label({
                text: rem + "%",
                style_class: "dpi-card-metric dpi-pill-text-" + tone,
            }));
        } else {
            header.add_child(this._makeBadge("Indisponivel", "muted"));
        }

        let pinBtn = new St.Button({
            style_class: isPinned ? "dpi-pin-btn dpi-pin-btn-active" : "dpi-pin-btn",
            can_focus: true,
            child: new St.Icon({
                icon_name: isPinned ? "starred-symbolic" : "non-starred-symbolic",
                icon_type: St.IconType.SYMBOLIC,
                icon_size: 13,
            }),
        });
        pinBtn.connect("clicked", () => {
            let nextPin = isPinned ? "auto" : q.id;
            this._dispatchCliAction(
                ["--pin-quota", String(nextPin)],
                nextPin === "auto" ? "Cota na TopBar: Automatico" : "Fixando " + (q.short_name || q.name) + " na TopBar..."
            );
        });
        header.add_child(pinBtn);
        card.add_child(header);

        // Progress bar + vertical Pace Marker (pace_pct is elapsed % of window; expected remaining = 100 - pace_pct)
        let remainingPaceMarker = (enabled && pace !== null && pace > 0) ? clamp(100 - pace, 0, 100) : null;
        card.add_child(this._makeProgressBar(rem, tone, remainingPaceMarker, 290));

        // Meta row: reset countdown + depletion ETA
        let metaRow = new St.BoxLayout({ style: "spacing: 6px;", y_align: Clutter.ActorAlign.CENTER });
        let resetTxt = !enabled
            ? "Nao disponivel no plano atual"
            : (q.reset_countdown && q.reset_countdown !== "--" ? "Reset em " + q.reset_countdown : "Janela ativa");
        metaRow.add_child(new St.Label({
            text: resetTxt,
            style_class: "dpi-subtitle",
            x_expand: true,
        }));

        let eta = stripEmojis(q.depletion_eta || "");
        if (enabled && eta) {
            metaRow.add_child(this._makeBadge("ETA " + eta, "warn"));
        } else if (enabled && pace !== null) {
            metaRow.add_child(new St.Label({
                text: "Pace " + Math.round(pace) + "%",
                style_class: "dpi-subtitle",
            }));
        }
        card.add_child(metaRow);

        return card;
    }

    _buildSwarmSessionCard(ag) {
        let card = new St.BoxLayout({ vertical: true, style_class: "dpi-card", x_expand: true });
        let swarm = ag.swarm || {};
        let ctx = ag.session_context || {};
        let agents = Array.isArray(swarm.agents) ? swarm.agents : [];
        let activeCount = Number(swarm.active_count) || agents.filter((a) => String(a.status).toUpperCase() === "WORKING").length;

        let header = new St.BoxLayout({ style: "spacing: 6px;", y_align: Clutter.ActorAlign.CENTER });
        header.add_child(new St.Icon({
            icon_name: "network-workgroup-symbolic",
            icon_type: St.IconType.SYMBOLIC,
            icon_size: 14,
        }));
        header.add_child(new St.Label({
            text: "Sessao Ativa & Swarm",
            style_class: "dpi-card-title",
            x_expand: true,
        }));
        header.add_child(this._makeBadge(
            activeCount > 0 ? activeCount + " WORKING" : "IDLE",
            activeCount > 0 ? "purple" : "muted"
        ));
        card.add_child(header);

        let project = ctx.active_project || ag.active_project || ctx.project || "Workspace ativo";
        card.add_child(new St.Label({
            text: "Projeto: " + project,
            style_class: "dpi-subtitle",
        }));

        // Context Tokens Bento Tiles (In, Cache, Out)
        let tilesRow = new St.BoxLayout({ style: "spacing: 6px;", x_expand: true });
        let tileSpecs = [
            { label: "IN", value: formatTokens(ctx.input_tokens) },
            { label: "CACHE", value: formatTokens(ctx.cache_read_tokens) },
            { label: "OUT", value: formatTokens(ctx.output_tokens) },
        ];
        for (let t of tileSpecs) {
            let tile = new St.BoxLayout({ vertical: true, style_class: "dpi-metric-tile", x_expand: true });
            tile.add_child(new St.Label({ text: t.label, style_class: "dpi-section-label" }));
            tile.add_child(new St.Label({ text: t.value, style_class: "dpi-metric-value" }));
            tilesRow.add_child(tile);
        }
        card.add_child(tilesRow);

        // Swarm Subagents List
        if (agents.length > 0) {
            card.add_child(this._makeSectionLabel("SUBAGENTES (" + agents.length + ")"));
            for (let agent of agents.slice(0, 8)) {
                let st = String(agent.status || "IDLE").toUpperCase();
                let isWorking = st === "WORKING";
                let row = new St.BoxLayout({ style_class: "dpi-swarm-row", y_align: Clutter.ActorAlign.CENTER });
                row.add_child(new St.Widget({
                    style_class: "dpi-status-dot " + (isWorking ? "dpi-dot-swarm" : "dpi-dot-muted"),
                    y_align: Clutter.ActorAlign.CENTER,
                }));
                let roleLbl = new St.Label({
                    text: agent.role || agent.name || agent.id || "agent",
                    style_class: "dpi-card-title",
                    x_expand: true,
                });
                roleLbl.clutter_text.ellipsize = Pango.EllipsizeMode.END;
                row.add_child(roleLbl);

                let steps = Number(agent.steps) || 0;
                row.add_child(new St.Label({
                    text: steps + " steps",
                    style_class: "dpi-subtitle",
                }));
                row.add_child(this._makeBadge(st, isWorking ? "purple" : "muted"));
                card.add_child(row);
            }
        }

        return card;
    }

    _buildHistogramMonthlyCard(ag) {
        let card = new St.BoxLayout({ vertical: true, style_class: "dpi-card", x_expand: true });

        let header = new St.BoxLayout({ style: "spacing: 6px;", y_align: Clutter.ActorAlign.CENTER });
        header.add_child(new St.Icon({
            icon_name: "utilities-system-monitor-symbolic",
            icon_type: St.IconType.SYMBOLIC,
            icon_size: 14,
        }));
        header.add_child(new St.Label({
            text: "Histograma 7 Dias & Mensal",
            style_class: "dpi-card-title",
            x_expand: true,
        }));

        let monthly = ag.monthly || {};
        if (monthly.month) {
            header.add_child(this._makeBadge(monthly.month, "info"));
        }
        card.add_child(header);

        // 7-Day Vertical Bar Chart
        let days = Array.isArray(ag.daily_histogram_7d) ? ag.daily_histogram_7d : [];
        if (days.length > 0) {
            let maxTok = 1;
            for (let d of days) {
                let tk = Number(d.tokens) || 0;
                if (tk > maxTok) maxTok = tk;
            }

            let histRow = new St.BoxLayout({ style_class: "dpi-hist-box", x_expand: true });
            for (let i = 0; i < days.length; i++) {
                let d = days[i];
                let tk = Number(d.tokens) || 0;
                let barH = tk > 0 ? clamp(Math.round((tk / maxTok) * 58), 4, 58) : 2;
                let isToday = i === days.length - 1;

                let col = new St.BoxLayout({
                    vertical: true,
                    style_class: "dpi-hist-col",
                    x_expand: true,
                    x_align: Clutter.ActorAlign.CENTER,
                });

                let track = new St.BoxLayout({
                    vertical: true,
                    style_class: "dpi-hist-track",
                    x_align: Clutter.ActorAlign.CENTER,
                    y_align: Clutter.ActorAlign.END,
                });
                let spacer = new St.Widget({ y_expand: true });
                let bar = new St.Widget({
                    style_class: isToday ? "dpi-hist-bar dpi-hist-bar-today" : "dpi-hist-bar",
                    style: "height: " + barH + "px;",
                });
                track.add_child(spacer);
                track.add_child(bar);

                col.add_child(new St.Label({
                    text: formatTokens(tk),
                    style_class: "dpi-hist-label dpi-muted",
                    x_align: Clutter.ActorAlign.CENTER,
                }));
                col.add_child(track);
                col.add_child(new St.Label({
                    text: d.label || (d.date ? String(d.date).slice(5) : ""),
                    style_class: "dpi-hist-label",
                    x_align: Clutter.ActorAlign.CENTER,
                }));
                histRow.add_child(col);
            }
            card.add_child(histRow);
        }

        // Monthly Summary & Top Projects
        let totalMonth = Number(monthly.total_tokens) || 0;
        let summaryRow = new St.BoxLayout({ style: "spacing: 6px;", y_align: Clutter.ActorAlign.CENTER });
        summaryRow.add_child(new St.Label({
            text: "Total Mensal: " + formatTokens(totalMonth) + " tokens",
            style_class: "dpi-card-metric",
            x_expand: true,
        }));
        if (monthly.cache_tokens) {
            summaryRow.add_child(new St.Label({
                text: "Cache " + formatTokens(monthly.cache_tokens),
                style_class: "dpi-subtitle",
            }));
        }
        card.add_child(summaryRow);

        let topProjects = Array.isArray(monthly.top_projects) ? monthly.top_projects : [];
        if (topProjects.length > 0) {
            card.add_child(this._makeSectionLabel("TOP PROJETOS"));
            for (let proj of topProjects.slice(0, 3)) {
                let pName = typeof proj === "string" ? proj : (proj.name || proj.project || "Projeto");
                let pTok = typeof proj === "object" ? (proj.tokens || proj.total_tokens || 0) : 0;
                let row = new St.BoxLayout({ style: "spacing: 6px;" });
                let nl = new St.Label({ text: pName, style_class: "dpi-subtitle", x_expand: true });
                nl.clutter_text.ellipsize = Pango.EllipsizeMode.END;
                row.add_child(nl);
                if (pTok) {
                    row.add_child(new St.Label({ text: formatTokens(pTok), style_class: "dpi-card-metric" }));
                }
                card.add_child(row);
            }
        }

        return card;
    }

    /* ======================================================================
     * Tab 3: Settings
     * ====================================================================== */

    _renderSettingsTab() {
        let settings = (this._data && this._data.settings) || {
            pin_mouse: true,
            pin_headset: false,
            pin_gamepad: false,
            pin_keyboard: false,
            pinned_quota: "auto",
            battery_alert_threshold: 20,
            poll_interval: 5,
            theme_mode: "auto",
        };

        let grid = new St.BoxLayout({
            style_class: "dpi-bento-grid",
            style: "spacing: 10px;",
            x_expand: true,
        });

        // Left Column: Fixar na TopBar + Cota Fixada
        let colLeft = new St.BoxLayout({
            vertical: true,
            style_class: "dpi-bento-col",
            style: "spacing: 8px; width: 336px;",
            x_expand: false,
        });

        // 1. Pin devices on TopBar
        let pinCard = new St.BoxLayout({ vertical: true, style_class: "dpi-card", x_expand: true });
        pinCard.add_child(this._makeSectionLabel("FIXAR NA TOPBAR"));

        let pinSpecs = [
            { key: "mouse", field: "pin_mouse", label: "Mouse AJAZZ AJ179 V2", icon: "input-mouse-symbolic" },
            { key: "headset", field: "pin_headset", label: "Headset Havit Fuxi H3", icon: "audio-headphones-symbolic" },
            { key: "gamepad", field: "pin_gamepad", label: "Controles GameSir / EasySMX", icon: "input-gaming-symbolic" },
            { key: "keyboard", field: "pin_keyboard", label: "Teclado Machenike K500", icon: "input-keyboard-symbolic" },
        ];
        for (let spec of pinSpecs) {
            let isOn = Boolean(settings[spec.field]);
            let row = new St.BoxLayout({ style_class: "dpi-setting-row", y_align: Clutter.ActorAlign.CENTER });
            row.add_child(new St.Icon({
                icon_name: spec.icon,
                icon_type: St.IconType.SYMBOLIC,
                icon_size: 14,
            }));
            row.add_child(new St.Label({
                text: spec.label,
                style_class: "dpi-card-title",
                x_expand: true,
            }));
            let toggle = new St.Button({
                label: isOn ? "FIXADO" : "AUTO",
                style_class: isOn ? "dpi-toggle dpi-toggle-on" : "dpi-toggle",
                can_focus: true,
            });
            toggle.connect("clicked", () => {
                let nextVal = isOn ? "off" : "on";
                this._dispatchCliAction(
                    ["--pin-device", spec.key + "=" + nextVal],
                    "Atualizando pin de " + spec.key + "..."
                );
            });
            row.add_child(toggle);
            pinCard.add_child(row);
        }
        colLeft.add_child(pinCard);

        // 2. Pinned Quota
        let quotaCard = new St.BoxLayout({ vertical: true, style_class: "dpi-card", x_expand: true });
        quotaCard.add_child(this._makeSectionLabel("COTA ANTIGRAVITY FIXADA NA BARRA"));
        quotaCard.add_child(this._makeChipRow(
            PINNED_QUOTA_OPTIONS.slice(0, 3).map((o) => ({ label: o.label, value: o.id })),
            settings.pinned_quota || "auto",
            (id) => this._dispatchCliAction(["--pin-quota", id], "Cota na barra: " + id)
        ));
        quotaCard.add_child(this._makeChipRow(
            PINNED_QUOTA_OPTIONS.slice(3).map((o) => ({ label: o.label, value: o.id })),
            settings.pinned_quota || "auto",
            (id) => this._dispatchCliAction(["--pin-quota", id], "Cota na barra: " + id)
        ));
        colLeft.add_child(quotaCard);
        grid.add_child(colLeft);

        // Right Column: Limiar de Bateria, Intervalo de Coleta & Tema
        let colRight = new St.BoxLayout({
            vertical: true,
            style_class: "dpi-bento-col",
            style: "spacing: 8px; width: 336px;",
            x_expand: false,
        });

        // 3. Telemetry & Appearance
        let sysCard = new St.BoxLayout({ vertical: true, style_class: "dpi-card", x_expand: true });

        sysCard.add_child(this._makeSectionLabel("LIMIAR DE ALERTA DE BATERIA"));
        sysCard.add_child(this._makeChipRow(
            ALERT_THRESHOLD_OPTIONS.map((v) => ({ label: v + "%", value: v })),
            Number(settings.battery_alert_threshold) || 20,
            (v) => this._dispatchCliAction(["--set-alert-threshold", String(v)], "Limiar de bateria: " + v + "%")
        ));

        sysCard.add_child(this._makeSectionLabel("INTERVALO DE COLETA"));
        sysCard.add_child(this._makeChipRow(
            POLL_INTERVAL_OPTIONS.map((v) => ({ label: v + "s", value: v })),
            Number(settings.poll_interval) || 5,
            (v) => {
                this._pollSeconds = v;
                this._schedulePoll();
                this._dispatchCliAction(["--set-poll-interval", String(v)], "Intervalo ajustado para " + v + "s");
            }
        ));

        sysCard.add_child(this._makeSectionLabel("TEMA DA CAPSULA E POPOVER"));
        sysCard.add_child(this._makeChipRow(
            THEME_MODE_OPTIONS.map((t) => ({ label: t.label, value: t.id })),
            settings.theme_mode || "auto",
            (mode) => this._dispatchCliAction(["--set-theme", mode], "Tema alterado para " + mode)
        ));

        sysCard.add_child(new St.Label({
            text: "Atalho global: Super + Alt + I",
            style_class: "dpi-subtitle",
        }));

        colRight.add_child(sysCard);
        grid.add_child(colRight);

        this._bodyStack.add_child(grid);
    }

    /* ======================================================================
     * Reusable UI Primitives
     * ====================================================================== */

    _buildCardHeader(opts) {
        let row = new St.BoxLayout({
            style_class: "dpi-card-header",
            x_expand: true,
            y_align: Clutter.ActorAlign.CENTER,
        });
        if (opts.icon) {
            row.add_child(this._makeDeviceIcon(opts.icon, null, 16));
        }

        let titleCol = new St.BoxLayout({ vertical: true, x_expand: true });
        titleCol.add_child(new St.Label({
            text: opts.title,
            style_class: "dpi-card-title",
        }));
        row.add_child(titleCol);

        if (opts.badgeText) {
            row.add_child(this._makeBadge(opts.badgeText, opts.badgeTone || "muted"));
        }

        if (opts.metricText) {
            let mCls = "dpi-card-metric";
            if (opts.metricTone && opts.metricTone !== "default") {
                mCls += " dpi-pill-text-" + opts.metricTone;
            }
            row.add_child(new St.Label({ text: opts.metricText, style_class: mCls }));
        }

        row.add_child(new St.Icon({
            icon_name: opts.expanded ? "pan-down-symbolic" : "pan-end-symbolic",
            icon_type: St.IconType.SYMBOLIC,
            icon_size: 13,
        }));

        let btn = new St.Button({
            style_class: "dpi-card-header-btn",
            x_expand: true,
            can_focus: true,
            child: row,
        });
        btn.connect("clicked", () => {
            let nextExpanded = !this._expandedCards[opts.cardKey];
            this._expandedCards[opts.cardKey] = nextExpanded;
            this._justExpandedCard = nextExpanded ? opts.cardKey : null;
            this._renderPopover();
        });
        return btn;
    }

    _makeBadge(text, tone) {
        return new St.Label({
            text: String(text),
            style_class: "dpi-badge dpi-badge-" + (tone || "muted"),
            y_align: Clutter.ActorAlign.CENTER,
        });
    }

    _makeSectionLabel(text) {
        return new St.Label({
            text: String(text),
            style_class: "dpi-section-label",
        });
    }

    _makeProgressBar(percent, tone, pacePercent, customWidth) {
        let barWidth = customWidth || PROGRESS_TRACK_WIDTH;
        let pct = clamp(Number(percent) || 0, 0, 100);
        let fillW = Math.round((pct / 100) * barWidth);

        let container = new St.Widget({
            layout_manager: new Clutter.FixedLayout(),
            width: barWidth,
            height: 11,
            x_expand: false,
        });

        let track = new St.Widget({
            style_class: "dpi-bar-track",
            width: barWidth,
            height: 7,
        });
        track.set_position(0, 2);
        container.add_child(track);

        if (fillW > 0) {
            let fill = new St.Widget({
                style_class: "dpi-bar-fill dpi-fill-" + (tone || "info"),
                width: Math.max(4, fillW),
                height: 7,
            });
            fill.set_position(0, 2);
            container.add_child(fill);
        }

        if (pacePercent !== null && pacePercent !== undefined && !isNaN(pacePercent)) {
            // Pace marker represents expected remaining budget along the window (100 - elapsed_pct)
            // or direct pace position if provided as remaining-space pace.
            let markerX = clamp(Math.round((Number(pacePercent) / 100) * barWidth), 2, barWidth - 4);
            let marker = new St.Widget({
                style_class: "dpi-pace-marker",
                width: 2,
                height: 11,
            });
            marker.set_position(markerX, 0);
            container.add_child(marker);
        }

        return container;
    }

    _makeChipRow(items, activeValue, onSelect) {
        let row = new St.BoxLayout({ style_class: "dpi-chip-row", x_expand: true });
        for (let item of items) {
            let active = activeValue === item.value;
            let btn = new St.Button({
                label: String(item.label),
                style_class: active ? "dpi-chip dpi-chip-active" : "dpi-chip",
                x_expand: true,
                can_focus: true,
            });
            btn.connect("clicked", () => onSelect(item.value));
            row.add_child(btn);
        }
        return row;
    }

    _makeActionButton(iconName, label, variant, onClick) {
        let content = new St.BoxLayout({
            style: "spacing: 5px;",
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
        });
        if (iconName) {
            content.add_child(new St.Icon({
                icon_name: iconName,
                icon_type: St.IconType.SYMBOLIC,
                icon_size: 13,
            }));
        }
        content.add_child(new St.Label({
            text: label,
            y_align: Clutter.ActorAlign.CENTER,
        }));

        let cls = "dpi-action-btn";
        if (variant === "primary") cls += " dpi-action-btn-primary";
        else if (variant === "warn") cls += " dpi-action-btn-warn";

        let btn = new St.Button({
            style_class: cls,
            x_expand: true,
            can_focus: true,
            child: content,
        });
        btn.connect("clicked", onClick);
        return btn;
    }

    _extractPlanName(plan) {
        if (!plan) return "";
        if (typeof plan === "string") return plan;
        return plan.name || plan.tier || plan.plan_name || "";
    }

    _extractPlanCredits(plan) {
        if (!plan || typeof plan !== "object") return "";
        if (plan.credits_label) return String(plan.credits_label);
        if (plan.credits !== null && plan.credits !== undefined) {
            return String(plan.credits) + " cr";
        }
        if (plan.prompt_credits !== null && plan.prompt_credits !== undefined) {
            return String(plan.prompt_credits) + " cr";
        }
        return "";
    }

    _extractActiveModelName(activeModel) {
        if (!activeModel) return "";
        if (typeof activeModel === "string") return activeModel;
        return activeModel.name || activeModel.label || activeModel.id || "";
    }
}

function main(metadata, orientation, panelHeight, instanceId) {
    return new DynamicPeripheralIslandApplet(metadata, orientation, panelHeight, instanceId);
}

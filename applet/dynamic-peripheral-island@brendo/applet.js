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

const UUID = "dynamic-peripheral-island@brendo";
const HOTKEY_NAME = "dpi-toggle-island";
const HOTKEY_BINDING = "<Super><Alt>i";
const DEFAULT_POLL_SECONDS = 5;
const MORPH_DURATION_MS = 4000;
const ALERT_COOLDOWN_MS = 60000;
const PROGRESS_TRACK_WIDTH = 398;

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

        // Runtime state
        this._data = null;
        this._activeTab = "peripherals";
        this._expandedCards = {
            mouse: false,
            headset: false,
            gamepad: false,
            keyboard: false,
        };
        this._resolvedTheme = "dark";
        this._pollSeconds = DEFAULT_POLL_SECONDS;
        this._pollTimerId = 0;
        this._morphTimerId = 0;
        this._toastTimerId = 0;
        this._idleAttachId = 0;
        this._isPolling = false;
        this._prewarmed = false;
        this._destroyed = false;
        this._unifiedCenterBox = null;
        this._taggedClockActors = [];
        this._seenAlerts = {};
        this._toastState = null;

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
    }

    /* ======================================================================
     * TopBar Unified Capsule Lifecycle
     * ====================================================================== */

    _buildTopBar() {
        this._leadDivider = new St.Widget({ style_class: "dpi-capsule-divider" });
        this._leadDivider.y_align = Clutter.ActorAlign.CENTER;
        this._leadDivider.hide();
        this.actor.add_child(this._leadDivider);

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
        this.actor.add_child(this._segPeripherals);

        // Mid divider between Peripherals and Antigravity
        this._midDivider = new St.Widget({ style_class: "dpi-capsule-divider" });
        this._midDivider.y_align = Clutter.ActorAlign.CENTER;
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
        this._segPeripherals.destroy_all_children();
        this._segPeripherals.add_child(this._makePillItem("input-mouse-symbolic", "--", "muted"));

        this._segAntigravity.destroy_all_children();
        this._segAntigravity.add_child(this._makePillItem("applications-science-symbolic", "AG", "muted"));
    }

    _makePillItem(iconName, text, tone, extraDotClass) {
        let item = new St.BoxLayout({
            style_class: "dpi-pill-item",
            y_align: Clutter.ActorAlign.CENTER,
        });
        if (iconName) {
            item.add_child(new St.Icon({
                icon_name: iconName,
                icon_type: St.IconType.SYMBOLIC,
                style_class: "dpi-pill-icon",
            }));
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
            let hasLeadingSibling = false;
            for (let i = 0; i < children.length; i++) {
                let child = children[i];
                if (child === this.actor) continue;
                let siblingUuid = child._applet ? child._applet._uuid : "";
                if (siblingUuid === "calendar@cinnamon.org" || i < children.indexOf(this.actor)) {
                    child.add_style_class_name("dpi-capsule-clock");
                    this._taggedClockActors.push(child);
                    hasLeadingSibling = true;
                }
            }

            if (hasLeadingSibling) {
                this._leadDivider.show();
            } else {
                this._leadDivider.hide();
            }
        } else {
            this.actor.add_style_class_name("dpi-standalone-capsule");
            this._applyThemeToActor(this.actor, this._resolvedTheme);
            this._leadDivider.hide();
        }
    }

    _detachUnifiedCapsule() {
        if (this._unifiedCenterBox) {
            try {
                this._unifiedCenterBox.remove_style_class_name("dpi-unified-capsule");
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

        for (let item of this._themeSignalIds) {
            try {
                item.settings.disconnect(item.id);
            } catch (e) {
                // ignore
            }
        }
        this._themeSignalIds = [];

        this._detachUnifiedCapsule();

        if (this.menu) {
            try {
                this.menu.destroy();
            } catch (e) {
                // ignore
            }
            this.menu = null;
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
        if (this.menu.isOpen && this._activeTab === tabName) {
            this.menu.close(true);
            return;
        }
        this._activeTab = tabName;
        this._renderPopover();
        if (!this.menu.isOpen) {
            this.menu.open(true);
        }
        this._refreshNow();
    }

    _toggleIsland() {
        if (!this.menu) return;
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
                } else if (this.menu && this.menu.isOpen) {
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
        };
        for (let tabId of ["peripherals", "antigravity", "settings"]) {
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
                gamepad: "input-gaming-symbolic",
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
                this._segPeripherals.add_child(this._makePillItem(icon, text, tone));
                pillCount++;
            }
        } else {
            let mouse = peripherals.mouse || {};
            let showMouse = settings.pin_mouse !== false || (mouse.connected && !mouse.standby);
            if (showMouse) {
                let bat = mouse.battery;
                let text = mouse.connected
                    ? (bat !== null && bat !== undefined ? bat + "%" : (mouse.standby ? "Standby" : "OK"))
                    : "OFF";
                let tone = !mouse.connected ? "muted" : (mouse.charging ? "ok" : pctSeverityClass(bat, threshold));
                let icon = mouse.charging ? "battery-full-charging-symbolic" : "input-mouse-symbolic";
                this._segPeripherals.add_child(this._makePillItem(icon, text, tone));
                pillCount++;
            }

            let headset = peripherals.headset || {};
            let showHeadset = Boolean(settings.pin_headset) || Boolean(headset.connected && headset.active);
            if (showHeadset) {
                let bat = headset.battery;
                let text = headset.connected
                    ? (bat !== null && bat !== undefined ? bat + "%" : (headset.connection_type === "2.4GHz" ? "2.4GHz" : "BT"))
                    : "OFF";
                let tone = !headset.connected ? "muted" : (headset.alsa_zero_bug ? "warn" : pctSeverityClass(bat, threshold));
                this._segPeripherals.add_child(this._makePillItem("audio-headphones-symbolic", text, tone));
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
                this._segPeripherals.add_child(this._makePillItem("input-gaming-symbolic", text, tone));
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
                this._segPeripherals.add_child(this._makePillItem("input-keyboard-symbolic", text, tone));
                pillCount++;
            }
        }

        if (pillCount === 0) {
            this._segPeripherals.add_child(this._makePillItem("input-mouse-symbolic", "Hub", "muted"));
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

        this._segAntigravity.add_child(
            this._makePillItem("applications-science-symbolic", agText, agTone, dotClass)
        );
        if (swarmCount > 0) {
            this._segAntigravity.add_child(
                this._makePillItem("network-workgroup-symbolic", String(swarmCount), "purple")
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
     * Popover Bento Grid UI
     * ====================================================================== */

    _buildPopover(orientation) {
        this.menuManager = new PopupMenu.PopupMenuManager(this);
        this.menu = new Applet.AppletPopupMenu(this, orientation);
        this.menuManager.addMenu(this.menu);

        this.menu.connect("open-state-changed", (menu, isOpen) => {
            this._syncSegmentHighlight();
            if (isOpen) {
                this._renderPopover();
            }
        });

        let menuItem = new PopupMenu.PopupBaseMenuItem({
            reactive: false,
            hover: false,
            focusOnHover: false,
            style_class: "",
        });

        this._popoverRoot = new St.BoxLayout({
            vertical: true,
            style_class: "dpi-popover-root dpi-theme-dark",
        });

        // Header bar
        this._headerBox = new St.BoxLayout({
            style_class: "dpi-header-row",
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

        menuItem.addActor(this._popoverRoot, { expand: true, span: -1 });
        this.menu.addMenuItem(menuItem);
    }

    _renderPopover() {
        if (!this._popoverRoot) return;
        this._applyTheme();
        this._renderHeader();
        this._renderTabBar();
        this._renderToastBanner();

        this._bodyStack.destroy_all_children();
        if (this._activeTab === "peripherals") {
            this._renderPeripheralsTab();
        } else if (this._activeTab === "antigravity") {
            this._renderAntigravityTab();
        } else {
            this._renderSettingsTab();
        }
    }

    _renderHeader() {
        this._headerBox.destroy_all_children();

        let ag = (this._data && this._data.antigravity) || {};
        let planName = this._extractPlanName(ag.plan);
        let activeModel = this._extractActiveModelName(ag.active_model);

        let leftCol = new St.BoxLayout({ vertical: true, x_expand: true });
        let titleRow = new St.BoxLayout({ style: "spacing: 6px;", y_align: Clutter.ActorAlign.CENTER });
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
        if (planName) {
            titleRow.add_child(this._makeBadge(planName, "purple"));
        }
        leftCol.add_child(titleRow);

        if (activeModel) {
            leftCol.add_child(new St.Label({
                text: activeModel,
                style_class: "dpi-subtitle",
            }));
        }
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
        this._tabBar.destroy_all_children();
        let tabs = [
            { id: "peripherals", label: "Perifericos", icon: "input-mouse-symbolic" },
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
                if (this._activeTab !== tab.id) {
                    this._activeTab = tab.id;
                    this._syncSegmentHighlight();
                    this._renderPopover();
                }
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

        this._bodyStack.add_child(this._buildMouseCard(devices.mouse || {}, threshold));
        this._bodyStack.add_child(this._buildHeadsetCard(devices.headset || {}, threshold));
        this._bodyStack.add_child(this._buildGamepadCard(devices.gamepad || {}, threshold));
        this._bodyStack.add_child(this._buildKeyboardCard(devices.keyboard || {}));
    }

    _buildMouseCard(mouse, threshold) {
        let expanded = Boolean(this._expandedCards.mouse);
        let card = new St.BoxLayout({ vertical: true, style_class: "dpi-card", x_expand: true });

        let connType = mouse.connection_type || (mouse.connected ? "2.4GHz" : "Desconectado");
        let bat = mouse.battery;
        let batLabel = bat !== null && bat !== undefined ? bat + "%" : (mouse.standby ? "Standby" : "--");
        let tone = !mouse.connected ? "muted" : (mouse.charging ? "ok" : pctSeverityClass(bat, threshold));

        let header = this._buildCardHeader({
            cardKey: "mouse",
            icon: "input-mouse-symbolic",
            title: "AJAZZ AJ179 V2",
            badgeText: mouse.charging ? connType + " / Chg" : connType,
            badgeTone: mouse.connected ? (mouse.standby ? "warn" : "info") : "muted",
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
            icon: "input-gaming-symbolic",
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
     * Tab 2: Antigravity View Usage
     * ====================================================================== */

    _renderAntigravityTab() {
        let ag = (this._data && this._data.antigravity) || {};
        let settings = (this._data && this._data.settings) || {};
        let pinnedQuota = settings.pinned_quota || "auto";

        // 1. Hero Header: Plan, Credits, Active Model
        let hero = new St.BoxLayout({ vertical: true, style_class: "dpi-hero-box", x_expand: true });
        let topRow = new St.BoxLayout({ style: "spacing: 6px;", y_align: Clutter.ActorAlign.CENTER });
        topRow.add_child(new St.Icon({
            icon_name: "applications-science-symbolic",
            icon_type: St.IconType.SYMBOLIC,
            icon_size: 15,
        }));
        topRow.add_child(new St.Label({
            text: "Antigravity View Usage",
            style_class: "dpi-card-title",
            x_expand: true,
        }));

        let planName = this._extractPlanName(ag.plan) || (ag.connected ? "Connected" : "Offline");
        topRow.add_child(this._makeBadge(planName, ag.connected ? "purple" : "muted"));
        hero.add_child(topRow);

        let modelName = this._extractActiveModelName(ag.active_model) || "Modelo nao detectado";
        let creditsStr = this._extractPlanCredits(ag.plan);
        let modelRow = new St.BoxLayout({ style: "spacing: 6px;", y_align: Clutter.ActorAlign.CENTER });
        modelRow.add_child(new St.Label({
            text: "Modelo Ativo:",
            style_class: "dpi-subtitle",
        }));
        modelRow.add_child(new St.Label({
            text: modelName,
            style_class: "dpi-card-metric",
            x_expand: true,
        }));
        if (creditsStr) {
            modelRow.add_child(this._makeBadge(creditsStr, "info"));
        }
        hero.add_child(modelRow);
        this._bodyStack.add_child(hero);

        // 2. Quota Cards with Pace Marker & Pin-to-TopBar
        let quotas = Array.isArray(ag.quotas) ? ag.quotas : [];
        if (quotas.length === 0) {
            let emptyCard = new St.BoxLayout({ vertical: true, style_class: "dpi-card", x_expand: true });
            emptyCard.add_child(new St.Label({
                text: ag.connected
                    ? "Nenhuma cota retornada pelo daemon Antigravity."
                    : "Daemon Antigravity offline ou inacessivel no momento.",
                style_class: "dpi-subtitle",
            }));
            this._bodyStack.add_child(emptyCard);
        } else {
            for (let q of quotas) {
                this._bodyStack.add_child(this._buildQuotaCard(q, pinnedQuota));
            }
        }

        // 3. Active Session & Swarm Card
        this._bodyStack.add_child(this._buildSwarmSessionCard(ag));

        // 4. 7-Day Histogram & Monthly Summary Card
        this._bodyStack.add_child(this._buildHistogramMonthlyCard(ag));
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
        card.add_child(this._makeProgressBar(rem, tone, remainingPaceMarker));

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
        this._bodyStack.add_child(pinCard);

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
        this._bodyStack.add_child(quotaCard);

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

        this._bodyStack.add_child(sysCard);
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
        row.add_child(new St.Icon({
            icon_name: opts.icon,
            icon_type: St.IconType.SYMBOLIC,
            icon_size: 16,
        }));

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
            this._expandedCards[opts.cardKey] = !this._expandedCards[opts.cardKey];
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

    _makeProgressBar(percent, tone, pacePercent) {
        let pct = clamp(Number(percent) || 0, 0, 100);
        let fillW = Math.round((pct / 100) * PROGRESS_TRACK_WIDTH);

        let container = new St.Widget({
            layout_manager: new Clutter.FixedLayout(),
            width: PROGRESS_TRACK_WIDTH,
            height: 11,
            x_expand: false,
        });

        let track = new St.Widget({
            style_class: "dpi-bar-track",
            width: PROGRESS_TRACK_WIDTH,
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
            let markerX = clamp(Math.round((Number(pacePercent) / 100) * PROGRESS_TRACK_WIDTH), 2, PROGRESS_TRACK_WIDTH - 4);
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

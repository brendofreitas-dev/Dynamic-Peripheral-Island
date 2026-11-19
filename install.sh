#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPLET_UUID="dynamic-peripheral-island@brendo"
APPLET_SRC="${SCRIPT_DIR}/applet/${APPLET_UUID}"
APPLET_DEST="${HOME}/.local/share/cinnamon/applets/${APPLET_UUID}"
BIN_SRC="${SCRIPT_DIR}/bin/dpi-hub"
BIN_DEST="${HOME}/.local/bin/dpi-hub"
UDEV_SRC="${SCRIPT_DIR}/udev/99-dynamic-peripheral-island.rules"
UDEV_DEST="/etc/udev/rules.d/99-dynamic-peripheral-island.rules"
PANEL_ENTRY="panel2:center:1:${APPLET_UUID}:99"

echo "[DPI] Installing Dynamic Peripheral Island..."

# 1. Install CLI binary symlink in ~/.local/bin/dpi-hub
mkdir -p "${HOME}/.local/bin"
if [ -f "${BIN_SRC}" ]; then
    chmod +x "${BIN_SRC}"
    ln -sf "${BIN_SRC}" "${BIN_DEST}"
    echo "[DPI] Linked CLI: ${BIN_DEST} -> ${BIN_SRC}"
else
    echo "[DPI] WARNING: ${BIN_SRC} not found; skipping CLI symlink." >&2
fi

# 2. Install Cinnamon Applet
if [ ! -d "${APPLET_SRC}" ]; then
    echo "[DPI] ERROR: Applet source directory not found at ${APPLET_SRC}" >&2
    exit 1
fi
mkdir -p "${HOME}/.local/share/cinnamon/applets"
rm -rf "${APPLET_DEST}"
cp -a "${APPLET_SRC}" "${APPLET_DEST}"
echo "[DPI] Installed Cinnamon applet to ${APPLET_DEST}"

# 3. Register applet in org.cinnamon enabled-applets at panel2:center:1 (next to calendar@cinnamon.org)
if command -v gsettings >/dev/null 2>&1; then
    CURRENT_APPLETS="$(gsettings get org.cinnamon enabled-applets 2>/dev/null || true)"
    if [ -n "${CURRENT_APPLETS}" ]; then
        UPDATED_APPLETS="$(python3 - "${CURRENT_APPLETS}" "${APPLET_UUID}" "${PANEL_ENTRY}" <<'PYEOF'
import ast
import sys

raw, uuid, entry = sys.argv[1], sys.argv[2], sys.argv[3]
items = ast.literal_eval(raw)
if not isinstance(items, list):
    sys.exit(1)

# Remove any previous registration of this applet to stay idempotent
cleaned = [x for x in items if f":{uuid}:" not in x]

# Insert immediately after calendar@cinnamon.org if present, else append
insert_idx = len(cleaned)
for idx, val in enumerate(cleaned):
    if "calendar@cinnamon.org" in val:
        insert_idx = idx + 1
        break

cleaned.insert(insert_idx, entry)
print(repr(cleaned))
PYEOF
)"
        if [ -n "${UPDATED_APPLETS}" ]; then
            gsettings set org.cinnamon enabled-applets "${UPDATED_APPLETS}"
            echo "[DPI] Registered applet in org.cinnamon enabled-applets (${PANEL_ENTRY})"
        fi
    else
        echo "[DPI] WARNING: Could not read org.cinnamon enabled-applets; skipping panel registration."
    fi
else
    echo "[DPI] WARNING: gsettings not found; skipping Cinnamon panel registration."
fi

# 4. Install udev rule via pkexec if not already present
if [ -f "${UDEV_SRC}" ]; then
    if [ -f "${UDEV_DEST}" ]; then
        echo "[DPI] udev rule already installed at ${UDEV_DEST}"
    else
        if [ -n "${DISPLAY:-}" ] && command -v pkexec >/dev/null 2>&1; then
            echo "[DPI] Installing udev rules to ${UDEV_DEST} (requires authorization)..."
            if pkexec sh -c "cp '${UDEV_SRC}' '${UDEV_DEST}' && udevadm control --reload-rules && udevadm trigger"; then
                echo "[DPI] Installed and reloaded udev rules."
            else
                echo "[DPI] WARNING: pkexec udev install skipped or cancelled."
                echo "[DPI] You can install manually with:"
                echo "      sudo cp '${UDEV_SRC}' '${UDEV_DEST}' && sudo udevadm control --reload-rules && sudo udevadm trigger"
            fi
        else
            echo "[DPI] Non-interactive session or pkexec unavailable; skipping automatic udev install."
            echo "[DPI] Install udev rules manually with:"
            echo "      sudo cp '${UDEV_SRC}' '${UDEV_DEST}' && sudo udevadm control --reload-rules && sudo udevadm trigger"
        fi
    fi
fi

# 5. Reload Cinnamon applet and theme via D-Bus
if command -v dbus-send >/dev/null 2>&1 && [ -n "${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
    dbus-send --session --dest=org.Cinnamon --type=method_call \
        /org/Cinnamon org.Cinnamon.ReloadTheme >/dev/null 2>&1 || true
    echo "[DPI] Reloaded Cinnamon theme via org.Cinnamon.ReloadTheme."

    if dbus-send --session --dest=org.Cinnamon --type=method_call \
        /org/Cinnamon org.Cinnamon.ReloadXlet \
        "string:${APPLET_UUID}" "string:APPLET" >/dev/null 2>&1; then
        echo "[DPI] Reloaded Cinnamon applet via org.Cinnamon.ReloadXlet."
    else
        echo "[DPI] Cinnamon D-Bus reload unavailable; restart Cinnamon with Alt+F2 -> r -> Enter if needed."
    fi
else
    echo "[DPI] Session D-Bus unavailable; restart Cinnamon with Alt+F2 -> r -> Enter to activate."
fi

echo "[DPI] Installation complete! Toggle the island anytime with Super + Alt + I."

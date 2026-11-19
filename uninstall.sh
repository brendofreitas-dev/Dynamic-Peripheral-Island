#!/usr/bin/env bash
set -euo pipefail

APPLET_UUID="dynamic-peripheral-island@brendo"
APPLET_DEST="${HOME}/.local/share/cinnamon/applets/${APPLET_UUID}"
BIN_DEST="${HOME}/.local/bin/dpi-hub"

echo "[DPI] Uninstalling Dynamic Peripheral Island..."

# 1. Remove from org.cinnamon enabled-applets
if command -v gsettings >/dev/null 2>&1; then
    CURRENT_APPLETS="$(gsettings get org.cinnamon enabled-applets 2>/dev/null || true)"
    if [ -n "${CURRENT_APPLETS}" ]; then
        UPDATED_APPLETS="$(python3 - "${CURRENT_APPLETS}" "${APPLET_UUID}" <<'PYEOF'
import ast
import sys

raw, uuid = sys.argv[1], sys.argv[2]
items = ast.literal_eval(raw)
if not isinstance(items, list):
    sys.exit(1)

cleaned = [x for x in items if f":{uuid}:" not in x]
print(repr(cleaned))
PYEOF
)"
        if [ -n "${UPDATED_APPLETS}" ]; then
            gsettings set org.cinnamon enabled-applets "${UPDATED_APPLETS}"
            echo "[DPI] Removed ${APPLET_UUID} from org.cinnamon enabled-applets."
        fi
    fi
fi

# 2. Remove installed applet directory
if [ -d "${APPLET_DEST}" ]; then
    rm -rf "${APPLET_DEST}"
    echo "[DPI] Removed ${APPLET_DEST}"
fi

# 3. Remove ~/.local/bin/dpi-hub symlink/wrapper
if [ -L "${BIN_DEST}" ] || [ -f "${BIN_DEST}" ]; then
    rm -f "${BIN_DEST}"
    echo "[DPI] Removed ${BIN_DEST}"
fi

echo "[DPI] Uninstallation complete."
